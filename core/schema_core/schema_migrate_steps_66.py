"""Migration 66: track peer reachability for auto-prune of stale LAN peers.

Adds two nullable INTEGER columns to ``peers``:

* ``last_reached_at``  — UNIX seconds of the most recent successful
  ``/ext/lan_cowork/fleet/info`` 200 response.
* ``last_attempted_at`` — UNIX seconds of the most recent fetch attempt
  (success or failure).

These are used by FleetManager to:

1. Skip peers in a soft-prune backoff window (default: 1 h since last reach).
2. Hard-prune rows whose ``last_reached_at`` is older than 7 days on next
   load (avoids unbounded growth as DHCP rotates IPs).
"""

import logging

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def _column_exists(con, table: str, column: str) -> bool:
    rows = con.execute(f"PRAGMA table_info({table})").fetchall()
    return any(r[1] == column for r in rows)


def apply_migration_66(con) -> None:
    logger.info("  -> Migration 66: peers.last_reached_at / last_attempted_at")
    if not _column_exists(con, "peers", "last_reached_at"):
        con.execute("ALTER TABLE peers ADD COLUMN last_reached_at INTEGER")
    if not _column_exists(con, "peers", "last_attempted_at"):
        con.execute("ALTER TABLE peers ADD COLUMN last_attempted_at INTEGER")
    set_schema_version(con, 66, "Track peer reachability for auto-prune")
