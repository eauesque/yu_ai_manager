#!/usr/bin/env python3
"""Reviewer gate: enforce AI_REPAIR_POLICY.json forbidden_paths against a patch.

Run before promoting an AI-generated `suggested.patch` to a signed update.zip.
Non-zero exit means the patch touches a forbidden path and must not be promoted.

Usage:
    uv run python scripts/review_suggested_patch.py PATCH --unsigned-zip UPDATE.zip [--emit-pass OUTPUT.json] [--meta META.json]

Arguments:
    PATCH                      Path to suggested.patch
    --emit-pass OUTPUT.json    On exit 0, write a review_pass.json artifact
                               consumed by tools/update/sign_update_zip.py.
                               Without this artifact, the signer refuses to
                               sign the update.zip — this is what makes the
                               reviewer gate structural rather than convention.
    --meta META.json           Optional suggested_patch.meta.json. If it
                               declares `repair_class: "cache_clear"`, the
                               patch must touch only paths in the policy's
                               cache_clear_allowlist; otherwise the gate
                               blocks (class-aware check, Q2 follow-up).

Exit codes:
    0 — patch passes all checks
    1 — patch touches a forbidden path or violates its declared repair_class
    2 — usage / I/O / parse error (policy missing, patch missing, malformed)
"""

from __future__ import annotations

import argparse
import datetime as dt
import fnmatch
import hashlib
import io
import json
import posixpath
import stat
import sys
import zipfile
from pathlib import Path, PurePosixPath
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from core.repair.update_package.paths import (  # noqa: E402
    normalize_update_path,
    update_path_key,
)

_POLICY_PATH = _PROJECT_ROOT / "AI_REPAIR_POLICY.json"
_SCRIPT_PATH = Path(__file__).resolve()
_CONTROL_ENTRIES = {"signed_manifest.json", "signature.bin", "checksum.sha256"}
_EXECUTABLE_SUFFIXES = {".bat", ".cmd", ".com", ".dll", ".exe", ".msi", ".ps1", ".sh", ".so"}
_MAX_ZIP_ENTRIES = 10_000
_MAX_ZIP_BYTES = 256 * 1024 * 1024
_MAX_ZIP_UNCOMPRESSED_BYTES = 256 * 1024 * 1024
_MAX_ZIP_COMPRESSION_RATIO = 100


class ReviewGateBlockedError(ValueError):
    """The patch violates the current reviewer policy."""


def _load_policy() -> dict[str, Any]:
    if not _POLICY_PATH.exists():
        raise FileNotFoundError(f"AI_REPAIR_POLICY.json not found at {_POLICY_PATH}")
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def _forbidden_paths(policy: dict[str, Any]) -> dict[str, list[str]]:
    forbidden = policy.get("forbidden_paths")
    if not isinstance(forbidden, dict):
        raise ValueError("forbidden_paths missing or not an object in AI_REPAIR_POLICY.json")
    return {str(k): [str(p) for p in v] for k, v in forbidden.items()}


def _extract_changed_paths(patch_text: str) -> set[str]:
    """Collect every file path mentioned in a unified-diff / git-format patch."""
    declared: dict[str, str] = {}
    represented: dict[str, str] = {}

    def add_path(raw_path: str, target: dict[str, str]) -> None:
        path = normalize_update_path(raw_path)
        key = update_path_key(path)
        previous = declared.get(key) or represented.get(key)
        if previous is not None and previous != path:
            raise ValueError(f"case-colliding patch paths are not supported: {previous}, {path}")
        target[key] = path

    in_header = False
    awaiting_plus = False
    for raw in patch_text.splitlines():
        line = raw.rstrip("\r")
        if line.startswith("diff --git "):
            if '"' in line:
                raise ValueError("C-quoted Git patch paths are not supported")
            parts = line.split()
            if len(parts) != 4:
                raise ValueError("diff --git header is invalid")
            for token in (parts[2], parts[3]):
                if token.startswith(("a/", "b/")):
                    add_path(token[2:], declared)
                elif token != "/dev/null":
                    raise ValueError("diff --git paths must use a/ and b/ prefixes")
            in_header = True
            awaiting_plus = False
        elif line.startswith("@@ "):
            in_header = False
            awaiting_plus = False
        elif line.startswith("--- "):
            if not in_header:
                raise ValueError("plain unified patches are not supported")
            awaiting_plus = True
        elif line.startswith("+++ "):
            if not in_header or not awaiting_plus:
                if not in_header:
                    continue
                raise ValueError("diff file header is invalid")
            target = line[4:].split("\t", 1)[0]
            if target != target.rstrip(" "):
                raise ValueError("patch path has trailing whitespace")
            if not target or target == "/dev/null":
                continue
            if target.startswith(("a/", "b/")):
                add_path(target[2:], represented)
            else:
                raise ValueError("diff file header paths must use a/ and b/ prefixes")
            awaiting_plus = False
        elif in_header and line.startswith(("rename from ", "rename to ", "copy from ", "copy to ")):
            add_path(line.split(" ", 2)[2].strip(), represented)
    unrepresented = sorted(set(declared) - set(represented))
    if unrepresented:
        paths = ", ".join(declared[key] for key in unrepresented)
        raise ValueError(f"diff --git paths lack a patch file header: {paths}")
    return set(declared.values()) | set(represented.values())


