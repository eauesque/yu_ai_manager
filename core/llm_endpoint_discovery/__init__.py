"""Shared LLM endpoint discovery primitives."""

from .local_detect import (
    LocalNetworkFacts,
    detect_local_network_facts,
    discover_local_hailo_endpoints,
    discover_local_ollama_endpoints,
)
from .models import DiscoveredEndpoint, EndpointIdentity, EndpointObservation
from .probes import normalize_base_url, probe_ollama_tags

__all__ = [
    "DiscoveredEndpoint",
    "EndpointIdentity",
    "EndpointObservation",
    "LocalNetworkFacts",
    "detect_local_network_facts",
    "discover_local_hailo_endpoints",
    "discover_local_ollama_endpoints",
    "normalize_base_url",
    "probe_ollama_tags",
]
