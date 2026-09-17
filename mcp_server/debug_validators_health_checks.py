"""Health check validator implementation."""


from .client import YuManagerClient
from .debug_helpers import _check, _g, _json, _sql, _summarize


def health_check(client: YuManagerClient) -> str:
    checks: list[dict] = []
    stats = client.get("/api/stats/all")
    if stats.get("ok") is False:
        checks.append(_check("flask_reachable", "fail", error=stats.get("error")))
        return _json(_summarize(checks))
    checks.append(_check("flask_reachable", "pass"))

    table_result = _sql(client, "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    if table_result.get("ok") is False:
        checks.append(_check("tables_exist", "fail", error=table_result.get("error")))
    else:
        names = [row["name"] for row in table_result.get("rows", [])]
        required = ["files", "tags", "file_tags", "templates", "schema_version"]
        missing = [name for name in required if name not in names]
        checks.append(_check("tables_exist", "fail" if missing else "pass", missing=missing) if missing else _check("tables_exist", "pass", tables=names))

    version_result = _sql(client, "SELECT MAX(version) as v FROM schema_version")
    if version_result.get("rows"):
        checks.append(_check("schema_version", "pass", version=version_result["rows"][0].get("v")))
    else:
        checks.append(_check("schema_version", "warn", detail="no version row"))

    basic = _g(_g(stats, "data", stats), "basic", {})
    checks.append(_check("file_count", "pass", file_count=basic.get("file_count"), total_files=basic.get("total_files")))
    return _json(_summarize(checks))
