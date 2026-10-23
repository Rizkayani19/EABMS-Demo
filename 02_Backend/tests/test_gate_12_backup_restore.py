import io
import json
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core import management
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from core.backup_service import create_backup, validate_backup


class Gate12BackupTests(TestCase):
    @override_settings(MEDIA_ROOT=None)
    def test_backup_bundle_is_created_and_validates(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ABMS_2026-08-21.abmsbackup"
            create_backup(path)
            manifest = validate_backup(path)

            self.assertTrue(path.exists())
            self.assertEqual(manifest["format"], "ABMS-OFFLINE-BACKUP")
            self.assertEqual(manifest["format_version"], 1)
            self.assertIn("database.json", manifest["files"])

    @override_settings(MEDIA_ROOT=None)
    def test_tampered_backup_fails_checksum_validation(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "ABMS_tamper.abmsbackup"
            create_backup(path)

            tampered = Path(temp_dir) / "tampered.abmsbackup"
            with zipfile.ZipFile(path, "r") as source:
                with zipfile.ZipFile(tampered, "w", compression=zipfile.ZIP_DEFLATED) as target:
                    for item in source.infolist():
                        data = source.read(item.filename)
                        if item.filename == "database.json":
                            data += b"\n"
                        target.writestr(item, data)

            with self.assertRaisesRegex(ValueError, "Checksum mismatch"):
                validate_backup(tampered)

    @override_settings(MEDIA_ROOT=None)
    def test_path_traversal_backup_is_rejected(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "unsafe.abmsbackup"
            manifest = {
                "format": "ABMS-OFFLINE-BACKUP",
                "format_version": 1,
                "created_at_utc": "2026-08-21T00:00:00+00:00",
                "files": {
                    "database.json": {"sha256": "44136fa355b3678a1146ad16f7e8649e94fb4fc21fe77e8310c060f61caaff8a"},
                    "../escape.txt": {"sha256": "00"}
                },
            }
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("manifest.json", json.dumps(manifest))
                archive.writestr("database.json", b"{}")
                archive.writestr("../escape.txt", b"unsafe")

            with self.assertRaisesRegex(ValueError, "Unsafe archive path"):
                validate_backup(path)

    @override_settings(MEDIA_ROOT=None)
    def test_restore_command_requires_explicit_confirmation_and_pre_backup(self):
        with TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "ABMS.abmsbackup"
            create_backup(backup)

            with self.assertRaises(CommandError):
                management.call_command("abms_restore", backup)

            with self.assertRaises(CommandError):
                management.call_command("abms_restore", backup, yes_i_understand=True)

    @override_settings(MEDIA_ROOT=None)
    def test_backup_validate_command_reports_pass(self):
        with TemporaryDirectory() as temp_dir:
            backup = Path(temp_dir) / "ABMS.abmsbackup"
            create_backup(backup)
            stdout = io.StringIO()
            management.call_command("abms_backup", validate=backup, stdout=stdout)
            self.assertIn("Backup validation: PASS", stdout.getvalue())

    @override_settings(ALLOWED_HOSTS=["localhost"], DEBUG=False, SECRET_KEY="gate12-test-secret")
    def test_preflight_reports_pass_with_hardened_settings(self):
        stdout = io.StringIO()
        management.call_command("abms_preflight", stdout=stdout)
        self.assertIn("ABMS preflight PASSED", stdout.getvalue())
