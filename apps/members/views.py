"""
Public-facing views for the member registration module. No login is
required for any of these — registering and checking status both happen
before someone has any kind of account, by design.

The portal_* views below (Stage 8: Member Self-Service Portal) are the
one exception, but deliberately don't introduce real Django auth for
Member — same reasoning apps.elections.views gives for voting login:
Members don't have User accounts, so "logging in" is a lightweight
session marker set after PortalLoginForm.authenticate() succeeds, not
request.login(). See _get_portal_member below.
"""
from django.conf import settings
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.models import Association

from . import card_services
from .forms import MemberRegistrationForm, PortalLoginForm, StatusCheckForm
from .models import Member, MembershipCard, RegistrationApplication
from .services import FILTERABLE_MEMBER_FIELDS, filter_members, member_filter_choices

PORTAL_SESSION_KEY = "portal_member_id"


def _get_default_association():
    """
    Single-tenant lookup for now: resolves the one Association this
    deployment registers members against, via
    settings.DEFAULT_ASSOCIATION_SLUG (already part of the project's
    multi-tenancy scaffolding — see core/models.py). Returns None if it
    hasn't been created yet (e.g. a fresh install before anyone has used
    the admin to set up the Association row), so callers can fail
    gracefully instead of raising.
    """
    return Association.objects.filter(slug=settings.DEFAULT_ASSOCIATION_SLUG).first()


def register_view(request):
    association = _get_default_association()
    if association is None:
        return render(request, "members/register.html", {"association_missing": True})

    if request.method == "POST":
        form = MemberRegistrationForm(request.POST, request.FILES)
        if form.is_valid():
            application = form.save(association=association)
            return redirect("members:registration_success", application_number=application.application_number)
    else:
        form = MemberRegistrationForm()

    return render(
        request,
        "members/register.html",
        {
            "form": form,
            "association": association,
            "association_missing": False,
            "show_recovery_cta": getattr(form, "duplicate_detected", False),
        },
    )


def registration_success_view(request, application_number):
    application = get_object_or_404(
        RegistrationApplication.objects.select_related("member"),
        application_number=application_number,
    )
    return render(request, "members/registration_success.html", {"application": application})


def status_check_view(request):
    """
    One view, one URL, both GET (empty form) and POST (run the search) —
    keeps a bookmarkable/shareable form page while still rendering the
    PART 9-required separate result template as an included partial once
    a search has actually been performed.
    """
    searched = False
    result = None

    if request.method == "POST":
        form = StatusCheckForm(request.POST)
        if form.is_valid():
            searched = True
            result = form.lookup()
    else:
        form = StatusCheckForm()

    return render(
        request,
        "members/status_check.html",
        {"form": form, "searched": searched, "result": result},
    )


# ---------------------------------------------------------------------------
# Stage 8: Member Self-Service Portal
# ---------------------------------------------------------------------------
def _get_portal_member(request):
    """
    Returns the Member logged into the self-service portal this session,
    or None. Re-checks approval_status on every call (not just at login)
    so a member who is later rejected/suspended loses portal access on
    their very next request, the same "recheck live, don't trust what
    was true at login" pattern elections._get_voting_member follows for
    the election window.
    """
    member_id = request.session.get(PORTAL_SESSION_KEY)
    if not member_id:
        return None
    return (
        Member.objects.filter(pk=member_id, approval_status=Member.ApprovalStatus.APPROVED)
        .select_related("association")
        .first()
    )


def portal_login_view(request):
    error_message = None

    if request.method == "POST":
        form = PortalLoginForm(request.POST)
        if form.is_valid():
            member, error_code = form.authenticate()
            if member is not None:
                request.session.cycle_key()  # mitigate session fixation on this privilege boundary
                request.session[PORTAL_SESSION_KEY] = member.pk
                return redirect("members:portal_dashboard")
            error_message = (
                "Membership not found."
                if error_code == PortalLoginForm.NOT_FOUND
                else "Your membership has not yet been approved."
            )
    else:
        form = PortalLoginForm()

    return render(request, "members/portal_login.html", {"form": form, "error_message": error_message})


def _portal_election_context(member):
    """
    Finds the one election most relevant to show on the portal dashboard
    right now (open for voting, else soonest upcoming, else most recently
    closed) and derives the Vote Now eligibility purely from methods
    Election/Member already expose (is_voting_open is the model's own
    documented single source of truth for "can a member vote right now"
    — see its docstring in elections/models.py) — no new elections-app
    code needed for this. Imported locally, matching the existing
    cross-app-import convention apps.elections.views._get_voting_member
    already uses the other way around (importing apps.members.models
    from within apps.elections).
    """
    from apps.elections.models import Election

    elections = list(Election.objects.filter(association=member.association, is_enabled=True))
    open_now = [election for election in elections if election.is_voting_open]
    upcoming = sorted((e for e in elections if e.is_upcoming()), key=lambda e: e.start_datetime)
    closed = sorted((e for e in elections if e.is_closed()), key=lambda e: e.end_datetime, reverse=True)

    current_election = None
    election_state = "none"
    can_vote = False

    if open_now:
        current_election = open_now[0]
        already_voted = current_election.has_member_voted(member)
        election_state = "voted" if already_voted else "open"
        can_vote = member.voting_status and not already_voted
    elif upcoming:
        current_election = upcoming[0]
        election_state = "upcoming"
    elif closed:
        current_election = closed[0]
        election_state = "closed"

    return {"current_election": current_election, "election_state": election_state, "can_vote": can_vote}


