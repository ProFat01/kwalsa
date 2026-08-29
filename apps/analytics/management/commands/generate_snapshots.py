"""
PART 9: snapshot generation, run on demand (cron/scheduled task in
production, or by hand) rather than on every dashboard request — the
dashboards themselves read live from Member/Vote (see services.py's
module docstring for why), so this command exists purely to populate
MembershipSnapshot/AgeDistributionSnapshot/ElectionResultSnapshot for
historical trend tracking and as the "future optimization" path the
spec asks to leave open.

    python manage.py generate_snapshots                  # everything
    python manage.py generate_snapshots --membership-only
    python manage.py generate_snapshots --elections-only
    python manage.py generate_snapshots --election-id 3  # one election only
"""
from django.core.management.base import BaseCommand

from apps.analytics import services
from apps.core.models import Association
from apps.elections.models import Election


class Command(BaseCommand):
    help = "Generate membership, age-distribution, and election-result snapshots."

    def add_arguments(self, parser):
        parser.add_argument("--membership-only", action="store_true", help="Skip election snapshots.")
        parser.add_argument("--elections-only", action="store_true", help="Skip membership/age snapshots.")
        parser.add_argument("--election-id", type=int, default=None, help="Only snapshot this one election.")

    def handle(self, *args, **options):
        if not options["elections_only"]:
            for association in Association.objects.all():
                services.generate_membership_snapshot(association)
                services.generate_age_distribution_snapshot(association)
                self.stdout.write(self.style.SUCCESS(f"Membership/age snapshot generated for {association}."))

        if not options["membership_only"]:
            elections = Election.objects.all()
            if options["election_id"] is not None:
                elections = elections.filter(pk=options["election_id"])
            count = 0
            for election in elections:
                services.generate_election_result_snapshots(election)
                count += 1
            self.stdout.write(self.style.SUCCESS(f"Election result snapshots generated for {count} election(s)."))
