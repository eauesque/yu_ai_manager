"""Shared helpers for the OpenAI-compatible API adapter.

Constants, model aliases, vision/audio helpers, error formatting, and
SSE chunk serialisation used by the chat, audio, and embedding routes.
"""

import base64
import contextlib
import json
import logging
import os
import subprocess
import tempfile
import time
import uuid

import numpy as np
from quart import jsonify

from core.llm_router.type_guards import is_finite_number as _is_finite_number
from core.llm_router.type_guards import is_integer as _is_integer

logger = logging.getLogger(__name__)

# ── Model aliases ────────────────────────────────────────────────
# OpenAI SDK users can use these aliases in the ``model`` field.
MODEL_ALIASES: dict[str, str] = {
    # Whisper API compat
    "whisper-1": "whisper-base",
    # CLIP embeddings
    "clip": "clip-vit-b-16",
    "text-embedding-clip": "clip-vit-b-16",
}

# Virtual model for embeddings (not in GENAI_MODELS)
_EMBEDDING_MODEL_ID = "clip-vit-b-16"


def _resolve_model(model_str: str) -> str:
    """Resolve an alias to a canonical model name."""
    return MODEL_ALIASES.get(model_str, model_str)


def _completion_id() -> str:
    return "chatcmpl-" + uuid.uuid4().hex[:24]


def _embedding_id() -> str:
    return "embd-" + uuid.uuid4().hex[:24]


def _ts() -> int:
    return int(time.time())


def _openai_error(
    message: str,
    type_: str = "invalid_request_error",
    code: str | None = None,
    status: int = 400,
):
    return (
        jsonify({"error": {"message": message, "type": type_, "code": code}}),
        status,
    )


def _validate_messages_shape(messages) -> str | None:
    if not isinstance(messages, list):
        return "messages must be an array"
    for idx, msg in enumerate(messages):
        if not isinstance(msg, dict):
            return f"messages[{idx}] must be an object"
        role = msg.get("role")
        if not isinstance(role, str):
            return f"messages[{idx}].role must be a string"
        content = msg.get("content", "")
        if isinstance(content, list):
            for part_idx, part in enumerate(content):
                if not isinstance(part, dict):
                    return f"messages[{idx}].content[{part_idx}] must be an object"
        elif content is not None and not isinstance(content, str):
            return f"messages[{idx}].content must be a string or an array"
    return None


def _validate_chat_request_types(data: dict, *, require_messages: bool = False) -> str | None:
    if not isinstance(data, dict):
        return "request body must be an object"
    model = data.get("model")
    if model is not None and not isinstance(model, str):
        return "model must be a string"
    if require_messages and not data.get("messages"):
        return "messages is required"
    if "messages" in data and (err := _validate_messages_shape(data["messages"])):
        return err
    for field in ("temperature", "top_p"):
        if field in data and not _is_finite_number(data[field]):
            return f"{field} must be a finite number"
    if "max_tokens" in data and not _is_integer(data["max_tokens"]):
        return "max_tokens must be an integer"
    if "stream" in data and not isinstance(data["stream"], bool):
        return "stream must be a boolean"
    return None


def _validate_generation_request_types(data: dict, *, max_tokens_field: str) -> str | None:
    if not isinstance(data, dict):
        return "request body must be an object"
    for field in ("model", "vlm_model", "prompt", "content", "system_prompt"):
        if field in data and data[field] is not None and not isinstance(data[field], str):
            return f"{field} must be a string"
    if "messages" in data and (err := _validate_messages_shape(data["messages"])):
        return err
    for field in ("temperature", "top_p"):
        if field in data and not _is_finite_number(data[field]):
            return f"{field} must be a finite number"
    if max_tokens_field in data and not _is_integer(data[max_tokens_field]):
        return f"{max_tokens_field} must be an integer"
    if "max_tokens" in data and max_tokens_field != "max_tokens" and not _is_integer(data["max_tokens"]):
        return "max_tokens must be an integer"
    return None


# ── Vision helpers ───────────────────────────────────────────────

def _has_images(messages: list) -> bool:
    """Check if any message contains image_url content."""
    for msg in messages:
        content = msg.get("content")
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict) and part.get("type") == "image_url":
                    return True
    return False


