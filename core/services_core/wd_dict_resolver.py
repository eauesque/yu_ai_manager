"""Resolve WD tag/model/category names to dictionary INT ids."""

from __future__ import annotations

import threading
from typing import Any

from core.tagging.tag_normalize import normalize_tag

_MODEL_CACHE: dict[str, int] = {}
_CAT_CACHE: dict[str, int] = {}
_LOCK = threading.Lock()
_VAR_CHUNK = 500

# Write-side and read-side resolvers intentionally share these caches. The
# dictionary tables are append-only: existing ids must not change, so a
# write-side insert can safely populate the same cache read-only lookups use
# without reset_caches(). Adding deletion, id rewrites, or None/negative cache
# entries would break this invariant and must add explicit invalidation.


def reset_caches() -> None:
    with _LOCK:
        _MODEL_CACHE.clear()
        _CAT_CACHE.clear()


def _resolve_simple(
    con: Any, table: str, col: str, value: str, cache: dict[str, int]
) -> int:
    with _LOCK:
        hit = cache.get(value)
    if hit is not None:
        return hit
    # Safe under single-writer executor: INSERT OR IGNORE + SELECT id is logically atomic. Revisit if concurrent writers on separate connections are introduced.
    con.execute(f"INSERT OR IGNORE INTO {table}({col}) VALUES(?)", (value,))
    rid = con.execute(f"SELECT id FROM {table} WHERE {col}=?", (value,)).fetchone()[0]
    with _LOCK:
        cache[value] = rid
    return rid


def resolve_model_id(con: Any, model: str) -> int:
    return _resolve_simple(con, "wd_model_dict", "model", model, _MODEL_CACHE)


def resolve_category_id(con: Any, category: str) -> int:
    return _resolve_simple(con, "wd_category_dict", "category", category, _CAT_CACHE)


def _readonly(
    con: Any, table: str, col: str, value: str, cache: dict[str, int]
) -> int | None:
    with _LOCK:
        hit = cache.get(value)
    if hit is not None:
        return hit
    row = con.execute(f"SELECT id FROM {table} WHERE {col}=?", (value,)).fetchone()
    if row is None:
        return None
    with _LOCK:
        cache[value] = row[0]
    return row[0]


def resolve_model_id_readonly(con: Any, model: str) -> int | None:
    return _readonly(con, "wd_model_dict", "model", model, _MODEL_CACHE)


def resolve_category_id_readonly(con: Any, category: str) -> int | None:
    return _readonly(con, "wd_category_dict", "category", category, _CAT_CACHE)


def resolve_tag_ids(con: Any, tags: list[str]) -> dict[str, int]:
    """Write-side resolver; normalized values are current normalize_tag output."""
    uniq = list(dict.fromkeys(tags))
    for i in range(0, len(uniq), _VAR_CHUNK):
        chunk = uniq[i : i + _VAR_CHUNK]
        con.executemany(
            "INSERT OR IGNORE INTO wd_tag_dict(tag_name, tag_name_normalized) "
            "VALUES(?,?)",
            [(tag, normalize_tag(tag)) for tag in chunk],
        )

    out: dict[str, int] = {}
    for i in range(0, len(uniq), _VAR_CHUNK):
        chunk = uniq[i : i + _VAR_CHUNK]
        ph = ",".join("?" * len(chunk))
        for tid, name in con.execute(
            f"SELECT id, tag_name FROM wd_tag_dict WHERE tag_name IN ({ph})",
            chunk,
        ):
            out[name] = tid
    return out


def resolve_tag_ids_readonly(con: Any, search_variants: list[str]) -> list[int]:
    """Read-side resolver for normalize_tag_for_search() variants."""
    ids: list[int] = []
    uniq = list(dict.fromkeys(search_variants))
    for i in range(0, len(uniq), _VAR_CHUNK):
        chunk = uniq[i : i + _VAR_CHUNK]
        ph = ",".join("?" * len(chunk))
        ids.extend(
            row[0]
            for row in con.execute(
                "SELECT id FROM wd_tag_dict "
                f"WHERE tag_name_normalized IN ({ph})",
                chunk,
            )
        )
    return ids
