import datetime

from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class ResultsAndDashboardTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        cls.president = Position.objects.create(association=cls.association, title="President")
        now = timezone.now()
        cls.election = Election.objects.create(
            association=cls.association, name="Test Election",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        cls.election.positions.set([cls.president])
        cls.candidate_a = Candidate.objects.create(election=cls.election, position=cls.president, name="Candidate A")
        cls.candidate_b = Candidate.objects.create(election=cls.election, position=cls.president, name="Candidate B")

    def _make_eligible_member(self, voting_status=True, **overrides):
        defaults = dict(
            full_name="Voter", phone_number="08000000000", nin_number="00000000000",
            date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, association=self.association,
        )
        defaults.update(overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        if voting_status:
            application = RegistrationApplication.objects.create(member=member)
            application.status = RegistrationApplication.Status.APPROVED
            application.save()
            member.refresh_from_db()
        return member


class ResultsCalculationTests(ResultsAndDashboardTestCase):
    """PART 8: vote count + percentage per candidate; PART 12: results calculation, turnout calculation."""

    def test_results_by_position_counts_and_percentages(self):
        voters = [
            self._make_eligible_member(phone_number=f"0800000000{i}", nin_number=f"0000000000{i}")
            for i in range(4)
        ]
        # 3 votes for A, 1 for B -> 75% / 25%
        for voter in voters[:3]:
            Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=voters[3], candidate=self.candidate_b)

        results = self.election.results_by_position()
        self.assertEqual(len(results), 1)
        rows = {row["candidate"].name: row for row in results[0]["candidates"]}
        self.assertEqual(rows["Candidate A"]["vote_count"], 3)
        self.assertEqual(rows["Candidate A"]["percentage"], 75.0)
        self.assertEqual(rows["Candidate B"]["vote_count"], 1)
        self.assertEqual(rows["Candidate B"]["percentage"], 25.0)
        self.assertEqual(results[0]["total_votes"], 4)

    def test_results_with_no_votes_yet_shows_zero_without_dividing_by_zero(self):
        results = self.election.results_by_position()
        rows = results[0]["candidates"]
        self.assertTrue(all(row["vote_count"] == 0 and row["percentage"] == 0.0 for row in rows))

    def test_eligible_voters_count_only_counts_voting_status_true_members(self):
        self._make_eligible_member(voting_status=True, phone_number="08011111111", nin_number="11111111111")
        self._make_eligible_member(voting_status=False, phone_number="08022222222", nin_number="22222222222")
        self.assertEqual(self.election.eligible_voters_count(), 1)

    def test_voters_count_counts_distinct_members_not_vote_rows(self):
        """A member casting votes for multiple positions still counts once towards turnout."""
        secretary = Position.objects.create(association=self.association, title="Secretary")
        self.election.positions.add(secretary)
        sec_candidate = Candidate.objects.create(election=self.election, position=secretary, name="Sec Candidate")

        voter = self._make_eligible_member(phone_number="08033333333", nin_number="33333333333")
        Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=voter, candidate=sec_candidate)

        self.assertEqual(self.election.voters_count(), 1)

    def test_turnout_percentage_calculation(self):
        for i in range(10):
            self._make_eligible_member(phone_number=f"080444444{i:02d}"[:11], nin_number=f"4444444444{i}"[:11])
        eligible = self.election.eligible_voters_count()
        self.assertEqual(eligible, 10)

        voters = list(Member.objects.filter(association=self.association, voting_status=True)[:4])
        for voter in voters:
            Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)

        self.assertEqual(self.election.voters_count(), 4)
        self.assertEqual(self.election.turnout_percentage(), 40.0)

    def test_turnout_percentage_zero_eligible_voters_does_not_divide_by_zero(self):
        self.assertEqual(self.election.eligible_voters_count(), 0)
        self.assertEqual(self.election.turnout_percentage(), 0.0)


class PublicResultsPageTests(ResultsAndDashboardTestCase):
    def test_results_page_renders_counts_and_percentages(self):
        voter = self._make_eligible_member()
        Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)

        response = self.client.get(reverse("elections:results", args=[self.election.pk]))
        self.assertContains(response, "Candidate A")
        self.assertContains(response, "100.0%")

    def test_results_page_is_public_no_login_required(self):
        response = self.client.get(reverse("elections:results", args=[self.election.pk]))
        self.assertEqual(response.status_code, 200)


class AdminDashboardTests(ResultsAndDashboardTestCase):
    """PART 9: dashboard summary numbers + access restricted to Election Admins/staff with the right permission."""

    @classmethod
    def setUpTestData(cls):
        super().setUpTestData()
        # Role groups are created by the setup_roles management command
        # (deliberately not a migration — see its docstring), so the test
        # database needs it run explicitly; this isn't test-only
        # plumbing, it's exactly the same command a real deployment runs
        # once after `migrate`.
        from django.core.management import call_command

        call_command("setup_roles", verbosity=0)

    def test_anonymous_redirected_to_admin_login(self):
        response = self.client.get(reverse("elections:admin_dashboard", args=[self.election.pk]))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/admin/login/", response["Location"])

    def test_staff_without_election_permission_gets_403(self):
        User.objects.create_user(username="plainstaff", password="x", is_staff=True)
        self.client.login(username="plainstaff", password="x")
        response = self.client.get(reverse("elections:admin_dashboard", args=[self.election.pk]))
        self.assertEqual(response.status_code, 403)

    def test_election_admin_can_view_dashboard_with_correct_numbers(self):
        from django.contrib.auth.models import Group

        admin_user = User.objects.create_user(username="election_admin", password="x", is_staff=True)
        admin_user.groups.add(Group.objects.get(name="Election Admin"))
        self.client.login(username="election_admin", password="x")

        voter1 = self._make_eligible_member(phone_number="08055555551", nin_number="55555555551")
        self._make_eligible_member(phone_number="08055555552", nin_number="55555555552")  # eligible, didn't vote
        Vote.objects.create(election=self.election, member=voter1, candidate=self.candidate_a)

        response = self.client.get(reverse("elections:admin_dashboard", args=[self.election.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Candidate A")
        # 1 voter out of 2 eligible = 50%
        self.assertContains(response, "50.0%")
