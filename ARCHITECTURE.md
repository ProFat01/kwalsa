# SAMS — Architecture Reference (Phase 1: backend foundation)

Scope of this phase: **apps, models, permissions, admin only.** No
templates/CSS/JS/dashboards yet — those are a later phase and will be
layered on top of what's described here without changing this layer.

Verified against a real install: Django 6.0.6 on Python 3.12, full
`makemigrations` → `migrate` → `setup_roles` → admin smoke test cycle run
successfully against SQLite before this was handed over.

---

## 1. Complete project structure

```
sams/
├── manage.py
├── requirements.txt
├── .env.example                  # copy to .env locally; never commit .env
├── .gitignore
│
├── config/                       # project-level config, no business logic
│   ├── settings/
│   │   ├── base.py               # shared: INSTALLED_APPS, MIDDLEWARE, AUTH_USER_MODEL...
│   │   ├── development.py        # DEBUG=True, SQLite + WAL, console email
│   │   └── production.py         # DEBUG=False, security headers, CSP, SQLite (for now)
│   ├── urls.py                   # admin/ only at this phase
│   ├── wsgi.py
│   └── asgi.py
│
├── apps/                         # all local apps, imported as "apps.<name>"
│   ├── core/                     # Association (tenant), SiteSettings, SequenceCounter
│   ├── accounts/                 # custom User, role groups, setup_roles command
│   ├── members/                  # Member, RegistrationApplication, AlumniRecord
│   ├── elections/                # Position, Election, Candidate, Vote
│   └── analytics/                # MembershipSnapshot, AgeDistributionSnapshot, ElectionResultSnapshot
│
├── templates/base.html           # shared layout; members/* and elections/* templates extend this
├── static/css/site.css           # plain functional CSS, shared across modules
└── media/       (empty, .gitkeep) # passport photos, receipts, candidate photos at runtime
```

See `REGISTRATION_MODULE.md` for the member registration module,
`ELECTION_MODULE.md` for the election management module,
`ANALYTICS_MODULE.md` for the analytics module,
`PUBLIC_WEBSITE_MODULE.md` for the public website / UX layer,
`ROLE_DASHBOARDS.md` for the role-adaptive staff dashboard hub, and
`FRONTEND_DESIGN_SYSTEM.md` for the Module 1 global design-system
polish pass, all built on top of this foundation.

Each app follows the same internal shape:

```
apps/<name>/
├── __init__.py
├── apps.py            # AppConfig, name = "apps.<name>"
├── models.py
├── admin.py
├── migrations/
│   ├── __init__.py
│   └── 0001_initial.py   # already generated + applied against SQLite, see §8
└── (validators.py / utils.py / signals.py / permissions.py / management/ where relevant)
```

**Why `apps/<name>` instead of top-level `<name>/`:** namespacing every
local app under one `apps` package means a future third-party package
that happens to be called `core` or `accounts` can never collide with
ours, and `INSTALLED_APPS` reads as "these five are ours" at a glance.

---

## 2. App responsibilities

| App | Owns | Does NOT own |
|---|---|---|
| **core** | `Association` (tenant root), `SiteSettings` (per-tenant branding), `SequenceCounter` (shared ID-generation primitive) | Public statistics — those are *read*, never stored, from `analytics` |
| **accounts** | Custom `User`, role `Group` definitions, `permissions.py` mapping, `setup_roles` command | Member identity — a Member doesn't need a `User` to exist |
| **members** | `Member`, `RegistrationApplication`, `AlumniRecord` | Voting — Member is *referenced* by elections, not the other way around |
| **elections** | `Position`, `Election`, `Candidate`, `Vote` | Result publication state — lives in `analytics.ElectionResultSnapshot` |
| **analytics** | Precomputed snapshots: `MembershipSnapshot`, `AgeDistributionSnapshot`, `ElectionResultSnapshot` | Raw data — never duplicates Member/Vote rows, only aggregates of them |

---

## 3 & 4. Models and relationships

