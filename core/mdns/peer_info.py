# core/mdns/peer_info.py
"""PeerInfo dataclass + TXT sanitising.

This module is intentionally free of any ``zeroconf`` import so that unit
tests can exercise it with plain dicts.
"""
from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from hashlib import sha256

from core.mdns.service_types import (
    MAX_TXT_BYTES,
    REQUIRED_TXT_KEYS,
    TXT_KEY_CAPABILITIES,
    TXT_KEY_HAILO_OLLAMA_URL,
    TXT_KEY_LLM_BASE_URL,
    TXT_KEY_LLM_PROVIDER,
    TXT_KEY_NODE_ID,
    TXT_KEY_VERSION,
    TXT_KEY_WEB_PORT,
)

logger = logging.getLogger("core.mdns.peer_info")

_HEX32 = re.compile(r"^[0-9a-f]{32}$")
_OUR_MAJOR_VERSION = "4"


@dataclass(frozen=True)
class PeerInfo:
    """A discovered yu_ai_manager peer on the LAN."""

    node_id: str
    version: str
    llm_base_url: str
    capabilities: tuple[str, ...]
    llm_provider: str
    web_port: int
    hostname: str
    addresses: tuple[str, ...]
    first_seen: str
    last_seen: str
    hailo_ollama_url: str | None = None
    service_kind: str = "yu"
    ollama_advertise_url: str = ""

    @classmethod
    def from_txt(
        cls,
        *,
        txt: Mapping[bytes, bytes],
        hostname: str,
        addresses: tuple[str, ...],
        first_seen: str,
        last_seen: str | None = None,
    ) -> PeerInfo | None:
        """Parse raw zeroconf TXT dict into a PeerInfo, or return None if invalid."""
        decoded = _decode_txt(txt)

        missing = [k for k in REQUIRED_TXT_KEYS if k not in decoded or not decoded[k]]
        if missing:
            logger.debug("[mdns] skip peer: missing keys=%s", missing)
            return None

        node_id = decoded[TXT_KEY_NODE_ID].lower()
        if not _HEX32.match(node_id):
            logger.debug("[mdns] skip peer: invalid node_id=%r", decoded[TXT_KEY_NODE_ID])
            return None

        version = decoded[TXT_KEY_VERSION]
        if version.split(".")[0] != _OUR_MAJOR_VERSION:
            logger.debug("[mdns] skip peer: incompatible major version=%s", version)
            return None

        # llm_base_url is optional (Hailo-only peers advertise without it).
        # If present, it must be http(s)://. If empty/None/missing we store "".
        base_url = decoded.get(TXT_KEY_LLM_BASE_URL, "") or ""
        if base_url and not (
            base_url.startswith("http://") or base_url.startswith("https://")
        ):
            logger.debug("[mdns] skip peer: non-http base_url=%r", base_url)
            return None

        web_port_raw = decoded.get(TXT_KEY_WEB_PORT, "0")
        try:
            web_port = int(web_port_raw)
        except ValueError:
            logger.debug("[mdns] skip peer: invalid web_port=%r", web_port_raw)
            return None

        capabilities_raw = decoded.get(TXT_KEY_CAPABILITIES, "")
        capabilities = tuple(
            c.strip() for c in capabilities_raw.split(",") if c.strip()
        )

        # Optional: hailo_ollama_url. Must be http(s):// to be accepted.
        # Unlike llm_base_url, an invalid value does NOT drop the whole peer.
        hailo_ollama_url_raw = decoded.get(TXT_KEY_HAILO_OLLAMA_URL, "")
        hailo_ollama_url: str | None = None
        if hailo_ollama_url_raw:
            if hailo_ollama_url_raw.startswith(("http://", "https://")):
                hailo_ollama_url = hailo_ollama_url_raw
            else:
                logger.debug(
                    "[mdns] ignoring invalid hailo_ollama_url=%r",
                    hailo_ollama_url_raw,
                )

        return cls(
            node_id=node_id,
            version=version,
            llm_base_url=base_url,
            capabilities=capabilities,
            llm_provider=decoded.get(TXT_KEY_LLM_PROVIDER, ""),
            web_port=web_port,
            hostname=hostname,
            addresses=addresses,
            first_seen=first_seen,
            last_seen=last_seen or first_seen,
            hailo_ollama_url=hailo_ollama_url,
            service_kind="yu",
        )

    @classmethod
    def from_ollama_service(
        cls,
        *,
        service_name: str,
        hostname: str,
        addresses: tuple[str, ...],
        port: int,
        first_seen: str,
        last_seen: str | None = None,
    ) -> PeerInfo | None:
        if port <= 0:
            logger.debug("[mdns] skip bare ollama: invalid port=%r", port)
            return None
        if not addresses:
            logger.debug("[mdns] skip bare ollama: no addresses for %s", service_name)
            return None
        node_seed = f"ollama|{service_name}|{hostname}|{port}"
        node_id = sha256(node_seed.encode("utf-8")).hexdigest()[:32]
        return cls(
            node_id=node_id,
            version="0",
            llm_base_url=f"http://{addresses[0]}:{port}/v1",
            capabilities=("llm",),
            llm_provider="ollama",
            web_port=0,
            hostname=hostname,
            addresses=addresses,
            first_seen=first_seen,
            last_seen=last_seen or first_seen,
            hailo_ollama_url=None,
            service_kind="ollama_mdns",
        )

    def to_txt(self) -> dict[bytes, bytes]:
        """Build a zeroconf-compatible TXT dict for advertising ourselves."""
        txt: dict[bytes, bytes] = {
            TXT_KEY_VERSION.encode(): self.version.encode(),
            TXT_KEY_NODE_ID.encode(): self.node_id.encode(),
            TXT_KEY_LLM_BASE_URL.encode(): self.llm_base_url.encode(),
            TXT_KEY_CAPABILITIES.encode(): ",".join(self.capabilities).encode(),
            TXT_KEY_LLM_PROVIDER.encode(): self.llm_provider.encode(),
            TXT_KEY_WEB_PORT.encode(): str(self.web_port).encode(),
        }
        if self.hailo_ollama_url:
            txt[TXT_KEY_HAILO_OLLAMA_URL.encode()] = self.hailo_ollama_url.encode()
        return txt


def _decode_txt(txt: Mapping[bytes, bytes]) -> dict[str, str]:
    """Decode zeroconf's bytes-keyed TXT dict into a str-keyed one, ignoring junk."""
    out: dict[str, str] = {}
    for k, v in txt.items():
        if v is None:
            continue
        try:
            out[k.decode()] = v.decode()
        except UnicodeDecodeError:
            continue
    return out


def assert_txt_size(txt: Mapping[bytes, bytes]) -> None:
    """Raise ``ValueError`` if the serialised TXT payload exceeds ``MAX_TXT_BYTES``.

    Used for our *own* advertise payload only. Received peer TXTs are never
    checked against this limit — they are silently dropped by ``from_txt`` if
    they contain unparseable data.
    """
    total = 0
    for k, v in txt.items():
        # Each entry in a mDNS TXT record is a length-prefixed "key=value" pair.
        total += 1 + len(k) + 1 + len(v)
    if total > MAX_TXT_BYTES:
        raise ValueError(
            f"TXT payload size={total} exceeds MAX_TXT_BYTES={MAX_TXT_BYTES}"
        )
