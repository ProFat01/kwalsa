# Member Registration Module

Built on top of the existing SAMS architecture, with **no changes to model
relationships**. The only model-layer changes were tightening two
validators and adding automatic receipt cleanup to an existing signal —
both behavioral refinements, not structural ones.

## What changed at the model layer, and why

| Change | File | Why |
|---|---|---|
| `phone_number_validator` now also checks the network prefix (070/071/080/081/090/091) | `members/validators.py` | New requirement; kept the *same* importable name so the existing migration's serialized validator reference still resolves — only the implementation changed |
| `nin_validator` rewritten with separate digit/length error messages | `members/validators.py` | "Show validation errors clearly" — one specific reason per failure instead of one generic regex message |
| `generate_application_number()` format changed from `APP-MSA-2026-00001` to `APP-2026-00001` | `members/utils.py` | Spec gives an explicit example in this exact format |
| `RegistrationApplication` review signal now calls `clear_receipt()` on **both** approval and rejection | `members/signals.py` | PART 6 requires automatic cleanup on either outcome, not just a manual admin action |
| `STORAGES["staticfiles"]` moved from manifest storage (base) to plain storage (base), with the manifest version moved into `production.py` only | `config/settings/base.py`, `production.py` | Pre-existing latent bug, surfaced now that templates actually use `{% static %}`: manifest storage requires `collectstatic` to have run first, which is true in production but never true in dev/tests |

**Flagging one real tradeoff from the application-number format change:**
`SequenceCounter` is still scoped *per association* internally
(unchanged), but the rendered string `APP-{year}-{n}` no longer encodes
which association issued it. With a single association (today's reality)
this is exactly equivalent to the old format. **The moment a second
association is onboarded**, both associations' counters restart
independently, so two associations could each mint `APP-2026-00001` in
the same year — and `application_number` is globally unique, so the
second save would fail outright. Flagged here rather than silently risked;
the fix when that day comes is straightforward (reintroduce the
association code, or move to one global counter).

## New files

```
apps/members/
├── forms.py                          # MemberRegistrationForm, StatusCheckForm
├── views.py                          # register_view, registration_success_view, status_check_view
├── urls.py                           # app_name="members"
├── templates/members/
│   ├── register.html
│   ├── registration_success.html
│   ├── status_check.html
│   └── status_result.html            # included partial, rendered once a search has run
└── tests/
    ├── helpers.py                    # make_image(), MediaIsolatedTestCase
    ├── test_validators.py
    ├── test_forms.py
    ├── test_views.py
    └── test_workflow.py

templates/base.html                   # shared layout (nav: Register / Check Status / Elections)
static/css/site.css                   # plain functional CSS, per the spec's explicit request
                                       # (renamed from members.css when the election module
                                       # started sharing it — see ELECTION_MODULE.md)
```

`config/urls.py` now mounts `apps.members.urls` at `/members/`.

## Routes

| URL | View | Purpose |
|---|---|---|
| `/members/register/` | `register_view` | PART 1–3, 7: registration form, duplicate detection, application creation |
| `/members/register/success/<application_number>/` | `registration_success_view` | PART 3: shows the generated application number |
| `/members/status/` | `status_check_view` | PART 4: public status lookup (GET shows the form; POST runs the search and includes `status_result.html`) |

All three are public — no login required, matching the brief (a
registrant has no account yet).

## Duplicate detection & recovery (PARTS 2 & 7)

`MemberRegistrationForm.clean()` checks for an existing `phone_number`
and/or `nin_number` **before** Django's own automatic uniqueness check
would fire (that automatic check is explicitly disabled via
`validate_unique()` → `pass`, since its generic per-field message doesn't
match the spec's exact wording). Three cases, exact strings:

- both exist → `"Membership Record Already Exists."`
- phone only → `"Phone Number Already Registered."`
- NIN only → `"NIN Number Already Registered."`

Whichever case fires, `form.duplicate_detected = True` is also set; the
view passes that to the template as `show_recovery_cta`, which renders
the separate PART 7 message (*"You already have a registration record.
Please use the Check Status page..."*) with a **Check Registration
Status** button — kept as two distinct, separately testable pieces of
text rather than one merged string, since the spec gives them as two
different things.

## Receipt cleanup (PART 6)

`RegistrationApplication.clear_receipt()` already existed (built in the
architecture phase) but was previously *not* wired to anything
automatic. It's now called from `members/signals.py` the moment a
`RegistrationApplication.status` transitions out of `Pending` — on
**either** `Approved` or `Rejected` — deleting the file from disk and
clearing the field. This is the same recursion-safe signal pattern
already in place for the Member sync (the nested `save()` inside
`clear_receipt()` doesn't re-trigger the member-sync logic, because the
status hasn't changed on that second save — verified by
`test_editing_a_reviewed_application_again_does_not_re_trigger_member_sync`).

In the admin, `RegistrationApplicationAdmin` now also shows a receipt
**image preview** while an application is still Pending (it has nothing
to preview once reviewed, by design — the file is already gone). The old
`clear_receipt_images` bulk action still exists but is now a manual
fallback, not the primary cleanup path.

## Status checker (PART 4)

One view, one URL, two input modes via `StatusCheckForm`:
- **Application Number** alone, or
- **NIN + Phone Number together** (both must match the *same* Member —
  neither field alone is treated as sufficient identification for
  someone else's record).

Looks up the most recent `RegistrationApplication` for that
member/number and renders exactly one of: Pending Review / Approved (+
Membership ID) / Rejected (+ reason) / "No registration record found."

## Running it

```bash
python manage.py migrate
python manage.py setup_roles

# Registration needs an Association to attach members to — create MSA once:
python manage.py shell -c "
from apps.core.models import Association
Association.objects.get_or_create(name='Malam Sidi Students Association', short_name='MSA', slug='msa')
"

python manage.py runserver
# -> http://127.0.0.1:8000/members/register/
# -> http://127.0.0.1:8000/members/status/
```

If that `Association` row doesn't exist yet, `/members/register/` shows
a "Registration is not currently available" message instead of a broken
page — checked explicitly in
`test_registration_unavailable_when_no_association_configured`.

## Tests (PART 10)

```bash
python manage.py test apps.members
```

35 tests, all passing against a real SQLite test database (Django's
default test runner — no extra dependency added):

| File | Covers |
|---|---|
| `test_validators.py` | valid/invalid phone (digits, length, prefix), valid/invalid NIN |
| `test_forms.py` | successful registration, duplicate phone / NIN / both, invalid phone/NIN through the form, `duplicate_detected` flag |
| `test_views.py` | register GET/POST, success page shows the real application number, duplicate → recovery CTA, registration-unavailable fallback, status checker — all four outcomes, both search modes, missing-field validation |
| `test_workflow.py` | approval → membership ID generated + `voting_status=True`; ID increments across members; rejection without reason blocked; rejection with reason → status synced; receipt deleted from disk after **both** approval and rejection; re-saving an already-reviewed application doesn't re-trigger the sync; DB-level uniqueness on phone/NIN; application numbers unique across re-application |

Each file that uploads a file extends `MediaIsolatedTestCase`, which
points `MEDIA_ROOT` at a fresh temp directory for the test class and
removes it afterward — test runs never touch (or leave files behind in)
the project's real `media/` folder.
