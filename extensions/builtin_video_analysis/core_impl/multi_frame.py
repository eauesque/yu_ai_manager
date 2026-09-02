"""Multi-keyframe video analysis via vision LLMs.

Sends multiple keyframes in a single request to get a holistic
video description instead of per-frame analysis.
"""

import base64
import io
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_MAX_DIM = 1024  # Downscale frames for payload size


def _encode_frame(frame_path: Path) -> tuple:
    """Encode a keyframe as base64 with media type."""
    from PIL import Image

    ext = frame_path.suffix.lower()
    media_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}
    media_type = media_map.get(ext, "image/jpeg")

    with Image.open(frame_path) as img:
        w, h = img.size
        if max(w, h) > _MAX_DIM:
            img.thumbnail((_MAX_DIM, _MAX_DIM), Image.LANCZOS)

        buf = io.BytesIO()
        if media_type == "image/jpeg":
            img.save(buf, format="JPEG", quality=80)
        else:
            img.save(buf, format="PNG")

    return media_type, base64.standard_b64encode(buf.getvalue()).decode("utf-8")


_SYSTEM_PROMPT = {
    "ja": (
        "あなたは動画分析の専門家です。複数のキーフレームから動画の内容を総合的に分析してください。"
        "回答は必ずJSON形式で、description と quality_notes は必ず日本語で記述してください。"
    ),
    "en": (
        "You are a video analysis expert. Analyze the video content holistically "
        "from the provided keyframes. Always respond with valid JSON only."
    ),
}

_USER_PROMPT = {
    "ja": """\
これらは動画から抽出した{n}枚のキーフレームです。
動画全体の内容を総合的に分析し、以下のJSON形式で回答してください:
{{
  "description": "動画の内容説明（日本語、2-3文）",
  "tags": ["tag1", "tag2", "最大15個の英語タグ"],
  "quality_score": 0-10,
  "quality_notes": "映像品質コメント（日本語）",
  "style": "anime/realistic/screen_recording/presentation/vlog/music_video",
  "composition": "talking_head/action/slideshow/tutorial/landscape/mixed",
  "mood": "cheerful/dark/serene/dynamic/informative/dramatic",
  "color_palette": ["color1", "color2", "color3"],
  "prompt_suggestion": "動画の改善提案（日本語）"
}}""",
    "en": """\
These are {n} keyframes extracted from a video.
Analyze the video content holistically and respond with ONLY valid JSON:
{{
  "description": "Brief description of the video content (2-3 sentences)",
  "tags": ["tag1", "tag2", "up to 15 English tags"],
  "quality_score": 0-10,
  "quality_notes": "Short quality comment",
  "style": "anime/realistic/screen_recording/presentation/vlog/music_video",
  "composition": "talking_head/action/slideshow/tutorial/landscape/mixed",
  "mood": "cheerful/dark/serene/dynamic/informative/dramatic",
  "color_palette": ["color1", "color2", "color3"],
  "prompt_suggestion": "Brief improvement suggestion"
}}""",
}


def build_claude_messages(
    frames: list[Path], language: str = "ja",
) -> tuple:
    """Build Claude API messages with multiple frames.

    Returns (messages_list, system_prompt).
    """
    n = len(frames)
    system = _SYSTEM_PROMPT.get(language, _SYSTEM_PROMPT["en"])
    user_text = _USER_PROMPT.get(language, _USER_PROMPT["en"]).format(n=n)

    content = []
    for i, frame in enumerate(frames):
        media_type, b64_data = _encode_frame(frame)
        content.append({
            "type": "image",
            "source": {"type": "base64", "media_type": media_type, "data": b64_data},
        })
        content.append({
            "type": "text",
            "text": f"Keyframe {i + 1}/{n}",
        })

    content.append({"type": "text", "text": user_text})
    messages = [{"role": "user", "content": content}]
    return messages, system


def build_openai_messages(
    frames: list[Path], language: str = "ja",
) -> list:
    """Build OpenAI/Ollama messages with multiple frames."""
    n = len(frames)
    system = _SYSTEM_PROMPT.get(language, _SYSTEM_PROMPT["en"])
    user_text = _USER_PROMPT.get(language, _USER_PROMPT["en"]).format(n=n)

    content = []
    for frame in frames:
        media_type, b64_data = _encode_frame(frame)
        data_url = f"data:{media_type};base64,{b64_data}"
        content.append({
            "type": "image_url",
            "image_url": {"url": data_url, "detail": "low"},
        })

    content.append({"type": "text", "text": user_text})

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": content},
    ]


def build_ollama_messages(
    frames: list[Path], language: str = "ja",
) -> list:
    """Build Ollama messages with multiple frames as base64 images."""
    n = len(frames)
    system = _SYSTEM_PROMPT.get(language, _SYSTEM_PROMPT["en"])
    user_text = _USER_PROMPT.get(language, _USER_PROMPT["en"]).format(n=n)

    images = []
    for frame in frames:
        _, b64_data = _encode_frame(frame)
        images.append(b64_data)

    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user_text, "images": images},
    ]
