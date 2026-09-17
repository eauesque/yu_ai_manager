"""Hailo-10H VLM engine for on-device image analysis.

All Hailo-specific imports are deferred to method bodies so that
this module can be safely imported on non-Hailo environments.
"""

import json
import logging
import re
from pathlib import Path
from typing import Any

from .engines_claude_parse import parse_image_analysis
from .types import AnalysisEngine, AnalysisResult

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT_EN = "You are an image analyst. Always respond with valid JSON only. All text values must be in English."
_SYSTEM_PROMPT_JA = (
    "You are an image analyst. Always respond with valid JSON only. "
    "description, quality_notes, prompt_suggestion must be written in Japanese (日本語)."
)
_HAILO_SYSTEM = {"ja": _SYSTEM_PROMPT_JA, "en": _SYSTEM_PROMPT_EN}

_IMAGE_PROMPT_EN = """\
Analyze this image and respond with ONLY valid JSON in this exact format:
{
  "description": "Brief description of the image content (1-2 sentences)",
  "tags": ["tag1", "tag2", "up to 15 English Danbooru-style tags"],
  "quality_score": 0-10,
  "quality_notes": "Short quality comment",
  "style": "anime/realistic/sketch/watercolor/pixel_art/3d_render",
  "composition": "portrait/full_body/close_up/landscape/group/action_pose",
  "mood": "cheerful/dark/serene/dynamic/romantic/mysterious",
  "color_palette": ["color1", "color2", "color3"],
  "prompt_suggestion": "Brief prompt improvement suggestion"
}"""

_IMAGE_PROMPT_JA = """\
Analyze this image and respond with ONLY valid JSON in this exact format.
Write "description", "quality_notes", and "prompt_suggestion" in Japanese:
{
  "description": "画像の内容説明（日本語、1-2文）",
  "tags": ["tag1", "tag2", "up to 15 English Danbooru-style tags"],
  "quality_score": 0-10,
  "quality_notes": "品質コメント（日本語）",
  "style": "anime/realistic/sketch/watercolor/pixel_art/3d_render",
  "composition": "portrait/full_body/close_up/landscape/group/action_pose",
  "mood": "cheerful/dark/serene/dynamic/romantic/mysterious",
  "color_palette": ["color1", "color2", "color3"],
  "prompt_suggestion": "プロンプト改善提案（日本語）"
}"""

_HAILO_PROMPTS = {"ja": _IMAGE_PROMPT_JA, "en": _IMAGE_PROMPT_EN}


def _parse_hailo_response(raw: str) -> AnalysisResult:
    """Three-stage parser for Hailo VLM output.

    1. Standard JSON parse via parse_image_analysis
    2. Regex extraction of {...} block
    3. Fallback: raw text as description
    """
    # Stage 1: standard parser
    result = parse_image_analysis(raw)
    if result.tags or result.description:
        return result

    # Stage 2: regex extract JSON object
    match = re.search(r"\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}", raw, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group())
            result = AnalysisResult()
            result.raw_response = raw
            result.tags = data.get("tags", [])
            result.quality_score = float(data.get("quality_score", 0))
            result.quality_notes = data.get("quality_notes", "")
            result.description = data.get("description", "")
            result.style = data.get("style", "")
            result.composition = data.get("composition", "")
            result.mood = data.get("mood", "")
            result.color_palette = data.get("color_palette", [])
            result.prompt_suggestion = data.get("prompt_suggestion", "")
            return result
        except (json.JSONDecodeError, ValueError):
            pass

    # Stage 3: fallback -- raw text as description
    result = AnalysisResult()
    result.raw_response = raw
    result.description = raw.strip()[:500]
    result.quality_notes = "Hailo VLM: structured parse failed, raw text used"
    return result


class HailoVLMEngine(AnalysisEngine):
    """On-device image analysis using Hailo-10H VLM (qwen2-vl-2b-instruct)."""

    def __init__(self, model_name: str = "qwen2-vl-2b-instruct", language: str = "ja"):
        self._model_name = model_name
        self._language = language

    def get_name(self) -> str:
        return f"Hailo VLM ({self._model_name})"

    def analyze_image(
        self,
        image_path: Path,
        existing_tags: list[str] | None = None,
        existing_prompt: str | None = None,
        mode: str = "full",
        format_json: bool = False,
        json_schema: dict | None = None,
    ) -> AnalysisResult:
        import importlib.util
        from pathlib import Path

        import cv2
        # Load from the Hailo GenAI extension module by file path.
        _spec = importlib.util.spec_from_file_location(
            "hailo_genai_vlm_inference",
            Path(__file__).resolve().parents[2] / "builtin_hailo_genai" / "core_impl" / "vlm_inference.py")
        _vlm_mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_vlm_mod)
        get_vlm = _vlm_mod.get_vlm
        preprocess_image = _vlm_mod.preprocess_image

        image_bgr = cv2.imread(str(image_path))
        if image_bgr is None:
            result = AnalysisResult()
            result.quality_notes = f"Failed to read image: {image_path}"
            return result

        frame = preprocess_image(image_bgr)
        vlm = get_vlm(self._model_name)
        vlm.clear_context()

        # OCR mode: use existing_prompt as-is
        if mode == "ocr" and existing_prompt:
            user_prompt = existing_prompt
            system_prompt = "You are an OCR assistant. Read text from images accurately."
        else:
            user_prompt = _HAILO_PROMPTS.get(self._language, _IMAGE_PROMPT_EN)
            system_prompt = _HAILO_SYSTEM.get(self._language, _SYSTEM_PROMPT_EN)

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": [
                {"type": "image"},
                {"type": "text", "text": user_prompt},
            ]},
        ]

        raw = vlm.generate_all(
            messages,
            frames=[frame],
            temperature=0.3,
            max_generated_tokens=1024 if mode == "ocr" else 512,
        )
        logger.debug("Hailo VLM raw response: %s", raw[:300])

        # In OCR mode, return raw response as-is (OCR parser handles it)
        if mode == "ocr":
            result = AnalysisResult()
            result.raw_response = raw
            return result

        return _parse_hailo_response(raw)

    def analyze_prompt_trends(self, prompts: list[dict]) -> dict[str, Any]:
        return {
            "error": "Hailo VLM does not support prompt trend analysis "
            "(image-only model)"
        }
