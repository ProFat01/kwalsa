"""
apps.members owns the membership lifecycle: a person submits a
RegistrationApplication, an admin reviews it, and on approval a Member
record becomes "active" (gets a membership_id, becomes voting_status
eligible). Later, an active Member can be converted to alumni, which
attaches an AlumniRecord without ever deleting their membership history.

Why Member and RegistrationApplication are two separate models rather
than one: a single application can be rejected and resubmitted, and we
want the full review history (who rejected what, and why) without
overwriting it on resubmission. `RegistrationApplication.member` is a
plain ForeignKey (not OneToOne) specifically so re-application keeps a
trail — see ARCHITECTURE.md "Relationships".
"""
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.core.models import Association

from .utils import generate_application_number, generate_membership_id
from .validators import nin_validator, phone_number_validator, validate_image_size


class Member(models.Model):
    class Category(models.TextChoices):
        UNDERGRADUATE = "undergraduate", "Undergraduate"
        GRADUATE_ALUMNI = "graduate_alumni", "Graduate/Alumni"

    class ApprovalStatus(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    association = models.ForeignKey(
        Association, on_delete=models.PROTECT, related_name="members"
    )
    # Optional and nullable on purpose: most members will never need to log
    # in (registration/approval is currently admin-mediated), but linking a
    # future self-service account just means setting this FK — no schema
    # change required when that portal is built.
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="member_profile",
    )

    full_name = models.CharField(max_length=255)
    phone_number = models.CharField(
        max_length=11, unique=True, validators=[phone_number_validator]
    )
    nin_number = models.CharField(
        max_length=11, unique=True, validators=[nin_validator]
    )
    date_of_birth = models.DateField()
    institution = models.CharField(max_length=255)
    course = models.CharField(max_length=255)
    category = models.CharField(max_length=20, choices=Category.choices)

    class Gender(models.TextChoices):
        MALE = "male", "Male"
        FEMALE = "female", "Female"

    # Optional, added for Membership Card System v1 (see MembershipCard
    # below). Blank on purpose: no existing registration flow collects
    # these, so every pre-existing Member has them empty until an admin
    # fills them in via the admin form — the card template renders each
    # one only "if available", exactly like registration_number already
    # does for membership_id.
    gender = models.CharField(max_length=10, choices=Gender.choices, blank=True)
    faculty = models.CharField(max_length=255, blank=True)
    department = models.CharField(max_length=255, blank=True)
    level = models.CharField(max_length=20, blank=True, help_text="e.g. '100', 'ND1', 'Year 3'.")
    passport_photo = models.ImageField(
        upload_to="members/passports/%Y/%m/", validators=[validate_image_size]
    )

    # v1.1 addition: optional email for approval notifications.
    # blank=True (no null=True) — EmailField stores empty string for "not
    # provided", consistent with Django's convention for text fields and
    # avoids two falsy states (None vs "") for the same concept.
    email = models.EmailField(
        blank=True,
        help_text="Optional. Used to send the welcome email when your application is approved.",
    )

    # Intentionally blank/null: only assigned once an application is
    # approved (see members/signals.py), never at registration time.
    membership_id = models.CharField(
        max_length=30, unique=True, blank=True, null=True, editable=False
    )
    registration_date = models.DateTimeField(auto_now_add=True)
    approval_status = models.CharField(
        max_length=10, choices=ApprovalStatus.choices, default=ApprovalStatus.PENDING
    )

    # Eligibility flag, not a vote record — actual votes live in
    # elections.Vote. Auto-flipped to True on approval and False if a
    # member is later rejected/suspended, so election-time eligibility
    # checks are a single indexed boolean lookup instead of a recomputation.
    voting_status = models.BooleanField(
        default=False,
        verbose_name="Eligible to vote",
        help_text="Auto-managed: set True when approval_status becomes Approved.",
    )
    alumni_status = models.BooleanField(default=False, verbose_name="Is alumni")

    class Meta:
        ordering = ["-registration_date"]
        indexes = [
            models.Index(fields=["association", "approval_status"]),
            models.Index(fields=["association", "alumni_status"]),
            models.Index(fields=["association", "category"]),
            # Backs apps.analytics.querysets.registration_counts_by_period()
            # (the Registration Growth dashboard/API): that query GROUPs BY
            # a truncated registration_date per association. Without this,
            # SQLite has nowhere to read rows already sorted by
            # registration_date within an association, so it falls back to
            # "USE TEMP B-TREE FOR GROUP BY" (confirmed via EXPLAIN QUERY
            # PLAN during the v2.0 load-testing pass) — a full sort of every
            # member row on every request. With the index, SQLite can walk
            # rows in registration_date order per association and group them
            # in a single pass instead. Read-only addition: no existing
            # query's results change, only how this one gets its rows.
            models.Index(fields=["association", "registration_date"]),
        ]
        permissions = [
            ("approve_member", "Can approve or reject a member's registration"),
            ("manage_alumni_status", "Can convert a member to alumni status"),
        ]
        verbose_name = "Member"
        verbose_name_plural = "Members"

    def __str__(self):
        return f"{self.full_name} ({self.membership_id or 'unapproved'})"

    def save(self, *args, **kwargs):
        """
        v1.2.1 bug fix (root cause, not a patch): "Approved" is a promise
        this model makes about itself — a membership_id, and voting
        eligibility. Before this fix, that promise was only kept as a
        *side effect* of members/signals.py reacting to a
        RegistrationApplication transitioning to Approved. Any other way
        approval_status could become "approved" (directly editing a
        Member in the admin — approval_status was never made read-only
        there — a future API, a script, a data fix) silently produced an
        Approved member with no membership_id and voting_status still
        False, because nothing was watching THIS model.

        Fixing it here instead means the invariant holds no matter which
        door someone comes through, and is self-healing: any save of an
        Approved member (including one that pre-dates this fix, sitting
        in production right now with a missing membership_id) repairs
        itself the moment it's next saved — no migration, no manual SQL.

        membership_id: healed unconditionally whenever it's missing on
        an Approved member. There's no legitimate reason for that
        combination to ever exist, so it's always safe to fix.

        voting_status: healed to True whenever it's False on an Approved
        member — EXCEPT when this specific save is a targeted
        voting_status-only write that does NOT also touch
        approval_status (`update_fields` contains "voting_status" but
        not "approval_status"). That one case is deliberate voting
        *suspension* of an otherwise-fine member — a real, pre-existing,
        tested feature (see
        elections/tests/test_voting_access.py::test_member_with_voting_status_revoked_rejected,
        "PART 4's 'Not suspended'") — and auto-healing must not silently
        overwrite an admin's intentional decision. Every other save
        (a fresh approval, a full form save, a script) still self-heals.

        Idempotent by construction: membership_id is only ever generated
        when missing, so re-saving an already-consistent Approved member
        is a no-op here, and uniqueness is guaranteed by the same
        select_for_update-guarded SequenceCounter every membership_id has
        always gone through (see core/utils.py:get_next_sequence) —
        concurrent approvals still serialise to distinct numbers, never
        a collision.
        """
        healed_fields = []
        update_fields = kwargs.get("update_fields")

        if self.approval_status == self.ApprovalStatus.APPROVED:
            if not self.membership_id:
                self.membership_id = generate_membership_id(self.association)
                healed_fields.append("membership_id")

            is_targeted_suspension_edit = (
                update_fields is not None
                and "voting_status" in update_fields
                and "approval_status" not in update_fields
            )
            if not self.voting_status and not is_targeted_suspension_edit:
                self.voting_status = True
                healed_fields.append("voting_status")

        # A caller may have restricted the write with update_fields (as
        # members/signals.py does) — if healing touched a field that
        # wasn't already in that list, it has to be added, or the healed
        # value would stay correct only in memory and never reach the
        # database.
        if healed_fields and update_fields is not None:
            kwargs["update_fields"] = set(update_fields) | set(healed_fields)

        super().save(*args, **kwargs)

    def convert_to_alumni(self, graduation_year=None, converted_by=None, **extra_fields):
        """
        Idempotent alumni conversion. Returns the (possibly pre-existing)
        AlumniRecord. Does not change approval_status or voting_status —
        an alumnus can remain an eligible, approved member; alumni_status
        tracks life stage, not membership standing.
        """
        self.alumni_status = True
        self.category = self.Category.GRADUATE_ALUMNI
        self.save(update_fields=["alumni_status", "category"])
        record, _ = AlumniRecord.objects.update_or_create(
            member=self,
            defaults={
                "graduation_year": graduation_year,
                "converted_by": converted_by,
                **extra_fields,
            },
        )
        return record


