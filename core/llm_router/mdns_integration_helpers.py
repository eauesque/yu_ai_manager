"""Helper functions for the mDNS bridge implementation."""

from __future__ import annotations

import asyncio
import dataclasses

from core.llm_router.models import BackendInfo
from core.mdns.peer_info import PeerInfo


async def verify_peer(bridge, peer: PeerInfo) -> str | None:
    """Try each advertised address in order until one verifies."""
    from core.llm_router import mdns_integration as facade

    if peer.service_kind == "ollama_mdns":
        return await facade._probe_bare_ollama(peer)
    if not peer.addresses:
        facade.logger.warning("[mdns] peer %s has no addresses", peer.node_id[:8])
        return None

    last_error: str | None = None
    for candidate in peer.addresses:
        narrowed = dataclasses.replace(peer, addresses=(candidate,))
        try:
            body = await asyncio.wait_for(
                bridge._verify_identity(narrowed),
                timeout=facade._VERIFY_TIMEOUT_SEC + facade._WAIT_FOR_BUFFER_SEC,
            )
        except TimeoutError:
            last_error = f"timeout on {candidate}"
            facade.logger.debug(
                "[mdns] identity verify timeout for %s via %s",
                peer.node_id[:8], candidate,
            )
            continue
        except Exception as exc:
            last_error = f"{candidate}: {exc}"
            facade.logger.debug(
                "[mdns] identity verify attempt failed for %s via %s: %s",
                peer.node_id[:8], candidate, exc,
            )
            continue

        if not isinstance(body, dict):
            last_error = f"{candidate}: non-dict response"
            continue
        if body.get("product") != "yu_ai_manager":
            facade.logger.warning(
                "[mdns] peer identity mismatch: product=%r",
                body.get("product"),
            )
            return None
        if body.get("node_id") != peer.node_id:
            facade.logger.warning(
                "[mdns] peer identity mismatch: node_id advertised=%s returned=%s",
                peer.node_id[:8],
                str(body.get("node_id"))[:8],
            )
            return None

        returned_version = body.get("version")
        if returned_version and returned_version != peer.version:
            facade.logger.info(
                "[mdns] peer %s version drift: advertised=%s returned=%s "
                "(accepting — major version check already applied)",
                peer.node_id[:8], peer.version, returned_version,
            )
        if candidate != peer.addresses[0]:
            facade.logger.info(
                "[mdns] peer %s verified via fallback address %s (primary %s unreachable)",
                peer.node_id[:8], candidate, peer.addresses[0],
            )
        return candidate

    facade.logger.info(
        "[mdns] identity verify failed for %s on all %d addresses; last_error=%s",
        peer.node_id[:8], len(peer.addresses), last_error,
    )
    return None


def apply_peer_to_catalog(bridge, peer: PeerInfo, verified_address: str | None = None) -> None:
    """Apply a verified peer to the backend catalog."""
    from core.llm_router import mdns_integration as facade

    assert bridge._catalog is not None, "attach_catalog must be called first"

    if peer.addresses and peer.service_kind == "yu":
        try:
            from core.web.trusted_peer_registry import get_registry
            get_registry().add_peer(peer.node_id, peer.addresses)
        except Exception as exc:
            facade.logger.warning(
                "[mdns] trusted peer registration failed for %s: %s",
                peer.node_id[:8], exc,
            )

    peer_ip = verified_address or (peer.addresses[0] if peer.addresses else None)
    alias = (
        f"{facade._ALIAS_PREFIX}{peer.node_id[:8]}-ollama"
        if peer.service_kind == "ollama_mdns"
        else f"{facade._ALIAS_PREFIX}{peer.node_id[:8]}"
    )
    if alias in bridge._config_aliases:
        facade.logger.info(
            "[mdns] alias %s collision with config, skipping mDNS-discovered peer",
            alias,
        )
        return

    if peer.llm_base_url:
        effective_base_url = peer.llm_base_url
        if peer_ip:
            from core.mdns.address_utils import _rewrite_host_to_lan
            rewritten = _rewrite_host_to_lan(peer.llm_base_url, peer_ip)
            if rewritten:
                effective_base_url = rewritten
                facade.logger.debug(
                    "[mdns] rewrote peer %s llm_base_url %s -> %s",
                    peer.node_id[:8], peer.llm_base_url, rewritten,
                )

        existing = find_backend(bridge, alias)
        info = BackendInfo(
            alias=alias,
            base_url=effective_base_url,
            type=peer.llm_provider or "ollama",
            status="unknown",
            models=existing.models if existing is not None else [],
            last_seen_at=facade._now_iso(),
            last_error=None,
            auto_discover=True,
            source="mdns",
        )
        bridge._catalog.set_backend(info)
        bridge._managed_aliases.add(alias)

    if peer.service_kind != "yu":
        return

    if "hailo" in peer.capabilities and peer_ip and peer.web_port:
        hailo_alias = f"{alias}-hailo"
        if hailo_alias not in bridge._config_aliases:
            existing_hailo = find_backend(bridge, hailo_alias)
            bridge._catalog.set_backend(BackendInfo(
                alias=hailo_alias,
                base_url=f"http://{peer_ip}:{peer.web_port}/ext/hailo-genai/v1",
                type="hailo-ollama",
                status="unknown",
                models=existing_hailo.models if existing_hailo is not None else [],
                last_seen_at=facade._now_iso(),
                last_error=None,
                auto_discover=True,
                source="mdns",
            ))
            bridge._managed_aliases.add(hailo_alias)

    if peer.hailo_ollama_url:
        ho_alias = f"{alias}-hailo-ollama"
        if ho_alias not in bridge._config_aliases:
            existing_ho = find_backend(bridge, ho_alias)
            bridge._catalog.set_backend(BackendInfo(
                alias=ho_alias,
                base_url=peer.hailo_ollama_url,
                type="hailo-ollama",
                status="unknown",
                models=existing_ho.models if existing_ho is not None else [],
                last_seen_at=facade._now_iso(),
                last_error=None,
                auto_discover=True,
                source="mdns",
            ))
            bridge._managed_aliases.add(ho_alias)


def mark_unreachable(bridge, node_id: str, *, reason: str) -> None:
    """Mark all aliases for a node as unreachable."""
    from core.llm_router import mdns_integration as facade

    assert bridge._catalog is not None, "attach_catalog must be called first"
    base_alias = f"{facade._ALIAS_PREFIX}{node_id[:8]}"
    candidates = (
        base_alias,
        f"{base_alias}-ollama",
        f"{base_alias}-hailo",
        f"{base_alias}-hailo-ollama",
    )
    for alias in candidates:
        if alias not in bridge._managed_aliases:
            continue
        existing = find_backend(bridge, alias)
        if existing is None:
            continue
        existing.status = "unreachable"
        existing.last_error = reason
        existing.last_seen_at = facade._now_iso()
        bridge._catalog.set_backend(existing)


def find_backend(bridge, alias: str) -> BackendInfo | None:
    """Find a backend by alias in the attached catalog."""
    assert bridge._catalog is not None
    for backend in bridge._catalog.list_backends():
        if backend.alias == alias:
            return backend
    return None
