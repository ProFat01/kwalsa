# Role-Based Dashboards

## Review: what existed before this task

| Role | Status | Detail |
|---|---|---|
| Analytics Admin | Complete | `apps/analytics/views.py` — 7 HTML dashboards + 7 JSON endpoints, gated by `analytics_staff_required` (`analytics.view_analytics_dashboard`). Built in the analytics module. |
| Election Admin | Partial | One view, `elections.admin_dashboard_view` at `/elections/<id>/dashboard/`, gated by `elections.manage_election`. Per-election only — no overview listing all elections, so you needed to already know an election's ID to reach it. |
| Registration Admin | None | Only the Django admin changelists (`MemberAdmin`, `RegistrationApplicationAdmin`). No purpose-built summary view. |
| Super Admin | None | Only the generic Django admin index, plus whatever they inherited access to via permissions. No cross-cutting view. |

`base.html`'s "Dashboard" nav link pointed at `admin:index` for every
authenticated user regardless of role — there was no role-aware landing
experience at all.

## What was built

One dashboard hub at `/dashboard/` (`apps.accounts`, which previously had
no views at all — it only held models/admin/permissions) rather than
four separate pages. Each section renders purely based on
`request.user.has_perm(...)`:

```python
sections = {
    "registration": user.has_perm("members.review_application"),
    "elections": user.has_perm("elections.manage_election"),
    "analytics": user.has_perm("analytics.view_analytics_dashboard"),
    "contact": user.has_perm("core.view_contactmessage"),
}
```

**No new permissions were created** — all four already existed and were
already attached to the right groups by `setup_roles`, exactly as the
request asked ("using the existing permission architecture"). The
practical effect:

- Registration Admin → sees only the Registration section
- Election Admin → sees only the Elections section
- Analytics Admin → sees only the Analytics section
- Super Admin → sees **all four** (holds all four permissions)
- A plain Django superuser with no group membership also sees all four
  (`has_perm()` always returns `True` for `is_superuser=True`) — verified
  explicitly, since this is an easy case to get wrong
- Staff with no group at all see a plain "you don't have access to any
  dashboard section yet" message instead of a blank or broken page

Permission choice for each section was deliberately the *narrowest*
relevant one rather than the broadest. The Elections section is gated on
`manage_election`, not `view_election`/`view_vote` — Analytics Admin
holds the latter two but not the former, so they correctly don't get a
redundant elections-management card cluttering their screen (they
already have richer election analytics in their own dashboard's Election
Detail page). Same reasoning for `review_application` over the broader
`view_member` on the Registration section.

## Reuses everything, rebuilds nothing

- Registration numbers: `apps.analytics.services.membership_overview()`
  — the exact function the Analytics dashboards already call.
- Election numbers: `apps.analytics.services.all_elections_overview()`
  — same function, same data, same source of truth.
- "Manage" links point at the **existing** per-election dashboard
  (`elections:admin_dashboard`) and existing admin changelists
  (`admin:members_registrationapplication_changelist`,
  `admin:core_contactmessage_changelist`, etc.) — nothing new was added
  to `apps.elections`, `apps.members`, or `apps.core` to support this.
  The hub is a thin aggregation layer, not a fifth parallel
  implementation of any of these.
- The Analytics section itself doesn't try to replicate the analytics
  module's dashboards — it shows three headline numbers and a single
  "Open Analytics Dashboard" button to `analytics:overview`.

## One known limitation, stated rather than silently patched

`LOGIN_URL` is Django admin's own login page (`admin:login`), which has
its own post-login redirect logic — it is *not* Django's generic
`LoginView`, so setting `LOGIN_REDIRECT_URL` would have no effect here
and wasn't added (it would be a dead setting, which is more misleading
than not having it). When a protected page redirects an anonymous user
to login, it appends `?next=/dashboard/`, and admin's login view *does*
honor `next` — so the natural flow (visit `/dashboard/` while logged
out → log in → land back on `/dashboard/`) already works correctly,
confirmed in `test_anonymous_redirected_to_admin_login`. What doesn't
happen: someone who logs in by visiting `/admin/login/` directly (no
`next`) still lands on the generic admin index, same as it always has
for the Analytics/Election dashboards that predate this task. The nav
bar's "Dashboard" link (now pointing at the hub) is the fix for that case
— one click away regardless of how someone logged in.

## Tests

```bash
python manage.py test apps.accounts
```

12 tests (152 project-wide): permission matrix across all four roles
plus the superuser-without-group and no-group-at-all edge cases;
content checks confirming each visible section shows real data with
correctly resolving links into the existing admin/dashboard views;
graceful behavior with no `Association` configured; confirmation that
the nav link actually points at the new hub.

Same lesson recurred from the public-website module's test suite:
literal template text isn't run through Django's auto-escaping (only
`{{ variable }}` output is), so an apostrophe in hand-written template
copy renders as a real `'`, not `&#x27;` — caught once, fixed once, worth
remembering for the next template-text assertion.
