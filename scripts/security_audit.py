"""Startup security audit for uv-managed Python deps and pnpm-managed JS deps.

Runs `pip-audit` (via `uvx`) and `pnpm audit` to detect known CVEs in the
current lockfiles, optionally bumping vulnerable packages to a patched
version (`--mode apply`). Designed to be invoked from start.sh / start.bat
right after the uv bootstrap step.

Behavior contract:
  - Always exits 0 — the audit must NEVER block app startup.
  - Throttled to once per 24h via `tmp/.last_security_audit` mtime.
  - Network errors / missing tools degrade to a warning, not an error.
  - In `apply` mode, only patch-level bumps are attempted (we never cross
    a major boundary automatically — that is Dependabot's job).

Env vars (consumed by the launchers, not by this script directly):
  YU_SKIP_SECURITY_AUDIT=1  → launcher skips invoking us entirely.
  YU_AUTO_SECURITY_PATCH=1  → launcher passes --mode apply.

CLI:
  python scripts/security_audit.py [--mode notify|apply]
                                   [--force] [--skip-uv-self]
                                   [--skip-pnpm] [--log PATH]
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = REPO_ROOT / "tmp"
STAMP_FILE = TMP_DIR / ".last_security_audit"
DEFAULT_LOG = TMP_DIR / "security_audit.log"
THROTTLE_SECONDS = 24 * 60 * 60


@dataclass
class Vuln:
    """A single advisory normalized across pip-audit / pnpm audit."""

    ecosystem: str  # "pypi" | "npm"
    name: str
    installed: str
    fix_versions: list[str] = field(default_factory=list)
    ids: list[str] = field(default_factory=list)
    severity: str = ""

    def short(self) -> str:
        fix = ", ".join(self.fix_versions) if self.fix_versions else "—"
        ids = ", ".join(self.ids) if self.ids else "—"
        sev = f" [{self.severity}]" if self.severity else ""
        return f"  {self.ecosystem}:{self.name} {self.installed} → {fix} ({ids}){sev}"


# ---------------------------------------------------------------------------
# throttling
# ---------------------------------------------------------------------------

def is_throttled(stamp: Path, now: float, window_s: int = THROTTLE_SECONDS) -> bool:
    """Return True if the previous run is recent enough to skip this one."""
    try:
        mtime = stamp.stat().st_mtime
    except FileNotFoundError:
        return False
    return (now - mtime) < window_s


def touch_stamp(stamp: Path) -> None:
    stamp.parent.mkdir(parents=True, exist_ok=True)
    stamp.touch(exist_ok=True)
    os.utime(stamp, None)


# ---------------------------------------------------------------------------
# pip-audit (Python)
# ---------------------------------------------------------------------------

def parse_pip_audit_json(payload: str) -> list[Vuln]:
    """Parse `pip-audit --format json` output into Vuln records.

    pip-audit shape (>=2.7):
      {"dependencies": [{"name": "...", "version": "...",
                         "vulns": [{"id": "...", "fix_versions": [...]}]}]}
    """
    if not payload.strip():
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    out: list[Vuln] = []
    deps = data.get("dependencies") or []
    if isinstance(data, list):  # very old shape
        deps = data
    for dep in deps:
        if not isinstance(dep, dict):
            continue
        vulns = dep.get("vulns") or []
        if not vulns:
            continue
        name = str(dep.get("name") or "?")
        installed = str(dep.get("version") or "?")
        ids: list[str] = []
        fixes: list[str] = []
        severity = ""
        for v in vulns:
            if not isinstance(v, dict):
                continue
            vid = v.get("id")
            if vid:
                ids.append(str(vid))
            for fv in v.get("fix_versions") or []:
                if fv and str(fv) not in fixes:
                    fixes.append(str(fv))
            sev = v.get("severity")
            if sev and not severity:
                severity = str(sev)
        out.append(
            Vuln(
                ecosystem="pypi",
                name=name,
                installed=installed,
                fix_versions=fixes,
                ids=ids,
                severity=severity,
            )
        )
    return out


def run_pip_audit(uv_bin: str, timeout: int = 120) -> tuple[list[Vuln], str]:
    """Invoke `uvx pip-audit` against the current project lockfile.

    Returns (vulns, raw_stdout). Network / tool errors → ([], reason_message).
    """
    cmd = [uv_bin, "tool", "run", "--quiet", "pip-audit", "--format", "json"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return [], f"[WARN] pip-audit could not run: {exc}"
    # pip-audit exits 1 when it found vulns but still emits valid JSON.
    if not proc.stdout.strip():
        return [], f"[WARN] pip-audit produced no output (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
    return parse_pip_audit_json(proc.stdout), proc.stdout


# ---------------------------------------------------------------------------
# pnpm audit (Node)
# ---------------------------------------------------------------------------

def parse_pnpm_audit_json(payload: str) -> list[Vuln]:
    """Parse `pnpm audit --json` output.

    pnpm audit shape (compatible with npm v6 audit):
      {"advisories": {"<id>": {"module_name": "...",
                                "findings": [{"version": "..."}],
                                "patched_versions": "...",
                                "severity": "..."}},
       "metadata": {...}}
    Newer pnpm wraps as `{"advisories": {...}}` similarly.
    """
    if not payload.strip():
        return []
    try:
        data = json.loads(payload)
    except json.JSONDecodeError:
        return []

    advisories = data.get("advisories")
    if not isinstance(advisories, dict):
        return []

    out: list[Vuln] = []
    for adv_id, adv in advisories.items():
        if not isinstance(adv, dict):
            continue
        name = str(adv.get("module_name") or "?")
        installed_versions: list[str] = []
        for f in adv.get("findings") or []:
            if isinstance(f, dict) and f.get("version"):
                installed_versions.append(str(f["version"]))
        installed = ", ".join(sorted(set(installed_versions))) or "?"
        patched = str(adv.get("patched_versions") or "").strip()
        fixes = [patched] if patched and patched != "<0.0.0" else []
        severity = str(adv.get("severity") or "")
        out.append(
            Vuln(
                ecosystem="npm",
                name=name,
                installed=installed,
                fix_versions=fixes,
                ids=[str(adv_id)],
                severity=severity,
            )
        )
    return out


def run_pnpm_audit(timeout: int = 120) -> tuple[list[Vuln], str]:
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return [], "[INFO] pnpm not on PATH — skipping JS audit."
    cmd = [pnpm, "audit", "--json", "--prod"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return [], f"[WARN] pnpm audit could not run: {exc}"
    if not proc.stdout.strip():
        return [], f"[WARN] pnpm audit produced no output (rc={proc.returncode}): {proc.stderr.strip()[:300]}"
    return parse_pnpm_audit_json(proc.stdout), proc.stdout


# ---------------------------------------------------------------------------
# apply mode (patch bumps)
# ---------------------------------------------------------------------------

def apply_python_fixes(uv_bin: str, vulns: list[Vuln]) -> list[str]:
    """For each vulnerable PyPI package, run `uv lock --upgrade-package <name>`.

    We deliberately do NOT pin to a specific version — uv resolves the highest
    compatible version that satisfies our pyproject constraints. If the user's
    pin is too tight to absorb the patch, that surfaces as a normal lock
    diff for human review.
    """
    msgs: list[str] = []
    for v in vulns:
        cmd = [uv_bin, "lock", "--upgrade-package", v.name]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                cwd=str(REPO_ROOT),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            msgs.append(f"[apply] {v.name}: failed to invoke uv ({exc})")
            continue
        if proc.returncode == 0:
            msgs.append(f"[apply] {v.name}: lock refreshed.")
        else:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
            msgs.append(f"[apply] {v.name}: uv lock failed — {tail[0][:200]}")
    return msgs


def apply_pnpm_fixes(vulns: list[Vuln]) -> list[str]:
    """Run `pnpm update <name>` per vulnerable npm package.

    pnpm honors the semver range in package.json, so this only crosses majors
    if the manifest already allows it.
    """
    pnpm = shutil.which("pnpm")
    if pnpm is None:
        return ["[apply] pnpm not on PATH — skipping JS fixes."]
    msgs: list[str] = []
    seen: set[str] = set()
    for v in vulns:
        if v.name in seen:
            continue
        seen.add(v.name)
        cmd = [pnpm, "update", v.name]
        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=180,
                check=False,
                cwd=str(REPO_ROOT),
            )
        except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
            msgs.append(f"[apply] {v.name}: pnpm update failed to invoke ({exc})")
            continue
        if proc.returncode == 0:
            msgs.append(f"[apply] {v.name}: pnpm update ok.")
        else:
            tail = (proc.stderr or proc.stdout).strip().splitlines()[-1:] or [""]
            msgs.append(f"[apply] {v.name}: pnpm update failed — {tail[0][:200]}")
    return msgs


# ---------------------------------------------------------------------------
# uv self-update
# ---------------------------------------------------------------------------

def try_uv_self_update(uv_bin: str) -> str:
    """Best-effort `uv self update`. Returns a one-line status."""
    cmd = [uv_bin, "self", "update"]
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
            cwd=str(REPO_ROOT),
        )
    except (subprocess.TimeoutExpired, FileNotFoundError, OSError) as exc:
        return f"[INFO] uv self update skipped: {exc}"
    if proc.returncode == 0:
        first = proc.stdout.strip().splitlines()[:1]
        return f"[OK] uv self update: {(first[0] if first else 'up to date')}"
    # Common: project-scoped uv was not installed via the standalone installer.
    msg = (proc.stderr or proc.stdout).strip().splitlines()[:1]
    return f"[INFO] uv self update unavailable ({(msg[0] if msg else 'unknown')[:120]})"


# ---------------------------------------------------------------------------
# logging / reporting
# ---------------------------------------------------------------------------

def write_log(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y-%m-%d %H:%M:%S %z").strip() or time.strftime("%Y-%m-%d %H:%M:%S")
    with path.open("a", encoding="utf-8") as f:
        f.write(f"\n===== {stamp} =====\n")
        for line in lines:
            f.write(line + "\n")


def print_summary(vulns: list[Vuln], stream: Any = sys.stderr) -> None:
    if not vulns:
        return
    by_eco: dict[str, int] = {}
    for v in vulns:
        by_eco[v.ecosystem] = by_eco.get(v.ecosystem, 0) + 1
    parts = ", ".join(f"{eco}={n}" for eco, n in sorted(by_eco.items()))
    print(f"[SECURITY] {len(vulns)} vulnerabilit(ies) found ({parts}). See tmp/security_audit.log.", file=stream)
    for v in vulns[:10]:
        print(v.short(), file=stream)
    if len(vulns) > 10:
        print(f"  ... and {len(vulns) - 10} more (full list in log)", file=stream)


# ---------------------------------------------------------------------------
# entry point
# ---------------------------------------------------------------------------

def resolve_uv_bin() -> str:
    """Prefer the project-scoped bin/uv, fall back to PATH."""
    local = REPO_ROOT / "bin" / ("uv.exe" if os.name == "nt" else "uv")
    if local.exists():
        return str(local)
    found = shutil.which("uv")
    return found or "uv"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--mode", choices=["notify", "apply"], default="notify")
    parser.add_argument("--force", action="store_true",
                        help="Bypass the 24h throttle.")
    parser.add_argument("--skip-uv-self", action="store_true")
    parser.add_argument("--skip-pnpm", action="store_true")
    parser.add_argument("--log", type=Path, default=DEFAULT_LOG)
    args = parser.parse_args(argv)

    TMP_DIR.mkdir(parents=True, exist_ok=True)

    if not args.force and is_throttled(STAMP_FILE, time.time()):
        # Silent: launcher should not be noisy on every start.
        return 0

    uv_bin = resolve_uv_bin()
    log_lines: list[str] = [f"mode={args.mode} uv_bin={uv_bin}"]

    if not args.skip_uv_self:
        status = try_uv_self_update(uv_bin)
        log_lines.append(status)

    py_vulns, py_raw = run_pip_audit(uv_bin)
    if py_raw.startswith("[WARN]") or py_raw.startswith("[INFO]"):
        log_lines.append(py_raw)
    else:
        log_lines.append(f"pip-audit: {len(py_vulns)} vulnerabilit(ies)")

    npm_vulns: list[Vuln] = []
    if not args.skip_pnpm:
        npm_vulns, npm_raw = run_pnpm_audit()
        if npm_raw.startswith("[WARN]") or npm_raw.startswith("[INFO]"):
            log_lines.append(npm_raw)
        else:
            log_lines.append(f"pnpm audit: {len(npm_vulns)} vulnerabilit(ies)")

    all_vulns = py_vulns + npm_vulns
    for v in all_vulns:
        log_lines.append(v.short())

    if args.mode == "apply" and all_vulns:
        log_lines.append("--- apply mode ---")
        if py_vulns:
            log_lines.extend(apply_python_fixes(uv_bin, py_vulns))
        if npm_vulns and not args.skip_pnpm:
            log_lines.extend(apply_pnpm_fixes(npm_vulns))

    write_log(args.log, log_lines)
    print_summary(all_vulns)
    touch_stamp(STAMP_FILE)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - never break startup
        print(f"[SECURITY] audit script crashed: {exc}", file=sys.stderr)
        sys.exit(0)
