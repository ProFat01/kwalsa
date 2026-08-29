"""
Views for the analytics module: PART 10's staff dashboards and PART 11's
JSON API endpoints. Every view in this file is gated by
`analytics_staff_required` (PART 12) — there is no public view here,
unlike the members/elections modules.

All computation lives in services.py; these views only resolve the
Association/Election from the URL, call a service function, and either
render a template or return JsonResponse. Kept deliberately thin so the
JSON endpoints and the HTML dashboards that show the same numbers can
never drift apart — both call the exact same service function.
"""
from datetime import datetime
from functools import wraps

from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, render

from apps.core.models import Association
from apps.elections.models import Election

from . import services


def visitor_analytics_required(view_func):
    """
    Same login_required + permission_required(raise_exception=True)
    combination as analytics_staff_required, but gated on the dedicated
    `analytics.view_visitor_analytics` permission (PART 11) instead of
    `view_analytics_dashboard` — visitor traffic data is deliberately a
    separate grant so it can be handed to a role without also exposing
    membership/election analytics, and vice versa.
    """

    @wraps(view_func)
    @login_required
    @permission_required("analytics.view_visitor_analytics", raise_exception=True)
    def wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapped


def analytics_staff_required(view_func):
    """
    PART 12: only Analytics Admin / Super Admin may access analytics
    views. Stacks login_required (anonymous -> redirect to admin login)
    with permission_required(..., raise_exception=True) (authenticated
    but lacking the permission -> 403, not an endless login redirect) —
    the same combination the election module's admin dashboard already
    uses, applied here to *every* view in this file via one decorator
    instead of repeating both on each view.
    """

    @wraps(view_func)
    @login_required
    @permission_required("analytics.view_analytics_dashboard", raise_exception=True)
    def wrapped(request, *args, **kwargs):
        return view_func(request, *args, **kwargs)

    return wrapped


def _default_association():
    return Association.objects.filter(slug=settings.DEFAULT_ASSOCIATION_SLUG).first()


# ---------------------------------------------------------------------------
# PART 10: Dashboard pages
# ---------------------------------------------------------------------------
@analytics_staff_required
def overview_dashboard_view(request):
    association = _default_association()
    context = {
        "association": association,
        "membership": services.membership_overview(association) if association else None,
        "elections": services.all_elections_overview(association) if association else [],
    }
    return render(request, "analytics/overview_dashboard.html", context)


@analytics_staff_required
def membership_dashboard_view(request):
    association = _default_association()
    granularity = request.GET.get("granularity", "month")
    context = {
        "association": association,
        "membership": services.membership_overview(association) if association else None,
        "growth": services.registration_growth(association, granularity) if association else [],
        "granularity": granularity,
    }
    return render(request, "analytics/membership_dashboard.html", context)


@analytics_staff_required
def course_dashboard_view(request):
    association = _default_association()
    order = request.GET.get("order", "desc")
    context = {
        "association": association,
        "rows": services.course_distribution(association, order) if association else [],
        "order": order,
    }
    return render(request, "analytics/course_dashboard.html", context)


@analytics_staff_required
def institution_dashboard_view(request):
    association = _default_association()
    order = request.GET.get("order", "desc")
    context = {
        "association": association,
        "rows": services.institution_distribution(association, order) if association else [],
        "order": order,
    }
    return render(request, "analytics/institution_dashboard.html", context)


@analytics_staff_required
def age_dashboard_view(request):
    association = _default_association()
    context = {
        "association": association,
        "rows": services.age_distribution(association) if association else [],
    }
    return render(request, "analytics/age_dashboard.html", context)


@analytics_staff_required
def election_dashboard_list_view(request):
    association = _default_association()
    context = {
        "association": association,
        "elections": services.all_elections_overview(association) if association else [],
    }
    return render(request, "analytics/election_dashboard_list.html", context)


@analytics_staff_required
def election_dashboard_detail_view(request, pk):
    election = get_object_or_404(Election.objects.select_related("association"), pk=pk)
    context = {
        "election": election,
        "overview": services.election_overview(election),
        "results": services.position_results_with_winner(election),
        "age_participation": services.age_participation(election),
    }
    return render(request, "analytics/election_dashboard_detail.html", context)


# ---------------------------------------------------------------------------
# v1.2 Feature 1 & 2: member-management filter dashboard + "Open Members"
# ---------------------------------------------------------------------------
def _member_filters_from_request(request):
    from apps.members.services import FILTERABLE_MEMBER_FIELDS

    return {field: request.GET.get(field, "") for field in FILTERABLE_MEMBER_FIELDS}


@analytics_staff_required
def member_management_dashboard_view(request):
    """
    Feature 1: filterable management view over Member — Faculty,
    Department, Level, Gender, Approval Status, independently and
    combined. Feature 2: the "Open Members" button reuses the exact same
    querystring on the staff Members list (apps.members.views.
    staff_member_list_view), which filters through the identical
    apps.members.services.filter_members() call — so what this page
    counts is always exactly what that page lists, by construction, not
    by keeping two implementations in sync by hand.
    """
    from apps.members.services import member_filter_choices

    association = _default_association()
    filters = _member_filters_from_request(request)
    active_filters = {key: value for key, value in filters.items() if value}

    context = {
        "association": association,
        "filters": filters,
        "querystring": request.GET.urlencode(),
        "overview": services.member_management_overview(association, filters) if association else None,
        "filter_choices": member_filter_choices(association) if association else {},
        "has_active_filters": bool(active_filters),
    }
    return render(request, "analytics/member_management_dashboard.html", context)


