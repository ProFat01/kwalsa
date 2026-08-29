/*
 * v1.2 Feature 3: quick actions on the staff Members list.
 * Loaded only on members/staff_list.html via {% block extra_js %} — same
 * pattern as home.js for the landing page (Module 2): page-specific
 * vanilla JS, never global, never touching site.js's existing listeners.
 *
 * CSP safety: no inline styles, no inline scripts. The only DOM styling
 * this file does is toggling a `disabled` attribute and text content —
 * neither goes through the HTML/CSS parser CSP gates.
 */
document.addEventListener("DOMContentLoaded", function () {
  var table = document.querySelector("[data-staff-members-table]");
  if (!table) return;

  var checkboxes = Array.prototype.slice.call(table.querySelectorAll(".member-select-checkbox"));
  var selectAllBtn = document.getElementById("select-all-members");
  var sendBtn = document.getElementById("send-to-selected");

  function refreshSendButtonState() {
    if (!sendBtn) return;
    var anyChecked = checkboxes.some(function (box) {
      return box.checked;
    });
    sendBtn.disabled = !anyChecked;
  }

  checkboxes.forEach(function (box) {
    box.addEventListener("change", refreshSendButtonState);
  });

  if (selectAllBtn) {
    selectAllBtn.addEventListener("click", function () {
      var allChecked = checkboxes.every(function (box) {
        return box.checked;
      });
      checkboxes.forEach(function (box) {
        box.checked = !allChecked;
      });
      selectAllBtn.textContent = allChecked ? "Select All On Page" : "Unselect All";
      refreshSendButtonState();
    });
  }

  refreshSendButtonState();

  // Copy Membership ID — Clipboard API with a document.execCommand fallback
  // for browsers/contexts where navigator.clipboard isn't available
  // (e.g. non-HTTPS PythonAnywhere free-tier preview URLs).
  var copyButtons = table.querySelectorAll(".copy-membership-id");
  copyButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      var value = button.getAttribute("data-membership-id");
      if (!value) return;

      var originalLabel = button.textContent;
      function showCopied() {
        button.textContent = "Copied!";
        window.setTimeout(function () {
          button.textContent = originalLabel;
        }, 1500);
      }

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(showCopied, function () {
          fallbackCopy(value, showCopied);
        });
      } else {
        fallbackCopy(value, showCopied);
      }
    });
  });

  function fallbackCopy(value, onDone) {
    var temp = document.createElement("textarea");
    temp.value = value;
    temp.setAttribute("readonly", "");
    temp.style.position = "absolute";
    temp.style.left = "-9999px";
    document.body.appendChild(temp);
    temp.select();
    try {
      document.execCommand("copy");
    } catch (err) {
      /* silently ignore — nothing else we can do in a fallback path */
    }
    document.body.removeChild(temp);
    onDone();
  }
});
