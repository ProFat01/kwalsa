from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = False

# base.py's SECRET_KEY falls back to a fixed, publicly-known
# "django-insecure-..." string when the environment variable isn't set —
# a sane default for a throwaway local dev run, but a real security hole
# in production: `manage.py check --deploy` does not flag it, so a
# deploy with a forgotten SECRET_KEY env var would silently start up and
# serve real traffic while signing sessions/CSRF tokens/password-reset
# tokens with a secret anyone can read in this file's history. Require
# it explicitly here instead — a missing SECRET_KEY must fail loudly at
# startup, not fall back to something insecure. Found during this
# project's own production audit.
SECRET_KEY = env("SECRET_KEY")

ALLOWED_HOSTS = [
    "kwalsa.pythonanywhere.com",
    "127.0.0.1",
    "localhost",
]  # e.g. yourusername.pythonanywhere.com

# CRITICAL for PythonAnywhere (and any reverse-proxy deployment): PA
# terminates HTTPS at its own proxy and forwards plain HTTP to this WSGI
# process, setting X-Forwarded-Proto: https on the forwarded request.
# Without telling Django to trust that header, request.is_secure()
# always returns False even for a genuinely HTTPS visitor — which,
# combined with SECURE_SSL_REDIRECT=True below, produces an *infinite
# redirect loop* (Django thinks every request is HTTP, including the
# ones it just redirected to HTTPS, and redirects again, forever). This
# is the single most common way a correctly-coded Django app fails to
# load at all on PythonAnywhere. See PRODUCTION_DEPLOYMENT.md "Reverse
# proxy / HTTPS" for how this was verified.
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")

# Django 4+ validates the Origin header on unsafe (POST/PUT/...)
# requests against CSRF_TRUSTED_ORIGINS for any request Django doesn't
# consider same-origin by scheme+host — exactly the situation behind a
# proxy that terminates TLS, so this must be set explicitly (must
# include the scheme) or every POST (registration, voting, the contact
# form, admin logins) fails CSRF validation in production.
CSRF_TRUSTED_ORIGINS = [
    "https://kwalsa.pythonanywhere.com",
]  # e.g. https://yourusername.pythonanywhere.com

# Parsed from DATABASE_URL, same as development.py — see that file's
# comment for why. Defaults to a SQLite file path that can also be set
# directly via DJANGO_DB_PATH (kept as its own variable since on
# PythonAnywhere it's often more convenient to point at a specific
# absolute path than to construct a full sqlite:/// URL by hand). If
# DATABASE_URL is explicitly set to a postgres:// URL, it takes
# precedence and DJANGO_DB_PATH is simply unused.
#
# This is still SQLite v1 for the first deployment — PythonAnywhere's
# free/low tiers don't give you a separate Postgres instance, and SQLite
# is fine for MSA's expected traffic outside of live election windows.
# See ARCHITECTURE.md "Future PostgreSQL migration" for the upgrade path
# and the concrete trigger conditions (concurrent voters, multi-
# association load) that should prompt the switch — at which point
# setting DATABASE_URL=postgres://... in the PythonAnywhere environment
# is the entire migration, no code change required.
_default_db_path = env("DJANGO_DB_PATH", default=str(BASE_DIR / "db.sqlite3"))
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{_default_db_path}")}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["OPTIONS"] = {
        "timeout": 20,
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;",
    }

