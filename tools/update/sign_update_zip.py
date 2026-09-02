#!/usr/bin/env python3
"""Sign an unsigned update.zip after enforcing the reviewer gate.

Usage:
    uv run python -m tools.update.sign_update_zip \\
        --unsigned-zip path/to/unsigned.zip \\
        --private-key path/to/ed25519_private.pem \\
        --review-pass path/to/review_pass.json \\
        --meta path/to/suggested_patch.meta.json \\
        --output path/to/signed.zip

This tool refuses to produce a signed update.zip unless a valid
`review_pass.json` artifact (emitted by scripts/review_suggested_patch.py
with --emit-pass) is presented. That is the structural enforcement of the
forbidden_paths reviewer gate: without the artifact, signing is impossible,
not merely "discouraged by policy".

The unsigned zip must already contain `manifest.json` plus the payload
(`files/...` and optionally `patch.diff`). This tool adds
`signed_manifest.json`, `signature.bin`, and `checksum.sha256`.

Exit codes:
    0 — signed update.zip written
    2 — usage / I/O / parse error
    3 — reviewer gate violation (review_pass.json missing, stale, mismatched,
        or refers to a different policy version/revision)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import shutil
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from scripts.review_suggested_patch import ReviewGateBlockedError, validate_review_gate

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_POLICY_PATH = _PROJECT_ROOT / "AI_REPAIR_POLICY.json"
_REVIEWER_SCRIPT_PATH = _PROJECT_ROOT / "scripts" / "review_suggested_patch.py"

REVIEW_PASS_MAX_AGE_SECONDS = 7 * 24 * 3600  # 7 days

CONTROL_ENTRIES = {"signed_manifest.json", "signature.bin", "checksum.sha256"}


class SignerGateError(Exception):
    pass


def _canonical(value: Any) -> bytes:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _load_policy() -> dict[str, Any]:
    return json.loads(_POLICY_PATH.read_text(encoding="utf-8"))


def _verify_review_pass(
    review_pass_path: Path,
    *,
    unsigned_zip_bytes: bytes,
    unsigned_entries: dict[str, bytes],
    meta_bytes: bytes,
    policy: dict[str, Any],
    now: dt.datetime,
) -> dict[str, Any]:
    """Validate a review_pass.json artifact. Raise SignerGateError if invalid."""
    if not review_pass_path.exists():
        raise SignerGateError(f"review_pass.json not found: {review_pass_path}")
    try:
        artifact = json.loads(review_pass_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SignerGateError(f"review_pass.json is not valid JSON: {exc}") from exc

    if artifact.get("status") != "pass":
        raise SignerGateError(f"review_pass.json status is not 'pass': {artifact.get('status')!r}")

    for required in (
        "reviewed_at",
        "patch_sha256",
        "policy_version",
        "reviewer_gate_script_sha256",
        "unsigned_zip_sha256",
        "meta_sha256",
    ):
        if required not in artifact:
            raise SignerGateError(f"review_pass.json missing required field: {required}")

    try:
        reviewed_at = dt.datetime.fromisoformat(artifact["reviewed_at"])
    except ValueError as exc:
        raise SignerGateError(f"review_pass.json reviewed_at is not ISO 8601: {exc}") from exc
    if reviewed_at.tzinfo is None:
        raise SignerGateError("review_pass.json reviewed_at must include a timezone")
    age = (now - reviewed_at).total_seconds()
    if age < 0:
        raise SignerGateError("review_pass.json reviewed_at is in the future")
    if age > REVIEW_PASS_MAX_AGE_SECONDS:
        raise SignerGateError(
            f"review_pass.json is stale ({age:.0f}s old, max {REVIEW_PASS_MAX_AGE_SECONDS}s). "
            "Re-run scripts/review_suggested_patch.py --emit-pass."
        )

    if artifact["policy_version"] != policy.get("policy_version"):
        raise SignerGateError(
            f"review_pass.json policy_version={artifact['policy_version']!r} "
            f"!= current {policy.get('policy_version')!r}"
        )
    if artifact.get("policy_revision", 0) != policy.get("policy_revision", 0):
        raise SignerGateError(
            f"review_pass.json policy_revision={artifact.get('policy_revision', 0)!r} "
            f"!= current {policy.get('policy_revision', 0)!r}"
        )

    actual_script_sha = _sha256_hex(_REVIEWER_SCRIPT_PATH.read_bytes())
    if artifact["reviewer_gate_script_sha256"] != actual_script_sha:
        raise SignerGateError(
            "review_pass.json reviewer_gate_script_sha256 does not match the current "
            f"{_REVIEWER_SCRIPT_PATH.relative_to(_PROJECT_ROOT)}. Re-run --emit-pass with the "
            "current script."
        )

    if artifact["unsigned_zip_sha256"] != _sha256_hex(unsigned_zip_bytes):
        raise SignerGateError("review_pass.json does not match the full unsigned zip payload")
    if artifact["meta_sha256"] != _sha256_hex(meta_bytes):
        raise SignerGateError("review_pass.json does not match the supplied suggested_patch.meta.json")

    patch_bytes = unsigned_entries.get("patch.diff")
    expected_patch_sha = artifact["patch_sha256"]
    if patch_bytes is None:
        if expected_patch_sha is not None:
            raise SignerGateError("review_pass.json declares patch_sha256 but the unsigned zip has no patch.diff entry")
    else:
        actual_patch_sha = _sha256_hex(patch_bytes)
        if actual_patch_sha != expected_patch_sha:
            raise SignerGateError(
                f"patch.diff sha256 mismatch: zip has {actual_patch_sha}, "
                f"review_pass.json declares {expected_patch_sha}"
            )

    return artifact


def _load_unsigned_entries(unsigned_zip: Path) -> dict[str, bytes]:
    if not unsigned_zip.exists():
        raise SignerGateError(f"unsigned zip not found: {unsigned_zip}")
    entries: dict[str, bytes] = {}
    with zipfile.ZipFile(unsigned_zip, "r") as zf:
        for info in zf.infolist():
            if info.is_dir():
                continue
            if info.filename in CONTROL_ENTRIES:
                raise SignerGateError(
                    f"unsigned zip already contains control entry '{info.filename}'. "
                    "Re-export the unsigned zip without signing material."
                )
            entries[info.filename] = zf.read(info.filename)
    if "manifest.json" not in entries:
        raise SignerGateError("unsigned zip is missing manifest.json")
    return entries


def _load_private_key(path: Path) -> Ed25519PrivateKey:
    key = serialization.load_pem_private_key(path.read_bytes(), password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise SignerGateError(f"private key at {path} is not an Ed25519 key")
    return key


def _build_signed_zip(
    entries: dict[str, bytes],
    private_key: Ed25519PrivateKey,
    output: Path,
) -> None:
    manifest_bytes = entries["manifest.json"]
    try:
        manifest = json.loads(manifest_bytes)
    except json.JSONDecodeError as exc:
        raise SignerGateError(f"manifest.json is not valid JSON: {exc}") from exc

    payload = {name: data for name, data in entries.items() if name != "manifest.json"}
    payload["manifest.json"] = manifest_bytes
    signed_manifest = {
        "manifest": manifest,
        "entries": {name: f"sha256:{_sha256_hex(data)}" for name, data in sorted(payload.items())},
    }
    signed_bytes = _canonical(signed_manifest)
    signature = private_key.sign(signed_bytes)

    checksum_lines = [f"{_sha256_hex(data)}  {name}" for name, data in sorted(payload.items())]
    checksum_lines.append(f"{_sha256_hex(signed_bytes)}  signed_manifest.json")

    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, data in entries.items():
            zf.writestr(name, data)
        zf.writestr("signed_manifest.json", signed_bytes)
        zf.writestr("signature.bin", signature)
        zf.writestr("checksum.sha256", ("\n".join(checksum_lines) + "\n").encode("utf-8"))


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--unsigned-zip", type=Path, required=True)
    parser.add_argument("--private-key", type=Path, required=True)
    parser.add_argument("--review-pass", type=Path, required=True)
    parser.add_argument("--meta", type=Path, required=True, help="Reviewed suggested_patch.meta.json")
    parser.add_argument("--output", type=Path, required=True)
    try:
        args = parser.parse_args(argv[1:])
    except SystemExit as exc:
        return int(exc.code) if isinstance(exc.code, int) else 2

    try:
        policy = _load_policy()
    except (OSError, json.JSONDecodeError) as exc:
        print(f"error: cannot load policy: {exc}", file=sys.stderr)
        return 2

    try:
        entries = _load_unsigned_entries(args.unsigned_zip)
    except SignerGateError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    try:
        unsigned_zip_bytes = args.unsigned_zip.read_bytes()
        meta_bytes = args.meta.read_bytes()
    except OSError as exc:
        print(f"error: cannot read signing input: {exc}", file=sys.stderr)
        return 2

    try:
        _verify_review_pass(
            args.review_pass,
            unsigned_zip_bytes=unsigned_zip_bytes,
            unsigned_entries=entries,
            meta_bytes=meta_bytes,
            policy=policy,
            now=dt.datetime.now(dt.UTC),
        )
    except SignerGateError as exc:
        print(f"REFUSED: reviewer gate not satisfied — {exc}", file=sys.stderr)
        return 3

    try:
        validate_review_gate(entries.get("patch.diff", b""), unsigned_zip_bytes, policy=policy, meta_bytes=meta_bytes)
    except (ReviewGateBlockedError, ValueError) as exc:
        print(f"REFUSED: reviewer gate not satisfied — independent validation failed: {exc}", file=sys.stderr)
        return 3

    try:
        private_key = _load_private_key(args.private_key)
    except (SignerGateError, OSError, ValueError) as exc:
        print(f"error: cannot load private key: {exc}", file=sys.stderr)
        return 2

    # Write to a temporary file in the output directory, then atomic-replace
    # to avoid leaving a half-written zip if the process dies mid-write.
    output_dir = args.output.parent if args.output.parent != Path("") else Path(".")
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(prefix=".sign-", suffix=".zip.tmp", dir=output_dir, delete=False) as tmp:
        tmp_path = Path(tmp.name)
    try:
        _build_signed_zip(entries, private_key, tmp_path)
        shutil.move(str(tmp_path), args.output)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)
        raise

    print(f"signed update.zip written: {args.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
