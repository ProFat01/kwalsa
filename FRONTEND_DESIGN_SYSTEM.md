# SAMS Version 1 Frontend Polish — Module 1: Global Design System

## Scope discipline

Three files changed. Nothing else.

| File | Type |
|---|---|
| `static/css/base.css` | Design tokens, typography, buttons, forms, nav, footer, alerts, utilities |
| `static/css/components.css` | Cards, tables, statistic cards, landing-page components |
| `static/js/site.js` | Mobile nav toggle (unchanged behavior), vote-bar width (unchanged behavior), new submit-button loading state |

**Zero templates were modified.** Every template already used shared
classes (`.btn`, `.summary-stat`, `.alert`, `.form-row`, `.election-card`,
etc.) defined in these two CSS files, so upgrading the definitions
upgrades every page that uses them automatically. `templates/base.html`
already contained the active-page-indicator logic and the
`alert-warning` tag mapping from a prior pass — confirmed by inspection
before starting, not re-implemented.

**No model, view, form, URL, admin, permission, migration, or settings
file was touched.** `python manage.py makemigrations --check --dry-run`
confirms zero migrations required. All 185 tests pass (176 pre-existing
+ 9 new), none of them modified.

---

## What changed, mapped to each requirement in the brief

### 1. Color palette
Kept every existing token name (`--civic-green`, `--paper`, `--surface`,
etc.) so nothing that already referenced them needed to change. Added,
purely additively:
- `--surface-soft` — the "soft gray surface" the brief asks for,
  distinct from both the page background (`--paper`) and card
  backgrounds (`--surface`) — used for table headers, disabled-input
  backgrounds, and the new `.chip` component.
- `--warning` / `--warning-tint` — the one genuine gap in the old
  palette. Success (civic green), error (`--alert`), and info existed;
  warning didn't.
- `--success` / `--error` as semantic aliases onto the existing civic
  green / alert colors, so new components can reference intent
  ("success", "error") rather than a specific brand color name.
Contrast was not an afterthought here — the palette was already built
around WCAG-safe ink-on-paper and white-on-ink pairings in an earlier
pass; this task didn't need to touch that.

### 2. Typography
`h1`–`h4` sizes refined (`h1` now `clamp(2rem, 4.2vw, 2.9rem)`, up
slightly from before, for a stronger hero presence), `letter-spacing:
-0.01em` added for a tighter, more considered heading feel, base
`line-height` increased from 1.55 to 1.6 for more comfortable reading.
Added `--text-xs/sm/base/lg/xl` scale tokens and a `.lead` utility class
for intro paragraphs. Fonts themselves (Fraunces / Inter / IBM Plex
Mono) were kept — they were already a deliberate, non-default choice
from the original design pass, not something this polish needed to
replace.

### 3. Buttons
- **Rounded corners**: the shared `--radius` token moved from 8px to
  10px, so `.btn` (and every input, since they shared the same token)
  became more rounded in one line, without touching every selector
  individually.
- **Hover effects**: `transform: translateY(-1px)` plus a shadow
  increase (`--shadow-md`) on hover, with a matching `:active` state
  that returns to flat — verified in a real browser (see "Verification"
  below).
- **Loading state**: `.btn.is-loading` makes the button's text
  transparent (preserving its exact width — no layout shift) and draws
  a spinner centered over it via `::after`. `site.js` adds this class
  and `disabled=true` on every form's submit event, automatically,
  for any submit button that doesn't opt out via `data-no-loading` on
  its `<form>`. This required a **JS behavior change** (the only one in
  this task) — detailed under "The one behavioral addition" below.
- **Disabled state**: `.btn:disabled` — reduced opacity, `cursor:
  not-allowed`, no hover motion.
- Consolidated existing `.btn-outline` / `.btn-on-dark` /
  `.btn-outline-on-dark` variants onto the same hover/transition system
  rather than each having ad hoc rules.

### 4. Cards
`.election-card`, `.summary-stat`, `.info-card`, `.candidate-profile`
all gained a consistent shadow (`--shadow-sm` at rest, `--shadow-md` on
hover for the interactive ones) and a hover-lift
(`translateY(-2px)`). Radius on the larger cards moved from 14px to
16px (`--radius-lg`). This is one CSS change per selector, no template
edits, because every one of these classes was already applied
consistently by existing templates.

### 5. Forms
- Inputs: padding increased slightly (0.6rem→0.7rem), border-color/
  box-shadow transition added for a smoother focus effect,
  `::placeholder` color made explicit, `:disabled` styling added
  (previously unstyled).
