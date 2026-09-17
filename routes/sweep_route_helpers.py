"""Helpers for sweep routes."""

from __future__ import annotations

import json
import logging
import os
import time
from pathlib import Path
from typing import Any

from core.services_core.db_api import get_readonly_db
from core.tools.xmp import read_namespaces

logger = logging.getLogger(__name__)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
SWEEP_FOLDER_SCAN_IMAGE_LIMIT = 1000
HISTORY_LIMIT_MAX = 500
_IN_CHUNK_SIZE = 500


def _chunks(items: list[str], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


def resolve_path(file_id: int) -> str | None:
    con = get_readonly_db()
    row = con.execute("SELECT path FROM files WHERE id=?", (file_id,)).fetchone()
    if not row:
        return None
    path = row["path"]
    return None if "!" in path else path


def attrs_to_meta(attrs: dict[str, str]) -> dict[str, Any] | None:
    if not attrs or not attrs.get("id"):
        return None
    try:
        axis_count = int(attrs.get("axis_count", "1"))
    except (TypeError, ValueError):
        axis_count = 1
    axes = [_axis_attrs_to_meta(attrs, i) for i in range(axis_count)]
    axes = [axis for axis in axes if axis is not None]
    out: dict[str, Any] = {
        "id": attrs["id"],
        "bridge": attrs.get("bridge", ""),
        "axes": axes,
        "base_seed": _int_attr(attrs, "base_seed", -1),
        "created_at": _int_attr(attrs, "created_at", 0),
    }
    if isinstance(attrs.get("prompt_template"), str):
        out["prompt_template"] = attrs["prompt_template"]
    if isinstance(attrs.get("negative_template"), str):
        out["negative_template"] = attrs["negative_template"]
    return out


def read_sweep_attrs(path: str) -> dict[str, str]:
    try:
        return read_namespaces(path).get_attrs("sweep")
    except Exception as exc:  # noqa: BLE001
        logger.debug("read_namespaces failed for %s: %s", path, exc)
        return {}


def scan_folder_for_sweep(folder: str, sweep_id: str) -> list[dict[str, Any]]:
    matches: list[dict[str, Any]] = []
    try:
        entries = list(os.scandir(folder))
    except OSError as exc:
        logger.warning("scandir failed for %s: %s", folder, exc)
        return matches
    image_candidates = 0
    for entry in entries:
        if not entry.is_file() or Path(entry.name).suffix.lower() not in IMAGE_SUFFIXES:
            continue
        if image_candidates >= SWEEP_FOLDER_SCAN_IMAGE_LIMIT:
            logger.warning("sweep folder scan reached image limit (%d) for %s", SWEEP_FOLDER_SCAN_IMAGE_LIMIT, folder)
            break
        image_candidates += 1
        attrs = read_sweep_attrs(entry.path)
        if attrs.get("id") != sweep_id:
            continue
        matches.append(_sweep_record(entry.path, attrs))
    matches.sort(key=lambda m: (m.get("axis_0_index", -1), m.get("axis_1_index", -1), m.get("axis_2_index", -1), m["path"]))
    return matches


def attach_file_ids(matches: list[dict[str, Any]]) -> None:
    if not matches:
        return
    paths = [m["path"] for m in matches]
    con = get_readonly_db()
    by_path = {}
    for chunk in _chunks(list(dict.fromkeys(paths))):
        placeholders = ",".join("?" for _ in chunk)
        rows = con.execute(
            f"SELECT id, path FROM files WHERE path IN ({placeholders})",
            chunk,
        )
        by_path.update({r["path"]: r["id"] for r in rows})
    for m in matches:
        m["file_id"] = by_path.get(m["path"])


def query_sweep_history(
    *,
    limit: int,
    ref_id: str | None,
    match_keys: list[str],
    tolerances: dict[str, str],
    completed_only: bool,
    saved_only: bool,
    axis_count: str,
    date_range: str,
) -> list[dict[str, Any]]:
    con = get_readonly_db()
    where = ["1=1"]
    params: list[Any] = []
    ref_row, ref_axes = _load_history_reference(con, ref_id, match_keys)
    if ref_row is not None:
        _append_reference_filters(where, params, ref_row, ref_axes, match_keys, tolerances)
    _append_constraint_filters(where, params, completed_only, saved_only, axis_count, date_range)
    sql = (
        "SELECT s.*, (SELECT GROUP_CONCAT(a.param, ',') FROM sweep_axes a "
        "WHERE a.sweep_id = s.id ORDER BY a.axis_index) AS axes_params_csv "
        f"FROM sweeps s WHERE {' AND '.join(where)} ORDER BY s.created_at DESC, s.id LIMIT ?"
    )
    params.append(limit)
    rows = con.execute(sql, params)
    out: list[dict[str, Any]] = []
    for r in rows:
        d = dict(r)
        csv = d.pop("axes_params_csv", None)
        d["axes_params"] = csv.split(",") if csv else []
        out.append(d)
    return out


def _axis_attrs_to_meta(attrs: dict[str, str], i: int) -> dict[str, Any] | None:
    prefix = f"axis_{i}_"
    param = attrs.get(prefix + "param")
    if not param:
        return None
    series_raw = attrs.get(prefix + "series", "")
    value_raw = attrs.get(prefix + "value")
    if param == "_macros":
        series = _json_list(series_raw)
        value = _json_value(value_raw) if value_raw else value_raw
    else:
        series = [_float_or_str(part) for part in series_raw.split(",") if part != ""]
        value = value_raw
    return {
        "param": param,
        "index": _int_attr(attrs, prefix + "index", 0),
        "total": _int_attr(attrs, prefix + "total", 0),
        "value": value,
        "series": series,
    }


def _sweep_record(path: str, attrs: dict[str, str]) -> dict[str, Any]:
    record: dict[str, Any] = {"path": path}
    for axis_n in range(3):
        idx_key = f"axis_{axis_n}_index"
        val_key = f"axis_{axis_n}_value"
        if idx_key not in attrs:
            continue
        record[idx_key] = _int_attr(attrs, idx_key, -1)
        raw_val = attrs.get(val_key)
        if attrs.get(f"axis_{axis_n}_param") == "_macros" and raw_val:
            record[val_key] = _json_value(raw_val)
        else:
            record[val_key] = raw_val
    return record


def _load_history_reference(con: Any, ref_id: str | None, match_keys: list[str]) -> tuple[dict[str, Any] | None, list[str]]:
    if not ref_id or not match_keys:
        return None, []
    r = con.execute("SELECT * FROM sweeps WHERE id = ?", (ref_id,)).fetchone()
    if r is None:
        return None, []
    ax_rows = con.execute(
        "SELECT axis_index, param FROM sweep_axes WHERE sweep_id = ? ORDER BY axis_index",
        (ref_id,),
    )
    return dict(r), [a["param"] for a in ax_rows]


def _append_reference_filters(
    where: list[str],
    params: list[Any],
    ref_row: dict[str, Any],
    ref_axes: list[str],
    match_keys: list[str],
    tolerances: dict[str, str],
) -> None:
    for key in match_keys:
        if key in ("bridge", "checkpoint", "vae", "sampler"):
            _append_equal_filter(where, params, f"s.{key}", ref_row.get(key))
        elif key == "positive":
            _append_equal_filter(where, params, "s.prompt_template", ref_row.get("prompt_template"))
        elif key == "negative":
            _append_equal_filter(where, params, "s.negative_template", ref_row.get("negative_template"))
        elif key == "resolution":
            if ref_row.get("width") and ref_row.get("height"):
                where.append("s.width = ? AND s.height = ?")
                params.extend([ref_row["width"], ref_row["height"]])
        elif key == "baseSeed":
            _append_equal_filter(where, params, "s.base_seed", ref_row.get("base_seed"))
        elif key in ("steps", "cfg"):
            _append_tolerant_filter(where, params, f"s.{key}", ref_row.get(key), tolerances.get(key, "exact"))
        elif key in ("axisX", "axisY", "axisZ"):
            pos = {"axisX": 0, "axisY": 1, "axisZ": 2}[key]
            if pos < len(ref_axes):
                where.append("EXISTS (SELECT 1 FROM sweep_axes a WHERE a.sweep_id = s.id AND a.axis_index = ? AND a.param = ?)")
                params.extend([pos, ref_axes[pos]])


def _append_constraint_filters(
    where: list[str],
    params: list[Any],
    completed_only: bool,
    saved_only: bool,
    axis_count: str,
    date_range: str,
) -> None:
    if completed_only:
        where.append("s.status = 'completed'")
    if saved_only:
        where.append("s.first_file_id IS NOT NULL")
    if axis_count and axis_count != "all":
        try:
            n = int(axis_count)
            if 1 <= n <= 3:
                where.append("s.axis_count = ?")
                params.append(n)
        except ValueError:
            pass
    if date_range and date_range != "all":
        sec = {"today": 86400, "week": 7 * 86400, "month": 30 * 86400}.get(date_range)
        if sec:
            where.append("s.created_at >= ?")
            params.append(int(time.time()) - sec)


def _append_equal_filter(where: list[str], params: list[Any], column: str, value: Any) -> None:
    if value is not None and value != "":
        where.append(f"{column} = ?")
        params.append(value)


def _append_tolerant_filter(where: list[str], params: list[Any], column: str, value: Any, tol: str) -> None:
    if value is None:
        return
    try:
        pct = 0.0 if tol == "exact" else float(tol)
    except (TypeError, ValueError):
        pct = 0.0
    if pct <= 0:
        _append_equal_filter(where, params, column, value)
        return
    eps = abs(float(value)) * (pct / 100.0)
    where.append(f"{column} BETWEEN ? AND ?")
    params.extend([float(value) - eps, float(value) + eps])


def _int_attr(attrs: dict[str, str], key: str, default: int) -> int:
    try:
        return int(attrs.get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _json_list(raw: str) -> list[Any]:
    value = _json_value(raw) if raw else []
    return value if isinstance(value, list) else []


def _json_value(raw: str | None) -> Any:
    try:
        return json.loads(raw or "")
    except (ValueError, TypeError):
        return raw


def _float_or_str(raw: str) -> float | str:
    try:
        return float(raw)
    except ValueError:
        return raw
