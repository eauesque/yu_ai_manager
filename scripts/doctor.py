#!/usr/bin/env python3
"""Diagnose a checkout without starting anything.

Answers the question a user actually has when the app misbehaves: *which*
server would start, and what would stop the other one. Every verdict is
computed by the same functions the launcher uses -- `fast_mode.decide`,
`checkout_blockers`, `dist_is_fresh` -- rather than by a second copy of the
rules, so a doctor that says "fine" cannot disagree with a launch that fails.

Exit code is 0 when nothing is broken, 1 when at least one ERROR was found.
WARN alone does not fail: a missing optional tool degrades a feature, it does
not stop the server.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sqlite3
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

OK = "OK"
WARN = "WARN"
ERROR = "ERROR"


@dataclass
class Finding:
    level: str
    topic: str
    detail: str


def _run(cmd: list[str], timeout: int = 10) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout,
            encoding="utf-8", errors="replace",
        )
        return proc.returncode, (proc.stdout or proc.stderr or "").strip()
    except FileNotFoundError:
        return 127, "not found"
    except subprocess.TimeoutExpired:
        return 124, f"timed out after {timeout}s"
    except OSError as exc:
        return 1, str(exc)


def check_launch_target(repo: Path, argv: list[str]) -> list[Finding]:
    """Which server this checkout would start, and why."""
    from scripts import fast_mode
    from scripts.internal.fast_mode_env import python_only_requested

    out: list[Finding] = []
    if python_only_requested(argv):
        out.append(
            Finding(OK, "launch target", "Python (--python / YU_FORCE_PYTHON requested)")
        )
        return out
    if os.environ.get("YU_SKIP_FAST_MODE") == "1":
        out.append(Finding(OK, "launch target", "Python (YU_SKIP_FAST_MODE=1)"))
        return out

    binary = fast_mode.binary_path(repo)
    decision = fast_mode.decide(repo, binary)
    if decision.use_fast_mode:
        out.append(Finding(OK, "launch target", f"Rust yu-server ({decision.reason})"))
    else:
        # Not an error: falling back to Python is a supported outcome, and the
        # reason is the useful part.
        out.append(Finding(WARN, "launch target", f"Python — {decision.reason}"))
    out.append(
        Finding(
            OK if binary.exists() else WARN,
            "rust binary",
            str(binary) if binary.exists() else f"absent ({binary})",
        )
    )
    return out


def check_toolchain() -> list[Finding]:
    """The external programs the app shells out to."""
    out: list[Finding] = []

    uv = REPO / "bin" / "uv"
    if uv.exists():
        code, text = _run([str(uv), "--version"])
        out.append(Finding(OK if code == 0 else ERROR, "uv", text.splitlines()[0] if text else "?"))
    else:
        out.append(Finding(ERROR, "uv", f"missing: {uv} (run scripts/bootstrap_uv.sh)"))

    for tool, topic, level_when_missing in (
        ("ffprobe", "ffprobe", WARN),
        ("ffmpeg", "ffmpeg", WARN),
        ("node", "node", WARN),
    ):
        path = shutil.which(tool)
        if path:
            code, text = _run([tool, "-version" if tool != "node" else "--version"], timeout=8)
            first = text.splitlines()[0] if text else ""
            out.append(Finding(OK, topic, f"{path} — {first[:60]}"))
        else:
            out.append(
                Finding(
                    level_when_missing,
                    topic,
                    "not on PATH (audio/video metadata is skipped without it)"
                    if tool in ("ffprobe", "ffmpeg")
                    else "not on PATH (needed only to rebuild the web bundle)",
                )
            )
    return out


def check_bundle(repo: Path) -> list[Finding]:
    from scripts import fast_mode

    fresh, why = fast_mode.dist_is_fresh(repo)
    return [Finding(OK if fresh else WARN, "web bundle", "fresh" if fresh else why)]


def check_extensions(repo: Path) -> list[Finding]:
    from scripts import fast_mode

    unlisted = fast_mode.unlisted_extensions(repo)
    if not unlisted:
        return [Finding(OK, "extensions", "all bundled extensions are on the roster")]
    return [
        Finding(
            WARN,
            "extensions",
            f"outside the bundled roster (forces the Python server): {', '.join(unlisted)}",
        )
    ]


def _db_path(repo: Path) -> Path:
    explicit = os.environ.get("TAGDB_DB")
    if explicit:
        return Path(explicit)
    config = repo / "config.json"
    if config.exists():
        try:
            data = json.loads(config.read_text(encoding="utf-8"))
            if isinstance(data, dict) and data.get("db"):
                return Path(str(data["db"]))
        except (OSError, ValueError):
            pass
    return repo / "data" / "tags.db"


def check_database(repo: Path) -> list[Finding]:
    """Reachability and schema of the library database.

    Read-only throughout: a diagnosis must not be the thing that modifies the
    database it is diagnosing.
    """
    from scripts import fast_mode

    path = _db_path(repo)
    if not path.exists():
        return [Finding(WARN, "database", f"absent (created on first run): {path}")]

    out = [Finding(OK, "database", str(path))]
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error as exc:
        out.append(Finding(ERROR, "database open", f"{exc} (encrypted DB needs YU_DB_KEY)"))
        return out

    try:
        version = con.execute("SELECT MAX(version) FROM schema_version").fetchone()[0]
        wanted = fast_mode.expected_schema_version(repo)
        if wanted is not None and version != wanted:
            out.append(
                Finding(
                    ERROR,
                    "schema version",
                    f"database is {version}, this checkout expects {wanted}",
                )
            )
        else:
            out.append(Finding(OK, "schema version", str(version)))
        files = con.execute("SELECT COUNT(*) FROM files WHERE is_deleted = 0").fetchone()[0]
        tags = con.execute("SELECT COUNT(*) FROM tags").fetchone()[0]
        out.append(Finding(OK, "library", f"{files} files, {tags} tags"))
    except sqlite3.Error as exc:
        # A SQLCipher database answers this way for the right reason.
        out.append(
            Finding(
                ERROR,
                "database read",
                f"{exc} — an encrypted database needs YU_DB_KEY to be set",
            )
        )
    finally:
        con.close()
    return out


def check_scan_roots(repo: Path) -> list[Finding]:
    """Whether the configured scan roots are actually reachable."""
    config = repo / "config.json"
    if not config.exists():
        return [Finding(WARN, "scan roots", "config.json absent")]
    try:
        data = json.loads(config.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        return [Finding(ERROR, "config.json", f"unreadable: {exc}")]

    roots = data.get("scan_roots") if isinstance(data, dict) else None
    if not roots:
        return [Finding(WARN, "scan roots", "none configured")]

    out: list[Finding] = []
    for entry in roots:
        if isinstance(entry, str):
            path, enabled = entry, True
        elif isinstance(entry, dict):
            path, enabled = str(entry.get("path", "")), bool(entry.get("enabled", True))
        else:
            continue
        if not path:
            continue
        state = "enabled" if enabled else "disabled"
        if Path(path).is_dir():
            out.append(Finding(OK, "scan root", f"{path} ({state})"))
        else:
            # An unreachable root is why a scan "finds nothing"; naming it is
            # the whole point of this check.
            out.append(
                Finding(
                    WARN if not enabled else ERROR,
                    "scan root",
                    f"{path} ({state}) — not a directory",
                )
            )
    return out


def collect(repo: Path, argv: list[str]) -> list[Finding]:
    findings: list[Finding] = []
    for step in (
        lambda: check_launch_target(repo, argv),
        check_toolchain,
        lambda: check_bundle(repo),
        lambda: check_extensions(repo),
        lambda: check_database(repo),
        lambda: check_scan_roots(repo),
    ):
        try:
            findings.extend(step())
        except Exception as exc:  # noqa: BLE001 -- one broken probe must not hide the rest
            findings.append(Finding(ERROR, "doctor", f"check failed: {type(exc).__name__}: {exc}"))
    return findings


def render(findings: list[Finding]) -> str:
    width = max((len(f.topic) for f in findings), default=0)
    lines = []
    for f in findings:
        lines.append(f"[{f.level:<5}] {f.topic.ljust(width)}  {f.detail}")
    errors = sum(1 for f in findings if f.level == ERROR)
    warns = sum(1 for f in findings if f.level == WARN)
    lines.append("")
    lines.append(f"{len(findings)} checks, {errors} error(s), {warns} warning(s)")
    # The flags a reader of this output is most likely to want next.
    lines.append("")
    lines.append("hints:")
    lines.append("  ./start.sh --python      force the Python server (env: YU_FORCE_PYTHON=1)")
    lines.append("  ./start.sh --safe-mode   start with repair-safe subsystems only")
    lines.append("  ./start.sh --doctor      this report (add --json for machine output)")
    lines.append("  ./start.sh --doctor --update-tools   re-download bin/uv to the pinned version")

    return "\n".join(lines)


def update_tools() -> int:
    """Force-refresh bin/uv against the pinned DEFAULT_UV_VERSION."""
    if os.name == "nt":
        cmd = [
            "powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
            "-File", str(REPO / "scripts" / "bootstrap_uv.ps1"), "-Force",
        ]
    else:
        cmd = ["bash", str(REPO / "scripts" / "bootstrap_uv.sh"), "--force"]
    return subprocess.run(cmd, cwd=str(REPO), check=False).returncode


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    parser.add_argument(
        "--update-tools", action="store_true",
        help="Re-download bin/uv to the pinned version, even if already present",
    )
    parser.add_argument(
        "--", dest="_sep", action="store_true", help=argparse.SUPPRESS
    )
    args, passthrough = parser.parse_known_args(argv)

    if args.update_tools:
        return update_tools()

    findings = collect(REPO, passthrough)
    if args.json:
        print(
            json.dumps(
                {
                    "findings": [
                        {"level": f.level, "topic": f.topic, "detail": f.detail}
                        for f in findings
                    ],
                    "errors": sum(1 for f in findings if f.level == ERROR),
                    "warnings": sum(1 for f in findings if f.level == WARN),
                },
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        print(render(findings))
    return 1 if any(f.level == ERROR for f in findings) else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
