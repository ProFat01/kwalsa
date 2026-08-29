"""
Version 2.0: Election Eligibility Engine.

Covers: National, Institution, Faculty, Department, Level, Gender,
Membership Category, and Custom (combined) elections; validation
failures; unauthorized vs eligible voting through the real views;
analytics reuse of the engine; and backward compatibility with
pre-2.0 elections (no eligibility fields set).
"""
import datetime

from django.core.exceptions import ValidationError
from django.test import Client
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association
from apps.elections.eligibility import eligible_members, is_member_eligible
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class EligibilityTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        cls.position = Position.objects.create(association=cls.association, title="President")

    def _make_election(self, **overrides):
        now = timezone.now()
        defaults = dict(
            association=self.association,
            name="Test Election",
            start_datetime=now - datetime.timedelta(hours=1),
            end_datetime=now + datetime.timedelta(hours=1),
        )
        defaults.update(overrides)
        election = Election(**defaults)
        election.full_clean()
        election.save()
        election.positions.set([self.position])
        return election

    def _make_member(self, approved=True, **overrides):
        defaults = dict(
            full_name="Voter",
            phone_number="0800000%04d" % Member.objects.count(),
            nin_number="000000%05d" % Member.objects.count(),
            date_of_birth="2001-01-01",
            institution="Gombe State University",
            course="Computer Science",
            category=Member.Category.UNDERGRADUATE,
            association=self.association,
        )
        defaults.update(overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        if approved:
            application = RegistrationApplication.objects.create(member=member)
            application.status = RegistrationApplication.Status.APPROVED
            application.save()
            member.refresh_from_db()
        return member


class NationalElectionEligibilityTests(EligibilityTestCase):
    def test_every_approved_member_eligible_regardless_of_stray_filters(self):
        election = self._make_election(scope=Election.Scope.NATIONAL, eligibility_level="300")
        member_a = self._make_member(institution="GSU", level="100")
        member_b = self._make_member(institution="ABU", level="400")
        self.assertTrue(is_member_eligible(member_a, election))
        self.assertTrue(is_member_eligible(member_b, election))
        self.assertEqual(eligible_members(election).count(), 2)

    def test_unapproved_member_not_eligible(self):
        election = self._make_election(scope=Election.Scope.NATIONAL)
        member = self._make_member(approved=False)
        self.assertFalse(is_member_eligible(member, election))

    def test_national_with_membership_category_undergraduate_only(self):
        election = self._make_election(
            scope=Election.Scope.NATIONAL,
            eligibility_membership_category=Member.Category.UNDERGRADUATE,
        )
        undergrad = self._make_member(category=Member.Category.UNDERGRADUATE)
        alumnus = self._make_member(category=Member.Category.GRADUATE_ALUMNI)
        self.assertTrue(is_member_eligible(undergrad, election))
        self.assertFalse(is_member_eligible(alumnus, election))

    def test_national_alumni_only(self):
        election = self._make_election(
            scope=Election.Scope.NATIONAL,
            eligibility_membership_category=Member.Category.GRADUATE_ALUMNI,
        )
        undergrad = self._make_member(category=Member.Category.UNDERGRADUATE)
        alumnus = self._make_member(category=Member.Category.GRADUATE_ALUMNI)
        self.assertFalse(is_member_eligible(undergrad, election))
        self.assertTrue(is_member_eligible(alumnus, election))


class InstitutionElectionEligibilityTests(EligibilityTestCase):
    def test_only_selected_institution_eligible(self):
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="Gombe State University")
        in_scope = self._make_member(institution="Gombe State University")
        out_of_scope = self._make_member(institution="Ahmadu Bello University")
        self.assertTrue(is_member_eligible(in_scope, election))
        self.assertFalse(is_member_eligible(out_of_scope, election))

    def test_institution_match_is_case_insensitive(self):
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="Gombe State University")
        member = self._make_member(institution="gombe state university")
        self.assertTrue(is_member_eligible(member, election))

    def test_institution_election_may_include_alumni_via_category_filter_unset(self):
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="GSU")
        undergrad = self._make_member(institution="GSU", category=Member.Category.UNDERGRADUATE)
        alumnus = self._make_member(institution="GSU", category=Member.Category.GRADUATE_ALUMNI)
        # No membership_category filter set -> both categories eligible.
        self.assertTrue(is_member_eligible(undergrad, election))
        self.assertTrue(is_member_eligible(alumnus, election))

    def test_institution_election_restricted_to_undergraduate(self):
        election = self._make_election(
            scope=Election.Scope.INSTITUTION,
            eligibility_institution="GSU",
            eligibility_membership_category=Member.Category.UNDERGRADUATE,
        )
        undergrad = self._make_member(institution="GSU", category=Member.Category.UNDERGRADUATE)
        alumnus = self._make_member(institution="GSU", category=Member.Category.GRADUATE_ALUMNI)
        self.assertTrue(is_member_eligible(undergrad, election))
        self.assertFalse(is_member_eligible(alumnus, election))


