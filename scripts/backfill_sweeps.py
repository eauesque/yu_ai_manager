#!/usr/bin/env python3
"""One-shot backfill for the ``sweeps`` and ``sweep_axes`` tables.

Walks ``has_sweep=1`` files, reads each file's ``sweep:*`` XMP attrs, and
UPSERTs the run header + axes into the DB so the ``/sweep`` history page
can list past sweeps without re-reading XMP every request.

Idempotent: re-running only adds files / runs that were missed before.
``ON CONFLICT(id)`` only updates ``last_file_id`` / ``file_count`` /
``updated_at`` (run header is immutable per id).

Usage::

    uv run python scripts/backfill_sweeps.py [--db PATH] [--limit N]
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("backfill_sweeps")


def _iter_candidates(con, limit: int | None, include_unflagged: bool):
    """Yield candidate (id, path, has_sweep) rows.

    By default we only walk ``has_sweep=1`` since the flag was supposed to
    be set at save time. With ``--include-unflagged`` we also walk rows
    where the flag is 0 — useful when the project was upgraded from a
    pre-v4.181 release without ever running ``backfill_has_sweep.py``.
    For those rows, finding sweep XMP also flips ``has_sweep`` to 1.
    """
    if include_unflagged:
        # Cheap pre-filter: skip archive members and non-image extensions
        # so we don't even attempt XMP reads on .zip / .mp4 / etc.
        sql = (
            "SELECT id, path, has_sweep FROM files "
            "WHERE is_deleted=0 "
            "  AND path NOT LIKE '%!%' "
            "  AND (path LIKE '%.png' OR path LIKE '%.jpg' "
            "       OR path LIKE '%.jpeg' OR path LIKE '%.webp') "
            "ORDER BY id"
        )
    else:
        sql = (
            "SELECT id, path, has_sweep FROM files "
            "WHERE is_deleted=0 AND has_sweep=1 ORDER BY id"
        )
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="Path to tags.db (defaults to configured DB)")
    ap.add_argument("--limit", type=int, default=None, help="Max files to scan")
    ap.add_argument(
        "--include-unflagged", action="store_true",
        help="Also scan files with has_sweep=0; flips the flag whenever "
             "sweep XMP is found. Use after upgrading from a release that "
             "did not yet set has_sweep at save time.",
    )
    args = ap.parse_args()

    project_root = Path(__file__).resolve().parent.parent
    db_path = (Path(args.db).resolve() if args.db
               else (project_root / "tags.db").resolve())
    if not db_path.exists():
        logger.error("DB not found: %s. Pass --db <path>.", db_path)
        return 1

    from core.services_core.app_runtime_state import init_app_state
    init_app_state(db_path, {})

    try:
        from core.services_core.db_state import get_raw_db
        con = get_raw_db()
    except Exception as exc:
        logger.error("Could not open DB: %s", exc)
        return 1

    try:
        from core.schema_core.schema_migrate import migrate_db
        migrate_db(con)
    except Exception as exc:
        logger.error("Schema migration failed: %s", exc)
        return 1

    from core.bridge_core.sweep_db import attrs_to_meta, upsert_sweep_sync
    from core.tools.xmp import read_namespaces

    scanned = 0
    upserted = 0
    missing = 0
    errors = 0
    skipped = 0
    flagged = 0  # files where we flipped has_sweep 0 -> 1
    t0 = time.perf_counter()

    for fid, path, hs in _iter_candidates(con, args.limit, args.include_unflagged):
        scanned += 1
        p = Path(path)
        if not p.exists():
            missing += 1
            continue
        try:
            xmp = read_namespaces(str(p))
        except Exception as exc:
            errors += 1
            logger.debug("xmp read failed for %s: %s", path, exc)
            continue
        attrs = xmp.get_attrs("sweep")
        meta = attrs_to_meta(attrs)
        if meta is None:
            skipped += 1
            continue
        try:
            ok = upsert_sweep_sync(con, meta, int(fid))
            if ok:
                upserted += 1
                # Promote files.has_sweep to 1 if it was missed at save time.
                if not hs:
                    con.execute(
                        "UPDATE files SET has_sweep=1 WHERE id=?", (int(fid),),
                    )
                    flagged += 1
        except Exception as exc:
            errors += 1
            logger.debug("upsert failed for %s: %s", path, exc)
            continue

        if scanned % 500 == 0:
            con.commit()
            logger.info(
                "  ... scanned=%d upserted=%d flagged=%d missing=%d "
                "skipped=%d errors=%d",
                scanned, upserted, flagged, missing, skipped, errors,
            )

    con.commit()
    elapsed = time.perf_counter() - t0
    logger.info(
        "Done. scanned=%d upserted=%d flagged=%d missing=%d "
        "skipped=%d errors=%d (%.1fs)",
        scanned, upserted, flagged, missing, skipped, errors, elapsed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
