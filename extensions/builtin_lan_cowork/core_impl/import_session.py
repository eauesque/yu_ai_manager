"""Persistent session management for remote import."""
from __future__ import annotations

import json
import sqlite3
import time
import uuid
from typing import Any

from core.services_core.db_write import submit_db_write


def _submit_write_with_fallback(fn) -> None:
    try:
        submit_db_write(fn)
    except sqlite3.ProgrammingError as exc:
        if "same thread" not in str(exc).lower():
            raise
        fn()


def _provider_supports_cross_thread_execution(provider) -> bool:
    module = getattr(provider, "__module__", "") or ""
    name = getattr(provider, "__name__", "") or ""
    return (
        (module == "core.services_core.db_state" and name in {"get_db", "get_readonly_db"})
        or (
            module == "core.services_core.lan_cowork_import_service"
            and name in {"get_import_write_db", "get_import_read_db"}
        )
    )


class ImportSession:
    """Class-level methods for import session CRUD (no instance state)."""

    _SESSION_SELECT_COLUMNS = (
        "id, peer_id, peer_name, mode, status, last_seen_rowid, snapshot_max_rowid, "
        "total_files, done_files, import_folder, options, created_at, updated_at"
    )
    _DOWNLOAD_BUDGET_KEY = "$._lan_import_download_remaining"

    @staticmethod
    def _get_write_con() -> sqlite3.Connection:
        from core.services_core.lan_cowork_import_service import get_import_write_db

        return get_import_write_db()

    @staticmethod
    def _get_con() -> sqlite3.Connection:
        return ImportSession._get_write_con()

    @staticmethod
    def _get_read_con() -> sqlite3.Connection:
        from core.services_core.lan_cowork_import_service import get_import_read_db

        return get_import_read_db()

    @classmethod
    def threadsafe_provider(cls) -> bool:
        return (
            _provider_supports_cross_thread_execution(cls._get_write_con)
            and _provider_supports_cross_thread_execution(cls._get_read_con)
        )

    @classmethod
    def create(
        cls,
        peer_id: str,
        peer_name: str,
        mode: str,
        import_folder: str,
        options: dict[str, Any],
    ) -> str:
        sid = str(uuid.uuid4())
        now = int(time.time())
        opts = {"include_favorites": False, "merge_metadata": False, **options}

        def _write() -> None:
            con = cls._get_write_con()
            con.execute(
                """INSERT INTO import_session
                   (id,peer_id,peer_name,mode,status,last_seen_rowid,snapshot_max_rowid,
                    total_files,done_files,import_folder,options,created_at,updated_at)
                   VALUES (?,?,?,?,'pending',NULL,NULL,NULL,0,?,?,?,?)""",
                (sid, peer_id, peer_name, mode, import_folder, json.dumps(opts), now, now),
            )
            con.commit()

        _submit_write_with_fallback(_write)
        return sid

    @classmethod
    def get(cls, session_id: str) -> dict[str, Any] | None:
        con = cls._get_read_con()
        row = con.execute(
            f"SELECT {cls._SESSION_SELECT_COLUMNS} FROM import_session WHERE id=?",
            (session_id,),
        ).fetchone()
        if row is None:
            return None
        d = dict(row)
        d["options"] = json.loads(d["options"] or "{}")
        return d

    @classmethod
    def update(cls, session_id: str, **fields) -> None:
        allowed = {
            "status", "last_seen_rowid", "snapshot_max_rowid",
            "total_files", "done_files",
        }
        updates = {k: v for k, v in fields.items() if k in allowed}
        if not updates:
            return
        current = cls.get(session_id)
        if current is None:
            return
        updates = {k: v for k, v in updates.items() if current.get(k) != v}
        if not updates:
            return
        updates["updated_at"] = int(time.time())
        set_clause = ", ".join(f"{k}=?" for k in updates)

        def _write() -> None:
            con = cls._get_write_con()
            con.execute(
                f"UPDATE import_session SET {set_clause} WHERE id=?",
                (*updates.values(), session_id),
            )
            con.commit()

        _submit_write_with_fallback(_write)

    @classmethod
    def claim_execution(cls, session_id: str, download_limit: int) -> bool:
        claimed = False

        def _write() -> None:
            nonlocal claimed
            con = cls._get_write_con()
            cur = con.execute(
                """UPDATE import_session
                   SET status='running',
                       options=json_set(COALESCE(NULLIF(options,''),'{}'), ?, ?),
                       updated_at=?
                   WHERE id=? AND status='pending'""",
                (cls._DOWNLOAD_BUDGET_KEY, download_limit, int(time.time()), session_id),
            )
            claimed = cur.rowcount == 1
            con.commit()

        _submit_write_with_fallback(_write)
        return claimed

    @classmethod
    def consume_download_budget(cls, session_id: str, size: int) -> bool:
        if size < 0:
            return False
        consumed = False

        def _write() -> None:
            nonlocal consumed
            con = cls._get_write_con()
            cur = con.execute(
                """UPDATE import_session
                   SET options=json_set(options, ?, json_extract(options, ?) - ?),
                       updated_at=?
                   WHERE id=? AND status='running'
                     AND json_type(options, ?)='integer'
                     AND json_extract(options, ?) >= ?""",
                (
                    cls._DOWNLOAD_BUDGET_KEY,
                    cls._DOWNLOAD_BUDGET_KEY,
                    size,
                    int(time.time()),
                    session_id,
                    cls._DOWNLOAD_BUDGET_KEY,
                    cls._DOWNLOAD_BUDGET_KEY,
                    size,
                ),
            )
            consumed = cur.rowcount == 1
            con.commit()

        _submit_write_with_fallback(_write)
        return consumed

    @classmethod
    def register_file(
        cls,
        session_id: str,
        remote_peer_id: str,
        remote_id: int,
        local_id: int,
        status: str = "done",
    ) -> None:
        def _write() -> None:
            con = cls._get_write_con()
            cls._register_file_write(
                con,
                session_id=session_id,
                remote_peer_id=remote_peer_id,
                remote_id=remote_id,
                local_id=local_id,
                status=status,
            )
            con.commit()

        _submit_write_with_fallback(_write)

    @staticmethod
    def _register_file_write(
        con: sqlite3.Connection,
        *,
        session_id: str,
        remote_peer_id: str,
        remote_id: int,
        local_id: int,
        status: str = "done",
    ) -> bool:
        cur = con.execute(
            """INSERT INTO import_file_id_map
               (session_id,remote_peer_id,remote_file_id,local_file_id,status)
               VALUES (?,?,?,?,?)
               ON CONFLICT(session_id,remote_peer_id,remote_file_id) DO NOTHING""",
            (session_id, remote_peer_id, remote_id, local_id, status),
        )
        if cur.rowcount > 0:
            con.execute(
                "UPDATE import_session SET done_files=done_files+1, updated_at=? WHERE id=?",
                (int(time.time()), session_id),
            )
            return True
        return False

    @classmethod
    def is_file_processed(
        cls, session_id: str, remote_peer_id: str, remote_id: int
    ) -> bool:
        con = cls._get_read_con()
        row = con.execute(
            """SELECT 1 FROM import_file_id_map
               WHERE session_id=? AND remote_peer_id=? AND remote_file_id=?""",
            (session_id, remote_peer_id, remote_id),
        ).fetchone()
        return row is not None

    @classmethod
    def get_local_file_id(
        cls, session_id: str, remote_peer_id: str, remote_id: int
    ) -> int | None:
        con = cls._get_read_con()
        row = con.execute(
            """SELECT local_file_id FROM import_file_id_map
               WHERE session_id=? AND remote_peer_id=? AND remote_file_id=?""",
            (session_id, remote_peer_id, remote_id),
        ).fetchone()
        return row[0] if row else None

    @classmethod
    def get_or_create_collection(
        cls,
        session_id: str,
        remote_peer_id: str,
        remote_collection_id: int,
        collection_name: str,
    ) -> int:
        result: dict[str, int] = {}

        def _write() -> None:
            con = cls._get_write_con()
            result["local_id"] = cls._get_or_create_collection_write(
                con,
                session_id=session_id,
                remote_peer_id=remote_peer_id,
                remote_collection_id=remote_collection_id,
                collection_name=collection_name,
            )
            con.commit()

        _submit_write_with_fallback(_write)
        return result["local_id"]

    @staticmethod
    def _get_or_create_collection_write(
        con: sqlite3.Connection,
        *,
        session_id: str,
        remote_peer_id: str,
        remote_collection_id: int,
        collection_name: str,
    ) -> int:
        row = con.execute(
            """SELECT local_collection_id FROM import_collection_id_map
               WHERE session_id=? AND remote_peer_id=? AND remote_collection_id=?""",
            (session_id, remote_peer_id, remote_collection_id),
        ).fetchone()
        if row:
            return row[0]
        name_clean = collection_name.strip()
        existing = con.execute(
            "SELECT id FROM collections WHERE LOWER(TRIM(name))=LOWER(?)",
            (name_clean,),
        ).fetchall()
        if len(existing) > 1:
            import logging
            logging.getLogger(__name__).warning(
                "Multiple collections match name %r - using first", name_clean
            )
        if existing:
            local_id = existing[0][0]
        else:
            cur = con.execute(
                "INSERT INTO collections (name, sort_order, created_at) VALUES (?,0,?)",
                (name_clean, int(time.time())),
            )
            local_id = cur.lastrowid
        con.execute(
            """INSERT INTO import_collection_id_map
               (session_id,remote_peer_id,remote_collection_id,local_collection_id)
               VALUES (?,?,?,?)
               ON CONFLICT(session_id,remote_peer_id,remote_collection_id) DO NOTHING""",
            (session_id, remote_peer_id, remote_collection_id, local_id),
        )
        return local_id

    @classmethod
    def list_all(cls) -> list[dict[str, Any]]:
        con = cls._get_read_con()
        rows = con.execute(
            f"SELECT {cls._SESSION_SELECT_COLUMNS} FROM import_session ORDER BY created_at DESC"
        ).fetchall()
        result = []
        for row in rows:
            d = dict(row)
            d["options"] = json.loads(d["options"] or "{}")
            result.append(d)
        return result
