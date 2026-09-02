"""AI server data model, read operations, and legacy compatibility.

Defines the ServerEntry dataclass and provides read-only access to
the server list, active server, language settings, and legacy config
migration.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from core.configuration.api import load_config_json
from core.settings_core.secret_store import decrypt

logger = logging.getLogger(__name__)

_MAX_SERVERS = 10

VALID_TYPES = {"claude_api", "openai", "openai_compat", "ollama", "hailo_vlm"}


# ── Data model ──────────────────────────────────────────────────

@dataclass
class ServerEntry:
    id: str
    name: str
    type: str  # claude_api, openai, openai_compat, ollama, hailo_vlm
    priority: int
    enabled: bool
    config: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> ServerEntry:
        config = dict(data.get("config", {}) or {})
        if "api_key" in config:
            config["api_key"] = decrypt(config.get("api_key", ""))
        return cls(
            id=data.get("id", ""),
            name=data.get("name", ""),
            type=data.get("type", ""),
            priority=data.get("priority", 50),
            enabled=data.get("enabled", True),
            config=config,
        )


# ── Read operations ──────────────────────────────────────────────

def get_all_servers(config: dict | None = None) -> list[ServerEntry]:
    """Return registered servers sorted by priority (ascending).

    Falls back to legacy ``ai_analysis`` conversion when ``ai_servers``
    is not configured.
    """
    if config is None:
        config = load_config_json(None)

    raw = config.get("ai_servers")
    if isinstance(raw, list) and raw:
        servers = [ServerEntry.from_dict(s) for s in raw]
        servers.sort(key=lambda s: s.priority)
        return servers

    # Legacy compat: generate 1 entry from ai_analysis
    legacy = _legacy_to_entry(config.get("ai_analysis", {}))
    return [legacy] if legacy else []


def get_active_server_id(config: dict | None = None) -> str | None:
    if config is None:
        config = load_config_json(None)
    return config.get("ai_servers_active")


def get_language(config: dict | None = None) -> str:
    if config is None:
        config = load_config_json(None)
    return (
        config.get("ai_servers_language")
        or config.get("ai_analysis", {}).get("language", "ja")
    )


def is_fallback_local_only(config: dict | None = None) -> bool:
    if config is None:
        config = load_config_json(None)
    v = config.get("ai_servers_fallback_local_only")
    if v is not None:
        return bool(v)
    return bool(config.get("ai_analysis", {}).get("fallback_local_only", False))


def has_servers(config: dict | None = None) -> bool:
    """Check whether ai_servers is explicitly configured (for legacy mode detection)."""
    if config is None:
        config = load_config_json(None)
    raw = config.get("ai_servers")
    return isinstance(raw, list) and len(raw) > 0


# ── Legacy compatibility ──────────────────────────────────────────

def _legacy_to_entry(ai_config: dict) -> ServerEntry | None:
    """Generate a single ServerEntry from legacy ai_analysis config."""
    if not ai_config:
        return None

    engine_type = ai_config.get("engine", "claude_api")
    language = ai_config.get("language", "ja")

    cfg: dict[str, Any] = {}
    if engine_type == "ollama":
        cfg = {
            "base_url": ai_config.get("ollama_url", "http://localhost:11434"),
            "model": ai_config.get("ollama_model", "llava:latest"),
        }
        name = f'Ollama ({cfg["model"]})'
    elif engine_type == "openai_compat":
        cfg = {
            "base_url": ai_config.get("openai_compat_url", ""),
            "api_key": decrypt(ai_config.get("openai_compat_api_key", "")),
            "model": ai_config.get("openai_compat_model", ""),
        }
        name = f'OpenAI Compatible ({cfg["model"] or "default"})'
    elif engine_type == "openai":
        cfg = {
            "api_key": decrypt(ai_config.get("openai_api_key", "")),
            "model": ai_config.get("openai_model", "gpt-4o-mini"),
        }
        name = f'OpenAI ({cfg["model"]})'
    elif engine_type == "hailo_vlm":
        cfg = {
            "model_name": ai_config.get("hailo_vlm_model", "qwen2-vl-2b-instruct"),
        }
        name = f'Hailo VLM ({cfg["model_name"]})'
    else:  # claude_api
        cfg = {
            "api_key": decrypt(ai_config.get("api_key", "")),
            "model": ai_config.get("model", "claude-sonnet-4-6"),
        }
        name = f'Claude ({cfg["model"]})'

    cfg["language"] = language

    return ServerEntry(
        id="legacy-default",
        name=name,
        type=engine_type,
        priority=10,
        enabled=True,
        config=cfg,
    )


# ── Validation and slug helpers ──────────────────────────────────

def _validate_and_build(data: dict, existing: list) -> ServerEntry | dict:
    """Validate input data and return a ServerEntry, or error dict on failure."""
    name = data.get("name", "").strip()
    if not name:
        return {"success": False, "error": "Server name is required"}

    stype = data.get("type", "")
    if stype not in VALID_TYPES:
        return {"success": False, "error": f"Invalid type: {stype}. Must be one of {VALID_TYPES}"}

    sid = data.get("id") or _slugify(name)
    if any(s.get("id") == sid for s in existing):
        # Add suffix on collision
        base = sid
        for i in range(2, 100):
            sid = f"{base}-{i}"
            if not any(s.get("id") == sid for s in existing):
                break

    return ServerEntry(
        id=sid,
        name=name,
        type=stype,
        priority=data.get("priority", (len(existing) + 1) * 10),
        enabled=data.get("enabled", True),
        config=data.get("config", {}),
    )


def _slugify(name: str) -> str:
    """Generate a URL-safe slug from a name."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s[:32] or "server"
