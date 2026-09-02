"""MCP debug tools for YU AI Manager."""

from mcp.server.fastmcp import FastMCP

from .client import YuManagerClient
from .debug_helpers import _json, _sql
from .debug_roundtrip import roundtrip_test
from .debug_tools_report import full_debug_report
from .debug_validators import (
    health_check,
    sample_files,
    validate_annotations,
    validate_collection,
    validate_counts,
    validate_search,
)
from .validators import validate_debug_limit


def register_debug_tools(mcp: FastMCP, client: YuManagerClient) -> None:
    """Register all debug tools on the MCP server instance."""

    @mcp.tool(description="Run a basic health check against the YU AI Manager backend.")
    def debug_health_check() -> str:
        return health_check(client)

    @mcp.tool(description="Validate aggregate database counts and consistency checks.")
    def debug_validate_counts() -> str:
        return validate_counts(client)

    @mcp.tool(description="Validate representative search patterns against the backend.")
    def debug_validate_search(patterns: str = "all") -> str:
        return validate_search(client)

    @mcp.tool(description="Validate collection APIs and collection-linked search behavior.")
    def debug_validate_collection() -> str:
        return validate_collection(client)

    @mcp.tool(description="Validate annotation APIs and annotation persistence behavior.")
    def debug_validate_annotations() -> str:
        return validate_annotations(client)

    @mcp.tool(description="Sample files and selected metadata fields for debugging.")
    def debug_sample_files(n: int = 50, fields: str = "meta_source,width,height") -> str:
        return sample_files(client, n, fields)

    @mcp.tool(description="Run a debug roundtrip test against the backend.")
    def debug_roundtrip_test() -> str:
        return roundtrip_test(client)

    @mcp.tool(description="Execute a readonly SQL query for debugging with a result limit.")
    def debug_readonly_query(sql: str, limit: int = 100) -> str:
        err = validate_debug_limit(limit)
        if err:
            return err
        return _json(_sql(client, sql, limit))

    @mcp.tool(description="Generate a combined debug report from health and validation tools.")
    def debug_full_report() -> str:
        return full_debug_report(client)
