/**
 * Membership-card-page-only JS. Loaded via {% block extra_js %} on
 * members/card.html only, same pattern as static/js/home.js,
 * static/js/register.js, etc.
 *
 * Scope, deliberately narrow (v1.1 polish brief: "Do NOT change
 * business logic", "browser-print based", "no forced downloads",
 * "no server-side PDF generation"):
 *   - Desktop: the Print button calls window.print() directly, same
 *     as before (it used to be an inline onclick="window.print()" on
 *     the button itself — moved here so it's an external script, since
 *     inline event-handler attributes are blocked under this site's
 *     CSP `script-src 'self'` and only ever worked because no CSP
 *     violation had been triggered/observed yet, not because it was
 *     actually compliant).
 *   - Mobile: same click shows a native <dialog> with a short print
 *     tip first (Android/iOS mobile print support varies and is often
 *     lower quality than desktop). The dialog itself has a "Print
 *     Anyway" button that calls window.print() — so mobile printing
 *     still works exactly as before if someone wants it, this only
 *     adds a heads-up in front of it, never blocks it.
 *   - No network calls, no downloads triggered by this script, no PDF
 *     generation — window.print() is the browser's own print/PDF
 *     flow, entirely unchanged.
 */
(function () {
  "use strict";

  function isLikelyMobile() {
    // Prefer the modern, spec'd signal where available.
    if (navigator.userAgentData && typeof navigator.userAgentData.mobile === "boolean") {
      return navigator.userAgentData.mobile;
    }
    // Fallback: UA string sniffing (still the most broadly supported
    // signal across older/other mobile browsers).
    var ua = navigator.userAgent || "";
    if (/Android|iPhone|iPad|iPod|Mobile/i.test(ua)) return true;
    // Last resort heuristic for UA strings that omit the above (some
    // in-app browsers): a touch-primary pointer on a narrow viewport.
    var coarsePointer = window.matchMedia && window.matchMedia("(pointer: coarse)").matches;
    var narrowViewport = window.matchMedia && window.matchMedia("(max-width: 900px)").matches;
    return !!(coarsePointer && narrowViewport);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var printBtn = document.getElementById("print-card-btn");
    if (!printBtn) return;

    var dialog = document.getElementById("mobile-print-dialog");
    var dismissBtn = document.getElementById("mobile-print-dismiss");
    var printAnywayBtn = document.getElementById("mobile-print-anyway");
    var supportsDialog = dialog && typeof dialog.showModal === "function";

    printBtn.addEventListener("click", function () {
      if (!isLikelyMobile()) {
        window.print();
        return;
      }

      if (supportsDialog) {
        dialog.showModal();
      } else {
        // No <dialog> support (very old mobile browser): fall back to
        // a plain confirm so the tip still gets shown, then still let
        // the person print if they want to.
        var wantsToPrint = window.confirm(
          "Best results on mobile: open this page in Chrome and use Share \u2192 Print \u2192 Save as PDF.\n\n" +
            "Press OK to try printing from here anyway, or Cancel to go do that instead."
        );
        if (wantsToPrint) window.print();
      }
    });

    if (dismissBtn && dialog) {
      dismissBtn.addEventListener("click", function () {
        dialog.close();
      });
    }

    if (printAnywayBtn && dialog) {
      printAnywayBtn.addEventListener("click", function () {
        dialog.close();
        window.print();
      });
    }
  });
})();
