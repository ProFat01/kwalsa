# SAMS Version 1 Frontend Polish — Module 2: Landing Page Experience

## Files modified (8 total)

| File | Why |
|---|---|
| `apps/core/views.py` | One new context key, `contact_form` (an unbound `ContactForm()` instance), added to the existing `home_view`. Needed so the landing page's new embedded mini contact section (Section 8) can render real form fields consistent with the actual form definition. See "The one view change" below. |
| `apps/core/templates/core/home.html` | Rewritten to add Sections 1, 2, 4, 5, 6, 7 (restyled), 8 and to make the hero's third CTA conditional. The existing About section (3), full elections board, and CTA section were kept, lightly adjusted. |
| `templates/base.html` | Footer: added the association logo image and a conditional "Donate" quick-link (Section 9 requirements that weren't previously in the footer). |
| `static/css/base.css` | Two new utility classes (`u-max-34`, `u-m-0`) needed by the restyled donation section. |
| `static/css/components.css` | New component styles for Sections 4–6 (benefit cards, spotlight card, countdown digits, results-preview rows, CSS-only pie chart) and the hero's dynamic background-image support. Reuses existing `.summary-stat` and `.vote-bar-track`/`.vote-bar-fill` unchanged. |
| `static/js/home.js` | **New file.** Landing-page-only JS: count-up animation, countdown timer, hero background-image application, and the CSS-conic-gradient pie chart. Loaded only on `home.html` via `{% block extra_js %}`, never on any other page. |
| `apps/core/tests/test_views.py` | Two assertions updated to match Module 2's explicit, intentional behavior changes (conditional Vote Now button; the "Total Members" label became "Total Registered Members" per the brief's exact wording). See "Tests that had to change, and why" below. |
| `apps/core/tests/test_landing_page_experience.py` | **New file.** 23 regression tests covering every new/changed section. |

**No `models.py`, `forms.py`, `urls.py`, `admin.py`, authentication, permissions, migrations, settings, or any election/analytics/registration business logic file was touched.**

---

## The one view change, justified precisely

`home_view` gained exactly one new context key:

```python
context["contact_form"] = ContactForm()
```

This is an **unbound** form instance — it exists only so the template can render `{{ field.label }}`/`{{ field }}` for each of `ContactForm`'s real fields (name, email, subject, message) with correct `<input>` types and `maxlength`/`required` attributes, rather than the template hand-rolling raw `<input name="...">` tags that could silently drift out of sync with the actual form definition in `apps/core/forms.py`.

**This changes nothing about how a submission is processed.** The embedded form's `<form method="post" action="{% url 'core:contact' %}">` posts straight to the existing, completely unmodified `contact_view` — the same endpoint the standalone `/contact/` page has always used. `home_view` never receives or validates a POST from this form; GET requests to `/` never touch validation logic at all. Proven directly by `test_submitting_the_embedded_form_creates_a_contact_message`, which posts to `core:contact` (not `core:home`) and confirms a `ContactMessage` is created exactly as it always was.

This is the narrow allowance the brief itself grants: *"If additional context data is absolutely necessary, add it only through existing views without changing business behaviour."*

---

## Section-by-section: what was built and what data it reuses

**Section 1 — Hero.** Association name/motto/welcome message were already rendered from `SiteSettings`/`Association` (Module 1). Added: the actual `Association.logo` now appears in the hero's membership-card seal (falling back to the existing letter-avatar when no logo is uploaded — same conditional pattern already used in the nav). `SiteSettings.hero_image` — a field that existed in the model since an earlier module but was **never actually used anywhere in any template** — now provides the hero's background photo when set, applied via `home.js` reading a `data-hero-bg` attribute (never an inline `style=""`; see "CSP safety" below). The third CTA, "Vote Now," is now conditional on an active election existing, linking directly to that election's voting login — previously this button was unconditional and pointed at the generic election list.

**Section 2 — Live Statistics.** All four/five figures come from functions and methods that already existed: `apps.analytics.services.membership_overview()` (the same function every analytics dashboard already calls) for Members/Undergraduates/Alumni, and `Election.voters_count()` (the same method the results page and admin dashboard already call) for Votes Cast. "Election Status" is a badge derived from whether `elections.active` (already-existing, already-sorted context) is non-empty — no new computation. Count-up animation is handled entirely by `home.js`, which reads each card's own already-correct, server-rendered number as its animation target — there is no separate "real value" hidden in a data attribute. This matters: it means a browser with JavaScript disabled, a search engine crawler, or an automated test sees the correct number immediately, with the animation as a pure visual enhancement on top, never as the only way to learn the real figure.

**Section 3 — About.** Unchanged in substance from Module 1; only benefited incidentally from Module 1's typography refinements.

