"""
Forms for the public-facing member registration module.

Two forms, two different jobs:
  - MemberRegistrationForm: collects Member fields + a receipt upload,
    does duplicate detection with the exact wording the spec calls for,
    and creates both the Member and its first RegistrationApplication
    together.
  - StatusCheckForm: a plain (non-model) form for the public status
    lookup, supporting either an application number or a NIN+phone pair.
"""
from django import forms
from django.core.exceptions import ValidationError
from django.db import transaction

from .courses import COURSE_CHOICES, OTHER_COURSE_VALUE
from .institutions import INSTITUTION_CHOICES, OTHER_INSTITUTION_VALUE
from .models import Member, RegistrationApplication
from .services import BY_MEMBERSHIP_ID, BY_NIN, CREDENTIAL_METHOD_CHOICES, find_member_by_credentials
from .validators import validate_image_size


class MemberRegistrationForm(forms.ModelForm):
    # Not a Member field — belongs to RegistrationApplication — so it's
    # declared here rather than via Meta.fields, and handled explicitly
    # in save() below.
    receipt_image = forms.ImageField(
        required=True,
        validators=[validate_image_size],
        help_text="Upload your payment receipt (image, max 5 MB).",
    )

    # Member.gender is blank=True on the model (see models.py — added for
    # the Membership Card System, optional because no registration flow
    # collected it yet and every pre-existing Member has it empty). That
    # same optionality is the business rule here: registrants may decline
    # to answer, exactly like apps.accounts.forms's Communication Center
    # targeting field treats this identical choice set. Declared
    # explicitly (rather than left to ModelForm auto-generation) only to
    # match that field's "---" blank-option label instead of Django's
    # default "---------", for a consistent placeholder across the app;
    # the choices themselves still come from Member.Gender, not a
    # hardcoded list.
    gender = forms.ChoiceField(
        choices=[("", "---")] + list(Member.Gender.choices),
        required=False,
    )

    # Institution is presented as a searchable dropdown seeded from
    # institutions.py (Gombe State institutions first, then well-known
    # national universities), with an "Other" option at the end. Declared
    # explicitly for the same reason gender is above: choices come from a
    # module constant rather than Django's ModelForm auto-generation
    # (which would otherwise just render a plain <input type="text">
    # for a CharField). Member.institution itself is untouched -- still
    # a plain CharField -- so this is presentation-only; see clean()
    # below for how the final string is resolved.
    institution = forms.ChoiceField(
        choices=INSTITUTION_CHOICES,
        required=True,
        error_messages={"invalid_choice": "Select an institution from the list, or choose Other."},
    )
    # Not a Member field (like receipt_image above) -- only used when
    # institution == "other". Required=False at the field level because
    # its actual requiredness is conditional; enforced explicitly in
    # clean() instead.
    institution_other = forms.CharField(
        required=False,
        max_length=255,
        label="Type your institution",
    )

    # Course is presented the same way institution is above: a grouped
    # dropdown seeded from courses.py, with an "Other" option at the end.
    # Declared explicitly (same reasoning as institution) so Member.course
    # -- still a plain CharField -- gets a real choice widget instead of
    # ModelForm's default plain text input; see clean() below for how the
    # final string is resolved.
    course = forms.ChoiceField(
        choices=COURSE_CHOICES,
        required=True,
        error_messages={"invalid_choice": "Select a course from the list, or choose Other."},
    )
    # Not a Member field (like institution_other above) -- only used when
    # course == "other". Required=False at the field level; enforced
    # explicitly in clean() instead.
    course_other = forms.CharField(
        required=False,
        max_length=255,
        label="Type your course",
    )

    # Not a Member/RegistrationApplication field until save() -- an image
    # used only by staff to verify the applicant's indigene status before
    # approval (see RegistrationApplication.indigene_image and its
    # clear_indigene_image() lifecycle in models.py). Required at
    # registration the same way receipt_image is.
    indigene_image = forms.ImageField(
        required=True,
        validators=[validate_image_size],
        help_text=(
            "Upload an image that can be used to verify your indigene status "
            "(e.g. a Certificate of Origin or similar document, max 5 MB). "
            "Only association administrators can view this, and it is deleted "
            "automatically once your application is approved."
        ),
    )

    class Meta:
        model = Member
        fields = [
            "full_name",
            "phone_number",
            "nin_number",
            "date_of_birth",
            "gender",
            "email",
            "institution",
            "course",
            "faculty",
            "department",
            "level",
            "category",
            "passport_photo",
        ]
        widgets = {
            "date_of_birth": forms.DateInput(attrs={"type": "date"}),
        }

    # Explicit so the Payment Receipt field renders last, after the
    # Member fields, exactly matching the PART 1 field order — Django
    # would otherwise put class-declared fields like receipt_image
    # *before* the Meta-derived ones.
    # v1.1: email added after date_of_birth (personal info step);
    # faculty/department/level added inside the academic step.
    # v1.2: gender added after date_of_birth (personal info step),
    # alongside the other Member.gender consumers (admin, staff list,
    # analytics, election eligibility) — see forms.py class comment above.
    # v1.3: course_other placed right after course (matching
    # institution/institution_other), indigene_image placed right after
    # receipt_image (both are uploads reviewed by staff before approval).
    field_order = [
        "full_name", "phone_number", "nin_number", "date_of_birth", "gender", "email",
        "institution", "institution_other", "course", "course_other", "faculty", "department", "level",
        "category", "passport_photo", "receipt_image", "indigene_image",
    ]

    def validate_unique(self):
        # Deliberately a no-op: PART 2 of the spec calls for specific,
        # combination-aware messages ("Phone Number Already Registered.",
        # "NIN Number Already Registered.", "Membership Record Already
        # Exists.") rather than Django's generic per-field "Member with
        # this phone number already exists." Those exact messages are
        # produced in clean() below instead.
        pass

    def clean(self):
        cleaned_data = super().clean()

        # Resolve the institution dropdown's "Other" sentinel into the
        # actual string Member.institution will store. Must happen here
        # (form-level clean, before ModelForm._post_clean() calls
        # construct_instance()) so the resolved value -- not the "other"
        # sentinel -- is what ends up on the model instance. See
        # institutions.py for why "other" can never collide with a real
        # institution name.
        institution = cleaned_data.get("institution")
        if institution == OTHER_INSTITUTION_VALUE:
            typed_institution = (cleaned_data.get("institution_other") or "").strip()
            if not typed_institution:
                self.add_error("institution_other", "Please type your institution.")
            else:
                cleaned_data["institution"] = typed_institution

        # Same "Other" resolution as institution above, for course ->
        # Member.course. Must also happen here, before ModelForm's
        # construct_instance() runs.
        course = cleaned_data.get("course")
        if course == OTHER_COURSE_VALUE:
            typed_course = (cleaned_data.get("course_other") or "").strip()
            if not typed_course:
                self.add_error("course_other", "Please type your course.")
            else:
                cleaned_data["course"] = typed_course

        phone = cleaned_data.get("phone_number")
        nin = cleaned_data.get("nin_number")

        # Both fields must already be individually valid (11-digit format,
        # phone prefix, etc. — enforced by the model field validators via
        # ModelForm's automatic full_clean()) before a duplicate check is
        # meaningful; if either failed its own field validation, skip.
        if phone and nin:
            phone_exists = Member.objects.filter(phone_number=phone).exists()
            nin_exists = Member.objects.filter(nin_number=nin).exists()

            if phone_exists or nin_exists:
                # PART 7: flips on the "you already have a record, go check
                # your status" recovery panel in the template regardless of
                # which specific case below applies.
                self.duplicate_detected = True

            if phone_exists and nin_exists:
                raise ValidationError("Membership Record Already Exists.", code="duplicate_both")
            if phone_exists:
                raise ValidationError("Phone Number Already Registered.", code="duplicate_phone")
            if nin_exists:
                raise ValidationError("NIN Number Already Registered.", code="duplicate_nin")

        return cleaned_data

    @transaction.atomic
    def save(self, association):
        """
        Creates the Member and its first RegistrationApplication
        together. `association` is passed in explicitly (rather than
        being a form field) because it's resolved by the view from the
        deployment's tenant context, never chosen by the registrant.
        """
        member = super().save(commit=False)
        member.association = association
        member.save()
        application = RegistrationApplication.objects.create(
            member=member,
            receipt_image=self.cleaned_data["receipt_image"],
            indigene_image=self.cleaned_data["indigene_image"],
        )
        return application


