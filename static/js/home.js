/**
 * Landing-page-only JS (Module 2). Loaded via {% block extra_js %} on
 * core/home.html only -- never on any other page -- so this file can
 * stay focused on hero/statistics/countdown/results-preview behavior
 * without growing static/js/site.js (the global chrome script) with
 * page-specific concerns.
 *
 * Every DOM write here uses individual CSSOM property assignment
 * (el.style.<property> = value) rather than setAttribute("style", ...)
 * or el.style.cssText -- the same CSP-safe pattern already established
 * for the vote-bar widths on the results page, since the production
 * Content-Security-Policy is script-src/style-src 'self' with no
 * 'unsafe-inline'. No inline <script> or style="" is introduced by any
 * of this.
 *
 * No JavaScript libraries are used (count-up, countdown, and the pie
 * chart are all implemented in plain JS/CSS) per the brief's
 * performance requirements.
 */
(function () {
  "use strict";

  function applyHeroBackground() {
    var hero = document.querySelector("[data-hero-bg]");
    if (!hero) return;
    var url = hero.getAttribute("data-hero-bg");
    if (!url) return;
    hero.style.backgroundImage = 'url("' + url + '")';
    hero.classList.add("hero--with-image");
  }

  function runCountUp() {
    // Reads each element's own already-correct, server-rendered number
    // as the animation target -- there is no separate data attribute
    // carrying the "real" value, on purpose. That would create two
    // sources of truth that could drift apart, and would leave anyone
    // without JavaScript (or a scraper, or an automated test using
    // Django's test client) seeing a placeholder "0" instead of the
    // real figure. Progressive enhancement here means: the correct
    // number is always present in the HTML; JavaScript only adds the
    // animation on top of it.
    var targets = document.querySelectorAll(".u-countup");
    var duration = 900; // ms -- brief, subtle, not a showpiece animation

    // Respect prefers-reduced-motion: leave the already-correct number
    // exactly as rendered, don't animate at all.
    if (window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches) {
      return;
    }

    targets.forEach(function (el) {
      var target = parseInt(el.textContent.replace(/[^0-9-]/g, ""), 10);
      if (isNaN(target)) return;

      el.textContent = "0";
      var start = null;
      function step(timestamp) {
        if (start === null) start = timestamp;
        var progress = Math.min((timestamp - start) / duration, 1);
        // ease-out-cubic, matches the feel of the site's existing CSS transitions
        var eased = 1 - Math.pow(1 - progress, 3);
        el.textContent = Math.round(eased * target).toLocaleString();
        if (progress < 1) {
          window.requestAnimationFrame(step);
        } else {
          el.textContent = target.toLocaleString();
        }
      }
      window.requestAnimationFrame(step);
    });
  }

  function initCountdown() {
    var container = document.querySelector("[data-countdown-until]");
    if (!container) return;
    var target = new Date(container.getAttribute("data-countdown-until")).getTime();
    if (isNaN(target)) return;

    var daysEl = container.querySelector("[data-cd-days]");
    var hoursEl = container.querySelector("[data-cd-hours]");
    var minutesEl = container.querySelector("[data-cd-minutes]");
    var secondsEl = container.querySelector("[data-cd-seconds]");

    function tick() {
      var remaining = target - Date.now();
      if (remaining <= 0) {
        container.textContent = "Voting has closed.";
        container.classList.add("countdown-ended");
        clearInterval(intervalId);
        return;
      }
      var totalSeconds = Math.floor(remaining / 1000);
      var days = Math.floor(totalSeconds / 86400);
      var hours = Math.floor((totalSeconds % 86400) / 3600);
      var minutes = Math.floor((totalSeconds % 3600) / 60);
      var seconds = totalSeconds % 60;

      if (daysEl) daysEl.textContent = String(days);
      if (hoursEl) hoursEl.textContent = String(hours).padStart(2, "0");
      if (minutesEl) minutesEl.textContent = String(minutes).padStart(2, "0");
      if (secondsEl) secondsEl.textContent = String(seconds).padStart(2, "0");
    }

    tick();
    var intervalId = setInterval(tick, 1000);
  }

  // A small, deterministic, presentation-only color rotation for the
  // pie chart slices -- candidates have no inherent brand color of
  // their own, so this just needs to be visually distinct and
  // consistent between the chart and its legend swatches.
  var PIE_PALETTE = [
    "#1a6b45", // civic-green
    "#a9762f", // brass
    "#3f68b0", // info blue (matches .alert-info's border)
    "#8a5a00", // warning
    "#5c6670", // slate
    "#0f4a30", // civic-green-deep
  ];

  function initPieCharts() {
    var charts = document.querySelectorAll(".pie-chart");
    charts.forEach(function (chart) {
      var wrap = chart.closest(".pie-chart-wrap");
      if (!wrap) return;
      var legendItems = wrap.querySelectorAll(".pie-chart-legend li[data-percentage]");
      if (!legendItems.length) return;

      var stops = [];
      var cumulative = 0;
      legendItems.forEach(function (li, index) {
        var pct = parseFloat(li.getAttribute("data-percentage")) || 0;
        var color = PIE_PALETTE[index % PIE_PALETTE.length];
        var start = cumulative;
        var end = cumulative + pct;
        stops.push(color + " " + start + "% " + end + "%");
        cumulative = end;

        var swatch = li.querySelector(".pie-chart-swatch");
        if (swatch) swatch.style.backgroundColor = color;
      });

      if (cumulative <= 0) return; // no votes yet -- leave the neutral placeholder background
      chart.style.background = "conic-gradient(" + stops.join(", ") + ")";
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    applyHeroBackground();
    runCountUp();
    initCountdown();
    initPieCharts();
  });
})();
