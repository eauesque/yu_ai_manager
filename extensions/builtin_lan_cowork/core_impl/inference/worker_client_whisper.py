"""Remote Whisper worker calls."""

from __future__ import annotations

import logging
from pathlib import Path

from ..models import PeerInfo
from .worker_client_transport import post_octet_stream

logger = logging.getLogger(__name__)


async def whisper_transcribe_remote(
    peer: PeerInfo,
    wav_path: str,
    language: str = "ja",
    timeout: float = 120.0,
) -> dict | None:
    try:
        wav_bytes = Path(wav_path).read_bytes()
    except OSError as exc:
        logger.debug("Cannot read WAV file %s: %s", wav_path, exc)
        return None
    if not wav_bytes:
        logger.debug("WAV file is empty: %s", wav_path)
        return None

    result = await post_octet_stream(
        peer,
        f"/api/peer/infer/whisper-transcribe?language={language}",
        wav_bytes,
        timeout=timeout,
    )
    if result is None:
        return None
    peer_id = getattr(peer, "peer_id", "<unknown>")
    if not isinstance(result, dict):
        logger.warning("Whisper worker returned non-dict response from %s", peer_id)
        return None
    ok_value = result.get("ok")
    legacy_success = "ok" not in result and result.get("status") == "ok"
    if ok_value is False:
        logger.warning("Whisper worker failed peer=%s error=%s", peer_id, result.get("error"))
        return None
    if ok_value is not True and not legacy_success:
        logger.warning("Whisper worker returned unsuccessful response peer=%s error=%s", peer_id, result.get("error"))
        return None
    text = result.get("text")
    segments = result.get("segments")
    if not isinstance(text, str) or not isinstance(segments, list):
        logger.warning(
            "Whisper worker returned invalid transcript peer=%s text_type=%s segments_type=%s",
            peer_id,
            type(text).__name__,
            type(segments).__name__,
        )
        return None
    return result
