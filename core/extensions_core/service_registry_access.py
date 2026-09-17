"""Sandbox/trust helpers for ServiceRegistry access."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

logger = logging.getLogger(__name__)


def is_trusted_caller(caller: str) -> bool:
    """Check whether the caller is L0 (TRUSTED = builtin)."""
    if caller.startswith("builtin-"):
        return True

    try:
        from core.extensions_core.token_mgmt.capability_token import get_enforcer

        enforcer = get_enforcer()
        tokens = enforcer.get_tokens(caller)
        if not tokens:
            return _check_manifest_trusted(caller)
    except Exception:
        # Falling through to `return False` is right -- fail closed -- but a
        # broken enforcer would otherwise make every caller untrusted in silence.
        logger.warning("trust check for %s did not complete", caller, exc_info=True)

    return False


def apply_sandbox_hook(
    name: str,
    service: Any,
    caller: str,
    hook: Callable | None,
) -> Any:
    """Apply sandboxing and access tracking for a service request."""
    if is_trusted_caller(caller):
        return service

    try:
        from core.extensions_core.token_mgmt.token_revocation import (
            get_revocation_tracker,
        )

        get_revocation_tracker().record_access(caller)
    except Exception:
        # This is the access trail for a caller we do NOT trust.
        logger.warning("access by %s was not recorded", caller, exc_info=True)

    if hook is None:
        return service

    try:
        return hook(service, caller)
    except Exception as exc:
        logger.error(
            "Sandbox proxy error for '%s' (caller=%s): %s",
            name,
            caller,
            exc,
        )
        return service


def _check_manifest_trusted(caller: str) -> bool:
    """Check the TrustLevel from the manifest."""
    try:
        from core.extensions_core.lifecycle.runtime import get_extension_manager

        mgr = get_extension_manager()
        manifest = mgr.manifests.get(caller)
        if manifest and str(manifest.trust_level) == "trusted":  # StrEnum.str() returns value (e.g. "trusted")
            return True
    except Exception:
        # Fail closed, but say why: an unreadable manifest and an untrusted
        # extension are the same answer with very different causes.
        logger.warning("manifest trust level for %s was unreadable", caller, exc_info=True)
    return False
