"""MCP tools for advanced OCR operations."""

from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .ocr_tools_advanced_media import register_ocr_advanced_media_tools
from .ocr_tools_advanced_ops import register_ocr_advanced_ops_tools


def register_ocr_advanced_tools(mcp: FastMCP, client: YuManagerClient):
    """Register advanced OCR tools."""
    register_ocr_advanced_ops_tools(mcp, client)
    register_ocr_advanced_media_tools(mcp, client)
