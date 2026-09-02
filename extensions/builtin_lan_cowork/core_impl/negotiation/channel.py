"""Negotiation communication channels.

Abstracts transport so the negotiation layer can switch
from HTTP to WebSocket or other protocols in the future.
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Protocol, runtime_checkable

from .protocol import NegotiationResponse, Proposal

if TYPE_CHECKING:
    from ..models import PeerInfo
    from ..transport import PeerTransport

logger = logging.getLogger(__name__)


@runtime_checkable
class NegotiationChannel(Protocol):
    """Abstract channel for sending negotiation proposals."""

    async def send_proposal(
        self, peer: PeerInfo, proposal: Proposal
    ) -> NegotiationResponse: ...


class HTTPChannel:
    """Send proposals via PeerTransport HTTP POST."""

    def __init__(self, transport: PeerTransport) -> None:
        self._transport = transport

    async def send_proposal(
        self, peer: PeerInfo, proposal: Proposal
    ) -> NegotiationResponse:
        ok, data = await self._transport.send(
            peer, "/api/peer/negotiate", proposal.to_dict()
        )
        if not ok:
            logger.warning("Negotiate send failed for peer %s", peer.name)
            return NegotiationResponse(
                proposal_id=proposal.proposal_id,
                accept=False,
                reason="Transport failed: peer unreachable",
                responder_peer_id=peer.peer_id,
            )
        return NegotiationResponse.from_dict(data)
