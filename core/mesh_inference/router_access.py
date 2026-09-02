"""Bridge helper for InferenceRouter strategy injection.

InferenceRouter lives in extensions/ and now exposes public ``strategy``
property and ``get_available_peers()`` method.  This module is the ONLY
place in core/mesh_inference/ that interacts with the router — keeping the
cross-layer coupling contained.

Rationale captured in the spec:
docs/superpowers/specs/2026-04-09-mesh-inference-per-peer-toggle-design.md
"""
from __future__ import annotations

from .state import MeshInferenceState
from .strategy import DisableAwareStrategy


def install_strategy(router: object, state: MeshInferenceState) -> None:
    """Inject DisableAwareStrategy into router.strategy (idempotent)."""
    if router is None:
        return
    current = getattr(router, "strategy", None)
    if current is None:
        current = getattr(router, "_strategy", None)
    if isinstance(current, DisableAwareStrategy):
        return  # already installed
    new_strategy = DisableAwareStrategy(state)
    if hasattr(type(router), "strategy") or hasattr(router, "strategy"):
        router.strategy = new_strategy  # type: ignore[attr-defined]
    else:
        router._strategy = new_strategy  # type: ignore[attr-defined]
