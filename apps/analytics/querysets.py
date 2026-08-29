"""
Thin queryset helpers for the analytics module.

Deliberately doesn't touch apps.members or apps.elections at all — those
modules are already completed and approved, so every aggregation here
reads Member/Election/Vote from the outside, as a consumer, rather than
adding analytics-flavored manager methods onto models owned by other
apps. apps.analytics.services then turns these querysets into the
percentages/labels/structures the dashboards and JSON endpoints actually
need.
"""
from django.db.models import Count
from django.db.models.functions import TruncDate, TruncMonth, TruncYear

from apps.members.models import Member


def members_for_association(association):
    return Member.objects.filter(association=association)


def page_visits_for_range(association, start_date, end_date):
    """
    v2.1: base queryset every visitor-analytics aggregation builds on —
    always filtered to an indexed [start_date, end_date] range so no
    caller can accidentally issue an unbounded full-table scan.
    """
    from .models import PageVisit

    return PageVisit.objects.filter(
        association=association, visit_date__gte=start_date, visit_date__lte=end_date
    )


def course_counts(association):
    """[{"course": "Chemistry", "count": 120}, ...] — unordered; services.py applies sort order."""
    return (
        members_for_association(association)
        .exclude(course="")
        .values("course")
        .annotate(count=Count("id"))
    )


def institution_counts(association):
    return (
        members_for_association(association)
        .exclude(institution="")
        .values("institution")
        .annotate(count=Count("id"))
    )


# Trunc function per granularity — kept as a small lookup rather than
# branching inside every caller.
_TRUNC_FUNCS = {"day": TruncDate, "month": TruncMonth, "year": TruncYear}


def registration_counts_by_period(association, granularity="month"):
    """
    granularity: "day" | "month" | "year". Returns an unordered queryset
    of {"period": date, "count": int} — services.py formats `period`
    into the display label ("January 2026") and orders it.
    """
    trunc_func = _TRUNC_FUNCS[granularity]
    return (
        members_for_association(association)
        .annotate(period=trunc_func("registration_date"))
        .values("period")
        .annotate(count=Count("id"))
    )
