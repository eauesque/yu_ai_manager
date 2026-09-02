"""What this machine is doing about a self-built Rust server.

Only the Python launch can answer this, and that is not a gap: fast_mode's
`main()` spawns an acquisition exactly on the branch where it also refuses
fast mode, so a build only ever runs while Python is the server. A Rust
launch means the binary is already there.

Everything here is read from files the acquisition child writes; nothing is
inferred from a process table, which would not survive a restart.
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

_LAST_LINE_LIMIT = 200
_TAIL_BYTES = 8192


def _last_line(path: Path) -> str | None:
    """The most recent line cargo wrote, or None when there is nothing yet.

    Reads only the tail: a release build's log runs to megabytes and this is
    polled every few seconds.
    """
    try:
        size = path.stat().st_size
        with path.open("rb") as handle:
            if size > _TAIL_BYTES:
                handle.seek(size - _TAIL_BYTES)
            chunk = handle.read()
    except OSError:
        return None
    text = chunk.decode("utf-8", errors="replace")
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if stripped:
            return stripped[:_LAST_LINE_LIMIT]
    return None


def fast_mode_build_status(repo: Path | None = None) -> dict[str, Any]:
    """Report the local Rust build: how it is configured, and what happened."""
    from scripts import fast_mode

    root = repo if repo is not None else Path.cwd()
    state = fast_mode.read_build_state(root)
    log_path = fast_mode.build_log_path(root)
    acquiring = fast_mode.acquire_lock_path(root).exists()

    phase = state.get("phase")
    if phase not in {"building", "ok", "failed"}:
        phase = "idle"

    try:
        log_bytes = log_path.stat().st_size
    except OSError:
        log_bytes = 0

    started_at = state.get("started_at")
    source = fast_mode.acquire_source(root)
    return {
        "source": source,
        "enabled": source in {"build", "auto"},
        # "building" with no acquisition holding the lock means the child died
        # without recording a result -- the OOM case the setting warns about.
        # Reporting that as "still compiling" would leave the user waiting for
        # a process that is gone.
        "phase": "stalled" if phase == "building" and not acquiring else phase,
        "acquiring": acquiring,
        "started_at": started_at,
        "finished_at": state.get("finished_at"),
        "elapsed_seconds": (
            int(time.time() - started_at)
            if phase == "building" and isinstance(started_at, (int, float))
            else None
        ),
        "failures": fast_mode.consecutive_build_failures(root),
        "max_failures": fast_mode._MAX_BUILD_FAILURES,
        "last_line": _last_line(log_path),
        "last_message": str(state.get("last") or "")[:_LAST_LINE_LIMIT] or None,
        "log_bytes": log_bytes,
        "decision": _decision(root),
        # Asked live, not read from the recorded verdict: the bundle can be
        # rebuilt after a launch decided against it (the launcher's retry,
        # web_ui.py's inline build, or a hand-run `pnpm build`), and a
        # snapshot would keep naming a staleness that no longer exists.
        "blockers": _blockers(root),
        "config": _config_files(),
    }


def _blockers(root: Path) -> list[str] | None:
    """Reasons fast mode cannot be used right now, or None if unknown."""
    from scripts import fast_mode

    try:
        return fast_mode.checkout_blockers(root)
    except Exception:  # noqa: BLE001 -- a diagnostic never breaks the response
        return None


def _config_files() -> dict[str, Any]:
    """Which config file the setting is read from, and which are ignored.

    A read stops at the first existing candidate while a write goes to the
    default path, so a config.toml next to a config.json makes every saved
    setting invisible. The user cannot diagnose that from a settings screen
    that only shows values.
    """
    from core.configuration.json_rw import effective_config_path, shadowed_config_paths

    try:
        return {
            "read_from": effective_config_path(),
            "shadowed": shadowed_config_paths(),
        }
    except Exception:  # noqa: BLE001 -- a diagnostic never breaks the response
        return {"read_from": None, "shadowed": []}


def _decision(root: Path) -> dict[str, Any] | None:
    """The last launch's verdict, or None when no launch has recorded one.

    Without this, a refusal whose cause is the checkout rather than the binary
    (a stale web bundle, an unlisted extension) produces no download, no
    build, no log and no explanation -- the setting simply appears to do
    nothing.
    """
    from scripts import fast_mode

    try:
        data = json.loads(fast_mode.decision_path(root).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    return {
        "use_fast_mode": bool(data.get("use_fast_mode")),
        "reason": str(data.get("reason") or "")[:_LAST_LINE_LIMIT] or None,
        # False means acquiring a binary cannot change the answer, so nothing
        # was even attempted. That distinction is the whole point of showing
        # this.
        "needs_binary": bool(data.get("needs_binary", True)),
        "at": data.get("at"),
    }
