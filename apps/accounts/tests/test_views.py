import datetime

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Association, ContactMessage
from apps.elections.models import Election
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class DashboardTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )

    def _user_in_group(self, username, group_name):
        user = User.objects.create_user(username=username, password="x", is_staff=True)
        user.groups.add(Group.objects.get(name=group_name))
        return user


class DashboardAccessTests(DashboardTestCase):
    """Confirms each role sees exactly its own section(s) — the core of the review request."""

    def test_anonymous_redirected_to_admin_login(self):
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])
        self.assertIn("next=", response["Location"])

    def test_registration_admin_sees_only_registration_section(self):
        self._user_in_group("reg", "Registration Admin")
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "<h2>Registration</h2>")
        self.assertNotContains(response, "<h2>Elections</h2>")
        self.assertNotContains(response, "<h2>Analytics</h2>")
        self.assertNotContains(response, "<h2>Contact Messages</h2>")

    def test_election_admin_sees_only_elections_section(self):
        self._user_in_group("elec", "Election Admin")
        self.client.login(username="elec", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, "<h2>Registration</h2>")
        self.assertContains(response, "<h2>Elections</h2>")
        self.assertNotContains(response, "<h2>Analytics</h2>")
        self.assertNotContains(response, "<h2>Contact Messages</h2>")

    def test_analytics_admin_sees_only_analytics_section(self):
        self._user_in_group("ana", "Analytics Admin")
        self.client.login(username="ana", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertNotContains(response, "<h2>Registration</h2>")
        self.assertNotContains(response, "<h2>Elections</h2>")
        self.assertContains(response, "<h2>Analytics</h2>")
        self.assertNotContains(response, "<h2>Contact Messages</h2>")

    def test_super_admin_sees_every_section(self):
        self._user_in_group("super", "Super Admin")
        self.client.login(username="super", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "<h2>Registration</h2>")
        self.assertContains(response, "<h2>Elections</h2>")
        self.assertContains(response, "<h2>Analytics</h2>")
        self.assertContains(response, "<h2>Contact Messages</h2>")

    def test_django_superuser_without_any_group_sees_every_section(self):
        """has_perm() always returns True for is_superuser=True, regardless of group membership."""
        User.objects.create_superuser(username="root", email="root@example.com", password="x")
        self.client.login(username="root", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "<h2>Registration</h2>")
        self.assertContains(response, "<h2>Elections</h2>")
        self.assertContains(response, "<h2>Analytics</h2>")
        self.assertContains(response, "<h2>Contact Messages</h2>")

    def test_plain_staff_with_no_group_sees_no_access_message(self):
        User.objects.create_user(username="plain", password="x", is_staff=True)
        self.client.login(username="plain", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "doesn't have access")
        self.assertNotContains(response, "<h2>Registration</h2>")


class DashboardContentTests(DashboardTestCase):
    """Confirms each visible section shows real, correctly-linked data — not just an empty shell."""

    def test_registration_section_lists_pending_applications_with_review_link(self):
        member = Member.objects.create(
            association=self.association, full_name="Applicant", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2002-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=member)

        self._user_in_group("reg", "Registration Admin")
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, application.application_number)
        self.assertContains(response, f"/admin/members/registrationapplication/{application.pk}/change/")

    def test_elections_section_lists_elections_with_manage_link(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Live Election",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        self._user_in_group("elec", "Election Admin")
        self.client.login(username="elec", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "Live Election")
        self.assertContains(response, reverse("elections:admin_dashboard", args=[election.pk]))

    def test_contact_section_shows_unread_count_and_recent_messages(self):
        ContactMessage.objects.create(
            association=self.association, name="Aisha", email="a@example.com", subject="Question", message="Hi"
        )
        self._user_in_group("super", "Super Admin")
        self.client.login(username="super", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertContains(response, "Question")
        self.assertContains(response, ">1<")  # unread count

    def test_graceful_when_no_association_configured(self):
        Association.objects.all().delete()
        self._user_in_group("super", "Super Admin")
        self.client.login(username="super", password="x")
        response = self.client.get(reverse("accounts:dashboard"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No association is configured")

    def test_dashboard_nav_link_points_here_for_authenticated_users(self):
        self._user_in_group("reg", "Registration Admin")
        self.client.login(username="reg", password="x")
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, reverse("accounts:dashboard"))
