"""Search command for legacy tagdb CLI."""

import datetime as _dt
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from core.tagdb_core.db_schema.tagdb_db_schema_common import connect_db
from core.tagdb_prompt import norm_space

from .tagdb_search_config import load_or_default_config
from .tagdb_search_query import build_tag_filter_sql


def cmd_search(args, default_config: dict[str, Any]) -> None:
    config = load_or_default_config(args.config, default_config)
    con = connect_db(Path(args.db))

    where_parts: list[str] = ["f.is_deleted=0"]
    params: list[Any] = []

    if args.from_date:
        d0 = _dt.date.fromisoformat(args.from_date)
        t0 = int(_dt.datetime(d0.year, d0.month, d0.day, 0, 0, 0).timestamp())  # noqa: DTZ001 -- operator typed a local date; naive midnight is the boundary
        where_parts.append("f.mtime>=?")
        params.append(t0)

    if args.to_date:
        d1 = _dt.date.fromisoformat(args.to_date)
        t1 = int(_dt.datetime(d1.year, d1.month, d1.day, 23, 59, 59).timestamp())  # noqa: DTZ001 -- operator typed a local date; naive midnight is the boundary
        where_parts.append("f.mtime<=?")
        params.append(t1)

    tag_sql, tag_params = build_tag_filter_sql(args.q)
    where_parts.append(tag_sql)
    params.extend(tag_params)

    if args.artist:
        a = norm_space(args.artist)
        if config.get("lowercase_tags", True):
            a = a.lower()
        where_parts.append(
            "EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id "
            "WHERE ft.file_id=f.id AND t.namespace='artist' AND t.tag=?)"
        )
        params.append(a)

    join_fts = ""
    if args.in_prompt:
        if not config.get("enable_fts", True):
            raise SystemExit("FTS is disabled in config; enable_fts=true")
        join_fts = "JOIN templates_fts tf ON tf.rowid = tm.id"
        where_parts.append("tf.raw_prompt MATCH ?")
        params.append(args.in_prompt)

    sql = (
        "SELECT f.path, f.mtime, tm.raw_prompt, f.meta_source "
        "FROM files f "
        "LEFT JOIN templates tm ON tm.file_id=f.id "
        + (join_fts + " " if join_fts else "")
        + "WHERE "
        + " AND ".join(where_parts)
        + " "
        + "ORDER BY f.mtime DESC "
        + "LIMIT ?"
    )
    params.append(int(args.limit))

    rows = con.execute(sql, params).fetchall()
    for path, mtime, raw_prompt, meta_source in rows:
        # Aware-local: same rendered digits as the old naive call
        # (measured), and the operator wants local time.
        dt = (
            _dt.datetime.fromtimestamp(int(mtime), tz=_dt.UTC)
            .astimezone()
            .strftime("%Y-%m-%d %H:%M:%S")
        )
        rp = (raw_prompt or "").replace("\n", " ")
        if len(rp) > 140:
            rp = rp[:140] + "…"
        logger.info(f"[{dt}] ({meta_source}) {path}")
        if rp:
            logger.info(f"  prompt: {rp}")

    logger.info(f"hits: {len(rows)}")
