"""Persistence for MeshInferenceState.

Schema v1:
    { "version": 1, "disabled": { "<peer_id>": ["tagger", "clip", ...], ... } }

Atomic write: serialize to .tmp sibling, then os.replace to target. Version
bumps should add a migration branch in load_state().
"""
from __future__ import annotations

import json
import logging
import os
import threading
from pathlib import Path

from .peer_id import is_valid_peer_id

logger = logging.getLogger("core.mesh_inference.persistence")

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
    return data_path("mesh_inference_state.json")

_write_lock = threading.Lock()


def _empty_state() -> dict[str, dict[str, list[str]]]:
    return {"disabled": {}}


def load_state() -> dict[str, dict[str, list[str]]]:
    """Read mesh_inference_state.json. Returns {'disabled': {peer_id: [...]}}.

    Falls back to empty state on: missing file, JSON error, version mismatch,
    missing keys. Invalid peer_id entries are dropped with a warning but the
    rest of the state loads normally.
    """
    path = _current_state_path()
    if not path.exists():
        return _empty_state()

    try:
        raw = path.read_text(encoding="utf-8")
        data = json.loads(raw)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning(
            "[mesh_inference] state file corrupt, using defaults: %s", exc
        )
        return _empty_state()

    if not isinstance(data, dict):
        return _empty_state()

    if data.get("version") != CURRENT_VERSION:
        logger.warning(
            "[mesh_inference] state version=%r unsupported (expected %d), "
            "using defaults",
            data.get("version"), CURRENT_VERSION,
        )
        return _empty_state()

    raw_disabled = data.get("disabled")
    if not isinstance(raw_disabled, dict):
        return _empty_state()

    clean: dict[str, list[str]] = {}
    for pid, types in raw_disabled.items():
        if not is_valid_peer_id(pid):
            logger.warning(
                "[mesh_inference] skipping invalid peer_id in state: %r", pid
            )
            continue
        if not isinstance(types, list):
            continue
        clean_types = [t for t in types if isinstance(t, str)]
        if clean_types:
            clean[pid] = clean_types

    return {"disabled": clean}


def save_state(disabled: dict[str, list[str]]) -> None:
    """Atomically write the disabled map to STATE_PATH."""
    path = _current_state_path()
    payload = {
        "version": CURRENT_VERSION,
        "disabled": {k: sorted(v) for k, v in disabled.items()},
    }
    serialized = json.dumps(payload, ensure_ascii=False, indent=2)

    with _write_lock:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        tmp_path.write_text(serialized, encoding="utf-8")
        os.replace(tmp_path, path)
