"""Shared data models for LLM endpoint discovery."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

ProviderKind = Literal["ollama", "openai_compat", "hailo_ollama", "hailo_genai"]
ApiStyle = Literal["ollama_native", "openai_compat"]
EndpointSource = Literal["local_auto", "mdns"]
EndpointScope = Literal["loopback", "private_lan", "public"]
Capability = Literal["llm"]
SuppressedReason = Literal[
    "timeout",
    "auth_required",
    "probe_not_found",
    "invalid_response",
    "connection_failed",
    "duplicate",
    "matched_existing",
    "policy_hidden",
]


@dataclass(frozen=True)
class EndpointIdentity:
    provider: ProviderKind
    base_url: str
    api_style: ApiStyle
    scope: EndpointScope
    node_id: str | None = None


@dataclass(frozen=True)
class EndpointObservation:
    source: EndpointSource
    advertisable: bool = False
    reachable: bool = False
    observed_at: str = ""
    model_probe_path: str = ""
    tags_probe_path: str = ""
    capability: Capability = "llm"


@dataclass(frozen=True)
class DiscoveredEndpoint:
    identity: EndpointIdentity
    observation: EndpointObservation
    alias_hint: str | None = None
    duplicate_of_canonical_url: str | None = None
    suppressed_reason: SuppressedReason | None = None
    display_preferred_url: str | None = None
    metadata: dict[str, str] = field(default_factory=dict)
