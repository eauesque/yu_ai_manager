#!/usr/bin/env python3
"""Verify a no-default-features yu-server binary excludes OCR code."""

from __future__ import annotations

import mmap
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CRATES = ROOT / "crates"
BINARY = CRATES / "target" / "debug" / "yu-server"
OCR_SYMBOLS = (
    "yu_server::ocr::",
    "yu_server::routes::ocr::",
    "yu_server::routes::ocr_jobs::",
    "yu_server::routes::ocr_npu::",
)
OCR_ROUTE_PREFIXES = (b"/api/ocr/",)
GATED_MODULES = (
    (ROOT / "crates" / "yu-server" / "src" / "main.rs", "#[cfg(feature = \"ocr\")]\nmod ocr;"),
    (ROOT / "crates" / "yu-server" / "src" / "routes" / "mod.rs", "#[cfg(feature = \"ocr\")]\npub mod ocr;"),
    (ROOT / "crates" / "yu-server" / "src" / "routes" / "mod.rs", "#[cfg(feature = \"ocr\")]\npub mod ocr_jobs;"),
    (ROOT / "crates" / "yu-server" / "src" / "routes" / "mod.rs", "#[cfg(feature = \"ocr\")]\npub mod ocr_npu;"),
)


def ungated_ocr_handlers() -> list[str]:
    routes = ROOT / "crates" / "yu-server" / "src" / "routes"
    found = []
    for path in routes.glob("*.rs"):
        if path.name in {"ocr.rs", "ocr_jobs.rs", "ocr_npu.rs"}:
            continue
        source = path.read_text()
        for match in re.finditer(r"\bpub\s+async\s+fn\s+(ocr_[A-Za-z0-9_]+)\b", source):
            name = match.group(1)
            if '#[cfg(feature = "ocr")]' not in source[max(0, match.start() - 80) : match.start()]:
                found.append(f"{path.relative_to(ROOT)}: {name}")
    return found


def main() -> int:
    missing_gates = [
        f"{path.relative_to(ROOT)}: {gate}"
        for path, gate in GATED_MODULES
        if gate not in path.read_text()
    ]
    if missing_gates:
        print("FAIL: OCR module gate missing")
        print("\n".join(missing_gates))
        return 1

    handlers = ungated_ocr_handlers()
    if handlers:
        print("FAIL: ungated OCR handler definitions found")
        print("\n".join(handlers))
        return 1

    nm = shutil.which("nm")
    if nm is None:
        print("FAIL: nm is required for the OCR feature-gate check")
        return 2

    # Build into a directory of its own. The shared `crates/target/` is what
    # every other stage reads, and dropping a --no-default-features binary
    # there makes the parity stage boot a server with no OCR routes: seven
    # entries then report rust=404 py=200 and the failure looks like a
    # regression in the port rather than this checker's leftovers.
    gate_target = CRATES / "target" / "ocr-gate-check"
    build = subprocess.run(
        [
            "cargo",
            "build",
            "-p",
            "yu-server",
            "-j",
            "2",
            "--no-default-features",
            "--features",
            "python-backend",
            "--target-dir",
            str(gate_target),
        ],
        cwd=CRATES,
        env={**os.environ, "CARGO_BUILD_JOBS": "2"},
        text=True,
        capture_output=True,
    )
    if build.returncode:
        print(build.stdout, end="")
        print(build.stderr, end="", file=sys.stderr)
        return build.returncode

    symbols = subprocess.run(
        [nm, "-C", "--defined-only", str(gate_target / "debug" / "yu-server")],
        text=True,
        capture_output=True,
        check=False,
    )
    if symbols.returncode:
        print(symbols.stderr, end="", file=sys.stderr)
        return symbols.returncode

    found_symbols = [
        line
        for line in symbols.stdout.splitlines()
        if any(name in line for name in OCR_SYMBOLS)
    ]
    gate_binary = gate_target / "debug" / "yu-server"
    with gate_binary.open("rb") as binary, mmap.mmap(binary.fileno(), 0, access=mmap.ACCESS_READ) as contents:
        found_routes = [prefix.decode() for prefix in OCR_ROUTE_PREFIXES if prefix in contents]
    if found_symbols or found_routes:
        print("FAIL: OCR routes or implementation symbols found in no-default-features binary")
        if found_routes:
            print("OCR route literals:\n" + "\n".join(found_routes))
        if found_symbols:
            print("OCR symbols:\n" + "\n".join(found_symbols))
        return 1

    # Put the default build back. This check compiles the workspace with a
    # different feature set, and cargo's shared fingerprints mean the default
    # binary can come back OCR-less afterwards -- which makes the *next* run's
    # parity stage boot a server with no OCR routes and report seven entries as
    # rust=404 py=200. That happened three times before this was added, each
    # time diagnosed as a port regression and each time fixed by a manual
    # rebuild. A checker must leave the tree as it found it.
    restore = subprocess.run(
        ["cargo", "build", "-p", "yu-server", "-j", "2"],
        cwd=CRATES,
        env={**os.environ, "CARGO_BUILD_JOBS": "2"},
        text=True,
        capture_output=True,
    )
    if restore.returncode:
        print("FAIL: could not restore the default build after the gate check")
        print(restore.stderr, end="", file=sys.stderr)
        return restore.returncode

    print("PASS: no OCR route or implementation symbols in no-default-features binary")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
