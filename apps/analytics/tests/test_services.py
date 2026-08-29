import datetime

from django.test import TestCase
from django.utils import timezone

from apps.analytics import services
from apps.analytics.models import AgeDistributionSnapshot, ElectionResultSnapshot, MembershipSnapshot
from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class AnalyticsTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def _make_member(self, age_years, approved=True, voting_status=None, **overrides):
        dob = timezone.now().date() - datetime.timedelta(days=age_years * 365 + 30)
        defaults = dict(
            association=self.association, full_name="Member", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, date_of_birth=dob,
        )
        defaults.update(overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        if approved:
            application = RegistrationApplication.objects.create(member=member)
            application.status = RegistrationApplication.Status.APPROVED
            application.save()
            member.refresh_from_db()
        if voting_status is not None:
            member.voting_status = voting_status
            member.save(update_fields=["voting_status"])
        return member


class MembershipOverviewTests(AnalyticsTestCase):
    """PART 1 & PART 13: membership counts."""

    def test_counts_and_percentages(self):
        self._make_member(20, approved=True, phone_number="08010000001", nin_number="10000000001")
        self._make_member(20, approved=True, phone_number="08010000002", nin_number="10000000002", alumni_status=True)
        self._make_member(20, approved=False, phone_number="08010000003", nin_number="10000000003")
        rejected = self._make_member(20, approved=False, phone_number="08010000004", nin_number="10000000004")
        app = RegistrationApplication.objects.create(member=rejected)
        app.status = RegistrationApplication.Status.REJECTED
        app.rejection_reason = "Incomplete documents."
        app.save()

        overview = services.membership_overview(self.association)
        self.assertEqual(overview["total_members"], 4)
        self.assertEqual(overview["total_approved"], 2)
        self.assertEqual(overview["approved_percentage"], 50.0)
        self.assertEqual(overview["total_pending"], 1)
        self.assertEqual(overview["total_rejected"], 1)
        self.assertEqual(overview["total_alumni"], 1)
        self.assertEqual(overview["alumni_percentage"], 25.0)

    def test_no_members_does_not_divide_by_zero(self):
        overview = services.membership_overview(self.association)
        self.assertEqual(overview["total_members"], 0)
        self.assertEqual(overview["approved_percentage"], 0.0)


class CourseAndInstitutionDistributionTests(AnalyticsTestCase):
    """PART 2 & 3: grouped counts, percentages, sort order."""

    def setUp(self):
        self._make_member(20, course="Chemistry", institution="GSU", phone_number="08010000001", nin_number="10000000001")
        self._make_member(20, course="Chemistry", institution="GSU", phone_number="08010000002", nin_number="10000000002")
        self._make_member(20, course="Biology", institution="FCE", phone_number="08010000003", nin_number="10000000003")

    def test_course_distribution_desc_default(self):
        rows = services.course_distribution(self.association)
        self.assertEqual(rows[0]["course"], "Chemistry")
        self.assertEqual(rows[0]["count"], 2)
        self.assertEqual(rows[0]["percentage"], 66.7)
        self.assertEqual(rows[1]["course"], "Biology")

    def test_course_distribution_asc(self):
        rows = services.course_distribution(self.association, order="asc")
        self.assertEqual(rows[0]["course"], "Biology")
        self.assertEqual(rows[-1]["course"], "Chemistry")

    def test_institution_distribution(self):
        rows = services.institution_distribution(self.association)
        labels = {row["institution"]: row["count"] for row in rows}
        self.assertEqual(labels, {"GSU": 2, "FCE": 1})


class AgeDistributionTests(AnalyticsTestCase):
    """PART 4: age bucketing boundaries."""

    def test_each_bracket_boundary(self):
        cases = [
            (15, AgeDistributionSnapshot.AgeBracket.BELOW_16),
            (16, AgeDistributionSnapshot.AgeBracket.AGE_16_20),
            (20, AgeDistributionSnapshot.AgeBracket.AGE_16_20),
            (21, AgeDistributionSnapshot.AgeBracket.AGE_21_25),
            (25, AgeDistributionSnapshot.AgeBracket.AGE_21_25),
            (26, AgeDistributionSnapshot.AgeBracket.AGE_26_30),
            (30, AgeDistributionSnapshot.AgeBracket.AGE_26_30),
            (31, AgeDistributionSnapshot.AgeBracket.AGE_31_40),
            (40, AgeDistributionSnapshot.AgeBracket.AGE_31_40),
            (41, AgeDistributionSnapshot.AgeBracket.AGE_41_PLUS),
            (70, AgeDistributionSnapshot.AgeBracket.AGE_41_PLUS),
        ]
        for age, expected_bracket in cases:
            with self.subTest(age=age):
                self.assertEqual(AgeDistributionSnapshot.bucket_for_age(age), expected_bracket)

    def test_age_distribution_counts_and_includes_all_brackets(self):
        self._make_member(15, phone_number="08010000001", nin_number="10000000001")  # below_16
        self._make_member(22, phone_number="08010000002", nin_number="10000000002")  # 21_25
        rows = services.age_distribution(self.association)
        self.assertEqual(len(rows), 6)  # every bracket present even at zero
        by_bracket = {row["bracket"]: row["count"] for row in rows}
        self.assertEqual(by_bracket["below_16"], 1)
        self.assertEqual(by_bracket["21_25"], 1)
        self.assertEqual(by_bracket["26_30"], 0)

    def test_age_distribution_includes_unapproved_members(self):
        """Age analytics isn't qualified by approval status in the spec — a pending applicant's age still counts."""
        self._make_member(22, approved=False, phone_number="08010000001", nin_number="10000000001")
        rows = services.age_distribution(self.association)
        by_bracket = {row["bracket"]: row["count"] for row in rows}
        self.assertEqual(by_bracket["21_25"], 1)


class RegistrationGrowthTests(AnalyticsTestCase):
    """PART 5: registration growth helper, future-chart-ready shape."""

    def test_growth_by_month_label_format(self):
        self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        rows = services.registration_growth(self.association, granularity="month")
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["count"], 1)
        self.assertRegex(rows[0]["label"], r"^[A-Za-z]+ \d{4}$")  # e.g. "June 2026"

    def test_invalid_granularity_raises(self):
        with self.assertRaises(ValueError):
            services.registration_growth(self.association, granularity="fortnight")


