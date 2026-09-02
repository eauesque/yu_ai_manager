import logging
import time
from typing import Any

from core.bridge_core import BridgeConnectionError, BridgeHTTPError

logger = logging.getLogger(__name__)

# TTL for /info and /config caches.  Forge restarts or schema changes are
# picked up after this many seconds without requiring a bridge client reset.
_CACHE_TTL_SECONDS = 300


def get_info(client) -> dict:
    now = time.monotonic()
    if client._info_cache is None or (now - getattr(client, "_info_cache_ts", 0)) > _CACHE_TTL_SECONDS:
        try:
            client._info_cache = client._http.get("/info", timeout=15)
            client._info_cache_ts = now
        except (BridgeConnectionError, BridgeHTTPError) as exc:
            logger.warning("Failed to fetch /info: %s", exc)
            client._info_cache = {}
    return client._info_cache


def get_config(client) -> dict:
    now = time.monotonic()
    if client._config_cache is None or (now - getattr(client, "_config_cache_ts", 0)) > _CACHE_TTL_SECONDS:
        try:
            client._config_cache = client._http.get("/config", timeout=15)
            client._config_cache_ts = now
            # Schema changed: invalidate the txt2img arg cache so it is rebuilt.
            client._txt2img_defaults = None
            client._txt2img_label_map = None
        except (BridgeConnectionError, BridgeHTTPError) as exc:
            logger.warning("Failed to fetch /config: %s", exc)
            client._config_cache = {}
    return client._config_cache


def ensure_txt2img_schema(client) -> None:
    if client._txt2img_defaults is not None:
        return
    config = get_config(client)
    deps = config.get("dependencies", [])
    components = {c["id"]: c for c in config.get("components", []) if "id" in c}
    txt2img_dep = next((dep for dep in deps if dep.get("api_name") == "txt2img"), None)
    if txt2img_dep is None:
        logger.warning("txt2img dependency not found in /config")
        client._txt2img_defaults = []
        client._txt2img_label_map = {}
        return
    defaults: list[Any] = []
    label_map: dict[str, int] = {}
    for idx, comp_id in enumerate(txt2img_dep.get("inputs", [])):
        comp = components.get(comp_id, {})
        props = comp.get("props", {})
        defaults.append(props.get("value"))
        label = props.get("label", "")
        if label:
            label_map[label] = idx
    client._txt2img_defaults = defaults
    client._txt2img_label_map = label_map
