"""Compatibility facade for search API services.

Route and internal code should prefer ``core.search_api.*`` concrete modules
when possible. This file remains for older import paths.
"""

from core.search_api import (
    build_search_response,
    build_server_info_response,
    build_suggest_embedding_response,
    build_suggest_lora_response,
    build_suggest_response,
)

__all__ = [
    "build_search_response",
    "build_server_info_response",
    "build_suggest_embedding_response",
    "build_suggest_lora_response",
    "build_suggest_response",
]
