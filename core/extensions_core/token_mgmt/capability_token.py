"""Capability Token + Runtime Enforcer (separation-of-powers Phase B: executive).

Manages capability tokens issued to extensions and controls
resource access via ServiceRegistry.

- Tokens are signed with a randomly generated HMAC key per startup
- In-memory management only (no persistence needed)
- L0 (TRUSTED) is fully bypassed
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import time
import uuid
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# HMAC signing key generated at startup
_HMAC_KEY: bytes = os.urandom(32)

# Token TTL (seconds): 24 hours
_TOKEN_TTL: float = 86400.0


@dataclass(frozen=True)
class CapabilityToken:
    """Permission token issued to an extension."""

    token_id: str
    ext_name: str
    permission: str
    scope: dict
    issued_at: float
    expires_at: float
    signature: str

    def is_expired(self) -> bool:
        return time.time() > self.expires_at


def _sign_token(token_id: str, ext_name: str, permission: str) -> str:
    """Sign a token with HMAC-SHA256."""
    msg = f"{token_id}:{ext_name}:{permission}".encode()
    return hmac.new(_HMAC_KEY, msg, hashlib.sha256).hexdigest()


def _verify_signature(token: CapabilityToken) -> bool:
    """Validate a token's HMAC signature."""
    expected = _sign_token(token.token_id, token.ext_name, token.permission)
    return hmac.compare_digest(token.signature, expected)


class RuntimeEnforcer:
    """Manages capability token issuance, verification, and revocation (executive).

    Singleton pattern. Retrieve the instance via get_enforcer().
    """

    def __init__(self) -> None:
        # ext_name -> {permission -> CapabilityToken}
        self._token_store: dict[str, dict[str, CapabilityToken]] = {}

    def issue_tokens(
        self,
        ext_name: str,
        permissions: list[str],
        scope_map: dict[str, dict] | None = None,
    ) -> dict[str, CapabilityToken]:
        """Issue capability tokens to an extension.

        Args:
            ext_name: Extension name
            permissions: List of approved permissions
            scope_map: Dict of permission name -> restriction parameters (defaults to empty dict)

        Returns:
            Dict of permission -> CapabilityToken
        """
        now = time.time()
        tokens: dict[str, CapabilityToken] = {}
        scope_map = scope_map or {}

        for perm in permissions:
            token_id = str(uuid.uuid4())
            sig = _sign_token(token_id, ext_name, perm)
            token = CapabilityToken(
                token_id=token_id,
                ext_name=ext_name,
                permission=perm,
                scope=scope_map.get(perm, {}),
                issued_at=now,
                expires_at=now + _TOKEN_TTL,
                signature=sig,
            )
            tokens[perm] = token

        self._token_store[ext_name] = tokens
        logger.info(
            "RuntimeEnforcer: %s に %d 件の権限を発行",
            ext_name,
            len(tokens),
        )
        return tokens

    def verify_token(self, token: CapabilityToken) -> bool:
        """Validate whether a token is valid.

        - HMAC signature match
        - Not expired
        - Exists in token_store
        """
        if token.is_expired():
            logger.debug("capability expired: %s/%s", token.ext_name, token.permission)
            return False

        if not _verify_signature(token):
            logger.warning(
                "capability signature mismatch: %s/%s",
                token.ext_name,
                token.permission,
            )
            return False

        ext_tokens = self._token_store.get(token.ext_name)
        if ext_tokens is None:
            return False
        stored = ext_tokens.get(token.permission)
        return not (stored is None or stored.token_id != token.token_id)

    def revoke_tokens(self, ext_name: str, reason: str = "manual") -> None:
        """Revoke all tokens for an extension.

        Args:
            ext_name: Extension name
            reason: Revocation reason ("manual", "file_tampering", "denial_threshold", "inactivity")
        """
        removed = self._token_store.pop(ext_name, None)
        if removed:
            logger.info(
                "RuntimeEnforcer: %s の %d 件の権限を失効 (reason=%s)",
                ext_name,
                len(removed),
                reason,
            )
            # Notify via event_bus
            self._emit_revocation_event(ext_name, reason)

    @staticmethod
    def _emit_revocation_event(ext_name: str, reason: str) -> None:
        """Fire a token revocation event to event_bus."""
        try:
            from core.extensions_core.service_registry import ServiceRegistry
            event_bus = ServiceRegistry.get("event_bus")
            if event_bus and hasattr(event_bus, "emit"):
                event_bus.emit("sandbox.token_revoked", {
                    "ext_name": ext_name,
                    "reason": reason,
                })
        except Exception:
            # Revocation stands; the event is what tells everything else.
            logger.warning(
                "revocation event for %s was not emitted", ext_name, exc_info=True
            )

    def get_token(self, ext_name: str, permission: str) -> CapabilityToken | None:
        """Retrieve the token for a specific extension and permission."""
        ext_tokens = self._token_store.get(ext_name)
        if ext_tokens is None:
            return None
        return ext_tokens.get(permission)

    def get_tokens(self, ext_name: str) -> dict[str, CapabilityToken]:
        """Retrieve all tokens for an extension."""
        return dict(self._token_store.get(ext_name, {}))

    def has_permission(self, ext_name: str, permission: str) -> bool:
        """Check whether an extension holds a valid token for the specified permission."""
        token = self.get_token(ext_name, permission)
        if token is None:
            return False
        return self.verify_token(token)

    def token_summary(self, ext_name: str) -> list:
        """Return token summary info (for API use, signature excluded)."""
        ext_tokens = self._token_store.get(ext_name, {})
        result = []
        for perm, tok in ext_tokens.items():
            result.append({
                "permission": perm,
                "issued_at": tok.issued_at,
                "expires_at": tok.expires_at,
                "expired": tok.is_expired(),
            })
        return result


# --- Singleton ---

_enforcer: RuntimeEnforcer | None = None


def get_enforcer() -> RuntimeEnforcer:
    """Return the singleton RuntimeEnforcer instance."""
    global _enforcer
    if _enforcer is None:
        _enforcer = RuntimeEnforcer()
    return _enforcer


def reset_enforcer() -> None:
    """For testing: reset the singleton."""
    global _enforcer
    _enforcer = None