class FacultyElectionEligibilityTests(EligibilityTestCase):
    def test_only_matching_institution_and_faculty_eligible(self):
        election = self._make_election(
            scope=Election.Scope.FACULTY, eligibility_institution="GSU", eligibility_faculty="Science",
        )
        in_scope = self._make_member(institution="GSU", faculty="Science")
        wrong_faculty = self._make_member(institution="GSU", faculty="Arts")
        wrong_institution = self._make_member(institution="ABU", faculty="Science")
        self.assertTrue(is_member_eligible(in_scope, election))
        self.assertFalse(is_member_eligible(wrong_faculty, election))
        self.assertFalse(is_member_eligible(wrong_institution, election))


class DepartmentElectionEligibilityTests(EligibilityTestCase):
    def test_only_matching_department_eligible(self):
        election = self._make_election(
            scope=Election.Scope.DEPARTMENT,
            eligibility_institution="GSU", eligibility_faculty="Science", eligibility_department="Computer Science",
        )
        in_scope = self._make_member(institution="GSU", faculty="Science", department="Computer Science")
        wrong_department = self._make_member(institution="GSU", faculty="Science", department="Chemistry")
        self.assertTrue(is_member_eligible(in_scope, election))
        self.assertFalse(is_member_eligible(wrong_department, election))


class LevelAndGenderElectionEligibilityTests(EligibilityTestCase):
    """Level Representative / Female Representative elections: Scope.CUSTOM + one filter."""

    def test_level_representative_election(self):
        election = self._make_election(scope=Election.Scope.CUSTOM, eligibility_level="300")
        in_level = self._make_member(level="300")
        other_level = self._make_member(level="400")
        self.assertTrue(is_member_eligible(in_level, election))
        self.assertFalse(is_member_eligible(other_level, election))

    def test_female_representative_election(self):
        election = self._make_election(scope=Election.Scope.CUSTOM, eligibility_gender=Member.Gender.FEMALE)
        female = self._make_member(gender=Member.Gender.FEMALE)
        male = self._make_member(gender=Member.Gender.MALE)
        self.assertTrue(is_member_eligible(female, election))
        self.assertFalse(is_member_eligible(male, election))

    def test_female_representative_election_membership_category_configurable(self):
        election = self._make_election(
            scope=Election.Scope.CUSTOM,
            eligibility_gender=Member.Gender.FEMALE,
            eligibility_membership_category=Member.Category.UNDERGRADUATE,
        )
        female_undergrad = self._make_member(gender=Member.Gender.FEMALE, category=Member.Category.UNDERGRADUATE)
        female_alumna = self._make_member(gender=Member.Gender.FEMALE, category=Member.Category.GRADUATE_ALUMNI)
        self.assertTrue(is_member_eligible(female_undergrad, election))
        self.assertFalse(is_member_eligible(female_alumna, election))


class CustomElectionEligibilityTests(EligibilityTestCase):
    def test_all_filters_must_match(self):
        election = self._make_election(
            scope=Election.Scope.CUSTOM,
            eligibility_institution="GSU",
            eligibility_faculty="Science",
            eligibility_department="Chemistry",
            eligibility_level="300",
            eligibility_gender=Member.Gender.FEMALE,
            eligibility_membership_category=Member.Category.UNDERGRADUATE,
        )
        matches_everything = self._make_member(
            institution="GSU", faculty="Science", department="Chemistry", level="300",
            gender=Member.Gender.FEMALE, category=Member.Category.UNDERGRADUATE,
        )
        wrong_level = self._make_member(
            institution="GSU", faculty="Science", department="Chemistry", level="400",
            gender=Member.Gender.FEMALE, category=Member.Category.UNDERGRADUATE,
        )
        wrong_gender = self._make_member(
            institution="GSU", faculty="Science", department="Chemistry", level="300",
            gender=Member.Gender.MALE, category=Member.Category.UNDERGRADUATE,
        )
        self.assertTrue(is_member_eligible(matches_everything, election))
        self.assertFalse(is_member_eligible(wrong_level, election))
        self.assertFalse(is_member_eligible(wrong_gender, election))
        self.assertEqual(eligible_members(election).count(), 1)


class ApprovedMembersOnlyTests(EligibilityTestCase):
    def test_approved_members_only_false_includes_unapproved(self):
        election = self._make_election(scope=Election.Scope.NATIONAL, approved_members_only=False)
        unapproved = self._make_member(approved=False)
        self.assertTrue(is_member_eligible(unapproved, election))

    def test_suspended_member_not_eligible_when_approved_members_only(self):
        election = self._make_election(scope=Election.Scope.NATIONAL)
        member = self._make_member()
        member.voting_status = False
        member.save(update_fields=["voting_status"])
        self.assertFalse(is_member_eligible(member, election))


