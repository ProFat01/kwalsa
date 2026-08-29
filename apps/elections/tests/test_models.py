import datetime

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position


class ElectionStatusTests(TestCase):
    """PART 1: status rules (Upcoming / Active / Closed) and the is_upcoming()/is_active()/is_closed() helpers."""

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def _make_election(self, start_offset, end_offset, **overrides):
        now = timezone.now()
        defaults = dict(
            association=self.association, name="Test Election",
            start_datetime=now + datetime.timedelta(**start_offset),
            end_datetime=now + datetime.timedelta(**end_offset),
        )
        defaults.update(overrides)
        return Election.objects.create(**defaults)

    def test_upcoming_election(self):
        election = self._make_election({"hours": 1}, {"hours": 2})
        self.assertTrue(election.is_upcoming())
        self.assertFalse(election.is_active())
        self.assertFalse(election.is_closed())
        self.assertEqual(election.status, "upcoming")
        self.assertFalse(election.is_voting_open)

    def test_active_election(self):
        election = self._make_election({"hours": -1}, {"hours": 1})
        self.assertFalse(election.is_upcoming())
        self.assertTrue(election.is_active())
        self.assertFalse(election.is_closed())
        self.assertEqual(election.status, "active")
        self.assertTrue(election.is_voting_open)

    def test_closed_election(self):
        election = self._make_election({"hours": -2}, {"hours": -1})
        self.assertFalse(election.is_upcoming())
        self.assertFalse(election.is_active())
        self.assertTrue(election.is_closed())
        self.assertEqual(election.status, "closed")
        self.assertFalse(election.is_voting_open)

    def test_is_voting_open_requires_is_enabled_even_during_active_window(self):
        """is_active() is pure clock logic; is_voting_open also respects the admin's enable/disable switch."""
        election = self._make_election({"hours": -1}, {"hours": 1}, is_enabled=False)
        self.assertTrue(election.is_active())  # clock says active...
        self.assertFalse(election.is_voting_open)  # ...but admin has disabled it

    def test_end_before_start_rejected(self):
        now = timezone.now()
        election = Election(
            association=self.association, name="Bad Election",
            start_datetime=now, end_datetime=now - datetime.timedelta(hours=1),
        )
        with self.assertRaises(ValidationError):
            election.full_clean()


class PositionTests(TestCase):
    """PART 2: position creation, fields, ordering."""

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")

    def test_create_position_with_description_and_display_order(self):
        position = Position.objects.create(
            association=self.association, title="President",
            description="Leads the association", display_order=1,
        )
        self.assertEqual(position.description, "Leads the association")
        self.assertEqual(str(position), "President")

    def test_positions_ordered_by_display_order(self):
        Position.objects.create(association=self.association, title="Treasurer", display_order=3)
        Position.objects.create(association=self.association, title="President", display_order=1)
        Position.objects.create(association=self.association, title="Secretary", display_order=2)
        titles = list(Position.objects.filter(association=self.association).values_list("title", flat=True))
        self.assertEqual(titles, ["President", "Secretary", "Treasurer"])

    def test_duplicate_position_title_per_association_rejected(self):
        Position.objects.create(association=self.association, title="President")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Position.objects.create(association=self.association, title="President")


class CandidateValidationTests(TestCase):
    """PART 3: candidate creation/validation rules."""

    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        cls.president = Position.objects.create(association=cls.association, title="President")
        cls.secretary = Position.objects.create(association=cls.association, title="Secretary")
        now = timezone.now()
        cls.election = Election.objects.create(
            association=cls.association, name="Test Election",
            start_datetime=now, end_datetime=now + datetime.timedelta(hours=1),
        )
        cls.election.positions.set([cls.president])

    def test_candidate_position_must_be_contested_in_election(self):
        """Secretary was never added to election.positions, so a candidate for it must be rejected."""
        candidate = Candidate(election=self.election, position=self.secretary, name="John Doe")
        with self.assertRaises(ValidationError) as ctx:
            candidate.full_clean()
        self.assertIn("position", ctx.exception.message_dict)

    def test_valid_candidate_for_contested_position_accepted(self):
        candidate = Candidate(election=self.election, position=self.president, name="John Doe")
        candidate.full_clean()
        candidate.save()
        self.assertEqual(Candidate.objects.count(), 1)

    def test_duplicate_candidate_name_for_same_position_same_election_rejected(self):
        Candidate.objects.create(election=self.election, position=self.president, name="John Doe")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Candidate.objects.create(election=self.election, position=self.president, name="John Doe")

    def test_same_candidate_name_allowed_in_a_different_election(self):
        """Re-running for the same office in a different election year is fine."""
        Candidate.objects.create(election=self.election, position=self.president, name="John Doe")
        other_election = Election.objects.create(
            association=self.association, name="Next Year's Election",
            start_datetime=timezone.now() + datetime.timedelta(days=365),
            end_datetime=timezone.now() + datetime.timedelta(days=366),
        )
        other_election.positions.set([self.president])
        # Should not raise.
        Candidate.objects.create(election=other_election, position=self.president, name="John Doe")
        self.assertEqual(Candidate.objects.filter(name="John Doe").count(), 2)

    def test_multiple_different_candidates_for_same_position_allowed(self):
        """The whole point of an election — this must NOT be blocked by the duplicate constraint."""
        Candidate.objects.create(election=self.election, position=self.president, name="Candidate A")
        Candidate.objects.create(election=self.election, position=self.president, name="Candidate B")
        self.assertEqual(Candidate.objects.filter(election=self.election, position=self.president).count(), 2)
