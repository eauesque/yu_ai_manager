"""Shared helpers for MCP debug tools."""

import json
from typing import Any

from .client import YuManagerClient


def _g(d: Any, key: str, fallback: Any = None) -> Any:
    """Safe get: returns fallback when key is missing OR value is None."""
    if not isinstance(d, dict):
        return fallback
    v = d.get(key)
    return v if v is not None else fallback


def _json(data: Any) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2)


def _sql(client: YuManagerClient, sql: str, limit: int = 100) -> dict:
    """Execute a readonly SQL query via the debug endpoint."""
    return client.post("/api/debug/query", {"sql": sql, "limit": limit})


def _check(name: str, status: str, **kw: Any) -> dict[str, Any]:
    """Build a single check result dict."""
    return {"name": name, "status": status, **kw}


def _summarize(checks: list[dict]) -> dict[str, Any]:
    """Summarize a list of check results."""
    passed = sum(1 for c in checks if c["status"] == "pass")
    failed = sum(1 for c in checks if c["status"] == "fail")
    return {
        "ok": failed == 0,
        "passed": passed,
        "failed": failed,
        "total": len(checks),
        "checks": checks,
    }
