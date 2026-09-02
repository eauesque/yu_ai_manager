"""Determines which remote files to import based on local hash dedup."""
from __future__ import annotations

import sqlite3
from typing import Any

_IN_CHUNK_SIZE = 500
REMOTE_FILE_COUNT_LIMIT = 10_000


def _chunks(items: list[str], size: int | None = None):
    size = _IN_CHUNK_SIZE if size is None else size
    for start in range(0, len(items), size):
        yield items[start:start + size]


class ImportPlanner:
    """Stateless helper: given remote file list, return (to_import, to_skip)."""

    @staticmethod
    def _get_con() -> sqlite3.Connection:
        from core.services_core.db_state import get_readonly_db
        return get_readonly_db()

    @staticmethod
    def validate_remote_files(remote_files: list[dict[str, Any]]) -> None:
        if len(remote_files) > REMOTE_FILE_COUNT_LIMIT:
            raise ValueError("remote import file count exceeds session limit")

    @classmethod
    def plan(
        cls, remote_files: list[dict[str, Any]]
    ) -> tuple[list[dict], list[dict]]:
        """
        Returns:
          to_import: remote file dicts that need downloading
          to_skip:   list of {remote_id, local_id} for hash-matched files
        """
        cls.validate_remote_files(remote_files)
        if not remote_files:
            return [], []

        hashes = list(dict.fromkeys(f["hash"] for f in remote_files if f.get("hash")))
        if hashes:
            con = cls._get_con()
            existing: dict[str, int] = {}
            for chunk in _chunks(hashes):
                placeholders = ",".join("?" for _ in chunk)
                cursor = con.execute(
                    f"SELECT hash, id FROM files WHERE hash IN ({placeholders}) AND is_deleted=0",
                    chunk,
                )
                existing.update({row[0]: row[1] for row in cursor})
        else:
            existing = {}

        to_import: list[dict] = []
        to_skip: list[dict] = []
        for f in remote_files:
            h = f.get("hash")
            if h and h in existing:
                to_skip.append({"remote_id": f["id"], "local_id": existing[h]})
            else:
                to_import.append(f)
        return to_import, to_skip
