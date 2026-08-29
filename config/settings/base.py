"""
Base settings shared by every environment.

Environment-specific files (development.py / production.py) import * from
here and only override what genuinely differs between environments. This
keeps DB credentials, debug flags, and security headers out of version
control while everything structural (apps, middleware, templates, auth)
lives in one place.
"""
from pathlib import Path

import environ

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent

env = environ.Env()
environ.Env.read_env(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Core security primitives (overridden per-environment, sane fallback here)
# ---------------------------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", default="django-insecure-only-for-local-dev")

# ---------------------------------------------------------------------------
# Applications
# ---------------------------------------------------------------------------
DJANGO_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
]

THIRD_PARTY_APPS = [
    # registered here as they are introduced (e.g. django-environ needs no
    # app entry; future REST/async-task packages would go here)
]

# Local apps live under apps/<name> and are referenced as "apps.<name>" so
# the top-level "apps" package can grow indefinitely without colliding with
# third-party package names (e.g. a future PyPI "core" or "accounts").
LOCAL_APPS = [
    "apps.core",
    "apps.accounts",
    "apps.members",
    "apps.elections",
    "apps.analytics",
]

INSTALLED_APPS = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # v2.1: needs request.session (member portal) and request.user
    # (staff exclusion) already populated, hence placed after both
    # Session and Authentication middleware. See apps/analytics/
    # middleware.py for what it does and doesn't track.
    "apps.analytics.middleware.VisitorTrackingMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Django 6.0 built-in CSP support. Left inert (no SECURE_CSP defined)
    # until the frontend exists and we know which script/style/img sources
    # it actually needs; enabling it blind would just break the future UI.
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# Auth
# ---------------------------------------------------------------------------
# Custom user model. This MUST be set before the very first `migrate` ever
# runs on this project (changing AUTH_USER_MODEL after tables exist requires
# a manual, error-prone migration). Since this is a brand-new project we set
# it correctly from day one even though we don't need extra fields yet.
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LOGIN_URL = "admin:login"  # no public login view exists yet; admin only for now

# ---------------------------------------------------------------------------
# i18n / timezone
# ---------------------------------------------------------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = "Africa/Lagos"  # adjust to MSA's actual locale; stored as UTC internally regardless
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# Static / media
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
# Plain (non-manifest) storage as the shared default: ManifestStaticFilesStorage
# requires `collectstatic` to have already run to generate staticfiles.json,
# which is true on a deployed PythonAnywhere instance but never true in local
# dev or in the test runner — using it here would break every {% static %}
# tag outside of a real deployment. production.py overrides this to the
# compressed *manifest* version once collectstatic is actually part of the
# deploy step (see PythonAnywhere deployment notes).
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {"BACKEND": "django.contrib.staticfiles.storage.StaticFilesStorage"},
}

MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

# ---------------------------------------------------------------------------
# Misc
# ---------------------------------------------------------------------------
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Centralised so every app's FileField/ImageField max upload size can be
# enforced consistently by apps/members/validators.py and friends.
MAX_UPLOAD_SIZE_MB = 5

# Slug of the association new admin commands / fixtures default to when one
# isn't explicitly specified (set up via the admin once MSA is created).
DEFAULT_ASSOCIATION_SLUG = env("DEFAULT_ASSOCIATION_SLUG", default="msa")

# ---------------------------------------------------------------------------
# Mailjet Email API (member-facing email: approval emails, announcements)
# ---------------------------------------------------------------------------
# Used by apps.core.mailjet_service, the single place in SAMS that talks to
# Mailjet's HTTPS Send API — never SMTP (see that module's docstring for
# why: PythonAnywhere Free blocks outbound SMTP but allows HTTPS).
#
# Defined here (not just in production.py) so the same setting names work
# in every environment: local development can optionally point at a real
# Mailjet account too, and tests can override them with @override_settings.
# When left unset (the default for a fresh clone / .env.example), the
# service module logs the email instead of making a real API call — see
# apps/core/mailjet_service.py's "Local development convenience" note.
MAILJET_API_KEY = env("MAILJET_API_KEY", default="")
MAILJET_SECRET_KEY = env("MAILJET_SECRET_KEY", default="")

# Sender identity for all Mailjet-delivered mail. DEFAULT_FROM_EMAIL must
# be an address verified in the Mailjet account — this project does not
# and cannot bypass Mailjet's own sender verification.
DEFAULT_FROM_EMAIL = env("DEFAULT_FROM_EMAIL", default="")
DEFAULT_FROM_NAME = env("DEFAULT_FROM_NAME", default="")

# ---------------------------------------------------------------------------
# v2.1 Visitor & Usage Analytics
# ---------------------------------------------------------------------------
# How many days of raw PageVisit rows to keep — enforced by the
# `cleanup_visitor_analytics` management command, not automatically (see
# VISITOR_ANALYTICS.md "Retention" for why no scheduled job is wired up
# on PythonAnywhere Free). 90 days is enough for month-over-month trend
# comparison without the table growing unbounded.
VISITOR_ANALYTICS_RETENTION_DAYS = env.int("VISITOR_ANALYTICS_RETENTION_DAYS", default=90)

# Dedicated secret for the visitor-hash HMAC (apps.analytics.tracking.
# hash_visitor), independent of SECRET_KEY so it can be rotated on its
# own without also invalidating sessions/CSRF tokens/password-reset
# links. Optional: falls back to SECRET_KEY if unset, since either way
# the value never leaves the server and is only ever used one-way.
VISITOR_HASH_SALT = env("VISITOR_HASH_SALT", default="")

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
# Base shape shared by every environment: everything goes to the console.
# In development that's just your terminal. In production, PythonAnywhere
# already captures a WSGI process's stdout/stderr into its own per-app
# error log automatically — but that log is unstructured and gets rotated
#/cleared by PythonAnywhere on its own schedule, not ours. production.py
# therefore *adds* a second, app-controlled handler (a rotating file in
# the project's own logs/ directory) on top of this base, rather than
# replacing it — so the same errors are visible in both places: the
# platform's own log for "is the process even running", and ours for
# "what actually happened, kept as long as we choose to keep it."
#
# Deliberately does NOT silence django.request: Django's own default
# logging config already routes unhandled view exceptions there at
# ERROR level, which is the single most useful thing to keep, not
# suppress, in production.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {
            "format": "{asctime} {levelname} {name} {message}",
            "style": "{",
        },
        "simple": {
            "format": "{levelname} {name}: {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "simple",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
    "loggers": {
        # Quieter than root for Django's own framework-level INFO noise
        # (e.g. "GET /path 200" access-log-style messages aren't useful
        # here — PythonAnywhere's own access log already covers that).
        "django": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        # CSRF failures, suspicious host headers, disallowed redirects,
        # etc. — exactly the signal worth keeping separate from general
        # request noise.
        "django.security": {
            "handlers": ["console"],
            "level": "WARNING",
            "propagate": False,
        },
        # Unhandled exceptions from views. Kept at the framework default
        # (ERROR) rather than narrowed, and explicit here so it's a
        # documented decision, not an accident of Django's own defaults.
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
        # Namespace for this project's own app code, should any view/
        # service ever call logging.getLogger("apps.<name>"). Nothing
        # does yet (none of SAMS's apps log anything explicitly today),
        # but the namespace is wired up now so adding a log line later
        # is a one-line change, not a settings change too.
        "apps": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}
