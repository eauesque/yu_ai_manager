"""Transfer paths for ImportExecutor."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# This outbound wire limit only happens to match the receiver SQL IN chunk size; change independently.
ZIP_IDS_PER_REQUEST = 500
DownloadBudget = Callable[[int], Awaitable[bool]]


async def individual_http(
    executor_cls,
    session_id,
    peer_id,
    peer,
    to_import,
    import_folder,
    tags,
    ratings,
    annotations,
    collections,
    local_peer_id: str = "",
    download_budget: DownloadBudget | None = None,
    merge_metadata: bool = False,
) -> None:
    from .import_session import ImportSession
    from .import_transfer import ImportTransfer

    for file_meta in to_import:
        remote_id = file_meta["id"]
        if not executor_cls._threadsafe_db_provider():
            already_done = ImportSession.is_file_processed(session_id, peer_id, remote_id)
        else:
            already_done = await executor_cls._call_import_session("is_file_processed", session_id, peer_id, remote_id)
        if already_done:
            continue

        dest = await ImportTransfer.download_file(
            peer=peer,
            remote_file_id=remote_id,
            dest_folder=import_folder,
            original_name=Path(file_meta["path"]).name,
            local_peer_id=local_peer_id,
            download_budget=download_budget,
        )
        if dest is None:
            logger.warning("DL failed: remote_id=%d, skipping", remote_id)
            continue
        if executor_cls._threadsafe_db_provider() and ImportSession.threadsafe_provider():
            await asyncio.to_thread(
                executor_cls._persist_downloaded_file,
                session_id,
                peer_id,
                remote_id,
                dest,
                file_meta,
                tags,
                ratings,
                annotations,
                collections,
                merge_metadata=merge_metadata,
            )
        else:
            executor_cls._persist_downloaded_file(
                session_id,
                peer_id,
                remote_id,
                dest,
                file_meta,
                tags,
                ratings,
                annotations,
                collections,
                merge_metadata=merge_metadata,
            )


async def batch_zip(
    executor_cls,
    session_id,
    peer_id,
    peer,
    to_import,
    import_folder,
    tags,
    ratings,
    annotations,
    collections,
    local_peer_id: str = "",
    download_budget: DownloadBudget | None = None,
    merge_metadata: bool = False,
) -> None:
    from .import_session import ImportSession
    from .import_transfer import ZIP_ABORT, ImportTransfer

    ids_to_dl = [
        file_meta["id"]
        for file_meta in to_import
        if not (
            await executor_cls._call_import_session("is_file_processed", session_id, peer_id, file_meta["id"])
            if executor_cls._threadsafe_db_provider() and ImportSession.threadsafe_provider()
            else ImportSession.is_file_processed(session_id, peer_id, file_meta["id"])
        )
    ]
    file_map_by_id = {file_meta["id"]: file_meta for file_meta in to_import}
    for start in range(0, len(ids_to_dl), ZIP_IDS_PER_REQUEST):
        ids = ids_to_dl[start : start + ZIP_IDS_PER_REQUEST]
        downloaded = await ImportTransfer.download_zip(
            peer,
            ids,
            import_folder,
            local_peer_id=local_peer_id,
            download_budget=download_budget,
        )
        if downloaded is ZIP_ABORT:
            # The peer refused our credentials. `download_zip` already
            # invalidated the outbound token; the remaining chunks would only
            # repeat that refusal and re-emit the same SSE.
            return
        if downloaded is None:
            await individual_http(
                executor_cls,
                session_id,
                peer_id,
                peer,
                [file_map_by_id[remote_id] for remote_id in ids],
                import_folder,
                tags,
                ratings,
                annotations,
                collections,
                local_peer_id,
                download_budget,
            )
            continue

        for remote_id, dest in downloaded.items():
            file_meta = file_map_by_id.get(remote_id)
            if file_meta is None:
                continue
            if executor_cls._threadsafe_db_provider() and ImportSession.threadsafe_provider():
                await asyncio.to_thread(
                    executor_cls._persist_downloaded_file,
                    session_id,
                    peer_id,
                    remote_id,
                    dest,
                    file_meta,
                    tags,
                    ratings,
                    annotations,
                    collections,
                    merge_metadata=merge_metadata,
                )
            else:
                executor_cls._persist_downloaded_file(
                    session_id,
                    peer_id,
                    remote_id,
                    dest,
                    file_meta,
                    tags,
                    ratings,
                    annotations,
                    collections,
                    merge_metadata=merge_metadata,
                )
