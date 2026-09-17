"""Local endpoint discovery for shared LLM providers."""

from __future__ import annotations

import datetime as _dt
import logging
import socket
from collections.abc import Sequence
from dataclasses import dataclass

from .models import DiscoveredEndpoint, EndpointIdentity, EndpointObservation
from .probes import normalize_base_url, probe_ollama_tags

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class LocalNetworkFacts:
    primary_lan_ip: str | None
    all_local_ips: tuple[str, ...]
    hostname: str


def _now_rfc3339() -> str:
    return _dt.datetime.now(_dt.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def detect_local_network_facts() -> LocalNetworkFacts:
    """Collect a minimal set of local network facts for discovery."""
    from core.mdns.advertiser import _detect_local_addresses

    addresses: list[str] = []
    for packed in _detect_local_addresses():
        ip = socket.inet_ntoa(packed)
        if ip not in addresses:
            addresses.append(ip)
    primary = next((ip for ip in addresses if not ip.startswith("127.")), None)
    return LocalNetworkFacts(
        primary_lan_ip=primary,
        all_local_ips=tuple(addresses),
        hostname=socket.gethostname(),
    )


def discover_local_ollama_endpoints(
    *,
    timeout: float = 1.0,
    local_network_facts: LocalNetworkFacts | None = None,
) -> Sequence[DiscoveredEndpoint]:
    """Discover local Ollama endpoints on the default port.

    Returns at most one candidate in v1. LAN-reachable endpoints are preferred
    over loopback-only endpoints and become the canonical candidate.
    """
    facts = local_network_facts or detect_local_network_facts()
    observed_at = _now_rfc3339()

    if facts.primary_lan_ip:
        lan_url = normalize_base_url(f"http://{facts.primary_lan_ip}:11434")
        if probe_ollama_tags(lan_url, timeout=timeout, user_agent="yu_ai_manager/mdns"):
            return [DiscoveredEndpoint(
                identity=EndpointIdentity(
                    provider="ollama",
                    base_url=lan_url,
                    api_style="ollama_native",
                    scope="private_lan",
                ),
                observation=EndpointObservation(
                    source="local_auto",
                    advertisable=True,
                    reachable=True,
                    observed_at=observed_at,
                    tags_probe_path="/api/tags",
                ),
                alias_hint="ollama-local",
                display_preferred_url=lan_url,
            )]

    loopback_url = normalize_base_url("http://localhost:11434")
    if probe_ollama_tags(loopback_url, timeout=timeout, user_agent="yu_ai_manager/mdns"):
        logger.warning(
            "  [MDNS] Ollama detected on localhost only — set "
            "OLLAMA_HOST=0.0.0.0:11434 to make it reachable from LAN peers. "
            "Skipping llm_base_url advertise for now."
        )
        return [DiscoveredEndpoint(
            identity=EndpointIdentity(
                provider="ollama",
                base_url=loopback_url,
                api_style="ollama_native",
                scope="loopback",
            ),
            observation=EndpointObservation(
                source="local_auto",
                advertisable=False,
                reachable=True,
                observed_at=observed_at,
                tags_probe_path="/api/tags",
            ),
            alias_hint="ollama-local",
            display_preferred_url=loopback_url,
            suppressed_reason="policy_hidden",
        )]

    return []


async def discover_local_hailo_endpoints(
    *,
    self_web_port: int,
    hailo_ollama_enabled: bool = True,
    hailo_ollama_port: int = 8000,
    existing_backend_urls: frozenset[str] = frozenset(),
) -> Sequence[DiscoveredEndpoint]:
    """Wrap existing Hailo local detection in the shared discovery model."""
    from core.llm_router import hailo_detect

    detected = await hailo_detect.detect_all(
        self_web_port=self_web_port,
        hailo_ollama_enabled=hailo_ollama_enabled,
        hailo_ollama_port=hailo_ollama_port,
        existing_backend_urls=existing_backend_urls,
    )
    observed_at = _now_rfc3339()
    found: list[DiscoveredEndpoint] = []

    if detected.yu_extension_available:
        found.append(DiscoveredEndpoint(
            identity=EndpointIdentity(
                provider="hailo_genai",
                base_url=normalize_base_url(
                    f"http://localhost:{self_web_port}/ext/hailo-genai/v1"
                ),
                api_style="openai_compat",
                scope="loopback",
            ),
            observation=EndpointObservation(
                source="local_auto",
                advertisable=False,
                reachable=True,
                observed_at=observed_at,
                model_probe_path="/models",
            ),
            alias_hint="hailo-local",
            display_preferred_url=f"http://localhost:{self_web_port}/ext/hailo-genai/v1",
            metadata={"device_count": str(detected.device_count)},
        ))

    if detected.hailo_ollama_base_url:
        found.append(DiscoveredEndpoint(
            identity=EndpointIdentity(
                provider="hailo_ollama",
                base_url=normalize_base_url(detected.hailo_ollama_base_url),
                api_style="openai_compat",
                scope="loopback",
            ),
            observation=EndpointObservation(
                source="local_auto",
                advertisable=False,
                reachable=True,
                observed_at=observed_at,
                model_probe_path="/models",
            ),
            alias_hint="hailo-ollama-local",
            display_preferred_url=normalize_base_url(detected.hailo_ollama_base_url),
        ))

    return found
