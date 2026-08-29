# SAMS — Production Deployment (Part 2)

## SQLite limitations and when to move to PostgreSQL

SQLite works for SAMS's initial deployment. WAL mode is already enabled
specifically for concurrent-write safety during elections. Move to PostgreSQL
when **any** of these trigger conditions apply:

1. A single election expects more than ~50 simultaneous voters in any
   5-minute window.
2. A second association is onboarded (also: `application_number` format
   `APP-YYYY-NNNNN` currently omits the association code — two associations
   could independently mint `APP-2026-00001` in the same year, which would
   fail the global uniqueness constraint; fix this separately before
   multi-tenancy goes live regardless of which database backend is in use).
3. PythonAnywhere starts logging "database is locked" errors in
   `logs/sams.log`.

**The migration when that time comes:**

```bash
# 1. Set the new DSN — this is the ONLY required change
#    Add to PythonAnywhere env vars:
DATABASE_URL=postgres://user:password@host:5432/sams

# 2. Uncomment psycopg in requirements.txt and reinstall
pip install -r requirements.txt

# 3. Run the same migrations against the new DB
python manage.py migrate

# 4. Transfer existing data
python manage.py dumpdata --natural-foreign --natural-primary > /tmp/sams_data.json
# (then point DATABASE_URL at the new DB and:)
python manage.py loaddata /tmp/sams_data.json
```

No application code changes are required — `DATABASE_URL` is now actually
wired up in both settings files (it wasn't before the audit; this was the
"documented but silent" bug described in Part 1 item 6).

---

## Communication Center: synchronous bulk-send limit

`send_announcement()` (`apps/accounts/notifications.py`) sends the whole
recipient batch inline, in the same request that submitted the compose
form — one open SMTP connection reused for every message, but still one
HTTP request per announcement. Verified during the v2.0 load-testing
pass: Django/DB overhead alone is ~0.36ms per recipient, but that's with
the local in-memory email backend — real SMTP round-trips (even pooled
over one connection) are what actually dominate, typically far more
than that per message on a free/shared SMTP relay. At a few hundred
recipients this is unnoticeable; **at thousands of recipients with real
SMTP, expect the request to run long enough to hit a typical web-server
or reverse-proxy timeout before the loop finishes.**

