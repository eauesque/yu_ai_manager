"""Transport helpers for remote worker inference."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import PeerInfo
from ..transport import PeerTransport

logger = logging.getLogger(__name__)

USER_AGENT = "YuAiManager/1.0 MeshInferenceClient"
DEFAULT_BOUNDARY = "----YuAiMeshInferenceBoundary"
YOLO_REMOTE_CHUNK = 4

IMAGE_EXTS = {
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif",
    ".bmp", ".tiff", ".tif", ".heif", ".heic", ".jxl",
}

MIME_MAP = {
    ".png": "image/png",
    ".webp": "image/webp",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".avif": "image/avif",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heif": "image/heif",
    ".heic": "image/heic",
    ".jxl": "image/jxl",
}


def _get_mgr():
    try:
        from ...lan_cowork_ext import _get_manager

        return _get_manager()
    except Exception:
        return None


def _signed_peer_headers(
    peer: PeerInfo,
    *,
    method: str,
    path: str,
    body: bytes,
    content_type: str,
) -> dict[str, str] | None:
    mgr = _get_mgr()
    if mgr is None:
        logger.warning("MeshInference: manager unavailable, cannot sign peer request")
        return None
    from core.crypto_identity import path_requires_nonce

    from ..peer_auth_client import build_peer_headers

    full_path = f"{PeerTransport._PREFIX}{path}"
    headers = build_peer_headers(
        mgr.local_seed(),
        mgr.local_peer.peer_id,
        getattr(peer, "token", None) or "",
        method,
        full_path,
        "",
        body,
        require_nonce=path_requires_nonce(full_path),
    )
    headers["Content-Type"] = content_type
    headers["Accept"] = "application/json"
    headers["User-Agent"] = USER_AGENT
    headers["X-Requested-With"] = "MeshInference"
    return headers


def build_multipart_images(image_paths: list[str], boundary: str = DEFAULT_BOUNDARY) -> tuple:
    body_parts: list[bytes] = []
    sent_indices: list[int] = []

    for i, path in enumerate(image_paths):
        if "!" in path:
            continue
        suffix = Path(path).suffix.lower()
        if suffix not in IMAGE_EXTS:
            continue
        try:
            image_bytes = Path(path).read_bytes()
        except OSError as exc:
            logger.debug("Skipping unreadable file %s: %s", path, exc)
            continue
        if not image_bytes:
            continue

        mime = MIME_MAP.get(suffix, "image/jpeg")
        filename = Path(path).name
        part_header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="images"; filename="{filename}"\r\n'
            f"Content-Type: {mime}\r\n\r\n"
        ).encode()
        body_parts.append(part_header + image_bytes + b"\r\n")
        sent_indices.append(i)

    if not body_parts:
        return None, sent_indices

    body_parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(body_parts), sent_indices


async def post_multipart(
    peer: PeerInfo,
    path: str,
    body: bytes,
    boundary: str = DEFAULT_BOUNDARY,
    timeout: float = 60.0,
) -> dict | None:
    import aiohttp

    url_path = PeerTransport._PREFIX + path
    full_url = f"http://{peer.api_host}:{peer.api_port}{url_path}"
    headers = _signed_peer_headers(
        peer,
        method="POST",
        path=path,
        body=body,
        content_type=f"multipart/form-data; boundary={boundary}",
    )
    if headers is None:
        return None

    try:
        async with aiohttp.ClientSession() as session, session.post(
            full_url,
            data=body,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status >= 400:
                logger.error("HTTP %s from %s", resp.status, full_url)
                return None
            return await resp.json()
    except Exception as exc:
        logger.error("POST to %s failed: %s", full_url, exc)
        return None


async def post_octet_stream(
    peer: PeerInfo,
    path: str,
    payload: bytes,
    *,
    timeout: float,
    content_type: str = "application/octet-stream",
) -> dict | None:
    import aiohttp

    full_url = f"http://{peer.api_host}:{peer.api_port}{PeerTransport._PREFIX}{path}"
    headers = _signed_peer_headers(
        peer,
        method="POST",
        path=path,
        body=payload,
        content_type=content_type,
    )
    if headers is None:
        return None

    try:
        async with aiohttp.ClientSession() as session, session.post(
            full_url,
            data=payload,
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=timeout),
        ) as resp:
            if resp.status >= 400:
                logger.error("HTTP %s from %s", resp.status, full_url)
                return None
            return await resp.json()
    except Exception as exc:
        logger.error("POST to %s failed: %s", full_url, exc)
        return None
