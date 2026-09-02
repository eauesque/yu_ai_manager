"""I/O helpers for the Forge Gradio 4 client."""

from __future__ import annotations

import base64
import contextlib
import json
import logging
import os
import tempfile
import urllib.error
import urllib.request
from typing import Any

# Safe root directories for local Gradio temp files.
# Gradio writes generated images under the system temp dir; paths outside this
# boundary (e.g. from a compromised remote backend via gateway_url) are rejected.
_SAFE_ROOTS = tuple(
    os.path.realpath(d)
    for d in (tempfile.gettempdir(),)
    if os.path.isdir(d)
)

from core.bridge_core import BridgeConnectionError, BridgeHTTPError

logger = logging.getLogger(__name__)

_USER_AGENT = "yu-ai-manager/BridgeHTTPClient"
_ALLOWED_IMAGE_EXTS = frozenset({
    ".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tiff", ".tif",
})


def call_gradio_and_wait(
    api_url: str,
    api_name: str,
    data: list,
    *,
    timeout: float = 120,
) -> list:
    """Submit ``/call`` request and wait for the SSE completion event."""
    submit_body = json.dumps({"data": data}).encode("utf-8")
    submit_url = f"{api_url}/call{api_name}"
    request = urllib.request.Request(submit_url, data=submit_body, method="POST")
    request.add_header("Content-Type", "application/json")
    request.add_header("User-Agent", _USER_AGENT)
    from .sd_webui_api import _get_default_headers
    for _k, _v in _get_default_headers().items():
        request.add_header(_k, _v)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            raw_submit = response.read()
    except urllib.error.HTTPError as exc:
        body = ""
        with contextlib.suppress(Exception):
            body = exc.read().decode("utf-8", errors="replace")
        raise BridgeHTTPError(exc.code, body) from exc
    except (urllib.error.URLError, OSError) as exc:
        raise BridgeConnectionError(
            f"Cannot connect to {api_url}: {exc}"
        ) from exc

    try:
        result = json.loads(raw_submit)
    except json.JSONDecodeError as exc:
        raise BridgeHTTPError(500, f"Invalid JSON from Gradio submit: {raw_submit[:200]}") from exc

    event_id = result.get("event_id")
    if not event_id:
        raise BridgeHTTPError(500, "No event_id in /call response")

    stream_url = f"{api_url}/call{api_name}/{event_id}"
    stream_request = urllib.request.Request(stream_url, method="GET")
    stream_request.add_header("User-Agent", _USER_AGENT)
    from .sd_webui_api import _get_default_headers
    for _k, _v in _get_default_headers().items():
        stream_request.add_header(_k, _v)

    try:
        with urllib.request.urlopen(stream_request, timeout=timeout) as response:
            current_event = ""
            for raw_line in response:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if line.startswith("event:"):
                    current_event = line.split(":", 1)[1].strip()
                elif line.startswith("data:"):
                    data_str = line[5:].strip()
                    if current_event == "complete":
                        return json.loads(data_str)
                    if current_event == "error":
                        raise BridgeHTTPError(500, f"Gradio error: {data_str[:200]}")
    except urllib.error.URLError as exc:
        raise BridgeConnectionError(f"SSE stream failed: {exc}") from exc
    except json.JSONDecodeError as exc:
        raise BridgeHTTPError(500, f"Invalid SSE data: {exc}") from exc

    raise BridgeHTTPError(500, "SSE stream ended without completion")


def set_arg(args: list, label_map: dict[str, int], label: str, value: Any) -> None:
    """Set a Gradio argument by its discovered label."""
    index = label_map.get(label)
    if index is not None and index < len(args):
        args[index] = value


def read_file_as_b64(path: str) -> str | None:
    """Read an image file and return it as base64.

    Only files within the system temp directory are permitted.  Paths outside
    that boundary (potentially from a compromised remote Forge backend) are
    rejected to prevent arbitrary local-file read via crafted SSE responses.
    """
    ext = os.path.splitext(path)[1].lower()
    if ext not in _ALLOWED_IMAGE_EXTS:
        logger.warning("Rejected non-image file path from Gradio response: %s", path)
        return None

    try:
        real = os.path.realpath(path)
        # Directory containment check: path must be inside a known-safe root.
        if _SAFE_ROOTS and not any(real.startswith(r + os.sep) or real == r
                                   for r in _SAFE_ROOTS):
            logger.warning(
                "Rejected Gradio file path outside safe root(s): %s (resolved: %s)",
                path, real,
            )
            return None
        if not os.path.isfile(real):
            return None
        with open(real, "rb") as handle:
            return base64.b64encode(handle.read()).decode("ascii")
    except OSError as exc:
        logger.warning("Failed to read image file %s: %s", path, exc)
        return None


def fetch_file_as_b64(api_url: str, url: str) -> str | None:
    """Fetch a Forge file URL and return it as base64."""
    try:
        fetch_url = url if url.startswith(("http://", "https://")) else api_url + url
        request = urllib.request.Request(fetch_url, method="GET")
        request.add_header("User-Agent", _USER_AGENT)
        # Include auth headers (api_key_enc) so authenticated Forge backends
        # don't return 401 on file download requests.
        from .sd_webui_api import _get_default_headers
        for _k, _v in _get_default_headers().items():
            request.add_header(_k, _v)
        with urllib.request.urlopen(request, timeout=30) as response:
            raw_bytes = response.read()
        return base64.b64encode(raw_bytes).decode("ascii")
    except Exception as exc:
        logger.warning("Failed to fetch image from %s: %s", url, exc)
        return None


def parse_seed(info_text: Any, fallback: int) -> int:
    """Extract seed value from Forge's info text."""
    if not isinstance(info_text, str):
        return fallback
    for line in info_text.replace("<br>", "\n").split("\n"):
        stripped = line.strip()
        if stripped.startswith("Seed:"):
            try:
                return int(stripped.split(":", 1)[1].strip().split(",")[0])
            except (ValueError, IndexError):
                pass
    return fallback
