"""Bridge handler registry — single source of truth for bridge generate / progress / cancel.

Each Bridge extension (NAI / SD-WebUI / ComfyUI) registers a handler keyed by
bridge id ("nai" / "sd-webui" / "comfyui"). Both the local route
(`/ext/<bridge>/api/generate`) and the LAN Cowork peer route
(`/api/peer/generate`) call the SAME handler, so request/response shape is
guaranteed to match. This eliminates the class of bugs where a new field is
added to the local path but silently dropped by the peer relay (see
`docs/development/development_docs/LAN_COWORK_PATH_ASYMMETRY.md`).

Handlers return whatever Quart routes normally return — either a `Response`
object (e.g. `api_error(...)` which wraps `jsonify(...)`) or a `(Response, status)`
tuple. The peer route forwards that result verbatim.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

# Handler signature: async def handle(data: dict) -> Quart-route-compatible value
# i.e. Response | (Response, int) | (str, int) | dict | etc.
BridgeHandler = Callable[[dict[str, Any]], Awaitable[Any]]

_GENERATE: dict[str, BridgeHandler] = {}
_PROGRESS: dict[str, BridgeHandler] = {}
_CANCEL: dict[str, BridgeHandler] = {}


def register_generate(bridge_id: str, handler: BridgeHandler) -> None:
    _GENERATE[bridge_id] = handler


def register_progress(bridge_id: str, handler: BridgeHandler) -> None:
    _PROGRESS[bridge_id] = handler


def register_cancel(bridge_id: str, handler: BridgeHandler) -> None:
    _CANCEL[bridge_id] = handler


def get_generate(bridge_id: str) -> BridgeHandler | None:
    return _GENERATE.get(bridge_id)


def get_progress(bridge_id: str) -> BridgeHandler | None:
    return _PROGRESS.get(bridge_id)


def get_cancel(bridge_id: str) -> BridgeHandler | None:
    return _CANCEL.get(bridge_id)


def known_bridges() -> list[str]:
    return sorted(_GENERATE.keys())
