"""
v1.2 Features 4-10: Communication Center — permissions, targeting,
sending, and history. Kept in its own file so apps/accounts/tests/
test_views.py (the existing dashboard test suite) stays untouched.

Mailjet migration note: ComposeAndSendTests no longer checks
django.core.mail.outbox — member-facing email is delivered through
apps.core.mailjet_service, which is mocked here instead. No test in this
file makes a real HTTPS call to Mailjet.
"""
from unittest.mock import patch

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse

from apps.accounts.models import Announcement, User
from apps.accounts.notifications import PROVIDERS
from apps.core.mailjet_service import MailjetServiceError
from apps.core.models import Association
from apps.members.models import Member
from apps.members.services import resolve_announcement_recipients


def _member(association, **overrides):
    defaults = dict(
        full_name="Test Member",
        phone_number="0800000000",
        nin_number="00000000000",
        date_of_birth="2001-01-01",
        institution="Malam Sidi College",
        course="Computer Science",
        category=Member.Category.UNDERGRADUATE,
        passport_photo="members/passports/x.jpg",
        faculty="Science",
        department="Computer Science",
        level="400",
        gender=Member.Gender.FEMALE,
        email="member@example.com",
    )
    defaults.update(overrides)
    return Member.objects.create(association=association, **defaults)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class CommunicationCenterPermissionTests(TestCase):
    """Feature 10: only authorized administrators may access the Communication Center."""

    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.super_admin = User.objects.create_user(username="root", password="x", is_staff=True)
        cls.super_admin.groups.add(Group.objects.get(name="Super Admin"))

        cls.analytics_admin = User.objects.create_user(username="ana", password="x", is_staff=True)
        cls.analytics_admin.groups.add(Group.objects.get(name="Analytics Admin"))

        cls.registration_admin = User.objects.create_user(username="reg", password="x", is_staff=True)
        cls.registration_admin.groups.add(Group.objects.get(name="Registration Admin"))

    def test_anonymous_redirected(self):
        response = self.client.get(reverse("accounts:communication_center"))
        self.assertEqual(response.status_code, 302)

    def test_super_admin_can_access(self):
        self.client.login(username="root", password="x")
        response = self.client.get(reverse("accounts:communication_center"))
        self.assertEqual(response.status_code, 200)

    def test_analytics_admin_without_the_new_permission_gets_403(self):
        self.client.login(username="ana", password="x")
        response = self.client.get(reverse("accounts:communication_center"))
        self.assertEqual(response.status_code, 403)

    def test_registration_admin_without_the_new_permission_gets_403(self):
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("accounts:communication_center"))
        self.assertEqual(response.status_code, 403)

    def test_compose_and_history_and_detail_are_all_gated_too(self):
        self.client.login(username="ana", password="x")
        for url in [
            reverse("accounts:communication_compose"),
            reverse("accounts:communication_history"),
        ]:
            self.assertEqual(self.client.get(url).status_code, 403)


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class RecipientResolutionTests(TestCase):
    """
    Feature 6: targeting reuses apps.members.services.filter_members() —
    tested directly here since it's the shared implementation behind both
    the analytics dashboard and the Communication Center.
    """

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.approved = _member(
            cls.association, full_name="Approved One", phone_number="0801111111", nin_number="11111111111"
        )
        cls.approved.approval_status = Member.ApprovalStatus.APPROVED
        cls.approved.save()

        cls.pending = _member(
            cls.association, full_name="Pending One", phone_number="0802222222", nin_number="22222222222"
        )

    def test_all_returns_every_member(self):
        recipients = resolve_announcement_recipients(self.association, "all")
        self.assertEqual(recipients.count(), 2)

    def test_approved_only(self):
        recipients = resolve_announcement_recipients(self.association, "approved")
        self.assertCountEqual(list(recipients), [self.approved])

    def test_pending_only(self):
        recipients = resolve_announcement_recipients(self.association, "pending")
        self.assertCountEqual(list(recipients), [self.pending])

    def test_selected_uses_explicit_ids_regardless_of_status(self):
        recipients = resolve_announcement_recipients(
            self.association, "selected", selected_ids=[self.pending.pk]
        )
        self.assertCountEqual(list(recipients), [self.pending])

    def test_custom_combines_filters(self):
        recipients = resolve_announcement_recipients(
            self.association, "custom", filters={"approval_status": "approved", "faculty": "Science"}
        )
        self.assertCountEqual(list(recipients), [self.approved])


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class ComposeAndSendTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.member_a = _member(
            cls.association, full_name="Member A", phone_number="0801111111", nin_number="11111111111",
            email="a@example.com",
        )
        cls.member_b = _member(
            cls.association, full_name="Member B", phone_number="0802222222", nin_number="22222222222",
            email="",  # no email on file
        )
        cls.super_admin = User.objects.create_user(username="root", password="x", is_staff=True)
        cls.super_admin.groups.add(Group.objects.get(name="Super Admin"))

    def setUp(self):
        self.client.login(username="root", password="x")

    def test_preview_does_not_create_an_announcement_or_send_mail(self):
        with patch("apps.accounts.notifications.mailjet_service.send_email") as mock_send:
            response = self.client.post(
                reverse("accounts:communication_compose"),
                {
                    "action": "preview",
                    "subject": "Hello",
                    "message": "Body",
                    "recipient_type": Announcement.RecipientType.ALL,
                    "delivery_method": Announcement.DeliveryMethod.EMAIL,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Announcement.objects.count(), 0)
        mock_send.assert_not_called()
        self.assertEqual(response.context["preview"]["count"], 2)

    def test_send_creates_announcement_and_sends_only_to_members_with_email(self):
        # member_b has no email — EmailProvider skips it before ever calling
        # mailjet_service, so simulating a real API failure isn't needed to
        # reproduce the same "1 sent, 1 failed" outcome as before.
        with patch("apps.accounts.notifications.mailjet_service.send_email") as mock_send:
            response = self.client.post(
                reverse("accounts:communication_compose"),
                {
                    "action": "send",
                    "subject": "Welcome",
                    "message": "Hello everyone",
                    "recipient_type": Announcement.RecipientType.ALL,
                    "delivery_method": Announcement.DeliveryMethod.EMAIL,
                },
            )
        self.assertEqual(response.status_code, 302)

        announcement = Announcement.objects.get()
        self.assertEqual(announcement.subject, "Welcome")
        self.assertEqual(announcement.recipient_count, 2)
        self.assertEqual(announcement.sent_count, 1)
        self.assertEqual(announcement.failed_count, 1)
        self.assertEqual(announcement.status, Announcement.Status.PARTIAL)
        self.assertEqual(announcement.created_by, self.super_admin)

        mock_send.assert_called_once()
        self.assertEqual(mock_send.call_args.kwargs["to_email"], "a@example.com")
        self.assertEqual(mock_send.call_args.kwargs["subject"], "Welcome")

    def test_one_failed_mailjet_delivery_does_not_stop_the_batch(self):
        """A Mailjet API failure for one recipient must not abort the rest."""
        member_c = _member(
            self.association, full_name="Member C", phone_number="0803333333", nin_number="33333333333",
            email="c@example.com",
        )
        with patch(
            "apps.accounts.notifications.mailjet_service.send_email",
            side_effect=MailjetServiceError("Mailjet API request failed: ConnectionError"),
        ) as mock_send:
            response = self.client.post(
                reverse("accounts:communication_compose"),
                {
                    "action": "send",
                    "subject": "Welcome",
                    "message": "Hello everyone",
                    "recipient_type": Announcement.RecipientType.ALL,
                    "delivery_method": Announcement.DeliveryMethod.EMAIL,
                },
            )
        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get()
        # member_a and member_c both have email (2 API calls attempted, both
        # fail); member_b has no email (skipped before any API call).
        self.assertEqual(mock_send.call_count, 2)
        self.assertEqual(announcement.sent_count, 0)
        self.assertEqual(announcement.failed_count, 2)
        self.assertEqual(announcement.status, Announcement.Status.FAILED)

    def test_sms_delivery_method_is_rejected_by_form_validation(self):
        with patch("apps.accounts.notifications.mailjet_service.send_email") as mock_send:
            response = self.client.post(
                reverse("accounts:communication_compose"),
                {
                    "action": "send",
                    "subject": "Welcome",
                    "message": "Hello",
                    "recipient_type": Announcement.RecipientType.ALL,
                    "delivery_method": Announcement.DeliveryMethod.SMS,
                },
            )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Announcement.objects.count(), 0)
        mock_send.assert_not_called()

    def test_selected_recipient_type_without_any_ids_is_rejected(self):
        response = self.client.post(
            reverse("accounts:communication_compose"),
            {
                "action": "send",
                "subject": "Welcome",
                "message": "Hello",
                "recipient_type": Announcement.RecipientType.SELECTED,
                "delivery_method": Announcement.DeliveryMethod.EMAIL,
                "selected_member_ids": "",
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Announcement.objects.count(), 0)

    def test_selected_recipient_type_sends_only_to_chosen_members(self):
        with patch("apps.accounts.notifications.mailjet_service.send_email") as mock_send:
            response = self.client.post(
                reverse("accounts:communication_compose"),
                {
                    "action": "send",
                    "subject": "Just You",
                    "message": "Hi",
                    "recipient_type": Announcement.RecipientType.SELECTED,
                    "delivery_method": Announcement.DeliveryMethod.EMAIL,
                    "selected_member_ids": str(self.member_a.pk),
                },
            )
        self.assertEqual(response.status_code, 302)
        announcement = Announcement.objects.get()
        self.assertEqual(announcement.recipient_count, 1)
        self.assertEqual(announcement.sent_count, 1)
        self.assertEqual(mock_send.call_args.kwargs["to_email"], "a@example.com")


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class HistoryAndDetailTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.super_admin = User.objects.create_user(username="root", password="x", is_staff=True)
        cls.super_admin.groups.add(Group.objects.get(name="Super Admin"))
        cls.announcement = Announcement.objects.create(
            association=cls.association,
            subject="Past Announcement",
            message="Body text",
            created_by=cls.super_admin,
            recipient_type=Announcement.RecipientType.ALL,
            delivery_method=Announcement.DeliveryMethod.EMAIL,
            status=Announcement.Status.SENT,
            recipient_count=3,
            sent_count=3,
        )

    def test_history_lists_the_announcement(self):
        self.client.login(username="root", password="x")
        response = self.client.get(reverse("accounts:communication_history"))
        self.assertContains(response, "Past Announcement")

    def test_detail_shows_counts(self):
        self.client.login(username="root", password="x")
        response = self.client.get(reverse("accounts:communication_detail", args=[self.announcement.pk]))
        self.assertContains(response, "Past Announcement")
        self.assertContains(response, "Body text")

    def test_announcement_created_by_deletion_keeps_the_history_row(self):
        """created_by=SET_NULL: deleting a staff account must not delete announcement history."""
        self.super_admin.delete()
        self.announcement.refresh_from_db()
        self.assertIsNone(self.announcement.created_by)


class NotificationProviderTests(TestCase):
    """Feature 8: only Email is enabled; SMS/Push are visible-but-disabled placeholders."""

    def test_only_email_provider_is_enabled(self):
        enabled = [key for key, provider in PROVIDERS.items() if provider.enabled]
        self.assertEqual(enabled, ["email"])

    def test_sms_and_push_providers_raise_if_ever_called_directly(self):
        with self.assertRaises(NotImplementedError):
            PROVIDERS["sms"].send(member=None, subject="x", message="y")
        with self.assertRaises(NotImplementedError):
            PROVIDERS["push"].send(member=None, subject="x", message="y")