class RegistrationApplication(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        APPROVED = "approved", "Approved"
        REJECTED = "rejected", "Rejected"

    application_number = models.CharField(max_length=30, unique=True, editable=False)
    member = models.ForeignKey(
        Member,
        on_delete=models.CASCADE,
        related_name="applications",
        help_text="Plain FK (not one-to-one) so a rejected member can reapply without losing history.",
    )
    # Nullable: deliberately deletable post-review (see clear_receipt below)
    # to avoid keeping payment-proof images around indefinitely once a
    # decision has been recorded.
    receipt_image = models.ImageField(
        upload_to="members/receipts/%Y/%m/",
        validators=[validate_image_size],
        null=True,
        blank=True,
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    rejection_reason = models.TextField(blank=True)
    submitted_at = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_applications",
    )

    class Meta:
        ordering = ["-submitted_at"]
        permissions = [
            ("review_application", "Can approve or reject a registration application"),
        ]
        verbose_name = "Registration Application"
        verbose_name_plural = "Registration Applications"

    def __str__(self):
        return self.application_number

    def clean(self):
        if self.status == self.Status.REJECTED and not self.rejection_reason.strip():
            raise ValidationError(
                {"rejection_reason": "A rejection reason is required when rejecting an application."}
            )

    def save(self, *args, **kwargs):
        if not self.application_number:
            self.application_number = generate_application_number(self.member.association)
        super().save(*args, **kwargs)

    def clear_receipt(self):
        """
        Deletes the stored receipt file and clears the field, keeping the
        rest of the application record (and its audit trail) intact. Not
        called automatically on review — wire this up later to a
        scheduled cleanup task once a retention window is decided, rather
        than deleting proof-of-payment the instant a decision is made.
        """
        if self.receipt_image:
            self.receipt_image.delete(save=False)
            self.receipt_image = None
            self.save(update_fields=["receipt_image"])


class AlumniRecord(models.Model):
    """
    Extra detail attached only once a Member is converted to alumni.
    Kept as its own table (rather than extra columns on Member that sit
    NULL for every undergraduate) since this data is optional, grows over
    time (could gain employment history, donations, etc.), and is queried
    far less often than core Member fields.
    """

    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name="alumni_record")
    graduation_year = models.PositiveSmallIntegerField(null=True, blank=True)
    current_employer = models.CharField(max_length=255, blank=True)
    current_role = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)
    converted_at = models.DateTimeField(auto_now_add=True)
    converted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="alumni_conversions",
    )

    class Meta:
        verbose_name = "Alumni Record"
        verbose_name_plural = "Alumni Records"

    def __str__(self):
        return f"Alumni record — {self.member.full_name}"


class MembershipCard(models.Model):
    """
    Membership Card System v1. One row per Member, created lazily
    (`MembershipCard.get_or_create_for(member)`) the first time a card is
    viewed, printed, or its QR is generated — not via a signal on
    approval, so this stays entirely additive and never touches
    members/signals.py or the approval workflow it already owns.

    `card_uuid` — never `membership_id` — is what the QR code encodes and
    what the public verification page looks up by. `membership_id` is
    sequential (see SequenceCounter in core) and therefore guessable;
    a UUID4 default here is the "avoid predictable IDs / prevent
    enumeration" requirement enforced at the schema level, the same way
    `Vote`'s UniqueConstraint enforces one-vote-per-position at the
    schema level rather than trusting every call site to check first.
    """

    member = models.OneToOneField(Member, on_delete=models.CASCADE, related_name="membership_card")
    card_uuid = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Membership Card"
        verbose_name_plural = "Membership Cards"

    def __str__(self):
        return f"Card — {self.member.full_name}"

    @classmethod
    def get_or_create_for(cls, member):
        card, _ = cls.objects.get_or_create(member=member)
        return card
