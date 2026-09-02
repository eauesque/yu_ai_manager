"""MCP tools for OCR operations.

Re-exports from ocr_tools_core and ocr_tools_advanced for backward compatibility.
"""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_tools_advanced import register_ocr_advanced_tools
from .ocr_tools_core import register_ocr_core_tools


def register_ocr_tools(mcp: FastMCP, client: YuManagerClient):
    """Register all OCR tools (core + advanced)."""
    register_ocr_core_tools(mcp, client)
    register_ocr_advanced_tools(mcp, client)
