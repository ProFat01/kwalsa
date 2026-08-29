/**
 * SAMS admin.css companion script (Version 1.2 "Admin Experience" polish).
 *
 * Scope, deliberately narrow, matching the brief's Section 9 ("Keep
 * browser-native form submission. No AJAX.") and Section 12
 * ("no unnecessary JavaScript"):
 *
 *   1. Submit-button loading state on the admin change-form save row --
 *      same technique static/js/site.js already uses on the public
 *      site (add a class + disable on `submit`, never call
 *      preventDefault, so the request goes through exactly as before).
 *   2. A clear (x) button on the changelist search box -- pure DOM,
 *      resubmits the existing GET search form with an empty `q`, which
 *      is exactly what manually clearing the field and pressing Enter
 *      already does today. No new endpoint, no fetch() call.
 *
 * Loaded only on admin pages, via templates/admin/base_site.html.
 */
(function () {
  "use strict";

  document.addEventListener("submit", function (event) {
    var form = event.target;
    if (!(form instanceof HTMLFormElement)) return;
    if (form.hasAttribute("data-no-loading")) return;

    var trigger =
      event.submitter ||
      form.querySelector('input[type="submit"]:focus, button[type="submit"]:focus') ||
      form.querySelector('.submit-row input[type="submit"]');
    if (!trigger) return;

    // Same reasoning as site.js: this fires after the browser has
    // already recorded which control triggered submission, so
    // disabling it here cannot drop it from the submitted data, and
    // Django's own validation re-render (on error) replaces the DOM
    // wholesale, clearing the stale loading state automatically.
    trigger.classList.add("sams-is-loading");
    trigger.disabled = true;
  });

  document.addEventListener("DOMContentLoaded", function () {
    var searchWrap = document.getElementById("changelist-search");
    var searchInput = searchWrap ? searchWrap.querySelector("#searchbar") : null;
    if (!searchWrap || !searchInput) return;

    var clearBtn = document.createElement("button");
    clearBtn.type = "button";
    clearBtn.className = "sams-search-clear";
    clearBtn.setAttribute("aria-label", "Clear search");
    clearBtn.textContent = "\u2715";
    searchWrap.appendChild(clearBtn);

    function syncVisibility() {
      clearBtn.classList.toggle("is-visible", searchInput.value.length > 0);
    }

    searchInput.addEventListener("input", syncVisibility);
    syncVisibility();

    clearBtn.addEventListener("click", function () {
      searchInput.value = "";
      searchInput.focus();
      syncVisibility();
      // Resubmits the existing native GET search form with q= empty --
      // identical outcome to a person clearing the field and hitting
      // Enter, so this is the same request Django already handles.
      var form = searchInput.closest("form");
      if (form) form.submit();
    });
  });
})();