def portal_dashboard_view(request):
    member = _get_portal_member(request)
    if member is None:
        return redirect("members:portal_login")

    context = {"member": member}
    context.update(_portal_election_context(member))
    return render(request, "members/portal_dashboard.html", context)


def portal_profile_view(request):
    """View-only detail page — no form, so there's nothing here that could edit a field."""
    member = _get_portal_member(request)
    if member is None:
        return redirect("members:portal_login")
    return render(request, "members/portal_profile.html", {"member": member})


@require_POST
def portal_logout_view(request):
    # Full session flush (not just popping PORTAL_SESSION_KEY) per the
    # brief's "Destroy session after logout" — a clean privilege
    # boundary rather than a partial clear.
    request.session.flush()
    return redirect("members:portal_login")


# ---------------------------------------------------------------------------
# Membership Card System v1
# ---------------------------------------------------------------------------
def portal_card_view(request):
    """Member-facing digital card — same portal-session gate as the rest of the portal."""
    member = _get_portal_member(request)
    if member is None:
        return redirect("members:portal_login")

    card = MembershipCard.get_or_create_for(member)
    return render(
        request,
        "members/card.html",
        {"member": member, "card": card, "qr_url": card_services.build_verification_url(request, card)},
    )


def portal_card_qr_view(request):
    """Streams the card's QR code as a PNG. Generated on the fly, never written to disk."""
    member = _get_portal_member(request)
    if member is None:
        return redirect("members:portal_login")

    card = MembershipCard.get_or_create_for(member)
    verification_url = card_services.build_verification_url(request, card)
    png_bytes = card_services.generate_qr_png(verification_url)
    return HttpResponse(png_bytes, content_type="image/png")


def verify_member_view(request, card_uuid):
    """
    Public page a scanned QR code opens. Deliberately exposes only safe,
    non-sensitive fields (name, membership ID, status, photo) — no phone
    number, NIN, date of birth, or address, matching the brief's "show
    only safe public information" requirement. An unknown/invalid
    card_uuid renders the same template with card=None rather than a
    404, so the page never confirms or denies via response shape whether
    a given UUID exists — a 404 vs 200 timing/behavior difference is
    itself a small enumeration signal.
    """
    card = MembershipCard.objects.select_related("member").filter(card_uuid=card_uuid).first()
    member = card.member if card else None
    is_valid = bool(member and member.approval_status == Member.ApprovalStatus.APPROVED)
    return render(request, "members/verify.html", {"member": member, "card": card, "is_valid": is_valid})


@login_required
@permission_required("members.view_member", raise_exception=True)
def staff_card_view(request, pk):
    """Staff-facing view/print of any member's card, gated by the existing members.view_member permission."""
    member = get_object_or_404(Member, pk=pk)
    card = MembershipCard.get_or_create_for(member)
    return render(
        request,
        "members/card.html",
        {
            "member": member,
            "card": card,
            "qr_url": card_services.build_verification_url(request, card),
            "is_staff_view": True,
        },
    )


@login_required
@permission_required("members.view_member", raise_exception=True)
def staff_card_qr_view(request, pk):
    """Streams the QR PNG for a staff-viewed card — same permission gate as staff_card_view."""
    member = get_object_or_404(Member, pk=pk)
    card = MembershipCard.get_or_create_for(member)
    verification_url = card_services.build_verification_url(request, card)
    png_bytes = card_services.generate_qr_png(verification_url)
    return HttpResponse(png_bytes, content_type="image/png")


# ---------------------------------------------------------------------------
# v1.2 Feature 2 & 3: staff Members list ("Open Members" from the analytics
# member-management dashboard) + per-row quick actions.
#
# Gated on the existing `members.view_member` permission — the same
# permission that already lets a role see Member in the Django admin — so
# no new permission was needed for a page that only *views* members.
# Filtering goes through the exact same apps.members.services.filter_members()
# call the analytics dashboard uses, via the exact same querystring keys, so
# "Open Members" always lands on precisely the set that was just counted.
# ---------------------------------------------------------------------------
@login_required
@permission_required("members.view_member", raise_exception=True)
def staff_member_list_view(request):
    association = _get_default_association()
    filters = {field: request.GET.get(field, "") for field in FILTERABLE_MEMBER_FIELDS}
    active_filters = {key: value for key, value in filters.items() if value}

    if association is None:
        members_page = None
        choices = {}
    else:
        members_qs = filter_members(association, filters)
        paginator = Paginator(members_qs, 25)
        members_page = paginator.get_page(request.GET.get("page"))
        choices = member_filter_choices(association)

    return render(
        request,
        "members/staff_list.html",
        {
            "association": association,
            "members": members_page,
            "filters": filters,
            "has_active_filters": bool(active_filters),
            "filter_choices": choices,
            "querystring": request.GET.urlencode(),
        },
    )
