"""mDNS service startup initialization for the web_ui runtime."""

import asyncio
import contextlib
import dataclasses
import logging

logger = logging.getLogger(__name__)

_MDNS_SERVICE = None  # module-level handle for shutdown
_MDNS_BRIDGE = None   # LlmRouterMdnsBridge, exposed for debug introspection
_MDNS_PENDING = None  # (service, config, self_peer) — consumed by start_mdns_pending
_MDNS_SWEEP_TASK: asyncio.Task | None = None  # periodic retry sweep
_MDNS_SELF_PEER = None  # latest self PeerInfo advertised via MdnsService

# How often to re-scan known peers for missed verifications. Matches the
# verify cooldown so a genuinely unreachable peer retries at most every
# window, but a peer that came up in cooldown recovers within one tick.
_SWEEP_INTERVAL_SEC: float = 60.0
_SELF_ADVERT_REFRESH_SEC: float = 15.0


def init_node_identity(config: dict) -> None:
    """Load (or create) the persistent node_id used for mDNS self-identification."""
    from core import node_identity
    nid = node_identity.get_node_id()
    logger.info("  [NODE_IDENTITY] node_id=%s", nid)


def init_mdns_service(config: dict) -> None:
    """Build the mDNS service and stash it for ``before_serving``.

    Runs AFTER init_llm_router_discovery so that the BackendCatalog and the
    LLM Router module are initialised and we can wire the bridge to them.
    The actual ``MdnsService.start()`` call is deferred to ``start_mdns_pending()``
    which runs inside a Quart ``before_serving`` hook (see ``runtime_app``),
    because ``asyncio.get_running_loop()`` is not yet available at subsystem
    init time.
    """
    import os
    import socket

    if os.environ.get("YU_AI_MDNS_DISABLED", "").lower() in ("1", "true", "yes"):
        logger.info("  [MDNS] Disabled via YU_AI_MDNS_DISABLED")
        return

    mdns_cfg_raw = config.get("mdns", {}) or {}
    if not mdns_cfg_raw.get("enabled", True):
        logger.info("  [MDNS] Disabled in config")
        return

    from pathlib import Path

    from core import node_identity
    from core.llm_router.mdns_integration import LlmRouterMdnsBridge
    from core.llm_router.state import get_catalog
    from core.mdns import MdnsConfig, MdnsService, PeerInfo
    version_path = Path(__file__).resolve().parent.parent.parent / "VERSION"
    try:
        version = version_path.read_text().strip()
    except OSError:
        version = "0.0.0"

    router_cfg = config.get("llm_router", {}) or {}
    web_port = int(config.get("server", {}).get("port", 5000))
    configured_backends = router_cfg.get("backends") or []
    llm_base_url = ""
    llm_provider = "none"
    ollama_advertise_url = ""

    # Preference order:
    #   1. Explicit local backend in config.llm_router.backends (user intent)
    #   2. Auto-detected localhost Ollama (probe /api/tags)
    #   3. No LLM advertised — we still start mDNS, but peers will drop us
    #      from LLM Router discovery because llm_base_url is required.
    for entry in configured_backends:
        base = entry.get("base_url", "")
        if "localhost" in base or "127.0.0.1" in base or ".local" in base:
            llm_base_url = base
            llm_provider = entry.get("type", "ollama")
            break
    if not llm_base_url:
        from core.web.runtime_llm_router import _detect_local_ollama
        detected = _detect_local_ollama()
        if detected is not None:
            llm_base_url, llm_provider = detected
            logger.info("  [MDNS] Auto-detected local Ollama at %s", llm_base_url)
        else:
            logger.info(
                "  [MDNS] No local LLM backend detected — advertising without llm_base_url"
            )
    from core.web.runtime_llm_router import _detect_local_ollama
    detected_ollama = _detect_local_ollama()
    if detected_ollama is not None:
        ollama_advertise_url = detected_ollama[0]
        logger.info("  [MDNS] Advertising bare Ollama service at %s", ollama_advertise_url)

    # v4.66.0: include Hailo capability / URL in self-advertised PeerInfo
    # (populated from the catalog entries set by init_llm_router_discovery's
    # Phase A block, which runs earlier in the SUBSYSTEMS order).
    from core.mdns.address_utils import _pick_lan_ip, _rewrite_host_to_lan

    capabilities: list[str] = ["llm"] if llm_base_url else []
    cat = get_catalog()

    if cat.get_backend("hailo-local") is not None:
        capabilities.append("hailo")

    hailo_ollama_url_for_advert: str | None = None
    hailo_ollama_backend = cat.get_backend("hailo-ollama-local")
    if hailo_ollama_backend is not None and hailo_ollama_backend.base_url:
        lan_ip = _pick_lan_ip()
        if lan_ip:
            hailo_ollama_url_for_advert = _rewrite_host_to_lan(
                hailo_ollama_backend.base_url, lan_ip
            )

    self_peer = PeerInfo(
        node_id=node_identity.get_node_id(),
        version=version,
        llm_base_url=llm_base_url,
        capabilities=tuple(capabilities),
        llm_provider=llm_provider,
        web_port=web_port,
        hostname=socket.gethostname(),
        addresses=(),
        first_seen="",
        last_seen="",
        hailo_ollama_url=hailo_ollama_url_for_advert,
        ollama_advertise_url=ollama_advertise_url,
    )

    mdns_cfg = MdnsConfig(
        enabled=True,
        service_name=mdns_cfg_raw.get("service_name"),
        bind_address=mdns_cfg_raw.get("bind_address"),
    )

    mdns_service = MdnsService()
    bridge = LlmRouterMdnsBridge(self_node_id=self_peer.node_id)
    bridge.attach_catalog(get_catalog())
    bridge.mark_config_aliases({b.alias for b in get_catalog().list_backends()})
    mdns_service.subscribe(
        on_peer_added=bridge.on_peer_added,
        on_peer_updated=bridge.on_peer_updated,
        on_peer_removed=bridge.on_peer_removed,
    )

    import core.web.runtime_mdns as _self_module
    _self_module._MDNS_SERVICE = mdns_service
    _self_module._MDNS_BRIDGE = bridge
    _self_module._MDNS_PENDING = (mdns_service, mdns_cfg, self_peer)
    _self_module._MDNS_SELF_PEER = self_peer

    logger.info("  [MDNS] Prepared: node_id=%s (start deferred)", self_peer.node_id[:8])


