"""Concrete checks for license audit script."""

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from license_audit_config import (
    FALSE_POSITIVE_PATTERNS,
    FALSE_POSITIVE_PKGS,
    GPL_LICENSE_RE,
    KNOWN_BAD_REQUIREMENTS,
    LICENSE_FILE_NAMES,
    LICENSE_HEADER_PATTERNS,
    PROJECT_ROOT,
    SELF_SCRIPT,
    SKIP_DIRS,
    SOURCE_EXTS,
)
from license_audit_i18n import msg
from license_audit_state import AuditState

logger = logging.getLogger(__name__)


def _iter_project_files():
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        yield root, files


def _iter_requirement_files() -> list[Path]:
    return [
        PROJECT_ROOT / "requirements.txt",
        PROJECT_ROOT / "requirements-portable.txt",
    ]


def _load_declared_requirement_names() -> set[str]:
    names: set[str] = set()
    for req_file in _iter_requirement_files():
        if not req_file.exists():
            continue
        for raw_line in req_file.read_text(encoding="utf-8").splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#") or line.startswith("-r "):
                continue
            line = line.split(";", 1)[0].strip()
            for marker in ("==", ">=", "<=", "~=", "!=", ">", "<"):
                if marker in line:
                    line = line.split(marker, 1)[0].strip()
                    break
            if "[" in line:
                line = line.split("[", 1)[0].strip()
            if line:
                names.add(line.lower().replace("_", "-"))
    return names


def check_pip_licenses(state: AuditState) -> None:
    print(f"\n{msg('chk1_header')}\n")
    try:
        result = subprocess.run([sys.executable, "-m", "piplicenses", "--format=json"], capture_output=True, text=True, timeout=30)
        packages = json.loads(result.stdout)
    except Exception as e:
        print(msg("skip_pip_licenses").format(err=e))
        return

    declared_requirements = _load_declared_requirement_names()
    allowed_false_positives = {p.lower().replace("_", "-") for p in FALSE_POSITIVE_PKGS}
    gpl_pkgs = []
    checked_packages = 0
    for pkg in packages:
        lic = (pkg.get("License") or "").upper()
        name = pkg.get("Name", "?")
        normalized = name.lower().replace("_", "-")
        if normalized not in declared_requirements:
            continue
        checked_packages += 1
        if normalized in allowed_false_positives:
            continue
        if any(g in lic for g in ("GPL", "LGPL", "AGPL")):
            if " OR " in lic or ";" in lic or "," in lic:
                continue
            gpl_pkgs.append(f"{name} ({lic})")

    state.check(msg("chk1_label").format(n=checked_packages), len(gpl_pkgs) == 0, "; ".join(gpl_pkgs) if gpl_pkgs else "")


def check_source_headers(state: AuditState) -> None:
    print(f"\n{msg('chk2_header')}\n")
    findings = []
    for root, files in _iter_project_files():
        for fn in files:
            if os.path.splitext(fn)[1].lower() not in SOURCE_EXTS or fn == SELF_SCRIPT:
                continue
            fpath = os.path.join(root, fn)
            rel_path = os.path.relpath(fpath, PROJECT_ROOT)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as handle:
                    for line_no, line in enumerate(handle, 1):
                        if not any(pat.search(line) for pat in LICENSE_HEADER_PATTERNS):
                            continue
                        if any(fp.search(line) for fp in FALSE_POSITIVE_PATTERNS):
                            continue
                        findings.append(f"{rel_path}:{line_no}: {line.strip()[:100]}")
            except Exception:
                logger.debug("step failed", exc_info=True)

    state.check(msg("chk2_label"), len(findings) == 0, msg("chk2_found").format(n=len(findings)) if findings else "")
    for finding in findings:
        print(f"    {finding}")


def check_license_files(state: AuditState) -> None:
    print(f"\n{msg('chk3_header')}\n")
    gpl_files = []
    all_files = []
    for root, files in _iter_project_files():
        for fn in files:
            if fn.lower() not in LICENSE_FILE_NAMES:
                continue
            fpath = os.path.join(root, fn)
            rel_path = os.path.relpath(fpath, PROJECT_ROOT)
            all_files.append(rel_path)
            try:
                with open(fpath, encoding="utf-8", errors="replace") as handle:
                    if GPL_LICENSE_RE.search(handle.read()):
                        gpl_files.append(rel_path)
            except Exception:
                logger.debug("step failed", exc_info=True)

    state.check(msg("chk3_label").format(n=len(all_files)), len(gpl_files) == 0, "; ".join(gpl_files) if gpl_files else "")


def check_requirements(state: AuditState) -> None:
    print(f"\n{msg('chk4_header')}\n")
    req_file = PROJECT_ROOT / "requirements.txt"
    if not req_file.exists():
        print(msg("skip_no_req"))
        return
    content = req_file.read_text(encoding="utf-8").lower()
    found = [pkg for pkg in KNOWN_BAD_REQUIREMENTS if pkg in content]
    state.check(msg("chk4_label"), len(found) == 0, "; ".join(found) if found else "")


def check_third_party_file(state: AuditState) -> None:
    print(f"\n{msg('chk5_header')}\n")
    state.check(msg("chk5_label"), (PROJECT_ROOT / "THIRD_PARTY_LICENSES.txt").exists())


def run_all_checks(state: AuditState) -> None:
    check_pip_licenses(state)
    check_source_headers(state)
    check_license_files(state)
    check_requirements(state)
    check_third_party_file(state)