```
Association (core)
 ├──1:1── SiteSettings
 ├──1:N── SequenceCounter            (one row per "key" being counted)
 ├──1:N── Member ───────────────────┐
 │         ├──1:N── RegistrationApplication
 │         ├──1:1── AlumniRecord (optional)
 │         ├──0:1── User (optional, future self-service login)
 │         └──1:N── Vote ───────────┐
 ├──1:N── Position                  │
 ├──1:N── Election                  │
 │         ├──M:N── Position             (which offices this election contests)
 │         ├──1:N── Candidate ──────┤
 │         │         └──1:N── Vote ─┘   (Vote: election + member + candidate + position)
 │         └──1:N── ElectionResultSnapshot  (one per contested Position)
 ├──1:N── MembershipSnapshot
 └──1:N── AgeDistributionSnapshot
```

**Member ↔ RegistrationApplication is a plain FK, not OneToOne.** A
rejected applicant can re-apply; making it OneToOne would force deleting
or overwriting the rejected application to allow a second attempt,
destroying the audit trail of *why* they were rejected the first time.
The signal in `members/signals.py` watches `RegistrationApplication`
status transitions and pushes the outcome onto `Member` (sets
`approval_status`, flips `voting_status`, generates `membership_id` on
first approval) — so admins review through one workflow object and the
Member record can never drift out of sync with the latest decision.

**One Election, multiple Positions, multiple Candidates per Position —
one vote per member per Position.** `Election.positions` is an explicit
M2M to `Position`: it declares the ballot's shape (which offices are
being contested) independently of which candidates have been nominated
yet. `Candidate.clean()` then requires a candidate's position to
actually be one of `election.positions` — you define the ballot first,
then nominate candidates against it, not the other way around.

`Vote` carries a `position` field that's *denormalized* from
`candidate.position` (auto-assigned in `Vote.clean()`/`save()`, never set
by hand — see `Vote._assign_position()`). That denormalization exists
for exactly one reason: a database `UniqueConstraint` can only reference
columns that physically live on the table being constrained — it can't
reach through `candidate.position` to enforce uniqueness. Copying
position onto `Vote` itself lets `UniqueConstraint(fields=["election",
"member", "position"])` be a *real* database guarantee — "an approved
member can cast at most one vote per position, in one election" holds
even against a concurrency bug or a future API that forgets to check
first, not just an application-level `if` that something could race
past. A member can still cast one vote each for President, Secretary,
Treasurer, etc., in the same election — they're just capped at one each,
not capped at one for the whole election.

*(This supersedes the project's very first iteration, which modeled "one
vote per election" with no position field at all — i.e., one Election =
one single contested office, with a multi-position ballot needing
several Election rows sharing a voting window. That was flagged at the
time as a real design fork rather than silently picked, and has now been
superseded by the explicit multi-position model above per your
direction.)*

**Why `SequenceCounter` (core) backs both `membership_id` and
`application_number`:** Naively computing the next ID as
`Member.objects.count() + 1` races under concurrent registrations and
*will* eventually mint a duplicate ID under real traffic. A locked
counter row (`select_for_update()` inside `@transaction.atomic`, see
`core/utils.get_next_sequence`) serialises only the increment, not the
whole table — same pattern as the certificate-ID generation already
proven elsewhere in your other Django projects.

**Why `AlumniRecord` is a separate table, not extra columns on
`Member`:** alumni-specific fields (`graduation_year`,
`current_employer`, ...) would sit NULL for every undergraduate
otherwise. Splitting it out means the common case (querying active
undergraduates) never carries dead weight, and the alumni-specific shape
can grow later (employment history, donations) without touching
`Member`.

**Why `analytics` stores snapshots instead of computing live:** a public
statistics page hitting `COUNT()`/`GROUP BY` on `Member`/`Vote` on every
request doesn't scale, and "age" is only meaningful as of a point in
time — there is deliberately no stored "age" field on `Member` anywhere;
it's computed from `date_of_birth` and bucketed into
`AgeDistributionSnapshot` by whatever job generates the snapshot.
`ElectionResultSnapshot` is one row **per (Election, Position)**, not per
Election — now that one election can contest several offices at once,
"the winner" and "turnout" are only meaningful per office (a member might
vote for President but abstain on Secretary, so turnout genuinely differs
by position too).

---

## 5. Permission architecture: Groups vs. Permissions vs. custom permissions

**The approach taken: Django's built-in `Group` + `Permission` system,
extended with custom permissions declared per-model, assigned via a
management command — no hand-rolled role field.**

Why, concretely:

