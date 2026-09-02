"""Registry construction helpers for Hailo GenAI models."""

from __future__ import annotations

import logging

try:
    from .genai_types import GenAIModelInfo, GenAIModelType
    from .model_manifest_cache import fetch_remote_manifest, load_cached_manifest, save_cached_manifest
    from .model_manifest_parse import ParsedModel, parse_models_rst
except ImportError:  # pragma: no cover - top-level extension import path
    from genai_types import GenAIModelInfo, GenAIModelType
    from model_manifest_cache import fetch_remote_manifest, load_cached_manifest, save_cached_manifest
    from model_manifest_parse import ParsedModel, parse_models_rst

logger = logging.getLogger(__name__)

MODEL_OVERRIDES = {
    "Qwen2.5-1.5B-Instruct.hef": {
        "name": "qwen2.5-1.5b-chat",
        "description": "Qwen 2.5 1.5B Chat (general purpose)",
    },
    "Llama3.2-1B-Instruct.hef": {
        "name": "llama3.2-1b",
        "description": "Llama 3.2 1B Instruct",
    },
    "DeepSeek-R1-Distill-Qwen-1.5B.hef": {
        "name": "deepseek-r1-1.5b",
        "description": "DeepSeek R1 1.5B (reasoning)",
    },
    "Qwen2.5-Coder-1.5B-Instruct.hef": {
        "name": "qwen2.5-coder-1.5b",
        "description": "Qwen 2.5 Coder 1.5B (code generation)",
    },
    "Qwen3-1.7B-Instruct.hef": {
        "name": "qwen3-1.7b-instruct",
        "description": "Qwen 3 1.7B Instruct (general purpose, default)",
    },
    "Qwen3-VL-2B-Instruct.hef": {
        "name": "qwen3-vl-2b-instruct",
        "description": "Qwen3 VL 2B (image/video understanding)",
    },
    "Qwen2-VL-2B-Instruct.hef": {
        "name": "qwen2-vl-2b-instruct",
        "description": "Qwen2 VL 2B (image/video understanding)",
    },
    "Whisper-Base.hef": {
        "name": "whisper-base",
        "description": "Whisper Base (fast, English-optimised)",
    },
    "Whisper-Small.hef": {
        "name": "whisper-small",
        "description": "Whisper Small (better accuracy)",
    },
}

BUNDLED_ROWS = [
    {"section": "Language Models", "hef_filename": "DeepSeek-R1-Distill-Qwen-1.5B.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/DeepSeek-R1-Distill-Qwen-1.5B.hef"},
    {"section": "Language Models", "hef_filename": "Llama3.2-1B-Instruct.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Llama3.2-1B-Instruct.hef"},
    {"section": "Language Models", "hef_filename": "Qwen2.5-1.5B-Instruct.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Qwen2.5-1.5B-Instruct.hef"},
    {"section": "Language Models", "hef_filename": "Qwen2.5-Coder-1.5B-Instruct.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Qwen2.5-Coder-1.5B-Instruct.hef"},
    {"section": "Language Models", "hef_filename": "Qwen3-1.7B-Instruct.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Qwen3-1.7B-Instruct.hef"},
    {"section": "Multimodal Vision-Language Models", "hef_filename": "Qwen2-VL-2B-Instruct.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Qwen2-VL-2B-Instruct.hef"},
    {"section": "Multimodal Vision-Language Models", "hef_filename": "Qwen3-VL-2B-Instruct.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Qwen3-VL-2B-Instruct.hef"},
    {"section": "Speech Recognition (Whisper)", "hef_filename": "Whisper-Tiny.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Whisper-Tiny.hef"},
    {"section": "Speech Recognition (Whisper)", "hef_filename": "Whisper-Base.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Whisper-Base.hef"},
    {"section": "Speech Recognition (Whisper)", "hef_filename": "Whisper-Small.hef", "url": "https://dev-public.hailo.ai/v5.3.0/blob/Whisper-Small.hef"},
]


def classify_by_filename(filename: str) -> GenAIModelType:
    if filename.startswith("Whisper-"):
        return GenAIModelType.SPEECH2TEXT
    if "-VL-" in filename:
        return GenAIModelType.VLM
    return GenAIModelType.LLM


def auto_name(filename: str) -> str:
    return filename.removesuffix(".hef").lower()


def auto_description(filename: str) -> str:
    return filename.removesuffix(".hef").replace("-", " ")


def rows_to_registry(rows) -> dict[str, GenAIModelInfo]:
    registry: dict[str, GenAIModelInfo] = {}
    for row in rows:
        if isinstance(row, ParsedModel):
            filename, url = row.hef_filename, row.url
        else:
            filename, url = row["hef_filename"], row["url"]
        override = MODEL_OVERRIDES.get(filename, {})
        name = override.get("name", auto_name(filename))
        description = override.get("description", auto_description(filename))
        registry[name] = GenAIModelInfo(
            name=name,
            type=classify_by_filename(filename),
            hef_filename=filename,
            description=description,
            url=url,
        )
    return registry


def build_models_registry(version: str) -> dict[str, GenAIModelInfo]:
    text = fetch_remote_manifest(version)
    if text:
        rows = parse_models_rst(text)
        if rows:
            registry = rows_to_registry(rows)
            if registry:
                save_cached_manifest(version, rows)
                return registry

    cached = load_cached_manifest(version)
    if cached:
        registry = rows_to_registry(cached)
        if registry:
            return registry

    logger.info(
        "Using bundled Hailo GenAI model registry (v%s); remote fetch and cache both unavailable",
        version,
    )
    return rows_to_registry(BUNDLED_ROWS)