- **Inline error display**: `.field-error` gained a `⚠` icon via
  `::before`. More importantly — **`.form-row:has(.field-error) input`
  now auto-applies a red border and red focus ring**, using the CSS
  `:has()` selector. This is progressive enhancement: browsers that
  don't support `:has()` (none of the current evergreen browsers — it
  shipped in Chrome 105, Safari 15.4, Firefox 121) simply don't get the
  red border; the actual error text was already there before and is
  completely unaffected either way. **No template or view change was
  needed** to wire this up, because every form already renders errors as
  `<p class="field-error">` inside a `.form-row` — this CSS rule just
  started reacting to markup that already existed.

### 6. Navigation
- Header gained a subtle `--shadow-sm` for depth against the page
  background.
- **Active-page indicator**: already implemented in `base.html` (found
  during the pre-work audit, not added by this task) — it compares
  `request.path` against each `{% url %}` and adds `class="is-active"`.
  This task added the *styling* for that class (`.nav-links a.is-active`
  — white text, subtle background tint, bold) so the existing logic
  actually produces a visible result.
- **Smooth mobile menu**: previously the mobile nav panel toggled via
  `display: none` / `display: block` — an instant snap with no
  animation possible (you can't transition `display`). Rewritten to use
  `max-height: 0` → `max-height: 32rem` with a `transition: max-height`,
  which *is* animatable, producing a smooth slide-open/closed effect.
  The JS class-toggling mechanism (`classList.toggle("is-open")`) is
  completely unchanged — only the CSS driving that class changed.
- Hamburger/close icon swap: `base.html` already had both icon `<span>`s
  with an `aria-expanded`-keyed CSS pattern in mind (found during
  audit); this task added the actual `.nav-toggle-icon-open` /
  `.nav-toggle-icon-close` display-toggling rules that make it work.
- Improved spacing throughout (`gap`, `padding`) for a less cramped feel
  at both desktop and mobile widths.

### 7. Footer
Added a 3px `--brass` top border for a distinguishing civic accent.
Section headings and link colors got smoother hover transitions. The
actual content (branding, quick links, contact, donation, social,
copyright) was already complete from an earlier module — this task
only refined its visual presentation, not its structure or content.

### 8. Animations
- A single shared `@keyframes fade-in-up` (opacity + 6px vertical
  shift, 0.35s) applied to `#main-content` — since that id already
  exists in `base.html` on every page, every page gets a subtle
  fade-in with zero template changes.
- Hover-lift on cards and buttons (above).
- All governed by the existing global
  `@media (prefers-reduced-motion: reduce)` rule, which was already
  present and neutralizes every animation/transition duration to
  `0.01ms` for users who've asked for reduced motion — this task didn't
  need to add that; it already existed and now protects more surface
  area automatically.
- Deliberately kept small and short, per the brief's "no excessive
  animation": no bouncing, no spinning content, no parallax.

### 9. Loading UX
- `.spinner` — a standalone CSS spinner (rotating border-circle) for use
  anywhere a loading indicator is needed outside of a button.
- Submit-button loading state — see "The one behavioral addition"
  below; this is the one part of this requirement that needed a JS
  change rather than pure CSS.

### 10. Notifications
`.alert` redesigned: left accent border (4px, colored per variant),
icon via `::before` (✓ success, ⚠ warning, ✕ error, ℹ info), subtle
shadow, fade-in on appearance. **Added the missing `.alert-warning`
variant** — success/error/info already existed, warning didn't. The
`base.html` tag-to-class mapping already handled `warning` correctly
(confirmed by the pre-work audit and locked in by a new test), so this
was a pure CSS addition.

### 11. Statistics cards
`.summary-stat` — already the single component reused across every
analytics dashboard, the elections admin dashboard, the registration
overview, and the accounts dashboard hub for exactly "Members / Alumni
/ Votes / Elections" summaries. Enhanced with a colored left accent bar,
larger record-face value typography, shadow, and hover-lift. Because
this is one shared class, the upgrade applies to every one of those
screens simultaneously.

### 12. Utility classes
Expanded the existing `.u-*` prefix (already established) with flex
helpers (`.u-flex`, `.u-flex-col`, `.u-items-center`, `.u-gap-1/2/3`),
grid helpers (`.u-grid-2/3/4`, responsive via `auto-fit`), more spacing
variants (`.u-mb-*`, `.u-p-*`), text helpers (`.u-text-muted`,
`.u-text-center`). Added two genuinely new categories the brief asked
for that didn't exist before: `.chip` (neutral pill for informal tags,
visually distinct from the semantic `.badge`) and `.status-label` +
`.status-success/warning/error/neutral` (generic status pills, same
visual language as the election-specific `.badge-upcoming/active/closed`
but under reusable semantic names for future modules).

---

## The one behavioral addition: submit-button loading state

Every other change in this task is presentation-only (CSS). The
button loading state genuinely needed new JS behavior, so it gets its
own explicit callout rather than being buried in section 3/9 above.

