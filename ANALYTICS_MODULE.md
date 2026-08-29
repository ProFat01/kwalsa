# Analytics Module

Built entirely as a *consumer* of `Member`, `Election`, `Vote`, and the
existing snapshot models — **zero changes to `apps.members` or
`apps.elections`.** One model change in `apps.analytics` itself, which
this module owns and the task explicitly asked it to extend (PART 9:
"Use the existing snapshot architecture").

## The one model change, and why

| Change | File | Why |
|---|---|---|
| `AgeDistributionSnapshot.AgeBracket` boundaries replaced: `under_18 / 18_20 / 21_23 / 24_26 / 27_plus` → `below_16 / 16_20 / 21_25 / 26_30 / 31_40 / 41_plus` | `analytics/models.py` | The original boundaries were placeholders invented during the architecture phase, before any spec defined real ones — and were never populated or read anywhere (confirmed by grep before changing). This module is the *first* feature to actually use them, and it comes with its own explicit boundaries (PART 4). Changing an unused enum costs nothing; there's no historical snapshot data shaped around the old buckets to migrate. |

Added a `bucket_for_age(age)` static method right on the model — the
single source of truth for where one bracket ends and the next begins,
called by both the live `age_distribution()`/`age_participation()`
functions and the snapshot generator, so the two can never quietly
disagree about a boundary.

## Why this is a `services.py` + `querysets.py` module, not view logic

Every computation lives in `apps/analytics/services.py` (business
logic/formatting) and `apps/analytics/querysets.py` (raw DB access).
Views only resolve the URL's `Association`/`Election`, call one service
function, and either `render()` or `JsonResponse()` the result. This
matters concretely: the HTML dashboard and the JSON API for the same
data (e.g. course statistics) call the *exact same*
`services.course_distribution()` — they cannot drift apart, because
there's only one place the math happens.

`querysets.py` deliberately doesn't touch `apps.members`/`apps.elections`
models at all — no new manager methods were added to `Member` or
`Election`, even though that's a common Django pattern. Both of those
apps are "already completed and approved," and reading them from the
outside as a consumer (`Member.objects.filter(...)` directly) means this
entire module could be deleted without leaving a trace in either app.

## Live computation, not snapshot-dependent — same call as the election module

PARTS 1–8's numbers (membership, course, institution, age, growth,
election overview, position results, age participation) are all computed
**live**, every time, directly from `Member`/`Vote`. This is the same
reasoning already documented in `ELECTION_MODULE.md` for the public
results page: these are cheap `GROUP BY`/`COUNT` queries even at several
thousand members, and the dashboards need to be *accurate right now*,
not cached. The existing `MembershipSnapshot` / `AgeDistributionSnapshot`
/ `ElectionResultSnapshot` tables are populated *in addition*, on
request (PART 9), for historical trend tracking and as the explicit
"allow future optimization" path — not because any dashboard in this
module reads from them.

## Winner determination: built on top of `Election.results_by_position()`, not inside it

PART 7 asks for a winner per position. Rather than teach the elections
app's `Election` model what a "winner" is, `services.position_results_with_winner()`
calls the existing (untouched) `results_by_position()` and adds
winner/tie logic over the top:

- Clear winner: the candidate with the strictly highest vote count.
- **Tie**: if two or more candidates share the top vote count, `winner`
  is `None`, `is_tie` is `True`, and `tied_candidates` lists everyone
  tied for first — silently picking one of two tied candidates as "the"
  winner would misrepresent a real election outcome.
