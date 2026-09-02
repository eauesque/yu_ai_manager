#!/usr/bin/env python3
"""One-shot backfill for the ``files.has_sweep`` flag.

Walks every active row in ``files`` and reads the sweep namespace from each
file's XMP packet. When ``sweep:id`` is present, sets ``has_sweep=1``.
Existing flagged rows are left alone (idempotent re-runs are cheap).

Usage::

    uv run python scripts/backfill_has_sweep.py [--db PATH] [--limit N]

Exit code is 0 on success, 1 on DB unavailable. The script commits in
batches of 500 so a Ctrl-C mid-run leaves a consistent partial state.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(message)s")
logger = logging.getLogger("backfill_has_sweep")


def _iter_candidates(con, limit: int | None):
    sql = "SELECT id, path FROM files WHERE is_deleted=0 AND has_sweep=0"
    if limit:
        sql += f" LIMIT {int(limit)}"
    return con.execute(sql)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--db", help="Path to tags.db (defaults to configured DB)")
    ap.add_argument("--limit", type=int, default=None, help="Max files to scan")
    ap.add_argument("--batch", type=int, default=500, help="Commit batch size")
    args = ap.parse_args()

    # The DB is SQLCipher-encrypted; use the project's connection helper which
    # applies the cipher key. Bootstrap app runtime state with the requested
    # (or default) path so get_raw_db() resolves correctly.
    project_root = Path(__file__).resolve().parent.parent
    db_path = Path(args.db).resolve() if args.db else (project_root / "tags.db").resolve()
    if not db_path.exists():
        logger.error("DB not found: %s. Pass --db <path> to override.", db_path)
        return 1
    from core.services_core.app_runtime_state import init_app_state
    init_app_state(db_path, {})

    try:
        from core.services_core.db_state import get_raw_db
        con = get_raw_db()
    except Exception as exc:
        logger.error(
            "Could not open DB: %s. Use --db <path> to point at tags.db.", exc,
        )
        return 1

    # Apply pending schema migrations so files.has_sweep exists. Idempotent
    # if the server has already run them.
    try:
        from core.schema_core.schema_migrate import migrate_db

        migrate_db(con)
    except Exception as exc:
        logger.error("Schema migration failed: %s", exc)
        return 1

    from core.tools.xmp import read_namespaces

    flipped = 0
    scanned = 0
    missing = 0
    errors = 0
    pending: list[int] = []
    t0 = time.perf_counter()

    for fid, path in _iter_candidates(con, args.limit):
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
        sweep_attrs = xmp.get_attrs("sweep")
        if sweep_attrs.get("id"):
            pending.append(int(fid))
            if len(pending) >= args.batch:
                placeholders = ",".join("?" * len(pending))
                con.execute(
                    f"UPDATE files SET has_sweep=1 WHERE id IN ({placeholders})",
                    pending,
                )
                con.commit()
                flipped += len(pending)
                pending.clear()
                logger.info(
                    "  ... scanned=%d flipped=%d missing=%d errors=%d",
                    scanned, flipped, missing, errors,
                )

    if pending:
        placeholders = ",".join("?" * len(pending))
        con.execute(
            f"UPDATE files SET has_sweep=1 WHERE id IN ({placeholders})",
            pending,
        )
        con.commit()
        flipped += len(pending)

    elapsed = time.perf_counter() - t0
    logger.info(
        "Done. scanned=%d flipped=%d missing=%d errors=%d (%.1fs)",
        scanned, flipped, missing, errors, elapsed,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
