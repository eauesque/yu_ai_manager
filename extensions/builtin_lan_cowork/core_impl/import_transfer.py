"""File transfer modes: HTTP direct and ZIP batch."""

from __future__ import annotations

import logging
import shutil
import tempfile
import time
import zipfile
from collections.abc import Awaitable, Callable
from enum import Enum, auto
from pathlib import Path
from typing import TYPE_CHECKING
from urllib.parse import urlencode

if TYPE_CHECKING:
    from .models import PeerInfo

logger = logging.getLogger(__name__)

_TIMEOUT = 60
_ZIP_TIMEOUT = 300
_FILE_DOWNLOAD_LIMIT = 8 * 1024 * 1024 * 1024
_ZIP_DOWNLOAD_LIMIT = 2 * 1024 * 1024 * 1024
_ZIP_MEMBER_LIMIT = 512 * 1024 * 1024
_ZIP_ENTRY_COUNT_LIMIT = 10_000
_ZIP_EXTRACT_LIMIT = 2 * 1024 * 1024 * 1024
_ZIP_COMPRESSION_RATIO_LIMIT = 100
_SESSION_DOWNLOAD_LIMIT = 8 * 1024 * 1024 * 1024

DownloadBudget = Callable[[int], Awaitable[bool]]


class ZipOutcome(Enum):
    """A ``download_zip`` answer that is not a file map.

    ``download_zip`` had only two answers: a file map, or ``None`` meaning
    "fetch this chunk one file at a time". Every transport failure therefore
    had to be reported as an empty map, which the caller cannot tell apart
    from "the peer legitimately sent nothing" — a 414 or a 500 passed for a
    successful empty chunk. Refused credentials need a third answer, because
    retrying the remaining chunks only repeats the refusal and re-emits the
    same token-revoked SSE once per chunk.
    """

    #: The peer refused our credentials; later chunks would be refused too.
    ABORT = auto()


ZIP_ABORT = ZipOutcome.ABORT


async def _consume_budget(budget: DownloadBudget | None, size: int) -> bool:
    return budget is None or await budget(size)


def _build_url(peer: PeerInfo, path: str) -> str:
    prefix = "/ext/lan_cowork"
    if path.startswith("/api/peer/"):
        path = f"{prefix}{path}"
    return f"http://{peer.api_host}:{peer.api_port}{path}"


def _get_mgr():
    """Return the active CoworkManager, or None if unavailable."""
    try:
        from ..lan_cowork_ext import _get_manager

        return _get_manager()
    except Exception as exc:
        logger.warning("ImportTransfer: _get_manager import failed: %s", exc)
        return None


def _build_headers(
    peer: PeerInfo,
    *,
    method: str,
    full_path: str,
    query_string: str = "",
    body: bytes = b"",
    local_peer_id: str | None = None,
) -> dict[str, str]:
    mgr = _get_mgr()
    if mgr is None:
        raise RuntimeError("ImportTransfer requires manager for signed peer headers")
    peer_id = local_peer_id or getattr(getattr(mgr, "local_peer", None), "peer_id", "")
    seed = mgr.local_seed()
    from core.crypto_identity import path_requires_nonce

    from .peer_auth_client import build_peer_headers

    token = getattr(peer, "token", None)
    token_expires_at = getattr(peer, "token_expires_at", None)
    token_valid = token and (token_expires_at is None or token_expires_at > time.time())
    headers = build_peer_headers(
        seed,
        peer_id,
        token if token_valid else "",
        method,
        full_path,
        query_string,
        body,
        require_nonce=path_requires_nonce(full_path),
    )
    headers["X-Requested-With"] = "ImportTransfer"
    return headers


def _unique_dest(folder: Path, name: str) -> Path:
    dest = folder / name
    if not dest.exists():
        return dest
    stem, suffix = dest.stem, dest.suffix
    i = 1
    while True:
        candidate = folder / f"{stem}_{i}{suffix}"
        if not candidate.exists():
            return candidate
        i += 1


def _validate_zip_entry_name(name: str) -> bool:
    """Reject zip-slip vectors before joining with dest_folder.

    Rejects null bytes, absolute paths (POSIX or Windows), drive letters,
    and any '..' segment after normalising both separators.
    """
    if not name or "\x00" in name:
        return False
    normalized = name.replace("\\", "/")
    if normalized.startswith("/"):
        return False
    # Windows drive letter (e.g. C:) or UNC (//server/share)
    if len(normalized) >= 2 and normalized[1] == ":":
        return False
    if normalized.startswith("//"):
        return False
    parts = normalized.split("/")
    return ".." not in parts


