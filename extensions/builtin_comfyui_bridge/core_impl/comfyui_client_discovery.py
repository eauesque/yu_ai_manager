"""Discovery helpers for ComfyUIClient."""

from __future__ import annotations

import logging
from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPError

logger = logging.getLogger(__name__)


def test_connection(http) -> dict[str, Any]:
    try:
        stats = http.get("/system_stats", timeout=10)
        system = stats.get("system", {})
        return {
            "ok": True,
            "version": system.get("comfyui_version", "unknown"),
            "device": system.get("device_name", "unknown"),
            "vram_total": system.get("vram_total", 0),
            "vram_free": system.get("vram_free", 0),
        }
    except BridgeConnectionError as exc:
        return {"ok": False, "error": str(exc)}
    except BridgeHTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.status}"}


def list_required_enum(http, node_type: str, field: str) -> list[str]:
    try:
        data = http.get(f"/object_info/{node_type}")
        inputs = data.get(node_type, {}).get("input", {}).get("required", {})
        entry = inputs.get(field, [[]])
        if not isinstance(entry, list) or not entry:
            return []
        first = entry[0]
        # New ComfyUI format: ["COMBO", {"options": [...]}]
        if first == "COMBO" and len(entry) > 1 and isinstance(entry[1], dict):
            return list(entry[1].get("options", []))
        # Legacy format: [["model1", "model2"], {...}]
        if isinstance(first, list):
            return list(first)
        return []
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list %s.%s failed: %s", node_type, field, exc)
        return []


def has_node(http, node_type: str) -> bool:
    """Return True if ``node_type`` is registered in ComfyUI's /object_info."""
    try:
        data = http.get(f"/object_info/{node_type}")
        return isinstance(data, dict) and node_type in data
    except (BridgeConnectionError, BridgeHTTPError):
        return False


def list_loras(http) -> list[str]:
    for node_name in ("LoraLoader", "LoraLoaderModelOnly"):
        try:
            data = http.get(f"/object_info/{node_name}")
            inputs = data.get(node_name, {}).get("input", {}).get("required", {})
            names = inputs.get("lora_name", [[]])[0]
            if names:
                return list(names)
        except (BridgeConnectionError, BridgeHTTPError):
            continue
    logger.warning("list_loras: no LoRA loader node found")
    return []


def list_embeddings(http) -> list[str]:
    try:
        data = http.get("/api/embeddings")
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            return list(data.keys())
        return []
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_embeddings failed: %s", exc)
        return []


def list_custom_nodes(http) -> list[dict[str, Any]]:
    try:
        data = http.get("/object_info")
        if not isinstance(data, dict):
            return []
        results: list[dict[str, Any]] = []
        for name, info in data.items():
            if not isinstance(info, dict):
                continue
            results.append(
                {
                    "name": name,
                    "category": info.get("category", ""),
                    "description": info.get("description", ""),
                }
            )
        return results
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_custom_nodes failed: %s", exc)
        return []
