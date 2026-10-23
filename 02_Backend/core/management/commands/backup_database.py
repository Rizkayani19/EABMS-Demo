import os
import sqlite3
import time
from datetime import datetime
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import connections


class Command(BaseCommand):
    help = "Automated database backup with strict file retention (default: 10-minute interval, 1,000 backups retained)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--interval",
            type=int,
            default=600,
            help="Interval in seconds between automated backups when running in daemon mode (default: 600s / 10 minutes).",
        )
        parser.add_argument(
            "--retention",
            type=int,
            default=1000,
            help="Maximum number of backups to retain before pruning oldest snapshots (default: 1000).",
        )
        parser.add_argument(
            "--daemon",
            action="store_true",
            help="Run continuously in the background, executing backups every interval seconds.",
        )
        parser.add_argument(
            "--output-dir",
            type=str,
            default=None,
            help="Custom directory to store backups (defaults to 02_Backend/backups/).",
        )
        parser.add_argument(
            "--quiet",
            action="store_true",
            help="Suppress operational messages to stdout.",
        )

    def perform_backup(self, backup_dir: Path, fund_code: str = "") -> Path:
        backup_dir.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = f"backup_{fund_code}_" if fund_code else "abms_db_"
        target_path = backup_dir / f"{prefix}{timestamp}.sqlite3"

        db_conn = connections["default"]
        if db_conn.vendor == "sqlite":
            db_path = Path(settings.DATABASES["default"]["NAME"])
            if not db_path.exists():
                raise FileNotFoundError(f"Source database file not found: {db_path}")

            # Use SQLite Online Backup API for atomic, non-blocking, zero-overhead snapshot
            src = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
            dst = sqlite3.connect(str(target_path))
            try:
                src.backup(dst)
            finally:
                dst.close()
                src.close()
        else:
            # Fallback for other database engines
            from django.core import management
            target_json = target_path.with_suffix(".json")
            with target_json.open("w", encoding="utf-8") as f:
                management.call_command(
                    "dumpdata",
                    natural_foreign=True,
                    natural_primary=True,
                    exclude=["admin.logentry", "sessions"],
                    stdout=f,
                )
            target_path = target_json

        return target_path

    def prune_old_backups(self, backup_dir: Path, retention: int) -> int:
        if retention <= 0:
            return 0

        # Scan for backup files (both sqlite3 and json fallbacks)
        backups = [
            p for p in backup_dir.iterdir()
            if p.is_file() and (
                p.name.startswith("abms_db_") or 
                p.name.startswith("backup_") or 
                p.suffix in [".sqlite3", ".json", ".abmsbackup"]
            )
        ]

        # Sort by mtime descending (newest first)
        backups.sort(key=lambda p: p.stat().st_mtime, reverse=True)

        pruned_count = 0
        if len(backups) > retention:
            to_delete = backups[retention:]
            for p in to_delete:
                try:
                    p.unlink()
                    pruned_count += 1
                except OSError as e:
                    self.stderr.write(f"Warning: Failed to delete {p.name}: {e}")

        return pruned_count

    def handle(self, *args, **options):
        interval = options["interval"]
        retention = options["retention"]
        daemon_mode = options["daemon"]
        quiet = options["quiet"]

        fund_code = getattr(settings, "ABMS_FUND", "") or os.environ.get("ABMS_FUND", "NGL").strip().upper()

        if options["output_dir"]:
            backup_dir = Path(options["output_dir"]).resolve()
        else:
            folder_name = f"backup_{fund_code}" if fund_code else "backups"
            backup_dir = Path(settings.BASE_DIR) / folder_name

        if not quiet:
            self.stdout.write(self.style.SUCCESS("ABMS Automated Database Backup Engine"))
            self.stdout.write(f"Target Directory: {backup_dir}")
            self.stdout.write(f"Retention Limit: Last {retention} backups")
            if daemon_mode:
                self.stdout.write(f"Mode: Background Daemon (Interval: {interval}s / {interval // 60}m)")
            else:
                self.stdout.write("Mode: Single Snapshot Execution")

        while True:
            try:
                snapshot = self.perform_backup(backup_dir, fund_code=fund_code)
                pruned = self.prune_old_backups(backup_dir, retention)
                if not quiet:
                    size_kb = snapshot.stat().st_size / 1024
                    self.stdout.write(
                        f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] "
                        f"Snapshot created: {snapshot.name} ({size_kb:.1f} KB)"
                    )
                    if pruned > 0:
                        self.stdout.write(f"  Pruned {pruned} old backup(s) to adhere to {retention} retention limit.")
            except Exception as exc:
                self.stderr.write(f"Backup failed: {exc}")

            if not daemon_mode:
                break

            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                if not quiet:
                    self.stdout.write("\nBackup daemon stopped by user.")
                break
