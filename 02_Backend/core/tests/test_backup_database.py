import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase


class BackupDatabaseCommandTests(TestCase):
    def test_backup_and_retention(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            backup_dir = Path(tmpdir)

            # Run backup 3 times into temp dir with retention 2
            call_command("backup_database", output_dir=str(backup_dir), retention=2, quiet=True)
            call_command("backup_database", output_dir=str(backup_dir), retention=2, quiet=True)
            call_command("backup_database", output_dir=str(backup_dir), retention=2, quiet=True)

            files = list(backup_dir.iterdir())
            self.assertLessEqual(len(files), 2, "Pruning should retain no more than retention count")
