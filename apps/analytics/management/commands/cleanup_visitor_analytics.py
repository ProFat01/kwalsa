"""
v2.1 — deletes PageVisit rows older than the configured retention
period (settings.VISITOR_ANALYTICS_RETENTION_DAYS, default 90).

A management command rather than an automatic scheduled job: this
project has no background worker/cron running by default (deliberately,
for PythonAnywhere Free-tier compatibility — see VISITOR_ANALYTICS.md),
so cleanup is a safe, explicit, re-runnable action instead of relying on
platform scheduling that may or may not be configured.

Run manually or from a PythonAnywhere scheduled task (available even on
the Free tier, once a day is plenty):

    python manage.py cleanup_visitor_analytics
    python manage.py cleanup_visitor_analytics --days 30   # override the configured retention
    python manage.py cleanup_visitor_analytics --dry-run   # report what would be deleted, delete nothing
"""
from django.conf import settings
from django.core.management.base import BaseCommand

from apps.analytics import services
from apps.analytics.models import PageVisit
from django.utils import timezone
from datetime import timedelta


class Command(BaseCommand):
    help = "Delete PageVisit rows older than the configured visitor-analytics retention period."

    def add_arguments(self, parser):
        parser.add_argument(
            "--days", type=int, default=None,
            help="Override settings.VISITOR_ANALYTICS_RETENTION_DAYS for this run.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Report how many rows would be deleted without deleting them.",
        )

    def handle(self, *args, **options):
        retention_days = options["days"] if options["days"] is not None else settings.VISITOR_ANALYTICS_RETENTION_DAYS
        if retention_days < 1:
            self.stderr.write(self.style.ERROR("Retention days must be at least 1."))
            return

        if options["dry_run"]:
            cutoff = timezone.localdate() - timedelta(days=retention_days)
            count = PageVisit.objects.filter(visit_date__lt=cutoff).count()
            self.stdout.write(
                f"Dry run: {count} PageVisit row(s) older than {cutoff.isoformat()} "
                f"({retention_days} day retention) would be deleted."
            )
            return

        deleted_count = services.cleanup_visitor_analytics(retention_days)
        self.stdout.write(
            self.style.SUCCESS(
                f"Deleted {deleted_count} PageVisit row(s) older than {retention_days} days."
            )
        )
