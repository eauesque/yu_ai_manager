"""Upload helper for ComfyUIClient."""

from __future__ import annotations

import json
import logging
import urllib.error
import urllib.request
import uuid

from core.bridge_core import BridgeConnectionError

logger = logging.getLogger(__name__)


def _detect_image_format(data: bytes) -> tuple[str, str]:
    if data[:2] == b"\xff\xd8":
        return "image/jpeg", "jpg"
    if len(data) > 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    return "image/png", "png"


def upload_image(api_url: str, image_bytes: bytes, filename: str = "from_bridge.png") -> str:
    from .comfyui_api import _get_default_headers
    content_type, ext = _detect_image_format(image_bytes)
    stem = filename.rsplit(".", 1)[0] if "." in filename else filename
    filename = f"{stem}.{ext}"
    boundary = uuid.uuid4().hex
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode() + image_bytes + f"\r\n--{boundary}--\r\n".encode()

    headers = {"Content-Type": f"multipart/form-data; boundary={boundary}"}
    headers.update(_get_default_headers())
    req = urllib.request.Request(
        f"{api_url}/upload/image",
        data=body,
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("name", filename)
    except (urllib.error.URLError, urllib.error.HTTPError, OSError) as exc:
        logger.warning("upload_image failed: %s", exc)
        raise BridgeConnectionError(f"upload_image failed: {exc}") from exc