- Zero votes cast yet: `winner` is `None`, `is_tie` is `False` (there's
  no tie when nobody has voted — it's simply undecided).

## "Eligible" and the age brackets, precisely

Two different "eligible" populations show up in this module and they are
**not** the same number:
- `membership_overview()` / `course_distribution()` / `age_distribution()`
  count **every Member** of the association, regardless of
  `approval_status` — a pending applicant's course, institution, and age
  all still count towards "how many Chemistry students have applied",
  which is itself useful information, not just "how many approved
  members".
- `election_overview()` / `age_participation()` use
  `eligible_voters_count()` (i.e. `voting_status=True` only) — consistent
  with the election module's existing turnout calculation, since an
  unapproved applicant was never eligible to vote in the first place.

This distinction is deliberate and tested explicitly
(`test_age_distribution_includes_unapproved_members` vs.
`test_ineligible_members_excluded_from_participation`).

## Routes

**Dashboards** (PART 10), all under `/analytics/`, all permission-gated:

| URL | Page |
|---|---|
| `/analytics/` | Overview |
| `/analytics/membership/` | Membership Analytics (+ registration growth, `?granularity=day\|month\|year`) |
| `/analytics/courses/` | Course Analytics (`?order=asc\|desc`) |
| `/analytics/institutions/` | Institution Analytics (`?order=asc\|desc`) |
| `/analytics/age/` | Age Analytics |
| `/analytics/elections/` | Election Analytics (cross-election list) |
| `/analytics/elections/<id>/` | One election: position results + winners + age participation |

**JSON API** (PART 11) under `/analytics/api/` — same permission gate,
no charting JS wired up, just clean JSON:
`api/membership/`, `api/courses/`, `api/institutions/`,
`api/age-distribution/`, `api/elections/<id>/results/`,
`api/elections/<id>/turnout/`, plus a bonus `api/registration-growth/`
(not in PART 11's explicit list, but a direct, cheap fulfilment of PART
5's "helper methods for future chart integration").

## Permissions (PART 12)

Every view in `views.py` — dashboards and JSON alike — is wrapped in one
decorator, `analytics_staff_required`, which stacks `login_required`
(anonymous → redirect to admin login) with
`permission_required("analytics.view_analytics_dashboard", raise_exception=True)`
(logged in but lacking the permission → 403, not an endless login
redirect). That permission already existed and was already granted to
exactly **Analytics Admin** and **Super Admin** in
`apps/accounts/permissions.py` from the architecture phase — no new
permission or role was needed; this module just builds the first views
that actually check it. Verified for all four cases: anonymous (302),
plain staff (403), Analytics Admin (200), and Django superuser (200,
without being in any group at all).

## Snapshot generation (PART 9)

Three functions in `services.py` populate the existing snapshot tables,
all `update_or_create`-based so re-running for the same day/election
refreshes rather than duplicates:

- `generate_membership_snapshot(association, snapshot_date=None)`
- `generate_age_distribution_snapshot(association, snapshot_date=None)` — one row per bracket, always all 6
- `generate_election_result_snapshots(election)` — one row per contested position; deliberately leaves `is_published` untouched, since refreshing the numbers and *publishing* them are different, separately-audited actions (the election module's existing design)

Two ways to run them:
1. **Management command**, the primary path (works even when zero
   snapshot rows exist yet — no chicken-and-egg problem):
   ```bash
   python manage.py generate_snapshots                  # everything, all associations/elections
   python manage.py generate_snapshots --membership-only
   python manage.py generate_snapshots --elections-only
   python manage.py generate_snapshots --elections-only --election-id 3
   ```
2. **Admin actions** (`MembershipSnapshotAdmin.regenerate_for_today`,
   `ElectionResultSnapshotAdmin.refresh_vote_counts`) — a convenience for
   *refreshing* once at least one row already exists (admin bulk actions
   need a row to select; they can't bootstrap the very first snapshot
   from an empty changelist). Both actions declare `permissions=["view"]`
   explicitly — without that, Django's default action-permission check
   requires *change* permission, which would have hidden these actions
   from exactly the view-only Analytics Admins they're meant for. Caught
   by manually checking the rendered changelist HTML, not by the
   automated tests.

## Tests (PART 13)

```bash
python manage.py test apps.analytics
```

39 tests, all passing (119 project-wide). `MediaIsolatedTestCase` (from
the registration module) is reused for every test that needs a `Member`
fixture, same as the elections module's tests.

| File | Covers |
|---|---|
| `test_services.py` | membership counts/percentages incl. zero-member edge case; course/institution sort order both directions; every age-bracket boundary value explicitly; age distribution includes unapproved members (by design); registration growth label format + invalid-granularity error; election overview counts; position winner/tie/no-votes-yet cases; age participation eligible-vs-voted; all three snapshot generators incl. idempotent-per-day and is_published preservation |
| `test_views.py` | permission matrix (anonymous/plain-staff/Analytics-Admin/superuser) across every dashboard URL including the per-election detail page; dashboard content spot-checks; JSON endpoint shape and permission gating |
| `test_management_command.py` | default run, `--membership-only`, `--elections-only`, `--election-id` filtering |

## Running it

```bash
python manage.py migrate
python manage.py setup_roles   # Analytics Admin / Super Admin already include view_analytics_dashboard

python manage.py runserver
# -> http://127.0.0.1:8000/analytics/   (log in at /admin/login/ as an Analytics Admin or superuser first)

python manage.py generate_snapshots    # populate historical snapshot tables whenever you want them
```
