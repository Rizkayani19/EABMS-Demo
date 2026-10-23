from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.backup_service import restore_backup, validate_backup


class Command(BaseCommand):
    help = "Validate and safely restore an ABMS offline backup bundle."

    def add_arguments(self, parser):
        parser.add_argument("backup", type=Path, help="Path to .abmsbackup bundle")
        parser.add_argument(
            "--pre-restore-backup",
            type=Path,
            help="Create a current-database backup immediately before restore",
        )
        parser.add_argument(
            "--yes-i-understand",
            action="store_true",
            help="Required confirmation because restore replaces current database contents",
        )
        parser.add_argument("--dry-run", action="store_true", help="Validate only; do not modify the database")

    def handle(self, *args, **options):
        backup = options["backup"]
        try:
            manifest = validate_backup(backup)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Backup validation: PASS ({manifest.get('created_at_utc')})")
        if options["dry_run"]:
            self.stdout.write(self.style.SUCCESS("Dry run complete; database was not changed."))
            return

        if not options["yes_i_understand"]:
            raise CommandError(
                "Restore replaces current database contents. Re-run with --yes-i-understand."
            )
        if options["pre_restore_backup"] is None:
            raise CommandError("A --pre-restore-backup path is required for a safe restore.")

        try:
            restored = restore_backup(backup, pre_restore_backup=options["pre_restore_backup"])
        except (OSError, ValueError, RuntimeError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"ABMS restore complete. Source backup created {restored.get('created_at_utc')}."
            )
        )
