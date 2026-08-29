import datetime
import json

from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


@override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
class AnalyticsViewsTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        call_command("setup_roles", verbosity=0)
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.member = Member.objects.create(
            association=cls.association, full_name="A Member", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2002-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=cls.member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()

        cls.president = Position.objects.create(association=cls.association, title="President")
        now = timezone.now()
        cls.election = Election.objects.create(
            association=cls.association, name="Test Election",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        cls.election.positions.set([cls.president])
        cls.candidate = Candidate.objects.create(election=cls.election, position=cls.president, name="Candidate A")

    def _login_as_analytics_admin(self):
        user = User.objects.create_user(username="analytics_admin", password="x", is_staff=True)
        user.groups.add(Group.objects.get(name="Analytics Admin"))
        self.client.login(username="analytics_admin", password="x")
        return user

    def _login_as_plain_staff(self):
        User.objects.create_user(username="plainstaff", password="x", is_staff=True)
        self.client.login(username="plainstaff", password="x")


DASHBOARD_URL_NAMES = [
    "analytics:overview",
    "analytics:membership_dashboard",
    "analytics:course_dashboard",
    "analytics:institution_dashboard",
    "analytics:age_dashboard",
    "analytics:election_dashboard_list",
]


class DashboardPermissionTests(AnalyticsViewsTestCase):
    """PART 12: only Analytics Admin / Super Admin may access analytics views."""

    def test_anonymous_redirected_to_admin_login_for_every_dashboard(self):
        for url_name in DASHBOARD_URL_NAMES:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 302)
                self.assertIn("/admin/login/", response["Location"])

    def test_plain_staff_gets_403_for_every_dashboard(self):
        self._login_as_plain_staff()
        for url_name in DASHBOARD_URL_NAMES:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 403)

    def test_analytics_admin_can_access_every_dashboard(self):
        self._login_as_analytics_admin()
        for url_name in DASHBOARD_URL_NAMES:
            with self.subTest(url_name=url_name):
                response = self.client.get(reverse(url_name))
                self.assertEqual(response.status_code, 200)

    def test_superuser_can_access_dashboards_without_being_in_any_group(self):
        User.objects.create_superuser(username="root", email="root@example.com", password="x")
        self.client.login(username="root", password="x")
        response = self.client.get(reverse("analytics:overview"))
        self.assertEqual(response.status_code, 200)

    def test_election_detail_dashboard_permission_gated_too(self):
        url = reverse("analytics:election_dashboard_detail", args=[self.election.pk])
        anon = self.client.get(url)
        self.assertEqual(anon.status_code, 302)

        self._login_as_analytics_admin()
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)


class DashboardContentTests(AnalyticsViewsTestCase):
    def setUp(self):
        self._login_as_analytics_admin()

    def test_overview_shows_membership_and_election_numbers(self):
        response = self.client.get(reverse("analytics:overview"))
        self.assertContains(response, "Total Members")
        self.assertContains(response, "Test Election")

    def test_course_dashboard_respects_order_param(self):
        response = self.client.get(reverse("analytics:course_dashboard"), {"order": "asc"})
        self.assertContains(response, "Chemistry")

    def test_election_detail_shows_results_and_age_participation(self):
        Vote.objects.create(election=self.election, member=self.member, candidate=self.candidate)
        response = self.client.get(reverse("analytics:election_dashboard_detail", args=[self.election.pk]))
        self.assertContains(response, "Candidate A")
        self.assertContains(response, "Participation by Age Group")


class JsonApiTests(AnalyticsViewsTestCase):
    """PART 11: clean JSON, same permission gating as the HTML dashboards."""

    def test_anonymous_gets_redirected_not_json(self):
        response = self.client.get(reverse("analytics:api_membership"))
        self.assertEqual(response.status_code, 302)

    def test_membership_json_shape(self):
        self._login_as_analytics_admin()
        response = self.client.get(reverse("analytics:api_membership"))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/json")
        data = json.loads(response.content)
        self.assertEqual(data["total_members"], 1)
        self.assertEqual(data["total_approved"], 1)

    def test_course_json_includes_order_and_results(self):
        self._login_as_analytics_admin()
        response = self.client.get(reverse("analytics:api_courses"), {"order": "asc"})
        data = json.loads(response.content)
        self.assertEqual(data["order"], "asc")
        self.assertEqual(data["results"][0]["course"], "Chemistry")

    def test_age_distribution_json(self):
        self._login_as_analytics_admin()
        response = self.client.get(reverse("analytics:api_age_distribution"))
        data = json.loads(response.content)
        self.assertEqual(len(data["results"]), 6)

    def test_election_results_json(self):
        self._login_as_analytics_admin()
        Vote.objects.create(election=self.election, member=self.member, candidate=self.candidate)
        response = self.client.get(reverse("analytics:api_election_results", args=[self.election.pk]))
        data = json.loads(response.content)
        self.assertEqual(data["results"][0]["position"], "President")
        self.assertEqual(data["results"][0]["winner"], "Candidate A")

    def test_election_turnout_json(self):
        self._login_as_analytics_admin()
        Vote.objects.create(election=self.election, member=self.member, candidate=self.candidate)
        response = self.client.get(reverse("analytics:api_election_turnout", args=[self.election.pk]))
        data = json.loads(response.content)
        self.assertEqual(data["eligible_voters"], 1)
        self.assertEqual(data["votes_cast"], 1)
        self.assertEqual(data["turnout_percentage"], 100.0)

    def test_registration_growth_json(self):
        self._login_as_analytics_admin()
        response = self.client.get(reverse("analytics:api_registration_growth"), {"granularity": "year"})
        data = json.loads(response.content)
        self.assertEqual(data["granularity"], "year")
        self.assertEqual(data["results"][0]["count"], 1)
