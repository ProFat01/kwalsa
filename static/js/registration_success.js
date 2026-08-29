/**
 * Registration-success-page-only JS: "Copy Application Number" button.
 * Loaded via {% block extra_js %} on members/registration_success.html
 * only, same pattern as static/js/home.js and static/js/register.js.
 */
(function () {
  "use strict";

  function fallbackCopy(text) {
    var textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "absolute";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    textarea.select();
    var ok = false;
    try {
      ok = document.execCommand("copy");
    } catch (err) {
      ok = false;
    }
    document.body.removeChild(textarea);
    return ok;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var button = document.getElementById("copy-application-number");
    var feedback = document.getElementById("copy-feedback");
    if (!button) return;

    button.addEventListener("click", function () {
      var value = button.getAttribute("data-copy-value") || "";
      var announce = function (ok) {
        if (!feedback) return;
        feedback.textContent = ok ? "Copied!" : "Couldn't copy \u2014 please copy it manually.";
        window.setTimeout(function () {
          feedback.textContent = "";
        }, 4000);
      };

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(value).then(
          function () { announce(true); },
          function () { announce(fallbackCopy(value)); }
        );
      } else {
        announce(fallbackCopy(value));
      }
    });
  });
})();
