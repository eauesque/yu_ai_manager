"""Translation layer: translate OCR results via LLM.

Uses the server registry's translate task score or any LLM server.
Text LLM is preferred over VLM for speed and cost.

LLM backends: translation_llm.py
DB persistence: translation_db.py
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import asdict, dataclass, field
from typing import Any

# Re-export DB functions for backward compatibility
from .translation_db import (  # noqa: F401
    ensure_translation_table,
    get_translation,
    get_translations_for_file,
    save_translation,
)
from .types import OcrResult

logger = logging.getLogger(__name__)


@dataclass
class TranslationResult:
    """Translation result container."""
    original_text: str = ""
    translated_text: str = ""
    source_lang: str = ""
    target_lang: str = ""
    engine: str = ""
    # Per-region translation (optional)
    region_translations: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


# Language code -> language name (for prompts)
_LANG_NAMES = {
    "ja": "Japanese",
    "en": "English",
    "zh": "Chinese",
    "ko": "Korean",
    "fr": "French",
    "de": "German",
    "es": "Spanish",
    "pt": "Portuguese",
    "ru": "Russian",
    "ar": "Arabic",
}


def _clean_jsonl_text(text: str) -> str:
    """Extract plain text from JSONL-formatted VLM output.

    When VLM returns {"text":"...", "type":"..."} lines, extract only
    the text fields joined by newlines. Returns empty string if not JSONL.
    """
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2 or not all(ln.startswith("{") for ln in lines):
        return ""
    texts = []
    for ln in lines:
        try:
            obj = json.loads(ln)
            t = obj.get("text", "")
            if t and t.strip():
                texts.append(t.strip())
        except json.JSONDecodeError:
            return ""
    return "\n".join(texts) if texts else ""


def _reparse_jsonl_regions(regions: list) -> list:
    """Re-parse and expand JSONL packed into a single region."""
    from .types import OcrRegion

    if len(regions) != 1 or not regions[0].text.strip().startswith("{"):
        return regions
    lines = [ln.strip() for ln in regions[0].text.strip().splitlines() if ln.strip()]
    if len(lines) < 2 or not all(ln.startswith("{") for ln in lines):
        return regions

    _label_map = {
        "speech": "speech_bubble", "speech_bubble": "speech_bubble",
        "thought": "thought_bubble", "thought_bubble": "thought_bubble",
        "sfx": "sfx", "sound_effect": "sfx",
        "narration": "narration", "caption": "caption",
        "title": "title", "sign": "sign",
    }
    new_regions = []
    for i, ln in enumerate(lines):
        try:
            obj = json.loads(ln)
        except json.JSONDecodeError:
            return regions
        text = obj.get("text", "")
        if not text or not text.strip():
            continue
        raw_type = obj.get("type", "") or obj.get("label", "")
        label = _label_map.get(raw_type.lower(), "other") if raw_type else "other"
        new_regions.append(OcrRegion(
            region_id=i + 1,
            text=text.strip(),
            label=label,
            direction=obj.get("direction", "vertical"),
        ))
    return new_regions if new_regions else regions


def _build_translation_prompt(
    text: str, source_lang: str, target_lang: str,
    is_manga: bool = False,
) -> str:
    """Build the translation prompt for the LLM."""
    src_name = _LANG_NAMES.get(source_lang, source_lang)
    tgt_name = _LANG_NAMES.get(target_lang, target_lang)

    if is_manga:
        return (
            f"Translate the following manga/comic dialogue from {src_name} to {tgt_name}. "
            f"Preserve the tone, character voice, and emotional nuance. "
            f"For sound effects (SFX), provide both a translation and the original. "
            f"Return ONLY the translated text, no explanations.\n\n"
            f"{text}"
        )

    return (
        f"Translate the following text from {src_name} to {tgt_name}. "
        f"Return ONLY the translated text, no explanations or notes.\n\n"
        f"{text}"
    )


def translate_text(
    text: str,
    source_lang: str,
    target_lang: str,
    server_id: str | None = None,
    is_manga: bool = False,
) -> TranslationResult:
    """Translate text using a resolved LLM server.

    Selects an LLM from the server registry and runs text translation.
    Uses VLM chat/completions endpoint with text-only input.
    """
    from .translation_llm import call_llm, resolve_translation_server

    if not text or not text.strip():
        return TranslationResult(
            original_text=text,
            translated_text="",
            source_lang=source_lang,
            target_lang=target_lang,
        )

    if source_lang == target_lang:
        return TranslationResult(
            original_text=text,
            translated_text=text,
            source_lang=source_lang,
            target_lang=target_lang,
        )

    prompt = _build_translation_prompt(text, source_lang, target_lang, is_manga)

    # Get engine from server registry
    engine_type, kwargs, engine_name, err = resolve_translation_server(server_id)
    if err:
        raise RuntimeError(f"Translation server not available: {err}")

    # Translate with LLM
    translated = call_llm(engine_type, kwargs, prompt)

    return TranslationResult(
        original_text=text,
        translated_text=translated,
        source_lang=source_lang,
        target_lang=target_lang,
        engine=engine_name,
    )


def translate_ocr_result(
    ocr: OcrResult,
    target_lang: str,
    server_id: str | None = None,
) -> TranslationResult:
    """Translate an OCR result.

    Batch-translates full_text and optionally per-region texts.
    """
    source_lang = ocr.language or "auto"
    is_manga = ocr.task == "ocr_manga"

    # Convert full_text to clean text if it is JSONL
    clean_text = _clean_jsonl_text(ocr.full_text) or ocr.full_text

    # Batch-translate full_text
    result = translate_text(
        clean_text, source_lang, target_lang,
        server_id=server_id, is_manga=is_manga,
    )

    # Batch-translate regions (one API call for all regions)
    if ocr.regions:
        # Re-parse then translate if JSONL is packed into 1 region
        regions = _reparse_jsonl_regions(ocr.regions)
        result.region_translations = _translate_regions_batch(
            regions, source_lang, target_lang,
            server_id=server_id, is_manga=is_manga,
        )

    return result


def _translate_regions_batch(
    regions: list,
    source_lang: str,
    target_lang: str,
    server_id: str | None = None,
    is_manga: bool = False,
) -> list[dict[str, str]]:
    """Batch-translate all regions in a single API call."""
    from .translation_llm import call_llm, resolve_translation_server

    if not regions:
        return []

    src_name = _LANG_NAMES.get(source_lang, source_lang)
    tgt_name = _LANG_NAMES.get(target_lang, target_lang)

    # Create numbered text list
    numbered_lines = []
    valid_regions = []
    for region in regions:
        if not region.text.strip():
            continue
        valid_regions.append(region)
        numbered_lines.append(f"[{region.region_id}] {region.text}")

    if not valid_regions:
        return []

    prompt = (
        f"Translate each numbered line from {src_name} to {tgt_name}. "
        f"Keep the [number] prefix. Return ONLY the translated lines.\n\n"
        + "\n".join(numbered_lines)
    )

    engine_type, kwargs, engine_name, err = resolve_translation_server(server_id)
    if err:
        logger.warning("Region batch translation server unavailable: %s", err)
        return []

    try:
        raw = call_llm(engine_type, kwargs, prompt)
    except Exception as exc:
        logger.warning("Region batch translation failed: %s", exc)
        return []

    # Parse response: [N] translated text (multi-line support)
    translated_map: dict[int, str] = {}
    parts = re.split(r'(?=\[\d+\])', raw.strip())
    for part in parts:
        m = re.match(r'\[(\d+)\]\s*(.*)', part.strip(), re.DOTALL)
        if m:
            rid = int(m.group(1))
            text = m.group(2).strip()
            if text:
                translated_map[rid] = text

    result = []
    for region in valid_regions:
        translated = translated_map.get(region.region_id, "")
        result.append({
            "region_id": region.region_id,
            "original": region.text,
            "translated": translated,
            "label": region.label,
        })
    return result