- **Groups, not a `role` CharField on `User`.** A field would mean every
  permission check is `if user.role == "registration_admin"` scattered
  through code — brittle, and impossible to combine (a user who's both
  Election Admin *and* Analytics Admin needs two roles at once, which a
  single field can't express but `user.groups.add(...)` trivially can).
- **Django's default per-model permissions (`add_`/`change_`/`delete_`/
  `view_<model>`) cover most of CRUD for free** — they're created
  automatically by `migrate`, and every `ModelAdmin` already checks them
  before showing the add/change/delete buttons. No custom code needed for
  "can this role edit a Position".
- **Custom permissions (`Meta.permissions` on the model) for the things
  default CRUD can't express**, because "can change a Member" and "can
  *approve* a Member" are genuinely different authorities — a future
  read/write API view might let a Registration Admin edit a typo in
  `full_name` without also letting them rubber-stamp approval. Declared
  per model:
  - `members.Member`: `approve_member`, `manage_alumni_status`
  - `members.RegistrationApplication`: `review_application`
  - `elections.Election`: `manage_election`, `publish_results`
  - `analytics.MembershipSnapshot`: `view_analytics_dashboard`
- **A management command (`setup_roles`), not a `post_migrate` signal**,
  creates the four groups and attaches permissions from the single
  source of truth `apps/accounts/permissions.py::ROLE_PERMISSIONS`. A
  signal handler in `accounts` would risk firing before
  `members`/`elections`/`analytics` have created the `Permission` rows
  their own models need — Django creates each app's permissions in its
  *own* `post_migrate` step, in `INSTALLED_APPS` order, not all at once.
  Running the command once after the *entire* `migrate` finishes
  sidesteps that ordering trap, is idempotent (`python manage.py
  setup_roles` re-run any time `ROLE_PERMISSIONS` changes), and shows up
  explicitly in deploy logs instead of being invisible magic.

**The four roles, concretely:**

| Role | Can | Cannot |
|---|---|---|
| **Super Admin** | Everything across core/members/elections/analytics | Manage `auth.Group`/`auth.Permission` (see below) |
| **Registration Admin** | View/approve/reject Members & Applications, manage Alumni conversion | Touch Elections, Candidates, or Votes at all |
| **Election Admin** | Manage Elections/Positions/Candidates, view Votes (audit only, never edit), publish results | Approve members, touch membership data |
| **Analytics Admin** | View all snapshot dashboards, view (not edit) Member/Election data for context | Change anything — this role is read-only by design |

**Deliberately excluded from every role, including Super Admin's
group:** permission to change `auth.Group` or `auth.Permission`
themselves. Granting that to a non-superuser account is a
privilege-escalation path — that account could add itself to any group,
including one with full access. Real "give someone unrestricted access"
should be a Django **superuser** (`is_superuser=True`, bypasses
permission checks entirely, separate from any group), not a member of a
"Super Admin" group with broad-but-bounded permissions. The group exists
for staff who need wide app access without touching Django's own
user/permission machinery.

**Votes are special-cased beyond permissions, in `VoteAdmin` directly:**
`has_add_permission`/`has_change_permission` return `False`
unconditionally (votes are only ever meant to be created by a future
member-facing voting view with its own eligibility checks, never typed
in by staff), and `has_delete_permission` is restricted to
`request.user.is_superuser` — a documented emergency-only escape hatch,
not a normal workflow, because ballot integrity matters more than
admin convenience.

---

## 6. Admin configuration highlights

- **ORM-optimised list views**: `list_select_related` on every
  `ModelAdmin` whose `list_display` crosses a FK (`Member.association`,
  `Candidate.election`/`position`, `Vote.election`/`member`/`candidate`,
  etc.) — same `select_related` discipline as your other Django projects,
  applied at the admin layer this time.
- **Inlines mirror the real workflow**: `RegistrationApplicationInline`
  and `AlumniRecordInline` under `Member` (full history, read-mostly);
  `CandidateInline` under `Election` (build the ballot in one screen) —
  its position dropdown is dynamically narrowed to only the positions
  already added to that election's `positions` field
  (`CandidateInline.get_formset`), so staff can't nominate a candidate
  for an office that isn't actually on the ballot; `ElectionAdmin` shows
  a `filter_horizontal` widget for picking those positions in the first
  place.
- **Bulk actions that respect business rules**: `approve_applications`
  only ever bulk-*approves* (rejection requires a
  `rejection_reason`, which only makes sense to capture per-application
  through the form — enforced by `RegistrationApplication.clean()`, not
  just left to admin discipline); `convert_selected_to_alumni`;
  `clear_receipt_images` for storage cleanup post-review.
