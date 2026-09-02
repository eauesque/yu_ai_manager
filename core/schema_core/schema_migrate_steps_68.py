"""Migration 68: persist Bridge sweep run metadata in DB tables.

Pre-migration, sweep run info lived in two places:

* per-image XMP packets (``sweep:*`` namespace) — survives DB rebuilds but
  reading 500 packets to render a history list is slow.
* per-browser localStorage on the bridge / sweep pages — fast but scoped
  to one browser, capped at 500 entries, and lost across devices.

Migration 68 introduces ``sweeps`` (run header) + ``sweep_axes`` (per-axis
parameter) so the dedicated ``/sweep`` page can render history straight
from the DB and apply server-side filters (sampler / resolution / steps /
CFG / etc.).

Population paths:

* At save time, ``core.bridge_core.bridge_save_batch`` UPSERTs the run
  header and inserts axis rows the first time a sweep id is seen. Each
  batch also updates ``last_file_id`` / ``file_count``.
* For sweeps that pre-date this migration, ``scripts/backfill_sweeps.py``
  walks ``has_sweep=1`` files and reconstructs rows from XMP attrs.
"""

import logging

from .schema_migrate_version import set_schema_version

logger = logging.getLogger(__name__)


def apply_migration_68(con) -> None:
    logger.info("  -> Migration 68: sweeps + sweep_axes tables")
    con.executescript("""
    CREATE TABLE IF NOT EXISTS sweeps (
      id TEXT PRIMARY KEY,
      bridge TEXT NOT NULL,
      base_seed INTEGER,
      created_at INTEGER NOT NULL,
      prompt_template TEXT,
      negative_template TEXT,
      checkpoint TEXT,
      vae TEXT,
      sampler TEXT,
      width INTEGER,
      height INTEGER,
      steps INTEGER,
      cfg REAL,
      axis_count INTEGER NOT NULL DEFAULT 0,
      first_file_id INTEGER,
      last_file_id INTEGER,
      file_count INTEGER NOT NULL DEFAULT 0,
      status TEXT NOT NULL DEFAULT 'completed',
      updated_at INTEGER NOT NULL,
      FOREIGN KEY (first_file_id) REFERENCES files(id) ON DELETE SET NULL,
      FOREIGN KEY (last_file_id) REFERENCES files(id) ON DELETE SET NULL
    );

    CREATE INDEX IF NOT EXISTS idx_sweeps_created_at ON sweeps(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_sweeps_bridge ON sweeps(bridge);
    CREATE INDEX IF NOT EXISTS idx_sweeps_checkpoint ON sweeps(checkpoint) WHERE checkpoint IS NOT NULL;
    CREATE INDEX IF NOT EXISTS idx_sweeps_sampler ON sweeps(sampler) WHERE sampler IS NOT NULL;

    CREATE TABLE IF NOT EXISTS sweep_axes (
      sweep_id TEXT NOT NULL,
      axis_index INTEGER NOT NULL,
      param TEXT NOT NULL,
      total INTEGER NOT NULL,
      PRIMARY KEY (sweep_id, axis_index),
      FOREIGN KEY (sweep_id) REFERENCES sweeps(id) ON DELETE CASCADE
    );

    CREATE INDEX IF NOT EXISTS idx_sweep_axes_param ON sweep_axes(param);
    """)
    set_schema_version(con, 68, "Bridge sweep history (sweeps + sweep_axes)")
