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
  // institution_other is validated as part of step 2 (its `required`
  // attribute is toggled by setupInstitutionCombobox() below, so
  // validateStep()'s normal required-field check already covers it) but
  // deliberately left out of REVIEW_STEP_FIELDS -- its value is folded
  // into the "institution" row on the review step instead of getting a
  // row of its own (see fieldDisplayValue()).
  var STEP_FIELDS = {
    1: ["full_name", "phone_number", "nin_number", "date_of_birth", "gender"],
    2: ["institution", "institution_other", "course", "category"],
    3: ["passport_photo", "receipt_image"],
  };
  var REVIEW_STEP_FIELDS = {
    1: STEP_FIELDS[1],
    2: ["institution", "course", "category"],
    3: STEP_FIELDS[3],
  };
  var OTHER_INSTITUTION_VALUE = "other";

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
     Institution: searchable combobox + "Other" reveal

     Progressive enhancement over the real <select id="id_institution">
     rendered by MemberRegistrationForm (see forms.py / institutions.py)
     -- that select is what actually gets submitted; nothing here
     changes its `name` or removes it from the form. Without JS, a
     registrant just uses the native select (grouped Gombe State /
     national-university <optgroup>s) and, if they pick "Other", types
     into the always-present institution_other text field below it.
     With JS, the select is visually replaced by a type-to-filter combo
     input + listbox that stays in sync with it, following the WAI-ARIA
     1.2 "combobox with list autocomplete" pattern.
     ------------------------------------------------------------- */

  function setupInstitutionCombobox() {
    var select = fieldEl("institution");
    if (!select) return;

    var otherRow = document.querySelector('[data-field="institution_other"]');
    var otherInput = fieldEl("institution_other");

    function syncOtherVisibility() {
      var isOther = select.value === OTHER_INSTITUTION_VALUE;
      if (otherRow) otherRow.hidden = !isOther;
      if (otherInput) otherInput.required = isOther;
    }
    select.addEventListener("change", syncOtherVisibility);
    syncOtherVisibility();

    // Collect (value, label, group) from the select's own <option>s /
    // <optgroup>s, so the combobox's option list can never drift out of
    // sync with what the server actually accepts.
    var entries = [];
    Array.prototype.forEach.call(select.children, function (node) {
      if (node.tagName === "OPTGROUP") {
        Array.prototype.forEach.call(node.children, function (opt) {
          if (opt.value) entries.push({ value: opt.value, label: opt.textContent, group: node.label });
        });
      } else if (node.tagName === "OPTION" && node.value) {
        entries.push({ value: node.value, label: node.textContent, group: null });
      }
    });
    if (!entries.length) return;

    var label = document.querySelector('label[for="' + select.id + '"]');

    var wrap = document.createElement("div");
    wrap.className = "combobox";

    var input = document.createElement("input");
    input.type = "text";
    input.className = "combobox-input";
    input.id = "institution-combo-input";
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-expanded", "false");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", "institution-listbox");
    input.setAttribute("autocomplete", "off");
    input.placeholder = "Type to search institutions\u2026";

    var listbox = document.createElement("ul");
    listbox.id = "institution-listbox";
    listbox.className = "combobox-listbox";
    listbox.setAttribute("role", "listbox");
    listbox.hidden = true;

    function currentLabel() {
      var opt = select.options[select.selectedIndex];
      return opt && opt.value ? opt.text : "";
    }

    function renderOptions(filterText) {
      listbox.innerHTML = "";
      var q = (filterText || "").trim().toLowerCase();
      var lastGroup = null;
      var shown = 0;
      entries.forEach(function (entry) {
        if (q && entry.label.toLowerCase().indexOf(q) === -1) return;
        if (entry.group && entry.group !== lastGroup) {
          var groupLi = document.createElement("li");
          groupLi.className = "combobox-group-label";
          groupLi.setAttribute("role", "presentation");
          groupLi.textContent = entry.group;
          listbox.appendChild(groupLi);
          lastGroup = entry.group;
        }
        var li = document.createElement("li");
        li.id = "institution-option-" + shown;
        li.className = "combobox-option";
        li.setAttribute("role", "option");
        li.setAttribute("data-value", entry.value);
        li.textContent = entry.label;
        if (entry.value === select.value) {
          li.setAttribute("aria-selected", "true");
          li.classList.add("is-selected");
        }
        listbox.appendChild(li);
        shown += 1;
      });
      if (!shown) {
        var empty = document.createElement("li");
        empty.className = "combobox-empty";
        empty.setAttribute("role", "presentation");
        empty.textContent = "No matches \u2014 choose \u201cOther\u201d to enter it manually.";
        listbox.appendChild(empty);
      }
      input.removeAttribute("aria-activedescendant");
    }

    function openListbox(filterText) {
      renderOptions(filterText);
      listbox.hidden = false;
      input.setAttribute("aria-expanded", "true");
    }

    function closeListbox() {
      listbox.hidden = true;
      input.setAttribute("aria-expanded", "false");
      input.removeAttribute("aria-activedescendant");
    }

    function chooseEntry(value, text) {
      select.value = value;
      input.value = text;
      closeListbox();
      syncOtherVisibility();
      // Real change event (not just the value assignment above) so
      // anything else listening to the select -- step validation,
      // review-step rendering -- sees the update exactly as if a person
      // had picked it from the native control.
      select.dispatchEvent(new Event("change", { bubbles: true }));
      if (value === OTHER_INSTITUTION_VALUE && otherInput) otherInput.focus();
    }

    function setActiveOption(index) {
      var options = listbox.querySelectorAll('[role="option"]');
      Array.prototype.forEach.call(options, function (opt, i) {
        opt.classList.toggle("is-active", i === index);
      });
      var active = options[index];
      if (active) {
        input.setAttribute("aria-activedescendant", active.id);
        active.scrollIntoView({ block: "nearest" });
      } else {
        input.removeAttribute("aria-activedescendant");
      }
      return options;
    }

    input.addEventListener("focus", function () {
      openListbox("");
    });

    input.addEventListener("input", function () {
      openListbox(input.value);
    });

    input.addEventListener("keydown", function (event) {
      var options = listbox.querySelectorAll('[role="option"]');
      var activeId = input.getAttribute("aria-activedescendant");
      var activeIndex = -1;
      for (var i = 0; i < options.length; i += 1) {
        if (options[i].id === activeId) { activeIndex = i; break; }
      }

      if (event.key === "ArrowDown") {
        event.preventDefault();
        if (listbox.hidden) { openListbox(input.value); return; }
        setActiveOption(Math.min(options.length - 1, activeIndex + 1));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        if (listbox.hidden) { openListbox(input.value); return; }
        setActiveOption(Math.max(0, activeIndex - 1));
      } else if (event.key === "Enter") {
        if (!listbox.hidden && activeIndex >= 0) {
          event.preventDefault();
          var chosen = options[activeIndex];
          chooseEntry(chosen.getAttribute("data-value"), chosen.textContent);
        }
      } else if (event.key === "Escape") {
        if (!listbox.hidden) {
          event.preventDefault();
          closeListbox();
        }
      } else if (event.key === "Tab") {
        closeListbox();
      }
    });

    listbox.addEventListener("mousedown", function (event) {
      var option = event.target.closest('[role="option"]');
      if (!option) return;
      event.preventDefault();
      chooseEntry(option.getAttribute("data-value"), option.textContent);
    });

    document.addEventListener("click", function (event) {
      if (!wrap.contains(event.target)) closeListbox();
    });

    input.value = currentLabel();

    wrap.appendChild(input);
    wrap.appendChild(listbox);
    select.parentNode.insertBefore(wrap, select);

    // The real select stays in the DOM (still submitted, still what
    // validateStep()/fieldDisplayValue() read from) but is visually
    // replaced by the combobox above; screen readers get the combobox's
    // own role="combobox"/role="listbox" semantics instead.
    select.hidden = true;
    if (label) label.setAttribute("for", input.id);
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
          if (row && !firstInvalidRow) {
            // The institution <select> is visually hidden once
            // setupInstitutionCombobox() replaces it (see above) --
            // focus its visible combobox input instead so keyboard/
            // focus behavior matches what's on screen.
            var focusEl = el;
            if (fieldName === "institution") {
              var comboInput = byId("institution-combo-input");
              if (comboInput) focusEl = comboInput;
            }
            firstInvalidRow = { row: row, el: focusEl };
          }
        }
      });

      return firstInvalidRow;
    }

    function fieldDisplayValue(fieldName) {
      if (fieldName === "institution") {
        var institutionSelect = fieldEl("institution");
        if (institutionSelect && institutionSelect.value === OTHER_INSTITUTION_VALUE) {
          var other = fieldEl("institution_other");
          var typed = other ? other.value.trim() : "";
          return typed || "Not provided";
        }
      }
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
        REVIEW_STEP_FIELDS[stepNumber].forEach(function (fieldName) {
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
    setupInstitutionCombobox();
    initWizard();
  });
})();
