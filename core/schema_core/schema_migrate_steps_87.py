"""Schema migration 87: import the legacy mesh inference overlay."""

import json
import logging
import re
import sqlite3
from pathlib import Path

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)
STATE_PATH: Path | None = None
_PEER_ID = re.compile(r"^[A-Za-z0-9_\-.:]{1,64}$")


def apply_migration_87(con: sqlite3.Connection) -> None:
    """Import the JSON overlay without modifying it for downgrade compatibility."""
    logger.info("  -> Migration 87: import mesh inference disabled overlay")
    path = STATE_PATH
    if path is None:
        from core.paths import data_path

        path = data_path("mesh_inference_state.json")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        payload = {}
    # Migrations are frozen historical artifacts; keep parsing here, not in live persistence.
    disabled = payload.get("disabled", {}) if payload.get("version") == 1 else {}
    if not isinstance(disabled, dict):
        disabled = {}
    for peer_id, inference_types in disabled.items():
        if not isinstance(peer_id, str) or not _PEER_ID.fullmatch(peer_id):
            continue
        if not isinstance(inference_types, list):
            continue
        for inference_type in inference_types:
            if not isinstance(inference_type, str):
                continue
            con.execute(
                "INSERT OR IGNORE INTO peer_inference_disabled "
                "(peer_id, inference_type) VALUES (?, ?)",
                (peer_id, inference_type),
            )

    row = con.execute(
        "SELECT 1 FROM schema_version WHERE version=? LIMIT 1", (87,)
    ).fetchone()
    if row is None:
        set_schema_version(con, 87, "import mesh inference disabled overlay")
