"""Remote CLIP worker calls."""

from __future__ import annotations

import base64
import logging

import numpy as np

from ..models import PeerInfo
from .worker_client_transport import build_multipart_images, post_multipart

logger = logging.getLogger(__name__)


async def clip_encode_remote(
    peer: PeerInfo,
    image_paths: list[str],
    timeout: float = 60.0,
) -> list[np.ndarray | None]:
    if not image_paths:
        return []

    body, sent_indices = build_multipart_images(image_paths)
    if body is None:
        return [None] * len(image_paths)

    result = await post_multipart(peer, "/api/peer/infer/clip-encode", body, timeout=timeout)
    if result is None:
        return [None] * len(image_paths)

    raw_vectors = result.get("vectors", [])
    vectors: list[np.ndarray | None] = [None] * len(image_paths)
    for j, b64 in enumerate(raw_vectors):
        if j >= len(sent_indices):
            break
        orig_idx = sent_indices[j]
        if b64 is None:
            continue
        try:
            arr = np.frombuffer(base64.b64decode(b64), dtype=np.float32).copy()
            if np.any(arr != 0):
                vectors[orig_idx] = arr
        except Exception as exc:
            logger.warning("Failed to decode vector[%d]: %s", j, exc)
    return vectors
