"""
Pure helper functions for v2.1 Visitor & Usage Analytics — kept separate
from middleware.py so the categorization/hashing logic can be unit
tested directly without going through the request/response cycle.

Nothing here does any I/O or DB access; middleware.py is the only place
that constructs and saves a PageVisit.
"""
import hashlib
import hmac

from django.conf import settings
from django.utils import timezone

# Path prefixes that are never "meaningful public page visits" — staff
# tooling, the analytics dashboards themselves (avoid the dashboard
# inflating its own stats), Django admin, and static/media. Checked
# before any view resolution, so this list is a cheap first filter.
EXCLUDED_PATH_PREFIXES = (
    "/admin/",
    "/dashboard/",
    "/analytics/",
    "/static/",
    "/media/",
    "/favicon.ico",
    "/robots.txt",
)

# Broad, deliberately coarse UA sniffing — good enough for "roughly what
# category of device/browser" without building or storing a fingerprint.
_MOBILE_MARKERS = ("iphone", "android", "mobile", "ipod")
_TABLET_MARKERS = ("ipad", "tablet")

_SEARCH_ENGINE_MARKERS = ("google.", "bing.", "yahoo.", "duckduckgo.", "baidu.", "yandex.")
_SOCIAL_MARKERS = (
    "facebook.com", "instagram.com", "twitter.com", "x.com", "t.co",
    "linkedin.com", "whatsapp.com", "tiktok.com", "reddit.com",
)


def is_excluded_path(path: str) -> bool:
    return path.startswith(EXCLUDED_PATH_PREFIXES)


def resolve_page_key(request) -> str | None:
    """
    Django's own URL resolver already computed this for free — reuse it
    rather than pattern-matching the raw path. Returns None for
    requests with no resolver match (404s) or with no namespaced/name
    view (nothing meaningful to bucket them under).
    """
    match = getattr(request, "resolver_match", None)
    if match is None or not match.view_name:
        return None
    return match.view_name


def classify_device(user_agent: str) -> str:
    from .models import PageVisit

    ua = (user_agent or "").lower()
    if not ua:
        return PageVisit.DeviceCategory.UNKNOWN
    if any(marker in ua for marker in _TABLET_MARKERS):
        return PageVisit.DeviceCategory.TABLET
    if any(marker in ua for marker in _MOBILE_MARKERS):
        return PageVisit.DeviceCategory.MOBILE
    return PageVisit.DeviceCategory.DESKTOP


def classify_browser(user_agent: str) -> str:
    from .models import PageVisit

    ua = (user_agent or "").lower()
    if not ua:
        return PageVisit.BrowserCategory.OTHER
    # Order matters: Edge/Chrome/Safari UAs all contain overlapping
    # substrings (Edge contains "chrome" and "safari"; Chrome contains
    # "safari"), so the most specific markers must be checked first.
    if "edg/" in ua or "edga/" in ua or "edgios/" in ua:
        return PageVisit.BrowserCategory.EDGE
    if "firefox/" in ua:
        return PageVisit.BrowserCategory.FIREFOX
    if "chrome/" in ua or "crios/" in ua:
        return PageVisit.BrowserCategory.CHROME
    if "safari/" in ua:
        return PageVisit.BrowserCategory.SAFARI
    return PageVisit.BrowserCategory.OTHER


def classify_referrer(referer: str, host: str) -> str:
    from .models import PageVisit

    if not referer:
        return PageVisit.ReferrerCategory.DIRECT
    ref = referer.lower()
    if host and host.lower() in ref:
        # Referred from our own site (internal navigation) — closest
        # existing category is "direct", since it's not an external
        # traffic source worth reporting on.
        return PageVisit.ReferrerCategory.DIRECT
    if any(marker in ref for marker in _SEARCH_ENGINE_MARKERS):
        return PageVisit.ReferrerCategory.SEARCH
    if any(marker in ref for marker in _SOCIAL_MARKERS):
        return PageVisit.ReferrerCategory.SOCIAL
    return PageVisit.ReferrerCategory.OTHER_WEBSITE


def client_ip(request) -> str:
    """
    PythonAnywhere terminates TLS and forwards directly to this WSGI
    process — there is no additional untrusted reverse-proxy hop in
    front of it the way SECURE_PROXY_SSL_HEADER exists to handle for
    scheme detection, so REMOTE_ADDR is trustworthy here and X-Forwarded-
    For (spoofable by any client if trusted blindly) is deliberately not
    consulted.
    """
    return request.META.get("REMOTE_ADDR", "") or ""


def hash_visitor(ip: str, user_agent: str, association_id, when=None) -> str:
    """
    One-way, salted, per-day visitor identifier. Never store the raw IP;
    this is the only thing PageVisit persists in its place.

    The calendar day is folded INTO the hashed message (not stored
    alongside it) so the identifier for the same visitor changes every
    day — matching the same "rotate the salt daily" design used by
    privacy-first analytics tools generally, so a stored hash can never
    be used to link a visitor's activity across different days, even by
    someone with database access and the secret salt.
    """
    when = when or timezone.localdate()
    secret = getattr(settings, "VISITOR_HASH_SALT", None) or settings.SECRET_KEY
    message = f"{ip}|{user_agent or ''}|{association_id or ''}|{when.isoformat()}".encode("utf-8")
    digest = hmac.new(secret.encode("utf-8"), message, hashlib.sha256).hexdigest()
    return digest
