"""Facade for mesh inference access across extensions.

Provides a stable import path for the InferenceRouter that lives in the
``builtin_lan_cowork`` directory. Other extensions and core modules import from
here instead of directly referencing the extension, which would create
circular dependencies.

v4.67.0: set_router() additionally loads the persisted disabled overlay
and injects DisableAwareStrategy so dispatch paths automatically skip
user-disabled peer/inference_type pairs.

Usage:
    from core.mesh_inference import get_router, has_mesh

    router = get_router()
    if router is not None:
        result = await router.dispatch_inference(...)
"""
from __future__ import annotations

import logging
from typing import Optional

from .router_access import install_strategy
from .state import get_state

logger = logging.getLogger(__name__)

_router: object | None = None
_persistence_loaded: bool = False


def _load_persistence_once() -> None:
    global _persistence_loaded
    if _persistence_loaded:
        return
    try:
        get_state().load_persisted()
    except Exception as exc:
        logger.warning("[mesh_inference] failed to load state: %s", exc)
    _persistence_loaded = True


def set_router(router: object | None) -> None:
    """Register or clear the active InferenceRouter.

    Called by CoworkManager at startup (with the router instance) and at
    shutdown (with None). Not thread-safe — expected to be called from the
    main asyncio thread.
    """
    global _router
    _router = router
    if router is not None:
        _load_persistence_once()
        install_strategy(router, get_state())


def get_router() -> object | None:
    """Return the active InferenceRouter, or None if mesh is not available."""
    return _router


def has_mesh() -> bool:
    """Return True if a mesh InferenceRouter is currently registered."""
    return _router is not None


def _reset() -> None:
    """Reset module state. For use in tests only."""
    global _router, _persistence_loaded
    _router = None
    _persistence_loaded = False
