"""
Business logic for the analytics module. Views (dashboards and JSON API)
call into these functions and either render a template or json.dumps the
result — none of this logic lives in views.py itself, and none of it
lives on Member/Election (both already-completed modules this task
isn't allowed to rewrite).

Two computation styles on purpose:
  - membership/course/institution/age/growth: always computed live from
    Member directly. These are cheap GROUP BY/COUNT queries even at
    several thousand members, and "accurate" matters more here than
    "cached" — see ELECTION_MODULE.md's identical reasoning for live
    results over snapshots.
  - Snapshot *generation* functions at the bottom populate the existing
    MembershipSnapshot / AgeDistributionSnapshot / ElectionResultSnapshot
    tables on demand (PART 9) — for historical trend tracking and as the
    "future optimization" path the spec asks to leave open, not because
    today's dashboards depend on them.
"""
from collections import Counter
from datetime import timedelta

from django.db import transaction
from django.db.models import Count
from django.utils import timezone

from apps.elections.models import Election

from .models import AgeDistributionSnapshot, ElectionResultSnapshot, MembershipSnapshot, PageVisit
from .querysets import (
    course_counts,
    institution_counts,
    members_for_association,
    page_visits_for_range,
    registration_counts_by_period,
)


def _percentage(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def _calculate_age(date_of_birth, as_of=None) -> int:
    as_of = as_of or timezone.now().date()
    return as_of.year - date_of_birth.year - ((as_of.month, as_of.day) < (date_of_birth.month, date_of_birth.day))


# ---------------------------------------------------------------------------
# PART 1: Membership analytics
# ---------------------------------------------------------------------------
def membership_overview(association) -> dict:
    from apps.members.models import Member

    members = members_for_association(association)
    total = members.count()
    approved = members.filter(approval_status=Member.ApprovalStatus.APPROVED).count()
    pending = members.filter(approval_status=Member.ApprovalStatus.PENDING).count()
    rejected = members.filter(approval_status=Member.ApprovalStatus.REJECTED).count()
    undergraduate = members.filter(category=Member.Category.UNDERGRADUATE).count()
    alumni = members.filter(alumni_status=True).count()

    return {
        "total_members": total,
        "total_approved": approved,
        "approved_percentage": _percentage(approved, total),
        "total_pending": pending,
        "pending_percentage": _percentage(pending, total),
        "total_rejected": rejected,
        "rejected_percentage": _percentage(rejected, total),
        "total_undergraduate": undergraduate,
        "undergraduate_percentage": _percentage(undergraduate, total),
        "total_alumni": alumni,
        "alumni_percentage": _percentage(alumni, total),
    }


# ---------------------------------------------------------------------------
# PARTS 2 & 3: Course / Institution analytics — same shape, same helper
# ---------------------------------------------------------------------------
def _distribution(rows, label_field, order="desc") -> list:
    rows = list(rows)
    total = sum(row["count"] for row in rows)
    for row in rows:
        row["percentage"] = _percentage(row["count"], total)
    # Two stable passes: alphabetical-by-label first, then by count — ties
    # come out in a deterministic, readable order instead of DB-dependent
    # GROUP BY ordering.
    rows.sort(key=lambda row: row[label_field])
    rows.sort(key=lambda row: row["count"], reverse=(order != "asc"))
    return rows


def course_distribution(association, order="desc") -> list:
    """order: "desc" (highest membership first, default) or "asc" (lowest first)."""
    return _distribution(course_counts(association), "course", order)


def institution_distribution(association, order="desc") -> list:
    return _distribution(institution_counts(association), "institution", order)


# ---------------------------------------------------------------------------
# PART 4: Age analytics
# ---------------------------------------------------------------------------
def age_distribution(association, as_of=None) -> list:
    as_of = as_of or timezone.now().date()
    dobs = members_for_association(association).exclude(date_of_birth__isnull=True).values_list(
        "date_of_birth", flat=True
    )
    bucket_counts = Counter(AgeDistributionSnapshot.bucket_for_age(_calculate_age(dob, as_of)) for dob in dobs)
    total = sum(bucket_counts.values())

    return [
        {
            "bracket": bracket_value,
            "label": bracket_label,
            "count": bucket_counts.get(bracket_value, 0),
            "percentage": _percentage(bucket_counts.get(bracket_value, 0), total),
        }
        for bracket_value, bracket_label in AgeDistributionSnapshot.AgeBracket.choices
    ]


# ---------------------------------------------------------------------------
# PART 5: Registration growth
# ---------------------------------------------------------------------------
_GROWTH_LABEL_FORMATS = {"day": "%d %b %Y", "month": "%B %Y", "year": "%Y"}


def registration_growth(association, granularity="month") -> list:
    """
    granularity: "day" | "month" | "year". Returns chronologically
    ordered [{"period": date, "label": "January 2026", "count": N}, ...]
    — a plain list of plain dicts, already shaped for a future chart
    library to consume directly (PART 5's "helper methods for future
    chart integration") without that library needing to know anything
    about Django querysets or Trunc functions.
    """
    if granularity not in _GROWTH_LABEL_FORMATS:
        raise ValueError(f"granularity must be one of {list(_GROWTH_LABEL_FORMATS)}, got {granularity!r}")

    rows = sorted(registration_counts_by_period(association, granularity), key=lambda row: row["period"])
    label_format = _GROWTH_LABEL_FORMATS[granularity]
    return [
        {
            "period": row["period"],
            "label": row["period"].strftime(label_format) if row["period"] else "Unknown",
            "count": row["count"],
        }
        for row in rows
    ]


# ---------------------------------------------------------------------------
# PART 6: Election analytics
# ---------------------------------------------------------------------------
def election_overview(election) -> dict:
    """
    Eligible/cast/turnout already exist on Election itself (built in the
    election module) — this just packages them with position/candidate
    counts.

    v2.0: also breaks eligible voters down by Membership Category, built
    entirely on Election.eligible_members() (the Election Eligibility
    Engine) — this module adds no eligibility logic of its own, it only
    narrows the same queryset one step further with a DB-level .filter(),
    same as the rest of this file does for course/institution/age.
    """
    from apps.members.models import Member

    eligible = election.eligible_members()
    eligible_voters = election.eligible_voters_count()
    votes_cast = election.voters_count()
    return {
        "election": election,
        "eligible_voters": eligible_voters,
        "eligible_undergraduate": eligible.filter(category=Member.Category.UNDERGRADUATE).count(),
        "eligible_alumni": eligible.filter(category=Member.Category.GRADUATE_ALUMNI).count(),
        "votes_cast": votes_cast,
        "turnout_percentage": election.turnout_percentage(eligible=eligible_voters, voters=votes_cast),
        "total_positions": election.positions.count(),
        "total_candidates": election.candidates.count(),
    }


def all_elections_overview(association) -> list:
    return [election_overview(election) for election in Election.objects.filter(association=association)]


# ---------------------------------------------------------------------------
# PART 7: Position analytics (vote totals, percentages, winner)
# ---------------------------------------------------------------------------
def position_results_with_winner(election) -> list:
    """
    Builds on Election.results_by_position() (already-approved election
    module code, untouched here) and adds winner determination on top,
    rather than teaching the elections app about "winners" — that's an
    analytics-module concern, not something Election itself needs to
    know how to compute.
    """
    results = election.results_by_position()
    for item in results:
        candidates = item["candidates"]  # already ordered by -vote_count, name
        if not candidates or item["total_votes"] == 0:
            item["winner"] = None
            item["is_tie"] = False
            continue

        top_count = candidates[0]["vote_count"]
        leaders = [row["candidate"] for row in candidates if row["vote_count"] == top_count]
        if len(leaders) > 1:
            item["winner"] = None
            item["is_tie"] = True
            item["tied_candidates"] = leaders
        else:
            item["winner"] = leaders[0]
            item["is_tie"] = False
    return results


# ---------------------------------------------------------------------------
# PART 8: Age participation analytics
# ---------------------------------------------------------------------------
def age_participation(election, as_of=None) -> list:
    as_of = as_of or timezone.now().date()
    eligible_members = (
        members_for_association(election.association)
        .filter(voting_status=True)
        .exclude(date_of_birth__isnull=True)
        .values_list("id", "date_of_birth")
    )
    voted_member_ids = set(election.votes.values_list("member_id", flat=True).distinct())

    eligible_counts = Counter()
    voted_counts = Counter()
    for member_id, date_of_birth in eligible_members:
        bracket = AgeDistributionSnapshot.bucket_for_age(_calculate_age(date_of_birth, as_of))
        eligible_counts[bracket] += 1
        if member_id in voted_member_ids:
            voted_counts[bracket] += 1

    return [
        {
            "bracket": bracket_value,
            "label": bracket_label,
            "eligible": eligible_counts.get(bracket_value, 0),
            "voted": voted_counts.get(bracket_value, 0),
            "participation_percentage": _percentage(
                voted_counts.get(bracket_value, 0), eligible_counts.get(bracket_value, 0)
            ),
        }
        for bracket_value, bracket_label in AgeDistributionSnapshot.AgeBracket.choices
    ]


# ---------------------------------------------------------------------------
# PART 9: Snapshot generation — populates the existing snapshot models
# ---------------------------------------------------------------------------
# ---------------------------------------------------------------------------
# v1.2 Feature 1: Advanced Course Analytics -> member-management dashboard
# ---------------------------------------------------------------------------
def member_management_overview(association, filters=None) -> dict:
    """
    Turns the Analytics page's filters (Faculty/Department/Level/Gender/
    Approval Status) into a total + a status breakdown "chart" (reusing
    the same vote-bar-track/vote-bar-fill markup the election/course
    dashboards already use — no new charting code). Built entirely on top
    of apps.members.services.filter_members(), the one shared filter
    implementation also used by the staff Members list and the
    Communication Center — this function adds no filtering logic of its
    own, only presentation shaping.
    """
    from django.db.models import Count

    from apps.members.models import Member
    from apps.members.services import filter_members

    qs = filter_members(association, filters)
    total = qs.count()

    status_counts = {row["approval_status"]: row["count"] for row in qs.values("approval_status").annotate(count=Count("id"))}
    status_breakdown = [
        {
            "value": value,
            "label": label,
            "count": status_counts.get(value, 0),
            "percentage": _percentage(status_counts.get(value, 0), total),
        }
        for value, label in Member.ApprovalStatus.choices
    ]

    gender_counts = {row["gender"]: row["count"] for row in qs.exclude(gender="").values("gender").annotate(count=Count("id"))}
    gender_breakdown = [
        {
            "value": value,
            "label": label,
            "count": gender_counts.get(value, 0),
            "percentage": _percentage(gender_counts.get(value, 0), total),
        }
        for value, label in Member.Gender.choices
    ]

    return {
        "total": total,
        "status_breakdown": status_breakdown,
        "gender_breakdown": gender_breakdown,
    }


@transaction.atomic
def generate_membership_snapshot(association, snapshot_date=None) -> MembershipSnapshot:
    snapshot_date = snapshot_date or timezone.now().date()
    overview = membership_overview(association)
    snapshot, _created = MembershipSnapshot.objects.update_or_create(
        association=association,
        snapshot_date=snapshot_date,
        defaults={
            "total_members": overview["total_members"],
            "total_approved": overview["total_approved"],
            "total_pending": overview["total_pending"],
            "total_rejected": overview["total_rejected"],
            "total_alumni": overview["total_alumni"],
            "total_undergraduate": overview["total_undergraduate"],
        },
    )
    return snapshot


@transaction.atomic
def generate_age_distribution_snapshot(association, snapshot_date=None) -> list:
    snapshot_date = snapshot_date or timezone.now().date()
    rows = age_distribution(association, as_of=snapshot_date)
    snapshots = []
    for row in rows:
        snapshot, _created = AgeDistributionSnapshot.objects.update_or_create(
            association=association,
            snapshot_date=snapshot_date,
            age_bracket=row["bracket"],
            defaults={"count": row["count"]},
        )
        snapshots.append(snapshot)
    return snapshots


@transaction.atomic
def generate_election_result_snapshots(election) -> list:
    """
    Refreshes the numbers/winner on the existing ElectionResultSnapshot
    rows for every contested position — deliberately leaves
    `is_published` untouched (defaults to False only on first creation).
    Generating/refreshing a snapshot is not the same action as publishing
    it; that stays the explicit, audited admin action the election module
    already built.
    """
    results = position_results_with_winner(election)
    eligible = election.eligible_voters_count()
    turnout = election.turnout_percentage(eligible=eligible, voters=election.voters_count())
    snapshots = []
    for item in results:
        snapshot, _created = ElectionResultSnapshot.objects.update_or_create(
            election=election,
            position=item["position"],
            defaults={
                "total_votes_cast": item["total_votes"],
                "total_eligible_voters": eligible,
                "turnout_percentage": turnout,
                "winner_candidate": item["winner"],
            },
        )
        snapshots.append(snapshot)
    return snapshots


# ---------------------------------------------------------------------------
# v2.1: Visitor & Usage Analytics
#
# Every function below is a live, indexed aggregation over PageVisit for
# an explicit [start_date, end_date] range (see querysets.
# page_visits_for_range) — deliberately not a second layer of
# precomputed snapshots on top. Table volume is retention-bounded (see
# VISITOR_ANALYTICS_RETENTION_DAYS), so a GROUP BY over even the full
# 90-day window stays cheap; see VISITOR_ANALYTICS.md "Performance" for
# the measured query counts/timings this claim is based on.
# ---------------------------------------------------------------------------

# Friendly display labels for the URL names most likely to matter to an
# administrator. Anything not listed here still renders — see
# page_label() — just with a mechanically prettified fallback instead of
# a hand-picked label.
PAGE_LABELS = {
    "core:home": "Home",
    "core:about": "About",
    "core:contact": "Contact",
    "members:register": "Registration",
    "members:registration_success": "Registration Success",
    "members:status_check": "Check Application Status",
    "members:portal_login": "Member Login",
    "members:portal_dashboard": "Member Dashboard",
    "members:portal_profile": "Member Profile",
    "members:portal_card": "Membership Card",
    "members:portal_card_qr": "Membership Card QR",
    "members:verify_member": "Member Verification",
    "elections:election_list": "Elections",
    "elections:election_detail": "Election Details",
    "elections:voting_login": "Voting Login",
    "elections:results": "Election Results",
}

DATE_RANGE_CHOICES = ("today", "7d", "30d", "90d", "custom")


def page_label(page_key: str) -> str:
    if page_key in PAGE_LABELS:
        return PAGE_LABELS[page_key]
    # Mechanical fallback for any URL name not explicitly labeled above,
    # e.g. "elections:vote_success" -> "Vote Success".
    name = page_key.split(":")[-1]
    return name.replace("_", " ").title()


def resolve_date_range(range_key: str, start=None, end=None, today=None):
    """
    Turns a filter key (PART 10's "Today / Last 7 days / Last 30 days /
    Last 90 days", plus an explicit custom start/end) into a concrete
    [start_date, end_date] pair. Unrecognized/missing input falls back
    to the last 30 days rather than raising, since this is always fed
    by a dashboard querystring a person could hand-edit.
    """
    today = today or timezone.localdate()
    if range_key == "today":
        return today, today
    if range_key == "7d":
        return today - timedelta(days=6), today
    if range_key == "90d":
        return today - timedelta(days=89), today
    if range_key == "custom" and start and end:
        return (start, end) if start <= end else (end, start)
    return today - timedelta(days=29), today


def _visits_and_unique(queryset):
    aggregate = queryset.aggregate(visits=Count("id"), unique=Count("visitor_hash", distinct=True))
    return aggregate["visits"] or 0, aggregate["unique"] or 0


def visitor_overview(association) -> dict:
    """
    PART 9's fixed summary cards — today / this week / this month / all-
    time — independent of whatever date-range filter the rest of the
    dashboard is currently showing.
    """
    today = timezone.localdate()
    week_start = today - timedelta(days=6)
    month_start = today.replace(day=1)

    visits_today, unique_today = _visits_and_unique(page_visits_for_range(association, today, today))
    visits_week, unique_week = _visits_and_unique(page_visits_for_range(association, week_start, today))
    visits_month, unique_month = _visits_and_unique(page_visits_for_range(association, month_start, today))
    visits_total, unique_total = _visits_and_unique(
        PageVisit.objects.filter(association=association)
    )

    return {
        "visits_today": visits_today,
        "unique_today": unique_today,
        "visits_this_week": visits_week,
        "unique_this_week": unique_week,
        "visits_this_month": visits_month,
        "unique_this_month": unique_month,
        "total_visits": visits_total,
        "total_unique_visitors": unique_total,
    }


def traffic_trend(association, start_date, end_date) -> list:
    """[{"date": date, "visits": int, "unique_visitors": int}, ...] ordered oldest -> newest."""
    rows = (
        page_visits_for_range(association, start_date, end_date)
        .values("visit_date")
        .annotate(visits=Count("id"), unique_visitors=Count("visitor_hash", distinct=True))
        .order_by("visit_date")
    )
    return [
        {"date": row["visit_date"], "visits": row["visits"], "unique_visitors": row["unique_visitors"]}
        for row in rows
    ]


def top_pages(association, start_date, end_date, limit=10) -> list:
    """[{"page_key": ..., "label": ..., "visits": int, "percentage": float}, ...] ordered by visits desc."""
    queryset = page_visits_for_range(association, start_date, end_date)
    total = queryset.count()
    rows = queryset.values("page_key").annotate(visits=Count("id")).order_by("-visits")[:limit]
    return [
        {
            "page_key": row["page_key"],
            "label": page_label(row["page_key"]),
            "visits": row["visits"],
            "percentage": _percentage(row["visits"], total),
        }
        for row in rows
    ]


def _category_breakdown(association, start_date, end_date, field: str, choices) -> list:
    queryset = page_visits_for_range(association, start_date, end_date)
    total = queryset.count()
    counts = dict(queryset.values_list(field).annotate(count=Count("id")))
    label_map = dict(choices)
    return [
        {
            "category": value,
            "label": label_map.get(value, value),
            "count": counts.get(value, 0),
            "percentage": _percentage(counts.get(value, 0), total),
        }
        for value, _label in choices
    ]


def device_breakdown(association, start_date, end_date) -> list:
    return _category_breakdown(association, start_date, end_date, "device_category", PageVisit.DeviceCategory.choices)


def browser_breakdown(association, start_date, end_date) -> list:
    return _category_breakdown(
        association, start_date, end_date, "browser_category", PageVisit.BrowserCategory.choices
    )


def referrer_breakdown(association, start_date, end_date) -> list:
    return _category_breakdown(
        association, start_date, end_date, "referrer_category", PageVisit.ReferrerCategory.choices
    )


def cleanup_visitor_analytics(retention_days: int, today=None) -> int:
    """
    Deletes PageVisit rows older than `retention_days`. Returns the
    number of rows deleted. Pure function (no stdout/logging) so it's
    directly unit-testable; the management command wraps this and does
    the reporting.
    """
    today = today or timezone.localdate()
    cutoff = today - timedelta(days=retention_days)
    deleted_count, _ = PageVisit.objects.filter(visit_date__lt=cutoff).delete()
    return deleted_count
