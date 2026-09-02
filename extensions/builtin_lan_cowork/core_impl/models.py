"""extensions/builtin_lan_cowork/core_impl/models.py
Data models for LAN Cowork peer communication.
"""
from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class PeerInfo:
    """Information about a single peer on the LAN."""

    name: str
    api_host: str
    api_port: int
    peer_id: str = ""
    version: str = ""
    bridges: list[str] = field(default_factory=list)
    inference_types: list[str] = field(default_factory=list)
    pubkey: bytes | None = None
    x25519_pk: bytes | None = None
    gpu: str = ""
    generating: bool = False
    queue_depth: int = 0
    status: str = "online"  # online | offline
    last_seen: float = field(default_factory=time.time)
    token: str | None = None  # issued auth token
    token_expires_at: int | None = None  # unix timestamp
    token_issued_at: int | None = None  # unix timestamp
    session_id: str = ""  # new uuid per boot; receivers use this to detect restarts
    roles: list[str] = field(default_factory=list)  # ["chief"] or [] for regular nodes
    # Reachability tracking for auto-prune (UNIX seconds, None = never recorded).
    last_reached_at: int | None = None
    last_attempted_at: int | None = None

    def __post_init__(self) -> None:
        # peer_id is derived from the Ed25519 pubkey upstream.
        pass

    def to_dict(self) -> dict[str, Any]:
        return {
            "peer_id": self.peer_id,
            "name": self.name,
            "api_host": self.api_host,
            "api_port": self.api_port,
            "version": self.version,
            "bridges": self.bridges,
            "inference_types": self.inference_types,
            "pubkey": base64.b64encode(self.pubkey).decode() if self.pubkey else None,
            "x25519_pk": base64.b64encode(self.x25519_pk).decode() if self.x25519_pk else None,
            "gpu": self.gpu,
            "generating": self.generating,
            "queue_depth": self.queue_depth,
            "status": self.status,
            "last_seen": self.last_seen,
            "token": self.token,
            "token_expires_at": self.token_expires_at,
            "token_issued_at": self.token_issued_at,
            "session_id": self.session_id,
            "roles": list(self.roles),
        }

    def to_public_dict(self) -> dict[str, Any]:
        """Safe for unauthenticated responses.

        Keep only discovery-relevant fields. Exclude auth/session state and
        internal role metadata that are not needed for initial peer discovery.
        """
        d = self.to_dict()
        for key in (
            "token",
            "token_expires_at",
            "token_issued_at",
            "session_id",
            "roles",
        ):
            d.pop(key, None)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeerInfo:
        obj = cls(
            peer_id=d.get("peer_id", ""),
            name=d.get("name", ""),
            api_host=d.get("api_host", ""),
            api_port=d.get("api_port", 5000),
            version=d.get("version", ""),
            bridges=d.get("bridges", []),
            inference_types=d.get("inference_types", []),
            pubkey=_decode_optional_bytes(d.get("pubkey")),
            x25519_pk=_decode_optional_bytes(d.get("x25519_pk")),
            gpu=d.get("gpu", ""),
            generating=d.get("generating", False),
            queue_depth=d.get("queue_depth", 0),
            status=d.get("status", "online"),
            last_seen=d.get("last_seen", time.time()),
        )
        obj.token = d.get("token")
        obj.token_expires_at = d.get("token_expires_at")
        obj.token_issued_at = d.get("token_issued_at")
        obj.session_id = d.get("session_id", "")
        obj.roles = list(d.get("roles", []))
        return obj


def _decode_optional_bytes(value: Any) -> bytes | None:
    if value is None or value == "":
        return None
    if isinstance(value, bytes):
        return value
    if isinstance(value, str):
        return base64.b64decode(value)
    return None


@dataclass
class PeerMessage:
    """Message exchanged between peers.

    type="structured" for protocol messages (heartbeat, job, sync).
    type="negotiation" reserved for future LLM agent natural language exchange.
    """

    type: str  # "structured" | "negotiation"
    payload: dict[str, Any] = field(default_factory=dict)
    text: str | None = None  # LLM negotiation text (future)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"type": self.type, "payload": self.payload}
        if self.text is not None:
            d["text"] = self.text
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PeerMessage:
        return cls(
            type=d.get("type", "structured"),
            payload=d.get("payload", {}),
            text=d.get("text"),
        )
