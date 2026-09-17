"""LAN Cowork manager orchestration."""

from __future__ import annotations

import asyncio
import contextlib
import logging
import socket
import uuid
from pathlib import Path

from .manager_bootstrap import detect_bridges, get_local_ip, get_version, load_or_create_identity

logger = logging.getLogger(__name__)
_SWEEPER_INTERVAL = 60


class CoworkManager:
    """Orchestrates all LAN Cowork subsystems."""

    def __init__(self, config: dict, *, loopback_listener: bool = False) -> None:
        self.config = config
        from core.mesh_inference import set_router
        from core.services_core.db_state import get_db, get_readonly_db

        from .core_impl.discovery import PeerDiscovery
        from .core_impl.gen_dispatcher import GenDispatcher, RuleBasedStrategy
        from .core_impl.heartbeat import HeartbeatLoop
        from .core_impl.inference.router import InferenceRouter
        from .core_impl.inference.state import InferenceState
        from .core_impl.models import PeerInfo
        from .core_impl.negotiation.channel import HTTPChannel
        from .core_impl.negotiation.negotiator import Negotiator
        from .core_impl.pairing_service import PairingService
        from .core_impl.peer_auth_client import PeerAuthClient
        from .core_impl.peer_event_relay import PeerEventRelay
        from .core_impl.registry import PeerRegistry
        from .core_impl.token_store import TokenStore
        from .core_impl.transport import PeerTransport

        peer_name = config.get("peer_name", "auto")
        if peer_name == "auto":
            peer_name = socket.gethostname()

        # P3: remove deprecated config key (no-op after first run).
        # Function-local import to avoid circular import / startup load-order dependency.
        # delete_extension_config_value is idempotent, so re-instantiation in tests is safe.
        from core.extensions_core.lifecycle.extensions_admin import (
            delete_extension_config_value,
        )
        delete_extension_config_value("builtin-lan-cowork", "ip_check_mode")

        peer_id, seed, pubkey, x25519_pk = load_or_create_identity()
        self._seed = seed
        self.local_peer = PeerInfo(
            name=peer_name,
            api_host=get_local_ip(),
            api_port=config.get("api_port", 5000),
            version=get_version(),
            bridges=detect_bridges(),
            peer_id=peer_id,
            session_id=uuid.uuid4().hex,
        )
        self.local_peer.pubkey = pubkey
        self.local_peer.x25519_pk = x25519_pk
        self.registry = PeerRegistry(local_peer_id=self.local_peer.peer_id)
        self.transport = PeerTransport(local_peer_id=self.local_peer.peer_id, seed=self._seed)
        self.discovery = PeerDiscovery(
            local_peer=self.local_peer,
            port=config.get("discovery_port", 19850),
            on_peer_found=self._on_peer_found,
            seed=self._seed,
        )
        self.heartbeat_loop = HeartbeatLoop(
            self.local_peer, self.registry, self.transport, self.discovery, loopback_listener,
        )
        self.event_relay = PeerEventRelay(
            self.registry, self.transport, self.local_peer.peer_id,
        )

        self.sync = None
        sync_cfg = config.get("sync", {})
        if sync_cfg.get("enabled", True):
            wc_root = self._resolve_wc_root(sync_cfg)
            if wc_root:
                from .core_impl.sync_manager import SyncManager
                self.sync = SyncManager(
                    wc_root=wc_root,
                    registry=self.registry,
                    transport=self.transport,
                    shared_folder_mode=sync_cfg.get("shared_folder_mode", False),
                )

        # GenDispatcher is the *send* side of LAN Cowork generation
        # (`should_dispatch` -> `select_target` -> `dispatch`). The receive
        # side is wired in routes/gen_api.py:peer_generate via the central
        # bridge_handlers registry. The send-side wiring (intercepting each
        # bridge's local /api/generate to consult should_dispatch) is
        # tracked as planned work in
        # docs/superpowers/plans/2026-04-04-distributed-gen-queue.md
        # — until then this dispatcher is constructed and unit-tested but
        # never invoked from the live request path. Do NOT assume LAN
        # Cowork auto-offload is active just because this object exists.
        self.dispatcher = GenDispatcher(
            local_peer=self.local_peer,
            registry=self.registry,
            transport=self.transport,
            strategy=RuleBasedStrategy(),
        )
        self.inference_state = InferenceState()
        self.inference_capabilities = []
        self.inference_router = InferenceRouter(
            local_peer=self.local_peer,
            registry=self.registry,
        )
        set_router(self.inference_router)

        self.negotiation_channel = HTTPChannel(self.transport)
        self.negotiator = Negotiator(
            local_peer_id=self.local_peer.peer_id,
            registry=self.registry,
            channel=self.negotiation_channel,
        )

        self.token_store = TokenStore(get_db, get_readonly_db)
        self.pairing_service = PairingService(
            get_db,
            self.token_store,
            get_readonly_db,
            server_pubkey=self.local_peer.pubkey,
            server_x25519_pk=self.local_peer.x25519_pk,
        )
        self.auth_client = PeerAuthClient(self.registry, self.local_peer)
        self._sweeper_task: asyncio.Task | None = None

        fleet_cfg = config.get("fleet", {}) or {}
        self._fleet_manager = None
        if fleet_cfg.get("chief", False):
            from .core_impl.fleet.fleet_manager import FleetManager
            self._fleet_manager = FleetManager(self)
            self.local_peer.roles = ["chief"]

    def local_seed(self) -> bytes:
        return self._seed

    def complete_pairing(self, request_id: str, peer_pubkey: bytes) -> None:
        from .core_impl.models import PeerInfo

        row = self.pairing_service.get(request_id)
        if row is None:
            raise ValueError("pairing request not found")
        peer = PeerInfo(
            name=row["peer_id"],
            api_host=row["host"],
            api_port=int(row["port"]),
            peer_id=row["peer_id"],
            pubkey=peer_pubkey,
            x25519_pk=row["x25519_pk"],
        )
        self.registry.upsert(peer)

    def _resolve_wc_root(self, sync_cfg: dict) -> Path | None:
        if sync_cfg.get("shared_folder_mode") and sync_cfg.get("shared_folder_path"):
            path = Path(sync_cfg["shared_folder_path"])
            return path if path.is_dir() else None
        try:
            from core.bridge_core.prompt_expand import _wc_dirs
            if _wc_dirs:
                return Path(_wc_dirs[0])
        except Exception:
            logger.debug("wildcard directory fallback unavailable", exc_info=True)
        return None

    def _on_peer_found(self, parsed, addr: str) -> None:
        import ipaddress
        import time

        from .core_impl.models import PeerInfo

        try:
            ip = ipaddress.ip_address(addr)
            if not (ip.is_private or ip.is_link_local) or ip.is_loopback:
                logger.debug("Ignoring peer from non-private addr: %s", addr)
                return
        except ValueError:
            return

        existing = self.registry.get_by_pubkey(parsed.pubkey)
        if existing is not None:
            from core.crypto_identity import verify_hello

            if not verify_hello(parsed, existing.pubkey):
                logger.warning(
                    "HELLO signature verify failed peer=%s addr=%s",
                    parsed.peer_dict.get("peer_id"),
                    addr,
                )
                return
            self.registry.update_runtime(
                existing.peer_id,
                last_seen=time.time(),
                status="online",
            )
            if existing.api_host != addr or existing.x25519_pk != parsed.x25519_pk:
                from dataclasses import replace

                updated_existing = replace(existing)
                updated_existing.api_host = addr
                updated_existing.x25519_pk = parsed.x25519_pk
                self.registry.upsert(updated_existing)
            return

        pd = parsed.peer_dict
        new_peer = PeerInfo(
            name=pd.get("name", ""),
            api_host=addr,
            api_port=int(pd.get("api_port", 0)),
            peer_id=pd.get("peer_id", ""),
            version=pd.get("version", ""),
            bridges=list(pd.get("bridges", [])),
            inference_types=list(pd.get("inference_types", [])),
        )
        new_peer.pubkey = parsed.pubkey
        new_peer.x25519_pk = parsed.x25519_pk
        existing_by_id = self.registry.get(new_peer.peer_id)
        if (
            existing_by_id is not None
            and existing_by_id.token
            and (not existing_by_id.pubkey or existing_by_id.pubkey == parsed.pubkey)
        ):
            new_peer.token = existing_by_id.token
            new_peer.token_expires_at = existing_by_id.token_expires_at
            new_peer.token_issued_at = existing_by_id.token_issued_at
        new_peer.last_seen = time.time()
        new_peer.status = "online"
        self.registry.upsert(new_peer)

    async def _introduce_to_peer(self, peer) -> None:
        my_host = self.local_peer.api_host
        my_port = self.local_peer.api_port
        if not my_host or my_host in ("0.0.0.0", "::"):
            return
        ok, resp = await self.transport.send(peer, "/api/peer/register", {"host": my_host, "port": my_port})
        if ok:
            logger.debug("Introduced ourselves to %s (%s)", peer.name, peer.api_host)
        else:
            logger.debug("Introduction to %s failed: %s", peer.name, resp.get("error", "unknown"))

    async def start(self) -> None:
        await self.discovery.start()
        await self.heartbeat_loop.start()
        self.event_relay.start()
        if self.sync:
            from .core_impl.sync_watcher import SyncWatcher
            self._sync_watcher = SyncWatcher(self.sync._wc_root, self.sync)
            self._sync_watcher.start()
            await self.sync.sync_with_all()

        from .core_impl.inference.probe import InferenceProbe
        probe = InferenceProbe()
        self.inference_capabilities = probe.detect_all()
        self.local_peer.inference_types = list(set(cap.inference_type for cap in self.inference_capabilities))
        logger.info("Inference capabilities: %s", [cap.to_dict() for cap in self.inference_capabilities])

        if "llm" in self.local_peer.inference_types:
            self._init_llm_client()
        if self._fleet_manager is not None:
            demoted = await self._fleet_manager.observe_and_maybe_demote()
            if demoted:
                self._fleet_manager = None
            else:
                await self._fleet_manager.start()

        self._sweeper_task = asyncio.ensure_future(self._pairing_sweeper())
        logger.info("CoworkManager started as '%s'", self.local_peer.name)

    async def _pairing_sweeper(self) -> None:
        while True:
            try:
                await asyncio.sleep(_SWEEPER_INTERVAL)
            except asyncio.CancelledError:
                break
            try:
                await asyncio.to_thread(self.pairing_service.sweep_expired)
            except Exception as exc:
                logger.warning("pairing_service.sweep_expired() failed: %s", exc)

    def _init_llm_client(self) -> None:
        try:
            from core.llm_core.registry import get_llm_client
            client = get_llm_client("general")
            if client is None:
                from core.configuration.api import load_config
                endpoints = load_config().get("llm_endpoints", {})
                for category in endpoints:
                    client = get_llm_client(category)
                    if client:
                        self.inference_state.set_llm_client(client, category)
                        logger.info("LLM client initialized: category=%s", category)
                        return
            else:
                self.inference_state.set_llm_client(client, "general")
                logger.info("LLM client initialized: category=general")
        except Exception as exc:
            logger.warning("LLM client init failed: %s", exc)

    async def stop(self) -> None:
        from core.mesh_inference import set_router
        set_router(None)
        if self._fleet_manager is not None:
            await self._fleet_manager.stop()
        if self._sweeper_task and not self._sweeper_task.done():
            self._sweeper_task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await self._sweeper_task
        if hasattr(self, "_sync_watcher") and self._sync_watcher:
            self._sync_watcher.stop()
        self.event_relay.stop()
        await self.heartbeat_loop.stop()
        await self.discovery.stop()
        logger.info("CoworkManager stopped")
