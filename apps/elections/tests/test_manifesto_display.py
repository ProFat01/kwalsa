import datetime

from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class ManifestoDisplayTests(MediaIsolatedTestCase):
    """
    New behavior added by the Public Website module: PART 5 requires
    manifestos on the election pages. Voting/validation logic itself is
    untouched (see ELECTION_MODULE.md's test suite for that coverage) —
    these tests only cover the new display behavior.
    """

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
        cls.candidate = Candidate.objects.create(
            election=cls.election, position=cls.president, name="Aisha Bello",
            manifesto="I will improve welfare services for every member.",
        )

        cls.member = Member.objects.create(
            association=cls.association, full_name="Voter", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=cls.member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        cls.member.refresh_from_db()

    def test_election_detail_page_shows_manifesto(self):
        response = self.client.get(reverse("elections:election_detail", args=[self.election.pk]))
        self.assertContains(response, "Aisha Bello")
        self.assertContains(response, "I will improve welfare services for every member.")

    def test_election_detail_page_handles_candidate_with_no_manifesto(self):
        Candidate.objects.create(election=self.election, position=self.president, name="No Manifesto Candidate")
        response = self.client.get(reverse("elections:election_detail", args=[self.election.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "No Manifesto Candidate")

    def test_ballot_page_shows_manifesto_next_to_candidate(self):
        self.client.post(reverse("elections:voting_login", args=[self.election.pk]), {
            "method": "membership_id", "membership_id": self.member.membership_id, "phone_number": self.member.phone_number,
        })
        response = self.client.get(reverse("elections:ballot", args=[self.election.pk]))
        self.assertContains(response, "Aisha Bello")
        self.assertContains(response, "I will improve welfare services for every member.")

    def test_ballot_radio_inputs_still_submit_correctly_with_manual_markup(self):
        """The hand-rendered radio inputs (added for manifesto display) must still produce a working, valid submission."""
        self.client.post(reverse("elections:voting_login", args=[self.election.pk]), {
            "method": "membership_id", "membership_id": self.member.membership_id, "phone_number": self.member.phone_number,
        })
        response = self.client.post(
            reverse("elections:ballot", args=[self.election.pk]),
            {f"position_{self.president.pk}": self.candidate.pk},
        )
        self.assertRedirects(response, reverse("elections:vote_success", args=[self.election.pk]))
