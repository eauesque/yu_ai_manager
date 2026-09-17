"""extensions/builtin_lan_cowork/core_impl/gen_models.py
Data models for distributed generation jobs.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any


@dataclass
class GenJob:
    """A generation job that can be dispatched to a peer."""

    bridge: str
    prompt: str
    negative_prompt: str
    params: dict[str, Any] = field(default_factory=dict)
    job_id: str = ""
    source_peer: str = ""
    target_peer: str = ""
    status: str = "pending"  # pending | running | complete | error
    image_sync: str = "immediate"  # immediate | lazy
    images: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    elapsed_ms: float = 0
    expanded_prompt: str = ""
    # Full bridge response payload from the executing peer / handler.
    # Holds fields the dispatcher does not flatten into named attributes
    # (bridge_managed_save / saved / saved_items / prompt_id /
    #  original_prompt / final_negative / ok / etc.) so callers can read
    # the exact shape the local route would have produced.
    response: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not self.job_id:
            self.job_id = uuid.uuid4().hex[:16]

    def to_dict(self) -> dict[str, Any]:
        # Canonical wire format is FLAT: params are spread at top-level so
        # bridge generation fields (seed/cfg/steps/sweep_meta/...) match
        # what the 3 Bridge JS clients already send. The receiver's
        # PeerGenerationRequest uses extra="allow" + GenJob.from_dict to
        # collect them back into params.
        d: dict[str, Any] = {
            "job_id": self.job_id,
            "bridge": self.bridge,
            "prompt": self.prompt,
            "negative_prompt": self.negative_prompt,
            "source_peer": self.source_peer,
            "target_peer": self.target_peer,
            "status": self.status,
            "image_sync": self.image_sync,
            "error": self.error,
            "elapsed_ms": self.elapsed_ms,
            "expanded_prompt": self.expanded_prompt,
        }
        d.update(self.params)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GenJob:
        # All non-known top-level keys are bridge generation fields and get
        # preserved in params for dispatch/orchestration code.
        # Legacy nested {"params": {...}} is still accepted for back-compat;
        # explicit top-level extras win over nested keys on collision.
        known_keys = {
            "job_id", "bridge", "prompt", "negative_prompt", "params",
            "source_peer", "target_peer", "status", "image_sync",
            "images", "error", "elapsed_ms", "expanded_prompt", "response",
        }
        extras = {k: v for k, v in d.items() if k not in known_keys}
        params: dict[str, Any] = {}
        params.update(d.get("params") or {})
        params.update(extras)
        return cls(
            job_id=d.get("job_id", ""),
            bridge=d.get("bridge", ""),
            prompt=d.get("prompt", ""),
            negative_prompt=d.get("negative_prompt", ""),
            params=params,
            source_peer=d.get("source_peer", ""),
            target_peer=d.get("target_peer", ""),
            status=d.get("status", "pending"),
            image_sync=d.get("image_sync", "immediate"),
            error=d.get("error", ""),
            elapsed_ms=d.get("elapsed_ms", 0),
            expanded_prompt=d.get("expanded_prompt", ""),
        )