Worth knowing if that happens: `announcement.sent_count`,
`.failed_count`, and `.status` are only written **after** the full loop
completes (`send_announcement`'s final `.save(...)`). If the request is
killed mid-send, none of that gets persisted — the Announcement row is
left showing its initial state even though some emails already went
out through the SMTP connection that was open at the time. There's
currently no way to recover how many actually sent in that case.

This is a known, accepted tradeoff, not a bug: background sending
(Celery/Redis) was explicitly out of scope for this project and isn't
something this validation pass adds — that would be a genuine
architecture change, not a fix. Two practical mitigations that don't
require a new dependency, if this is ever hit in practice:
- Send to smaller recipient groups (e.g. per-faculty rather than
  "All Members") when the association's total membership climbs into
  the thousands.
- Increase the web server / reverse-proxy request timeout for the
  `communication_compose_view` POST path specifically, if your
  PythonAnywhere plan allows it.



### Taking a backup

```bash
workon sams && cd ~/sams

# Full backup (DB + media)
python manage.py backup_db

# DB only (faster, use before/after deploys)
python manage.py backup_db --no-media

# Retain more than the default 7 backups
python manage.py backup_db --keep 30
```

Backups are written to `~/sams/backups/<YYYYMMDD_HHMMSS>/`:
- `db.sqlite3` — a consistent snapshot via SQLite's backup API
- `media.tar.gz` — all uploaded files (passport photos, receipts, candidate photos)

`backups/` is in `.gitignore` — it will not be accidentally committed.

### Scheduling automatic backups (PythonAnywhere Tasks tab, paid tier)

Create a daily scheduled task:
```
cd ~/sams && workon sams && python manage.py backup_db
```

Run it at low-traffic hours (e.g. 03:00 WAT). Also run it **manually
before and after every election event** and before every deployment.

### Restore procedure

```bash
# 1. Put the site into maintenance (Web tab → Reload with an intentionally
#    broken ALLOWED_HOSTS, or just accept brief downtime)

# 2. Restore the database
cp ~/sams/backups/<timestamp>/db.sqlite3 ~/sams/db.sqlite3

# 3. Restore media files
tar -xzf ~/sams/backups/<timestamp>/media.tar.gz -C ~/sams/

# 4. Verify
cd ~/sams
workon sams
python manage.py check
python -c "
import sqlite3
conn = sqlite3.connect('db.sqlite3')
cur = conn.cursor()
cur.execute('PRAGMA integrity_check')
print(cur.fetchone())   # should print ('ok',)
conn.close()
"

# 5. Reload the web app (Web tab → Reload)
```

**IMPORTANT: Test a restore before you need one.** Run the restore procedure
on a spare account or a local clone *now*, while it's not an emergency. A
backup that has never been test-restored is an optimistic claim, not a
recovery plan.

---

## Reverse proxy / HTTPS (why `SECURE_PROXY_SSL_HEADER` is not optional)

PythonAnywhere's architecture in one diagram:

```
Browser ──[HTTPS]──► PythonAnywhere reverse proxy ──[HTTP]──► Your Django process
                                                      │
                                          X-Forwarded-Proto: https
```

Django's `request.is_secure()` checks `wsgi.url_scheme` in the WSGI environ,
which is determined by the *actual transport* — plain HTTP in this case, even
for genuine HTTPS visitors.

Without `SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")`:

| Setting | Consequence |
|---|---|
| `SECURE_SSL_REDIRECT = True` | Infinite redirect loop — site completely inaccessible |
| `SESSION_COOKIE_SECURE = True` | Session cookies never set on "insecure" responses — no one can stay logged in |
| `CSRF_COOKIE_SECURE = True` | CSRF cookies never set — every POST returns 403 |

This is the most severe class of bug in the codebase and the easiest to miss,
because:
- `manage.py check --deploy` cannot know what proxy setup you're deploying behind
- It never manifests in any test run (no proxy in the test environment)
- The symptom (redirect loop) looks like a misconfigured URL or server error,
  not a missing single line in settings

This is now fixed and the fix has been verified (see Part 1 item 1).

---

## Deploying an update

```bash
cd ~/sams
workon sams
git pull origin main          # or upload the new zip

# Back up before touching anything
python manage.py backup_db --no-media

# Apply any new migrations
python manage.py migrate

# Re-run setup_roles if permissions.py changed
python manage.py setup_roles

# Rebuild the static manifest (always needed when static files change)
python manage.py collectstatic --noinput

# PythonAnywhere Web tab → Reload
```

---

## Quick-reference: everything that changed in this audit

| File | What changed |
|---|---|
| `config/settings/production.py` | `SECURE_PROXY_SSL_HEADER`, `CSRF_TRUSTED_ORIGINS`, `DATABASE_URL` wiring, fixed CSP (`font-src`, `fonts.googleapis.com`), production `LOGGING` with rotating file + `mail_admins` |
| `config/settings/development.py` | `DATABASE_URL` wiring (matches production) |
| `config/settings/base.py` | Base `LOGGING` config (console handler for all envs) |
| `requirements.txt` | Exact version pins instead of wildcards |
| `.env.example` | Complete rewrite — every variable actually referenced, with explanatory comments, `DATABASE_URL` correctly commented-out-by-default |
| `.gitignore` | Added `/logs/` and `/backups/` |
| `templates/base.html` | Inline `<script>` → `<script src="{% static 'js/site.js' %}">`, inline `style=""` → utility class |
| `static/js/site.js` | New file — nav toggle + vote-bar-width setter (CSP-safe) |
| `static/css/base.css` | New utility classes replacing the removed inline styles |
| `static/css/components.css` | `vote-bar-fill` width now set by JS instead of inline style |
| 12 other template files | `style="..."` → CSS utility classes, `data-percentage` on vote bars |
| `apps/core/management/commands/backup_db.py` | New — the entire backup mechanism |
| `apps/core/tests/test_backup_command.py` | 6 new tests for backup_db |
| `deploy/pythonanywhere_wsgi.py` | New WSGI configuration file |

## v2.0 Final Validation Phase — what changed

Load-tested at 500 / 1,000 / 5,000 / 10,000 members, plus a full
security/UI/documentation review. Full findings in the engineering
report delivered alongside this pass. Code/doc changes:

| File | What changed |
|---|---|
| `apps/members/models.py` | New `(association, registration_date)` index — backs the Registration Growth dashboard's GROUP BY, which was doing a full unindexed scan+sort at scale |
| `apps/members/migrations/0005_*.py` | Migration for the index above |
| `apps/members/services.py` | `member_filter_choices()` now cached 5 minutes per association — was 3 unindexed `DISTINCT` scans on every single staff member-list page view (~37ms of ~130ms at 10,000 members) |
| `apps/members/tests/test_staff_list.py` | 3 new tests locking in the cache's correctness and per-association isolation |
| `apps/accounts/notifications.py` | Fixed a dangling doc reference to a "Known limitation" write-up that didn't actually exist anywhere — now points at this file |
| `.env.example` | Removed a duplicated header line |
| `PRODUCTION_DEPLOYMENT.md` | Corrected stale "158 tests" to the current 328; documented that `SECRET_KEY` is now enforced in code, not just checklist-recommended |
| `PRODUCTION_DEPLOYMENT_2.md` | This section, plus the new Communication Center limitation section above |
