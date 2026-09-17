"""Bootstrap helpers for LAN Cowork manager setup."""

from __future__ import annotations

import logging
import socket

logger = logging.getLogger(__name__)


def get_local_ip() -> str:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.connect(("8.8.8.8", 80))
        ip = sock.getsockname()[0]
        sock.close()
        return ip
    except OSError:
        return "127.0.0.1"


def get_version() -> str:
    try:
        from pathlib import Path
        return (Path(__file__).resolve().parent.parent.parent / "VERSION").read_text().strip()
    except Exception:
        return "unknown"


def detect_bridges() -> list:
    bridges = []
    try:
        from core.extensions_core.lifecycle.extensions_admin import get_extension_config_value
        for name, key in [
            ("builtin-nai-bridge", "nai"),
            ("builtin-sd-webui-bridge", "sd-webui"),
            ("builtin-comfyui-bridge", "comfyui"),
        ]:
            if get_extension_config_value(name, "enabled", False):
                bridges.append(key)
    except Exception:
        # An empty list reads as "no bridges enabled", not "could not check".
        logger.warning("bridge enablement could not be read", exc_info=True)
    return bridges


def load_or_create_identity() -> tuple[str, bytes, bytes, bytes]:
    """Return (peer_id, ed25519_seed, ed25519_pubkey, x25519_pubkey)."""
    try:
        from core.services_core.lan_cowork_identity_service import (
            load_or_create_identity as _load,
        )

        return _load()
    except Exception as exc:
        logger.warning("load crypto identity from DB failed: %s", exc)
        raise