def _extract_images(messages: list) -> list:
    """Decode base64 images from OpenAI Vision format.

    Returns list of BGR numpy arrays (ready for ``preprocess_image``).
    """
    import cv2

    images = []
    for msg in messages:
        content = msg.get("content")
        if not isinstance(content, list):
            continue
        for part in content:
            if not isinstance(part, dict) or part.get("type") != "image_url":
                continue
            url = part.get("image_url", {}).get("url", "")
            if url.startswith("data:"):
                # data:image/jpeg;base64,...
                try:
                    header, b64data = url.split(",", 1)
                    raw = base64.b64decode(b64data)
                    arr = np.frombuffer(raw, np.uint8)
                    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                    if img is not None:
                        images.append(img)
                except Exception as exc:
                    logger.warning("Failed to decode base64 image: %s", exc)
            elif url.startswith("file_id:"):
                # YU extension: file_id:123
                try:
                    fid = int(url.split(":", 1)[1])
                    from core.services_core.db_api import get_readonly_db
                    con = get_readonly_db()
                    row = con.execute(
                        "SELECT path FROM files WHERE id=? AND is_deleted=0",
                        (fid,),
                    ).fetchone()
                    if row:
                        import os
                        if os.path.isfile(row[0]):
                            img = cv2.imread(row[0])
                            if img is not None:
                                images.append(img)
                except Exception as exc:
                    logger.warning("Failed to load file_id image: %s", exc)
            # HTTP URLs not supported (SSRF prevention)
    return images


def _extract_text_messages(messages: list) -> list:
    """Convert OpenAI Vision messages to plain text messages for LLM/VLM."""
    out = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, str):
            out.append({"role": role, "content": content})
        elif isinstance(content, list):
            parts = []
            for part in content:
                if isinstance(part, dict) and part.get("type") == "text":
                    parts.append(part.get("text", ""))
            out.append({"role": role, "content": "\n".join(parts)})
        else:
            out.append({"role": role, "content": str(content)})
    return out


def _messages_to_hailo_format(messages: list) -> list:
    """Convert plain-text messages to Hailo structured format."""
    return [
        {
            "role": msg["role"],
            "content": [{"type": "text", "text": msg["content"]}],
        }
        for msg in messages
    ]


# ── Audio helpers ────────────────────────────────────────────────

def _convert_to_wav(audio_bytes: bytes, filename: str) -> bytes:
    """Convert audio to WAV (16kHz, mono, PCM16) using ffmpeg."""
    import os
    import tempfile

    suffix = os.path.splitext(filename)[1] or ".bin"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp_in:
        tmp_in.write(audio_bytes)
        tmp_in_path = tmp_in.name

    tmp_out_path = tmp_in_path + ".wav"
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", tmp_in_path,
                "-ar", "16000", "-ac", "1", "-f", "wav",
                tmp_out_path,
            ],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed: {result.stderr.decode(errors='replace')[:200]}"
            )
        with open(tmp_out_path, "rb") as f:
            return f.read()
    finally:
        for p in (tmp_in_path, tmp_out_path):
            with contextlib.suppress(OSError):
                os.unlink(p)


def _convert_path_to_wav(src_path: str) -> str:
    """Convert audio to a temp WAV path (16kHz, mono, PCM16) using ffmpeg."""
    tmp_out_fd, tmp_out_path = tempfile.mkstemp(suffix=".wav", prefix="yu_openai_audio_")
    os.close(tmp_out_fd)
    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y", "-i", src_path,
                "-ar", "16000", "-ac", "1", "-f", "wav",
                tmp_out_path,
            ],
            capture_output=True, timeout=60,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"ffmpeg failed: {result.stderr.decode(errors='replace')[:200]}"
            )
        return tmp_out_path
    except Exception:
        with contextlib.suppress(OSError):
            os.unlink(tmp_out_path)
        raise


# ── SSE chunk formatter ──────────────────────────────────────────

def _sse_chunk(
    cid: str,
    ts: int,
    model: str,
    *,
    content: str | None = None,
    role: str | None = None,
    finish_reason: str | None = None,
) -> str:
    """Format a single SSE chunk in OpenAI streaming format."""
    delta = {}
    if role:
        delta["role"] = role
    if content is not None:
        delta["content"] = content

    chunk = {
        "id": cid,
        "object": "chat.completion.chunk",
        "created": ts,
        "model": model,
        "choices": [{
            "index": 0,
            "delta": delta,
            "finish_reason": finish_reason,
        }],
    }
    return f"data: {json.dumps(chunk, ensure_ascii=False)}\n\n"
