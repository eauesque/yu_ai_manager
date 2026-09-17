# core/node_identity.py
"""Persistent node identifier used for mDNS self-identification.

A 32-hex UUID is generated on first run and stored under ``data/node_id.txt``.
Every subsequent run loads the same id so that other nodes on the LAN can
recognise us across restarts and so that zeroconf service name collisions
don't change our identity.
"""
from __future__ import annotations

import logging
import re
import uuid
from pathlib import Path

logger = logging.getLogger("core.node_identity")

# Sentinel: when None, _current_node_id_path() resolves via core.paths.data_path().
# Tests may monkey-patch this attribute directly to override the location.
_NODE_ID_PATH: Path | None = None
_CACHED_NODE_ID: str | None = None
_HEX32 = re.compile(r"^[0-9a-f]{32}$")


def _current_node_id_path() -> Path:
    """Resolve the node_id file path, honoring test monkey-patches."""
    if _NODE_ID_PATH is not None:
        return _NODE_ID_PATH
    from core.paths import data_path
    return data_path("node_id.txt")


def get_node_id() -> str:
    """Return this node's persistent 32-hex identifier.

    Creates the id (and parent directory) on first call. Corrupted files are
    replaced with a fresh id and a warning log.
    """
    global _CACHED_NODE_ID
    if _CACHED_NODE_ID is not None:
        return _CACHED_NODE_ID

    path = _current_node_id_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    if path.exists():
        raw = path.read_text().strip().lower()
        if _HEX32.match(raw):
            _CACHED_NODE_ID = raw
            return raw
        logger.warning(
            "[node_identity] corrupted node_id file at %s, regenerating", path
        )

    new_id = uuid.uuid4().hex
    path.write_text(new_id)
    _CACHED_NODE_ID = new_id
    logger.info("[node_identity] generated new node_id=%s", new_id)
    return new_id
