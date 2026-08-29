"""
Part of the production deployment audit: SAMS previously had zero backup
mechanism — confirmed by searching the codebase before writing this.
Run manually or via a scheduled task (PythonAnywhere's "Tasks" tab on
paid tiers, or any cron-like scheduler):

    python manage.py backup_db
    python manage.py backup_db --no-media        # database only, faster
    python manage.py backup_db --keep 14         # retain the last 14 backups instead of the default 7

See PRODUCTION_DEPLOYMENT.md "Backup strategy" for the full restore
procedure and the reasoning behind what's backed up and what isn't.
"""
import shutil
import sqlite3
import tarfile
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Back up the SQLite database (and media/ by default) to BACKUP_DIR, with retention."

    def add_arguments(self, parser):
        parser.add_argument(
            "--no-media", action="store_true",
            help="Skip backing up media/ (passport photos, candidate photos) — database only.",
        )
        parser.add_argument(
            "--keep", type=int, default=7,
            help="Number of most recent backups to retain; older ones are deleted. Default: 7.",
        )

    def handle(self, *args, **options):
        db_config = settings.DATABASES["default"]
        if db_config["ENGINE"] != "django.db.backends.sqlite3":
            raise CommandError(
                "backup_db only knows how to back up SQLite. This project's DATABASES['default'] "
                f"is using {db_config['ENGINE']!r} — use your database engine's own backup tooling "
                "instead (e.g. pg_dump for PostgreSQL)."
            )

        source_path = Path(db_config["NAME"])
        if not source_path.exists():
            raise CommandError(f"Database file not found at {source_path}.")

        backup_root = Path(getattr(settings, "BACKUP_DIR", settings.BASE_DIR / "backups"))
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        run_dir = backup_root / timestamp
        run_dir.mkdir(parents=True, exist_ok=True)

        self._backup_database(source_path, run_dir / "db.sqlite3")
        if not options["no_media"]:
            self._backup_media(run_dir / "media.tar.gz")

        self._enforce_retention(backup_root, keep=options["keep"])
        self.stdout.write(self.style.SUCCESS(f"Backup complete: {run_dir}"))

    def _backup_database(self, source_path, dest_path):
        """
        Uses SQLite's own online backup API (sqlite3.Connection.backup),
        not a raw file copy. A plain `shutil.copy()` of a live SQLite
        file can capture it mid-write — especially under WAL mode (which
        this project's settings enable for exactly the concurrent-vote-
        write scenario described in ARCHITECTURE.md) — and produce a
        corrupt or inconsistent snapshot. The backup API instead takes
        SQLite's own read lock and copies a transactionally consistent
        snapshot, safely, even while the live site is actively serving
        requests against the same file.
        """
        source_conn = sqlite3.connect(str(source_path))
        dest_conn = sqlite3.connect(str(dest_path))
        try:
            source_conn.backup(dest_conn)
        finally:
            dest_conn.close()
            source_conn.close()
        self.stdout.write(f"  Database backed up to {dest_path}")

    def _backup_media(self, dest_path):
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists() or not any(media_root.iterdir()):
            self.stdout.write("  No media files to back up (media/ is empty or missing).")
            return
        with tarfile.open(dest_path, "w:gz") as tar:
            tar.add(media_root, arcname="media")
        self.stdout.write(f"  Media backed up to {dest_path}")

    def _enforce_retention(self, backup_root, keep):
        if not backup_root.exists():
            return
        run_dirs = sorted(
            (p for p in backup_root.iterdir() if p.is_dir()),
            key=lambda p: p.name,
            reverse=True,
        )
        for old_dir in run_dirs[keep:]:
            shutil.rmtree(old_dir, ignore_errors=True)
            self.stdout.write(f"  Removed old backup: {old_dir}")
