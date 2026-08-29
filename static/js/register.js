/**
 * Registration-page-only JS. Loaded via {% block extra_js %} on
 * members/register.html only, the same pattern static/js/home.js uses
 * for the landing page (see LANDING_PAGE_EXPERIENCE.md).
 *
 * IMPORTANT: this is presentation-only progressive enhancement.
 *   - Every field from MemberRegistrationForm still lives in one real
 *     <form>, posted in one request to the existing register_view /
 *     MemberRegistrationForm exactly as before. This file only changes
 *     which fields are *visible* at a given moment and adds client-side
 *     UX feedback; it never blocks the eventual real submission if JS
 *     fails to load or a browser doesn't support something used here
 *     (the underlying <form> has no `hidden` steps baked into the HTML
 *     itself -- see register.html -- so a no-JS visit still renders
 *     every field on one page and can still submit normally).
 *   - Server-side validation (validators.py / forms.py) is the only
 *     source of truth. The client-side phone/NIN checks below mirror
 *     those rules purely so mistakes are caught before a submit
 *     round-trip; they intentionally use the same digit/length/prefix
 *     rules as apps/members/validators.py but do not replace it.
 *   - The <form> carries data-no-loading so site.js's generic
 *     submit-spinner handler skips it; the submit-loading state here
 *     is managed directly so the button can show "Submitting..." text
 *     per the brief, instead of site.js's icon-only spinner treatment.
 */
