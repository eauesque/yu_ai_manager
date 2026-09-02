"""Verify signed update.zip packages before any apply path can run."""

from __future__ import annotations

import hashlib
import json
import logging
import re
import stat
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey

from core.system.safe_mode import is_safe_mode

from .paths import UnsafeUpdatePath, normalize_update_path, update_path_key

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PUBLIC_KEY_PATH = PROJECT_ROOT / "security" / "update_signing_pubkey.pem"
_PUBLIC_KEY_PATHS = [
    PROJECT_ROOT / "security" / "update_signing_pubkey.pem",
    PROJECT_ROOT / "security" / "update_signing_pubkey_previous.pem",
]
ALLOWED_OPERATIONS = {("files",), ("patch",), ("files", "patch"), ("patch", "files")}
REQUIRED_ENTRIES = {"manifest.json", "checksum.sha256", "signature.bin", "signed_manifest.json"}
SIGNATURE_CONTROL_ENTRIES = {"signature.bin", "checksum.sha256", "signed_manifest.json"}
PACKAGE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
MAX_ZIP_ENTRIES = 10000
MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
MAX_ZIP_COMPRESSION_RATIO = 100

_logger = logging.getLogger(__name__)


class UpdatePackageError(Exception):
    """Structured update package failure surfaced by API routes."""

    def __init__(self, code: str, message: str, *, status: int = 400) -> None:
        super().__init__(message)
        self.code = code
        self.status = status


@dataclass(frozen=True)
class VerificationResult:
    zip_path: Path
    manifest: dict[str, Any]
    signed_manifest: dict[str, Any]
    file_operations: list[str]
    patch_operations: list[str]