class StatusCheckForm(forms.Form):
    """
    Powers PART 4's "Check Registration Status" page: search either by
    application number alone, or by NIN + phone number together (both
    must match the same Member — neither alone is treated as sufficient
    identification for someone else's record).
    """

    BY_APPLICATION_NUMBER = "application_number"
    BY_NIN_PHONE = "nin_phone"
    SEARCH_CHOICES = [
        (BY_APPLICATION_NUMBER, "Application Number"),
        (BY_NIN_PHONE, "NIN + Phone Number"),
    ]

    search_by = forms.ChoiceField(
        choices=SEARCH_CHOICES,
        widget=forms.RadioSelect,
        initial=BY_APPLICATION_NUMBER,
    )
    application_number = forms.CharField(required=False, max_length=30)
    nin_number = forms.CharField(required=False, max_length=11)
    phone_number = forms.CharField(required=False, max_length=11)

    def clean(self):
        cleaned_data = super().clean()
        mode = cleaned_data.get("search_by")

        if mode == self.BY_APPLICATION_NUMBER:
            if not cleaned_data.get("application_number", "").strip():
                raise ValidationError("Please enter your application number.")
        elif mode == self.BY_NIN_PHONE:
            if not cleaned_data.get("nin_number", "").strip() or not cleaned_data.get("phone_number", "").strip():
                raise ValidationError("Please enter both your NIN and phone number.")

        return cleaned_data

    def lookup(self):
        """Returns the matching RegistrationApplication, or None if nothing matches."""
        mode = self.cleaned_data["search_by"]

        if mode == self.BY_APPLICATION_NUMBER:
            number = self.cleaned_data["application_number"].strip()
            return (
                RegistrationApplication.objects.filter(application_number=number)
                .select_related("member")
                .first()
            )

        # BY_NIN_PHONE: both must match the same Member record.
        nin = self.cleaned_data["nin_number"].strip()
        phone = self.cleaned_data["phone_number"].strip()
        member = Member.objects.filter(nin_number=nin, phone_number=phone).first()
        if not member:
            return None
        # Most recent application — relevant after a rejection + reapply,
        # where the latest decision is the one the registrant cares about.
        return member.applications.order_by("-submitted_at").first()


