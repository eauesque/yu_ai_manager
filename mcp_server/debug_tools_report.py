"""Aggregated report builder for debug MCP tools."""

import json
from typing import Any

from .client import YuManagerClient
from .debug_helpers import _check, _json, _summarize
from .debug_validators import health_check, validate_annotations, validate_collection, validate_counts, validate_search


def full_debug_report(client: YuManagerClient) -> str:
    """Run all validation tools and aggregate results."""
    sections: dict[str, Any] = {}
    all_checks: list[dict] = []
    for name, fn in [
        ("health_check", lambda: health_check(client)),
        ("validate_counts", lambda: validate_counts(client)),
        ("validate_search", lambda: validate_search(client)),
        ("validate_collection", lambda: validate_collection(client)),
        ("validate_annotations", lambda: validate_annotations(client)),
    ]:
        try:
            raw = json.loads(fn())
            sections[name] = raw
            all_checks.extend(raw.get("checks", []))
        except Exception as e:
            sections[name] = {"ok": False, "error": str(e)}
            all_checks.append(_check(name, "fail", error=str(e)))

    summary = _summarize(all_checks)
    bugs_found = [check for check in all_checks if check["status"] == "fail"]
    warnings = [check for check in all_checks if check["status"] == "warn"]
    return _json({
        "summary": {
            "ok": summary["ok"],
            "passed": summary["passed"],
            "failed": summary["failed"],
            "warnings": len(warnings),
            "total": summary["total"],
        },
        "bugs_found": bugs_found,
        "warnings": warnings,
        "sections": sections,
    })
