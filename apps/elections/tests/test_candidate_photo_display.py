import datetime

from django.urls import reverse
from django.utils import timezone

from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class CandidatePhotoDisplayTests(MediaIsolatedTestCase):
    """
    ISSUE 2: Candidate.photo must render on Election Detail, Ballot, and
    Results pages. The Voting Login page never lists candidates at all
    (it's a credential form only), so there is nothing to display there
    — audited and confirmed, not a gap.
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

        cls.member = Member.objects.create(
            association=cls.association, full_name="Voter", phone_number="08010000001",
            nin_number="10000000001", date_of_birth="2001-01-01", institution="X", course="Y",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=cls.member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        cls.member.refresh_from_db()

    def _candidate_with_photo(self):
        candidate = Candidate.objects.create(election=self.election, position=self.president, name="Aisha Bello")
        candidate.photo.save("candidate.png", make_image("candidate.png"), save=True)
        return candidate

    def test_photo_displays_on_election_detail_page(self):
        candidate = self._candidate_with_photo()
        response = self.client.get(reverse("elections:election_detail", args=[self.election.pk]))
        self.assertContains(response, candidate.photo.url)

    def test_photo_displays_on_ballot_page(self):
        candidate = self._candidate_with_photo()
        self.client.post(reverse("elections:voting_login", args=[self.election.pk]), {
            "method": "membership_id", "membership_id": self.member.membership_id,
            "phone_number": self.member.phone_number,
        })
        response = self.client.get(reverse("elections:ballot", args=[self.election.pk]))
        self.assertContains(response, candidate.photo.url)

    def test_photo_displays_on_results_page(self):
        candidate = self._candidate_with_photo()
        Vote.objects.create(election=self.election, member=self.member, candidate=candidate)
        response = self.client.get(reverse("elections:results", args=[self.election.pk]))
        self.assertContains(response, candidate.photo.url)

    def test_no_broken_image_when_candidate_has_no_photo(self):
        """Candidates without a photo must not render an empty/broken <img> tag."""
        Candidate.objects.create(election=self.election, position=self.president, name="No Photo Candidate")
        response = self.client.get(reverse("elections:election_detail", args=[self.election.pk]))
        self.assertContains(response, "No Photo Candidate")
        self.assertNotContains(response, 'src=""')
