"""Post-refactor smoke audit.

Validates that large refactor waves have not broken the runtime surface:

  1. MCP server   — imports `mcp_server.server` in-process and counts the
                    registered tools.
  2. HTTP routes  — spins up the Quart app via `create_app()` (after
                    `init_core_services`) and probes every GET endpoint
                    whose rule has no required path parameters, reporting
                    the status code distribution.

Run (Windows Git Bash):
    venv/Scripts/python scripts/audit_refactor.py
Run (Linux/macOS):
    venv/bin/python scripts/audit_refactor.py

Exit codes:
    0  no 500s observed, MCP imported successfully
    1  at least one 500 in the HTTP sweep, or an import failure
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import traceback
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def probe_mcp() -> tuple[bool, int, str]:
    """Import the MCP server and count its tools.

    Returns (ok, tool_count, detail)."""
    try:
        from mcp_server.server import mcp  # noqa: WPS433
    except Exception as exc:  # pragma: no cover - audit tool
        return False, 0, f"import failed: {exc}\n{traceback.format_exc()}"

    # FastMCP exposes `list_tools()` as async.
    try:
        tools = asyncio.run(mcp.list_tools())
    except Exception as exc:
        return False, 0, f"list_tools failed: {exc}"
    return True, len(tools), ""


def _build_app(db_path: Path):
    from core.paths import init_app_paths
    init_app_paths()  # idempotent; uses cwd defaults

    from core.extensions_core.service_registry_init import init_core_services
    from core.services_core.db_api import init_app_state
    from core.web.runtime_app import create_app

    config: dict = {}
    init_app_state(db_path, config)
    init_core_services(db_path=db_path)
    return create_app(db_path, config)


# Paths that never return (SSE streams) or that shell out to slow external
# binaries — excluded from the default sweep because they would always time
# out and drown real regressions. Pass `--include-streams` to sweep them.
_DEFAULT_SKIP_SUBSTRINGS = (
    "/stream",           # SSE endpoints never complete within per-request timeout
    "/secrets/op-vaults",  # shells out to 1Password CLI
)


def _collect_get_rules(app, *, include_streams: bool = False) -> list[str]:
    rules: list[str] = []
    for rule in app.url_map.iter_rules():
        methods = rule.methods or set()
        if "GET" not in methods:
            continue
        if not rule.rule.startswith("/api/"):
            continue
        # Skip rules with path parameters; we cannot synthesize valid values.
        if "<" in rule.rule:
            continue
        if not include_streams and any(s in rule.rule for s in _DEFAULT_SKIP_SUBSTRINGS):
            continue
        rules.append(rule.rule)
    return sorted(set(rules))


async def _sweep(
    app,
    rules: list[str],
    *,
    verbose: bool = False,
    per_timeout: float = 10.0,
) -> tuple[Counter, list[tuple[str, int]]]:
    client = app.test_client()
    buckets: Counter = Counter()
    failures: list[tuple[str, int]] = []
    total = len(rules)
    for idx, path in enumerate(rules, 1):
        try:
            resp = await asyncio.wait_for(client.get(path), timeout=per_timeout)
            code = resp.status_code
        except TimeoutError:
            code = -2
        except Exception:
            code = -1
        buckets[code] += 1
        if code >= 500 or code < 0:
            failures.append((path, code))
        if verbose:
            print(f"  [{idx:3d}/{total}] {code:>4}  {path}", flush=True)
    return buckets, failures


def probe_http(
    db_path: Path,
    *,
    verbose: bool = False,
    per_timeout: float = 10.0,
    limit: int | None = None,
    include_streams: bool = False,
) -> tuple[bool, dict, list[tuple[str, int]]]:
    try:
        app = _build_app(db_path)
    except Exception as exc:
        return False, {"error": str(exc), "trace": traceback.format_exc()}, []

    rules = _collect_get_rules(app, include_streams=include_streams)
    if limit is not None:
        rules = rules[:limit]
    if verbose:
        print(f"[HTTP] sweeping {len(rules)} GET endpoints...", flush=True)
    buckets, failures = asyncio.run(
        _sweep(app, rules, verbose=verbose, per_timeout=per_timeout)
    )
    summary = {
        "total": sum(buckets.values()),
        "by_status": dict(buckets),
    }
    return len(failures) == 0, summary, failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--db",
        default=str(ROOT / "tags.db"),
        help="SQLite DB path (default: tags.db)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON report",
    )
    parser.add_argument(
        "--skip-mcp",
        action="store_true",
        help="Skip MCP import/tool count",
    )
    parser.add_argument(
        "--skip-http",
        action="store_true",
        help="Skip HTTP endpoint sweep",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print per-endpoint progress lines",
    )
    parser.add_argument(
        "--per-timeout",
        type=float,
        default=10.0,
        help="Per-request timeout (seconds)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Only sweep the first N endpoints (smoke mode)",
    )
    parser.add_argument(
        "--include-streams",
        action="store_true",
        help="Include SSE/long-poll endpoints (default: skipped, they always time out)",
    )
    args = parser.parse_args()

    report: dict = {"mcp": None, "http": None, "ok": True}

    if not args.skip_mcp:
        ok, count, detail = probe_mcp()
        report["mcp"] = {"ok": ok, "tool_count": count, "detail": detail}
        if not ok:
            report["ok"] = False

    if not args.skip_http:
        ok, summary, failures = probe_http(
            Path(args.db),
            verbose=args.verbose,
            per_timeout=args.per_timeout,
            limit=args.limit,
            include_streams=args.include_streams,
        )
        report["http"] = {
            "ok": ok,
            "summary": summary,
            "failures": failures,
        }
        if not ok:
            report["ok"] = False

    if args.json:
        print(json.dumps(report, indent=2, ensure_ascii=False))
    else:
        if report["mcp"] is not None:
            m = report["mcp"]
            tag = "OK" if m["ok"] else "FAIL"
            print(f"[MCP ] {tag}  tools={m['tool_count']}")
            if not m["ok"]:
                print(m["detail"])
        if report["http"] is not None:
            h = report["http"]
            s = h["summary"]
            tag = "OK" if h["ok"] else "FAIL"
            print(f"[HTTP] {tag}  probed={s.get('total', 0)}  status={s.get('by_status', {})}")
            for path, code in h["failures"]:
                print(f"  500/err  {code}  {path}")

    return 0 if report["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
