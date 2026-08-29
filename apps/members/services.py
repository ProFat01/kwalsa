"""
Shared services for apps.members.

`find_member_by_credentials` is the one place that knows how to look a
Member up by (Membership ID + Phone) or (NIN + Phone) without a Django
User account — there is no self-service login on Member itself (see the
`user` field's docstring on Member in models.py), so any feature that
needs to verify "is this really you" from those two credential pairs
calls this instead of re-writing the query.

Two callers use it:
  - apps.elections.forms.VotingLoginForm.authenticate() (pre-existing;
    refactored to call this instead of duplicating the lookup)
  - apps.members.forms.PortalLoginForm.authenticate() (Stage 8: Member
    Self-Service Portal)

This function deliberately stops at "find the member" — it does not
check approval_status or voting_status. Those are caller-specific
eligibility rules (voting requires voting_status; the member portal
just requires approval_status == APPROVED), so they stay out of the
shared lookup and are decided by each form/view instead.
"""
from django.core.cache import cache

from .models import Member

BY_MEMBERSHIP_ID = "membership_id"
BY_NIN = "nin"

CREDENTIAL_METHOD_CHOICES = [
    (BY_MEMBERSHIP_ID, "Membership ID + Phone Number"),
    (BY_NIN, "NIN + Phone Number"),
]


def find_member_by_credentials(method, identifier, phone_number):
    """
    Returns the matching Member, or None. `identifier` is a
    membership_id when method == BY_MEMBERSHIP_ID, or an nin_number when
    method == BY_NIN.
    """
    identifier = (identifier or "").strip()
    phone_number = (phone_number or "").strip()
    if not identifier or not phone_number:
        return None

    if method == BY_MEMBERSHIP_ID:
        return Member.objects.filter(membership_id=identifier, phone_number=phone_number).first()
    if method == BY_NIN:
        return Member.objects.filter(nin_number=identifier, phone_number=phone_number).first()
    return None


# ---------------------------------------------------------------------------
# v1.2: shared staff-facing Member filtering.
#
# Single source of truth for "which members match these filters", used by
# three different v1.2 features that must never disagree with each other:
#   - apps.analytics's member-management dashboard (counts a filtered set)
#   - apps.members's own staff member list ("Open Members" from analytics)
#   - apps.accounts's Communication Center (targeting an announcement)
#
# Deliberately lives here rather than in apps.analytics: Member is owned by
# this app, and apps.analytics already only ever *reads* Member as a
# consumer (see ANALYTICS_MODULE.md) — it never gets new manager methods of
# its own. Putting the one shared filter function on the owning app keeps
# that direction-of-dependency consistent instead of introducing a second,
# competing "how do I filter members" implementation.
# ---------------------------------------------------------------------------
FILTERABLE_MEMBER_FIELDS = ("faculty", "department", "level", "gender", "approval_status")


def filter_members(association, filters=None):
    """
    Returns a Member queryset for `association`, narrowed by any of
    FILTERABLE_MEMBER_FIELDS present (and non-empty) in `filters`. Every
    filter is independent and they combine with AND, exactly as Feature 1
    of the v1.2 brief asks ("each filter should work independently and
    together"). An empty/missing filters dict returns every member of the
    association, unfiltered — never Member.objects.all() unscoped by
    association, matching every other queryset in this project.

    Returns a queryset (never evaluated here) so callers decide whether
    they want .count(), a paginated slice, or to iterate it for sending
    mail — exactly the "reuse existing queryset logic, no duplicate
    filtering logic" requirement from the brief.
    """
    qs = Member.objects.filter(association=association)
    filters = filters or {}
    for field in FILTERABLE_MEMBER_FIELDS:
        raw_value = filters.get(field)
        value = raw_value.strip() if isinstance(raw_value, str) else raw_value
        if value:
            qs = qs.filter(**{field: value})
    return qs.select_related("association")


def member_filter_choices(association):
    """
    Distinct, non-blank values already on file for each free-text filter
    field, so the filter UI never hardcodes a faculty/department/level
    list that could drift from what members actually registered with.
    Gender/Approval Status use the model's own TextChoices instead, since
    those are fixed, not free text.

    Cached for a few minutes per association: this recomputes 3 DISTINCT
    scans over every member row on every single staff member-list page
    view/pagination click, which showed up as a real, N-scaling cost
    during the v2.0 load-testing pass (~37ms of the page's ~130ms total
    at 10,000 members — the paginated member list itself is only ~4ms,
    this was the actual bottleneck). The set of distinct
    faculty/department/level values in use changes rarely — a short TTL
    trades a few minutes of dropdown staleness for not re-scanning the
    whole table on every click. Nothing about which members are shown or
    how filtering behaves changes; this only caches the filter *options*.
    """
    cache_key = f"member_filter_choices:{association.pk}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    base = Member.objects.filter(association=association)
    choices = {
        "faculty": list(base.exclude(faculty="").order_by("faculty").values_list("faculty", flat=True).distinct()),
        "department": list(
            base.exclude(department="").order_by("department").values_list("department", flat=True).distinct()
        ),
        "level": list(base.exclude(level="").order_by("level").values_list("level", flat=True).distinct()),
        "gender": list(Member.Gender.choices),
        "approval_status": list(Member.ApprovalStatus.choices),
    }
    cache.set(cache_key, choices, 300)
    return choices


def resolve_announcement_recipients(association, recipient_type, filters=None, selected_ids=None):
    """
    Turns a Communication Center "recipient type" selection into an actual
    Member queryset. Built entirely on top of filter_members() above —
    there is no second, parallel filtering implementation for
    announcements; "Only approved members" and "Approval Status: Approved"
    on the analytics filter dashboard resolve through the exact same
    filter_members() call with {"approval_status": "approved"}.
    """
    filters = dict(filters or {})

    if recipient_type == "all":
        return filter_members(association, {})
    if recipient_type == "approved":
        return filter_members(association, {"approval_status": Member.ApprovalStatus.APPROVED})
    if recipient_type == "pending":
        return filter_members(association, {"approval_status": Member.ApprovalStatus.PENDING})
    if recipient_type in ("faculty", "department", "level", "gender"):
        return filter_members(association, {recipient_type: filters.get(recipient_type)})
    if recipient_type == "custom":
        return filter_members(association, filters)
    if recipient_type == "selected":
        return Member.objects.filter(association=association, pk__in=selected_ids or [])
    return Member.objects.none()
