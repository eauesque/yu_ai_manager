"""Snapshot helpers for cumulative extension audits."""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _snapshot_dir() -> Path:
    """Resolve the extension audit snapshot directory lazily via core.paths."""
    from core.paths import data_path
    return data_path("extension_snapshots")


def compute_snapshot(ext_dir: Path) -> dict[str, Any]:
    """Compute a snapshot of extension state for baseline comparison."""
    if not ext_dir.exists():
        return {}

    files: dict[str, str] = {}
    imports: set[str] = set()
    total_size = 0
    for file_path in sorted(ext_dir.rglob("*")):
        if not file_path.is_file():
            continue
        rel = str(file_path.relative_to(ext_dir)).replace("\\", "/")
        content = file_path.read_bytes()
        files[rel] = hashlib.sha256(content).hexdigest()
        total_size += len(content)
        if file_path.suffix == ".py":
            _collect_imports(imports, content)

    permissions = _read_permissions(ext_dir / "extension.json")
    return {
        "files": files,
        "file_count": len(files),
        "total_size": total_size,
        "imports": sorted(imports),
        "permissions": permissions,
        "code_hash": hashlib.sha256(json.dumps(files, sort_keys=True).encode()).hexdigest(),
        "timestamp": time.time(),
    }


def compute_distance(baseline: dict, current: dict) -> dict[str, Any]:
    """Compute cumulative distance between baseline and current state."""
    if not baseline or not current:
        return {"change_rate": 0, "new_imports": [], "file_count_change": 0, "size_change": 0}

    base_files = baseline.get("files", {})
    curr_files = current.get("files", {})
    all_keys = set(base_files.keys()) | set(curr_files.keys())
    changed = sum(1 for key in all_keys if base_files.get(key) != curr_files.get(key))
    base_imports = set(baseline.get("imports", []))
    curr_imports = set(current.get("imports", []))
    return {
        "change_rate": round((changed / len(all_keys)) * 100, 1) if all_keys else 0.0,
        "new_imports": sorted(curr_imports - base_imports),
        "removed_imports": sorted(base_imports - curr_imports),
        "file_count_change": current.get("file_count", 0) - baseline.get("file_count", 0),
        "size_change": current.get("total_size", 0) - baseline.get("total_size", 0),
        "code_hash_changed": baseline.get("code_hash") != current.get("code_hash"),
    }


def save_approval_snapshot(ext_name: str, ext_dir: Path) -> dict:
    """Record snapshot at approval time."""
    snapshot = compute_snapshot(ext_dir)
    if not snapshot:
        return {"ok": False, "error": "Extension directory not found"}

    snapshot_dir = _snapshot_dir()
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    path = snapshot_dir / f"{ext_name}.json"
    path.write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
    logger.info("[ext-audit] Snapshot saved for %s: %d files, %d imports", ext_name, snapshot["file_count"], len(snapshot["imports"]))
    return {"ok": True, "file_count": snapshot["file_count"]}


def load_approval_snapshot(ext_name: str) -> dict | None:
    """Load the approval-time snapshot."""
    path = _snapshot_dir() / f"{ext_name}.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def _collect_imports(imports: set[str], content: bytes) -> None:
    try:
        text = content.decode("utf-8", errors="ignore")
        for line in text.splitlines():
            stripped = line.strip()
            if stripped.startswith("import "):
                imports.add(stripped.split()[1].split(".")[0].split(",")[0])
            elif stripped.startswith("from "):
                parts = stripped.split()
                if len(parts) >= 2:
                    imports.add(parts[1].split(".")[0])
    except Exception:
        # An unreadable file yields no imports, which reads as "imports
        # nothing" -- the most innocent possible snapshot.
        logger.warning("import snapshot did not complete", exc_info=True)


def _read_permissions(manifest_path: Path) -> list[str]:
    if not manifest_path.exists():
        return []
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        perms = manifest.get("permissions", {})
        return sorted(list(perms.get("required", [])) + list(perms.get("optional", [])))
    except Exception:
        return []
