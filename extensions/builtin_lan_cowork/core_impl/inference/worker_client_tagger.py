"""Remote tagger worker calls."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import PeerInfo
from .worker_client_transport import DEFAULT_BOUNDARY, IMAGE_EXTS, MIME_MAP, post_multipart

logger = logging.getLogger(__name__)


async def tagger_tag_remote(
    peer: PeerInfo,
    image_path: str,
    timeout: float = 60.0,
) -> list[dict] | None:
    suffix = Path(image_path).suffix.lower()
    if suffix not in IMAGE_EXTS:
        logger.debug("Unsupported image extension for tagger: %s", image_path)
        return None

    try:
        image_bytes = Path(image_path).read_bytes()
    except OSError as exc:
        logger.debug("Cannot read image file %s: %s", image_path, exc)
        return None
    if not image_bytes:
        logger.debug("Image file is empty: %s", image_path)
        return None

    boundary = DEFAULT_BOUNDARY
    mime = MIME_MAP.get(suffix, "image/jpeg")
    filename = Path(image_path).name
    part_header = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="image"; filename="{filename}"\r\n'
        f"Content-Type: {mime}\r\n\r\n"
    ).encode()
    body = part_header + image_bytes + b"\r\n" + f"--{boundary}--\r\n".encode()

    result = await post_multipart(
        peer,
        "/api/peer/infer/tag",
        body,
        boundary=boundary,
        timeout=timeout,
    )
    if result is None:
        return None
    peer_id = getattr(peer, "peer_id", "<unknown>")
    if not isinstance(result, dict):
        logger.warning("Tagger worker returned non-dict response from %s", peer_id)
        return None
    if result.get("ok") is not True:
        logger.warning("Tagger worker failed peer=%s error=%s", peer_id, result.get("error"))
        return None
    tags = result.get("tags")
    if not isinstance(tags, list):
        logger.warning("Tagger worker returned invalid tags peer=%s type=%s", peer_id, type(tags).__name__)
        return None
    return tags
