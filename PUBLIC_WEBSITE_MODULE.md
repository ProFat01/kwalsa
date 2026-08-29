# Public Website & User Experience Layer

This is the first module where real visual design mattered — every prior
module's brief explicitly said "keep styling simple." This one asks for
"professional, clean... suitable for real students, alumni,
administrators." The design direction below is deliberate, not default
Bootstrap-looking output.

## Design direction

SAMS isn't a startup product — it's a small civic institution, and the
data already reads like one: `MSA-2026-0001`, `APP-2026-00001`, vote
tallies, turnout percentages. That's the signature thread this design
builds on, rather than decorating on top of:

- **Color**: ink navy (`--ink`), civic green (`--civic-green`, ballot-box
  green — the primary action color), brass (`--brass`, used sparingly for
  accents), on a cool, neutral paper background (`--paper`) — deliberately
  *not* the warm cream background that's become a generic "AI-generated
  site" tell.
- **Type**: Fraunces (a characterful serif, not the generic high-contrast
  serif used everywhere) for headings; Inter for body/UI text; **IBM Plex
  Mono reserved exclusively for "records"** — membership IDs, application
  numbers, vote counts, percentages, turnout — via a single `.record`
  utility class. Prose never uses it. This is the one consistent
  typographic signal that ties every page back to "this is an official
  record-keeping system."
- **Signature element**: a CSS-only membership card mockup in the hero
  (`.member-card`), echoing the real `MSA-2026-0001` format members
  actually receive — not a stock photo or generic illustration, a motif
  built directly from the product's own data shape. Paired with a "ledger
  strip" (`.ledger`) directly below the hero showing live statistics in
  the same record typeface — one element for "your personal record," one
  for "the institution's aggregate record."

