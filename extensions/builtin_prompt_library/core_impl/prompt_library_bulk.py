"""Prompt Library bulk & export/import operations."""

from __future__ import annotations

import contextlib
import json
import time
from typing import Any, TypeVar

from .prompt_library_db import get_pl_db
from .prompt_library_write import _serialize_characters

_IN_CHUNK_SIZE = 500
T = TypeVar("T")


def _chunks(items: list[T], size: int | None = None):
    chunk_size = size or _IN_CHUNK_SIZE
    for start in range(0, len(items), chunk_size):
        yield items[start:start + chunk_size]


def bulk_delete(prompt_ids: list[int]) -> int:
    """Delete multiple prompts. Returns count deleted."""
    if not prompt_ids:
        return 0
    con = get_pl_db()
    deleted = 0
    try:
        for chunk in _chunks(prompt_ids):
            ph = ",".join("?" * len(chunk))
            cur = con.execute(f"DELETE FROM prompt_library WHERE id IN ({ph})", chunk)
            deleted += cur.rowcount
        con.commit()
    except Exception:
        con.rollback()
        raise
    return deleted


def bulk_move(prompt_ids: list[int], folder_id: int) -> int:
    """Move prompts to a folder (replace existing folder assignments). Returns count.

    DELETE and INSERT are wrapped in a single transaction so a mid-operation
    failure cannot leave prompts without any folder assignment.
    """
    if not prompt_ids:
        return 0
    con = get_pl_db()
    try:
        for chunk in _chunks(prompt_ids):
            ph = ",".join("?" * len(chunk))
            con.execute(
                f"DELETE FROM prompt_library_folder_items WHERE prompt_id IN ({ph})",
                chunk,
            )
        con.executemany(
            "INSERT OR IGNORE INTO prompt_library_folder_items "
            "(prompt_id, folder_id, sort_order) VALUES (?,?,0)",
            ((pid, folder_id) for pid in prompt_ids),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return len(prompt_ids)


def bulk_tag(prompt_ids: list[int], tag_ids: list[int]) -> int:
    """Add tags to multiple prompts (additive). Returns count affected."""
    if not prompt_ids or not tag_ids:
        return 0
    con = get_pl_db()
    try:
        con.executemany(
            "INSERT OR IGNORE INTO prompt_library_tag_map "
            "(prompt_id, tag_id) VALUES (?,?)",
            ((pid, tid) for pid in prompt_ids for tid in tag_ids),
        )
        con.commit()
    except Exception:
        con.rollback()
        raise
    return len(prompt_ids)


def _load_export_tags(con, prompt_ids: list[int]) -> dict[int, list[str]]:
    tags_by_prompt: dict[int, list[str]] = {}
    for chunk in _chunks(prompt_ids):
        placeholders = ",".join("?" * len(chunk))
        cursor = con.execute(
            "SELECT tm.prompt_id, t.name FROM prompt_library_tags t "
            "JOIN prompt_library_tag_map tm ON tm.tag_id=t.id "
            f"WHERE tm.prompt_id IN ({placeholders}) "
            "ORDER BY tm.prompt_id, t.name",
            chunk,
        )
        for prompt_id, name in cursor:
            tags_by_prompt.setdefault(int(prompt_id), []).append(name)
    return tags_by_prompt


def _load_export_folders(con, prompt_ids: list[int]) -> dict[int, list[str]]:
    folders_by_prompt: dict[int, list[str]] = {}
    for chunk in _chunks(prompt_ids):
        placeholders = ",".join("?" * len(chunk))
        cursor = con.execute(
            "SELECT fi.prompt_id, f.name FROM prompt_library_folders f "
            "JOIN prompt_library_folder_items fi ON fi.folder_id=f.id "
            f"WHERE fi.prompt_id IN ({placeholders}) "
            "ORDER BY fi.prompt_id, f.name",
            chunk,
        )
        for prompt_id, name in cursor:
            folders_by_prompt.setdefault(int(prompt_id), []).append(name)
    return folders_by_prompt


def export_library(folder_id: int | None = None) -> dict[str, Any]:
    """Export library data as JSON-serializable dict."""
    con = get_pl_db()
    if folder_id is not None:
        rows = list(
            con.execute(
                "SELECT p.id, p.title, p.positive, p.negative, p.seed, p.steps, "
                "p.sampler, p.cfg_scale, p.model_name, p.memo, "
                "p.characters_json, p.created_at, p.updated_at "
                "FROM prompt_library p "
                "JOIN prompt_library_folder_items fi ON fi.prompt_id=p.id "
                "WHERE fi.folder_id=? ORDER BY p.updated_at DESC",
                (folder_id,),
            )
        )
    else:
        rows = list(
            con.execute(
                "SELECT id, title, positive, negative, seed, steps, "
                "sampler, cfg_scale, model_name, memo, "
                "characters_json, created_at, updated_at "
                "FROM prompt_library ORDER BY updated_at DESC"
            )
        )

    prompt_ids = [int(r[0]) for r in rows]
    tags_by_prompt = _load_export_tags(con, prompt_ids)
    folders_by_prompt = _load_export_folders(con, prompt_ids)
    prompts = []
    for r in rows:
        pid = r[0]
        # characters_json -> characters list
        chars = []
        raw_chars = r[10] or ""
        if raw_chars:
            with contextlib.suppress(json.JSONDecodeError, TypeError):
                chars = json.loads(raw_chars)

        entry = {
            "title": r[1], "positive": r[2], "negative": r[3],
            "seed": r[4], "steps": r[5], "sampler": r[6],
            "cfg_scale": r[7], "model_name": r[8], "memo": r[9],
            "created_at": r[11], "updated_at": r[12],
            "tags": tags_by_prompt.get(int(pid), []),
            "folders": folders_by_prompt.get(int(pid), []),
        }
        if chars:
            entry["characters"] = chars
        prompts.append(entry)

    return {
        "version": 1,
        "exported_at": int(time.time()),
        "count": len(prompts),
        "prompts": prompts,
    }


def import_library(data: dict[str, Any]) -> dict[str, int]:
    """Import prompts from exported JSON. Returns {imported, skipped}.

    The entire import is wrapped in a transaction: if any row fails, all
    previously inserted rows are rolled back so the library stays consistent.
    """
    prompts = data.get("prompts", [])
    if not prompts:
        return {"imported": 0, "skipped": 0}

    con = get_pl_db()
    imported = 0
    skipped = 0
    tag_ids_by_name: dict[str, int] = {}
    folder_ids_by_name: dict[str, int] = {}

    try:
        for p in prompts:
            title = (p.get("title") or "").strip()
            if not title:
                skipped += 1
                continue

            chars_json = _serialize_characters(p.get("characters"))

            now = int(time.time())
            cur = con.execute(
                "INSERT INTO prompt_library "
                "(title, positive, negative, seed, steps, sampler, cfg_scale, "
                " model_name, memo, source_file_id, characters_json, "
                " created_at, updated_at) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    title,
                    p.get("positive", ""), p.get("negative", ""),
                    str(p.get("seed", "")), str(p.get("steps", "")),
                    p.get("sampler", ""), str(p.get("cfg_scale", "")),
                    p.get("model_name", ""), p.get("memo", ""),
                    None, chars_json, now, now,
                ),
            )
            pid = cur.lastrowid

            # Create/assign tags
            tag_rows: list[tuple[int, int]] = []
            for tag_name in (p.get("tags") or []):
                tag_name = tag_name.strip()
                if not tag_name:
                    continue
                tid = tag_ids_by_name.get(tag_name)
                if tid is None:
                    row = con.execute(
                        "SELECT id FROM prompt_library_tags WHERE name=?", (tag_name,)
                    ).fetchone()
                    if row:
                        tid = row[0]
                    else:
                        c = con.execute(
                            "INSERT INTO prompt_library_tags (name) VALUES (?)",
                            (tag_name,),
                        )
                        tid = c.lastrowid
                    tag_ids_by_name[tag_name] = int(tid)
                tag_rows.append((pid, int(tid)))
            if tag_rows:
                con.executemany(
                    "INSERT OR IGNORE INTO prompt_library_tag_map (prompt_id, tag_id) VALUES (?,?)",
                    tag_rows,
                )

            # Create/assign folders
            folder_rows: list[tuple[int, int]] = []
            for folder_name in (p.get("folders") or []):
                folder_name = folder_name.strip()
                if not folder_name:
                    continue
                fid = folder_ids_by_name.get(folder_name)
                if fid is None:
                    row = con.execute(
                        "SELECT id FROM prompt_library_folders WHERE name=?",
                        (folder_name,),
                    ).fetchone()
                    if row:
                        fid = row[0]
                    else:
                        c = con.execute(
                            "INSERT INTO prompt_library_folders (name, parent_id, sort_order, created_at) "
                            "VALUES (?,?,0,?)",
                            (folder_name, None, now),
                        )
                        fid = c.lastrowid
                    folder_ids_by_name[folder_name] = int(fid)
                folder_rows.append((pid, int(fid)))
            if folder_rows:
                con.executemany(
                    "INSERT OR IGNORE INTO prompt_library_folder_items "
                    "(prompt_id, folder_id, sort_order) VALUES (?,?,0)",
                    ((prompt_id, folder_id) for prompt_id, folder_id in folder_rows),
                )

            imported += 1

        con.commit()
    except Exception:
        con.rollback()
        raise

    return {"imported": imported, "skipped": skipped}