class ElectionAnalyticsTestCase(AnalyticsTestCase):
    def setUp(self):
        self.president = Position.objects.create(association=self.association, title="President")
        now = timezone.now()
        self.election = Election.objects.create(
            association=self.association, name="Test Election",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        self.election.positions.set([self.president])
        self.candidate_a = Candidate.objects.create(election=self.election, position=self.president, name="A")
        self.candidate_b = Candidate.objects.create(election=self.election, position=self.president, name="B")


class ElectionOverviewTests(ElectionAnalyticsTestCase):
    """PART 6: eligible voters, votes cast, turnout, position/candidate counts."""

    def test_election_overview_counts(self):
        voter = self._make_member(22, phone_number="08010000001", nin_number="10000000001")
        Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)

        overview = services.election_overview(self.election)
        self.assertEqual(overview["eligible_voters"], 1)
        self.assertEqual(overview["votes_cast"], 1)
        self.assertEqual(overview["turnout_percentage"], 100.0)
        self.assertEqual(overview["total_positions"], 1)
        self.assertEqual(overview["total_candidates"], 2)


class PositionResultsWinnerTests(ElectionAnalyticsTestCase):
    """PART 7: vote totals, percentages, winner — including ties."""

    def test_clear_winner(self):
        v1 = self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        v2 = self._make_member(20, phone_number="08010000002", nin_number="10000000002")
        v3 = self._make_member(20, phone_number="08010000003", nin_number="10000000003")
        Vote.objects.create(election=self.election, member=v1, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=v2, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=v3, candidate=self.candidate_b)

        results = services.position_results_with_winner(self.election)
        self.assertEqual(len(results), 1)
        item = results[0]
        self.assertFalse(item["is_tie"])
        self.assertEqual(item["winner"], self.candidate_a)
        rows = {row["candidate"].name: row["percentage"] for row in item["candidates"]}
        self.assertEqual(rows["A"], 66.7)
        self.assertEqual(rows["B"], 33.3)

    def test_tie_has_no_single_winner(self):
        v1 = self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        v2 = self._make_member(20, phone_number="08010000002", nin_number="10000000002")
        Vote.objects.create(election=self.election, member=v1, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=v2, candidate=self.candidate_b)

        item = services.position_results_with_winner(self.election)[0]
        self.assertTrue(item["is_tie"])
        self.assertIsNone(item["winner"])
        self.assertEqual(set(item["tied_candidates"]), {self.candidate_a, self.candidate_b})

    def test_no_votes_yet_no_winner_no_crash(self):
        item = services.position_results_with_winner(self.election)[0]
        self.assertIsNone(item["winner"])
        self.assertFalse(item["is_tie"])