All of this lives in two CSS files (PART 10's "CSS Structure"):
- `static/css/base.css` — design tokens, reset, typography, header/nav/
  footer, buttons, forms, alerts, accessibility primitives (focus rings,
  skip link). The "site chrome."
- `static/css/components.css` — reusable components (badges, tables,
  summary stats, vote bars, cards) plus the landing page's specific
  sections (hero, member card, ledger, status columns, CTA). The
  "page-specific vocabulary."

No build step, no UI framework (per PART 10) — both files are plain CSS
with custom properties, linked directly in `base.html`.

## What's new vs. what's improved

**Brand new** (apps.core had zero views/URLs before this task):
- `apps/core/views.py`: `home_view`, `about_view`, `contact_view`
- `apps/core/forms.py`: `ContactForm`
- `apps/core/urls.py`, mounted at `/` in `config/urls.py`
- `ContactMessage` model + admin
- `SiteSettings` gained content fields: `motto`, `welcome_message`,
  `mission`, `vision`, `leadership_text`, `donation_details`

**Improved, not rewritten** — every existing registration/election/status
template got a `.container` wrapper, the new design tokens, and minor
accessibility additions (`role="alert"`, explicit `required`, `<time>`
elements). **No views, forms, or URLs in `apps.members` changed at all.**
`apps.elections` got exactly one small, additive context change (below)
— nothing else.

## The one view change, and why it was necessary

PART 5 explicitly requires manifestos on the Ballot and Election Detail
pages. `Candidate.manifesto` already existed but `ballot_view`'s context
only passed the bound form field, whose `CandidateChoiceField` (by
design, from the election module) renders just the candidate's name as
the radio label — there was no way to reach the manifesto from inside
the auto-rendered widget.

The fix: `ballot_view` now also passes each position's `Candidate`
queryset alongside its form field. The *field* — used for `cleaned_data`,
validation, the uniqueness constraint, everything that matters for
PART 6/10's security — is completely unchanged. `ballot.html` now renders
the radio inputs by hand (`name="{{ item.field.html_name }}"`,
`value="{{ candidate.pk }}"`) instead of relying on Django's
auto-rendered widget, purely so the manifesto can sit next to each
option. Verified with a dedicated test
(`test_ballot_radio_inputs_still_submit_correctly_with_manual_markup`)
that a real submission through the hand-rendered markup still works
exactly as before.

## Site Settings (PART 9)

Two deliberate non-additions, both to avoid duplicating something that
already exists:

- **No `SiteSettings.logo` field.** `Association.logo` already means
  exactly this (added in the architecture phase). A second logo field
  would just create two places that could disagree about which image is
  "the" logo — checked explicitly in
  `test_does_not_duplicate_association_logo`.
- **No dedicated `Leadership` model.** The brief calls these "editable
  content blocks" and lists Leadership alongside History/Mission/Vision
  — all four are implemented identically, as plain `TextField`s on
  `SiteSettings`. `leadership_text` is free text for now (e.g. "President:
  Jane Doe, Secretary: ..."); upgrading to per-person profiles with
  photos later would be a clean, isolated addition if that's ever
  actually needed — not built ahead of being asked for.

The landing page reads `SiteSettings` and live statistics from
`apps.analytics.services.membership_overview()` — the exact same
function the analytics dashboards call (PART 9: "Landing page should
read from Site Settings" + reusing the existing service layer rather
than recomputing membership counts a third way).

## Contact system (PART 8)

`ContactMessage` (new model, `apps.core`) stores every inquiry —
`association`, `name`, `email`, `subject`, `message`, `submitted_at`,
plus `is_read` for admin triage. The admin can mark messages read/unread
in bulk but can't create or edit message content (`has_add_permission`
returns `False`; `name`/`email`/`subject`/`message` are all readonly) —
these only ever arrive through the public form, and editing what someone
actually wrote would be the wrong kind of "moderation."

`contact_view` uses Django's messages framework
(`django.contrib.messages`) for the success confirmation — the first real
use of flash messages in this project, now rendered by every page via
`base.html`'s `{% if messages %}` block (PART 1). Existing success pages
(registration success, vote success) deliberately keep their own
dedicated, more detailed confirmation templates rather than switching to
a flash banner — a one-line toast would be a worse experience for
"here's your application number," not a better one.

Only **Super Admin** can view/manage `ContactMessage` in the admin
(`core.view_contactmessage`, `core.change_contactmessage`,
`core.delete_contactmessage`, added to `ROLE_SUPER_ADMIN` in
`apps/accounts/permissions.py`) — general site inquiries don't obviously
belong to Registration/Election/Analytics Admin's specific domains, so
this stays with the broadest role rather than being arbitrarily assigned
to one specialist role.

## Accessibility (PART 11)

- Skip link (`.skip-link`, jumps to `#main-content`) on every page.
- Visible focus rings on every interactive element
  (`:focus-visible { outline: 3px solid var(--brass); }`), not just the
  browser default outline removed-and-forgotten.
- Every form field uses a real `<label for="...">`; error messages get
  `role="alert"` so screen readers announce them immediately.
- The mobile nav toggle is a real `<button>` with `aria-expanded`/
  `aria-controls`, kept in sync by the (vanilla, ~8-line) JS — not a
  `<div onclick>`.
- Flash messages render inside `role="status" aria-live="polite"`.
- Heading hierarchy was audited on every page with a small script
  (parsing rendered HTML for `<h1>`–`<h6>` and checking for level skips)
  and one real issue was found and fixed: the footer's column labels were
  `<h4>`, which skips levels on any page whose content ends at `<h2>` or
  `<h1>` (most of them). Since the *correct* heading level for a footer
  varies per page — there's no single right answer — the labels were
  changed to non-heading `<p class="footer-heading">` elements instead,
  styled identically. Re-running the audit confirmed zero skips across
  every page.
- `prefers-reduced-motion: reduce` respected globally.

## SEO basics (PART 12)

`base.html` defines `{% block title %}`, `{% block meta_description %}`,
`{% block og_title %}`, `{% block og_description %}` with sensible
association-aware fallbacks; every page overrides at least `title` and
`meta_description` with real, specific content (not just "Page —
SAMS" everywhere). One implementation note: Django templates don't
support Jinja2's `{{ self.title }}` — `og_title` is its own independent
block with its own default, not a reference to the `title` block's
rendered output.

## Responsive design (PART 10)

No framework, no breakpoints-for-everything — most layouts use
`grid-template-columns: repeat(auto-fit, minmax(...))`, which reflows
naturally without explicit media queries (footer columns, the ledger
strip, the about-page grid, election status columns). Explicit
`@media (max-width: ...)` rules exist only where a layout genuinely needs
a structural change at narrow widths: the nav collapses to a toggleable
mobile menu at 760px, the hero's two-column grid stacks at 860px, and
(added after a deliberate check) data tables become horizontally
scrollable rather than overflowing at 600px.

## Template organization (PART 13)

Already-compliant with the requested structure before this task started
— `members`/`elections`/`analytics` each already keep their templates at
`apps/<name>/templates/<name>/`, the standard Django app-namespaced
convention. This task just continued it: `apps/core/templates/core/` is
new, nothing else moved. `templates/base.html` (project root) stays the
one genuinely shared, cross-app layout — that's standard practice, not a
violation of the per-app convention. `accounts` has no templates because
it has no public views (Django admin handles that app's UI entirely);
nothing was created there to avoid an empty, pointless directory.

## Tests (PART 14)

```bash
python manage.py test apps.core                          # 17 tests, new
python manage.py test apps.elections.tests.test_manifesto_display  # 4 tests, new
python manage.py test                                     # 140 tests, full project
```

| File | Covers |
|---|---|
| `apps/core/tests/test_models.py` | new `SiteSettings` fields round-trip; no duplicate logo field; `ContactMessage` defaults/ordering |
| `apps/core/tests/test_views.py` | landing page renders for anonymous visitors, hero shows name/motto/welcome message, all three hero buttons present, live statistics reflect real `Member` data, election status sections correctly show upcoming/active/completed, CTA buttons present, graceful empty state with no `Association` configured; About page renders all four content blocks and falls back to placeholder text; Contact page shows configured details, valid submission creates a `ContactMessage` and shows the flash message, missing/invalid fields are rejected without creating a record |
| `apps/elections/tests/test_manifesto_display.py` | manifesto appears on both Election Detail and Ballot pages; a candidate with no manifesto doesn't break rendering; the hand-rendered ballot radio inputs still produce a valid, correctly-recorded vote |

"Election Pages" and "Status Checker Pages" testing (also listed in
PART 14) is covered by the existing, comprehensive
`apps/elections/tests/` (45 tests) and `apps/members/tests/` (35 tests)
suites from their own modules — re-run after every template change in
this task specifically to confirm the polish never altered behavior, not
duplicated here.

One real bug caught by the test suite during this task, worth recording:
`assertRedirects()` follows a redirect *itself* by default to verify the
target returns 200 — which silently consumed the one-shot flash message
before the test's own follow-up `.get()` could see it. Fixed by checking
`response.status_code`/`response["Location"]` manually instead of via
`assertRedirects` for that one test.

## Running it

```bash
python manage.py migrate
python manage.py setup_roles

python manage.py shell -c "
from apps.core.models import Association, SiteSettings
assoc, _ = Association.objects.get_or_create(name='Malam Sidi Students Association', short_name='MSA', slug='msa')
SiteSettings.objects.get_or_create(association=assoc, defaults={
    'motto': 'Unity in Service',
    'welcome_message': 'Welcome to MSA — register, vote, and stay informed.',
})
"

python manage.py runserver
# -> http://127.0.0.1:8000/        (landing page)
# -> http://127.0.0.1:8000/about/
# -> http://127.0.0.1:8000/contact/
```
