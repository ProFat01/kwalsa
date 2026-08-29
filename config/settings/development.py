from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env

DEBUG = True

ALLOWED_HOSTS = env.list("ALLOWED_HOSTS", default=["127.0.0.1", "localhost"])

# Parsed from DATABASE_URL (django-environ's env.db()) rather than
# hardcoded, so .env.example's DATABASE_URL variable actually does
# something — previously it was documented there but silently ignored,
# which is exactly the kind of "looks configurable but isn't" trap this
# audit exists to catch. Defaults to the same local SQLite file as
# before when DATABASE_URL isn't set, so a fresh clone with no .env
# customisation still works out of the box.
#
# WAL mode is added on top, only for sqlite3, because the election app
# can have many members hitting the DB with near-simultaneous writes
# (casting votes) during a live vote window — the default SQLite journal
# mode serialises writers far more aggressively than WAL and is the
# single most common cause of "database is locked" errors under that
# exact load pattern. This buys real headroom but is not a substitute
# for moving to PostgreSQL before a large, time-boxed election (see
# ARCHITECTURE.md "Future PostgreSQL migration"). Once DATABASE_URL
# points at postgres://, this block is a no-op — env.db() already
# returned a complete Postgres config and nothing here touches it.
DATABASES = {"default": env.db("DATABASE_URL", default=f"sqlite:///{BASE_DIR / 'db.sqlite3'}")}
if DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3":
    DATABASES["default"]["OPTIONS"] = {
        "timeout": 20,
        "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL; PRAGMA foreign_keys=ON;",
    }

# Django's own EMAIL_BACKEND — kept as console for any incidental use of
# django.core.mail directly. Member-facing email (approval emails,
# Communication Center announcements) no longer goes through this at all;
# it calls apps.core.mailjet_service directly, which — when
# MAILJET_API_KEY/MAILJET_SECRET_KEY aren't set, the default for local
# dev — logs the email instead of calling the real Mailjet API, giving
# the same "nothing actually gets sent, but you can see what would have
# been" developer experience this console backend used to provide for it.
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# Permissive locally; never use these two in production.
CORS_ALLOW_ALL_ORIGINS = True  # only meaningful once an API/frontend is added