# Manifest storage (cache-busted filenames, gzip/brotli precompression) is
# only safe once `collectstatic` is guaranteed to have run first — that's
# true for a real deploy (it's a required step below) but never true in
# dev/tests, hence the override living here rather than in base.py.
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# --- Security hardening for the public deployment ---
SECURE_SSL_REDIRECT = env.bool("SECURE_SSL_REDIRECT", default=True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Django 6.0's built-in CSP support (middleware already enabled in base.py).
#
# Every inline style="" attribute and inline <script> block in the
# templates was deliberately eliminated (moved to static/css utility
# classes and static/js/site.js) specifically so style-src/script-src
# can stay 'self'-only here — no 'unsafe-inline', no nonces. The two
# real external resources the site actually loads are Google Fonts'
# stylesheet (style-src) and font files (font-src) — both listed
# explicitly below. Audited against the rendered HTML before being
# finalized; see PRODUCTION_DEPLOYMENT.md "CSP audit" for how this was
# verified and why the previous (narrower) policy would have silently
# broken fonts, the mobile nav, and every progress-bar width in
# production despite passing `manage.py check --deploy` clean.
from django.utils.csp import CSP  # noqa: E402

SECURE_CSP = {
    "default-src": [CSP.SELF],
    "img-src": [CSP.SELF, "data:"],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF, "https://fonts.googleapis.com"],
    "font-src": [CSP.SELF, "https://fonts.gstatic.com"],
}

# Member-facing email (approval emails, Communication Center announcements)
# no longer uses this Django EMAIL_BACKEND at all — as of the Mailjet
# migration, apps.core.mailjet_service calls the Mailjet HTTPS Send API
# directly (see that module's docstring). DEFAULT_FROM_EMAIL and
# DEFAULT_FROM_NAME, used by mailjet_service, are defined once in base.py
# and read the same MAILJET_API_KEY / MAILJET_SECRET_KEY / DEFAULT_FROM_*
# env vars in every environment.
#
# The SMTP settings below are kept only for Django's own built-in
# mail_admins() error notifications (see LOGGING's "mail_admins" handler
# further down this file) — unrelated to member email and out of scope
# for this migration. Note that these were never confirmed to work on
# PythonAnywhere Free either, for the exact same outbound-SMTP restriction
# that motivated the Mailjet migration in the first place; if admin error
# emails matter in production, the cleanest fix would be pointing
# mail_admins at Mailjet too in a future change, not part of this one.
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = env("EMAIL_HOST", default="")
EMAIL_PORT = env.int("EMAIL_PORT", default=587)
EMAIL_USE_TLS = env.bool("EMAIL_USE_TLS", default=True)
EMAIL_HOST_USER = env("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = env("EMAIL_HOST_PASSWORD", default="")
SERVER_EMAIL = env("SERVER_EMAIL", default=EMAIL_HOST_USER)

# Surface server errors to maintainers instead of failing silently.
ADMINS = [tuple(a.split(":")) for a in env.list("DJANGO_ADMINS", default=[])]

# --- Logging: extend base.py's console-only config with a rotating
# file (so errors survive past whatever rotation schedule PythonAnywhere
# applies to its own captured-stdout log) and an explicit mail_admins
# handler on unhandled view exceptions (Django enables this by default
# when DEBUG=False *and* ADMINS is set, but it's made explicit here so
# it can't silently stop happening if ADMINS is ever left empty by
# accident — see the deployment checklist's "ADMINS must be set" item).
#
# LOG_DIR must exist and be writable by the WSGI process; on
# PythonAnywhere that's automatically true for anything under the
# project's own directory in your home folder. Created here at
# settings-import time so a fresh deploy doesn't 500 on its first
# request just because logs/ hasn't been created yet.
LOG_DIR = BASE_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)

LOGGING["handlers"]["file"] = {
    "class": "logging.handlers.RotatingFileHandler",
    "filename": str(LOG_DIR / "sams.log"),
    "maxBytes": 5 * 1024 * 1024,  # 5 MB
    "backupCount": 5,
    "formatter": "verbose",
}
LOGGING["handlers"]["mail_admins"] = {
    "class": "django.utils.log.AdminEmailHandler",
    "level": "ERROR",
}

for _logger_name in ("django", "django.security", "apps"):
    LOGGING["loggers"][_logger_name]["handlers"] = ["console", "file"]

LOGGING["loggers"]["django.request"]["handlers"] = ["console", "file", "mail_admins"]
LOGGING["root"]["handlers"] = ["console", "file"]