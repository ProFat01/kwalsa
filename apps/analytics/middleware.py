"""
v2.1 — Visitor & Usage Analytics tracking middleware.

Writes exactly one PageVisit row for a request that is:
  - a GET request
  - resolved to a real, named view (no 404s)
  - not under an excluded path prefix (admin/dashboard/analytics/static/media)
  - answered with a 200 and an HTML response (not a redirect, not JSON,
    not a file download)
  - not made by an authenticated staff account (is_staff) — staff/admin
    activity is excluded from public visitor statistics by design

Positioned after WhiteNoiseMiddleware in MIDDLEWARE (see config/settings/
base.py) so in production, static files served by WhiteNoise never reach
this code at all; the path-prefix check below is a defensive second
layer for the dev/test static-serving path, which does go through the
full middleware stack.

Exactly one DB write per tracked request, and nothing is written at all
for the (large) majority of requests this middleware skips — this is
the entire performance budget of the feature.
"""
from . import tracking


class VisitorTrackingMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)

        try:
            self._maybe_track(request, response)
        except Exception:
            # Analytics must never be able to break a real page request.
            # Any failure here is swallowed rather than propagated —
            # see VISITOR_ANALYTICS.md "Failure mode" for why this
            # trade-off (silently losing a data point) beats the
            # alternative (a 500 caused by the tracker itself).
            pass

        return response

    def _maybe_track(self, request, response):
        if request.method != "GET":
            return
        if tracking.is_excluded_path(request.path):
            return
        if response.status_code != 200:
            return
        content_type = response.get("Content-Type", "")
        if not content_type.startswith("text/html"):
            return

        page_key = tracking.resolve_page_key(request)
        if not page_key:
            return

        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and user.is_staff:
            return

        from django.conf import settings

        from apps.core.models import Association

        association = Association.objects.filter(slug=settings.DEFAULT_ASSOCIATION_SLUG).first()

        visitor_type = "member" if request.session.get("portal_member_id") else "anonymous"
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        ip = tracking.client_ip(request)
        visitor_hash = tracking.hash_visitor(ip, user_agent, association.pk if association else None)

        from django.utils import timezone

        from .models import PageVisit

        PageVisit.objects.create(
            association=association,
            visit_date=timezone.localdate(),
            page_key=page_key,
            path=request.path[:255],
            visitor_hash=visitor_hash,
            visitor_type=visitor_type,
            device_category=tracking.classify_device(user_agent),
            browser_category=tracking.classify_browser(user_agent),
            referrer_category=tracking.classify_referrer(
                request.META.get("HTTP_REFERER", ""), request.get_host()
            ),
        )