**What it does**: `site.js` listens for `submit` events on the whole
document (event delegation, so it covers every form on every page
without per-form wiring). On submit, it finds the button that triggered
submission (`event.submitter`, with a `querySelector` fallback for
older browsers), adds `.is-loading` and `disabled=true` to it, and does
nothing else.

**Why this is safe and does not change any business logic**:
- It never calls `event.preventDefault()`. The form submits exactly as
  it always did — same request, same data, same server-side view, same
  validation, same redirect-or-re-render outcome.
- Disabling the button *after* the browser has already captured which
  button triggered submission does not remove it from the submitted
  data (browsers finalize the triggering-button decision before
  dispatching the `submit` event) — and none of this project's submit
  buttons carry a `name` attribute anyway, so there is no form field to
  lose even in principle.
- If a required field is empty and the form has no `novalidate`, the
  browser fires its own `invalid` event instead of `submit` and blocks
  submission entirely — our listener never runs, so it can't interfere
  with browser-native validation either. Where a form does use
  `novalidate` (registration, status check, elections), the *server's*
  validation renders the response, and that full-page response replaces
  the DOM (including the now-stale disabled button) — the loading state
  clears itself automatically, no matter whether the submission
  succeeded or failed server-side.
- It can be opted out per-form via `data-no-loading` on the `<form>`
  tag, for any future form where this wouldn't make sense (none exist
  today).
- **Django's test client never executes JavaScript at all** — every one
  of the 185 automated tests exercises the real view/form/model layer
  exactly as before; this addition is invisible to them by construction,
  which is exactly why all 185 continue to pass unmodified.

---

## Verification performed

Beyond the automated test suite, this task was verified with a real
headless Chromium session (Playwright) against the actual running dev
server, because a CSS/design task can't be honestly verified by reading
Django template output alone:

- **Active-page indicator**: confirmed `is-active` class present on the
  correct nav link on `/` and `/about/`, absent from the others, on both
  requests.
- **Mobile menu**: confirmed the hamburger button sits flush against
  the right edge at a 375px viewport (0.0px gap) — and, by deliberately
  reverting the fix and re-measuring, confirmed the *original*
  misalignment bug (documented in an earlier module) does not regress.
  Confirmed the panel opens as a smooth full-width panel below the
  header and the hamburger/close icon swap fires correctly
  (`aria-expanded` toggles, the correct icon span becomes visible).
- **Inline validation styling**: submitted an empty registration form
  and read back the *computed* `border-color` of an errored input —
  `rgb(178, 58, 46)`, exactly `--error`. Confirms the `:has()`
  progressive enhancement is genuinely active, not just present in the
  stylesheet source.
- **Notification alert**: read back computed `background-color` (civic
  green tint), `border-left-color`, `border-radius`, `box-shadow`, and
  the `::before` icon content (`"✓"`) on a real rendered success alert
  — all matched the intended design tokens exactly.
- **Button loading state**: proved the `submit` listener actually fires
  and applies `is-loading` + `disabled` + `aria-busy="true"` correctly
  (confirmed via direct DOM inspection with navigation deliberately
  blocked so the state could be captured before the page moved on).
- **Statistic cards**: read back computed `border-radius` (16px),
  `box-shadow`, the `::before` accent-bar color (civic green), and
  measured an actual 2px upward shift on `:hover`.
- **Vote-bar animation**: confirmed the JS-applied `style.width` still
  works correctly and now transitions smoothly (`width 0.6s`) instead of
  snapping instantly.
- **CSP safety**: grepped the entire rendered output of every major page
  for `style="` and `<script>` — zero matches, confirming the earlier
  production audit's CSP-safety work (no `'unsafe-inline'` anywhere in
  the policy) was not undone by this pass. This is now also a permanent
  automated test (`test_no_inline_style_attributes_on_any_major_page`,
  `test_no_inline_script_blocks_on_any_major_page`).

---

## Answers to the required confirmations

1. **Are migrations required?** No. Zero model changes; `manage.py
   makemigrations --check --dry-run` reports "No changes detected."
2. **Did deployment settings change?** No. No file under
   `config/settings/` was touched.
3. **Did business logic change?** No. No `models.py`, `views.py`
   (business logic), `forms.py` (validation), `urls.py`, `admin.py`,
   permissions, or election/analytics calculation code was modified.
   The one JS behavior addition (button loading state) does not alter
   what any form submits or how any view processes it — see "The one
   behavioral addition" above for the specific reasoning.
4. **Does all existing functionality remain intact?** Yes. All 185
   automated tests pass (176 pre-existing, unmodified + 9 new,
   covering only this task's own additions). Verified additionally via
   a real browser session across the registration form, contact form,
   navigation, and analytics dashboard.
