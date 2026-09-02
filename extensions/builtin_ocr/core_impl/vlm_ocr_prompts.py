"""VLM OCR prompts, JSON schemas, and label normalization constants."""

from __future__ import annotations

# ── Task-specific prompts ──
# VLM output format is unstable (JSON/Markdown/text), so
# provide many few-shot examples and force JSON output at API level with format_json=True.
# Parser side also handles all formats (JSON array, JSONL, Markdown, text).

PROMPTS = {
    "ocr": (
        "Read all text in this image. Output the text exactly as written.\n"
        "Reply with JSON only:\n"
        '{"full_text": "all text here", "language": "detected language code"}'
    ),
    "ocr_document": (
        "Read all text in this document image in reading order.\n"
        "Separate headings from body text.\n"
        "Reply with JSON only:\n"
        '{"headings": ["..."], "body_text": "...", "full_text": "all text"}'
    ),
    "ocr_manga": (
        "Read ALL text in this manga/comic page. "
        "Include every speech bubble, sound effect (SFX), narration box, sign, and title.\n"
        "For Japanese manga, read right-to-left, top-to-bottom.\n\n"
        "You MUST reply with a JSON array. Each element has \"text\" and \"type\".\n"
        "Valid types: speech, sfx, narration, sign, title, other\n\n"
        "Example output for a page with 3 text elements:\n"
        "[\n"
        '  {"text": "おはよう", "type": "speech"},\n'
        '  {"text": "ドン！！", "type": "sfx"},\n'
        '  {"text": "次の日——", "type": "narration"}\n'
        "]\n\n"
        "Now read this image and output the JSON array:"
    ),
}

# Simplified prompt for retry (used after first attempt failure)
MANGA_RETRY_PROMPT = (
    "List all text in this manga page as a JSON array.\n"
    "Format: [{\"text\": \"...\", \"type\": \"speech\"}]\n"
    "Types: speech, sfx, narration, sign, title, other\n"
    "Output ONLY the JSON array, nothing else."
)

# JSON Schema for Ollama Structured Output
# Enforce schema at token generation level (supported models only)
MANGA_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "type": {
                        "type": "string",
                        "enum": ["speech", "sfx", "narration",
                                 "sign", "title", "other"],
                    },
                },
                "required": ["text", "type"],
            },
        },
    },
    "required": ["items"],
}

OCR_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "full_text": {"type": "string"},
        "language": {"type": "string"},
    },
    "required": ["full_text"],
}

# Language specification prompt
LANG_HINT = {
    "ja": "The text is primarily in Japanese. Output text in Japanese.",
    "en": "The text is primarily in English. Output text in English.",
    "zh": "The text is primarily in Chinese. Output text in Chinese.",
    "ko": "The text is primarily in Korean. Output text in Korean.",
}

# VLM returned type name -> normalized label
LABEL_NORMALIZE = {
    # speech types
    "speech": "speech_bubble",
    "speech_bubble": "speech_bubble",
    "speechbubble": "speech_bubble",
    "dialogue": "speech_bubble",
    "dialog": "speech_bubble",
    "bubble": "speech_bubble",
    "セリフ": "speech_bubble",
    "台詞": "speech_bubble",
    "吹き出し": "speech_bubble",
    # thought types
    "thought": "thought_bubble",
    "thought_bubble": "thought_bubble",
    "thinking": "thought_bubble",
    # sfx types
    "sfx": "sfx",
    "sound": "sfx",
    "sound_effect": "sfx",
    "sound effect": "sfx",
    "onomatopoeia": "sfx",
    "効果音": "sfx",
    "se": "sfx",
    # narration types
    "narration": "narration",
    "narrator": "narration",
    "caption": "caption",
    "ナレーション": "narration",
    "キャプション": "caption",
    # sign types
    "sign": "sign",
    "label": "sign",
    "看板": "sign",
    "表示": "sign",
    # title types
    "title": "title",
    "heading": "title",
    "chapter": "title",
    "タイトル": "title",
    # other
    "other": "other",
    "text": "other",
    "その他": "other",
}


def normalize_label(raw_label: str) -> str:
    """Normalize VLM-returned label to a canonical form."""
    if not raw_label:
        return "speech_bubble"
    key = raw_label.strip().lower()
    return LABEL_NORMALIZE.get(key, "speech_bubble")