- **Server-set audit fields, never user-editable**: `reviewed_by` on
  `RegistrationApplication` and `published_by` on
  `ElectionResultSnapshot` are set in `save_model()` from
  `request.user`, not exposed as form fields — so a reviewer can't be
  misattributed by editing a dropdown.
- **Generated tables are view-only in the admin**: `SequenceCounter`,
  `MembershipSnapshot`, `AgeDistributionSnapshot` block add/change
  entirely (`has_add_permission`/`has_change_permission` → `False`) since
  hand-editing any of them would let them silently disagree with the
  real underlying data. `ElectionResultSnapshot` is the one exception —
  its vote-derived numbers are readonly, but `is_published` and
  `winner_candidate` stay editable since that *is* the publish workflow.

---

## 7. Validation rules

| Field | Rule | Where enforced |
|---|---|---|
| `Member.phone_number` | exactly 11 digits, numbers only | `RegexValidator` in `members/validators.py`, **and** `unique=True` at the DB level |
| `Member.nin_number` | exactly 11 digits, numbers only | same pattern, separate validator instance |
| `Member.membership_id` | unique, only ever set on approval | `unique=True, blank=True, null=True`; generation happens once in `signals.py` |
| `RegistrationApplication.application_number` | unique, auto-generated on first save | `unique=True, editable=False`; `save()` calls `generate_application_number()` if blank |
| `RegistrationApplication.rejection_reason` | required when `status == REJECTED` | `clean()` — raised as a real `ValidationError`, not just a UI hint, so it can't be bypassed via the admin, a future API, or the Django shell |
| Passport photo / receipt / candidate photo | size-capped (5 MB default) | `MaxFileSizeValidator` in `members/validators.py`, configurable via `settings.MAX_UPLOAD_SIZE_MB` |
| `Election.end_datetime` | must be after `start_datetime` | `clean()` |
| `Candidate.position` | must belong to the same association as its `Election`, **and** must be one of that election's declared `positions` | `clean()` |
| `Vote` | one per `(election, member, position)` — a member can vote once per office, not once per whole election | **DB-level** `UniqueConstraint`; `position` is auto-assigned from `candidate.position` (never set by hand) so the constraint always reflects reality |
| `Vote` | candidate must belong to the stated election; member must be `voting_status=True`; election must be currently open | `clean()` (defence-in-depth on top of the DB constraint above) |
| `ElectionResultSnapshot.winner_candidate` | must be a candidate for that snapshot's own position | `clean()` |

All of the above were exercised against a real SQLite database during
development (duplicate phone/NIN correctly rejected by the unique
constraint, malformed phone/NIN correctly rejected by `full_clean()`,
rejection-without-reason correctly blocked, double-voting correctly
rejected by the `UniqueConstraint`, an unapproved member correctly
blocked from voting).

---

## 8. Migration strategy

**Dependency order matters and was respected:** `core` (no FKs out) →
`accounts` (custom `User`, must exist before `AUTH_USER_MODEL` is first
used by `migrate`) → `members` (FKs to `core.Association` and
`AUTH_USER_MODEL`) → `elections` (FKs to `core`, `members`) →
`analytics` (FKs to `core`, `elections`). `makemigrations core accounts
members elections analytics` in that order, then one `migrate`, produced
a clean single `0001_initial.py` per app with no circular-dependency
issues — already generated and committed in each app's `migrations/`
folder. (`analytics` later split into `0001_initial.py` +
`0002_initial.py` after the multi-position refactor below — Django does
this automatically when a cross-app FK graph needs two passes to resolve;
it's normal, not a sign of a problem, and both are already applied
cleanly in testing.)

**Multi-position election refactor — a real example of evolving this
schema:** when the ballot structure changed from "one Election = one
office" to "one Election contests several Positions, one vote per
Position", the `elections` and `analytics` migrations were *regenerated*
from a clean `0001_initial.py` rather than patched with a chain of
`0002`/`0003`/`0004` migrations — because at that point this project had
not been deployed or migrated against any real database anywhere
(confirmed before doing it). That's the one case where rewriting
migration history is safe, and Django's own docs endorse deleting and
regenerating migrations for an app that hasn't shipped yet. **The moment
this project has a real deployed database with member/vote data in it,
that option is gone** — any future schema change like this one would
instead need to add a *nullable* field first, backfill it with a data
migration (`RunPython`), and only then tighten it to `NOT NULL` in a
third migration, exactly as called out in the `Vote.position` docstring
in `elections/models.py`.

