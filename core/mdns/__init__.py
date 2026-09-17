# core/mdns/__init__.py
"""mDNS / zeroconf integration for yu_ai_manager.

See ``docs/superpowers/specs/2026-04-08-mdns-phase-b-design.md`` for the full
design. This module exposes the public facade only; internal threading and
zeroconf-specific code lives in :mod:`core.mdns.worker` and friends.
"""
from core.mdns.event_dispatcher import SubscriptionHandle
from core.mdns.peer_info import PeerInfo
from core.mdns.service import MdnsConfig, MdnsService

__all__ = ["MdnsConfig", "MdnsService", "PeerInfo", "SubscriptionHandle"]