class AgeParticipationTests(ElectionAnalyticsTestCase):
    """PART 8."""

    def test_participation_per_bracket(self):
        young_voter = self._make_member(18, phone_number="08010000001", nin_number="10000000001")
        self._make_member(18, phone_number="08010000002", nin_number="10000000002")  # eligible, didn't vote
        older_voter = self._make_member(35, phone_number="08010000003", nin_number="10000000003")
        Vote.objects.create(election=self.election, member=young_voter, candidate=self.candidate_a)
        Vote.objects.create(election=self.election, member=older_voter, candidate=self.candidate_b)

        rows = {row["bracket"]: row for row in services.age_participation(self.election)}
        self.assertEqual(rows["16_20"]["eligible"], 2)
        self.assertEqual(rows["16_20"]["voted"], 1)
        self.assertEqual(rows["16_20"]["participation_percentage"], 50.0)
        self.assertEqual(rows["31_40"]["eligible"], 1)
        self.assertEqual(rows["31_40"]["voted"], 1)
        self.assertEqual(rows["31_40"]["participation_percentage"], 100.0)

    def test_ineligible_members_excluded_from_participation(self):
        self._make_member(18, approved=False, phone_number="08010000001", nin_number="10000000001")
        rows = {row["bracket"]: row for row in services.age_participation(self.election)}
        self.assertEqual(rows["16_20"]["eligible"], 0)


class SnapshotGenerationTests(ElectionAnalyticsTestCase):
    """PART 9."""

    def test_generate_membership_snapshot(self):
        self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        snapshot = services.generate_membership_snapshot(self.association)
        self.assertEqual(snapshot.total_members, 1)
        self.assertEqual(MembershipSnapshot.objects.count(), 1)

    def test_generate_membership_snapshot_is_idempotent_per_day(self):
        self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        services.generate_membership_snapshot(self.association)
        self._make_member(20, phone_number="08010000002", nin_number="10000000002")
        services.generate_membership_snapshot(self.association)  # same day, run again
        self.assertEqual(MembershipSnapshot.objects.count(), 1)  # updated, not duplicated
        self.assertEqual(MembershipSnapshot.objects.get().total_members, 2)

    def test_generate_age_distribution_snapshot_creates_all_brackets(self):
        self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        snapshots = services.generate_age_distribution_snapshot(self.association)
        self.assertEqual(len(snapshots), 6)
        self.assertEqual(AgeDistributionSnapshot.objects.count(), 6)

    def test_generate_election_result_snapshot_does_not_touch_is_published(self):
        voter = self._make_member(20, phone_number="08010000001", nin_number="10000000001")
        Vote.objects.create(election=self.election, member=voter, candidate=self.candidate_a)

        snapshots = services.generate_election_result_snapshots(self.election)
        self.assertEqual(len(snapshots), 1)
        snapshot = snapshots[0]
        self.assertEqual(snapshot.total_votes_cast, 1)
        self.assertEqual(snapshot.winner_candidate, self.candidate_a)
        self.assertFalse(snapshot.is_published)  # untouched, stays the model default

        snapshot.is_published = True
        snapshot.save()
        services.generate_election_result_snapshots(self.election)  # regenerate again
        snapshot.refresh_from_db()
        self.assertTrue(snapshot.is_published)  # still untouched by a second generation run
