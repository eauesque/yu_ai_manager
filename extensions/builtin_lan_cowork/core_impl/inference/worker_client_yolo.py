"""Remote YOLO worker calls."""

from __future__ import annotations

from ..models import PeerInfo
from .worker_client_transport import YOLO_REMOTE_CHUNK, build_multipart_images, post_multipart


async def yolo_detect_remote(
    peer: PeerInfo,
    image_paths: list[str],
    chunk_size: int = YOLO_REMOTE_CHUNK,
    timeout: float = 60.0,
) -> list[list[dict] | None]:
    if not image_paths:
        return []

    detections: list[list[dict] | None] = [None] * len(image_paths)
    for start in range(0, len(image_paths), chunk_size):
        chunk = image_paths[start : start + chunk_size]
        body, sent_indices = build_multipart_images(chunk)
        if body is None:
            continue

        result = await post_multipart(peer, "/api/peer/infer/yolo-detect", body, timeout=timeout)
        if result is None:
            continue

        raw_detections = result.get("detections", [])
        for j, dets in enumerate(raw_detections):
            if j >= len(sent_indices):
                break
            detections[start + sent_indices[j]] = dets
    return detections
