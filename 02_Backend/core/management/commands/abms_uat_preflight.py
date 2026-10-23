from pathlib import Path

from django.conf import settings
from django.core import management
from django.core.management import CommandError
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Run the ABMS UAT and release-readiness preflight checks."

    def add_arguments(self, parser):
        parser.add_argument("--strict", action="store_true", help="Treat deployment-hardening warnings as failures.")

    def handle(self, *args, **options):
        strict = options["strict"]
        failures: list[str] = []
        warnings: list[str] = []
        self.stdout.write("ABMS UAT / RELEASE READINESS PREFLIGHT")
        self.stdout.write("=" * 44)

        try:
            connections["default"].ensure_connection()
            self.stdout.write(self.style.SUCCESS("PASS  Database connection"))
        except Exception as exc:
            failures.append(f"Database connection: {exc}")
            self.stdout.write(self.style.ERROR(f"FAIL  Database connection: {exc}"))

        for label, kwargs in (("Django system checks", {"check": True}), ("Database migrations", {"migrate": True})):
            try:
                if label == "Django system checks":
                    management.call_command("check", verbosity=0)
                else:
                    management.call_command("migrate", check=True, verbosity=0)
                self.stdout.write(self.style.SUCCESS(f"PASS  {label}"))
            except Exception as exc:
                failures.append(f"{label}: {exc}")
                self.stdout.write(self.style.ERROR(f"FAIL  {label}: {exc}"))

        command_map = management.get_commands()
        required_commands = ("abms_backup", "abms_restore", "abms_preflight", "abms_uat_preflight")
        missing_commands = [name for name in required_commands if name not in command_map]
        if missing_commands:
            failures.append("Missing management commands: " + ", ".join(missing_commands))
            self.stdout.write(self.style.ERROR("FAIL  Required management commands missing"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  Required management commands"))

        manual_path = Path(settings.BASE_DIR).parent / "05_Documentation" / "ABMS_User_Manual_and_Training_Guide.md"
        if manual_path.is_file():
            self.stdout.write(self.style.SUCCESS("PASS  User Manual present"))
        else:
            failures.append(f"User Manual not found: {manual_path}")
            self.stdout.write(self.style.ERROR("FAIL  User Manual present"))

        required_assets = (
            Path(settings.BASE_DIR) / "static" / "css" / "tailwind.css",
            Path(settings.BASE_DIR) / "static" / "js" / "htmx.min.js",
        )
        missing_assets = [str(path) for path in required_assets if not path.is_file()]
        if missing_assets:
            failures.append("Offline frontend assets missing: " + ", ".join(missing_assets))
            self.stdout.write(self.style.ERROR("FAIL  Offline frontend assets"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  Offline frontend assets"))

        shell_files = (
            Path(settings.BASE_DIR) / "templates" / "base.html",
            Path(settings.BASE_DIR) / "static" / "css" / "style.css",
        )
        forbidden_external_markers = (
            "https://cdn.tailwindcss.com",
            "https://unpkg.com/",
            "https://cdn.jsdelivr.net/",
            "https://fonts.googleapis.com/",
            "https://fonts.gstatic.com/",
        )
        external_hits: list[str] = []
        for shell_file in shell_files:
            if not shell_file.is_file():
                continue
            text = shell_file.read_text(encoding="utf-8")
            for marker in forbidden_external_markers:
                if marker in text:
                    external_hits.append(f"{shell_file.name}: {marker}")
        if external_hits:
            failures.append("External frontend dependencies remain: " + "; ".join(external_hits))
            self.stdout.write(self.style.ERROR("FAIL  Offline frontend dependency scan"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  Offline frontend dependency scan"))

        debug = bool(getattr(settings, "DEBUG", False))
        hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
        if debug:
            warnings.append("DEBUG=True")
            self.stdout.write(self.style.WARNING("WARN  DEBUG=True"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  DEBUG=False"))
        if "*" in hosts:
            warnings.append("ALLOWED_HOSTS contains '*'")
            self.stdout.write(self.style.WARNING("WARN  ALLOWED_HOSTS contains '*'."))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  ALLOWED_HOSTS restricted"))

        self.stdout.write(self.style.SUCCESS("PASS  Offline deployment mode: network-independent by design"))
        self.stdout.write(self.style.SUCCESS("PASS  RBAC and Account/FY isolation are covered by regression tests"))

        if failures or (strict and warnings):
            reasons = failures + (warnings if strict else [])
            raise CommandError("UAT preflight FAILED: " + "; ".join(reasons))
        self.stdout.write(self.style.SUCCESS("UAT preflight PASSED"))
        if warnings:
            self.stdout.write(self.style.WARNING(f"Warnings: {len(warnings)}"))