class PortalLoginForm(forms.Form):
    """
    Stage 8: Member Self-Service Portal login.

    Verifies identity the exact same way apps.elections.forms.VotingLoginForm
    does — (Membership ID + Phone) or (NIN + Phone) — via the shared
    apps.members.services.find_member_by_credentials lookup, so this
    doesn't re-implement that query. The one thing that's genuinely
    different from voting login is eligibility: the portal only requires
    the member to be Approved, not also voting_status-eligible (a
    narrower, elections-specific concept), and the brief calls for its
    own two distinct messages here rather than voting login's single
    generic one — so authenticate() returns an error *code*, not text,
    and lets the view own the actual copy.
    """

    NOT_FOUND = "not_found"
    NOT_APPROVED = "not_approved"

    method = forms.ChoiceField(
        choices=CREDENTIAL_METHOD_CHOICES, widget=forms.RadioSelect, initial=BY_MEMBERSHIP_ID
    )
    membership_id = forms.CharField(required=False, max_length=30)
    nin_number = forms.CharField(required=False, max_length=11)
    phone_number = forms.CharField(required=False, max_length=11)

    def clean(self):
        cleaned_data = super().clean()
        method = cleaned_data.get("method")

        if method == BY_MEMBERSHIP_ID:
            if not cleaned_data.get("membership_id", "").strip() or not cleaned_data.get("phone_number", "").strip():
                raise ValidationError("Please enter your Membership ID and phone number.")
        elif method == BY_NIN:
            if not cleaned_data.get("nin_number", "").strip() or not cleaned_data.get("phone_number", "").strip():
                raise ValidationError("Please enter your NIN and phone number.")

        return cleaned_data

    def authenticate(self):
        """Returns (member, error_code). error_code is None on success."""
        method = self.cleaned_data["method"]
        identifier_field = "membership_id" if method == BY_MEMBERSHIP_ID else "nin_number"
        member = find_member_by_credentials(
            method,
            self.cleaned_data.get(identifier_field, ""),
            self.cleaned_data.get("phone_number", ""),
        )

        if member is None:
            return None, self.NOT_FOUND
        if member.approval_status != Member.ApprovalStatus.APPROVED:
            return None, self.NOT_APPROVED

        return member, None
