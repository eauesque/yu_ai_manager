"""Persistence layer for LLM Router runtime state.

Currently stores only the list of administratively-disabled backend aliases.
Format is forward-compatible via the `version` field; bumps must add a
migration in load_state().
"""

from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

logger = logging.getLogger("core.llm_router.persistence")

# Schema version. Increment when the on-disk format changes in an
# incompatible way and add a migration branch in load_state().
CURRENT_VERSION = 1

# Default location, resolved lazily at call time via core.paths so the
# Tauri installer can redirect writes via TAGDB_DATA_DIR. Tests can
# monkey-patch this module attribute to a tmpdir to bypass core.paths.
STATE_PATH: Path | None = None


def _current_state_path() -> Path:
    """Return the path to use for read/write. Honors a monkey-patched STATE_PATH."""
    if STATE_PATH is not None:
        return STATE_PATH
    from core.paths import data_path
    return data_path("llm_router_state.json")

_write_lock = threading.Lock()


def _empty_state() -> dict:
    return {"disabled_aliases": []}


def load_state() -> dict:
    """Read llm_router_state.json. Returns {'disabled_aliases': [...]}.

    Falls back to an empty state on:
      - file does not exist
      - JSON parse error
      - unsupported `version` field
      - missing required keys
    """
    path = _current_state_path()
    if not path.exists():
        return _empty_state()

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "[llm_router] state file corrupt, using defaults: %s", exc
        )
        return _empty_state()

    if not isinstance(data, dict):
        logger.warning(
            "[llm_router] state file root is not an object, using defaults"
        )
        return _empty_state()

    version = data.get("version")
    if version != CURRENT_VERSION:
        logger.warning(
            "[llm_router] state file version=%r is unsupported (expected %d), "
            "using defaults",
            version, CURRENT_VERSION,
        )
        return _empty_state()

    aliases = data.get("disabled_aliases")
    if not isinstance(aliases, list):
        return _empty_state()

    # Sanitize: only keep string entries
    return {"disabled_aliases": [str(a) for a in aliases if isinstance(a, str)]}


def save_disabled_aliases(aliases: list[str]) -> None:
    """Atomically write the disabled-aliases snapshot to disk.

    Writes to a sibling .tmp file then os.replace's it onto the real path,
    so a crash mid-write cannot corrupt the existing file.
    """
    path = _current_state_path()
    payload = {
        "version": CURRENT_VERSION,
        "disabled_aliases": list(aliases),
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)

    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(serialized, encoding="utf-8")
        os.replace(tmp_path, path)
