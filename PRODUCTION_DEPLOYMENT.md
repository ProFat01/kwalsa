# SAMS — Production Deployment Guide (PythonAnywhere)

## Audit findings: what was wrong and what was fixed

### Critical blockers (would have taken the site down immediately)

**1. Infinite redirect loop under PythonAnywhere's HTTPS proxy [FIXED]**

PythonAnywhere terminates HTTPS at its own reverse proxy and forwards plain
HTTP to your WSGI process, adding `X-Forwarded-Proto: https`. Without
`SECURE_PROXY_SSL_HEADER`, `request.is_secure()` always returns `False` even
for genuine HTTPS visitors. Combined with `SECURE_SSL_REDIRECT = True` already
in the settings, this causes Django to redirect every request to its HTTPS
version — including ones that are already HTTPS — creating an infinite `301`
loop that takes the entire site down on first deploy.

Fixed by adding to `production.py`:
```python
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
```

Verified end-to-end: a request carrying `X-Forwarded-Proto: https` now returns
`200`. A genuine HTTP request returns exactly one `301` to `https://`. Neither
result was achievable before the fix.

**2. All POST requests fail CSRF validation [FIXED]**

Django 4+ validates the `Origin` header on POST/PUT/... requests against
`CSRF_TRUSTED_ORIGINS`. Behind PythonAnywhere's TLS-terminating proxy, every
POST has `Origin: https://yoursite.pythonanywhere.com` — not in the trusted-
origins list before the fix. Every form submission (registration, voting, the
contact form, admin logins) would have returned a silent `403`.

Fixed by adding `CSRF_TRUSTED_ORIGINS = env.list("CSRF_TRUSTED_ORIGINS", ...)`
to `production.py`. **Must include the `https://` scheme.**

Verified by running a contact-form POST with `enforce_csrf_checks=True` under
simulated proxy conditions: `302` (success) with the fix, `403` (blocked)
without it.

**3. CSP blocks every page's fonts and the mobile nav [FIXED]**

`production.py` had `style-src 'self'` with no Google Fonts allowance, and
`script-src 'self'` with an inline `<script>` block in `base.html`. Result:
fonts silently discarded on every page, mobile nav silently broken.

Fixed in two parts:
- Inline `<script>` moved to `static/js/site.js` (external same-origin
  scripts pass `script-src 'self'`; inline blocks do not).
- All 13 template files with `style=""` attributes had those replaced with
  utility CSS classes. Vote-bar widths (the only dynamic inline style) now
  use `data-percentage="..."` set to `el.style.width` by `site.js` —
  individual CSSOM property assignment is NOT blocked by CSP; only
  `setAttribute("style", ...)` and HTML `style=""` attributes are.
- `fonts.googleapis.com` added to `style-src`, `fonts.gstatic.com` added
  to a new `font-src` directive.

Verified: `inline style attrs: 0`, `inline <script> blocks: 0` in the
rendered production HTML. CSP header confirmed correct by actually rendering
the homepage under `DJANGO_SETTINGS_MODULE=config.settings.production`.

### Significant issues (operational risk / data loss)

**4. Zero backup mechanism [FIXED]**

No backup command, no documentation, nothing in `.gitignore` for backup dirs.

Added `python manage.py backup_db` (`apps/core/management/commands/backup_db.py`):
- Uses `sqlite3.Connection.backup()` — NOT a raw `shutil.copy()`. WAL mode
  (already enabled in the settings) makes a raw file copy dangerous: you can
  capture the file mid-write and produce a corrupt snapshot. The backup API
  takes SQLite's own read lock and produces a transactionally consistent copy
  even while the site is actively serving requests. Proved by running the
  command while a background thread was continuously writing — `PRAGMA
  integrity_check` returned `ok` on the result.
- Packages `media/` as `media.tar.gz` alongside the DB.
- Rotates old backups (default: keep 7, `--keep N` to change).

**5. No logging configuration [FIXED]**

Zero `LOGGING` config existed. Added to `base.py` (console) and extended in
`production.py` with:
- A `RotatingFileHandler` writing to `logs/sams.log` (5 MB / 5 backups).
  Directory auto-created at settings-import time.
- An explicit `mail_admins` handler wired to `django.request` for unhandled
  exceptions.

Verified: `logs/sams.log` is created and written to on first startup.

**6. `DATABASE_URL` documented but silently ignored [FIXED]**

`.env.example` claimed `DATABASE_URL` could be set to a Postgres DSN "without
touching any other code." Both settings files hardcoded their `DATABASES` dict
directly and never read it. The Postgres migration path was aspirational.

Fixed: both `development.py` and `production.py` now use
`env.db("DATABASE_URL", default=...)`. Setting `DATABASE_URL=postgres://...`
is now the entire PostgreSQL migration — no code change required. SQLite WAL
options are merged in automatically only when the engine is still sqlite3.

**WARNING**: `DATABASE_URL=` (blank, present in `.env`) is parsed as an
invalid URL. Leave it **commented out** to use the default SQLite path.
This is documented in the rewritten `.env.example`.

**7. Wildcard version pins [FIXED]**

`Django==6.0.*`, `Pillow==11.*` — non-reproducible across time. Pinned to
exact versions (`Django==6.0.6`, `Pillow==11.3.0`, etc.) verified together
in a clean venv.

---

## Pre-deploy checklist

