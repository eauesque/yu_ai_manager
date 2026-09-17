"""Hailo Chat web search facade."""

from .web_search_format import format_search_context
from .web_search_query import search_web

__all__ = ["format_search_context", "search_web"]

