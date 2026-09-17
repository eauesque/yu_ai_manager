"""Background backfill: populate ``sweeps`` / ``sweep_axes`` from XMP packets.

Specialization of :class:`core.services_core.backfill_task.BackfillTask`
for the Bridge sweep history tables introduced in migration 68. Walks
every active image file in chunks, reads the ``sweep:*`` namespace, and
UPSERTs the run header + axes whenever ``sweep:id`` is present. Also
flips ``files.has_sweep`` so the search filter ("sweep あり") and the
next backfill pass converge.

Runs once per DB lifetime, after migrations. Progress is checkpointed
to ``db_meta`` (``sweeps_backfill_cursor`` / ``sweeps_backfill_done`` /
``sweeps_backfill_started_at``) — a crashed / restarted process picks
up exactly where it left off.

Throttle: 50 files per batch, 100ms between batches → ~50 files/sec,
light enough not to perturb interactive browsing on the same NAS.
"""

from __future__ import annotations

import logging
from pathlib import Path

from core.services_core.backfill_task import BackfillTask

logger = logging.getLogger(__name__)

CHUNK_SIZE = 50
BATCH_SLEEP = 0.1

_CANDIDATE_SQL = """
SELECT id, path, has_sweep FROM files
WHERE id > ?
  AND is_deleted = 0
  AND path NOT LIKE '%!%'
  AND (path LIKE '%.png' OR path LIKE '%.jpg'
       OR path LIKE '%.jpeg' OR path LIKE '%.webp')
ORDER BY id
LIMIT ?
"""


def _scan_one_for_sweep(con, row) -> dict[str, int]:
    """Process one (id, path, has_sweep) row. Returns stats delta."""
    from core.bridge_core.sweep_db import attrs_to_meta, upsert_sweep_sync
    from core.tools.xmp import read_namespaces

    fid, path, hs = int(row[0]), row[1], int(row[2] or 0)
    p = Path(path)
    if not p.exists() or "!" in str(p):
        return {}
    try:
        attrs = read_namespaces(str(p)).get_attrs("sweep")
    except Exception as exc:  # noqa: BLE001
        logger.debug("xmp read failed for %s: %s", path, exc)
        return {}
    meta = attrs_to_meta(attrs)
    if meta is None:
        return {}
    if not upsert_sweep_sync(con, meta, fid):
        return {}
    delta = {"upserted": 1}
    if not hs:
        try:
            con.execute("UPDATE files SET has_sweep=1 WHERE id=?", (fid,))
            delta["flagged"] = 1
        except Exception as exc:  # noqa: BLE001
            logger.debug("flag flip failed for fid=%s: %s", fid, exc)
    return delta


_task = BackfillTask(
    name="sweeps_backfill",
    candidate_sql=_CANDIDATE_SQL,
    processor=_scan_one_for_sweep,
    chunk_size=CHUNK_SIZE,
    batch_sleep=BATCH_SLEEP,
)


def schedule_sweep_backfill() -> None:
    """Idempotent. Spawns the daemon thread on first call."""
    _task.schedule()


def stop_sweep_backfill() -> None:
    """Signal the worker to stop after the current chunk."""
    _task.stop()


__all__ = ["schedule_sweep_backfill", "stop_sweep_backfill"]