**Section 4 — Why Join.** Entirely new marketing copy (five benefit cards with inline SVG icons) — this is new *content*, not backend *data*, so there was nothing in the database to reuse here; the brief itself asks for this to be newly created. Icons are hand-written inline SVG (structural markup, not a CSP concern) rather than an icon font or library, keeping the "no unnecessary JavaScript libraries" requirement.

**Section 5 — Active Election Spotlight.** Spotlights the soonest-closing currently-active election — `elections.active` was already sorted by `end_datetime` in `_elections_by_status()` (existing code, untouched), so the spotlight is simply `elections.active.0`, picked in the template with `{% with %}`. Nothing new was computed to determine "which" election to feature. The countdown timer is pure client-side JS ticking down from the election's own `end_datetime` (already in context, already correct) — no polling, no new endpoint. When no election is active, shows the exact required string: *"No election is currently active."*

**Section 6 — Live Results Preview.** Calls `Election.results_by_position()` **exactly once**, via `{% with first_position_results=active_election.results_by_position.0 %}` — the identical method the dedicated results page (`elections/views.py::results_view`) already uses, invoked here through Django's template auto-calling instead of being pre-computed in a second Python view. No vote tallying, percentage math, or ranking logic was reimplemented; this section reuses the exact same computation, just once, for the first contested position. Progress bars reuse the existing `.vote-bar-track`/`.vote-bar-fill` classes unchanged. The "pie chart" is CSS-only (`conic-gradient`, computed by `home.js` from the same `data-percentage` values already used for the progress bars) — no charting library was added. Per the brief's only stated condition ("if an election is active"), this section shows honestly even with zero votes cast so far, rather than hiding real (if uneventful) information.

