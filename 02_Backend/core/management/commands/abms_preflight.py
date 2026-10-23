from pathlib import Path

from django.conf import settings
from django.core import management
from django.core.management.base import BaseCommand, CommandError
from django.db import connections


class Command(BaseCommand):
    help = "Check whether an ABMS installation is ready for controlled offline operation."

    def add_arguments(self, parser):
        parser.add_argument(
            "--strict",
            action="store_true",
            help="Treat production-hardening warnings as failures",
        )

    def handle(self, *args, **options):
        strict = options.get("strict", False)
        failures: list[str] = []
        warnings: list[str] = []

        try:
            connections["default"].ensure_connection()
            self.stdout.write(self.style.SUCCESS("PASS  Database connection"))
        except Exception as exc:
            failures.append(f"Database connection: {exc}")
            self.stdout.write(self.style.ERROR(f"FAIL  Database connection: {exc}"))

        media_root = getattr(settings, "MEDIA_ROOT", None)
        if media_root:
            path = Path(media_root)
            if path.exists() or path.parent.exists():
                self.stdout.write(self.style.SUCCESS(f"PASS  Media root: {path}"))
            else:
                failures.append(f"Media root is unavailable: {path}")
                self.stdout.write(self.style.ERROR(f"FAIL  Media root: {path}"))
        else:
            self.stdout.write("INFO  Media uploads are disabled")

        static_root = getattr(settings, "STATIC_ROOT", None)
        if static_root:
            path = Path(static_root)
            if path.exists():
                self.stdout.write(self.style.SUCCESS(f"PASS  Static root: {path}"))
            else:
                warnings.append(f"Static root does not yet exist: {path}")
                self.stdout.write(self.style.WARNING(f"WARN  Static root missing: {path}"))

        debug = bool(getattr(settings, "DEBUG", False))
        allowed_hosts = list(getattr(settings, "ALLOWED_HOSTS", []))
        secret_key = str(getattr(settings, "SECRET_KEY", ""))
        if debug:
            warnings.append("DEBUG=True")
            self.stdout.write(self.style.WARNING("WARN  DEBUG=True"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  DEBUG=False"))
        if "*" in allowed_hosts:
            warnings.append("ALLOWED_HOSTS contains '*'")
            self.stdout.write(
                self.style.WARNING(
                    "WARN  ALLOWED_HOSTS contains '*'; restrict it for deployed environments"
                )
            )
        else:
            self.stdout.write(self.style.SUCCESS("PASS  ALLOWED_HOSTS is restricted"))
        if not secret_key or "insecure-stage1-foundation-key" in secret_key:
            warnings.append("Django SECRET_KEY appears to be a development/default key")
            self.stdout.write(self.style.WARNING("WARN  SECRET_KEY is not production-hardened"))
        else:
            self.stdout.write(self.style.SUCCESS("PASS  SECRET_KEY is configured"))

        try:
            management.call_command("check", verbosity=0)
            self.stdout.write(self.style.SUCCESS("PASS  Django system checks"))
        except Exception as exc:
            failures.append(f"Django system checks: {exc}")
            self.stdout.write(self.style.ERROR(f"FAIL  Django system checks: {exc}"))

        if failures or (strict and warnings):
            raise CommandError(
                "ABMS preflight FAILED: " + "; ".join(failures or warnings)
            )

        self.stdout.write(self.style.SUCCESS("ABMS preflight PASSED"))
        if warnings:
            self.stdout.write(self.style.WARNING(f"Warnings: {len(warnings)}"))
