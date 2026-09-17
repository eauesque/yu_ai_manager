"""OpenAI-compatible API adapter for Hailo-10H GenAI.

This module is a compatibility shim that re-exports all public symbols
from the split sub-modules.  External callers (tests, hailo_genai_ext)
can continue to ``from hailo_openai_routes import ...`` unchanged.

Implementation is split into:
- ``openai_helpers``      -- constants, aliases, vision/audio/SSE helpers
- ``openai_chat_routes``  -- /v1/models, /v1/chat/completions
- ``openai_media_routes`` -- /v1/audio/transcriptions, /v1/embeddings
"""

# ── Re-exports from openai_helpers ───────────────────────────────
# ── Sub-module route registrars ──────────────────────────────────
from openai_chat_routes import register_openai_chat_routes
from openai_helpers import (  # noqa: F401
    _EMBEDDING_MODEL_ID,
    MODEL_ALIASES,
    _completion_id,
    _convert_to_wav,
    _embedding_id,
    _extract_images,
    _extract_text_messages,
    _has_images,
    _messages_to_hailo_format,
    _openai_error,
    _resolve_model,
    _sse_chunk,
    _ts,
)
from openai_media_routes import register_openai_media_routes


def register_openai_routes(bp):
    """Register all OpenAI-compatible endpoints on the Blueprint."""
    register_openai_chat_routes(bp)
    register_openai_media_routes(bp)
