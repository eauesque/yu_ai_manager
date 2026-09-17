"""Automatic language detection utility.

Uses the langdetect library to determine the language of text.
Short text (fewer than 10 characters) has high misdetection risk and returns unknown.
Also reports scores for low-confidence cases such as prompts with mixed Danbooru tags.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# langdetect is lazily imported (allows startup even when not installed)
_langdetect_available: bool | None = None

# Language code -> language name
LANG_NAMES = {
    "ja": "日本語",
    "en": "English",
    "zh": "中文",
    "ko": "한국어",
    "fr": "Français",
    "de": "Deutsch",
    "es": "Español",
    "pt": "Português",
    "ru": "Русский",
    "ar": "العربية",
}

# Minimum text length (below this, detection is unreliable)
MIN_TEXT_LENGTH = 10

# Confidence thresholds
CONFIDENCE_HIGH = 0.8
CONFIDENCE_LOW = 0.5

# Danbooru tag patterns (English comma-separated, underscore-separated)
_DANBOORU_TAG_RE = re.compile(
    r'(?:^|,\s*)(?:\d+(?:girl|boy)|'
    r'[a-z_]+(?:_[a-z_]+)+|'
    r'(?:masterpiece|best quality|highres|absurdres|'
    r'solo|multiple girls|looking at viewer|smile|'
    r'open mouth|closed eyes|blush|long hair|short hair|'
    r'blonde hair|blue eyes|red eyes|school uniform|'
    r'white background|simple background|upper body|full body))',
    re.IGNORECASE,
)


@dataclass
class LangDetectResult:
    """Language detection result."""

    lang: str
    """ISO 639-1 language code (e.g. "ja", "en") or "unknown"."""

    confidence: float
    """Confidence score (0.0 to 1.0)."""

    is_mixed: bool = False
    """Whether multiple languages are mixed."""

    all_langs: list[dict] | None = None
    """List of all detected languages and their scores."""

    def to_dict(self) -> dict:
        d = {
            "lang": self.lang,
            "confidence": round(self.confidence, 3),
            "is_mixed": self.is_mixed,
        }
        if self.all_langs:
            d["all_langs"] = self.all_langs
        return d

    @property
    def lang_name(self) -> str:
        """Return a human-readable language name."""
        return LANG_NAMES.get(self.lang, self.lang)

    @property
    def is_reliable(self) -> bool:
        """Whether the confidence is sufficient."""
        return self.confidence >= CONFIDENCE_HIGH


def _normalize_lang(lang: str) -> str:
    """Normalize language code to ISO 639-1 (2 characters).

    langdetect may return sub-tags like "zh-cn", "zh-tw".
    """
    if "-" in lang:
        return lang.split("-")[0]
    return lang


def _ensure_langdetect() -> bool:
    """Check whether the langdetect library is available."""
    global _langdetect_available
    if _langdetect_available is not None:
        return _langdetect_available
    try:
        import langdetect  # noqa: F401
        _langdetect_available = True
    except ImportError:
        logger.warning("langdetect がインストールされていません: uv pip install langdetect")
        _langdetect_available = False
    return _langdetect_available


def detect_language(text: str) -> LangDetectResult:
    """Detect the language of the given text.

    Args:
        text: Text to analyze.

    Returns:
        LangDetectResult: Language code, confidence, and mixed-language flag.
    """
    if not text or not text.strip():
        return LangDetectResult(lang="unknown", confidence=0.0)

    cleaned = text.strip()

    # Text too short for reliable detection
    if len(cleaned) < MIN_TEXT_LENGTH:
        return LangDetectResult(lang="unknown", confidence=0.0)

    if not _ensure_langdetect():
        return LangDetectResult(lang="unknown", confidence=0.0)

    from langdetect import detect_langs
    from langdetect.lang_detect_exception import LangDetectException

    try:
        results = detect_langs(cleaned)
    except LangDetectException:
        return LangDetectResult(lang="unknown", confidence=0.0)

    if not results:
        return LangDetectResult(lang="unknown", confidence=0.0)

    top = results[0]
    all_langs = [{"lang": _normalize_lang(str(r.lang)), "score": round(r.prob, 3)} for r in results]

    # Mixed language detection: if 2nd language has a significant score
    is_mixed = len(results) >= 2 and results[1].prob >= 0.2

    return LangDetectResult(
        lang=_normalize_lang(str(top.lang)),
        confidence=round(top.prob, 3),
        is_mixed=is_mixed,
        all_langs=all_langs if is_mixed or top.prob < CONFIDENCE_HIGH else None,
    )


def detect_prompt_language(prompt: str) -> LangDetectResult:
    """Detect the language of an AI image generation prompt.

    Danbooru tags (English) and natural language text may be mixed.
    Excludes tag portions before analyzing the natural language part;
    returns all language scores when confidence is low.

    Args:
        prompt: Prompt text (positive or negative).

    Returns:
        LangDetectResult: Language code, confidence, and mixed-language flag.
    """
    if not prompt or not prompt.strip():
        return LangDetectResult(lang="unknown", confidence=0.0)

    cleaned = prompt.strip()

    # Text too short for reliable detection
    if len(cleaned) < MIN_TEXT_LENGTH:
        return LangDetectResult(lang="unknown", confidence=0.0)

    if not _ensure_langdetect():
        return LangDetectResult(lang="unknown", confidence=0.0)

    # Remove Danbooru tags and extract natural language parts
    natural_text = _extract_natural_text(cleaned)

    # If enough natural language text exists, use it for detection
    if natural_text and len(natural_text) >= MIN_TEXT_LENGTH:
        result = detect_language(natural_text)
        # Flag indicating tag mixture
        if natural_text != cleaned:
            result.is_mixed = True
            # Add all_langs if absent (for confidence score reporting)
            if result.all_langs is None:
                from langdetect import detect_langs
                from langdetect.lang_detect_exception import LangDetectException
                try:
                    langs = detect_langs(natural_text)
                    result.all_langs = [
                        {"lang": str(r.lang), "score": round(r.prob, 3)}
                        for r in langs
                    ]
                except LangDetectException:
                    pass
        return result

    # If no natural language text, assume tags only
    # Tags-only content is mostly English Danbooru tags
    tag_count = len(_DANBOORU_TAG_RE.findall(cleaned))
    if tag_count >= 3:
        return LangDetectResult(
            lang="en",
            confidence=0.6,
            is_mixed=False,
            all_langs=[{"lang": "en", "score": 0.6}],
        )

    # Fallback: detect on entire text
    return detect_language(cleaned)


def _extract_natural_text(prompt: str) -> str:
    """Extract natural language text from a prompt, excluding Danbooru tags.

    Analyzes comma-separated tokens and removes underscore-separated
    English words and known tag patterns.
    """
    tokens = [t.strip() for t in prompt.split(",")]
    natural_parts = []

    for token in tokens:
        if not token:
            continue

        # Remove weight notation: {text}, (text), <lora:...>
        clean = re.sub(r'[{}\[\]<>]', '', token).strip()
        clean = re.sub(r'\(([^)]*)\)', r'\1', clean).strip()
        # Skip numeric-only tokens and weight values (e.g. 1.2)
        if re.match(r'^[\d.:]+$', clean):
            continue
        # Skip lora/embedding directives
        if clean.lower().startswith(('lora:', 'embedding:', 'hypernetwork:')):
            continue

        # Underscore-separated English words = tag
        if re.match(r'^[a-zA-Z0-9_]+$', clean) and '_' in clean:
            continue

        # Known Danbooru tag patterns
        if _DANBOORU_TAG_RE.match(clean):
            continue

        # Short English-only tokens are likely tags
        if re.match(r'^[a-zA-Z\s]{1,20}$', clean) and len(clean.split()) <= 2:
            # But keep common English text (3+ words)
            continue

        natural_parts.append(clean)

    return ", ".join(natural_parts)
