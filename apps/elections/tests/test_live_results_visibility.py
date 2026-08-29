import datetime

from django.test import override_settings
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class LiveResultsVisibilityTests(MediaIsolatedTestCase):
    """
    ISSUE 4: results_view itself was never gated by election status —
    the actual bug was that navigation links to it were hidden while an
    election was active (election_list.html and election_detail.html
    both only showed the results link when status == "closed"). These
    tests confirm both the navigation links AND that the results page
    itself renders live, correct data during an active election, without
    changing anything about how final (closed-election) results work.
    """

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(
            name="Malam Sidi Students Association", short_name="MSA", slug="msa"
        )
        cls.president = Position.objects.create(association=cls.association, title="President")
        now = timezone.now()
        cls.active_election = Election.objects.create(
            association=cls.association, name="Active Election",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        cls.active_election.positions.set([cls.president])
        cls.candidate = Candidate.objects.create(election=cls.active_election, position=cls.president, name="Candidate A")

        cls.member = Member.objects.create(
            association=cls.association, full_name="Voter", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=cls.member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        cls.member.refresh_from_db()
        Vote.objects.create(election=cls.active_election, member=cls.member, candidate=cls.candidate)

    def test_results_page_accessible_and_shows_live_data_during_active_election(self):
        response = self.client.get(reverse("elections:results", args=[self.active_election.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Candidate A")
        self.assertContains(response, "100.0%")  # 1 vote / 1 vote cast for this position

    def test_results_page_shows_in_progress_notice_during_active_election(self):
        response = self.client.get(reverse("elections:results", args=[self.active_election.pk]))
        self.assertContains(response, "Voting is still open")

    def test_election_list_shows_live_results_link_for_active_election(self):
        response = self.client.get(reverse("elections:election_list"))
        self.assertContains(response, "Live results")
        self.assertContains(response, reverse("elections:results", args=[self.active_election.pk]))

    def test_election_detail_shows_live_results_link_for_active_election(self):
        response = self.client.get(reverse("elections:election_detail", args=[self.active_election.pk]))
        self.assertContains(response, "View Live Results")
        self.assertContains(response, reverse("elections:results", args=[self.active_election.pk]))

    @override_settings(DEFAULT_ASSOCIATION_SLUG="msa")
    def test_homepage_active_column_shows_live_results_link(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Live Results")

    def test_closed_election_results_unaffected_no_in_progress_notice(self):
        """Confirms this fix didn't change final-result behavior for closed elections."""
        now = timezone.now()
        closed_election = Election.objects.create(
            association=self.association, name="Closed Election",
            start_datetime=now - datetime.timedelta(days=2), end_datetime=now - datetime.timedelta(days=1),
        )
        closed_election.positions.set([self.president])
        Candidate.objects.create(election=closed_election, position=self.president, name="Candidate B")

        response = self.client.get(reverse("elections:results", args=[closed_election.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Voting is still open")

        list_response = self.client.get(reverse("elections:election_list"))
        self.assertContains(list_response, "View results")  # closed-election link text unchanged

    def test_upcoming_election_has_no_results_link_anywhere(self):
        """Results links should only appear for active/closed elections, never upcoming ones."""
        now = timezone.now()
        upcoming = Election.objects.create(
            association=self.association, name="Upcoming Election",
            start_datetime=now + datetime.timedelta(days=1), end_datetime=now + datetime.timedelta(days=2),
        )
        response = self.client.get(reverse("elections:election_detail", args=[upcoming.pk]))
        self.assertNotContains(response, "Live Results")
        self.assertNotContains(response, "View Results")