(function () {
  "use strict";

  var VALID_PHONE_PREFIXES = ["070", "071", "080", "081", "090", "091"];
  var MAX_FILE_MB = 5; // mirrors apps.members.validators.validate_image_size
  var COMPRESS_TRIGGER_BYTES = 800 * 1024; // only bother compressing above ~800KB
  var STEP_TITLES = { 1: "Personal Information", 2: "Academic Information", 3: "Uploads", 4: "Review" };
  var STEP_FIELDS = {
    1: ["full_name", "phone_number", "nin_number", "date_of_birth"],
    2: ["institution", "course", "category"],
    3: ["passport_photo", "receipt_image"],
  };

  var filePreviewData = {}; // fieldName -> { dataUrl, name, size }

  function byId(id) {
    return document.getElementById(id);
  }

  function formatSize(bytes) {
    if (bytes >= 1024 * 1024) return (bytes / (1024 * 1024)).toFixed(2) + " MB";
    return Math.max(1, Math.round(bytes / 1024)) + " KB";
  }

  function fieldEl(name) {
    return byId("id_" + name);
  }

  /* ---------------------------------------------------------------
     Live validation: phone / NIN
     ------------------------------------------------------------- */

  function validatePhoneValue(value) {
    if (!value) return null;
    if (!/^[0-9]+$/.test(value)) return { ok: false, msg: "Numbers only." };
    if (value.length !== 11) return { ok: false, msg: value.length + " of 11 digits." };
    if (VALID_PHONE_PREFIXES.indexOf(value.slice(0, 3)) === -1) {
      return { ok: false, msg: "Must start with " + VALID_PHONE_PREFIXES.join(", ") + "." };
    }
    return { ok: true, msg: "Looks good." };
  }

  function validateNinValue(value) {
    if (!value) return null;
    if (!/^[0-9]+$/.test(value)) return { ok: false, msg: "Numbers only." };
    if (value.length !== 11) return { ok: false, msg: value.length + " of 11 digits." };
    return { ok: true, msg: "Looks good." };
  }

  function paintLiveFeedback(fieldName, result) {
    var feedback = byId("feedback-" + fieldName);
    var icon = byId("feedback-icon-" + fieldName);
    if (!feedback || !icon) return;
    if (!result) {
      feedback.textContent = "";
      feedback.className = "field-live-feedback";
      icon.textContent = "";
      icon.className = "input-feedback-icon";
      return;
    }
    feedback.textContent = result.msg;
    feedback.className = "field-live-feedback " + (result.ok ? "is-valid" : "is-invalid");
    icon.textContent = result.ok ? "\u2713" : "\u2715";
    icon.className = "input-feedback-icon " + (result.ok ? "is-valid" : "is-invalid");
  }

  function setupLiveValidation() {
    var phone = fieldEl("phone_number");
    var nin = fieldEl("nin_number");
    if (phone) {
      phone.addEventListener("input", function () {
        paintLiveFeedback("phone_number", validatePhoneValue(phone.value.trim()));
      });
    }
    if (nin) {
      nin.addEventListener("input", function () {
        paintLiveFeedback("nin_number", validateNinValue(nin.value.trim()));
      });
    }
  }

  /* ---------------------------------------------------------------
     Uploads: preview, filename/size, type rejection, in-browser
     compression before submit.
     ------------------------------------------------------------- */

  function showUploadWarning(fieldName, message) {
    var warning = byId("warning-" + fieldName);
    if (!warning) return;
    if (!message) {
      warning.hidden = true;
      warning.textContent = "";
      return;
    }
    warning.hidden = false;
    warning.textContent = message;
  }

  function showUploadPreview(fieldName, dataUrl, name, size, statusText) {
    var wrap = byId("preview-" + fieldName);
    if (!wrap) return;
    var img = wrap.querySelector(".upload-preview-thumb");
    var nameEl = wrap.querySelector(".upload-preview-name");
    var sizeEl = wrap.querySelector(".upload-preview-size");
    var statusEl = wrap.querySelector(".upload-preview-status");
    if (img && dataUrl) img.src = dataUrl;
    if (nameEl) nameEl.textContent = name;
    if (sizeEl) sizeEl.textContent = formatSize(size);
    if (statusEl) statusEl.textContent = statusText || "";
    wrap.hidden = false;
    filePreviewData[fieldName] = { dataUrl: dataUrl, name: name, size: size };
  }

  function hideUploadPreview(fieldName) {
    var wrap = byId("preview-" + fieldName);
    if (wrap) wrap.hidden = true;
    delete filePreviewData[fieldName];
  }

  function replaceInputFile(input, file) {
    try {
      var dt = new DataTransfer();
      dt.items.add(file);
      input.files = dt.files;
      return true;
    } catch (err) {
      // Old browsers without DataTransfer support: leave the original
      // file in place and just skip the compression swap. The upload
      // still works, it's simply not pre-compressed client-side.
      return false;
    }
  }

  function compressImage(file) {
    return new Promise(function (resolve) {
      var supportsCanvas = !!window.HTMLCanvasElement;
      var isCompressibleType = file.type === "image/jpeg" || file.type === "image/png" || file.type === "image/webp";
      if (!supportsCanvas || !isCompressibleType || file.size <= COMPRESS_TRIGGER_BYTES) {
        resolve(file);
        return;
      }

      var img = new Image();
      var objectUrl = URL.createObjectURL(file);

      img.onerror = function () {
        URL.revokeObjectURL(objectUrl);
        resolve(file);
      };

      img.onload = function () {
        URL.revokeObjectURL(objectUrl);
        try {
          var maxDim = 1600;
          var scale = Math.min(1, maxDim / Math.max(img.width, img.height));
          var canvas = document.createElement("canvas");
          canvas.width = Math.round(img.width * scale);
          canvas.height = Math.round(img.height * scale);
          var ctx = canvas.getContext("2d");
          ctx.drawImage(img, 0, 0, canvas.width, canvas.height);

          var qualities = [0.82, 0.65, 0.5];
          var attempt = 0;

          function tryQuality() {
            if (attempt >= qualities.length) {
              resolve(file); // give up gracefully, keep the original
              return;
            }
            canvas.toBlob(
              function (blob) {
                if (!blob) {
                  resolve(file);
                  return;
                }
                if (blob.size < file.size || attempt === qualities.length - 1) {
                  var compressed = new File([blob], file.name, { type: "image/jpeg" });
                  resolve(compressed.size < file.size ? compressed : file);
                } else {
                  attempt += 1;
                  tryQuality();
                }
              },
              "image/jpeg",
              qualities[attempt]
            );
          }
          tryQuality();
        } catch (err) {
          resolve(file);
        }
      };

      img.src = objectUrl;
    });
  }

  function handleFileChange(fieldName) {
    var input = fieldEl(fieldName);
    if (!input) return;
    var file = input.files && input.files[0];

    if (!file) {
      hideUploadPreview(fieldName);
      showUploadWarning(fieldName, null);
      return;
    }

    if (file.type.indexOf("image/") !== 0) {
      showUploadWarning(fieldName, "That file type isn't supported. Please choose an image (JPG, PNG, or WEBP).");
      hideUploadPreview(fieldName);
      input.value = "";
      return;
    }

    showUploadWarning(fieldName, null);

    compressImage(file).then(function (finalFile) {
      var wasCompressed = finalFile !== file;
      if (wasCompressed) replaceInputFile(input, finalFile);

      var reader = new FileReader();
      reader.onload = function (e) {
        var statusText = wasCompressed ? "Compressed for a faster upload" : "";
        showUploadPreview(fieldName, e.target.result, finalFile.name, finalFile.size, statusText);
        if (finalFile.size > MAX_FILE_MB * 1024 * 1024) {
          showUploadWarning(
            fieldName,
            "This image is " + formatSize(finalFile.size) + " -- please choose a smaller photo (max " + MAX_FILE_MB + " MB)."
          );
        }
      };
      reader.readAsDataURL(finalFile);
    });
  }

  function setupUploads() {
    ["passport_photo", "receipt_image"].forEach(function (fieldName) {
      var input = fieldEl(fieldName);
      if (input) input.addEventListener("change", function () { handleFileChange(fieldName); });

      var removeBtn = document.querySelector('[data-remove-for="' + fieldName + '"]');
      if (removeBtn) {
        removeBtn.addEventListener("click", function () {
          if (input) input.value = "";
          hideUploadPreview(fieldName);
          showUploadWarning(fieldName, null);
          if (input) input.focus();
        });
      }
    });
  }

  /* ---------------------------------------------------------------
     Wizard: steps, progress, per-step validation, review, submit
     ------------------------------------------------------------- */

  function initWizard() {
    var form = byId("registration-form");
    if (!form) return;

    var steps = Array.prototype.slice.call(form.querySelectorAll(".wizard-step"));
    var total = steps.length;
    if (!total) return;

    var progressWrap = byId("wizard-progress");
    var progressFill = byId("wizard-progress-fill");
    var progressLabel = byId("wizard-progress-label");
    var dots = Array.prototype.slice.call(form.querySelectorAll(".wizard-progress-dot"));
    var backBtn = byId("wizard-back-btn");
    var nextBtn = byId("wizard-next-btn");
    var submitBtn = byId("wizard-submit-btn");
    var reviewEl = byId("wizard-review");

    steps.forEach(function (step) {
      var heading = step.querySelector(".wizard-step-title");
      if (heading) heading.tabIndex = -1;
    });

    function clearStepJsErrors(step) {
      Array.prototype.forEach.call(step.querySelectorAll(".field-error"), function (el) {
        el.parentNode.removeChild(el);
      });
    }

    function addFieldError(fieldName, message) {
      var row = form.querySelector('[data-field="' + fieldName + '"]');
      if (!row) return null;
      var p = document.createElement("p");
      p.className = "field-error";
      p.setAttribute("role", "alert");
      p.textContent = message;
      row.appendChild(p);
      return row;
    }

    function validateStep(stepNumber) {
      var step = steps[stepNumber - 1];
      clearStepJsErrors(step);
      var fields = STEP_FIELDS[stepNumber] || [];
      var firstInvalidRow = null;

      fields.forEach(function (fieldName) {
        var el = fieldEl(fieldName);
        if (!el) return;
        var isRequired = el.hasAttribute("required");
        var errorMessage = null;

        if (el.type === "file") {
          if (isRequired && (!el.files || el.files.length === 0)) {
            errorMessage = "Please choose a file.";
          }
        } else {
          var value = (el.value || "").trim();
          if (isRequired && !value) {
            errorMessage = "This field is required.";
          } else if (fieldName === "phone_number" && value) {
            var phoneResult = validatePhoneValue(value);
            if (phoneResult && !phoneResult.ok) errorMessage = phoneResult.msg;
          } else if (fieldName === "nin_number" && value) {
            var ninResult = validateNinValue(value);
            if (ninResult && !ninResult.ok) errorMessage = ninResult.msg;
          }
        }

        if (errorMessage) {
          var row = addFieldError(fieldName, errorMessage);
          if (row && !firstInvalidRow) firstInvalidRow = { row: row, el: el };
        }
      });

      return firstInvalidRow;
    }

    function fieldDisplayValue(fieldName) {
      var el = fieldEl(fieldName);
      if (!el) return "Not provided";
      if (el.tagName === "SELECT") {
        var opt = el.options[el.selectedIndex];
        return opt ? opt.text : "Not provided";
      }
      if (el.type === "file") {
        var preview = filePreviewData[fieldName];
        return preview ? preview.name : "Not provided";
      }
      return el.value ? el.value : "Not provided";
    }

    function fieldLabel(fieldName) {
      var row = form.querySelector('[data-field="' + fieldName + '"]');
      var label = row && row.querySelector("label");
      return label ? label.textContent.replace("*", "").trim() : fieldName;
    }

    function buildReview() {
      if (!reviewEl) return;
      reviewEl.innerHTML = "";

      [1, 2, 3].forEach(function (stepNumber) {
        var section = document.createElement("div");
        section.className = "review-section";

        var head = document.createElement("div");
        head.className = "review-section-head";
        var h3 = document.createElement("h3");
        h3.textContent = STEP_TITLES[stepNumber];
        var editBtn = document.createElement("button");
        editBtn.type = "button";
        editBtn.className = "review-edit-btn";
        editBtn.textContent = "Edit";
        editBtn.setAttribute("data-goto-step", String(stepNumber));
        head.appendChild(h3);
        head.appendChild(editBtn);
        section.appendChild(head);

        var dl = document.createElement("dl");
        dl.className = "review-fields";
        STEP_FIELDS[stepNumber].forEach(function (fieldName) {
          var dt = document.createElement("dt");
          dt.textContent = fieldLabel(fieldName);
          var dd = document.createElement("dd");

          var preview = filePreviewData[fieldName];
          if (preview) {
            var img = document.createElement("img");
            img.src = preview.dataUrl;
            img.alt = "";
            img.className = "review-thumb";
            dd.appendChild(img);
            var span = document.createElement("span");
            span.textContent = preview.name + " (" + formatSize(preview.size) + ")";
            dd.appendChild(span);
          } else {
            dd.textContent = fieldDisplayValue(fieldName);
          }

          dl.appendChild(dt);
          dl.appendChild(dd);
        });
        section.appendChild(dl);
        reviewEl.appendChild(section);
      });
    }

    var current = 1;

    function goToStep(n) {
      current = n;
      steps.forEach(function (step) {
        var stepNumber = parseInt(step.getAttribute("data-step"), 10);
        step.hidden = stepNumber !== n;
      });
      dots.forEach(function (dot) {
        var dotNumber = parseInt(dot.getAttribute("data-dot"), 10);
        dot.classList.toggle("is-current", dotNumber === n);
        dot.classList.toggle("is-complete", dotNumber < n);
      });
      if (progressFill) progressFill.style.width = Math.round((n / total) * 100) + "%";
      if (progressLabel) progressLabel.textContent = "Step " + n + " of " + total + " \u2014 " + STEP_TITLES[n];
      if (backBtn) backBtn.hidden = n === 1;
      if (nextBtn) nextBtn.hidden = n === total;
      if (submitBtn) submitBtn.hidden = n !== total;
      if (n === total) buildReview();

      var activeStep = steps[n - 1];
      var heading = activeStep && activeStep.querySelector(".wizard-step-title");
      if (heading) {
        heading.focus();
        heading.scrollIntoView({ behavior: "smooth", block: "start" });
      }
    }

    if (nextBtn) {
      nextBtn.addEventListener("click", function () {
        var invalid = validateStep(current);
        if (invalid) {
          invalid.el.focus();
          invalid.row.scrollIntoView({ behavior: "smooth", block: "center" });
          return;
        }
        goToStep(Math.min(total, current + 1));
      });
    }

    if (backBtn) {
      backBtn.addEventListener("click", function () {
        goToStep(Math.max(1, current - 1));
      });
    }

    if (reviewEl) {
      reviewEl.addEventListener("click", function (event) {
        var target = event.target.closest("[data-goto-step]");
        if (!target) return;
        goToStep(parseInt(target.getAttribute("data-goto-step"), 10));
      });
    }

    form.addEventListener("submit", function (event) {
      for (var stepNumber = 1; stepNumber < total; stepNumber += 1) {
        var invalid = validateStep(stepNumber);
        if (invalid) {
          event.preventDefault();
          goToStep(stepNumber);
          invalid.el.focus();
          return;
        }
      }

      if (submitBtn && !submitBtn.classList.contains("is-submitting")) {
        submitBtn.classList.add("is-submitting");
        submitBtn.disabled = true;
        submitBtn.setAttribute("aria-busy", "true");
        submitBtn.innerHTML = '<span class="spinner" aria-hidden="true"></span> Submitting...';
      } else if (submitBtn && submitBtn.classList.contains("is-submitting")) {
        // Already submitting -- block a second, duplicate submission
        // (e.g. a second Enter-key press before navigation completes).
        event.preventDefault();
      }
    });

    // If the server re-rendered this page with field errors (a failed
    // POST -- duplicate registration, a validator rejecting a value,
    // etc.), open the wizard on the earliest step that has one instead
    // of silently starting back at step 1.
    var startStep = 1;
    for (var i = 0; i < steps.length; i += 1) {
      if (steps[i].querySelector(".field-error")) {
        startStep = parseInt(steps[i].getAttribute("data-step"), 10);
        break;
      }
    }

    if (progressWrap) progressWrap.hidden = false;
    if (nextBtn) nextBtn.hidden = false;
    goToStep(startStep);
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupLiveValidation();
    setupUploads();
    initWizard();
  });
})();
