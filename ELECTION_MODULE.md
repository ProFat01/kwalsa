# Election Management Module

Built on the existing `Election` / `Position` / `Candidate` / `Vote` models
(from the architecture phase and the earlier multi-position refactor) and
the existing `Member` model. **No model relationships changed.** Three
small, additive model changes, one of which was an unavoidable rename —
flagged in detail below rather than buried in a diff.

## What changed at the model layer, and why

| Change | File | Why |
|---|---|---|
| `Election.is_active` (field) renamed to `Election.is_enabled` | `elections/models.py` | **Forced, not a design choice.** The spec requires a method called `is_active()` meaning "between start and end". Python cannot have a field and a method share one name on the same class — one had to move. The field's behavior is 100% unchanged (admin publish/disable switch); only its name changed. Migration generated as a genuine `RenameField` (confirmed interactively with `makemigrations`), not a drop+add, so no data is at risk. |
| Added `Election.description` (TextField, blank) | `elections/models.py` | New field the spec lists explicitly |
| Added `Position.description` (TextField, blank) | `elections/models.py` | Same |
| Added `Candidate` uniqueness constraint on `(election, position, name)` | `elections/models.py` | "Candidate cannot appear twice for same position in same election" — this blocks an accidental *duplicate entry* (the same name added twice for President), not multiple *different* candidates for one position, which is the entire point of an election. Verified both directions are correct (`test_duplicate_candidate_name_for_same_position_same_election_rejected` and `test_multiple_different_candidates_for_same_position_allowed`). |
| **No changes to `Member`** | — | See below |

