"""Apply verified update.zip packages with locking, backup, and pending replace."""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from types import TracebackType
from typing import Any

from .paths import UnsafeUpdatePath, normalize_update_path
from .verify import (
    PACKAGE_ID_RE,
    PROJECT_ROOT,
    UpdatePackageError,
    VerificationResult,
    _validate_zip_entries,
    verify_update_package,
)


@dataclass(frozen=True)
class ApplyResult:
    package_id: str
    applied: list[str]
    backup_dir: Path | None
    pending_path: Path | None = None


class _UpdateLock:
    def __init__(self, lock_path: Path) -> None:
        self.lock_path = lock_path
        self.file = None

    def __enter__(self) -> _UpdateLock:
        self.lock_path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.lock_path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            self.file.close()
            raise UpdatePackageError("update_in_progress", "Another update is already in progress", status=409) from exc
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if self.file is None:
            return
        with contextlib.suppress(OSError):
            if os.name == "nt":
                import msvcrt

                self.file.seek(0)
                msvcrt.locking(self.file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                fcntl.flock(self.file.fileno(), fcntl.LOCK_UN)
        self.file.close()


def apply_update_package(
    zip_path: Path,
    *,
    project_root: Path | None = None,
    current_version: str = "0.0.0",
    current_schema_version: int = 0,
    after_extract: Callable[[Path], None] | None = None,
    replace_func: Callable[[Path, Path], None] = os.replace,
    force_pending_on_replace_error: bool = False,
) -> ApplyResult:
    root = (project_root or PROJECT_ROOT).resolve()
    data_dir = root / "data"
    with _UpdateLock(data_dir / "locks" / "update_apply.lock"):
        verification = verify_update_package(
            zip_path,
            project_root=root,
            current_version=current_version,
            current_schema_version=current_schema_version,
        )
        package_id = str(verification.manifest["package_id"])
        _validate_package_id(package_id)
        tmp_parent = root / "tmp"
        tmp_parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix=f"update_apply_{package_id}_", dir=tmp_parent) as tmp:
            extract_dir = Path(tmp)
            with zipfile.ZipFile(zip_path) as zf:
                _extract_verified_zip(zf, extract_dir)
            if after_extract:
                after_extract(extract_dir)
            _verify_extracted_hashes(extract_dir, verification)
            backup_dir = _backup_targets(root, sorted(set(verification.file_operations + verification.patch_operations)))
            applied: list[str] = []
            pending: list[dict[str, str]] = []
            targets = sorted(set(verification.file_operations + verification.patch_operations))
            try:
                for operation in verification.manifest["operations_order"]:
                    if operation == "files":
                        _apply_files(
                            root,
                            extract_dir,
                            verification.file_operations,
                            applied,
                            pending,
                            replace_func=replace_func,
                            force_pending_on_replace_error=force_pending_on_replace_error,
                        )
                    elif operation == "patch":
                        _apply_patch(
                            root,
                            extract_dir / "patch.diff",
                            verification.patch_operations,
                            applied,
                            pending,
                            replace_func=replace_func,
                            force_pending_on_replace_error=force_pending_on_replace_error,
                        )
                pending_path = _write_pending(root, package_id, pending) if pending else None
            except Exception:
                _restore_applied_files(root, backup_dir, applied)
                _cleanup_update_staging_files(root, targets)
                raise
            return ApplyResult(package_id=package_id, applied=applied, backup_dir=backup_dir, pending_path=pending_path)


def _validate_package_id(package_id: str) -> None:
    if PACKAGE_ID_RE.fullmatch(package_id) is None:
        raise UpdatePackageError("manifest_invalid", "package_id is invalid")


def _extract_verified_zip(zf: zipfile.ZipFile, extract_dir: Path) -> None:
    infos = zf.infolist()
    _validate_zip_entries(infos)
    for info in infos:
        if info.is_dir():
            continue
        target = extract_dir / _relative_update_path(info.filename)
        target.parent.mkdir(parents=True, exist_ok=True)
        with zf.open(info, "r") as src, target.open("wb") as dst:
            shutil.copyfileobj(src, dst)


