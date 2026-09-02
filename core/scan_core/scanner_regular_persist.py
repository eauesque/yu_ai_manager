"""DB persistence phase for regular-file scanner."""

import sqlite3
import time
from pathlib import Path
from typing import Any

from core.models_core.models_tags import insert_file_tags_batch, upsert_tag
from core.models_core.models_templates import replace_template_tokens, upsert_template
from core.parsers.prompt_parse import parse_prompt_to_tags
from core.parsers.prompt_parse_candidates import effective_config

from .scanner_hooks_tags import normalize_via_hooks
from .scanner_media_state import upsert_media_extract_state

# When the persist phase alone takes longer than this, emit a per-substep
# dlog so we can isolate the slowest of parse / build-rows / replace-tags /
# template / tokens / media-state. Threshold matches scanner_regular's.
_PERSIST_SLOW_LOG_MS = 500.0


def _build_meta_rows(file_id: int, parsed_tags, *, mtime: int, con: sqlite3.Connection):
    rows_map: dict[int, tuple[int, int, float, str]] = {}
    for ns, t, w in parsed_tags:
        t = normalize_via_hooks(t)
        tag_id = upsert_tag(con, ns, t, first_seen_mtime=mtime or None)
        rows_map[int(tag_id)] = (file_id, int(tag_id), float(w), "meta")
    return list(rows_map.values())


def _replace_meta_tags_if_changed(con: sqlite3.Connection, file_id: int, rows) -> None:
    existing_rows = con.execute(
        "SELECT tag_id, weight FROM file_tags WHERE file_id=? AND source='meta'",
        (file_id,),
    )
    existing_map = {int(r[0]): float(r[1]) for r in existing_rows}
    incoming_map = {int(r[1]): float(r[2]) for r in rows}
    if existing_map == incoming_map:
        return

    if rows:
        ids = list(incoming_map.keys())
        if len(ids) <= 900:
            insert_file_tags_batch(con, rows)
            placeholders = ",".join("?" for _ in ids)
            con.execute(
                f"DELETE FROM file_tags WHERE file_id=? AND source='meta' AND tag_id NOT IN ({placeholders})",
                [file_id, *ids],
            )
        else:
            # Rare large prompts: keep semantics simple and safe.
            con.execute("DELETE FROM file_tags WHERE file_id=? AND source='meta'", (file_id,))
            insert_file_tags_batch(con, rows)
    else:
        con.execute("DELETE FROM file_tags WHERE file_id=? AND source='meta'", (file_id,))


def persist_regular_scan_result(
    con: sqlite3.Connection,
    p: Path,
    file_id: int,
    config: dict[str, Any],
    meta_source: str,
    fmt: str,
    raw_prompt: str | None,
    raw_negative: str | None,
    raw_meta_json: str | None,
    tag_source: str | None,
    *,
    mtime: int = 0,
) -> None:
    _t_total = time.perf_counter()
    _steps: dict[str, float] = {}

    def _mark(name: str, t0: float) -> None:
        _steps[name] = round((time.perf_counter() - t0) * 1000, 1)

    if meta_source == "unknown":
        fname = p.name if hasattr(p, "name") else str(p).rsplit("/", 1)[-1].rsplit("\\", 1)[-1]
        if fname.startswith("TA-") or "tensor" in fname.lower():
            meta_source = "tensor_art"
            con.execute("UPDATE files SET meta_source=? WHERE id=?", (meta_source, file_id))

    tag_extraction_source = tag_source if tag_source else raw_prompt
    n_tags = 0
    if tag_extraction_source:
        _t = time.perf_counter()
        parsed = parse_prompt_to_tags(tag_extraction_source, effective_config(config, meta_source))
        _mark("parse_prompt", _t)
        n_tags = len(parsed.tags)
        _t = time.perf_counter()
        file_tag_rows = _build_meta_rows(file_id, parsed.tags, mtime=mtime, con=con)
        _mark("build_meta_rows", _t)
        _t = time.perf_counter()
        _replace_meta_tags_if_changed(con, file_id, file_tag_rows)
        _mark("replace_meta_tags", _t)
        _t = time.perf_counter()
        template_id = upsert_template(con, file_id, raw_prompt, raw_negative, fmt, raw_meta_json)
        _mark("upsert_template", _t)
        _t = time.perf_counter()
        replace_template_tokens(con, template_id, parsed.template_tokens)
        _mark("replace_tokens", _t)
    elif raw_meta_json is not None:
        _t = time.perf_counter()
        _replace_meta_tags_if_changed(con, file_id, [])
        _mark("replace_meta_tags", _t)
        _t = time.perf_counter()
        template_id = upsert_template(con, file_id, None, raw_negative, fmt, raw_meta_json)
        _mark("upsert_template", _t)
        _t = time.perf_counter()
        replace_template_tokens(con, template_id, [])
        _mark("replace_tokens", _t)
    else:
        _t = time.perf_counter()
        _replace_meta_tags_if_changed(con, file_id, [])
        _mark("replace_meta_tags", _t)

    _t = time.perf_counter()
    upsert_media_extract_state(con, file_id, meta_source, raw_meta_json)
    _mark("media_state", _t)

    total_ms = round((time.perf_counter() - _t_total) * 1000, 1)
    if total_ms >= _PERSIST_SLOW_LOG_MS:
        from core.infra_core.debug_log import dlog
        dlog(
            "scan",
            "persist_regular.slow",
            file_id=file_id,
            meta_source=meta_source,
            n_tags=n_tags,
            total_ms=total_ms,
            **{f"{k}_ms": v for k, v in _steps.items()},
        )
