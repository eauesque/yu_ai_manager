"""ImportExecutor facade."""

from __future__ import annotations

import asyncio
from pathlib import Path
from typing import TYPE_CHECKING, Any

from .import_executor_batches import batch_zip, individual_http
from .import_executor_db import (
    get_write_con as _get_write_con,
)
from .import_executor_db import (
    insert_file,
    provider_supports_cross_thread_execution,
    write_metadata,
)

if TYPE_CHECKING:
    from .models import PeerInfo

_BATCH_THRESHOLD = 100


class ImportExecutor:
    """Stateless executor: runs a full import session."""

    @staticmethod
    def _threadsafe_db_provider() -> bool:
        return provider_supports_cross_thread_execution(_get_write_con)

    @staticmethod
    async def _call_import_session(method_name: str, *args, **kwargs):
        from .import_session import ImportSession

        method = getattr(ImportSession, method_name)
        if ImportSession.threadsafe_provider():
            return await asyncio.to_thread(method, *args, **kwargs)
        return method(*args, **kwargs)

    @staticmethod
    def _persist_downloaded_file(*args, **kwargs) -> None:
        session_id, peer_id, remote_id, dest, file_meta, tags, ratings, annotations, collections = args
        merge_metadata = bool(kwargs.get("merge_metadata", False))
        from .import_session import ImportSession

        con = _get_write_con()
        local_id = insert_file(con, str(dest), peer_id, file_meta)
        ImportSession._register_file_write(
            con,
            session_id=session_id,
            remote_peer_id=peer_id,
            remote_id=remote_id,
            local_id=local_id,
            status="done",
        )

        def _resolve_collection_id(
            current_session_id: str, current_peer_id: str, remote_collection_id: int, collection_name: str
        ) -> int:
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
            merge_metadata,
        )
        con.commit()

    @classmethod
    async def run(
        cls,
        session_id: str,
        peer: PeerInfo,
        meta: dict[str, Any],
        import_folder: Path,
        options: dict[str, bool],
        local_peer_id: str = "",
        execution_claimed: bool = False,
    ) -> None:
        from .import_planner import ImportPlanner
        from .import_transfer import _SESSION_DOWNLOAD_LIMIT

        peer_id = getattr(peer, "peer_id", None) or str(peer.name)
        remote_files: list[dict] = meta.get("files", [])
        tags: dict[str, list[str]] = meta.get("tags", {})
        collections: list[dict] = meta.get("collections", [])
        ratings: dict[str, int] = meta.get("file_ratings", {})
        annotations: dict[str, Any] = meta.get("file_annotations", {})
        max_rowid: int = meta.get("max_rowid", 0)
        ImportPlanner.validate_remote_files(remote_files)
        if not execution_claimed and not await cls._call_import_session(
            "claim_execution", session_id, _SESSION_DOWNLOAD_LIMIT
        ):
            raise RuntimeError("import session was already executed")

        async def download_budget(size: int) -> bool:
            return await cls._call_import_session("consume_download_budget", session_id, size)

        await cls._call_import_session(
            "update", session_id, total_files=len(remote_files), snapshot_max_rowid=max_rowid
        )

        to_import, to_skip = ImportPlanner.plan(remote_files)
        for skip in to_skip:
            if not await cls._call_import_session("is_file_processed", session_id, peer_id, skip["remote_id"]):
                await cls._call_import_session(
                    "register_file",
                    session_id,
                    peer_id,
                    skip["remote_id"],
                    skip["local_id"],
                    "skipped",
                )

        if len(to_import) >= _BATCH_THRESHOLD:
            await batch_zip(
                cls,
                session_id,
                peer_id,
                peer,
                to_import,
                import_folder,
                tags,
                ratings,
                annotations,
                collections,
                local_peer_id,
                download_budget,
                merge_metadata=bool(options.get("merge_metadata", False)),
            )
        else:
            await individual_http(
                cls,
                session_id,
                peer_id,
                peer,
                to_import,
                import_folder,
                tags,
                ratings,
                annotations,
                collections,
                local_peer_id,
                download_budget,
                merge_metadata=bool(options.get("merge_metadata", False)),
            )

        unprocessed = len(to_import)
        for file_meta in to_import:
            remote_id = file_meta.get("id") if isinstance(file_meta, dict) else None
            if (
                isinstance(remote_id, int)
                and not isinstance(remote_id, bool)
                and await cls._call_import_session("is_file_processed", session_id, peer_id, remote_id)
            ):
                unprocessed -= 1

        completion: dict[str, Any] = {"status": "completed"}
        if unprocessed == 0:
            completion["last_seen_rowid"] = max_rowid
        await cls._call_import_session("update", session_id, **completion)
