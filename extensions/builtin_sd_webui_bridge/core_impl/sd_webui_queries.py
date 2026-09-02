"""Query helpers for the classic SD WebUI API client."""

from __future__ import annotations

from core.bridge_core import BridgeConnectionError, BridgeHTTPError


def test_connection(http) -> dict:
    """Test connectivity and return basic info."""
    try:
        opts = http.get("/sdapi/v1/options", timeout=10)
        return {
            "ok": True,
            "model": opts.get("sd_model_checkpoint", "unknown"),
            "version": opts.get("_version", ""),
        }
    except BridgeConnectionError as exc:
        return {"ok": False, "error": str(exc)}
    except BridgeHTTPError as exc:
        return {"ok": False, "error": f"HTTP {exc.status}"}


def list_names(http, endpoint: str, logger, key: str) -> list[str]:
    """Return a list of names from a simple array response."""
    try:
        data = http.get(endpoint)
        return [item.get(key, "") for item in data if isinstance(item, dict)]
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("%s failed: %s", endpoint, exc)
        return []


def list_loras(http, logger) -> list[dict]:
    try:
        data = http.get("/sdapi/v1/loras")
        if not isinstance(data, list):
            return []
        return [
            {"name": item.get("name", ""), "alias": item.get("alias", ""), "path": item.get("path", "")}
            for item in data
            if isinstance(item, dict)
        ]
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_loras failed: %s", exc)
        return []


def list_embeddings(http, logger) -> dict:
    try:
        data = http.get("/sdapi/v1/embeddings")
        if not isinstance(data, dict):
            return {"loaded": [], "skipped": []}
        loaded = list(data.get("loaded", {}).keys()) if isinstance(data.get("loaded"), dict) else []
        skipped = list(data.get("skipped", {}).keys()) if isinstance(data.get("skipped"), dict) else []
        return {"loaded": loaded, "skipped": skipped}
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_embeddings failed: %s", exc)
        return {"loaded": [], "skipped": []}


def list_scripts(http, logger) -> dict:
    try:
        data = http.get("/sdapi/v1/scripts")
        if not isinstance(data, dict):
            return {"txt2img": [], "img2img": []}
        return {"txt2img": list(data.get("txt2img", [])), "img2img": list(data.get("img2img", []))}
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_scripts failed: %s", exc)
        return {"txt2img": [], "img2img": []}


def list_script_info(http, logger) -> list[dict]:
    try:
        data = http.get("/sdapi/v1/script-info")
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_script_info failed: %s", exc)
        return []


def list_extensions(http, logger) -> list[dict]:
    try:
        data = http.get("/sdapi/v1/extensions")
        if not isinstance(data, list):
            return []
        return [
            {"name": item.get("name", ""), "enabled": item.get("enabled", False), "version": item.get("version", "")}
            for item in data
            if isinstance(item, dict)
        ]
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("list_extensions failed: %s", exc)
        return []


def get_progress(http) -> dict:
    try:
        return http.get("/sdapi/v1/progress", timeout=5)
    except (BridgeConnectionError, BridgeHTTPError):
        return {"progress": 0, "eta_relative": 0}


def interrupt(http, logger) -> bool:
    try:
        http.post_json("/sdapi/v1/interrupt", {}, timeout=5)
        return True
    except (BridgeConnectionError, BridgeHTTPError) as exc:
        logger.warning("interrupt failed: %s", exc)
        return False
