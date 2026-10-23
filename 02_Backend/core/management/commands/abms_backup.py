from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.backup_service import create_backup, validate_backup


class Command(BaseCommand):
    help = "Create or validate an ABMS offline backup bundle."

    def add_arguments(self, parser):
        parser.add_argument("--output", type=Path, help="Output .abmsbackup path")
        parser.add_argument("--validate", type=Path, help="Validate an existing backup bundle")
        parser.add_argument("--overwrite", action="store_true", help="Allow replacing an existing backup")

    def handle(self, *args, **options):
        validate_path = options.get("validate")
        output = options.get("output")
        overwrite = options.get("overwrite", False)

        if validate_path:
            try:
                manifest = validate_backup(validate_path)
            except (OSError, ValueError) as exc:
                raise CommandError(str(exc)) from exc
            self.stdout.write(self.style.SUCCESS("Backup validation: PASS"))
            self.stdout.write(f"Created: {manifest.get('created_at_utc')}")
            self.stdout.write(f"Database engine: {manifest.get('database_engine')}")
            self.stdout.write(f"Format version: {manifest.get('format_version')}")
            return

        if output is None:
            raise CommandError("Provide --output or --validate.")
        if output.suffix.lower() != ".abmsbackup":
            raise CommandError("Backup output must use the .abmsbackup extension.")

        try:
            backup = create_backup(output, overwrite=overwrite)
            manifest = validate_backup(backup)
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"ABMS backup created and self-validated: {backup}"))
        self.stdout.write(f"Created: {manifest.get('created_at_utc')}")
        self.stdout.write(f"Database engine: {manifest.get('database_engine')}")
        self.stdout.write(f"Format version: {manifest.get('format_version')}")
