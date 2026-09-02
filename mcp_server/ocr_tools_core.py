"""MCP tools for basic OCR operations."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_tools_core_extract import register_ocr_core_extract_tools
from .ocr_tools_core_output import register_ocr_core_output_tools


def register_ocr_core_tools(mcp: FastMCP, client: YuManagerClient):
    """Register basic OCR tools."""
    register_ocr_core_extract_tools(mcp, client)
    register_ocr_core_output_tools(mcp, client)
