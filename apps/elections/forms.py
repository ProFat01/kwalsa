"""
Forms for the public voting flow.

Two different jobs, same reasoning behind both: Members don't have User
accounts (registration is admin-mediated, not self-service login — see
apps.members), so "logging in to vote" can't use Django's normal auth.
VotingLoginForm verifies identity against Member fields directly, the
same pattern already used by members.forms.StatusCheckForm for the
status-lookup page.
"""
from django import forms
from django.core.exceptions import ValidationError

from apps.members.models import Member
from apps.members.services import find_member_by_credentials

from .models import Candidate


class VotingLoginForm(forms.Form):
    """
    PART 4: verifies a voter via (Membership ID + Phone) or (NIN + Phone),
    then checks they're actually allowed to vote. Deliberately returns one
    generic "couldn't verify your details" message for *any* credential
    mismatch (wrong ID, wrong NIN, wrong phone, or no such member at all)
    rather than confirming which part was wrong — that would let someone
    probe for valid membership IDs/NINs one field at a time.
    """

    BY_MEMBERSHIP_ID = "membership_id"
    BY_NIN = "nin"
    METHOD_CHOICES = [
        (BY_MEMBERSHIP_ID, "Membership ID + Phone Number"),
        (BY_NIN, "NIN + Phone Number"),
    ]

    method = forms.ChoiceField(choices=METHOD_CHOICES, widget=forms.RadioSelect, initial=BY_MEMBERSHIP_ID)
    membership_id = forms.CharField(required=False, max_length=30)
    nin_number = forms.CharField(required=False, max_length=11)
    phone_number = forms.CharField(required=False, max_length=11)

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")

        if method == self.BY_MEMBERSHIP_ID:
            if not cleaned_data.get("membership_id", "").strip() or not cleaned_data.get("phone_number", "").strip():
                raise ValidationError("Please enter your Membership ID and phone number.")
        elif method == self.BY_NIN:
            if not cleaned_data.get("nin_number", "").strip() or not cleaned_data.get("phone_number", "").strip():
                raise ValidationError("Please enter your NIN and phone number.")

        return cleaned_data

    def authenticate(self):
        """
        Returns (member, error_message): on success `member` is a Member
        instance and `error_message` is None; on failure `member` is None
        and `error_message` is the clear, user-facing reason (PART 4:
        "Show clear messages") — distinguishing "no such credentials" from
        "found you, but you're not eligible" since those genuinely call
        for different next steps (try again vs. contact the Registration
        Admin), without revealing anything sharper about why.
        """
        method = self.cleaned_data["method"]
        phone = self.cleaned_data.get("phone_number", "")
        identifier_field = "membership_id" if method == self.BY_MEMBERSHIP_ID else "nin_number"

        member = find_member_by_credentials(
            method,
            self.cleaned_data.get(identifier_field, ""),
            phone,
        )

        if member is None:
            return None, "We couldn't verify your details. Please check your information and try again."

        # PART 4: Approved + Not suspended + Eligible to vote. The latter
        # two both collapse onto voting_status — see Member.voting_status's
        # own docstring in members/models.py, which already documents that
        # it's flipped False for "rejected/suspended" alike. No new Member
        # field needed; this module just reads the eligibility flag that
        # was already designed to mean this.
        if member.approval_status != Member.ApprovalStatus.APPROVED or not member.voting_status:
            return None, "Your membership is not currently approved and eligible to vote. Please contact the Registration Admin."

        return member, None


class CandidateChoiceField(forms.ModelChoiceField):
    """
    Plain forms.ModelChoiceField defaults to Candidate.__str__() for each
    radio option's label, i.e. "Jane Doe — President" — redundant here
    since the ballot already groups options under a "President" heading.
    """

    def label_from_instance(self, obj):
        return obj.name


def build_ballot_form_class(election):
    """
    Returns a Form *class* (not instance) with one required
    ModelChoiceField per position contested in `election`, named
    "position_<position_id>". Built dynamically because the set of
    positions/candidates differs per election — there's no fixed field
    list to declare statically.

    Each field's queryset is scoped to `Candidate.objects.filter(election=
    election, position=position)`, which is what actually defends PART 6's
    "prevent manual form manipulation": if someone tampers with the
    submitted candidate id to point at a candidate from a different
    election, or a different position, ModelChoiceField's own validation
    rejects it as "not a valid choice" before any view code even runs.
    `required=True` on every field is PART 5's "require vote selection for
    every position".
    """
    fields = {}
    for position in election.positions.all().order_by("display_order", "title"):
        field_name = f"position_{position.pk}"
        fields[field_name] = CandidateChoiceField(
            queryset=Candidate.objects.filter(election=election, position=position),
            widget=forms.RadioSelect,
            label=position.title,
            required=True,
            error_messages={"required": f'Please select a candidate for "{position.title}".'},
        )
    return type("BallotForm", (forms.Form,), fields)