def _match_pattern(file_path: str, pattern: str) -> bool:
    file_path = update_path_key(file_path)
    normalized = pattern.replace("**", "*").casefold()
    if pattern.endswith("/"):
        normalized = normalized.rstrip("/")
        return fnmatch.fnmatchcase(file_path, normalized) or fnmatch.fnmatchcase(file_path, normalized + "/*")
    return fnmatch.fnmatchcase(file_path, normalized)


def _categorize(paths: set[str], forbidden: dict[str, list[str]]) -> dict[str, list[tuple[str, str]]]:
    hits: dict[str, list[tuple[str, str]]] = {}
    for category, patterns in forbidden.items():
        for path in sorted(paths):
            for pat in patterns:
                if _match_pattern(path, pat):
                    hits.setdefault(category, []).append((path, pat))
                    break
    return hits


def _check_class_bytes(
    paths: set[str],
    meta_bytes: bytes,
    policy: dict[str, Any],
) -> tuple[bool, str | None, list[str]]:
    """Return (ok, repair_class, violating_paths).

    For repair_class == "cache_clear", every changed path must match the
    policy's cache_clear_allowlist. Other classes currently impose no
    additional path constraint (the forbidden_paths check still applies to
    them; this function is the *positive* allow-list arm).
    """
    try:
        meta = json.loads(meta_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"invalid suggested_patch.meta.json: {exc}") from exc
    repair_class = meta.get("repair_class")
    if repair_class is None:
        return True, None, []
    if repair_class != "cache_clear":
        return True, str(repair_class), []
    allowlist = policy.get("cache_clear_allowlist") or []
    violating = [path for path in sorted(paths) if not any(_match_pattern(path, pat) for pat in allowlist)]
    return (not violating), repair_class, violating


def validate_review_gate(
    patch_bytes: bytes,
    unsigned_zip_bytes: bytes | None,
    *,
    policy: dict[str, Any] | None = None,
    meta_bytes: bytes | None = None,
) -> tuple[set[str], str | None]:
    """Validate the exact promotion inputs without trusting a pass artifact."""
    try:
        changed = _extract_changed_paths(patch_bytes.decode("utf-8"))
    except UnicodeDecodeError as exc:
        raise ValueError(f"cannot decode patch as UTF-8: {exc}") from exc
    policy = _load_policy() if policy is None else policy
    if unsigned_zip_bytes is not None:
        _validate_unsigned_zip(unsigned_zip_bytes, patch_bytes, changed)
    hits = _categorize(changed, _forbidden_paths(policy))
    if hits:
        details = ", ".join(
            f"{category}: {path}" for category, entries in hits.items() for path, _ in entries
        )
        raise ReviewGateBlockedError(f"suggested.patch touches forbidden paths: {details}")
    if meta_bytes is None:
        return changed, None
    ok, repair_class, violating = _check_class_bytes(changed, meta_bytes, policy)
    if not ok:
        raise ReviewGateBlockedError(
            f"declared repair_class={repair_class!r} touches paths outside cache_clear_allowlist: "
            + ", ".join(violating)
        )
    return changed, repair_class


