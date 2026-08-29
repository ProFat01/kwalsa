# SAMS — Student Association Management System

A Django app for running a student association's membership, elections,
and analytics: online registration with staff approval, QR-verified
membership cards, rule-driven elections with live results, a member
directory/filtering tool, an email Communication Center, and
association-wide analytics dashboards. Built for the Malam Sidi
Students Association; scoped to a single association per deployment
(see `DEFAULT_ASSOCIATION_SLUG` below).

Django 6.0.6, Python 3.12+, SQLite by default (WAL mode) with an easy
PostgreSQL swap when needed — see PRODUCTION_DEPLOYMENT_2.md.

## Quickstart (local development)

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then fill in SECRET_KEY etc.

python manage.py migrate
python manage.py setup_roles       # creates the 4 staff role groups + permissions
python manage.py createsuperuser

python manage.py runserver
# -> http://127.0.0.1:8000/admin/
```

First thing to do in the admin: create the `Association` row for your
association (matching `DEFAULT_ASSOCIATION_SLUG` in `.env`) — every
Member/Election/Position created after that hangs off it.

Run the test suite with `python manage.py test` (328 tests as of the
v2.0 validation pass).

## Project layout

```
apps/
├── core/         # Association (tenant), SiteSettings, public landing pages
├── accounts/     # Custom User, staff role groups, Communication Center
├── members/      # Member, RegistrationApplication, membership cards, QR verification
├── elections/    # Position, Election, Candidate, Vote, the Eligibility Engine
└── analytics/    # Membership/age/course/institution/election dashboards + snapshots
```

## Documentation map

- **ARCHITECTURE.md** — models, permissions, and admin structure (written
  during the initial backend-foundation phase; later modules below cover
  what was layered on top of it).
- **REGISTRATION_MODULE.md** — registration → approval → membership card workflow.
- **ELECTION_MODULE.md** — the Eligibility Engine, voting flow, live results.
- **ANALYTICS_MODULE.md** — the analytics dashboards and JSON endpoints.
- **PUBLIC_WEBSITE_MODULE.md** / **LANDING_PAGE_EXPERIENCE.md** — the public-facing pages.
- **ROLE_DASHBOARDS.md** — what each staff role (Registration/Election/Analytics/Super Admin) can see and do.
- **FRONTEND_DESIGN_SYSTEM.md** — CSS/JS conventions, CSP-safe patterns.
- **PRODUCTION_DEPLOYMENT.md** + **PRODUCTION_DEPLOYMENT_2.md** — the full
  PythonAnywhere deployment guide, backup/restore procedure, and known
  operational limits (SQLite scale, Communication Center bulk-send).

## Support

Not a hosted product — this is a codebase handed over to whoever runs
it for their association. There is no support contact; the docs above
are the full operational reference.
