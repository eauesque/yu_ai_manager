"""extensions/builtin_lan_cowork/core_impl/sync_manager.py
Orchestrates wildcard/prompt file synchronization between peers.
"""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from .sync_manifest import Manifest, build_manifest, diff_manifests

if TYPE_CHECKING:
    from .models import PeerInfo
    from .registry import PeerRegistry
    from .transport import PeerTransport

logger = logging.getLogger(__name__)


def _backup_file(path: Path) -> None:
    """Create a .bak copy of a file (1 generation)."""
    bak = path.with_suffix(path.suffix + ".bak")
    shutil.copy2(str(path), str(bak))


def _validate_sync_path(root: Path, rel_path: str) -> Path:
    """Validate that rel_path resolves to a location within root.

    Raises ValueError if the path escapes the root directory.
    """
    resolved_root = root.resolve()
    target = (root / rel_path).resolve()
    if not target.is_relative_to(resolved_root):
        raise ValueError(f"Path escapes root: {rel_path}")
    return target


def _write_synced_file(root: Path, rel_path: str, content: bytes) -> bool:
    """Write a synced file, creating directories and backing up existing.

    Returns True if an existing file was overwritten (conflict).
    Raises ValueError if rel_path escapes the root directory.
    """
    target = _validate_sync_path(root, rel_path)
    conflict = target.exists()
    if conflict:
        _backup_file(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)
    return conflict


class SyncManager:
    """Manages bidirectional file sync between peers."""

    def __init__(
        self,
        wc_root: Path,
        registry: PeerRegistry,
        transport: PeerTransport,
        shared_folder_mode: bool = False,
    ) -> None:
        self._wc_root = wc_root.resolve()
        self._registry = registry
        self._transport = transport
        self._shared_folder = shared_folder_mode

    def local_manifest(self) -> Manifest:
        """Build manifest of local WC directory."""
        return build_manifest(self._wc_root)

    async def sync_with_peer(self, peer: PeerInfo) -> dict[str, list[str]]:
        """Full sync with a single peer. Returns {fetched: [...], pushed: [...]}."""
        if self._shared_folder:
            return {"fetched": [], "pushed": []}

        ok, resp = await self._transport.fetch_json(peer, "/api/peer/sync/manifest")
        if not ok:
            logger.warning("Failed to get manifest from %s", peer.name)
            return {"fetched": [], "pushed": []}

        remote_manifest = resp.get("manifest", {})
        local_manifest = self.local_manifest()
        to_fetch, to_push = diff_manifests(local_manifest, remote_manifest)

        fetched: list[str] = []
        skipped_fetches = 0
        for rel_path in to_fetch:
            content = await self._fetch_file(peer, rel_path)
            if content is not None:
                try:
                    conflict = _write_synced_file(self._wc_root, rel_path, content)
                except ValueError:
                    skipped_fetches += 1
                    continue
                fetched.append(rel_path)
                if conflict:
                    self._emit("SYNC_CONFLICT", {"path": rel_path})
                self._emit("SYNC_FILE_RECEIVED", {"path": rel_path, "peer": peer.name})

        if skipped_fetches:
            logger.warning("Skipped %d peer sync file(s) outside local root", skipped_fetches)

        pushed: list[str] = []
        for rel_path in to_push:
            ok = await self._push_file(peer, rel_path)
            if ok:
                pushed.append(rel_path)

        if fetched or pushed:
            self._emit("SYNC_MANIFEST_EXCHANGED", {
                "peer": peer.name, "fetched": len(fetched), "pushed": len(pushed),
            })

        return {"fetched": fetched, "pushed": pushed}

    async def sync_with_all(self) -> None:
        """Sync with all online peers (in parallel — offline peers each hit
        the 5 s connect timeout, so a serial loop balloons to peers x 5 s)."""
        import asyncio
        peers = self._registry.list_online()
        if not peers:
            return
        await asyncio.gather(
            *(self.sync_with_peer(p) for p in peers),
            return_exceptions=True,
        )

    async def handle_remote_change(self, peer: PeerInfo, rel_path: str) -> None:
        """Called when a peer notifies us of a file change."""
        if self._shared_folder:
            return
        content = await self._fetch_file(peer, rel_path)
        if content is not None:
            try:
                conflict = _write_synced_file(self._wc_root, rel_path, content)
            except ValueError:
                logger.warning("Skipped 1 peer sync file outside local root")
                return
            if conflict:
                self._emit("SYNC_CONFLICT", {"path": rel_path})
            self._emit("SYNC_FILE_RECEIVED", {"path": rel_path, "peer": peer.name})

    def notify_local_change(self, rel_path: str) -> None:
        """Called when a local WC file changes. Emits event for relay."""
        try:
            full_path = _validate_sync_path(self._wc_root, rel_path)
        except ValueError:
            logger.debug("Skipping local sync notification outside root: %s", rel_path)
            return
        entry = {}
        if full_path.exists():
            from .sync_manifest import file_hash
            stat = full_path.stat()
            entry = {
                "hash": file_hash(full_path),
                "mtime": stat.st_mtime,
                "size": stat.st_size,
            }
        self._emit("SYNC_FILE_CHANGED", {"path": rel_path, "entry": entry})

    async def _fetch_file(self, peer: PeerInfo, rel_path: str) -> bytes | None:
        """Download a file from a peer."""
        from urllib.parse import urlencode

        import httpx

        query_string = urlencode({"path": rel_path})
        path = "/api/peer/sync/file"
        url = self._transport.build_url(peer, f"{path}?{query_string}")
        headers = self._transport.build_signed_headers(
            peer,
            "GET",
            f"{self._transport._PREFIX}{path}",
            b"",
            query_string=query_string,
        )
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, headers=headers)
                if resp.status_code == 200:
                    return resp.content
        except Exception as e:
            logger.warning("Failed to fetch %s from %s: %s", rel_path, peer.name, e)
        return None

    async def _push_file(self, peer: PeerInfo, rel_path: str) -> bool:
        """Upload a file to a peer."""
        try:
            full_path = _validate_sync_path(self._wc_root, rel_path)
        except ValueError:
            logger.debug("Skipping local sync push outside root: %s", rel_path)
            return False
        if not full_path.exists():
            return False
        content = full_path.read_bytes()
        import base64
        ok, _ = await self._transport.send(
            peer, "/api/peer/sync/push",
            {"path": rel_path, "content_b64": base64.b64encode(content).decode()},
        )
        return ok

    def _emit(self, event_type: str, data: dict) -> None:
        """Emit event via event bus."""
        try:
            from core.event_bus import emit, event_types
            emit(getattr(event_types, event_type), data, source="lan-cowork")
        except Exception:
            logger.warning("sync event %s was not emitted", event_type, exc_info=True)
