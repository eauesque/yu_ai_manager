"""MCP tools for batch operations, annotations, and scan."""

from .server_tools_batch_annotations import register_batch_annotation_tools
from .server_tools_batch_ops import register_batch_operation_tools
from .server_tools_batch_scan import register_batch_scan_tools


def register_batch_tools(mcp, client) -> None:
    """Register batch operation, annotation, and scan tools."""
    register_batch_operation_tools(mcp, client)
    register_batch_annotation_tools(mcp, client)
    register_batch_scan_tools(mcp, client)
