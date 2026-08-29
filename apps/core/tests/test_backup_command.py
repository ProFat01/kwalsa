import sqlite3
import tarfile
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import SimpleTestCase, override_settings


def _make_real_sqlite_file():
    """
    Django's test runner uses an in-memory SQLite database by default —
    there's no real file on disk to back up, and backup_db correctly
    refuses to operate on one (see its ENGINE/file-existence checks).
    These tests therefore create their own throwaway, real, on-disk
    SQLite file with a minimal schema and point settings.DATABASES at it
    via override_settings, rather than going through Django's ORM/normal
    TestCase database at all.
    """
    db_path = Path(tempfile.mkdtemp(prefix="sams_test_realdb_")) / "test.sqlite3"
    conn = sqlite3.connect(str(db_path))
    conn.execute("CREATE TABLE core_association (id INTEGER PRIMARY KEY, short_name TEXT)")
    conn.execute("INSERT INTO core_association (id, short_name) VALUES (1, 'MSA')")
    conn.commit()
    conn.close()
    return db_path


class BackupCommandTests(SimpleTestCase):
    databases = []  # this TestCase deliberately never touches Django's own test database

    def test_backup_creates_valid_restorable_database_copy(self):
        db_path = _make_real_sqlite_file()
        backup_dir = Path(tempfile.mkdtemp(prefix="sams_test_backups_"))

        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}},
            BACKUP_DIR=backup_dir,
        ):
            call_command("backup_db", "--no-media", verbosity=0)

        run_dirs = list(backup_dir.iterdir())
        self.assertEqual(len(run_dirs), 1)
        backup_db_path = run_dirs[0] / "db.sqlite3"
        self.assertTrue(backup_db_path.exists())

        conn = sqlite3.connect(str(backup_db_path))
        cur = conn.cursor()
        cur.execute("PRAGMA integrity_check;")
        self.assertEqual(cur.fetchone(), ("ok",))
        cur.execute("SELECT short_name FROM core_association WHERE id = 1")
        self.assertEqual(cur.fetchone(), ("MSA",))
        conn.close()

    def test_backup_includes_media_archive_by_default(self):
        db_path = _make_real_sqlite_file()
        backup_dir = Path(tempfile.mkdtemp(prefix="sams_test_backups_"))
        media_dir = Path(tempfile.mkdtemp(prefix="sams_test_media_"))
        media_file = media_dir / "members" / "passports" / "test.jpg"
        media_file.parent.mkdir(parents=True, exist_ok=True)
        media_file.write_bytes(b"fake image data")

        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}},
            BACKUP_DIR=backup_dir,
            MEDIA_ROOT=media_dir,
        ):
            call_command("backup_db", verbosity=0)

        run_dir = next(backup_dir.iterdir())
        media_archive = run_dir / "media.tar.gz"
        self.assertTrue(media_archive.exists())
        with tarfile.open(media_archive) as tar:
            names = tar.getnames()
        self.assertTrue(any("test.jpg" in name for name in names))

    def test_no_media_flag_skips_media_archive(self):
        db_path = _make_real_sqlite_file()
        backup_dir = Path(tempfile.mkdtemp(prefix="sams_test_backups_"))

        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}},
            BACKUP_DIR=backup_dir,
        ):
            call_command("backup_db", "--no-media", verbosity=0)

        run_dir = next(backup_dir.iterdir())
        self.assertFalse((run_dir / "media.tar.gz").exists())

    def test_retention_removes_oldest_backups_beyond_keep_count(self):
        db_path = _make_real_sqlite_file()
        backup_dir = Path(tempfile.mkdtemp(prefix="sams_test_backups_"))
        for name in ["20260101_000000", "20260102_000000", "20260103_000000"]:
            (backup_dir / name).mkdir(parents=True)

        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": str(db_path)}},
            BACKUP_DIR=backup_dir,
        ):
            call_command("backup_db", "--no-media", "--keep", "2", verbosity=0)

        remaining = sorted(p.name for p in backup_dir.iterdir())
        self.assertEqual(len(remaining), 2)
        self.assertNotIn("20260101_000000", remaining)
        self.assertNotIn("20260102_000000", remaining)
        self.assertIn("20260103_000000", remaining)

    def test_non_sqlite_engine_is_rejected_with_a_clear_message(self):
        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.postgresql", "NAME": "irrelevant"}},
        ):
            with self.assertRaisesMessage(Exception, "only knows how to back up SQLite"):
                call_command("backup_db", "--no-media", verbosity=0)

    def test_missing_database_file_raises_clear_error(self):
        with override_settings(
            DATABASES={"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": "/nonexistent/path/db.sqlite3"}},
        ):
            with self.assertRaisesMessage(Exception, "not found"):
                call_command("backup_db", "--no-media", verbosity=0)
