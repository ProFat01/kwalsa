# Visitor & Usage Analytics (v2.1)

Additive-only feature on top of the stable v2.0 baseline: no existing
model, view, URL, migration, or test was modified — see "Files changed"
at the end of this document for the complete, short list of touch
points, all of which are new files or small, isolated additions to
files that already belonged to `apps.analytics`/`apps.accounts`.

## What it records

One `PageVisit` row per meaningful public page view:

- `association`, `visit_date`, `visited_at`
- `page_key` — Django's own resolved URL name (`"core:home"`,
  `"elections:election_detail"`), not the raw path. This is what makes
  "Most Visited Pages" group `/elections/3/` and `/elections/7/` under
  one "Elections" row instead of fragmenting by primary key.
- `path` — the raw request path, kept for reference/troubleshooting only.
- `visitor_hash` — a one-way HMAC-SHA256, never the raw IP (see
  "Privacy model" below).
- `visitor_type` — `anonymous` or `member` (a logged-in member portal
  session). Staff/admin activity is not tracked at all (see below).
- `device_category` — `mobile` / `desktop` / `tablet` / `unknown`,
  from a deliberately coarse User-Agent check.
- `browser_category` — `chrome` / `firefox` / `edge` / `safari` / `other`.
- `referrer_category` — `direct` / `search` / `social` / `other_website`
  / `unknown`, from the `Referer` header's domain only.

## What it deliberately does NOT record

No raw IP addresses, no full User-Agent strings, no cookies, no NIN,
phone numbers, email addresses, passwords, auth tokens, request
headers, POST bodies, or form submissions. `PageVisit` has no field
that could hold any of these — see
`PrivacyTests.test_raw_ip_never_stored_on_model` in
`apps/analytics/tests/test_visitor_analytics.py`, which asserts this
structurally rather than just by convention.

## What is tracked vs. excluded

Tracked: a `GET` request that resolves to a real, named public view,
answers `200` with an HTML response, and isn't made by an authenticated
staff account.

Excluded, by design:

- `/admin/`, `/dashboard/`, `/analytics/` — staff tooling and the
  analytics dashboards themselves (so the feature never inflates its
  own numbers).
- `/static/`, `/media/`, `/favicon.ico`, `/robots.txt`.
- Anything not a `GET` (form POSTs, votes, logins).
- Any response that isn't `200` (redirects, 404s, 500s) or isn't
  `text/html` (JSON/API responses, file downloads).
- Any request from an authenticated `is_staff` account, even on an
  otherwise-public page — "Staff/admin activity is excluded from
  public visitor statistics by default" (PART 5).

A logged-in member (SAMS's separate portal-session concept, not a
Django staff account) is tracked and labeled `visitor_type="member"`,
distinct from anonymous public traffic.

## Privacy model

`visitor_hash = HMAC-SHA256(secret, f"{ip}|{user_agent}|{association}|{day}")`

The secret is `settings.VISITOR_HASH_SALT` if set, else
`settings.SECRET_KEY` — either way it never leaves the server, and the
hash is one-way (the raw IP cannot be recovered from it).

The calendar day is folded *into* the hashed message rather than stored
as a separate column, so **the same visitor gets a different hash every
day**. This is the same "rotate the salt daily" design used by
privacy-first analytics tools generally: a stored hash from one day can
never be used to link that visitor's activity to a different day, even
by someone with full database access and the secret.

**Consequence, stated plainly:** daily unique-visitor counts are
accurate (`COUNT(DISTINCT visitor_hash)` within one day). Weekly/monthly
"unique visitors" are really *unique visitor-days* summed across the
range — a visitor who returns on three different days within a 7-day
window counts as three unique visitors, not one. This is disclosed
directly on the dashboard, immediately under the summary cards:

> Unique visitors are an approximate, privacy-preserving metric based on
> a one-way hash that rotates daily — they may differ from analytics
> platforms that use persistent cookies or cross-device tracking, and
> figures spanning more than one day count a returning visitor once per
> day rather than once overall.

No fingerprinting: device/browser/referrer are broad categories derived
from a handful of substring checks, not a combined fingerprint of
screen size, fonts, plugins, timezone, etc.

## Retention

`settings.VISITOR_ANALYTICS_RETENTION_DAYS` (default: 90, overridable
via the `VISITOR_ANALYTICS_RETENTION_DAYS` env var).

