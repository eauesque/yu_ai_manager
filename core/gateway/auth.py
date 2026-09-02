from __future__ import annotations

import base64
import hashlib
import logging
import secrets
from dataclasses import dataclass

from core.gateway.scopes import Scope
from core.settings_core.secret_store import decrypt

logger = logging.getLogger(__name__)

_MAX_TOKEN_BYTES = 256
_LOOPBACK_ADDRS = {"127.0.0.1", "::1"}


def extract_bearer(auth_header: str | None, x_api_key: str | None = None) -> str | None:
    """Extract API key from Authorization header (Bearer or Basic) or x-api-key header.

    Basic auth: password field is used as the API key (username is ignored).
    This allows SD/ComfyUI clients that support HTTP Basic auth to authenticate
    without needing custom header support.
    """
    h = auth_header or ""
    if h.startswith("Bearer "):
        return h[len("Bearer "):] or None
    if h.startswith("Basic "):
        try:
            decoded = base64.b64decode(h[len("Basic "):]).decode("utf-8")
            _, _, password = decoded.partition(":")
            return password or None
        except Exception:
            return None
    return x_api_key or None


@dataclass
class AuthResult:
    key_id: str
    scopes: set[str]
    allowed_models: list[str] | None  # None = allow all


class GatewayAuth:
    def __init__(self) -> None:
        self._allow_loopback_bypass: bool = True
        # (key_id, sha256_digest, scopes, allowed_models)
        self._keys: list[tuple[str, bytes, set[str], list[str] | None]] = []
        self._secret_enc: dict[str, str] = {}

    def load_config(self, cfg: dict) -> None:
        self._allow_loopback_bypass = cfg.get("allow_loopback_bypass", True)
        if cfg.get("trusted_peer_bypass"):
            logger.warning(
                "[gateway] trusted_peer_bypass not supported in Phase 1; forcing false"
            )
        loaded = []
        enc_map: dict[str, str] = {}
        for entry in cfg.get("api_keys", []):
            key_id = entry["id"]
            try:
                plain = decrypt(entry["secret_enc"])
            except Exception as exc:
                logger.warning(
                    "[gateway] failed to decrypt key %r: %s; skipping. "
                    "This secret was encrypted with a lost key and cannot be recovered; "
                    "recreate the API key/secret.",
                    key_id,
                    exc,
                )
                continue
            if not plain:
                logger.warning(
                    "[gateway] failed to decrypt key %r; skipping. "
                    "This secret was encrypted with a lost key and cannot be recovered; "
                    "recreate the API key/secret.",
                    key_id,
                )
                continue
            digest = hashlib.sha256(plain.encode()).digest()
            scopes: set[str] = set(entry.get("scopes", []))
            models: list[str] | None = entry.get("allowed_models")
            loaded.append((key_id, digest, scopes, models))
            enc_map[key_id] = entry["secret_enc"]
        self._keys = loaded
        self._secret_enc = enc_map
        logger.info("[gateway] loaded %d API keys", len(self._keys))

    def check_bearer(self, token: str | None, remote_addr: str) -> AuthResult | None:
        if token is None or len(token.encode()) > _MAX_TOKEN_BYTES:
            return None
        token_digest = hashlib.sha256(token.encode()).digest()
        matched_idx: int | None = None
        for i, (_, expected, _, _) in enumerate(self._keys):
            if secrets.compare_digest(token_digest, expected):
                matched_idx = i
        if matched_idx is None:
            return None
        kid, _, scopes, models = self._keys[matched_idx]
        return AuthResult(key_id=kid, scopes=scopes, allowed_models=models)

    def check_request(
        self,
        bearer: str | None,
        remote_addr: str,
        *,
        allow_loopback_bypass: bool = False,
    ) -> AuthResult | None:
        if (
            allow_loopback_bypass
            and self._allow_loopback_bypass
            and remote_addr in _LOOPBACK_ADDRS
        ):
            return AuthResult(key_id="loopback", scopes={Scope.WILDCARD}, allowed_models=None)
        return self.check_bearer(bearer, remote_addr)

    @staticmethod
    def has_scope(result: AuthResult, needed: Scope) -> bool:
        return Scope.WILDCARD in result.scopes or str(needed) in result.scopes

    @staticmethod
    def model_allowed(result: AuthResult, model: str) -> bool:
        return result.allowed_models is None or model in result.allowed_models

    def add_key(self, key_id: str, secret_enc: str, scopes: list[str],
                allowed_models: list[str] | None) -> None:
        plain = decrypt(secret_enc)
        digest = hashlib.sha256(plain.encode()).digest()
        self._keys.append((key_id, digest, set(scopes), allowed_models))
        self._secret_enc[key_id] = secret_enc

    def add_key_by_digest(self, key_id: str, digest: bytes, scopes: list[str],
                           allowed_models: list[str] | None) -> None:
        """Register a key directly by SHA-256 digest (no encrypt/decrypt)."""
        self._keys = [t for t in self._keys if t[0] != key_id]
        self._keys.append((key_id, digest, set(scopes), allowed_models))

    def remove_key(self, key_id: str) -> bool:
        before = len(self._keys)
        self._keys = [t for t in self._keys if t[0] != key_id]
        self._secret_enc.pop(key_id, None)
        return len(self._keys) < before

    def patch_key(self, key_id: str, scopes: list[str] | None,
                  allowed_models: list[str] | None) -> bool:
        for i, (k, d, s, m) in enumerate(self._keys):
            if k == key_id:
                self._keys[i] = (k, d,
                                  set(scopes) if scopes is not None else s,
                                  allowed_models if allowed_models is not None else m)
                return True
        return False

    def list_keys(self) -> list[dict]:
        return [{"id": k, "scopes": list(s), "allowed_models": m}
                for k, _, s, m in self._keys]

    def iter_persistable_keys(self):
        """Yield key entries that can be written back to gateway config."""
        for key_id, _, scopes, models in self._keys:
            if key_id == "loopback":
                continue
            secret_enc = self._secret_enc.get(key_id)
            if not secret_enc:
                continue
            yield {
                "id": key_id,
                "secret_enc": secret_enc,
                "scopes": list(scopes),
                "allowed_models": models,
            }

    def has_key(self, key_id: str) -> bool:
        """Return True if a key with key_id exists."""
        return any(k == key_id for k, *_ in self._keys)

    def wildcard_key_ids(self) -> list[str]:
        """Return list of key IDs that have Scope.WILDCARD."""
        return [k for k, _, s, _ in self._keys if Scope.WILDCARD in s]

    def get_key_scopes(self, key_id: str) -> list[str] | None:
        """Return scopes for key_id, or None if not found."""
        for k, _, s, _ in self._keys:
            if k == key_id:
                return list(s)
        return None

    def get_bearer_for_scope(self, scope: str) -> str | None:
        """Return decrypted bearer token for first key with the given scope (or wildcard).

        Re-decrypts from _secret_enc on each call — plaintext is not cached.
        Returns None if no matching key exists or decryption fails.
        """
        for key_id, _, scopes, _ in self._keys:
            if Scope.WILDCARD in scopes or scope in scopes:
                enc = self._secret_enc.get(key_id)
                if enc:
                    try:
                        return decrypt(enc)
                    except Exception as exc:
                        # Only the key id and the exception *type*: a decrypt
                        # failure must not put ciphertext or plaintext into the
                        # log, and the type is what tells an operator whether
                        # the key store is missing or the key is wrong.
                        logger.warning(
                            "gateway key %s: decryption failed (%s), skipping this key",
                            key_id,
                            type(exc).__name__,
                        )
                        continue
        return None


_auth: GatewayAuth = GatewayAuth()


def get_auth() -> GatewayAuth:
    return _auth


def load_config_from_app_config(app_config: dict) -> dict:
    """Extract gateway.auth config, migrating legacy llm_router.auth if needed."""
    if "gateway" in app_config:
        return app_config["gateway"].get("auth", {})

    old = app_config.get("llm_router", {}).get("auth", {})
    if not old:
        return {"mode": "loopback", "allow_loopback_bypass": True, "api_keys": []}

    mode = old.get("mode", "loopback")
    logger.warning(
        "[gateway] migrated legacy auth (mode=%s); please reconfigure via "
        "gateway.auth schema and rotate keys.", mode,
    )
    if mode in ("loopback", "none"):
        return {"mode": "api_key", "allow_loopback_bypass": True, "api_keys": []}

    raw_key = old.get("api_key", "")
    from core.settings_core.secret_store import encrypt, is_encrypted
    plain = decrypt(raw_key) if is_encrypted(raw_key) else raw_key
    return {
        "mode": "api_key",
        "allow_loopback_bypass": old.get("allow_loopback_bypass", True),
        "api_keys": [{"id": "legacy", "secret_enc": encrypt(plain),
                      "scopes": ["*"], "allowed_models": None}],
    }
