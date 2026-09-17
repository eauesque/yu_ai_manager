"""extensions/builtin_lan_cowork/core_impl/gen_dispatcher.py
Job dispatch logic with pluggable strategy for future LLM negotiation.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol

from .gen_models import GenJob
from .models import PeerInfo

if TYPE_CHECKING:
    from .registry import PeerRegistry
    from .transport import PeerTransport

logger = logging.getLogger(__name__)


class DispatchStrategy(Protocol):
    """Pluggable strategy for selecting a peer to handle a job.

    Initial: RuleBasedStrategy (bridge match + queue depth).
    Future: LLMNegotiationStrategy (natural language peer negotiation).
    """

    def select_peer(self, job: GenJob, peers: list[PeerInfo]) -> PeerInfo | None: ...


class RuleBasedStrategy:
    """Select peer by: bridge support → not generating → lowest queue_depth."""

    def select_peer(self, job: GenJob, peers: list[PeerInfo]) -> PeerInfo | None:
        candidates = [
            p for p in peers
            if p.status == "online" and job.bridge in p.bridges
        ]
        if not candidates:
            return None
        candidates.sort(key=lambda p: (p.generating, p.queue_depth, -p.last_seen))
        return candidates[0]


class GenDispatcher:
    """Decides whether/where to dispatch a generation job."""

    def __init__(
        self,
        local_peer: PeerInfo,
        registry: PeerRegistry,
        transport: PeerTransport | None,
        strategy: DispatchStrategy = None,
    ) -> None:
        self._local = local_peer
        self._registry = registry
        self._transport = transport
        self._strategy = strategy or RuleBasedStrategy()

    def should_dispatch(self, job: GenJob) -> bool:
        """Determine if this job should be sent to a remote peer."""
        # Local bridge not available
        if job.bridge not in self._local.bridges:
            return True
        # Local is busy and remote peers exist
        return bool(self._local.generating and self._registry.list_online())

    def select_target(self, job: GenJob) -> PeerInfo | None:
        """Select the best peer for the job."""
        peers = self._registry.list_online()
        return self._strategy.select_peer(job, peers)

    async def dispatch(self, job: GenJob) -> GenJob:
        """Send job to a remote peer and return updated job with results."""
        target = self.select_target(job)
        if target is None:
            job.status = "error"
            job.error = "No available peer for bridge: " + job.bridge
            return job

        job.target_peer = target.peer_id
        job.source_peer = self._local.peer_id
        job.status = "running"

        logger.info("Dispatching job %s to %s (%s)", job.job_id, target.name, target.api_host)

        ok, resp = await self._transport.send(target, "/api/peer/generate", job.to_dict())
        if not ok:
            job.status = "error"
            job.error = resp.get("error", "peer request failed") if isinstance(resp, dict) else "peer request failed"
            return job

        if not isinstance(resp, dict):
            job.status = "error"
            job.error = "peer returned non-object response"
            return job

        # Treat an explicit ok=False or an "error" payload as a failure even
        # when transport.send reported HTTP 2xx. Bridges return 400-style
        # validation failures (e.g. missing XMP target path) as 200+ok=False;
        # the dispatcher must surface those as job errors, not "complete".
        peer_ok = resp.get("ok")
        peer_error = resp.get("error") or ""
        if peer_ok is False or (peer_ok is None and peer_error):
            job.status = "error"
            job.error = peer_error or "peer reported failure"
            job.response = resp
            return job

        job.status = resp.get("status", "complete")
        job.images = resp.get("images", [])
        job.elapsed_ms = resp.get("elapsed_ms", 0)
        job.expanded_prompt = resp.get("expanded_prompt", "")
        job.error = peer_error
        # Forward the full peer payload so callers can read fields the
        # dispatcher does not flatten (bridge_managed_save, saved,
        # saved_items, prompt_id, original_prompt, final_negative).
        job.response = resp
        return job