No automatic scheduled job is wired up — this project has no
background worker running by default (deliberately, for PythonAnywhere
Free-tier compatibility), so an unattended cron-like mechanism would be
new infrastructure the spec explicitly disallows introducing. Instead:

```
python manage.py cleanup_visitor_analytics                # uses the configured retention
python manage.py cleanup_visitor_analytics --days 30       # override for this run
python manage.py cleanup_visitor_analytics --dry-run       # report only, deletes nothing
```

Run this from a PythonAnywhere **scheduled task** (available on the
Free tier, once a day is enough) — see PRODUCTION_DEPLOYMENT.md for how
scheduled tasks are already configured for this project's backups.

## Database design

Single table, `apps.analytics.models.PageVisit` — integrated into the
existing `apps.analytics` app rather than a new app, since that app
already owns "staff-only dashboards + aggregation over other apps'
data" and visitor analytics is the same shape of problem. No second
"rollup" table: every dashboard number (today/week/month totals, daily
trend, top pages, device/browser/referrer breakdowns) is a live,
indexed `GROUP BY`/`COUNT` over `PageVisit` for an explicit date range —
simpler than maintaining a second denormalized table in sync, and cheap
enough at retention-bounded volumes (see "Performance" below).

Indexes (each justified against an actual query — see
`apps/analytics/querysets.py:page_visits_for_range`, the base queryset
every aggregation in `services.py` builds on):

| Index | Supports |
|---|---|
| `visit_date` | Retention cleanup (`cleanup_visitor_analytics`), the only query with no association filter. |
| `association, visit_date` | The base filter every dashboard query shares — overview totals, traffic trend. |
| `association, visit_date, page_key` | "Most Visited Pages" — confirmed as a **covering index scan** (no table row lookups at all) via `EXPLAIN QUERY PLAN` at 10,000 rows. |
| `association, visit_date, device_category` | Device breakdown. |
| `association, visit_date, browser_category` | Browser breakdown. |
| `association, visit_date, referrer_category` | Referrer breakdown. |

The composite indexes lead with `association` (not `visit_date` alone)
because that's how every real query filters — an earlier draft that led
with `visit_date` alone was verified with `EXPLAIN QUERY PLAN` to be
*ignored* by SQLite's planner in favor of the FK's own auto-created
`association_id` index, silently turning every aggregation into an
association-wide scan. Caught and fixed before shipping; see
"Performance" for the before/after numbers.

## Performance

Tracking cost: exactly one `INSERT` for a tracked request, zero writes
for everything else (redirects, static assets, staff traffic, etc.) —
confirmed by `PerformanceTests.test_tracking_a_single_request_is_a_single_insert`.

Dashboard cost, measured with a synthetic dataset (random pages/devices/
browsers/referrers spread across a 90-day window):

| Rows | Full dashboard (6 aggregation queries) |
|---|---|
| 500 | ~9.8 ms |
| 1,000 | ~10.4 ms |
| 5,000 | ~22.7 ms |
| 10,000 | ~38.5 ms |

`EXPLAIN QUERY PLAN` at 10,000 rows confirms indexed access, not a
table scan, for both query shapes:

```
-- traffic trend
SEARCH analytics_pagevisit USING INDEX pv_assoc_date_referrer_idx
  (association_id=? AND visit_date>? AND visit_date<?)
USE TEMP B-TREE FOR count(DISTINCT)

-- top pages
SEARCH analytics_pagevisit USING COVERING INDEX pv_assoc_date_page_idx
  (association_id=? AND visit_date>? AND visit_date<?)
USE TEMP B-TREE FOR GROUP BY
USE TEMP B-TREE FOR ORDER BY
```

(SQLite still needs a temp B-tree for `GROUP BY`/`ORDER BY`/`DISTINCT`
aggregation itself — that's expected and cheap at this row count; the
important thing the index avoids is a full table scan to *find* the
matching rows in the first place.)

`PerformanceTests.test_dashboard_query_count_does_not_scale_with_row_count`
asserts the query *count* (not just timing) stays identical between 50
and 550 rows — the concrete guard against a future change accidentally
introducing an N+1.

## PythonAnywhere Free-tier considerations

- No new infrastructure: no Redis, Celery, cron daemon, or external
  analytics service. Retention cleanup is a manual/scheduled-task
  management command, matching the existing backup command's pattern.
- SQLite-compatible throughout — every query above is a plain indexed
  `GROUP BY`/`COUNT`, nothing Postgres-specific.
