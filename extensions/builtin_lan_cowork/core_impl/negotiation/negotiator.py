"""Negotiator: orchestrate task proposals across mesh peers."""
from __future__ import annotations

import asyncio
import logging
from typing import TYPE_CHECKING

from .channel import NegotiationChannel
from .protocol import Proposal

if TYPE_CHECKING:
    from ..models import PeerInfo
    from ..registry import PeerRegistry

logger = logging.getLogger(__name__)


class Negotiator:
    """Send task proposals to LLM-capable peers and pick the best responder."""

    def __init__(
        self,
        local_peer_id: str,
        registry: PeerRegistry,
        channel: NegotiationChannel,
    ) -> None:
        self._local_peer_id = local_peer_id
        self._registry = registry
        self._channel = channel

    async def negotiate(
        self,
        task_type: str,
        task_description: str,
        requirements: dict,
    ) -> PeerInfo | None:
        """Propose a task to LLM-capable peers, return the best acceptor or None."""
        candidates = [
            p for p in self._registry.list_all()
            if p.status == "online"
            and "llm" in p.inference_types
            and p.peer_id != self._local_peer_id
        ]
        if not candidates:
            logger.debug("No LLM-capable peers for negotiation")
            return None

        proposal = Proposal(
            task_type=task_type,
            task_description=task_description,
            requirements=requirements,
            sender_peer_id=self._local_peer_id,
        )

        # Send proposals to all candidates concurrently
        tasks = [
            self._channel.send_proposal(peer, proposal)
            for peer in candidates
        ]
        responses = await asyncio.gather(*tasks, return_exceptions=True)

        # Collect acceptors
        acceptors = []
        for peer, resp in zip(candidates, responses, strict=False):
            if isinstance(resp, Exception):
                logger.warning("Negotiation error from %s: %s", peer.name, resp)
                continue
            logger.info(
                "Negotiation %s from %s: accept=%s reason=%s",
                proposal.proposal_id[:8], peer.name, resp.accept, resp.reason,
            )
            if resp.accept:
                acceptors.append(peer)

        if not acceptors:
            logger.info("No peers accepted proposal %s", proposal.proposal_id[:8])
            return None

        # Pick peer with lowest queue_depth
        best = min(acceptors, key=lambda p: p.queue_depth)
        logger.info(
            "Negotiation winner: %s (queue_depth=%d)", best.name, best.queue_depth
        )
        return best
