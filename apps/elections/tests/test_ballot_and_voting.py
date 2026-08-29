import datetime

from django.db import IntegrityError, transaction
from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class BallotTestCase(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        cls.president = Position.objects.create(association=cls.association, title="President", display_order=1)
        cls.secretary = Position.objects.create(association=cls.association, title="Secretary", display_order=2)

        now = timezone.now()
        cls.election = Election.objects.create(
            association=cls.association, name="Test Election",
            start_datetime=now - datetime.timedelta(minutes=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        cls.election.positions.set([cls.president, cls.secretary])

        cls.pres_a = Candidate.objects.create(election=cls.election, position=cls.president, name="Pres A")
        cls.pres_b = Candidate.objects.create(election=cls.election, position=cls.president, name="Pres B")
        cls.sec_a = Candidate.objects.create(election=cls.election, position=cls.secretary, name="Sec A")
        cls.sec_b = Candidate.objects.create(election=cls.election, position=cls.secretary, name="Sec B")

    def _approved_member(self, **overrides):
        defaults = dict(
            association=self.association, full_name="Test Voter", phone_number="08012345678",
            nin_number="12345678901", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE,
        )
        defaults.update(overrides)
        member = Member.objects.create(passport_photo=make_image("p.png"), **defaults)
        application = RegistrationApplication.objects.create(member=member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        member.refresh_from_db()
        return member

    def _login(self, member):
        self.client.post(reverse("elections:voting_login", args=[self.election.pk]), {
            "method": "membership_id", "membership_id": member.membership_id, "phone_number": member.phone_number,
        })


class BallotPageTests(BallotTestCase):
    def test_ballot_requires_login_session(self):
        response = self.client.get(reverse("elections:ballot", args=[self.election.pk]))
        self.assertRedirects(response, reverse("elections:voting_login", args=[self.election.pk]))

    def test_ballot_shows_all_positions_and_candidates(self):
        member = self._approved_member()
        self._login(member)
        response = self.client.get(reverse("elections:ballot", args=[self.election.pk]))
        self.assertContains(response, "President")
        self.assertContains(response, "Secretary")
        for name in ["Pres A", "Pres B", "Sec A", "Sec B"]:
            self.assertContains(response, name)


class VoteSubmissionTests(BallotTestCase):
    """PARTS 5, 6, 7: requiring every position, atomic creation, completion message."""

    def test_submission_missing_a_position_is_rejected(self):
        member = self._approved_member()
        self._login(member)
        response = self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": self.pres_a.pk,
            # secretary deliberately omitted
        })
        self.assertContains(response, "Please select a candidate")
        self.assertEqual(Vote.objects.filter(member=member).count(), 0)

    def test_successful_submission_creates_one_vote_per_position(self):
        member = self._approved_member()
        self._login(member)
        response = self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": self.pres_a.pk,
            f"position_{self.secretary.pk}": self.sec_a.pk,
        })
        self.assertRedirects(response, reverse("elections:vote_success", args=[self.election.pk]))
        votes = Vote.objects.filter(election=self.election, member=member)
        self.assertEqual(votes.count(), 2)
        self.assertEqual(set(votes.values_list("position_id", flat=True)), {self.president.pk, self.secretary.pk})

    def test_vote_success_page_shows_completion_message(self):
        member = self._approved_member()
        self._login(member)
        self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": self.pres_a.pk,
            f"position_{self.secretary.pk}": self.sec_a.pk,
        })
        response = self.client.get(reverse("elections:vote_success", args=[self.election.pk]))
        self.assertContains(response, "Your vote has been recorded successfully.")

    def test_second_ballot_visit_after_voting_is_redirected_not_re_shown(self):
        member = self._approved_member()
        self._login(member)
        self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": self.pres_a.pk,
            f"position_{self.secretary.pk}": self.sec_a.pk,
        })
        # Member must not vote again — re-logging in for the same election sends them to success, not a fresh ballot.
        self._login(member)
        response = self.client.get(reverse("elections:ballot", args=[self.election.pk]))
        self.assertRedirects(response, reverse("elections:voting_login", args=[self.election.pk]))

    def test_manual_manipulation_with_candidate_from_wrong_position_rejected(self):
        """PART 6/10: tampering with the submitted candidate id is caught by ModelChoiceField's own queryset validation."""
        member = self._approved_member()
        self._login(member)
        response = self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": self.sec_a.pk,  # sec_a doesn't belong to the President field's queryset
            f"position_{self.secretary.pk}": self.sec_a.pk,
        })
        self.assertContains(response, "valid choice")
        self.assertEqual(Vote.objects.filter(member=member).count(), 0)

    def test_manual_manipulation_with_candidate_from_different_election_rejected(self):
        member = self._approved_member()
        other_election = Election.objects.create(
            association=self.association, name="Other Election",
            start_datetime=self.election.start_datetime, end_datetime=self.election.end_datetime,
        )
        other_election.positions.set([self.president])
        rogue = Candidate.objects.create(election=other_election, position=self.president, name="Rogue")

        self._login(member)
        response = self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": rogue.pk,
            f"position_{self.secretary.pk}": self.sec_a.pk,
        })
        self.assertContains(response, "valid choice")
        self.assertEqual(Vote.objects.filter(member=member).count(), 0)

    def test_voting_blocked_once_election_has_closed_mid_session(self):
        """Re-checked at POST time, not just at login — covers PART 10's 'voting after election closes'."""
        member = self._approved_member()
        self._login(member)
        self.election.end_datetime = timezone.now() - datetime.timedelta(seconds=1)
        self.election.save(update_fields=["end_datetime"])

        response = self.client.post(reverse("elections:ballot", args=[self.election.pk]), {
            f"position_{self.president.pk}": self.pres_a.pk,
            f"position_{self.secretary.pk}": self.sec_a.pk,
        })
        self.assertContains(response, "Voting is not currently open for this election.")
        self.assertEqual(Vote.objects.filter(member=member).count(), 0)


