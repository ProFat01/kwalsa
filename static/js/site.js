/**
 * Site-wide JS, loaded as an external file specifically so it's exempt
 * from the production CSP's `script-src 'self'` (same-origin script
 * *files* are allowed; inline <script> blocks are not).
 */
(function () {
  "use strict";

  function setupMobileNav() {
    var toggle = document.getElementById("nav-toggle");
    var nav = document.getElementById("primary-navigation");
    var navWrapper = document.getElementById("primary-nav-wrapper");
    if (!toggle || !nav || !navWrapper) return;
    toggle.addEventListener("click", function () {
      var isOpen = nav.classList.toggle("is-open");
      // The <nav> wrapper is a third flex sibling alongside brand and
      // toggle on mobile. If it stayed in the flex flow at full size
      // even while closed, space-between would misplace the toggle
      // button. base.css collapses/expands the wrapper via max-height
      // (for a smooth transition) keyed off this same is-open class.
      navWrapper.classList.toggle("is-open", isOpen);
      toggle.setAttribute("aria-expanded", isOpen ? "true" : "false");
    });
  }

  function applyVoteBarWidths() {
    // Sets each bar's width via individual CSSOM property assignment
    // (el.style.width = "..."), not via setAttribute("style", ...) or
    // el.style.cssText -- only the latter two are subject to CSP's
    // style-src restriction. Reading the percentage from a data-
    // attribute keeps the HTML itself free of any inline style="".
    var bars = document.querySelectorAll("[data-percentage]");
    for (var i = 0; i < bars.length; i++) {
      var value = parseFloat(bars[i].getAttribute("data-percentage"));
      if (!isNaN(value)) {
        bars[i].style.width = Math.max(0, Math.min(100, value)) + "%";
      }
    }
  }

  function setupSubmitLoadingState() {
    // Progressive UX enhancement only: on submit, the triggering
    // button gets a spinner and becomes inert so a slow connection or
    // a large file upload (e.g. passport photo, receipt, candidate
    // photo) can't be double-submitted by an impatient click. This
    // never calls preventDefault() and never blocks the browser's own
    // "required field" validation (which fires its own "invalid"
    // event instead of "submit" when a required field is empty) --
    // the form always submits exactly as it did before this file
    // existed; this only changes what the button looks like while
    // that submission is in flight. A full page navigation follows
    // either way (success redirect or a re-rendered page with
    // errors), which naturally clears the loading state without any
    // extra code.
    document.addEventListener(
      "submit",
      function (event) {
        var form = event.target;
        if (!(form instanceof HTMLFormElement)) return;
        if (form.hasAttribute("data-no-loading")) return;

        var submitter =
          event.submitter ||
          form.querySelector('button[type="submit"], input[type="submit"]');
        if (!submitter || submitter.classList.contains("is-loading")) return;

        submitter.classList.add("is-loading");
        submitter.setAttribute("aria-busy", "true");
        submitter.disabled = true;
      },
      true
    );
  }

  document.addEventListener("DOMContentLoaded", function () {
    setupMobileNav();
    applyVoteBarWidths();
    setupSubmitLoadingState();
  });
})();