**Section 7 — Donation.** Already existed since Module 1 (as part of the homepage's general layout); restyled into a bordered `.info-card` and given an `id="donate"` anchor so the new footer "Donate" link and other pages can jump straight to it. Still reads the same, single `SiteSettings.donation_details` field, only rendered when it's non-empty. See "Known limitation" below for why this can't yet show distinct "Account Name / Account Number / Bank" fields.

**Section 8 — Contact.** New: an embedded mini version of the existing contact page's content (details + form) directly on the landing page, using the exact same `.contact-grid`/`.contact-detail` CSS already established for the standalone `/contact/` page — zero new CSS needed for the layout itself. Posts to the same, completely unmodified `contact_view`.

**Section 9 — Footer.** Already had Quick Links, Contact, Donation text, Social, and Copyright from earlier modules. This task added the two pieces that were missing: the actual `Association.logo` image, and an explicit "Donate" quick-link (pointing to the new `#donate` anchor), shown only when donation details are configured.

**Section 10 — Responsiveness.** Every new component (benefit cards, spotlight card, countdown, pie-chart-wrap) uses the same `repeat(auto-fit, minmax(...))` / flex-wrap patterns already established project-wide — no new breakpoints were needed beyond the existing ones. Verified with a real headless-browser session at a 375px mobile viewport: `document.documentElement.scrollWidth` equals `clientWidth` exactly (375px both) — confirmed zero horizontal scroll.

**Section 11 — Performance.** No JavaScript library was added — count-up, countdown, and the pie chart are all hand-written vanilla JS in one new ~150-line file. CSS handles every hover/transition effect; JS only handles the three things CSS genuinely cannot do (animated counting, a ticking clock, and computing conic-gradient stops from dynamic percentages). `home.js` is loaded only on the one page that needs it (`{% block extra_js %}`, not global). No new image assets were added by this task; the one truly new image path (`SiteSettings.hero_image`) is optional, admin-controlled, and was already a model field with existing upload validation (`MaxFileSizeValidator`) from an earlier module.

---

## Tests that had to change, and why

Two pre-existing assertions in `apps/core/tests/test_views.py` **had to be updated**, not left alone, because the brief itself mandates the exact behavior they were asserting against:

1. **`test_hero_buttons_present`** previously asserted "Vote Now" is *always* present in the hero. Module 2 explicitly requires this button to be conditional: *"If an election is currently active, automatically display a third button: Vote Now. Otherwise hide it."* The fixture this test uses has no `Election` at all, so under the new (correct, brief-mandated) behavior, "Vote Now" must **not** appear — the opposite of the old assertion. Split into three tests: the unconditional two buttons, "hidden with no election," and a new dedicated "shown and correctly linked when active."
2. **`test_statistics_section_shows_live_membership_counts`** asserted the literal text "Total Members." Module 2's brief specifies the exact label "Total Registered Members" for this card. Updated the assertion to match the new, intentional label.

Both changes were made because the *specification* changed this exact behavior on purpose, not because of an accidental regression — leaving the old assertions in place would have meant testing against a requirement the brief explicitly superseded.

---

## CSP safety (production has a strict Content-Security-Policy)

Production's `style-src 'self' https://fonts.googleapis.com; script-src 'self'` has no `'unsafe-inline'` anywhere. This module adds real dynamic styling (hero background image, pie chart colors, countdown text) that had to be done without ever writing an HTML `style=""` attribute or an inline `<script>` block.

Every dynamic style in this module is applied via **individual CSSOM property assignment** (`el.style.width = "73%"`, `el.style.background = "conic-gradient(...)"`, `el.style.backgroundImage = 'url("...")'`) — never `setAttribute("style", ...)`, never `.style.cssText`. This is the same pattern already established for the vote-bar widths in an earlier module. I did not take this on faith this time — I built a small, isolated, Django-free test page (served via Playwright's own route interception, with a genuinely strict `style-src 'self'; script-src 'self'` header attached to the real HTTP response) and confirmed directly: the external script executes, `el.style.width`/`el.style.background` are both applied exactly as requested, and the browser logs **zero** CSP violations. This is a real, structural property of how the CSP specification defines "inline style" (the HTML attribute and `<style>` elements, and `.cssText`/`setAttribute` reproductions of them) versus direct CSSOM manipulation (which was never routed through the HTML/CSS parser CSP is gating) — not a coincidence of this particular browser or a loophole that might close.

The full page (every optional section populated: logo, hero image, active election with votes) was also checked directly against the raw HTTP response bytes — `apps/core/tests/test_landing_page_experience.py::LandingPageCspSafetyTests` — confirming zero `style="` and zero `<script>` (non-`src`) occurrences in what the server actually sends, which is what CSP enforcement actually gates.

---

## Answers to the required confirmations

- **Migrations required?** No. `python manage.py makemigrations --check --dry-run` reports "No changes detected." No model field was added, removed, or altered.
- **Deployment files changed?** No. Nothing under `config/settings/` or `deploy/` was touched.
- **Settings changed?** No.
- **Backend logic changed?** No. `models.py`, `forms.py` (validation), `urls.py`, `admin.py`, authentication, permissions, and every election/analytics calculation are byte-for-byte unchanged. The one view edit (`contact_form` context key) does not alter any request-handling behavior — see "The one view change" above.
- **Tests passing?** Yes — **210/210**, run from a clean install (176 project tests before this module, 34 added across Module 1 + Module 2, 2 pre-existing assertions updated to match this module's explicit, intentional spec changes as documented above).

---

## PythonAnywhere Free Hosting compatibility

Yes, fully compatible, with no new requirements:
- No new Python package was added to `requirements.txt` — `home.js` is hand-written vanilla JavaScript, zero libraries.
- No new external network request was introduced — Google Fonts was already loaded (Module 1); this module adds no third-party script, font, or stylesheet.
- The one new potential asset, `SiteSettings.hero_image`, uses the exact same `ImageField` + `MEDIA_ROOT`/`MEDIA_URL` + WhiteNoise-adjacent media-serving setup already documented and working for every other uploaded image in the project (passport photos, candidate photos, the association logo) — no new static/media configuration was required.
- `home.js` is served exactly like the existing `site.js`: collected by `collectstatic`, hashed by `ManifestStaticFilesStorage`, served by WhiteNoise — verified directly against the real production settings module (`DJANGO_SETTINGS_MODULE=config.settings.production`), confirming the correct CSP header, a 200 response, and a correctly manifest-hashed `<script src="...">` reference in the rendered page.

---

## Known frontend weakness identified during this module (documented, not fixed)

**`SiteSettings.donation_details` is a single free-text field, not structured data.** The brief for Section 7 asks for distinctly labeled *Account Name*, *Account Number*, *Bank*, and a *short donation message* — genuinely separate pieces of information. The current model only has one `TextField`, so the "professional" presentation this task built can style the block as a whole (card, border, monospace-ish emphasis) but cannot give each individual fact its own icon, label, or layout treatment — it can only render whatever the administrator typed, line by line, trusting them to follow a `Bank: ...` / `Account Name: ...` / `Account Number: ...` convention that nothing enforces or validates.

This wasn't fixed in this module because doing so properly requires adding new fields to `SiteSettings` (e.g. `donation_bank_name`, `donation_account_name`, `donation_account_number`, `donation_message`) — a `models.py` change explicitly out of scope for "Only improve the Landing Page experience." Flagged here, as instructed, rather than silently working around it or quietly changing an unrelated file. A future module focused on Site Settings/admin data structure would be the right place to address this; the presentational groundwork (a dedicated `#donate` section, footer link, and card styling) is already in place to receive genuinely structured fields with no further template rework needed once they exist.
