"""Mirror Bridge sweep run metadata into the ``sweeps`` / ``sweep_axes`` tables.

Created in migration 68. The tables let the /sweep page render history with
SQL-driven filters (sampler / checkpoint / resolution / steps / etc.) instead
of the per-browser localStorage cache it used before.

Population paths:

* Live: :func:`upsert_sweep_from_meta` is called from
  :mod:`core.bridge_core.bridge_save_batch` whenever a save batch carries
  one or more ``sweep_meta`` items. The first call inserts the run header
  + axes; later calls just bump ``last_file_id`` and ``file_count``.
* Backfill: :mod:`scripts.backfill_sweeps` walks ``has_sweep=1`` files and
  reconstructs rows from XMP attrs.

Both paths route through ``submit_db_write_no_wait`` so they ride the
shared writer thread and never block the request handler.
"""

from __future__ import annotations

import contextlib
import json
import logging
import time
from typing import Any

from core.bridge_core.sweep_xmp import validate_sweep_meta


def attrs_to_meta(attrs: dict) -> dict | None:
    """Reconstruct a sweep_meta dict from flattened ``sweep:*`` XMP attrs.

    Mirror of :func:`core.bridge_core.sweep_xmp.sweep_meta_to_attrs`.
    Returns None if required fields are missing or unparseable. Used by
    both the background backfill task and the one-shot CLI script.
    """
    sid = attrs.get("id")
    bridge = attrs.get("bridge")
    if not sid or not bridge:
        return None
    try:
        axis_count = int(attrs.get("axis_count") or 0)
    except (TypeError, ValueError):
        axis_count = 0
    if axis_count <= 0 or axis_count > 3:
        return None

    axes: list[dict] = []
    for i in range(axis_count):
        prefix = f"axis_{i}_"
        param = attrs.get(prefix + "param")
        if not param:
            return None
        try:
            total = int(attrs.get(prefix + "total") or 0)
            index = int(attrs.get(prefix + "index") or 0)
        except (TypeError, ValueError):
            return None
        series_raw = attrs.get(prefix + "series") or ""
        if param == "_macros":
            try:
                series = json.loads(series_raw)
            except Exception:  # noqa: BLE001
                series = []
        else:
            series = [s for s in series_raw.split(",") if s] if series_raw else []
        axes.append({
            "param": param, "total": total, "index": index,
            "series": series, "value": None,
        })

    try:
        base_seed = int(attrs.get("base_seed") or -1)
    except (TypeError, ValueError):
        base_seed = -1
    try:
        created_at = int(attrs.get("created_at") or 0)
    except (TypeError, ValueError):
        created_at = 0

    out: dict = {
        "id": sid, "bridge": bridge, "axes": axes,
        "base_seed": base_seed, "created_at": created_at,
    }
    for key in ("prompt_template", "negative_template",
                "checkpoint", "vae", "sampler"):
        v = attrs.get(key)
        if isinstance(v, str) and v:
            out[key] = v
    for key in ("width", "height", "steps"):
        try:
            iv = int(attrs.get(key) or 0)
        except (TypeError, ValueError):
            iv = 0
        if iv > 0:
            out[key] = iv
    cfg_raw = attrs.get("cfg")
    if cfg_raw is not None:
        with contextlib.suppress(TypeError, ValueError):
            out["cfg"] = float(cfg_raw)
    return out

logger = logging.getLogger(__name__)


def _upsert_sweep_row(con, meta: dict, file_id: int | None) -> None:
    """Run on the writer thread. ``meta`` is already validated."""
    now = int(time.time())
    sweep_id = meta["id"]
    axes = meta.get("axes") or []
    axis_count = len(axes)
    cols = [
        "id", "bridge", "base_seed", "created_at",
        "prompt_template", "negative_template",
        "checkpoint", "vae", "sampler",
        "width", "height", "steps", "cfg",
        "axis_count", "first_file_id", "last_file_id",
        "file_count", "status", "updated_at",
    ]
    vals = [
        sweep_id,
        meta["bridge"],
        meta.get("base_seed"),
        int(meta.get("created_at") or now),
        meta.get("prompt_template"),
        meta.get("negative_template"),
        meta.get("checkpoint"),
        meta.get("vae"),
        meta.get("sampler"),
        meta.get("width"),
        meta.get("height"),
        meta.get("steps"),
        meta.get("cfg"),
        axis_count,
        file_id,
        file_id,
        1 if file_id is not None else 0,
        "completed",
        now,
    ]
    placeholders = ",".join("?" for _ in cols)
    # Insert if new; on conflict, only bump trailing counters / last_file_id.
    # Run-header fields (bridge, axes, prompts, etc.) are immutable for a
    # given sweep id — first writer wins.
    con.execute(
        f"INSERT INTO sweeps ({','.join(cols)}) VALUES ({placeholders}) "
        "ON CONFLICT(id) DO UPDATE SET "
        "  last_file_id = COALESCE(excluded.last_file_id, sweeps.last_file_id), "
        "  first_file_id = COALESCE(sweeps.first_file_id, excluded.first_file_id), "
        "  file_count = sweeps.file_count + CASE WHEN excluded.file_count > 0 THEN 1 ELSE 0 END, "
        "  updated_at = excluded.updated_at",
        vals,
    )
    # Axes (only on first insert — INSERT OR IGNORE).
    for i, ax in enumerate(axes):
        try:
            total = int(ax.get("total") or 0)
        except (TypeError, ValueError):
            total = 0
        param = ax.get("param") or ""
        if not param:
            continue
        con.execute(
            "INSERT OR IGNORE INTO sweep_axes (sweep_id, axis_index, param, total) "
            "VALUES (?, ?, ?, ?)",
            (sweep_id, i, param, total),
        )


def upsert_sweep_from_meta(meta: Any, file_id: int | None) -> None:
    """Validate ``meta`` and UPSERT into sweeps / sweep_axes synchronously.

    Best-effort: silently no-op on validation failure or DB errors so the
    save path itself never breaks. Uses the blocking writer submit so that
    the row is committed before the caller returns its HTTP response — the
    client polls ``/api/sweeps/history`` immediately after save_batch /
    generate completes, and a fire-and-forget queue races that read.
    """
    norm = validate_sweep_meta(meta)
    if norm is None:
        return
    try:
        from core.services_core.db_write import submit_db_write
    except Exception as exc:  # noqa: BLE001
        logger.debug("upsert_sweep_from_meta: writer unavailable: %s", exc)
        return

    def _runner(_norm=norm, _fid=file_id) -> None:
        from core.services_core.db_state import get_raw_db
        try:
            con = get_raw_db()
        except Exception as exc:  # noqa: BLE001
            logger.debug("upsert_sweep_from_meta: get_raw_db failed: %s", exc)
            return
        try:
            _upsert_sweep_row(con, _norm, _fid)
            con.commit()
        except Exception as exc:  # noqa: BLE001
            logger.warning("upsert_sweep_from_meta: %s", exc)

    try:
        submit_db_write(_runner)
    except Exception as exc:  # noqa: BLE001
        logger.warning("upsert_sweep_from_meta: submit failed: %s", exc)


def upsert_sweep_sync(con, meta: Any, file_id: int | None) -> bool:
    """Synchronous variant for the backfill script (already on writer)."""
    norm = validate_sweep_meta(meta)
    if norm is None:
        return False
    try:
        _upsert_sweep_row(con, norm, file_id)
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning("upsert_sweep_sync: %s", exc)
        return False


__all__ = ["attrs_to_meta", "upsert_sweep_from_meta", "upsert_sweep_sync"]
