"""
Custom auth user model.

We don't need extra *fields* yet, but Django strongly recommends starting
every new project with a custom user model because swapping
AUTH_USER_MODEL after the first migration touches every FK to auth.User
in the database. Doing it now costs nothing and buys total freedom later
(e.g. adding 2FA fields, or letting Members log in to a future
self-service portal without a second user table).

Role enforcement itself is NOT done with a field on this model — see
ARCHITECTURE.md "Permission architecture" for the reasoning — it is done
with `django.contrib.auth.models.Group` ("Super Admin", "Registration
Admin", "Election Admin", "Analytics Admin"), seeded by the
`setup_roles` management command in apps/accounts/management/commands/.
"""
from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models

from apps.core.models import Association

# Group names used throughout the project. Defined once here (rather than
# as magic strings scattered across admin.py files) so renaming a role is
# a one-line change.
ROLE_SUPER_ADMIN = "Super Admin"
ROLE_REGISTRATION_ADMIN = "Registration Admin"
ROLE_ELECTION_ADMIN = "Election Admin"
ROLE_ANALYTICS_ADMIN = "Analytics Admin"

ALL_ROLES = [ROLE_SUPER_ADMIN, ROLE_REGISTRATION_ADMIN, ROLE_ELECTION_ADMIN, ROLE_ANALYTICS_ADMIN]


class User(AbstractUser):
    """
    SAMS staff/admin account. Ordinary registrants do NOT need one of
    these to apply for membership (see apps.members.Member), only people
    who administer the system through Django admin (or a future custom
    dashboard) do.
    """

    association = models.ForeignKey(
        Association,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="staff_users",
        help_text=(
            "Scopes a non-superuser admin to a single association. Leave "
            "blank for Super Admins, who are expected to be Django "
            "superusers and therefore see every association."
        ),
    )
    phone_number = models.CharField(max_length=20, blank=True)

    class Meta:
        verbose_name = "Staff User"
        verbose_name_plural = "Staff Users"

    def __str__(self):
        return self.get_full_name() or self.username

    @property
    def role_names(self):
        """Cheap helper for templates/admin checks: ['Registration Admin', ...]."""
        return list(self.groups.values_list("name", flat=True))

    def has_role(self, role_name):
        return self.is_superuser or self.groups.filter(name=role_name).exists()


# ---------------------------------------------------------------------------
# v1.2 Feature 4 & 7: Communication Center + announcement history.
#
# Lives in apps.accounts (not a new app) because config/settings/base.py's
# INSTALLED_APPS is explicitly out of scope for this task — accounts is
# already the project's "staff-only, cross-cutting" app (it's where the
# role-adaptive dashboard hub lives, and it already imports both
# apps.members and apps.analytics), so a staff-only feature that targets
# Members and reuses Analytics-style filtering fits the same shape.
#
# One row per *attempt* to send an announcement (draft, sent, failed, or
# partially sent) — never edited after creation, so the history in Feature
# 7 is a genuine audit trail, not a mutable log a later action could quietly
# rewrite.
# ---------------------------------------------------------------------------
class Announcement(models.Model):
    class RecipientType(models.TextChoices):
        ALL = "all", "All Members"
        APPROVED = "approved", "Approved Members"
        PENDING = "pending", "Pending Members"
        FACULTY = "faculty", "Faculty"
        DEPARTMENT = "department", "Department"
        LEVEL = "level", "Level"
        GENDER = "gender", "Gender"
        SELECTED = "selected", "Selected Members"
        CUSTOM = "custom", "Custom Filter"

    class DeliveryMethod(models.TextChoices):
        EMAIL = "email", "Email"
        SMS = "sms", "SMS (Coming Soon)"
        PUSH = "push", "Push Notification (Coming Soon)"

    class Status(models.TextChoices):
        DRAFT = "draft", "Draft"
        SENT = "sent", "Sent"
        PARTIAL = "partial", "Partially Sent"
        FAILED = "failed", "Failed"

    association = models.ForeignKey(
        Association, on_delete=models.CASCADE, related_name="announcements"
    )
    subject = models.CharField(max_length=255)
    message = models.TextField()
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="announcements",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    recipient_type = models.CharField(max_length=20, choices=RecipientType.choices)
    # Whatever combination of faculty/department/level/gender/approval_status
    # (or a "selected" member id list) produced this announcement's
    # recipients — kept so history (Feature 7) shows exactly who was
    # targeted, not just how many, without needing a separate M2M of
    # thousands of Member rows per announcement.
    recipient_filters = models.JSONField(default=dict, blank=True)

    delivery_method = models.CharField(
        max_length=20, choices=DeliveryMethod.choices, default=DeliveryMethod.EMAIL
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.DRAFT)

    recipient_count = models.PositiveIntegerField(
        default=0, help_text="How many members matched the targeting at send time."
    )
    sent_count = models.PositiveIntegerField(default=0)
    failed_count = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["-created_at"]
        permissions = [
            ("send_announcement", "Can access the Communication Center and send announcements"),
        ]
        verbose_name = "Announcement"
        verbose_name_plural = "Announcements"

    def __str__(self):
        return self.subject
