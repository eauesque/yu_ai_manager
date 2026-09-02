"""ComfyUI client: WebSocket wait and image retrieval logic.

Split from comfyui_client.py to keep each module under 300 lines.
"""

from __future__ import annotations

import base64
import json
import logging
import time
from collections.abc import Callable
from typing import Any
from urllib.parse import urlencode

from core.bridge_core import BridgeConnectionError, BridgeHTTPClient, BridgeHTTPError

logger = logging.getLogger(__name__)


def _build_ws_url(api_url: str, client_id: str, backend_id: str | None = None) -> str:
    ws_base = api_url.replace("http://", "ws://").replace("https://", "wss://")
    params = {"clientId": client_id}
    if backend_id and backend_id != "__fallback__":
        params["backend_id"] = backend_id
    return f"{ws_base}/ws?{urlencode(params)}"


def connect_ws(api_url: str, client_id: str, backend_id: str | None = None):
    """Open a WebSocket connection to ComfyUI *before* queuing a prompt.

    Connecting early ensures that progress/executing events are not missed
    when the model is already warm (fast execution completes in < 1 s).

    Returns the open ``websocket.WebSocket`` on success, or ``None`` if
    the ``websocket-client`` package is unavailable or the connection fails.
    The caller is responsible for closing the returned socket.
    """
    try:
        import websocket  # type: ignore[import-untyped]  # noqa: PLC0415

        from .comfyui_api import _get_api_key  # noqa: PLC0415
        ws_url = _build_ws_url(api_url, client_id, backend_id)
        ws = websocket.WebSocket()
        ws.settimeout(5)
        _api_key = _get_api_key()
        _subprotocols = [f"bearer.{_api_key}"] if _api_key else []
        if _subprotocols:
            ws.connect(ws_url, subprotocols=_subprotocols)
        else:
            ws.connect(ws_url)
        return ws
    except Exception as exc:
        logger.info("connect_ws: pre-connect failed: %s", exc)
        return None


def wait_for_result_impl(
    http: BridgeHTTPClient,
    api_url: str,
    prompt_id: str,
    client_id: str,
    *,
    on_progress: Callable[[int, int], None] | None = None,
    timeout: float = 300.0,
    pre_ws=None,
    backend_id: str | None = None,
) -> dict[str, Any]:
    """Wait for prompt completion via WebSocket, with HTTP polling fallback.

    Parameters
    ----------
    http:
        The BridgeHTTPClient instance for API calls.
    api_url:
        Root URL of ComfyUI (for WS URL derivation).
    prompt_id:
        The prompt ID returned from queue_prompt.
    client_id:
        The client ID used in queue_prompt.
    on_progress:
        Optional callback ``(value, max)`` called on each progress update.
    timeout:
        Maximum wait time in seconds.
    pre_ws:
        An already-open ``websocket.WebSocket`` connected before
        ``queue_prompt`` was called.  When provided, ``_wait_ws`` skips
        its own connect step and does *not* close this socket on exit —
        the caller owns the lifecycle.

    Returns the /history entry for the prompt on success.
    Raises ``RuntimeError`` on execution error or timeout.
    """
    try:
        return _wait_ws(
            http,
            api_url,
            prompt_id,
            client_id,
            on_progress,
            timeout,
            pre_ws=pre_ws,
            backend_id=backend_id,
        )
    except RuntimeError:
        # RuntimeError signals an execution error or timeout from _wait_ws;
        # the original message must be preserved for meta-tensor / error
        # detection upstream.  Do NOT fall back to polling here — polling
        # would replace the message with the generic "from history" string.
        raise
    except Exception as exc:
        logger.info(
            "WebSocket wait failed (%s), falling back to HTTP polling", exc
        )
        return _wait_poll(http, prompt_id, timeout)


