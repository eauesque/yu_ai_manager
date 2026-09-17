# core/mdns/service_types.py
"""Constants shared by advertiser, browser and peer_info.

Keep this file dependency-free — importing it must not pull in ``zeroconf``
or any other optional package.
"""
from __future__ import annotations

YU_SERVICE_TYPE: str = "_yu-ai._tcp.local."
OLLAMA_SERVICE_TYPE: str = "_ollama._tcp.local."
BROWSE_SERVICE_TYPES: tuple[str, ...] = (
    YU_SERVICE_TYPE,
    OLLAMA_SERVICE_TYPE,
)
SERVICE_TYPE: str = YU_SERVICE_TYPE
SERVICE_VERSION: str = "1"

# TXT record keys. Values are str when constructing, bytes when zeroconf hands
# them back. peer_info handles both.
TXT_KEY_VERSION = "version"
TXT_KEY_NODE_ID = "node_id"
TXT_KEY_LLM_BASE_URL = "llm_base_url"
TXT_KEY_CAPABILITIES = "capabilities"
TXT_KEY_LLM_PROVIDER = "llm_provider"
TXT_KEY_WEB_PORT = "web_port"
TXT_KEY_HAILO_OLLAMA_URL = "hailo_ollama_url"  # optional, only advertised if a local hailo-ollama is detected

REQUIRED_TXT_KEYS: tuple[str, ...] = (
    TXT_KEY_VERSION,
    TXT_KEY_NODE_ID,
)
# NOTE: llm_base_url is intentionally NOT required. A Hailo-only peer
# (Pi5 with yu's hailo-genai extension but no local Ollama) legitimately
# advertises an empty llm_base_url; the hailo capability alone is enough
# reason to track the peer. ``from_txt`` accepts an empty value and
# ``_apply_peer_to_catalog`` only registers the base Ollama backend when
# llm_base_url is present.

# Self-advertise limit. zeroconf's hard ceiling is ~1300 bytes; leave headroom.
MAX_TXT_BYTES: int = 1200
