"""
Views for the election management module.

Members don't have User accounts (see apps.members), so "logging in to
vote" is a lightweight, election-scoped session marker rather than
Django's normal authentication — set by voting_login_view after
VotingLoginForm.authenticate() succeeds, checked by _get_voting_member()
before the ballot is ever shown, and cleared once a ballot is submitted.

Django admin login (LOGIN_URL = "admin:login", see config/settings/base.py)
is reused as-is for the one screen that *does* need real auth: the staff
dashboard in PART 9.
"""
from django.contrib.auth.decorators import login_required, permission_required
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render

from .eligibility import is_member_eligible
from .forms import VotingLoginForm, build_ballot_form_class
from .models import Candidate, Election, Vote

# Election Eligibility Engine (v2.0): the one, generic, never-more-specific
# message shown to a voter who is authenticated but not eligible for this
# particular election. Deliberately does not say *why* — see eligibility.py
# module docstring: internal eligibility rules (institution/faculty/level/
# gender/etc.) are never exposed to the voter.
NOT_ELIGIBLE_MESSAGE = "You are not eligible to participate in this election."

VOTING_SESSION_KEY_TEMPLATE = "voting_member_{election_id}"


def _voting_session_key(election):
    return VOTING_SESSION_KEY_TEMPLATE.format(election_id=election.pk)


def _get_voting_member(request, election):
    """Returns the Member authenticated for *this* election's ballot this session, or None."""
    member_id = request.session.get(_voting_session_key(election))
    if not member_id:
        return None
    from apps.members.models import Member

    return Member.objects.filter(pk=member_id).first()


# ---------------------------------------------------------------------------
# PART 11: Election List / Election Detail — public, read-only
# ---------------------------------------------------------------------------
def election_list_view(request):
    elections = list(Election.objects.select_related("association").all())
    return render(request, "elections/election_list.html", {"elections": elections})


def election_detail_view(request, pk):
    election = get_object_or_404(Election.objects.select_related("association"), pk=pk)
    positions = election.positions.all().order_by("display_order", "title")
    # Built explicitly (not via position.candidates.all) because Position
    # is shared across elections — that reverse relation would include
    # candidates from every *other* election that ever contested this
    # same position too.
    position_candidates = [
        {"position": position, "candidates": list(election.candidates.filter(position=position))}
        for position in positions
    ]
    return render(
        request,
        "elections/election_detail.html",
        {"election": election, "position_candidates": position_candidates},
    )


# ---------------------------------------------------------------------------
# PART 4: Voting Login
# ---------------------------------------------------------------------------
def voting_login_view(request, pk):
    election = get_object_or_404(Election, pk=pk)

    # Checked before the form is even shown — PART 4's "Reject access if
    # ... Election not active", with a message that distinguishes
    # upcoming from closed rather than one generic "not active" string.
    if not election.is_voting_open:
        if election.is_upcoming():
            message = "Voting has not opened yet for this election."
        elif election.is_closed():
            message = "Voting has closed for this election."
        else:
            message = "Voting is not currently open for this election."
        return render(request, "elections/voting_login.html", {"election": election, "voting_closed_message": message})

    error_message = None
    if request.method == "POST":
        form = VotingLoginForm(request.POST)
        if form.is_valid():
            member, error_message = form.authenticate()
            if member is not None and not is_member_eligible(member, election):
                # Credentials were valid, but the Eligibility Engine says
                # this member isn't in scope for *this* election (wrong
                # institution/faculty/department/level/gender/membership
                # category). Treated as a login failure, same as bad
                # credentials, so the form stays up and nothing about the
                # actual rule is revealed.
                member = None
                error_message = NOT_ELIGIBLE_MESSAGE
            if member is not None:
                if election.has_member_voted(member):
                    # Not an error — they're already done. Send them
                    # straight to the same success page rather than
                    # making them sit through a ballot that would just
                    # fail the uniqueness constraint anyway.
                    return redirect("elections:vote_success", pk=election.pk)
                request.session.cycle_key()  # mitigate session fixation on this privilege boundary
                request.session[_voting_session_key(election)] = member.pk
                return redirect("elections:ballot", pk=election.pk)
    else:
        form = VotingLoginForm()

    return render(
        request,
        "elections/voting_login.html",
        {"election": election, "form": form, "error_message": error_message},
    )


