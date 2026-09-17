"""Trophy DB operations (CRUD)."""

import contextlib
import json
import sqlite3
import time

from .trophy_definitions import ALL_TROPHY_DEFS, TROPHY_MAP


def list_trophies(con: sqlite3.Connection) -> list[dict]:
    """Return all trophies (earned + unearned silhouettes).

    Hidden trophies return title="???" when unearned.
    """
    achieved_rows = con.execute(
        "SELECT trophy_type, title, tier, category, achieved_month, achieved_at, metadata "
        "FROM trophies"
    )
    achieved_map = {r[0]: r for r in achieved_rows}

    result: list[dict] = []
    for d in ALL_TROPHY_DEFS:
        row = achieved_map.get(d.trophy_type)
        if row:
            meta = {}
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                meta = json.loads(row[6]) if row[6] else {}
            result.append({
                "type": d.trophy_type,
                "title": row[1],
                "tier": row[2],
                "category": row[3],
                "achieved": True,
                "achieved_month": row[4],
                "achieved_at": row[5],
                "metadata": meta,
            })
        else:
            result.append({
                "type": d.trophy_type,
                "title": "???" if d.hidden else d.title,
                "tier": d.tier,
                "category": d.category,
                "achieved": False,
                "achieved_month": None,
                "achieved_at": None,
                "metadata": {},
            })
    return result


def award_trophy(
    con: sqlite3.Connection,
    trophy_type: str,
    *,
    achieved_month: str | None = None,
    metadata: dict | None = None,
) -> bool:
    """Award a trophy. Returns False if already earned."""
    defn = TROPHY_MAP.get(trophy_type)
    if not defn:
        return False
    if is_achieved(con, trophy_type):
        return False
    con.execute(
        "INSERT INTO trophies(trophy_type, title, tier, category, achieved_month, achieved_at, metadata) "
        "VALUES(?,?,?,?,?,?,?)",
        (
            trophy_type,
            defn.title,
            defn.tier,
            defn.category,
            achieved_month,
            int(time.time()),
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )
    return True


def is_achieved(con: sqlite3.Connection, trophy_type: str) -> bool:
    """Check if the specified trophy has been earned."""
    row = con.execute(
        "SELECT 1 FROM trophies WHERE trophy_type=?", (trophy_type,)
    ).fetchone()
    return row is not None