def _wait_ws(
    http: BridgeHTTPClient,
    api_url: str,
    prompt_id: str,
    client_id: str,
    on_progress: Callable[[int, int], None] | None,
    timeout: float,
    *,
    pre_ws=None,
    backend_id: str | None = None,
) -> dict[str, Any]:
    """Wait for completion via WebSocket.

    When *pre_ws* is supplied the socket is used as-is and ownership stays
    with the caller (not closed here).  Otherwise a new socket is opened
    and closed in the finally block.
    """
    import websocket  # type: ignore[import-untyped]

    if pre_ws is not None:
        ws = pre_ws
        ws_owner = False
    else:
        ws_url = _build_ws_url(api_url, client_id, backend_id)
        ws = websocket.WebSocket()
        ws.settimeout(5)
        ws.connect(ws_url)
        ws_owner = True

    deadline = time.time() + timeout
    last_history_check = time.time()
    try:
        while time.time() < deadline:
            remaining = deadline - time.time()
            # Cap recv timeout at 1 s so we can do periodic history checks
            # even when no WS messages arrive (warm-cache fast generation).
            ws.settimeout(min(1.0, max(0.05, remaining)))
            try:
                raw = ws.recv()
            except websocket.WebSocketTimeoutException:
                # Periodically poll /history to detect executions that
                # completed before (or without sending) WS events.
                now = time.time()
                if now - last_history_check >= 3.0:
                    last_history_check = now
                    try:
                        entry = get_history(http, prompt_id)
                        if entry.get("outputs") or entry.get("status", {}).get("completed"):
                            logger.info(
                                "prompt %s already in history — skipping WS wait",
                                prompt_id,
                            )
                            return entry
                    except Exception:
                        logger.debug("history lookup failed; falling back to the WS wait", exc_info=True)
                continue
            if not raw:
                continue

            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                # Non-JSON frame (binary, ping/pong, custom node debug output) — skip.
                continue
            msg_type = msg.get("type", "")
            msg_data = msg.get("data", {})

            if msg_type == "progress" and msg_data.get("prompt_id") == prompt_id:
                if on_progress:
                    on_progress(msg_data.get("value", 0), msg_data.get("max", 0))

            elif msg_type == "executing" and msg_data.get("prompt_id") == prompt_id:
                if msg_data.get("node") is None:
                    # Execution complete
                    return get_history(http, prompt_id)

            elif msg_type == "execution_error":
                err_pid = msg_data.get("prompt_id", "")
                if err_pid == prompt_id:
                    err_msg = msg_data.get("exception_message", "Execution error")
                    raise RuntimeError(f"ComfyUI execution error: {err_msg}")
    finally:
        if ws_owner:
            ws.close()

    raise RuntimeError("ComfyUI generation timed out")


def _wait_poll(
    http: BridgeHTTPClient, prompt_id: str, timeout: float,
) -> dict[str, Any]:
    """Fallback: poll GET /history/{prompt_id} until completion."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            history = http.get(f"/history/{prompt_id}", timeout=5)
            entry = history.get(prompt_id, {})
            if entry.get("outputs"):
                return entry
            status = entry.get("status", {})
            if status.get("completed", False):
                return entry
            if status.get("status_str") == "error":
                raise RuntimeError("ComfyUI execution error (from history)")
        except (BridgeConnectionError, BridgeHTTPError):
            pass
        time.sleep(1.5)

    raise RuntimeError("ComfyUI generation timed out (polling)")


def get_history(http: BridgeHTTPClient, prompt_id: str) -> dict[str, Any]:
    """Retrieve history entry for a prompt."""
    history = http.get(f"/history/{prompt_id}", timeout=10)
    return history.get(prompt_id, {})


def get_images(
    http: BridgeHTTPClient, prompt_id: str,
) -> list[dict[str, Any]]:
    """Retrieve generated images as base64 from history outputs.

    Returns list of ``{"base64": ..., "filename": ...}`` dicts.
    """
    history = get_history(http, prompt_id)
    outputs = history.get("outputs", {})

    images: list[dict[str, Any]] = []
    for _node_id, node_output in outputs.items():
        for img_info in node_output.get("images", []):
            filename = img_info.get("filename", "")
            subfolder = img_info.get("subfolder", "")
            img_type = img_info.get("type", "output")

            qs_parts: dict[str, str] = {"filename": filename, "type": img_type}
            if subfolder:
                qs_parts["subfolder"] = subfolder
            params = urlencode(qs_parts)

            try:
                raw_bytes = http.get_bytes(f"/view?{params}", timeout=30)
                b64 = base64.b64encode(raw_bytes).decode("ascii")
                images.append({"base64": b64, "filename": filename})
            except (BridgeConnectionError, BridgeHTTPError) as exc:
                logger.warning("Failed to fetch image %s: %s", filename, exc)

    return images


def get_output_paths(
    http: BridgeHTTPClient, prompt_id: str,
) -> list[dict[str, str]]:
    """Return ComfyUI-saved output file descriptors for *prompt_id*.

    Each entry is ``{"filename": ..., "subfolder": ..., "type": ...}`` where
    ``type == "output"`` means ComfyUI persisted the file to its output dir.
    Used by Bridge-managed save mode to write Sweep XMP into ComfyUI's own
    saved files (without creating a duplicate copy).
    """
    history = get_history(http, prompt_id)
    outputs = history.get("outputs", {})
    descs: list[dict[str, str]] = []
    for _node_id, node_output in outputs.items():
        for img_info in node_output.get("images", []):
            descs.append({
                "filename": str(img_info.get("filename", "")),
                "subfolder": str(img_info.get("subfolder", "")),
                "type": str(img_info.get("type", "output")),
            })
    return descs