def _restore_applied_files(project_root: Path, backup_dir: Path, applied: list[str]) -> None:
    for rel in reversed(applied):
        relative = _relative_update_path(rel)
        dst = project_root / relative
        backup = backup_dir / relative
        if backup.exists():
            dst.parent.mkdir(parents=True, exist_ok=True)
            staging = dst.with_name(f".{dst.name}.rollback-tmp")
            shutil.copy2(backup, staging)
            os.replace(staging, dst)
        else:
            with contextlib.suppress(OSError):
                dst.unlink()


def _cleanup_update_staging_files(project_root: Path, targets: list[str]) -> None:
    for rel in targets:
        dst = project_root / _relative_update_path(rel)
        staging = dst.with_name(f".{dst.name}.update-tmp")
        with contextlib.suppress(OSError):
            staging.unlink()


def _verify_extracted_hashes(extract_dir: Path, verification: VerificationResult) -> None:
    entries = verification.signed_manifest.get("entries", {})
    for name, expected in entries.items():
        path = extract_dir / _relative_update_path(name)
        if not path.is_file():
            raise UpdatePackageError("extracted_hash_mismatch", f"Extracted file is missing: {name}")
        digest = _sha256_file(path)
        if expected != f"sha256:{digest}":
            raise UpdatePackageError("extracted_hash_mismatch", f"Extracted file hash mismatch: {name}")


