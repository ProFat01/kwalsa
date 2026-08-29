import datetime

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.analytics.models import AgeDistributionSnapshot, ElectionResultSnapshot, MembershipSnapshot
from apps.core.models import Association
from apps.elections.models import Candidate, Election, Position, Vote
from apps.members.models import Member, RegistrationApplication
from apps.members.tests.helpers import MediaIsolatedTestCase, make_image


class GenerateSnapshotsCommandTests(MediaIsolatedTestCase):
    @classmethod
    def setUpTestData(cls):
        cls.association = Association.objects.create(name="Malam Sidi Students Association", short_name="MSA")
        cls.member = Member.objects.create(
            association=cls.association, full_name="A", phone_number="08010000001", nin_number="10000000001",
            date_of_birth="2002-01-01", institution="GSU", course="Chemistry",
            category=Member.Category.UNDERGRADUATE, passport_photo=make_image("p.png"),
        )
        application = RegistrationApplication.objects.create(member=cls.member)
        application.status = RegistrationApplication.Status.APPROVED
        application.save()
        cls.member.refresh_from_db()

        cls.president = Position.objects.create(association=cls.association, title="President")
        now = timezone.now()
        cls.election = Election.objects.create(
            association=cls.association, name="Test Election",
            start_datetime=now - datetime.timedelta(hours=1), end_datetime=now + datetime.timedelta(hours=1),
        )
        cls.election.positions.set([cls.president])
        cls.candidate = Candidate.objects.create(election=cls.election, position=cls.president, name="A")
        Vote.objects.create(election=cls.election, member=cls.member, candidate=cls.candidate)

    def test_default_run_generates_everything(self):
        call_command("generate_snapshots", verbosity=0)
        self.assertEqual(MembershipSnapshot.objects.filter(association=self.association).count(), 1)
        self.assertEqual(AgeDistributionSnapshot.objects.filter(association=self.association).count(), 6)
        self.assertEqual(ElectionResultSnapshot.objects.filter(election=self.election).count(), 1)

    def test_membership_only_skips_election_snapshots(self):
        call_command("generate_snapshots", "--membership-only", verbosity=0)
        self.assertEqual(MembershipSnapshot.objects.count(), 1)
        self.assertEqual(ElectionResultSnapshot.objects.count(), 0)

    def test_elections_only_skips_membership_snapshots(self):
        call_command("generate_snapshots", "--elections-only", verbosity=0)
        self.assertEqual(MembershipSnapshot.objects.count(), 0)
        self.assertEqual(ElectionResultSnapshot.objects.count(), 1)

    def test_election_id_filter_targets_one_election(self):
        other_election = Election.objects.create(
            association=self.association, name="Other Election",
            start_datetime=self.election.start_datetime, end_datetime=self.election.end_datetime,
        )
        other_election.positions.set([self.president])

        call_command("generate_snapshots", "--elections-only", f"--election-id={self.election.pk}", verbosity=0)
        self.assertEqual(ElectionResultSnapshot.objects.filter(election=self.election).count(), 1)
        self.assertEqual(ElectionResultSnapshot.objects.filter(election=other_election).count(), 0)
