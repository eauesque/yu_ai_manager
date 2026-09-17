"""VLM-based OCR engine. Wraps an existing AnalysisEngine for OCR tasks."""

from __future__ import annotations

import logging
from pathlib import Path

from .types import OcrEngine, OcrRegion, OcrResult
from .vlm_ocr_parsers import (
    deduplicate_regions,
    extract_json_object,
    fallback_text,
    manga_parse_quality,
    parse_manga_any_format,
    should_retry_manga,
)
from .vlm_ocr_prompts import (
    LANG_HINT,
    MANGA_JSON_SCHEMA,
    MANGA_RETRY_PROMPT,
    OCR_JSON_SCHEMA,
    PROMPTS,
    normalize_label,
)

logger = logging.getLogger(__name__)

# Re-export for backward compatibility (internal callers used _private names)
_PROMPTS = PROMPTS
_MANGA_RETRY_PROMPT = MANGA_RETRY_PROMPT
_MANGA_JSON_SCHEMA = MANGA_JSON_SCHEMA
_OCR_JSON_SCHEMA = OCR_JSON_SCHEMA
_LANG_HINT = LANG_HINT
_LABEL_NORMALIZE = None  # Use normalize_label() instead
_normalize_label = normalize_label
_extract_json_object = extract_json_object
_extract_json_any = None  # Use vlm_ocr_parsers.extract_json_any
_parse_manga_any_format = parse_manga_any_format
_deduplicate_regions = deduplicate_regions
_fallback_text = fallback_text
_manga_parse_quality = manga_parse_quality
_should_retry_manga = should_retry_manga


class VlmOcrEngine(OcrEngine):
    """VLM-based OCR engine. Switches prompts based on task type."""

    def __init__(self, analysis_engine):
        """Wrap an existing AnalysisEngine instance for OCR use.

        Args:
            analysis_engine: AnalysisEngine implementation from builtin-analysis
        """
        self._engine = analysis_engine

    def get_name(self) -> str:
        return self._engine.get_name()

    def supports_task(self, task: str) -> bool:
        return task in ("ocr", "ocr_document", "ocr_manga")

    def extract_text(self, image_path: Path, task: str = "ocr",
                     language: str = "auto") -> OcrResult:
        prompt = PROMPTS.get(task, PROMPTS["ocr"])

        if language != "auto" and language in LANG_HINT:
            prompt += "\n" + LANG_HINT[language]

        # Structured Output: specify JSON Schema based on task
        # (supported engines only -- Ollama enforces schema at token generation level)
        schema = MANGA_JSON_SCHEMA if task == "ocr_manga" else OCR_JSON_SCHEMA
        # format_json=True is fallback for engines without schema support
        result = self._engine.analyze_image(
            image_path, existing_tags=[], existing_prompt=prompt,
            mode="ocr", format_json=True, json_schema=schema,
        )
        raw = result.raw_response or ""
        ocr_result = self._parse_response(raw, task, language)

        # Retry with different prompt if manga OCR parse quality is low
        if task == "ocr_manga" and should_retry_manga(ocr_result):
            logger.info("Manga OCR parse quality low, retrying with simplified prompt")
            retry_prompt = MANGA_RETRY_PROMPT
            if language != "auto" and language in LANG_HINT:
                retry_prompt += "\n" + LANG_HINT[language]
            try:
                retry_result = self._engine.analyze_image(
                    image_path, existing_tags=[], existing_prompt=retry_prompt,
                    mode="ocr", format_json=True, json_schema=schema,
                )
                retry_raw = retry_result.raw_response or ""
                retry_ocr = self._parse_response(retry_raw, task, language)
                # Adopt retry result if better
                if manga_parse_quality(retry_ocr) > manga_parse_quality(ocr_result):
                    logger.info(
                        "Retry improved: %d regions -> %d regions",
                        len(ocr_result.regions), len(retry_ocr.regions),
                    )
                    return retry_ocr
            except Exception as exc:
                logger.warning("Manga OCR retry failed: %s", exc)

        return ocr_result

    def _parse_response(self, raw: str, task: str, language: str) -> OcrResult:
        """Parse VLM raw response into OcrResult."""
        if task == "ocr_document":
            data = extract_json_object(raw)
            return self._parse_document(data, raw, language)
        elif task == "ocr_manga":
            return self._parse_manga(raw, language)
        else:
            data = extract_json_object(raw)
            return self._parse_general(data, raw, language)

    def _parse_general(self, data: dict, raw: str, language: str) -> OcrResult:
        regions = []
        for i, r in enumerate(data.get("regions", [])):
            regions.append(OcrRegion(
                region_id=i + 1,
                bbox=r.get("bbox", []),
                text=r.get("text", ""),
                confidence=r.get("confidence", 0.0),
                direction=r.get("direction", "horizontal"),
                label=normalize_label(r.get("label", "")),
            ))
        full_text = data.get("full_text", "")
        if not full_text and regions:
            full_text = "\n".join(r.text for r in regions if r.text)
        if not full_text:
            full_text = fallback_text(raw)
        lang = data.get("language_detected", "") or data.get("language", "") or language
        return OcrResult(
            engine="",  # Set by caller
            task="ocr",
            regions=regions,
            full_text=full_text,
            language=lang if lang != "auto" else "",
            raw_response=raw,
        )

    def _parse_document(self, data: dict, raw: str, language: str) -> OcrResult:
        headings = data.get("headings", [])
        tables = data.get("tables", [])
        page_layout = data.get("page_layout", "")
        body_text = data.get("body_text", "")
        full_text = data.get("full_text", "") or body_text

        regions = []
        rid = 1
        for h in headings:
            regions.append(OcrRegion(
                region_id=rid, text=h, label="heading", direction="horizontal",
            ))
            rid += 1
        if body_text:
            regions.append(OcrRegion(
                region_id=rid, text=body_text, label="body", direction="horizontal",
            ))
            rid += 1

        if not full_text:
            full_text = fallback_text(raw)

        lang = data.get("language_detected", "") or language
        return OcrResult(
            engine="",
            task="ocr_document",
            regions=regions,
            full_text=full_text,
            language=lang if lang != "auto" else "",
            headings=headings,
            tables=tables,
            page_layout=page_layout,
            raw_response=raw,
        )

    def _parse_manga(self, raw: str, language: str) -> OcrResult:
        """Parse manga OCR response.

        VLM output format is unstable, so try in priority order:
        1. JSON array ([{"text":"...", "type":"..."}])
        2. JSON object ({"regions": [...]})
        3. Markdown / text (- text... or *"text"*)
        """
        regions = parse_manga_any_format(raw)

        # Synthesize full_text on this side (do not leave it to VLM)
        full_text = "\n".join(r.text for r in regions if r.text)
        if not full_text:
            full_text = fallback_text(raw)

        # Remove duplicate text
        regions = deduplicate_regions(regions)

        return OcrResult(
            engine="",
            task="ocr_manga",
            regions=regions,
            full_text=full_text,
            language=language if language != "auto" else "ja",
            raw_response=raw,
        )