def _backup_targets(project_root: Path, targets: list[str]) -> Path:
    backup_dir = project_root / "backup" / datetime.now(tz=UTC).astimezone().strftime("%Y%m%d-%H%M%S")
    for rel in targets:
        relative = _relative_update_path(rel)
        src = project_root / relative
        if src.exists():
            dst = backup_dir / relative
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
    backup_dir.mkdir(parents=True, exist_ok=True)
    manifest = {"created_at": datetime.now(UTC).isoformat(), "targets": targets}
    (backup_dir / "update_backup_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return backup_dir


def _apply_patch(
    project_root: Path,
    patch_path: Path,
    targets: list[str],
    applied: list[str],
    pending: list[dict[str, str]],
    *,
    replace_func: Callable[[Path, Path], None],
    force_pending_on_replace_error: bool,
) -> None:
    patches = _parse_unified_diff(patch_path.read_text(encoding="utf-8"))
    if sorted(patches) != sorted(targets):
        raise UpdatePackageError("conflicting_operation", "patch.diff targets changed after verification")
    for rel, hunks in patches.items():
        dst = project_root / _relative_update_path(rel)
        original = dst.read_text(encoding="utf-8").splitlines(keepends=True) if dst.exists() else []
        patched = _apply_hunks(original, hunks, rel)
        dst.parent.mkdir(parents=True, exist_ok=True)
        staging = dst.with_name(f".{dst.name}.update-tmp")
        staging.write_text("".join(patched), encoding="utf-8")
        try:
            replace_func(staging, dst)
            applied.append(rel)
        except PermissionError:
            if os.name != "nt" and not force_pending_on_replace_error:
                raise
            pending.append({"src": str(staging), "dst": str(dst)})


def _parse_unified_diff(text: str) -> dict[str, list[tuple[int, list[str]]]]:
    lines = text.splitlines(keepends=True)
    patches: dict[str, list[tuple[int, list[str]]]] = {}
    i = 0
    current: str | None = None
    while i < len(lines):
        line = lines[i]
        if line.startswith("--- "):
            i += 1
            if i >= len(lines) or not lines[i].startswith("+++ "):
                raise UpdatePackageError("invalid_patch", "patch.diff has invalid file header")
            raw_path = lines[i][4:].rstrip("\r\n").split("\t", 1)[0]
            current = _normalize_patch_path(raw_path)
            patches.setdefault(current, [])
            i += 1
            continue
        if line.startswith("@@ "):
            if current is None:
                raise UpdatePackageError("invalid_patch", "patch.diff hunk appears before file header")
            old_start = _parse_hunk_old_start(line)
            i += 1
            hunk: list[str] = []
            while i < len(lines) and not lines[i].startswith(("--- ", "@@ ")):
                hunk.append(lines[i])
                i += 1
            patches[current].append((old_start, hunk))
            continue
        i += 1
    return patches


def _normalize_patch_path(value: str) -> str:
    if value == "/dev/null":
        return value
    if value.startswith(("a/", "b/")):
        value = value[2:]
    if value == "/dev/null":
        raise UpdatePackageError("unsupported_operation", "Deleting files through patch.diff is not supported")
    return _relative_update_path(value).as_posix()


def _parse_hunk_old_start(header: str) -> int:
    try:
        old_part = header.split(" ", 2)[1]
        return int(old_part.removeprefix("-").split(",", 1)[0])
    except (IndexError, ValueError) as exc:
        raise UpdatePackageError("invalid_patch", "patch.diff has invalid hunk header") from exc


def _apply_hunks(original: list[str], hunks: list[tuple[int, list[str]]], rel: str) -> list[str]:
    output: list[str] = []
    src_index = 0
    for old_start, hunk_lines in hunks:
        hunk_index = max(old_start - 1, 0)
        if hunk_index < src_index:
            raise UpdatePackageError("invalid_patch", f"Overlapping patch hunk: {rel}")
        output.extend(original[src_index:hunk_index])
        src_index = hunk_index
        for raw in hunk_lines:
            if raw.startswith(" "):
                expected = raw[1:]
                if src_index >= len(original) or original[src_index] != expected:
                    raise UpdatePackageError("invalid_patch", f"Patch context mismatch: {rel}")
                output.append(original[src_index])
                src_index += 1
            elif raw.startswith("-"):
                expected = raw[1:]
                if src_index >= len(original) or original[src_index] != expected:
                    raise UpdatePackageError("invalid_patch", f"Patch removal mismatch: {rel}")
                src_index += 1
            elif raw.startswith("+"):
                output.append(raw[1:])
            elif raw.startswith("\\ No newline at end of file"):
                continue
            else:
                raise UpdatePackageError("invalid_patch", f"Unsupported patch line: {rel}")
    output.extend(original[src_index:])
    return output


def _apply_files(
    project_root: Path,
    extract_dir: Path,
    targets: list[str],
    applied: list[str],
    pending: list[dict[str, str]],
    *,
    replace_func: Callable[[Path, Path], None],
    force_pending_on_replace_error: bool,
) -> None:
    for rel in targets:
        relative = _relative_update_path(rel)
        src = extract_dir / "files" / relative
        dst = project_root / relative
        dst.parent.mkdir(parents=True, exist_ok=True)
        staging = dst.with_name(f".{dst.name}.update-tmp")
        shutil.copy2(src, staging)
        try:
            replace_func(staging, dst)
            applied.append(rel)
        except PermissionError:
            if os.name != "nt" and not force_pending_on_replace_error:
                raise
            pending.append({"src": str(staging), "dst": str(dst)})


def _write_pending(project_root: Path, package_id: str, pending: list[dict[str, str]]) -> Path:
    _validate_package_id(package_id)
    pending_dir = project_root / "data" / "update_pending"
    pending_dir.mkdir(parents=True, exist_ok=True)
    pending_path = pending_dir / f"{package_id}.json"
    payload: dict[str, Any] = {
        "package_id": package_id,
        "created_at": datetime.now(UTC).isoformat(),
        "pending": pending,
    }
    pending_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return pending_path


def _sha256_file(path: Path) -> str:
    h = __import__("hashlib").sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _relative_update_path(value: str) -> Path:
    try:
        return Path(*normalize_update_path(value).split("/"))
    except UnsafeUpdatePath as exc:
        raise UpdatePackageError("unsafe_zip_entry", str(exc)) from exc
