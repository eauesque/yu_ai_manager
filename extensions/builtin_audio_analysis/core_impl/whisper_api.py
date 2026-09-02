"""OpenAI Whisper API transcription."""

import http.client
import json
import logging
import ssl
from pathlib import Path
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

_TIMEOUT = 120
_MAX_FILE_SIZE = 25 * 1024 * 1024  # 25 MB (OpenAI limit)


def transcribe(
    audio_path: Path,
    api_key: str,
    model: str = "whisper-1",
    language: str = "",
    base_url: str = "",
) -> dict:
    """Transcribe audio file using OpenAI Whisper API.

    Args:
        audio_path: Path to audio file.
        api_key: OpenAI API key.
        model: Model name (default: whisper-1).
        language: ISO 639-1 code (empty for auto-detect).
        base_url: Custom API base (for compatible endpoints).

    Returns:
        {"text": str, "segments": list, "language": str, "duration": float}
    """
    if not api_key:
        raise RuntimeError("OpenAI API key is required for Whisper API")

    file_size = audio_path.stat().st_size
    if file_size > _MAX_FILE_SIZE:
        raise RuntimeError(
            f"Audio file too large ({file_size / 1024 / 1024:.1f}MB). "
            f"Max: {_MAX_FILE_SIZE / 1024 / 1024:.0f}MB"
        )

    url = base_url.rstrip("/") if base_url else "https://api.openai.com"
    endpoint = f"{url}/v1/audio/transcriptions"
    parsed = urlparse(endpoint)

    # Build multipart/form-data
    boundary = "----YuAudioAnalysisBoundary"
    body_parts = []

    # model field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="model"\r\n\r\n')
    body_parts.append(f"{model}\r\n")

    # response_format field
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append('Content-Disposition: form-data; name="response_format"\r\n\r\n')
    body_parts.append("verbose_json\r\n")

    # language field (optional)
    if language:
        body_parts.append(f"--{boundary}\r\n")
        body_parts.append('Content-Disposition: form-data; name="language"\r\n\r\n')
        body_parts.append(f"{language}\r\n")

    # file field
    file_data = audio_path.read_bytes()
    body_parts.append(f"--{boundary}\r\n")
    body_parts.append(
        f'Content-Disposition: form-data; name="file"; filename="{audio_path.name}"\r\n'
    )
    body_parts.append("Content-Type: application/octet-stream\r\n\r\n")

    # Combine text parts + binary file data + closing boundary
    text_before = "".join(body_parts).encode("utf-8")
    closing = f"\r\n--{boundary}--\r\n".encode()
    payload = text_before + file_data + closing

    headers = {
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Authorization": f"Bearer {api_key}",
    }

    ctx = ssl.create_default_context()
    conn = http.client.HTTPSConnection(
        parsed.hostname, parsed.port or 443, timeout=_TIMEOUT, context=ctx,
    )

    try:
        conn.request("POST", parsed.path, body=payload, headers=headers)
        resp = conn.getresponse()
        resp_body = resp.read().decode("utf-8")
    finally:
        conn.close()

    if resp.status != 200:
        raise RuntimeError(f"Whisper API error (HTTP {resp.status}): {resp_body[:300]}")

    data = json.loads(resp_body)

    segments = []
    for seg in data.get("segments", []):
        segments.append({
            "start": round(seg.get("start", 0), 2),
            "end": round(seg.get("end", 0), 2),
            "text": seg.get("text", "").strip(),
        })

    return {
        "text": data.get("text", ""),
        "segments": segments,
        "language": data.get("language", ""),
        "duration": round(data.get("duration", 0), 2),
    }
