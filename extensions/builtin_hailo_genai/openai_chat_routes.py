"""OpenAI-compatible chat completions and model listing routes facade."""

from __future__ import annotations

try:
    from .openai_chat_route_handlers import register_openai_chat_route_handlers
except ImportError:  # pragma: no cover - top-level extension import path
    from openai_chat_route_handlers import register_openai_chat_route_handlers


def register_openai_chat_routes(bp):
    register_openai_chat_route_handlers(bp)
