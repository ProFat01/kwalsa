# KWALSA Customization Notes (preparation pass — no rebranding done yet)

This file inventories every place in SAMS that currently carries the
previous association's identity (Malam Sidi Students Association / "MSA" /
`msaweb.pythonanywhere.com`) so a future rebranding pass has a checklist.
Nothing listed here has been changed. Branch: `kwalsa-customization`.

## A. Data, not code (do this first, in the Django admin — zero code changes)

SAMS is already multi-tenant: branding lives in DB rows, not in code.
Once deployed, create/edit these two rows in `/admin/`:

- `core.Association` — `name="Kwami Local Government Students Association"`,
  `short_name="KWALSA"`, `slug="kwalsa"`, `logo=<the KWALSA crest>`.
  `short_name` automatically drives membership IDs (`KWALSA-2026-0001`,
  see `apps/members/utils.py:generate_membership_id`) — no code change needed.
- `core.SiteSettings` (one-to-one with the Association above) —
  `motto="Learn, Unite & Serve"`, `contact_email="kwalsanational@gmail.com"`,
  `welcome_message`, `about_text`, `mission`, `vision`, `leadership_text`,
  social links, `hero_image`.

## B. Environment variables (deployment-time, not code)

Set in `.env` on the `kwalsa.pythonanywhere.com` PythonAnywhere account
(never commit the real `.env`):

- `DEFAULT_ASSOCIATION_SLUG=kwalsa` (must match the slug in A above)
- `ALLOWED_HOSTS` / production `ALLOWED_HOSTS` list → add `kwalsa.pythonanywhere.com`
- `CSRF_TRUSTED_ORIGINS=https://kwalsa.pythonanywhere.com`
- `DEFAULT_FROM_EMAIL` / Mailjet sender → `kwalsanational@gmail.com`
  (must also be a verified sender in the Mailjet account)
- `DJANGO_DB_PATH` → path under the `kwalsa` PythonAnywhere home dir
- `deploy/pythonanywhere_wsgi.py` → replace `PYTHONANYWHERE_USERNAME = "yourusername"`
  with the real `kwalsa` account username (already a placeholder, not hardcoded to MSA)

## C. Hardcoded strings that still need editing (found by inspection)

These are template/text defaults, not data — they only show if the DB
`association`/`site_settings` context is empty, but should still be
updated so KWALSA never accidentally shows "Malam Sidi":

| File | Line(s) | Content |
|---|---|---|
| `templates/base.html` | 6–9 | `<title>`, meta description, OG title/description say "Malam Sidi Students Association" |
| `templates/base.html` | 106, 139 | `{{ association.name\|default:"Malam Sidi Students Association" }}` — fallback text |
| `apps/core/templates/core/home.html` | 6 | meta description fallback |
| `apps/core/templates/core/about.html` | 5 | meta description fallback |
| `apps/core/templates/core/contact.html` | 5 | meta description fallback |
| `apps/members/templates/members/register.html` | 5 | meta description: "Register for membership at Malam Sidi Students Association." |
| `apps/members/email_service.py` | 41 | `APPROVAL_EMAIL_SUBJECT = "Welcome to Malam Sidi Students Association"` |
| `README.md` | intro | "Built for the Malam Sidi Students Association" |
| `.env.example` | `DEFAULT_ASSOCIATION_SLUG=msa`, `CSRF_TRUSTED_ORIGINS=https://msaweb.pythonanywhere.com` | example values only, not read at runtime |
| `config/settings/production.py` | `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS` | currently hardcoded to `msaweb.pythonanywhere.com` — needs `kwalsa.pythonanywhere.com` |

## D. Files that reference "MSA" but should generally be LEFT ALONE

- `apps/**/tests/test_*.py` — use `"MSA"` purely as sample/fixture tenant
  data inside test cases. This is normal test-data, not branding; changing
  it risks unrelated diffs and is unnecessary (tests create their own
  throwaway `Association` rows and don't touch the real KWALSA data).
- `apps/core/migrations/0001_initial.py` — the string `"MSA"` there is only
  inside a field's `help_text` (documentation shown in the admin form),
  not a stored value. No migration changes are needed for rebranding.
- `apps/members/utils.py` — docstring/comment examples only (`MSA-2026-0001`),
  the logic itself is already dynamic (see section A).
- `ARCHITECTURE.md`, `ELECTION_MODULE.md`, `PRODUCTION_DEPLOYMENT.md`,
  `PUBLIC_WEBSITE_MODULE.md`, `REGISTRATION_MODULE.md` — historical/
  architecture docs that mention MSA as the original launch tenant;
  update prose only if desired, not required for KWALSA to function.

## E. Not found (confirmed absent)

- No hardcoded logo/crest image files in `static/` — logos are uploaded
  via `Association.logo` / `SiteSettings.hero_image` (ImageField, media/).
- No fixture/seed files that create an "MSA" Association row — the tenant
  row must already be created by hand via the admin either way, so there
  is nothing to migrate away from.