def _read_unsigned_zip(unsigned_zip: Path) -> bytes:
    try:
        with unsigned_zip.open("rb") as source:
            data = source.read(_MAX_ZIP_BYTES + 1)
    except OSError as exc:
        raise ValueError(f"cannot read unsigned zip: {exc}") from exc
    if len(data) > _MAX_ZIP_BYTES:
        raise ValueError("unsigned zip is too large")
    return data


def _validate_unsigned_zip(unsigned_zip_bytes: bytes, patch_bytes: bytes, changed: set[str]) -> None:
    """Validate the exact payload before issuing a review pass."""
    try:
        with zipfile.ZipFile(io.BytesIO(unsigned_zip_bytes)) as zf:
            infos = zf.infolist()
            names = [info.filename for info in infos]
            if len(infos) > _MAX_ZIP_ENTRIES:
                raise ValueError("unsigned zip has too many entries")
            if len(names) != len(set(names)):
                raise ValueError("unsigned zip contains duplicate entries")
            total_size = 0
            for info in infos:
                name = info.filename
                normalized = posixpath.normpath(name)
                mode = (info.external_attr >> 16) & 0xFFFF
                total_size += info.file_size
                if total_size > _MAX_ZIP_UNCOMPRESSED_BYTES:
                    raise ValueError("unsigned zip uncompressed size is too large")
                if info.compress_size and info.file_size / info.compress_size > _MAX_ZIP_COMPRESSION_RATIO:
                    raise ValueError(f"suspicious compression ratio: {name}")
                if (
                    "\x00" in name
                    or "\\" in name
                    or name.startswith("/")
                    or normalized != name.rstrip("/")
                    or normalized in {"", "."}
                    or ".." in PurePosixPath(normalized).parts
                    or stat.S_ISLNK(mode)
                ):
                    raise ValueError(f"unsafe unsigned zip entry: {name}")
                if name in _CONTROL_ENTRIES:
                    raise ValueError(f"unsigned zip contains control entry: {name}")
                normalize_update_path(name.rstrip("/"))
            entries = {info.filename: zf.read(info) for info in infos if not info.is_dir()}
    except (OSError, zipfile.BadZipFile, RuntimeError) as exc:
        raise ValueError(f"malformed unsigned zip: {exc}") from exc

    if "manifest.json" not in entries:
        raise ValueError("unsigned zip is missing manifest.json")
    if entries.get("patch.diff") != patch_bytes:
        raise ValueError("unsigned zip patch.diff does not exactly match the reviewed patch")
    try:
        manifest = json.loads(entries["manifest.json"].decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"manifest.json is invalid: {exc}") from exc
    if not isinstance(manifest, dict):
        raise ValueError("manifest.json must contain an object")
    checksums = manifest.get("target_file_checksums") or {}
    if not isinstance(checksums, dict):
        raise ValueError("manifest target_file_checksums must be an object")
    changed_by_key = {update_path_key(path): path for path in changed}
    changed_keys = set(changed_by_key)
    checksum_paths = [normalize_update_path(str(path)) for path in checksums]
    if len({update_path_key(path) for path in checksum_paths}) != len(checksum_paths):
        raise ValueError("manifest target_file_checksums contains case-colliding paths")
    if any(
        update_path_key(path) in changed_by_key and changed_by_key[update_path_key(path)] != path
        for path in checksum_paths
    ):
        raise ValueError("manifest target_file_checksums case-collides with a reviewed patch path")
    unreviewed_checksums = sorted(path for path in checksum_paths if update_path_key(path) not in changed_keys)
    if unreviewed_checksums:
        raise ValueError(
            "manifest target_file_checksums contains paths not represented by the reviewed patch: "
            + ", ".join(unreviewed_checksums)
        )

    for name in entries:
        if name in {"manifest.json", "patch.diff"}:
            continue
        if not name.startswith("files/") or name == "files/":
            raise ValueError(f"unexpected unsigned zip entry: {name}")
        target = normalize_update_path(name.removeprefix("files/"))
        target_key = update_path_key(target)
        if target_key in changed_by_key and changed_by_key[target_key] != target:
            raise ValueError(f"payload entry case-collides with reviewed patch path: {name}")
        if target_key not in changed_keys:
            if PurePosixPath(target).suffix.lower() in _EXECUTABLE_SUFFIXES:
                raise ValueError(f"unexpected executable entry: {name}")
            raise ValueError(f"payload entry was not represented by the reviewed patch or manifest: {name}")


