"""Portable offline backup/restore service for ABMS.

The service works across the approved PostgreSQL and SQLite configurations
using Django's native serialization plus a ZIP container. Uploaded media is
included when present. Every bundle carries a manifest and SHA-256 checksums
so an operator can validate it before restore.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import django
from django.conf import settings
from django.core import management
from django.db import connections, transaction


FORMAT_VERSION = 1
DATASET_NAME = "database.json"
MANIFEST_NAME = "manifest.json"
MEDIA_DIR_NAME = "media"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_member(relative: str) -> Path:
    """Return a safe relative archive path or reject path traversal."""
    candidate = Path(relative)
    if candidate.is_absolute() or candidate.drive:
        raise ValueError(f"Unsafe archive path: {relative}")
    normalized = Path(*candidate.parts)
    if ".." in normalized.parts:
        raise ValueError(f"Unsafe archive path: {relative}")
    return normalized


def _serialize_database(target: Path) -> None:
    with target.open("w", encoding="utf-8", newline="\n") as handle:
        management.call_command(
            "dumpdata",
            natural_foreign=True,
            natural_primary=True,
            exclude=["admin.logentry", "sessions"],
            stdout=handle,
        )


def _backup_media(root: Path) -> list[str]:
    configured = getattr(settings, "MEDIA_ROOT", None)
    if not configured:
        return []
    media_root = Path(configured)
    if not media_root.exists():
        return []
    copied: list[str] = []
    destination = root / MEDIA_DIR_NAME
    for source in media_root.rglob("*"):
        if not source.is_file():
            continue
        relative = source.relative_to(media_root)
        target = destination / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(str(Path(MEDIA_DIR_NAME) / relative).replace("\\", "/"))
    return copied


def create_backup(output: Path, *, overwrite: bool = False) -> Path:
    output = output.resolve()
    if output.exists() and not overwrite:
        raise FileExistsError(f"Backup already exists: {output}")
    output.parent.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="abms-backup-") as temp_dir:
        root = Path(temp_dir)
        dataset = root / DATASET_NAME
        _serialize_database(dataset)
        media_files = _backup_media(root)

        manifest: dict[str, Any] = {
            "format": "ABMS-OFFLINE-BACKUP",
            "format_version": FORMAT_VERSION,
            "created_at_utc": datetime.now(timezone.utc).isoformat(),
            "django_version": django.get_version(),
            "database_engine": connections["default"].vendor,
            "database_alias": "default",
            "database_file": DATASET_NAME,
            "media_files": media_files,
        }
        manifest["files"] = {
            DATASET_NAME: {"sha256": _sha256(dataset), "size": dataset.stat().st_size}
        }
        for media_relative in media_files:
            media_path = root / media_relative
            manifest["files"][media_relative] = {
                "sha256": _sha256(media_path),
                "size": media_path.stat().st_size,
            }

        manifest_path = root / MANIFEST_NAME
        manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")

        temp_output = output.with_suffix(output.suffix + ".tmp")
        if temp_output.exists():
            temp_output.unlink()
        with zipfile.ZipFile(temp_output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.write(dataset, DATASET_NAME)
            archive.write(manifest_path, MANIFEST_NAME)
            for media_relative in media_files:
                archive.write(root / media_relative, media_relative)
        temp_output.replace(output)
    return output


def validate_backup(backup: Path) -> dict[str, Any]:
    backup = backup.resolve()
    if not backup.is_file():
        raise FileNotFoundError(f"Backup not found: {backup}")

    with zipfile.ZipFile(backup, "r") as archive:
        try:
            manifest = json.loads(archive.read(MANIFEST_NAME).decode("utf-8"))
        except KeyError as exc:
            raise ValueError("Backup manifest is missing") from exc
        except json.JSONDecodeError as exc:
            raise ValueError("Backup manifest is invalid JSON") from exc

        if manifest.get("format") != "ABMS-OFFLINE-BACKUP":
            raise ValueError("Unsupported ABMS backup format")
        if manifest.get("format_version") != FORMAT_VERSION:
            raise ValueError("Unsupported ABMS backup format version")

        files = manifest.get("files") or {}
        if DATASET_NAME not in files:
            raise ValueError("Backup manifest does not contain database.json")

        for relative, metadata in files.items():
            _safe_archive_member(relative)
            if not isinstance(metadata, dict) or not metadata.get("sha256"):
                raise ValueError(f"Invalid checksum metadata: {relative}")
            try:
                data = archive.read(relative)
            except KeyError as exc:
                raise ValueError(f"Backup is missing file: {relative}") from exc
            digest = hashlib.sha256(data).hexdigest()
            if digest != metadata.get("sha256"):
                raise ValueError(f"Checksum mismatch: {relative}")

    return manifest


def _extract_archive_safely(archive: zipfile.ZipFile, root: Path) -> None:
    for member in archive.infolist():
        relative = _safe_archive_member(member.filename)
        target = (root / relative).resolve()
        root_resolved = root.resolve()
        if target != root_resolved and root_resolved not in target.parents:
            raise ValueError(f"Unsafe archive path: {member.filename}")
        if member.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        with archive.open(member, "r") as source, target.open("wb") as destination:
            shutil.copyfileobj(source, destination)


def restore_backup(backup: Path, *, pre_restore_backup: Path | None = None) -> dict[str, Any]:
    manifest = validate_backup(backup)
    backup = backup.resolve()

    if pre_restore_backup is not None:
        pre_restore_backup = pre_restore_backup.resolve()
        if pre_restore_backup == backup:
            raise ValueError("Pre-restore backup path must differ from source backup path")
        create_backup(pre_restore_backup, overwrite=False)

    with tempfile.TemporaryDirectory(prefix="abms-restore-") as temp_dir:
        root = Path(temp_dir)
        with zipfile.ZipFile(backup, "r") as archive:
            _extract_archive_safely(archive, root)

        dataset = root / DATASET_NAME
        if not dataset.is_file():
            raise ValueError("Backup database dataset is missing")

        with transaction.atomic():
            management.call_command("flush", interactive=False, verbosity=0)
            management.call_command("loaddata", str(dataset), verbosity=0)
            connection = connections["default"]
            tables = connection.introspection.table_names()
            models = connection.introspection.installed_models(tables)
            sequence_sql = connection.ops.sequence_reset_sql(
                no_style(), models
            )
            with connection.cursor() as cursor:
                for sql in sequence_sql:
                    cursor.execute(sql)

        configured_media = getattr(settings, "MEDIA_ROOT", None)
        extracted_media = root / MEDIA_DIR_NAME
        if configured_media and extracted_media.exists():
            media_root = Path(configured_media)
            media_root.mkdir(parents=True, exist_ok=True)
            for source in extracted_media.rglob("*"):
                if not source.is_file():
                    continue
                relative = source.relative_to(extracted_media)
                target = media_root / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)

    return manifest


def no_style():
    from django.core.management.color import no_style as django_no_style

    return django_no_style()
