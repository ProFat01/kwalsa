import datetime

from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association
from apps.elections.forms import VotingLoginForm
from apps.elections.models import Candidate, Election, Position
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class VotingAccessTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        cls.president = Position.objects.create(association=cls.association, title="President")

    def _make_member(self, approved=True, **overrides):
        defaults = dict(
            association=self.association, full_name="Test Voter", phone_number="08012345678",
            nin_number="12345678901", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE,
        )
        defaults.update(overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        if approved:
            application = RegistrationApplication.objects.create(member=member)
            application.status = RegistrationApplication.Status.APPROVED
            application.save()
            member.refresh_from_db()
        return member

    def _make_active_election(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Test Election",
            start_datetime=now - datetime.timedelta(minutes=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        election.positions.set([self.president])
        return election


class VotingLoginFormAuthenticateTests(VotingAccessTestCase):
    """PART 4: credential verification logic, independent of the view."""

    def test_authenticate_by_membership_id_and_phone_succeeds(self):
        member = self._make_member()
        form = VotingLoginForm(data={
            "method": "membership_id", "membership_id": member.membership_id, "phone_number": member.phone_number,
        })
        self.assertTrue(form.is_valid())
        authenticated, error = form.authenticate()
        self.assertEqual(authenticated, member)
        self.assertIsNone(error)

    def test_authenticate_by_nin_and_phone_succeeds(self):
        member = self._make_member()
        form = VotingLoginForm(data={
            "method": "nin", "nin_number": member.nin_number, "phone_number": member.phone_number,
        })
        self.assertTrue(form.is_valid())
        authenticated, error = form.authenticate()
        self.assertEqual(authenticated, member)

    def test_wrong_phone_number_rejected_with_generic_message(self):
        member = self._make_member()
        form = VotingLoginForm(data={
            "method": "membership_id", "membership_id": member.membership_id, "phone_number": "08000000000",
        })
        self.assertTrue(form.is_valid())
        authenticated, error = form.authenticate()
        self.assertIsNone(authenticated)
        self.assertEqual(error, "We couldn't verify your details. Please check your information and try again.")

    def test_unapproved_member_rejected_with_clear_eligibility_message(self):
        member = self._make_member(approved=False)
        form = VotingLoginForm(data={
            "method": "nin", "nin_number": member.nin_number, "phone_number": member.phone_number,
        })
        self.assertTrue(form.is_valid())
        authenticated, error = form.authenticate()
        self.assertIsNone(authenticated)
        self.assertIn("not currently approved and eligible to vote", error)

    def test_member_with_voting_status_revoked_rejected(self):
        """Covers PART 4's 'Not suspended' — voting_status=False is how suspension is represented."""
        member = self._make_member()
        member.voting_status = False
        member.save(update_fields=["voting_status"])
        form = VotingLoginForm(data={
            "method": "membership_id", "membership_id": member.membership_id, "phone_number": member.phone_number,
        })
        self.assertTrue(form.is_valid())
        authenticated, error = form.authenticate()
        self.assertIsNone(authenticated)
        self.assertIn("not currently approved and eligible to vote", error)


class VotingLoginViewTests(VotingAccessTestCase):
    def test_login_blocked_when_election_is_upcoming(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Future Election",
            start_datetime=now + datetime.timedelta(days=1), end_datetime=now + datetime.timedelta(days=2),
        )
        response = self.client.get(reverse("elections:voting_login", args=[election.pk]))
        self.assertContains(response, "Voting has not opened yet for this election.")

    def test_login_blocked_when_election_is_closed(self):
        now = timezone.now()
        election = Election.objects.create(
            association=self.association, name="Past Election",
            start_datetime=now - datetime.timedelta(days=2), end_datetime=now - datetime.timedelta(days=1),
        )
        response = self.client.get(reverse("elections:voting_login", args=[election.pk]))
        self.assertContains(response, "Voting has closed for this election.")

    def test_successful_login_redirects_to_ballot_and_sets_session(self):
        member = self._make_member()
        election = self._make_active_election()
        response = self.client.post(reverse("elections:voting_login", args=[election.pk]), {
            "method": "membership_id", "membership_id": member.membership_id, "phone_number": member.phone_number,
        })
        self.assertRedirects(response, reverse("elections:ballot", args=[election.pk]))
        self.assertEqual(self.client.session.get(f"voting_member_{election.pk}"), member.pk)

    def test_already_voted_member_redirected_straight_to_success(self):
        member = self._make_member()
        election = self._make_active_election()
        candidate = Candidate.objects.create(election=election, position=self.president, name="A")
        from apps.elections.models import Vote
        Vote.objects.create(election=election, member=member, candidate=candidate)

        response = self.client.post(reverse("elections:voting_login", args=[election.pk]), {
            "method": "membership_id", "membership_id": member.membership_id, "phone_number": member.phone_number,
        })
        self.assertRedirects(response, reverse("elections:vote_success", args=[election.pk]))