class ValidationFailureTests(EligibilityTestCase):
    def test_department_without_faculty_is_invalid(self):
        election = Election(
            association=self.association, name="Bad Election",
            start_datetime=timezone.now(), end_datetime=timezone.now() + datetime.timedelta(hours=1),
            scope=Election.Scope.CUSTOM, eligibility_department="Chemistry",
        )
        with self.assertRaises(ValidationError):
            election.full_clean()

    def test_faculty_without_institution_is_invalid(self):
        election = Election(
            association=self.association, name="Bad Election",
            start_datetime=timezone.now(), end_datetime=timezone.now() + datetime.timedelta(hours=1),
            scope=Election.Scope.CUSTOM, eligibility_faculty="Science",
        )
        with self.assertRaises(ValidationError):
            election.full_clean()

    def test_national_election_ignores_invalid_combinations(self):
        election = Election(
            association=self.association, name="National Election",
            start_datetime=timezone.now(), end_datetime=timezone.now() + datetime.timedelta(hours=1),
            scope=Election.Scope.NATIONAL, eligibility_department="Chemistry",
        )
        election.full_clean()  # must not raise


class VotingAccessTests(EligibilityTestCase):
    """End-to-end through the real voting views — unauthorized vs eligible."""

    def setUp(self):
        self.client = Client()

    def _login(self, election, member, phone):
        return self.client.post(
            reverse("elections:voting_login", args=[election.pk]),
            {"method": "membership_id", "membership_id": member.membership_id, "phone_number": phone},
        )

    def test_ineligible_member_blocked_at_login(self):
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="GSU")
        election.positions.set([self.position])
        Candidate.objects.create(election=election, position=self.position, name="Candidate A")
        member = self._make_member(institution="ABU", phone_number="08099999999", nin_number="09999999999")

        response = self._login(election, member, "08099999999")
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not eligible")
        self.assertFalse(Vote.objects.filter(election=election, member=member).exists())

    def test_eligible_member_can_reach_ballot(self):
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="GSU")
        election.positions.set([self.position])
        Candidate.objects.create(election=election, position=self.position, name="Candidate A")
        member = self._make_member(institution="GSU", phone_number="08088888888", nin_number="08888888888")

        response = self._login(election, member, "08088888888")
        self.assertRedirects(response, reverse("elections:ballot", args=[election.pk]))

    def test_ballot_view_rechecks_eligibility_server_side(self):
        """Simulates a manually-guessed/replayed session for an ineligible member (URL manipulation defense)."""
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="GSU")
        election.positions.set([self.position])
        member = self._make_member(institution="ABU", phone_number="08077777777", nin_number="07777777777")

        session = self.client.session
        session[f"voting_member_{election.pk}"] = member.pk
        session.save()

        response = self.client.get(reverse("elections:ballot", args=[election.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "not eligible")

    def test_vote_model_rejects_ineligible_member_at_model_layer(self):
        """Defense in depth: even a direct Vote.full_clean() bypassing the views must reject this."""
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="GSU")
        election.positions.set([self.position])
        candidate = Candidate.objects.create(election=election, position=self.position, name="Candidate A")
        member = self._make_member(institution="ABU")

        vote = Vote(election=election, member=member, candidate=candidate)
        with self.assertRaises(ValidationError):
            vote.full_clean()


class AnalyticsReuseTests(EligibilityTestCase):
    def test_eligible_voters_count_uses_engine(self):
        election = self._make_election(scope=Election.Scope.INSTITUTION, eligibility_institution="GSU")
        self._make_member(institution="GSU")
        self._make_member(institution="ABU")
        self.assertEqual(election.eligible_voters_count(), 1)

    def test_analytics_election_overview_breaks_down_by_category(self):
        from apps.analytics import services

        election = self._make_election(scope=Election.Scope.NATIONAL)
        self._make_member(category=Member.Category.UNDERGRADUATE)
        self._make_member(category=Member.Category.GRADUATE_ALUMNI)

        overview = services.election_overview(election)
        self.assertEqual(overview["eligible_undergraduate"], 1)
        self.assertEqual(overview["eligible_alumni"], 1)


class BackwardCompatibilityTests(EligibilityTestCase):
    def test_election_created_without_eligibility_fields_behaves_as_national(self):
        election = self._make_election()  # no scope/filters passed -> model defaults
        self.assertEqual(election.scope, Election.Scope.NATIONAL)
        self.assertTrue(election.approved_members_only)
        member = self._make_member()
        self.assertTrue(is_member_eligible(member, election))

    def test_eligible_voters_count_matches_pre_2_0_voting_status_query(self):
        election = self._make_election()
        eligible = self._make_member()
        self._make_member(approved=False)
        self.assertEqual(
            election.eligible_voters_count(),
            Member.objects.filter(association=self.association, voting_status=True).count(),
        )
        self.assertEqual(election.eligible_voters_count(), 1)
        self.assertEqual(eligible.voting_status, True)