def verify_update_package(
    zip_path: Path,
    *,
    project_root: Path | None = None,
    current_version: str = "0.0.0",
    current_schema_version: int = 0,
    public_key_path: Path | None = None,
) -> VerificationResult:
    """Verify structure, checksums, Ed25519 signature, and local preconditions."""
    root = (project_root or PROJECT_ROOT).resolve()
    zip_path = zip_path.resolve()
    try:
        with zipfile.ZipFile(zip_path) as zf:
            infos = zf.infolist()
            names = [info.filename for info in infos]
            _validate_zip_entries(infos)
            if not REQUIRED_ENTRIES.issubset(set(names)):
                raise UpdatePackageError("signature_invalid", "Required signed update entries are missing")
            entry_bytes = {info.filename: zf.read(info) for info in infos if not info.is_dir()}
    except UpdatePackageError:
        raise
    except (OSError, zipfile.BadZipFile) as exc:
        raise UpdatePackageError("invalid_zip", f"Invalid update zip: {exc}") from exc

    _verify_checksum_file(entry_bytes)
    signed_bytes = entry_bytes.get("signed_manifest.json")
    signature = entry_bytes.get("signature.bin")
    if signed_bytes is None or signature is None:
        raise UpdatePackageError("signature_invalid", "Signature files are missing")
    public_key_paths = [public_key_path] if public_key_path is not None else _PUBLIC_KEY_PATHS
    _verify_signature(signed_bytes, signature, public_key_paths)

    try:
        signed_manifest = json.loads(signed_bytes.decode("utf-8"))
        manifest = json.loads(entry_bytes["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise UpdatePackageError("invalid_manifest", "Manifest JSON is invalid") from exc
    if signed_manifest.get("manifest") != manifest:
        raise UpdatePackageError("signature_invalid", "signed_manifest.json does not match manifest.json")
    _verify_signed_entry_hashes(entry_bytes, signed_manifest)
    if is_safe_mode():
        _validate_safe_mode_constraints(names, manifest, current_schema_version=current_schema_version)
    _validate_manifest(manifest, current_version=current_version, current_schema_version=current_schema_version)

    file_ops = _files_operations(names)
    patch_ops = _patch_operations(entry_bytes.get("patch.diff"))
    if {update_path_key(path) for path in file_ops} & {update_path_key(path) for path in patch_ops}:
        raise UpdatePackageError("conflicting_operation", "patch.diff and files/ target the same path")
    _validate_target_checksums(manifest, root)

    return VerificationResult(
        zip_path=zip_path,
        manifest=manifest,
        signed_manifest=signed_manifest,
        file_operations=file_ops,
        patch_operations=patch_ops,
    )


def _validate_safe_mode_constraints(
    names: list[str],
    manifest: dict[str, Any],
    *,
    current_schema_version: int,
) -> None:
    operations = manifest.get("operations_order")
    if "patch.diff" in names or (isinstance(operations, list) and "patch" in operations):
        raise UpdatePackageError(
            "patch_forbidden_in_safe_mode",
            "Safe Mode only permits files/ full replacement updates",
            status=403,
        )
    if any(name.startswith("scripts/") for name in names):
        raise UpdatePackageError(
            "scripts_forbidden_in_safe_mode",
            "Safe Mode does not permit update scripts",
            status=403,
        )
    required_schema = manifest.get("required_schema_version")
    if required_schema is not None and int(required_schema) != int(current_schema_version):
        raise UpdatePackageError(
            "migration_forbidden_in_safe_mode",
            "Safe Mode does not permit schema migrations",
            status=403,
        )


def _validate_zip_entries(infos: list[zipfile.ZipInfo]) -> None:
    if len(infos) > MAX_ZIP_ENTRIES:
        raise UpdatePackageError("unsafe_zip_entry", "Update zip has too many entries")
    total_size = 0
    seen: set[str] = set()
    for info in infos:
        total_size += info.file_size
        if total_size > MAX_ZIP_UNCOMPRESSED_BYTES:
            raise UpdatePackageError("unsafe_zip_entry", "Update zip uncompressed size is too large")
        if info.compress_size > 0 and info.file_size / info.compress_size > MAX_ZIP_COMPRESSION_RATIO:
            raise UpdatePackageError("unsafe_zip_entry", f"Suspicious zip compression ratio: {info.filename}")
        name = info.filename
        try:
            key = update_path_key(name.rstrip("/"))
        except UnsafeUpdatePath as exc:
            raise UpdatePackageError("unsafe_zip_entry", str(exc)) from exc
        if key in seen:
            raise UpdatePackageError("unsafe_zip_entry", f"Duplicate zip entry: {name}")
        seen.add(key)
        mode = (info.external_attr >> 16) & 0xFFFF
        if stat.S_ISLNK(mode):
            raise UpdatePackageError("unsafe_zip_entry", f"Symlink zip entry is not allowed: {name}")


def _verify_checksum_file(entry_bytes: dict[str, bytes]) -> None:
    try:
        text = entry_bytes["checksum.sha256"].decode("utf-8")
    except UnicodeDecodeError as exc:
        raise UpdatePackageError("checksum_mismatch", "checksum.sha256 is not UTF-8") from exc
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        try:
            expected, name = line.split(None, 1)
        except ValueError as exc:
            raise UpdatePackageError("checksum_mismatch", "checksum.sha256 has invalid line format") from exc
        name = name.strip()
        if "\x00" in name:
            raise UpdatePackageError("unsafe_zip_entry", f"Unsafe checksum entry: {name}")
        if name not in entry_bytes:
            raise UpdatePackageError("checksum_mismatch", f"checksum.sha256 references missing entry: {name}")
        if _sha256(entry_bytes[name]) != expected.lower():
            raise UpdatePackageError("checksum_mismatch", f"Zip checksum mismatch: {name}")


def _verify_signature(signed_bytes: bytes, signature: bytes, public_key_paths: list[Path]) -> None:
    saw_key = False
    invalid_signature = False
    for index, public_key_path in enumerate(public_key_paths):
        try:
            public_key = serialization.load_pem_public_key(public_key_path.read_bytes())
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise UpdatePackageError("signature_invalid", "Bundled update signing public key is unavailable") from exc
        saw_key = True
        if not isinstance(public_key, Ed25519PublicKey):
            raise UpdatePackageError("signature_invalid", "Bundled update signing public key is not Ed25519")
        try:
            public_key.verify(signature, signed_bytes)
            if index > 0:
                _logger.warning("Update package signature verified with previous public key: %s", public_key_path)
            return
        except InvalidSignature:
            invalid_signature = True
    if not saw_key:
        raise UpdatePackageError("signature_invalid", "Bundled update signing public key is unavailable")
    if invalid_signature:
        raise UpdatePackageError("signature_invalid", "Update package signature is invalid")
    raise UpdatePackageError("signature_invalid", "Update package signature is invalid")


def _verify_signed_entry_hashes(entry_bytes: dict[str, bytes], signed_manifest: dict[str, Any]) -> None:
    entries = signed_manifest.get("entries")
    if not isinstance(entries, dict):
        raise UpdatePackageError("signature_invalid", "signed_manifest.json has no entries hash map")
    if set(entries) != set(entry_bytes) - SIGNATURE_CONTROL_ENTRIES:
        raise UpdatePackageError("signature_invalid", "signed_manifest.json entries do not match zip contents")
    for name, expected in entries.items():
        if name in SIGNATURE_CONTROL_ENTRIES:
            raise UpdatePackageError("signature_invalid", f"Unsigned control entry cannot be signed entry: {name}")
        if name not in entry_bytes:
            raise UpdatePackageError("signature_invalid", f"Signed entry missing from zip: {name}")
        if expected != f"sha256:{_sha256(entry_bytes[name])}":
            raise UpdatePackageError("signature_invalid", f"Signed entry hash mismatch: {name}")


def _validate_manifest(manifest: dict[str, Any], *, current_version: str, current_schema_version: int) -> None:
    package_id = manifest.get("package_id")
    if not isinstance(package_id, str) or PACKAGE_ID_RE.fullmatch(package_id) is None:
        raise UpdatePackageError("manifest_invalid", "package_id is invalid")
    if manifest.get("target_app") != "YU AI Manager":
        raise UpdatePackageError("version_mismatch", "Update package targets a different app")
    operations = manifest.get("operations_order")
    if not isinstance(operations, list) or tuple(operations) not in ALLOWED_OPERATIONS:
        raise UpdatePackageError("conflicting_operation", "operations_order is invalid")
    required_schema = manifest.get("required_schema_version")
    if required_schema is not None and int(required_schema) != int(current_schema_version):
        raise UpdatePackageError("version_mismatch", "Schema version does not match")
    if not (_version_tuple(str(manifest.get("target_version_min", "0.0.0"))) <= _version_tuple(current_version) <= _version_tuple(str(manifest.get("target_version_max", "999999.0.0")))):
        raise UpdatePackageError("version_mismatch", "App version is outside the package target range")


def _files_operations(names: list[str]) -> list[str]:
    result: list[str] = []
    for name in names:
        if name.startswith("files/") and not name.endswith("/"):
            rel = name.removeprefix("files/")
            if rel:
                result.append(_safe_relative_path_string(rel))
    return sorted(result)


def _patch_operations(patch_bytes: bytes | None) -> list[str]:
    if not patch_bytes:
        return []
    declared: dict[str, str] = {}
    represented: dict[str, str] = {}

    def record(raw: str, target: dict[str, str]) -> None:
        path = _safe_relative_path_string(raw)
        key = update_path_key(path)
        previous = declared.get(key) or represented.get(key)
        if previous is not None and previous != path:
            raise UpdatePackageError("invalid_patch", f"Case-colliding patch paths: {previous}, {path}")
        target[key] = path

    for line in patch_bytes.decode("utf-8", errors="replace").splitlines():
        if line.startswith("diff --git "):
            if '"' in line:
                raise UpdatePackageError("invalid_patch", "C-quoted Git patch paths are not supported")
            parts = line.split()
            if len(parts) != 4:
                raise UpdatePackageError("invalid_patch", "diff --git header is invalid")
            for raw in parts[2:4]:
                record(raw[2:] if raw.startswith(("a/", "b/")) else raw, declared)
        if line.startswith(("--- ", "+++ ")):
            raw = line[4:].split("\t", 1)[0]
            if raw != raw.rstrip(" "):
                raise UpdatePackageError("invalid_patch", "patch path has trailing whitespace")
            if raw == "/dev/null":
                continue
            if raw.startswith(("a/", "b/")):
                raw = raw[2:]
            if raw:
                record(raw, represented)
    missing = sorted(set(declared) - set(represented))
    if missing:
        paths = ", ".join(declared[key] for key in missing)
        raise UpdatePackageError("invalid_patch", f"diff --git paths lack a patch file header: {paths}")
    return sorted(represented.values())


def _validate_target_checksums(manifest: dict[str, Any], project_root: Path) -> None:
    checksums = manifest.get("target_file_checksums") or {}
    if not isinstance(checksums, dict):
        raise UpdatePackageError("target_checksum_mismatch", "target_file_checksums must be an object")
    for rel, expected in checksums.items():
        rel_path = Path(*_safe_relative_path_string(str(rel)).split("/"))
        path = (project_root / rel_path).resolve()
        if not path.is_file() or not _is_relative_to(path, project_root):
            raise UpdatePackageError("target_checksum_mismatch", f"Target file is missing or unsafe: {rel}")
        if expected != f"sha256:{_sha256(path.read_bytes())}":
            raise UpdatePackageError("target_checksum_mismatch", f"Target file checksum mismatch: {rel}")


def _safe_relative_path_string(value: str) -> str:
    try:
        return normalize_update_path(value)
    except UnsafeUpdatePath as exc:
        raise UpdatePackageError("unsafe_zip_entry", str(exc)) from exc


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _is_relative_to(path: Path, parent: Path) -> bool:
    try:
        path.relative_to(parent)
        return True
    except ValueError:
        return False


def _version_tuple(value: str) -> tuple[int, ...]:
    parts = [int(part) for part in re.findall(r"\d+", value)]
    return tuple((parts + [0, 0, 0])[:3])