Items marked **[BLOCKER]** will cause an immediate outage or data loss.

### Code
- [ ] **[BLOCKER]** `python manage.py test` passes all 328 tests
- [ ] **[BLOCKER]** `python manage.py check --deploy` (with real `SECRET_KEY`) returns 0 issues
- [ ] `python manage.py makemigrations --check --dry-run` shows "No changes detected"

### Secrets and env vars
- [ ] **[BLOCKER]** `SECRET_KEY` ≥ 50 chars from `python -c "import secrets; print(secrets.token_urlsafe(50))"` —
  `config/settings/production.py` requires this env var outright (`env("SECRET_KEY")`,
  no fallback) since the v2.0 production audit, so a genuinely missing
  `SECRET_KEY` now fails startup with `ImproperlyConfigured` instead of silently
  running on `base.py`'s dev-only insecure default. This checklist item still
  matters — a *present but weak* key isn't caught by that guard.
- [ ] **[BLOCKER]** `ALLOWED_HOSTS=yourusername.pythonanywhere.com`
- [ ] **[BLOCKER]** `CSRF_TRUSTED_ORIGINS=https://yourusername.pythonanywhere.com` (with `https://`)
- [ ] `DJANGO_ADMINS=Name:email@example.com` (at least one, or server errors are silent)
- [ ] `DJANGO_DB_PATH=/home/yourusername/sams/db.sqlite3`
- [ ] Email variables set (needed for ADMINS error notification)

### Database
- [ ] `python manage.py migrate` runs cleanly
- [ ] `python manage.py setup_roles` runs cleanly
- [ ] MSA `Association` row exists (see Step 1 below)
- [ ] Superuser created: `python manage.py createsuperuser`

### Static files
- [ ] `python manage.py collectstatic --noinput` succeeds (133 files + 399 post-processed)
- [ ] PythonAnywhere static files: `/static/` → `/home/yourusername/sams/staticfiles/`
- [ ] PythonAnywhere static files: `/media/` → `/home/yourusername/sams/media/` (**WhiteNoise does not serve user uploads**)

### WSGI
- [ ] WSGI file points at `deploy/pythonanywhere_wsgi.py`
- [ ] `PYTHONANYWHERE_USERNAME` in that file replaced with your actual username

### Backup
- [ ] `python manage.py backup_db` runs cleanly
- [ ] **[BLOCKER for data safety]** Scheduled task configured to run `backup_db` daily
- [ ] Test restore completed at least once before going live

### Post-deploy smoke tests
- [ ] `https://yoursite/` loads (not a redirect loop, not a 500)
- [ ] `https://yoursite/admin/` loads the login page
- [ ] A test registration form submission succeeds
- [ ] Status checker retrieves that application
- [ ] `logs/sams.log` exists and has content after the above traffic

---

## Step-by-step deployment

### Step 1: PythonAnywhere console

```bash
cd ~
git clone https://github.com/yourrepo/sams.git   # or upload + unzip

mkvirtualenv sams --python=python3.12
workon sams
pip install -r ~/sams/requirements.txt

cd ~/sams

# Set env vars for this console session
export DJANGO_SETTINGS_MODULE=config.settings.production
export SECRET_KEY="$(python -c 'import secrets; print(secrets.token_urlsafe(50))')"
export ALLOWED_HOSTS="yourusername.pythonanywhere.com"
export CSRF_TRUSTED_ORIGINS="https://yourusername.pythonanywhere.com"
export DJANGO_DB_PATH="/home/yourusername/sams/db.sqlite3"

python manage.py collectstatic --noinput
python manage.py migrate
python manage.py setup_roles
python manage.py createsuperuser
python manage.py shell -c "
from apps.core.models import Association
Association.objects.get_or_create(
    name='Malam Sidi Students Association', short_name='MSA', slug='msa'
)
"
python manage.py check --deploy
```

### Step 2: PythonAnywhere Web tab

| Setting | Value |
|---|---|
| Python version | 3.12 |
| Virtualenv | `/home/yourusername/.virtualenvs/sams` |
| WSGI configuration file | `/home/yourusername/sams/deploy/pythonanywhere_wsgi.py` |

**Environment variables** (add in the Web tab's env var section):

| Variable | Value |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` |
| `SECRET_KEY` | _(50+ random chars — generate fresh, don't reuse)_ |
| `ALLOWED_HOSTS` | `yourusername.pythonanywhere.com` |
| `CSRF_TRUSTED_ORIGINS` | `https://yourusername.pythonanywhere.com` |
| `DJANGO_DB_PATH` | `/home/yourusername/sams/db.sqlite3` |
| `DJANGO_ADMINS` | `Your Name:your@email.com` |
| `EMAIL_HOST` | _(SMTP server)_ |
| `EMAIL_PORT` | `587` |
| `EMAIL_USE_TLS` | `True` |
| `EMAIL_HOST_USER` | _(SMTP username)_ |
| `EMAIL_HOST_PASSWORD` | _(SMTP password)_ |

**Static files mappings**:

| URL | Directory |
|---|---|
| `/static/` | `/home/yourusername/sams/staticfiles/` |
| `/media/` | `/home/yourusername/sams/media/` |

Click **Reload**.

Continue reading `PRODUCTION_DEPLOYMENT_2.md` for SQLite limits,
backup/restore procedure, and the reverse-proxy explanation.