**No new field was needed for PART 4's "Not suspended."** `Member.voting_status`
already exists specifically as the unified eligibility flag, and its own
comment in `members/models.py` already says it's flipped `False` "if a
member is later rejected/**suspended**" — written during the registration
module phase, before this module existed. PART 4's three conditions
("Approved", "Not suspended", "Eligible to vote") collapse cleanly onto
the two fields that already encode exactly this:
`approval_status == APPROVED` and `voting_status == True`. This is direct
continuity with already-approved architecture, not a new mechanism.

## Status: computed, never stored

`status` is a **property**, not a database column, even though the spec
lists "Status" among the Election fields. Storing it would mean either a
cron job or a signal keeping it in sync with the clock — exactly the kind
of staleness this project avoids elsewhere (see
`analytics.AgeDistributionSnapshot`'s reasoning for the identical call on
age). Computing `is_upcoming()` / `is_active()` / `is_closed()` /
`status` fresh on every access is what "status should update
automatically" means here: there's nothing to keep in sync because
nothing is cached. `is_voting_open` (pre-existing) now combines
`is_enabled` (the admin switch) with `is_active()` (the clock) — use
`is_voting_open` wherever voting eligibility is actually being decided;
`is_active()` alone only answers the narrower clock question.

## Live results — no dependency on `analytics.ElectionResultSnapshot`

The architecture already has `analytics.ElectionResultSnapshot`, built
for exactly this kind of data — but it's gated by an explicit
`is_published` flag an admin has to set, and PART 8 here asks for the
opposite: always-live numbers, "no manual refresh logic required,
simple implementation is acceptable." Rather than force a publish step
the spec doesn't ask for, `Election.results_by_position()`,
`voters_count()`, `eligible_voters_count()`, and `turnout_percentage()`
compute directly from `Vote`/`Member` on every call — no caching, no
snapshot row, always current. `ElectionResultSnapshot` remains available
untouched if a future phase needs a caching layer under heavy live-count
traffic; this module just doesn't reach for it where a direct query is
both simpler and what was actually asked for.

One terminology choice worth being explicit about: **"Total Votes Cast"**
counts *distinct members who voted* (ballots submitted), not individual
`Vote` rows — a member who votes for President and Secretary still
counts once. That's also the numerator for turnout. (Verified by
`test_voters_count_counts_distinct_members_not_vote_rows`.)

## New files

```
apps/elections/
├── forms.py            # VotingLoginForm, build_ballot_form_class(), CandidateChoiceField
├── views.py            # election_list/detail, voting_login, ballot, vote_success, results, admin_dashboard
├── urls.py              # app_name="elections"
├── templates/elections/
│   ├── election_list.html
│   ├── election_detail.html
│   ├── voting_login.html
│   ├── ballot.html
│   ├── vote_success.html
│   ├── results.html
│   └── admin_dashboard.html
└── tests/
    ├── test_models.py             # status rules, position/candidate validation
    ├── test_voting_access.py      # credential verification, eligibility, login view
    ├── test_ballot_and_voting.py  # ballot rendering, submission, duplicate prevention, manipulation
    └── test_results_and_dashboard.py
```

`config/urls.py` now also mounts `apps.elections.urls` at `/elections/`.
`static/css/site.css` (renamed from `members.css`) gained badge/table/
progress-bar utility classes shared by both modules.

## Routes

| URL | View | Auth |
|---|---|---|
| `/elections/` | `election_list_view` | public |
| `/elections/<id>/` | `election_detail_view` | public |
| `/elections/<id>/login/` | `voting_login_view` | public (verifies Member credentials) |
| `/elections/<id>/vote/` | `ballot_view` | requires the per-election voting session set by login |
| `/elections/<id>/vote/success/` | `vote_success_view` | public |
| `/elections/<id>/results/` | `results_view` | public |
| `/elections/<id>/dashboard/` | `admin_dashboard_view` | staff login + `elections.manage_election` permission (403 if logged in without it) |

## Voting identity: session-based, not Django auth

Members don't have `User` accounts (registration is admin-mediated, not
self-service — see `REGISTRATION_MODULE.md`), so "logging in to vote"
can't use Django's normal authentication. `voting_login_view` verifies
identity directly against `Member` fields (same pattern as the status
checker's NIN+phone lookup), then stores
`request.session[f"voting_member_{election.pk}"] = member.pk` — scoped
to *one specific election*, so logging in for Election A never grants
access to Election B's ballot. `request.session.cycle_key()` runs on
every successful login to mitigate session fixation. The marker is
cleared (`.pop()`, not `del`, to tolerate it already being gone) the
moment a ballot is successfully submitted.

## Security (PART 10), enforced at all three levels

| Threat | View level | Model level | Database level |
|---|---|---|---|
| Voting twice | `has_member_voted()` checked before showing the ballot, both at login and at the top of `ballot_view` | `Vote.clean()` re-checks eligibility/timing on every save | `UniqueConstraint(election, member, position)` |
| Page-refresh / double-submit duplicate votes | whole ballot submitted inside one `transaction.atomic()` block; `IntegrityError` caught and turned into a normal redirect, not a 500 | — | same constraint catches the race the view-level check alone can't (verified by `test_resubmitting_the_same_ballot_does_not_create_duplicate_votes`, which manually restores the session marker to simulate a genuinely concurrent second request) |
| Voting before/after the window | `election.is_voting_open` checked at login **and again at the top of `ballot_view`'s POST handler** (the election could close between GET and POST) | `Vote.clean()` checks `election.is_voting_open` independently | — (time-based; not a DB-enforceable constraint) |
| Unapproved/ineligible members | `VotingLoginForm.authenticate()` checks `approval_status`/`voting_status` before any session is granted | `Vote.clean()` checks `member.voting_status` again | — |
| Invalid credentials | one generic "couldn't verify" message for *any* mismatch (doesn't reveal which field was wrong) | — | `Member` lookup is a simple filter; no information leaked by timing differences worth engineering around at this scale |
| Manual form manipulation (tampered candidate id) | `ModelChoiceField`'s queryset is scoped to `Candidate.objects.filter(election=election, position=position)` — a tampered id outside that set fails as "not a valid choice" before any view logic runs | `Vote.clean()` independently checks `candidate.election_id == election.id` | `Candidate`/`Vote` FKs enforce referential integrity regardless |

Also verified: an atomic block containing two `Vote` inserts where the
second violates the constraint leaves **neither** committed
(`test_partial_ballot_failure_in_one_atomic_block_rolls_back_entirely`) —
the whole-ballot transaction is genuinely all-or-nothing, not
best-effort.

## Running it

```bash
python manage.py migrate
python manage.py setup_roles

python manage.py shell -c "
from apps.core.models import Association
Association.objects.get_or_create(name='Malam Sidi Students Association', short_name='MSA', slug='msa')
"

python manage.py runserver
# -> http://127.0.0.1:8000/elections/
```

Create an `Election`, its `Position`s, and `Candidate`s through the
Django admin (already fully built — `Election Admin` group already has
`manage_election`/`add_candidate`/etc.) — PARTS 1–3 are about model
support and admin updates, not a second parallel CRUD UI; the admin
already does this well and was approved in an earlier phase.

## Tests (PART 12)

```bash
python manage.py test apps.elections
```

45 tests, all passing (80 project-wide including the registration
module). `AdminDashboardTests` explicitly calls
`call_command("setup_roles")` in `setUpTestData` — the role groups are
created by that management command, not a migration, so a fresh test
database needs it run the same way a real deployment does after
`migrate`.

| File | Covers |
|---|---|
| `test_models.py` | upcoming/active/closed status + `is_voting_open` vs `is_enabled`; end-before-start rejected; position creation/ordering/uniqueness; candidate-must-be-on-the-ballot validation; duplicate-candidate-name constraint in both directions |
| `test_voting_access.py` | credential verification by both methods; wrong phone → generic message; unapproved/suspended → clear eligibility message; login blocked while upcoming/closed; already-voted → redirect straight to success |
| `test_ballot_and_voting.py` | ballot requires session; shows all positions/candidates; missing-position rejected; successful submission creates exactly one vote per position; completion message; already-voted member not shown a fresh ballot; manipulated candidate (wrong position / wrong election) rejected; voting blocked if the election closes mid-session; DB-level constraint bypass test; simulated double-submit race; atomic partial-failure rollback |
| `test_results_and_dashboard.py` | vote count + percentage per candidate; zero-vote and zero-eligible-voter edge cases (no division by zero); distinct-voter turnout counting; public results page renders correctly with no login; dashboard 302→login when anonymous, 403 when staff lack the permission, 200 with correct numbers for an Election Admin |
