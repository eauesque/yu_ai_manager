"""Negotiation message types: Proposal and NegotiationResponse."""
from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class Proposal:
    """A task proposal sent to candidate peers for negotiation."""
    task_type: str
    task_description: str
    requirements: dict[str, Any]
    sender_peer_id: str
    proposal_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "task_type": self.task_type,
            "task_description": self.task_description,
            "requirements": self.requirements,
            "sender_peer_id": self.sender_peer_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Proposal:
        return cls(
            proposal_id=d["proposal_id"],
            task_type=d["task_type"],
            task_description=d["task_description"],
            requirements=d.get("requirements", {}),
            sender_peer_id=d["sender_peer_id"],
            timestamp=d.get("timestamp", time.time()),
        )


@dataclass
class NegotiationResponse:
    """A peer's response to a negotiation proposal."""
    proposal_id: str
    accept: bool
    reason: str
    responder_peer_id: str
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, Any]:
        return {
            "proposal_id": self.proposal_id,
            "accept": self.accept,
            "reason": self.reason,
            "responder_peer_id": self.responder_peer_id,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> NegotiationResponse:
        return cls(
            proposal_id=d["proposal_id"],
            accept=d.get("accept", False),
            reason=d.get("reason", ""),
            responder_peer_id=d.get("responder_peer_id", ""),
            timestamp=d.get("timestamp", time.time()),
        )