# ---------------------------------------------------------------------------
# PART 5 & 6: Ballot Page / Vote Submission
# ---------------------------------------------------------------------------
def ballot_view(request, pk):
    election = get_object_or_404(Election, pk=pk)
    member = _get_voting_member(request, election)
    if member is None:
        return redirect("elections:voting_login", pk=election.pk)

    # Re-checked on every request (not just at login) — the election
    # could have closed, or this member could have already voted (e.g. in
    # another tab) between logging in and reaching this page.
    if not election.is_voting_open:
        return render(request, "elections/voting_login.html", {
            "election": election,
            "voting_closed_message": "Voting is not currently open for this election.",
        })

    # Election Eligibility Engine (v2.0): re-checked here too, not just at
    # login — belt-and-braces server-side enforcement per "Client-side
    # checks are never sufficient" / "Eligibility must always be verified
    # server-side before voting". Session is cleared so a stale session
    # can't be replayed against the ballot form directly.
    if not is_member_eligible(member, election):
        request.session.pop(_voting_session_key(election), None)
        return render(request, "elections/voting_login.html", {
            "election": election,
            "voting_closed_message": NOT_ELIGIBLE_MESSAGE,
        })
    if election.has_member_voted(member):
        return redirect("elections:vote_success", pk=election.pk)

    BallotForm = build_ballot_form_class(election)
    positions = list(election.positions.all().order_by("display_order", "title"))

    if request.method == "POST":
        form = BallotForm(request.POST)
        if form.is_valid():
            try:
                with transaction.atomic():
                    # One atomic block for the *whole* ballot: if any
                    # single position's vote fails (most likely the
                    # uniqueness constraint catching a concurrent
                    # double-submit), none of this member's votes for
                    # this election are left half-recorded.
                    for position in positions:
                        candidate = form.cleaned_data[f"position_{position.pk}"]
                        vote = Vote(election=election, member=member, candidate=candidate)
                        vote.full_clean()
                        vote.save()
            except IntegrityError:
                # Page-refresh / double-submit / two tabs racing each
                # other — the DB constraint is what actually stopped the
                # second write; this is just turning that into a normal
                # response instead of a 500.
                request.session.pop(_voting_session_key(election), None)
                return redirect("elections:vote_success", pk=election.pk)

            request.session.pop(_voting_session_key(election), None)
            return redirect("elections:vote_success", pk=election.pk)
    else:
        form = BallotForm()

    # Candidates are also passed alongside each field (not just the
    # auto-rendered widget) purely so the template can show manifestos —
    # CandidateChoiceField.label_from_instance only returns the name, and
    # the public-website brief (PART 5) requires manifestos on this page.
    # This is additive context for display only: the field itself, used
    # for validation/cleaned_data below, is completely unchanged.
    ballot_positions = [
        {
            "position": position,
            "field": form[f"position_{position.pk}"],
            "candidates": list(Candidate.objects.filter(election=election, position=position)),
        }
        for position in positions
    ]

    return render(
        request,
        "elections/ballot.html",
        {"election": election, "member": member, "form": form, "ballot_positions": ballot_positions},
    )


def vote_success_view(request, pk):
    election = get_object_or_404(Election, pk=pk)
    return render(request, "elections/vote_success.html", {"election": election})


# ---------------------------------------------------------------------------
# PART 8: Live Public Results
# ---------------------------------------------------------------------------
def results_view(request, pk):
    election = get_object_or_404(Election.objects.select_related("association"), pk=pk)
    voters_count = election.voters_count()
    eligible_voters_count = election.eligible_voters_count()
    return render(
        request,
        "elections/results.html",
        {
            "election": election,
            # Computed fresh on every request — see Election.results_by_position()
            # for why this deliberately doesn't read from a cached snapshot.
            "results": election.results_by_position(),
            "voters_count": voters_count,
            "eligible_voters_count": eligible_voters_count,
            # Reuses the two counts already computed above instead of
            # having turnout_percentage() silently re-run both queries.
            "turnout_percentage": election.turnout_percentage(eligible=eligible_voters_count, voters=voters_count),
        },
    )


# ---------------------------------------------------------------------------
# PART 9: Admin Election Dashboard (staff-only)
# ---------------------------------------------------------------------------
@login_required
@permission_required("elections.manage_election", raise_exception=True)
def admin_dashboard_view(request, pk):
    election = get_object_or_404(Election.objects.select_related("association"), pk=pk)
    voters_count = election.voters_count()
    eligible_voters_count = election.eligible_voters_count()
    return render(
        request,
        "elections/admin_dashboard.html",
        {
            "election": election,
            "results": election.results_by_position(),
            "voters_count": voters_count,
            "eligible_voters_count": eligible_voters_count,
            "turnout_percentage": election.turnout_percentage(eligible=eligible_voters_count, voters=voters_count),
        },
    )