- One `INSERT` per tracked page view is the entire steady-state write
  cost; static assets never reach the tracking code at all in
  production (WhiteNoise serves and returns before the middleware
  chain gets there).

## Permissions

New permission: `analytics.view_visitor_analytics`, declared on
`PageVisit` (`Meta.permissions`) and granted, via `setup_roles`, to
**Super Admin** and **Analytics Admin** only — the same two roles that
already receive `view_analytics_dashboard`. Registration Admin and
Election Admin do not receive it. Gated the same way every other
analytics dashboard is: `login_required` +
`permission_required("analytics.view_visitor_analytics",
raise_exception=True)` (anonymous → redirect to admin login; logged-in
without the permission → `403`).

## Navigation

A "Visitors" link is added to the analytics sub-nav
(`apps/analytics/templates/analytics/_nav.html`) and a "Visitor
Analytics" button on the accounts dashboard hub's existing Analytics
section — both wrapped in `{% if perms.analytics.view_visitor_analytics %}`,
so they're invisible to anyone without the permission.

## Failure mode

The tracking middleware wraps its own logic in a `try/except` that
swallows any exception — a bug in analytics tracking must never turn
into a `500` on a real page. The trade-off (silently losing one data
point rather than surfacing the error) is deliberate: nothing about
visitor counts is safety- or correctness-critical enough to justify
risking the pages people actually came to use.

## Known limitations

- Weekly/monthly "unique visitors" are unique visitor-*days*, not
  unique humans — see "Privacy model" above.
- Device/browser detection is coarse substring matching on the
  User-Agent header, not a maintained parsing library — it will
  misclassify unusual or spoofed User-Agents, and browsers not
  explicitly listed fall into "Other".
- Referrer categorization only inspects the `Referer` header's domain
  against a short hardcoded list of major search engines and social
  platforms; anything else external is bucketed as "Other Website".
- `visitor_hash` is IP+User-Agent-based; a visitor whose IP changes
  mid-session (e.g. switching from WiFi to mobile data) is counted as
  two visitors, and multiple people behind the same NAT/IP with similar
  browsers can collapse into one.

## Deployment commands

```
python manage.py migrate                     # creates analytics_pagevisit + its indexes
python manage.py collectstatic --noinput      # no new static assets shipped by this feature
python manage.py setup_roles                  # re-run to grant view_visitor_analytics to existing groups
python manage.py cleanup_visitor_analytics    # run once, then schedule via PythonAnywhere's Tasks tab
```

## Files changed / added

**Added:**
- `apps/analytics/tracking.py` — hashing/categorization/exclusion helpers (pure, unit-tested directly)
- `apps/analytics/middleware.py` — `VisitorTrackingMiddleware`
- `apps/analytics/migrations/0004_pagevisit.py`
- `apps/analytics/templates/analytics/visitor_analytics_dashboard.html`
- `apps/analytics/management/commands/cleanup_visitor_analytics.py`
- `apps/analytics/tests/test_visitor_analytics.py` (54 tests)
- `VISITOR_ANALYTICS.md` (this file)

**Changed (small, additive):**
- `apps/analytics/models.py` — new `PageVisit` model
- `apps/analytics/services.py` — new visitor-analytics functions, appended at the end of the existing file
- `apps/analytics/querysets.py` — new `page_visits_for_range` helper
- `apps/analytics/views.py` — new `visitor_analytics_required` decorator + two new views
- `apps/analytics/urls.py` — two new URL patterns
- `apps/analytics/admin.py` — new read-only `PageVisitAdmin`
- `apps/analytics/templates/analytics/_nav.html` — one new permission-gated link
- `apps/accounts/permissions.py` — `analytics.view_visitor_analytics` added to Super Admin + Analytics Admin
- `apps/accounts/templates/accounts/dashboard.html` — one new permission-gated button
- `config/settings/base.py` — `VisitorTrackingMiddleware` added to `MIDDLEWARE`; `VISITOR_ANALYTICS_RETENTION_DAYS` and `VISITOR_HASH_SALT` settings added

**Not touched:** `production.py`, `development.py`, WSGI, elections
(voting/eligibility/results), member registration/approval/ID/card/QR,
Communication Center, email delivery, or any existing test file.

## Exact version recommendation

Ship as **SAMS v2.1** — a single additive migration
(`analytics.0004_pagevisit`), no changes to any v2.0 migration, model,
or URL. Safe to deploy without downtime: `migrate` then reload the WSGI
app; existing traffic is unaffected until the middleware starts writing
its first row.
