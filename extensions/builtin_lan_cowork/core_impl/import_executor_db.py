"""DB helpers for ImportExecutor."""

from __future__ import annotations

import base64
import sqlite3
import time
from pathlib import Path


def get_write_con() -> sqlite3.Connection:
    from core.services_core.lan_cowork_import_service import get_import_write_db

    return get_import_write_db()


def provider_supports_cross_thread_execution(provider) -> bool:
    module = getattr(provider, "__module__", "") or ""
    name = getattr(provider, "__name__", "") or ""
    return (
        (module == "core.services_core.db_state" and name == "get_db")
        or (module == "core.services_core.lan_cowork_import_service" and name == "get_import_write_db")
    )


def insert_file(con: sqlite3.Connection, path: str, peer_id: str, file_meta: dict) -> int:
    now = int(time.time())
    con.execute(
        """INSERT OR IGNORE INTO files
           (path, hash, phash, mtime, size, width, height, meta_source,
            imported_from_peer, is_deleted, not_modified, parser_version)
           VALUES (?,?,?,?,?,?,?,?,?,0,0,1)""",
        (
            path,
            file_meta.get("hash"),
            file_meta.get("phash"),
            file_meta.get("mtime", now),
            file_meta.get("size", 0),
            file_meta.get("width"),
            file_meta.get("height"),
            file_meta.get("meta_source"),
            peer_id,
        ),
    )
    row = con.execute("SELECT id FROM files WHERE path=?", (path,)).fetchone()
    return row[0]


def write_metadata(
    session_id: str,
    peer_id: str,
    remote_id: int,
    local_id: int,
    tags: dict,
    ratings: dict,
    annotations: dict,
    collections: list,
    con: sqlite3.Connection,
    resolve_collection_id,
    merge_metadata: bool = False,
) -> None:
    rid_str = str(remote_id)
    now = int(time.time())

    for tag in tags.get(rid_str, []):
        if not tag:
            continue
        row = con.execute(
            "SELECT id FROM tags WHERE tag=? AND namespace IS NULL",
            (tag,),
        ).fetchone()
        if row is None:
            cur = con.execute(
                "INSERT INTO tags (tag, first_seen_mtime) VALUES (?, ?)",
                (tag, now),
            )
            tag_id = cur.lastrowid
        else:
            tag_id = row[0]
        con.execute(
            "INSERT OR IGNORE INTO file_tags (file_id, tag_id, weight, source) VALUES (?,?,?,?)",
            (local_id, tag_id, 1.0, "meta"),
        )

    if rid_str in ratings:
        # file_ratings is keyed on file_id alone, so a plain DO UPDATE replaces
        # whatever the local user had rated this file. That only happens on a
        # path collision (re-import, or the scanner indexed the file first) --
        # a hash match never reaches here -- but on that path the local rating
        # was silently lost. specs/2026-04-19-remote-import-design.md:212-213:
        # local wins by default; merge_metadata takes the higher of the two.
        #
        # file_annotations needs no such split: its conflict key includes
        # `source`, so a remote row can only ever replace a previous remote row.
        if merge_metadata:
            con.execute(
                """INSERT INTO file_ratings
                   (file_id, rating, rated_at, updated_at) VALUES (?,?,?,?)
                   ON CONFLICT(file_id) DO UPDATE SET
                     rating=MAX(file_ratings.rating, excluded.rating),
                     rated_at=excluded.rated_at,
                     updated_at=excluded.updated_at""",
                (local_id, ratings[rid_str], now, now),
            )
        else:
            con.execute(
                """INSERT INTO file_ratings
                   (file_id, rating, rated_at, updated_at) VALUES (?,?,?,?)
                   ON CONFLICT(file_id) DO NOTHING""",
                (local_id, ratings[rid_str], now, now),
            )

    ann_rows = annotations.get(rid_str)
    if ann_rows:
        if isinstance(ann_rows, str):
            ann_rows = [{"source": "remote", "key": "note", "value": ann_rows}]
        for ann in ann_rows:
            value = ann.get("value", "")
            if ann.get("value_enc") == "base64" and isinstance(value, str):
                value_blob = base64.b64decode(value.encode("ascii"))
            elif isinstance(value, str):
                value_blob = value.encode("utf-8")
            else:
                value_blob = value
            con.execute(
                """INSERT INTO file_annotations
                   (file_id, source, key, value, confidence, created_at)
                   VALUES (?,?,?,?,?,?)
                   ON CONFLICT(file_id, source, key) DO UPDATE SET
                     value=excluded.value,
                     confidence=excluded.confidence,
                     created_at=excluded.created_at""",
                (
                    local_id,
                    ann.get("source", "remote"),
                    ann.get("key", "note"),
                    value_blob,
                    ann.get("confidence"),
                    ann.get("created_at") or now,
                ),
            )

    now = int(time.time())
    for coll in collections:
        coll_id = resolve_collection_id(session_id, peer_id, coll["id"], coll["name"])
        if coll_id == 1:
            continue
        con.execute(
            "INSERT OR IGNORE INTO favorites (file_id, collection_id, added_at) VALUES (?,?,?)",
            (local_id, coll_id, now),
        )


def persist_downloaded_file(
    session_id: str,
    peer_id: str,
    remote_id: int,
    dest: Path,
    file_meta: dict,
    tags: dict,
    ratings: dict,
    annotations: dict,
    collections: list,
) -> None:
    from .import_session import ImportSession

    con = get_write_con()
    local_id = insert_file(con, str(dest), peer_id, file_meta)
    ImportSession._register_file_write(
        con,
        session_id=session_id,
        remote_peer_id=peer_id,
        remote_id=remote_id,
        local_id=local_id,
        status="done",
    )

    def _resolve_collection_id(current_session_id: str, current_peer_id: str, remote_collection_id: int, collection_name: str) -> int:
        return ImportSession._get_or_create_collection_write(
            con,
            session_id=current_session_id,
            remote_peer_id=current_peer_id,
            remote_collection_id=remote_collection_id,
            collection_name=collection_name,
        )

    write_metadata(
        session_id,
        peer_id,
        remote_id,
        local_id,
        tags,
        ratings,
        annotations,
        collections,
        con,
        _resolve_collection_id,
    )
    con.commit()