def _verify_within(child: Path, parent: Path) -> bool:
    """Ensure child resolves inside parent (post-write containment check)."""
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except ValueError:
        return False


class ImportTransfer:
    """Stateless download helpers."""

    @classmethod
    async def download_file(
        cls,
        peer: PeerInfo,
        remote_file_id: int,
        dest_folder: Path,
        original_name: str,
        local_peer_id: str | None = None,
        download_budget: DownloadBudget | None = None,
    ) -> Path | None:
        """Download a single file via HTTP. Returns local path or None on failure."""
        import httpx

        full_path = f"/ext/lan_cowork/api/peer/import/file/{remote_file_id}"
        url = _build_url(peer, f"/api/peer/import/file/{remote_file_id}")
        dest: Path | None = None
        try:
            headers = _build_headers(
                peer,
                method="GET",
                full_path=full_path,
                local_peer_id=local_peer_id,
            )
        except RuntimeError as exc:
            logger.warning("DL cannot build signed headers for peer=%s: %s", peer.peer_id, exc)
            return None
        try:
            async with httpx.AsyncClient(timeout=_TIMEOUT) as client:  # noqa: SIM117
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 401:
                        logger.warning("401 Unauthorized from peer %s, token invalidated", peer.peer_id)
                        try:
                            mgr = _get_mgr()
                            if mgr is not None and hasattr(mgr, "auth_client"):
                                mgr.auth_client.invalidate_token(peer.peer_id)
                        except Exception:
                            logger.debug("Could not invalidate peer token")
                        return None
                    if resp.status_code != 200:
                        logger.warning("DL failed file_id=%d status=%d", remote_file_id, resp.status_code)
                        return None
                    if not _validate_zip_entry_name(original_name):
                        logger.warning(
                            "DL: rejected unsafe original_name from peer=%s: %r",
                            peer.peer_id,
                            original_name,
                        )
                        return None
                    dest = _unique_dest(dest_folder, original_name)
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    if not _verify_within(dest, dest_folder):
                        logger.warning("DL: dest escaped dest_folder, aborted: %s", dest)
                        return None
                    bytes_written = 0
                    with dest.open("wb") as fh:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                within_budget = await _consume_budget(download_budget, len(chunk))
                                if bytes_written + len(chunk) > _FILE_DOWNLOAD_LIMIT or not within_budget:
                                    fh.close()
                                    dest.unlink(missing_ok=True)
                                    return None
                                fh.write(chunk)
                                bytes_written += len(chunk)
                    return dest
        except Exception as exc:
            if dest is not None:
                dest.unlink(missing_ok=True)
            logger.warning("DL error file_id=%d: %s", remote_file_id, exc)
            return None

    @classmethod
    async def download_zip(
        cls,
        peer: PeerInfo,
        remote_file_ids: list[int],
        dest_folder: Path,
        local_peer_id: str | None = None,
        download_budget: DownloadBudget | None = None,
    ) -> dict[int, Path] | ZipOutcome | None:
        """Download multiple files as a ZIP.

        Returns ``{remote_id: local_path}`` on success, ``None`` to have the
        caller fetch this chunk file by file, or :data:`ZIP_ABORT` to end the
        batch.
        """
        import httpx

        query_string = urlencode({"ids": ",".join(str(i) for i in remote_file_ids)})
        full_path = "/ext/lan_cowork/api/peer/import/zip"
        url = _build_url(peer, f"/api/peer/import/zip?{query_string}")
        result: dict[int, Path] = {}
        created: list[Path] = []
        try:
            headers = _build_headers(
                peer,
                method="GET",
                full_path=full_path,
                query_string=query_string,
                local_peer_id=local_peer_id,
            )
        except RuntimeError as exc:
            logger.warning("ZIP cannot build signed headers for peer=%s: %s", peer.peer_id, exc)
            return None
        try:
            async with httpx.AsyncClient(timeout=_ZIP_TIMEOUT) as client:  # noqa: SIM117
                async with client.stream("GET", url, headers=headers) as resp:
                    if resp.status_code == 401:
                        logger.warning("401 Unauthorized from peer %s, token invalidated", peer.peer_id)
                        try:
                            mgr = _get_mgr()
                            if mgr is not None and hasattr(mgr, "auth_client"):
                                mgr.auth_client.invalidate_token(peer.peer_id)
                        except Exception:
                            logger.debug("Could not invalidate peer token")
                        return ZIP_ABORT
                    if resp.status_code != 200:
                        logger.warning("ZIP DL failed status=%d", resp.status_code)
                        return None
                    bytes_written = 0
                    with tempfile.SpooledTemporaryFile(max_size=16 * 1024 * 1024, mode="w+b") as tmp:
                        async for chunk in resp.aiter_bytes():
                            if chunk:
                                if bytes_written + len(chunk) > _ZIP_DOWNLOAD_LIMIT:
                                    logger.warning("ZIP DL exceeded size limit=%d", _ZIP_DOWNLOAD_LIMIT)
                                    return None
                                tmp.write(chunk)
                                bytes_written += len(chunk)
                        tmp.seek(0)
                        with zipfile.ZipFile(tmp) as zf:
                            infos = [info for info in zf.infolist() if not info.is_dir()]
                            if len(infos) > _ZIP_ENTRY_COUNT_LIMIT:
                                logger.warning("ZIP DL exceeded entry limit=%d", _ZIP_ENTRY_COUNT_LIMIT)
                                return None
                            expanded = sum(info.file_size for info in infos)
                            if expanded > _ZIP_EXTRACT_LIMIT or any(
                                info.file_size > _ZIP_MEMBER_LIMIT for info in infos
                            ):
                                logger.warning("ZIP DL exceeded extraction limit")
                                return None
                            if any(
                                info.file_size > 0
                                and (
                                    info.compress_size == 0
                                    or info.file_size / info.compress_size > _ZIP_COMPRESSION_RATIO_LIMIT
                                )
                                for info in infos
                            ):
                                logger.warning("ZIP DL exceeded compression ratio limit")
                                return None
                            if shutil.disk_usage(dest_folder).free < expanded:
                                logger.warning("ZIP DL lacks free space for extraction")
                                return None
                            planned: list[tuple[zipfile.ZipInfo, int, str]] = []
                            remote_ids: set[int] = set()
                            for info in infos:
                                name = info.filename
                                parts = name.split("/", 1)
                                if len(parts) != 2:
                                    raise ValueError("malformed zip entry")
                                try:
                                    rid = int(parts[0])
                                except ValueError as exc:
                                    raise ValueError("malformed remote id in zip") from exc
                                if rid not in remote_file_ids:
                                    raise ValueError("unexpected remote id in zip")
                                if rid in remote_ids:
                                    raise ValueError("duplicate remote id in zip")
                                remote_ids.add(rid)
                                fname = parts[1]
                                # Zip-slip guard: reject traversal vectors before
                                # joining with dest_folder. A malicious peer must
                                # not be able to write outside the import folder.
                                if not _validate_zip_entry_name(fname):
                                    logger.warning(
                                        "ZIP DL: rejected unsafe entry name from peer=%s: %r",
                                        peer.peer_id,
                                        name,
                                    )
                                    raise ValueError("unsafe zip entry name")
                                planned.append((info, rid, fname))
                            if not await _consume_budget(download_budget, expanded):
                                logger.warning("ZIP DL exceeded session extraction budget")
                                return None
                            for info, rid, fname in planned:
                                dest = _unique_dest(dest_folder, fname)
                                dest.parent.mkdir(parents=True, exist_ok=True)
                                # Post-resolve containment check (defence in depth
                                # against symlink races and platform-specific
                                # path normalisation surprises).
                                if not _verify_within(dest, dest_folder):
                                    logger.warning(
                                        "ZIP DL: dest escaped dest_folder, skipped: %s",
                                        dest,
                                    )
                                    raise ValueError("zip destination escaped import folder")
                                created.append(dest)
                                with zf.open(info) as src, dest.open("xb") as dst:
                                    shutil.copyfileobj(src, dst, length=1024 * 1024)
                                result[rid] = dest
        except Exception as exc:
            for path in created:
                path.unlink(missing_ok=True)
            logger.warning("ZIP DL error: %s", exc)
            return None
        return result