async def start_mdns_pending() -> None:
    """Start the pending MdnsService from a ``before_serving`` hook.

    Called once per process after the asyncio loop is up. No-op if mDNS
    is disabled or already started.
    """
    import core.web.runtime_mdns as _self_module
    pending = getattr(_self_module, "_MDNS_PENDING", None)
    if pending is None:
        return
    mdns_service, mdns_cfg, self_peer = pending
    _self_module._MDNS_PENDING = None
    try:
        await mdns_service.start(mdns_cfg, self_peer)
        logger.info("  [MDNS] Started: status=%s", mdns_service.status)
    except Exception as exc:
        logger.warning("  [MDNS] Start failed: %s", exc)
        return

    bridge = getattr(_self_module, "_MDNS_BRIDGE", None)
    if bridge is not None and _self_module._MDNS_SWEEP_TASK is None:
        _self_module._MDNS_SWEEP_TASK = asyncio.create_task(
            _sweep_loop(mdns_service, bridge),
            name="mdns-bridge-sweep",
        )


async def _sweep_loop(mdns_service, bridge) -> None:
    """Periodically retry verification for peers not reachable in the catalog.

    Backs up the event-driven ``on_peer_added`` / ``on_peer_updated`` path:
    if a peer's TXT update event was missed (zeroconf cache edge case) or
    the peer came up while in a cooldown window, this sweep brings it back
    without waiting for the next service_info refresh.
    """
    try:
        while True:
            await asyncio.sleep(_SELF_ADVERT_REFRESH_SEC)
            try:
                await _maybe_refresh_self_advertisement(mdns_service)
            except Exception as exc:
                logger.debug("[MDNS] self advertisement refresh failed: %s", exc)
            await asyncio.sleep(max(0.0, _SWEEP_INTERVAL_SEC - _SELF_ADVERT_REFRESH_SEC))
            try:
                await bridge.retry_pending_peers(mdns_service.list_peers())
            except Exception as exc:
                logger.debug("[MDNS] sweep iteration failed: %s", exc)
    except asyncio.CancelledError:
        return


async def _maybe_refresh_self_advertisement(mdns_service) -> bool:
    """Promote a late-starting local Ollama into our self mDNS advertisement."""
    import core.web.runtime_mdns as _self_module
    current_peer = getattr(_self_module, "_MDNS_SELF_PEER", None)
    if current_peer is None:
        return False
    if current_peer.llm_base_url and current_peer.ollama_advertise_url:
        return False

    from core.web.runtime_llm_router import _detect_local_ollama

    detected = _detect_local_ollama()
    if detected is None:
        return False
    base_url, provider = detected
    if current_peer.llm_base_url == base_url and current_peer.ollama_advertise_url == base_url:
        return False

    capabilities = tuple(current_peer.capabilities)
    if "llm" not in capabilities:
        capabilities = (*capabilities, "llm")
    refreshed_peer = dataclasses.replace(
        current_peer,
        llm_base_url=base_url,
        llm_provider=provider,
        capabilities=capabilities,
        ollama_advertise_url=base_url,
    )
    changed = await mdns_service.readvertise_self(refreshed_peer)
    if changed:
        _self_module._MDNS_SELF_PEER = refreshed_peer
        logger.info("  [MDNS] Refreshed self advertisement with local Ollama at %s", base_url)
    return changed


async def stop_mdns_pending() -> None:
    """Cancel the periodic sweep task (paired with ``after_serving``)."""
    import core.web.runtime_mdns as _self_module
    task = _self_module._MDNS_SWEEP_TASK
    if task is None:
        return
    _self_module._MDNS_SWEEP_TASK = None
    task.cancel()
    with contextlib.suppress(asyncio.CancelledError, Exception):
        await task
