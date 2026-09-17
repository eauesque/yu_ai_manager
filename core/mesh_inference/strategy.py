"""DisableAwareStrategy — extends BatchInferenceStrategy with a filter.

Wraps the project-side MeshInferenceState disabled overlay so any peer that
has been explicitly disabled for a given inference_type is skipped during
router work-stealing. Inherits (not composes) the base strategy so it slots
into InferenceRouter._strategy without any router-side changes.
"""
from __future__ import annotations

import sys
from importlib import import_module
from pathlib import Path

from .state import MeshInferenceState

# Extension is not an installed package; its path must be on sys.path for
# import. lan_cowork_ext does this at startup for its own modules; we repeat
# the same trick so strategy.py can import cleanly from either production
# (after extension init) or tests.
_EXT = Path(__file__).resolve().parent.parent.parent / "extensions" / "builtin_lan_cowork"
if _EXT.exists() and str(_EXT) not in sys.path:
    sys.path.insert(0, str(_EXT))

try:
    from core_impl.inference.router import BatchInferenceStrategy  # type: ignore
    from core_impl.models import PeerInfo  # type: ignore  # noqa: F401
except ModuleNotFoundError:
    # Fallback: tests may have polluted sys.modules['core_impl'] with a
    # different extension's core_impl. Import through the concrete extension
    # package to avoid that collision.
    BatchInferenceStrategy = import_module(
        "extensions.builtin_lan_cowork.core_impl.inference.router"
    ).BatchInferenceStrategy
    PeerInfo = import_module(
        "extensions.builtin_lan_cowork.core_impl.models"
    ).PeerInfo  # noqa: F401


class DisableAwareStrategy(BatchInferenceStrategy):
    """Filter that removes peers whose (peer_id, inference_type) is disabled."""

    def __init__(self, state: MeshInferenceState) -> None:
        super().__init__()
        self._state = state

    def _eligible_peers(
        self,
        inference_type: str,
        peers,
    ):
        base = super()._eligible_peers(inference_type, peers)
        return [
            p for p in base
            if not self._state.is_disabled(p.peer_id, inference_type)
        ]
