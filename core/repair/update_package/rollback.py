"""Rollback helpers for update package backups."""

from __future__ import annotations

import json
import os
import shutil
from dataclasses import dataclass
from pathlib import Path

from .verify import PROJECT_ROOT, UpdatePackageError


@dataclass(frozen=True)
class RollbackResult:
    backup_dir: Path
    restored: list[str]


def rollback_latest_update(*, project_root: Path | None = None) -> RollbackResult:
    root = (project_root or PROJECT_ROOT).resolve()
    backup_root = root / "backup"
    backups = sorted(path for path in backup_root.glob("*") if path.is_dir())
    if not backups:
        raise UpdatePackageError("rollback_unavailable", "No update backup is available")
    backup_dir = backups[-1]
    manifest_path = backup_dir / "update_backup_manifest.json"
    try:
        targets = json.loads(manifest_path.read_text(encoding="utf-8")).get("targets", [])
    except (OSError, json.JSONDecodeError) as exc:
        raise UpdatePackageError("rollback_unavailable", "Latest backup manifest is invalid") from exc
    restored: list[str] = []
    for rel in targets:
        src = backup_dir / rel
        dst = root / rel
        if not src.exists():
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        staging = dst.with_name(f".{dst.name}.rollback-tmp")
        shutil.copy2(src, staging)
        os.replace(staging, dst)
        restored.append(rel)
    return RollbackResult(backup_dir=backup_dir, restored=restored)