# ---------------------------------------------------------------------------
# PART 11: JSON API endpoints — clean, chart-library-ready data only.
# No JS charting is wired up here on purpose; these just return JSON.
# ---------------------------------------------------------------------------
@analytics_staff_required
def api_membership_statistics(request):
    association = _default_association()
    return JsonResponse(services.membership_overview(association) if association else {})


@analytics_staff_required
def api_course_statistics(request):
    association = _default_association()
    order = request.GET.get("order", "desc")
    rows = services.course_distribution(association, order) if association else []
    return JsonResponse({"order": order, "results": rows})


@analytics_staff_required
def api_institution_statistics(request):
    association = _default_association()
    order = request.GET.get("order", "desc")
    rows = services.institution_distribution(association, order) if association else []
    return JsonResponse({"order": order, "results": rows})


@analytics_staff_required
def api_age_distribution(request):
    association = _default_association()
    rows = services.age_distribution(association) if association else []
    return JsonResponse({"results": rows})


@analytics_staff_required
def api_registration_growth(request):
    """Bonus endpoint (not in PART 11's explicit list, but directly fulfils PART 5's 'helper methods for future chart integration')."""
    association = _default_association()
    granularity = request.GET.get("granularity", "month")
    rows = services.registration_growth(association, granularity) if association else []
    return JsonResponse({"granularity": granularity, "results": rows})


@analytics_staff_required
def api_election_results(request, pk):
    election = get_object_or_404(Election, pk=pk)
    results = services.position_results_with_winner(election)
    payload = [
        {
            "position": item["position"].title,
            "total_votes": item["total_votes"],
            "is_tie": item["is_tie"],
            "winner": item["winner"].name if item["winner"] else None,
            "candidates": [
                {"name": row["candidate"].name, "vote_count": row["vote_count"], "percentage": row["percentage"]}
                for row in item["candidates"]
            ],
        }
        for item in results
    ]
    return JsonResponse({"election": election.name, "results": payload})


@analytics_staff_required
def api_election_turnout(request, pk):
    election = get_object_or_404(Election, pk=pk)
    overview = services.election_overview(election)
    return JsonResponse(
        {
            "election": election.name,
            "eligible_voters": overview["eligible_voters"],
            "votes_cast": overview["votes_cast"],
            "turnout_percentage": overview["turnout_percentage"],
            "total_positions": overview["total_positions"],
            "total_candidates": overview["total_candidates"],
            "age_participation": services.age_participation(election),
        }
    )


# ---------------------------------------------------------------------------
# v2.1: Visitor & Usage Analytics
# ---------------------------------------------------------------------------
def _parse_date(value):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def _visitor_date_range_from_request(request):
    range_key = request.GET.get("range", "30d")
    if range_key not in services.DATE_RANGE_CHOICES:
        range_key = "30d"
    start = _parse_date(request.GET.get("start"))
    end = _parse_date(request.GET.get("end"))
    if range_key == "custom" and not (start and end):
        # Malformed/missing custom bounds — fall back cleanly rather
        # than erroring on a hand-edited querystring.
        range_key = "30d"
    start_date, end_date = services.resolve_date_range(range_key, start, end)
    return range_key, start_date, end_date


@visitor_analytics_required
def visitor_analytics_dashboard_view(request):
    association = _default_association()
    range_key, start_date, end_date = _visitor_date_range_from_request(request)
    context = {
        "association": association,
        "range_key": range_key,
        "start_date": start_date,
        "end_date": end_date,
        "overview": services.visitor_overview(association),
        "trend": services.traffic_trend(association, start_date, end_date),
        "pages": services.top_pages(association, start_date, end_date),
        "devices": services.device_breakdown(association, start_date, end_date),
        "browsers": services.browser_breakdown(association, start_date, end_date),
        "referrers": services.referrer_breakdown(association, start_date, end_date),
    }
    return render(request, "analytics/visitor_analytics_dashboard.html", context)


@visitor_analytics_required
def api_visitor_analytics(request):
    association = _default_association()
    range_key, start_date, end_date = _visitor_date_range_from_request(request)
    return JsonResponse(
        {
            "range": range_key,
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "overview": services.visitor_overview(association),
            "trend": [
                {"date": row["date"].isoformat(), "visits": row["visits"], "unique_visitors": row["unique_visitors"]}
                for row in services.traffic_trend(association, start_date, end_date)
            ],
            "pages": services.top_pages(association, start_date, end_date),
            "devices": services.device_breakdown(association, start_date, end_date),
            "browsers": services.browser_breakdown(association, start_date, end_date),
            "referrers": services.referrer_breakdown(association, start_date, end_date),
        }
    )