class DuplicateVotingPreventionTests(BallotTestCase):
    """PART 6 & 10: double voting / page-refresh duplicate votes, enforced at the database level."""

    def test_database_level_constraint_blocks_duplicate_vote_bypassing_the_view(self):
        member = self._approved_member()
        Vote.objects.create(election=self.election, member=member, candidate=self.pres_a)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vote.objects.create(election=self.election, member=member, candidate=self.pres_b)

    def test_resubmitting_the_same_ballot_does_not_create_duplicate_votes(self):
        """
        Simulates a double-click / browser back-button resubmit: two
        submissions carrying the *same* still-valid session marker (the
        realistic race, since the marker is cleared only after the first
        request's response — a genuinely concurrent second request would
        still see it present).
        """
        member = self._approved_member()
        self._login(member)
        payload = {
            f"position_{self.president.pk}": self.pres_a.pk,
            f"position_{self.secretary.pk}": self.sec_a.pk,
        }
        first = self.client.post(reverse("elections:ballot", args=[self.election.pk]), payload)
        self.assertRedirects(first, reverse("elections:vote_success", args=[self.election.pk]))

        # Restore the session marker the first request had already
        # cleared, standing in for a second request that read the session
        # before the first one's cleanup ran.
        session = self.client.session
        session[f"voting_member_{self.election.pk}"] = member.pk
        session.save()

        second = self.client.post(reverse("elections:ballot", args=[self.election.pk]), payload)
        self.assertRedirects(second, reverse("elections:vote_success", args=[self.election.pk]))

        self.assertEqual(Vote.objects.filter(election=self.election, member=member).count(), 2)

    def test_partial_ballot_failure_in_one_atomic_block_rolls_back_entirely(self):
        """
        Directly exercises the same atomic-block pattern ballot_view uses
        for the whole submission: if one position's Vote insert violates
        the uniqueness constraint (standing in for a concurrent request
        that landed first), an otherwise-valid Vote for a *different*
        position in the same block must not survive either — the
        transaction is genuinely all-or-nothing.
        """
        member = self._approved_member()
        # Stands in for a write that already landed for just one position
        # (e.g. from a concurrent request) — secretary already has a vote.
        Vote.objects.create(election=self.election, member=member, candidate=self.sec_a)

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Vote.objects.create(election=self.election, member=member, candidate=self.pres_a)  # would succeed alone
                Vote.objects.create(election=self.election, member=member, candidate=self.sec_b)  # violates the constraint

        # Because both inserts were in the same atomic() block, the
        # otherwise-valid president vote must not have survived either.
        votes = Vote.objects.filter(election=self.election, member=member)
        self.assertEqual(votes.count(), 1)
        self.assertEqual(votes.get().candidate, self.sec_a)