def _write_pass_artifact(
    emit_path: Path,
    *,
    patch_path: Path,
    patch_bytes: bytes,
    changed: set[str],
    policy: dict[str, Any],
    repair_class: str | None,
    unsigned_zip_bytes: bytes,
    meta_bytes: bytes | None,
) -> None:
    artifact = {
        "status": "pass",
        "reviewed_at": dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "patch_path": str(patch_path),
        "patch_sha256": hashlib.sha256(patch_bytes).hexdigest(),
        "patch_size": len(patch_bytes),
        "unsigned_zip_sha256": hashlib.sha256(unsigned_zip_bytes).hexdigest(),
        "changed_paths_count": len(changed),
        "policy_version": policy.get("policy_version"),
        "policy_revision": policy.get("policy_revision", 0),
        "reviewer_gate_script_sha256": hashlib.sha256(_SCRIPT_PATH.read_bytes()).hexdigest(),
        "repair_class": repair_class,
        "meta_sha256": hashlib.sha256(meta_bytes).hexdigest() if meta_bytes is not None else None,
    }
    emit_path.parent.mkdir(parents=True, exist_ok=True)
    emit_path.write_text(
        json.dumps(artifact, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        add_help=True, description="Review a suggested.patch against AI_REPAIR_POLICY.json"
    )
    parser.add_argument("patch", type=Path, help="Path to suggested.patch")
    parser.add_argument("--emit-pass", type=Path, default=None, help="Write review_pass.json artifact on exit 0")
    parser.add_argument("--meta", type=Path, default=None, help="suggested_patch.meta.json for class-aware checks")
    parser.add_argument("--unsigned-zip", type=Path, default=None, help="Unsigned update.zip reviewed with this patch")
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    if not args.patch.exists():
        print(f"error: patch not found: {args.patch}", file=sys.stderr)
        return 2
    if args.emit_pass and (args.unsigned_zip is None or not args.unsigned_zip.is_file()):
        print("error: --emit-pass requires an existing --unsigned-zip", file=sys.stderr)
        return 2

    try:
        policy = _load_policy()
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        print(f"error: cannot load policy: {exc}", file=sys.stderr)
        return 2

    try:
        patch_bytes = args.patch.read_bytes()
    except (OSError, UnicodeDecodeError) as exc:
        print(f"error: cannot read patch: {exc}", file=sys.stderr)
        return 2

    meta_bytes: bytes | None = None
    if args.meta is not None:
        try:
            meta_bytes = args.meta.read_bytes()
        except OSError as exc:
            print(f"error: cannot read --meta {args.meta}: {exc}", file=sys.stderr)
            return 2
    unsigned_zip_bytes: bytes | None = None
    if args.emit_pass:
        try:
            unsigned_zip_bytes = _read_unsigned_zip(args.unsigned_zip)
        except ValueError as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 2
    try:
        changed, repair_class = validate_review_gate(
            patch_bytes, unsigned_zip_bytes, policy=policy, meta_bytes=meta_bytes
        )
    except ReviewGateBlockedError as exc:
        print(f"BLOCKED: {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    if not changed:
        print("warning: no changed paths detected in patch", file=sys.stderr)
        print("OK: no forbidden paths touched (0 changed paths).")
        if args.emit_pass:
            _write_pass_artifact(
                args.emit_pass,
                patch_path=args.patch,
                patch_bytes=patch_bytes,
                changed=changed,
                policy=policy,
                repair_class=None,
                unsigned_zip_bytes=unsigned_zip_bytes,
                meta_bytes=meta_bytes,
            )
        return 0

    msg = f"OK: no forbidden paths touched ({len(changed)} changed paths)."
    if repair_class:
        msg += f" repair_class={repair_class!r} satisfied."
    print(msg)

    if args.emit_pass:
        _write_pass_artifact(
            args.emit_pass,
            patch_path=args.patch,
            patch_bytes=patch_bytes,
            changed=changed,
            policy=policy,
            repair_class=repair_class,
            unsigned_zip_bytes=unsigned_zip_bytes,
            meta_bytes=meta_bytes,
        )

    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