**The one genuinely irreversible decision in this whole project:**
`AUTH_USER_MODEL = "accounts.User"` is set in `config/settings/base.py`
*before* the first `migrate` ever ran. Changing a project's user model
after tables exist requires manually rewriting every FK that points at
`auth.User`, project-wide — by far the most common "wish we'd known on
day one" Django mistake. Since SAMS is brand new, this was simply done
correctly from the start rather than something to "fix later".

**Going forward, for every future change once real data exists:**
1. Edit the model.
2. `python manage.py makemigrations <app_label>` — scope it to the one
   app you changed rather than running it bare, so you can read exactly
   what's about to be generated before it touches other apps.
3. Read the generated migration. SQLite's limited `ALTER TABLE` support
   means Django sometimes rewrites a whole table to add one column —
   harmless, but worth knowing it's happening on a large table.
4. `python manage.py migrate`.
5. If `ROLE_PERMISSIONS` changed (new custom permission, new app), re-run
   `python manage.py setup_roles`.

**Squashing:** once there are 10+ migrations in a single app with no
external consumers depending on the intermediate ones,
`squashmigrations` is safe to run; not needed yet at `0001_initial`.

---

## 9. Future PostgreSQL migration

SQLite v1 is right for now (PythonAnywhere's lower tiers, MSA's expected
traffic outside election windows, zero ops overhead). Two genuinely
different triggers should prompt moving off it, and they call for
different responses:

- **A single election with many concurrent voters.** SQLite serialises
  writers; `development.py`/`production.py` already turn on WAL mode
  (`PRAGMA journal_mode=WAL`) specifically because Vote inserts are
  exactly the near-simultaneous-write pattern that causes "database is
  locked" errors under the default rollback-journal mode. WAL buys real
  headroom but is not a substitute for Postgres at real scale — if a
  live vote count climbs into the hundreds of simultaneous submitters,
  move the DB, don't just tune SQLite harder.
- **Multiple associations running concurrently** (the explicit
  multi-tenant future this architecture was built for) multiplies
  overall write volume across every app, not just elections — a second
  trigger independent of the first.

**Why the move itself should be low-friction here, specifically:**
- `config/settings/` already isolates `DATABASES` per environment;
  swapping to Postgres in `production.py` is a few lines using
  `django-environ`'s `env.db()` against a `DATABASE_URL`, not a rewrite.
- Every model uses Django's database-agnostic field types and ORM
  constraints (`UniqueConstraint`, `Meta.indexes`) rather than any
  SQLite-specific SQL — the exact same migration files replay against
  Postgres unchanged.
- `BigAutoField` (Django's default since 3.2, explicit here too) behaves
  identically on both backends — no PK-type surprises.

**The one real behavioural difference to watch for:** SQLite does **not**
enforce `CharField(max_length=...)` at the database column level the way
Postgres (`varchar(n)`) does — Django enforces it at the
`full_clean()`/form layer on both backends, but a raw `bulk_create()` or
direct SQL that skips validation could silently insert an over-length
value on SQLite that Postgres would reject outright. As long as data
only ever goes through model `full_clean()`/`save()` — true everywhere
in this codebase today — this difference never bites.

**Data migration mechanics, when the day comes:** for a dataset this
shape (a handful of thousand rows, not millions),
`python manage.py dumpdata --natural-foreign --natural-primary >
data.json` against SQLite followed by `loaddata` against a freshly
migrated Postgres database is simpler and safer than a binary
SQLite→Postgres converter, and lets you eyeball the JSON before trusting
it.

---

## 10. Quickstart

```bash
python3.12 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env               # then fill in SECRET_KEY etc.

python manage.py makemigrations    # already generated; re-run only after model changes
python manage.py migrate
python manage.py setup_roles       # creates the 4 role groups + permissions
python manage.py createsuperuser

python manage.py runserver
# -> http://127.0.0.1:8000/admin/
```

First thing to do in the admin: create the `Association` row for MSA
(`short_name="MSA"`) — every Member/Election/Position you create after
that will hang off it.
