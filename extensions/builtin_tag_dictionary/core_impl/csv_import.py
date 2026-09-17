"""CSV import for a1111-sd-webui-tagcomplete format."""

from __future__ import annotations

import csv
import io
import logging
import os
import time

from core.services_core.db_api import get_db
from core.services_core.db_write import submit_db_write

logger = logging.getLogger(__name__)

_BATCH_SIZE = 1000


def import_csv(csv_path_or_stream, on_progress=None) -> dict:
    """Import a CSV file.

    CSV format: tag_name,category,post_count,aliases
    Batch processing with ON CONFLICT upsert.
    Returns: {"imported": int, "skipped": int, "total_time": float}
    """
    t0 = time.monotonic()

    closer = None
    if isinstance(csv_path_or_stream, bytes):
        stream = io.StringIO(csv_path_or_stream.decode("utf-8", errors="replace"))
    elif isinstance(csv_path_or_stream, str):
        if os.path.exists(csv_path_or_stream):
            stream = open(csv_path_or_stream, encoding="utf-8", errors="replace", newline="")  # noqa: SIM115 — intentional: file lives beyond context
            closer = stream
        else:
            stream = io.StringIO(csv_path_or_stream)
    elif hasattr(csv_path_or_stream, "read"):
        sample = csv_path_or_stream.read(0)
        if isinstance(sample, bytes):
            stream = io.TextIOWrapper(
                csv_path_or_stream,
                encoding="utf-8",
                errors="replace",
                newline="",
            )
            closer = stream
        else:
            stream = csv_path_or_stream
    else:
        stream = csv_path_or_stream

    reader = csv.reader(stream)
    imported = 0
    skipped = 0
    batch: list[tuple] = []

    try:
        for i, row in enumerate(reader):
            # Header detection: skip lines starting with "tag_name"
            if i == 0 and row and row[0].strip().lower() in ("tag_name", "name", "tag"):
                continue

            if len(row) < 1:
                skipped += 1
                continue

            tag_name = row[0].strip()
            if not tag_name:
                skipped += 1
                continue

            # category (default 0)
            try:
                category = int(row[1]) if len(row) > 1 and row[1].strip() else 0
            except ValueError:
                skipped += 1
                continue

            # post_count (default 0)
            try:
                post_count = int(row[2]) if len(row) > 2 and row[2].strip() else 0
            except ValueError:
                post_count = 0

            # aliases (default "")
            aliases = row[3].strip() if len(row) > 3 else ""

            batch.append((tag_name, category, post_count, aliases))

            if len(batch) >= _BATCH_SIZE:
                imported += _flush_batch(batch)
                batch.clear()
                if on_progress:
                    on_progress(imported + skipped)

        if batch:
            imported += _flush_batch(batch)
    finally:
        if closer is not None:
            closer.close()

    elapsed = time.monotonic() - t0
    logger.info("Tag dictionary import: %d imported, %d skipped in %.1fs", imported, skipped, elapsed)
    return {"imported": imported, "skipped": skipped, "total_time": round(elapsed, 2)}


def _flush_batch(batch: list[tuple]) -> int:
    """Write a batch to the database."""
    from core.services_core.tag_dictionary_service import import_tag_dictionary_batch

    return submit_db_write(
        lambda: import_tag_dictionary_batch(batch, get_db_fn=get_db)
    )
