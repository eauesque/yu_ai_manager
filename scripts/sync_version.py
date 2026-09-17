"""Sync package.json and Cargo.toml/Cargo.lock version to match VERSION file.

Usage:
    python scripts/sync_version.py           # Sync all files to VERSION
    python scripts/sync_version.py --check   # Exit 1 if any version diverges
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
VERSION_FILE = REPO / "VERSION"
PACKAGE_JSON = REPO / "package.json"
CARGO_TOML = REPO / "src-tauri" / "Cargo.toml"
CARGO_LOCK = REPO / "src-tauri" / "Cargo.lock"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def read_canonical() -> str:
    return VERSION_FILE.read_text(encoding="utf-8").strip()


def get_pkg_version() -> str:
    m = re.search(r'"version"\s*:\s*"([^"]+)"', _read(PACKAGE_JSON))
    if not m:
        raise RuntimeError("version field not found in package.json")
    return m.group(1)


def set_pkg_version(ver: str) -> None:
    old = _read(PACKAGE_JSON)
    new = re.sub(r'("version"\s*:\s*)"[^"]+"', rf'\1"{ver}"', old, count=1)
    if old == new:
        raise RuntimeError(f"package.json substitution had no effect (looking for version={get_pkg_version()!r})")
    _write(PACKAGE_JSON, new)


def get_cargo_toml_version() -> str:
    # Match only the first bare `version = "..."` in [package] section
    m = re.search(r'^version\s*=\s*"([^"]+)"', _read(CARGO_TOML), re.MULTILINE)
    if not m:
        raise RuntimeError("version field not found in Cargo.toml")
    return m.group(1)


def set_cargo_toml_version(ver: str) -> None:
    old = _read(CARGO_TOML)
    new = re.sub(r'^(version\s*=\s*)"[^"]+"', rf'\1"{ver}"', old, count=1, flags=re.MULTILINE)
    if old == new:
        raise RuntimeError("Cargo.toml substitution had no effect")
    _write(CARGO_TOML, new)


def get_cargo_lock_version() -> str:
    if not CARGO_LOCK.exists():
        return ""
    m = re.search(r'name\s*=\s*"yu-ai-manager"\s*\nversion\s*=\s*"([^"]+)"', _read(CARGO_LOCK))
    return m.group(1) if m else ""


def set_cargo_lock_version(ver: str) -> None:
    if not CARGO_LOCK.exists():
        return
    old = _read(CARGO_LOCK)
    new = re.sub(
        r'(name\s*=\s*"yu-ai-manager"\s*\nversion\s*=\s*)"[^"]+"',
        rf'\1"{ver}"',
        old,
    )
    if old == new:
        raise RuntimeError("Cargo.lock substitution had no effect (yu-ai-manager entry not found)")
    _write(CARGO_LOCK, new)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="Verify consistency only; exit 1 on mismatch")
    args = ap.parse_args()

    canonical = read_canonical()
    pkg_ver = get_pkg_version()
    cargo_ver = get_cargo_toml_version()
    lock_ver = get_cargo_lock_version()

    mismatches: list[str] = []
    if pkg_ver != canonical:
        mismatches.append(f"package.json    : {pkg_ver!r}  (expected {canonical!r})")
    if cargo_ver != canonical:
        mismatches.append(f"Cargo.toml      : {cargo_ver!r}  (expected {canonical!r})")
    if lock_ver and lock_ver != canonical:
        mismatches.append(f"Cargo.lock      : {lock_ver!r}  (expected {canonical!r})")

    if args.check:
        if mismatches:
            print("Version mismatch (VERSION is the source of truth):", file=sys.stderr)
            for line in mismatches:
                print(f"  {line}", file=sys.stderr)
            print("Run `python scripts/sync_version.py` to fix.", file=sys.stderr)
            return 1
        print(f"OK: all versions match {canonical!r}")
        return 0

    # Sync mode
    if pkg_ver != canonical:
        set_pkg_version(canonical)
        print(f"  package.json   : {pkg_ver} -> {canonical}")
    if cargo_ver != canonical:
        set_cargo_toml_version(canonical)
        print(f"  Cargo.toml     : {cargo_ver} -> {canonical}")
    if lock_ver and lock_ver != canonical:
        set_cargo_lock_version(canonical)
        print(f"  Cargo.lock     : {lock_ver} -> {canonical}")

    # dev-overview.json/.html also track VERSION, via their own script. Chain it
    # here so "sync the version" means all of them: when it was a separate step
    # to remember, it silently drifted 55 versions behind and only CI caught it.
    _sync_dev_overview()

    if not mismatches:
        print(f"Already in sync: {canonical!r}")
    else:
        print(f"Synced to {canonical!r}")
    return 0


def _sync_dev_overview() -> None:
    """Run scripts/sync_dev_overview.py, reporting but not failing on error.

    A missing/broken dev-overview must not block a version bump; CI's
    dev-overview check is still the authority on whether it ended up in sync.
    """
    import subprocess

    script = Path(__file__).resolve().parent / "sync_dev_overview.py"
    if not script.exists():
        return
    result = subprocess.run(
        [sys.executable, str(script)], capture_output=True, text=True
    )
    for line in result.stdout.splitlines():
        if line.strip():
            print(f"  {line.strip()}")
    if result.returncode != 0:
        print(f"  WARNING: sync_dev_overview.py exited {result.returncode}")
        if result.stderr.strip():
            print(f"  {result.stderr.strip().splitlines()[-1]}")


if __name__ == "__main__":
    sys.exit(main())
