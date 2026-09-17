"""Rust axum ルート ↔ MCP ツール参照パスの静的 parity チェッカー。

Python 版 check_mcp_parity.py と同じ2クラスの不整合を検出する:

  ERROR   MCP ツールが参照するパスに対応する axum .route() が存在しない。
          (pre-push でブロック — ツールが broken)

  WARNING axum ルートに対応する MCP ツール参照が存在しない。
          (Advisory のみ — MCP surface を持たないルートは正当)

Usage:
  uv run python scripts/check_rust_mcp_parity.py
  uv run python scripts/check_rust_mcp_parity.py --errors-only
  uv run python scripts/check_rust_mcp_parity.py --json
  uv run python scripts/check_rust_mcp_parity.py --no-warnings
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from dataclasses import dataclass
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
CRATES_DIR = REPO / "crates"

# ---------------------------------------------------------------------------
# Dynamic import of shared helpers from check_mcp_parity.py
# ---------------------------------------------------------------------------

def _import_mcp_parity():
    spec = importlib.util.spec_from_file_location(
        "check_mcp_parity",
        REPO / "scripts" / "check_mcp_parity.py",
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["check_mcp_parity"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_mcp = _import_mcp_parity()
load_exceptions = _mcp.load_exceptions
collect_mcp_paths = _mcp.collect_mcp_paths
MCPPathEntry = _mcp.MCPPathEntry
ParityError = _mcp.ParityError
ParityReport = _mcp.ParityReport
check_broken_mcp_paths = _mcp.check_broken_mcp_paths
check_uncovered_routes = _mcp.check_uncovered_routes
format_report = _mcp.format_report

# ---------------------------------------------------------------------------
# Rust route collection
# ---------------------------------------------------------------------------

# .route("/api/foo/{id}", get(handler))
# axum の MethodRouter は `get(h1).post(h2).put(h3)` のようにチェーンできるため、
# 先頭の1メソッドだけでなくチェーン全体を _extract_chained_methods() で走査する。
_ROUTE_RE = re.compile(
    r"""\.route\s*\(\s*"([^"]+)"\s*,\s*(get|post|put|delete|patch|head|options)\s*\(""",
    re.IGNORECASE,
)
_METHOD_CALL_RE = re.compile(
    r"""\.?\b(get|post|put|delete|patch|head|options)\s*\(""",
    re.IGNORECASE,
)


def _extract_chained_methods(content: str, route_call_start: int) -> list[str]:
    """`.route("path", get(h1).post(h2).put(h3))` の第2引数全体から
    チェーンされた全 HTTP メソッドを抽出する。`route_call_start` は
    `.route(` の直前（またはその `.`）の位置。

    第2引数の開始位置を、`.route(` の開き括弧から数えて最初のカンマの直後とし、
    そこから括弧の深さを追跡して `.route(...)` 呼出全体の終端（深さが0に戻る位置）
    までを対象にメソッド名を列挙する。
    """
    paren_start = content.index("(", route_call_start)
    # 第1引数（パス文字列）の後の最初のトップレベルカンマを探す。
    depth = 0
    i = paren_start
    arg2_start = None
    while i < len(content):
        c = content[i]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
            if depth == 0:
                break
        elif c == "," and depth == 1:
            arg2_start = i + 1
            break
        i += 1
    if arg2_start is None:
        return []

    depth = 1  # `.route(` の開き括弧の内側
    j = arg2_start
    while j < len(content) and depth > 0:
        c = content[j]
        if c == "(":
            depth += 1
        elif c == ")":
            depth -= 1
        j += 1
    arg2 = content[arg2_start:j]
    return [m.group(1).upper() for m in _METHOD_CALL_RE.finditer(arg2)]

# let p = "/ext/foo"; .route(&format!("{p}/bar"), get(handler))
_FORMAT_VAR_RE = re.compile(r'let\s+(\w+)\s*=\s*"(/[^"]+)"\s*;')
_FORMAT_ROUTE_RE = re.compile(
    r"""\.route\s*\(\s*&format!\s*\(\s*"\{(\w+)\}([^"]+)"\s*\)\s*,\s*(get|post|put|delete|patch|head|options)\s*\(""",
    re.IGNORECASE,
)

@dataclass
class RustRouteEntry:
    file: str       # relative to repo root
    line: int
    path: str       # raw path from .route(...)
    method: str     # GET / POST / ...
    normalized: str # path with {x} placeholders (axum already uses this form)


def collect_rust_routes(crates_dir: Path = CRATES_DIR) -> list[RustRouteEntry]:
    entries: list[RustRouteEntry] = []
    for rs_file in sorted(crates_dir.rglob("*.rs")):
        if any(p in ("target", ".cargo") for p in rs_file.parts):
            continue
        try:
            content = rs_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(rs_file.relative_to(REPO)).replace("\\", "/")
        for m in _ROUTE_RE.finditer(content):
            path = m.group(1)
            line = content[: m.start()].count("\n") + 1
            # axum already uses {param}; strip trailing slash for normalisation
            normalized = path.rstrip("/") or "/"
            methods = _extract_chained_methods(content, m.start()) or [m.group(2).upper()]
            for method in methods:
                entries.append(RustRouteEntry(
                    file=rel, line=line, path=path, method=method, normalized=normalized,
                ))
        # Secondary: detect .route(&format!("{p}/suffix"), method(handler))
        prefixes: dict[str, str] = {}
        for vm in _FORMAT_VAR_RE.finditer(content):
            prefixes[vm.group(1)] = vm.group(2)
        for m in _FORMAT_ROUTE_RE.finditer(content):
            var, suffix = m.group(1), m.group(2)
            if var in prefixes:
                path = prefixes[var] + suffix
                line = content[: m.start()].count("\n") + 1
                normalized = path.rstrip("/") or "/"
                methods = _extract_chained_methods(content, m.start()) or [m.group(3).upper()]
                for method in methods:
                    entries.append(RustRouteEntry(
                        file=rel, line=line, path=path, method=method, normalized=normalized,
                    ))
    return entries


# ---------------------------------------------------------------------------
# Parity checks (route-side adapted for RustRouteEntry)
# ---------------------------------------------------------------------------

def _route_matches_path(route: RustRouteEntry, path: str, is_prefix: bool) -> bool:
    """Return True if *path* (from an MCP client call) matches *route*.

    Mirrors check_mcp_parity._route_matches_path logic for Python routes.
    """
    if not path:
        return False
    if is_prefix:
        # prefix: MCP calls paths *under* this prefix.
        # A Rust route covers it if the route starts with the prefix,
        # OR the route's static portion (before first {param}) is covered by the prefix.
        # Segment-boundary guard: after the common prefix the next char must be '/' or end-of-string.
        def _seg_ok(s: str, prefix: str) -> bool:
            return s.startswith(prefix) and (
                len(s) == len(prefix) or s[len(prefix)] in ("/", "?")
            )

        route_static = route.normalized.split("{")[0]
        return _seg_ok(route.normalized, path) or (
            bool(route_static) and _seg_ok(path, route_static)
        )
    # Exact path match
    if route.normalized == path:
        return True
    # Pattern match when route has {param} placeholders
    if "{" in route.normalized:
        try:
            escaped = re.escape(route.normalized)
            pattern = re.sub(r"\\\{[^}]+\\\}", r"[^/]+", escaped)
            return bool(re.match(r"^" + pattern + r"$", path))
        except re.error:
            return False
    return False


def check_broken_rust_mcp_paths(
    routes: list[RustRouteEntry],
    mcp_paths: list[MCPPathEntry],
    exceptions: set[str],
) -> list[ParityError]:
    """MCP が参照するパスに対応する Rust ルートが存在しない → ERROR."""
    errors: list[ParityError] = []
    for ep in mcp_paths:
        if _mcp._is_excluded(ep.static_path, exceptions):
            continue
        if not (ep.static_path.startswith("/api/") or ep.static_path.startswith("/ext/")):
            continue
        if not any(_route_matches_path(r, ep.static_path, ep.is_prefix) for r in routes):
            errors.append(ParityError(
                level="ERROR",
                file=ep.file,
                line=ep.line,
                message=(
                    f"MCP references {'prefix ' if ep.is_prefix else ''}path "
                    f"{ep.static_path!r} but no matching Rust .route() exists"
                ),
                path=ep.static_path,
            ))
    return errors


def check_uncovered_rust_routes(
    routes: list[RustRouteEntry],
    mcp_paths: list[MCPPathEntry],
    exceptions: set[str],
) -> list[ParityError]:
    """Rust ルートに対応する MCP 参照が存在しない → WARNING."""
    warnings: list[ParityError] = []
    for route in routes:
        if _mcp._is_excluded(route.normalized, exceptions):
            continue
        # Skip internal / auth / non-API paths
        if not route.normalized.startswith("/api/"):
            continue
        if not any(_route_matches_path(route, ep.static_path, ep.is_prefix) for ep in mcp_paths):
            warnings.append(ParityError(
                level="WARNING",
                file=route.file,
                line=route.line,
                message=(
                    f"Rust route {route.method} {route.normalized!r} "
                    f"has no MCP tool referencing it"
                ),
                path=route.normalized,
            ))
    return warnings


def run_rust_parity_check(
    crates_dir: Path = CRATES_DIR,
    include_warnings: bool = True,
) -> ParityReport:
    exceptions = load_exceptions()
    routes = collect_rust_routes(crates_dir)
    mcp_paths = collect_mcp_paths()

    errors = check_broken_rust_mcp_paths(routes, mcp_paths, exceptions)
    warnings = check_uncovered_rust_routes(routes, mcp_paths, exceptions) if include_warnings else []

    return ParityReport(errors=errors, warnings=warnings)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def format_rust_report(report: ParityReport, *, json_out: bool = False) -> str:
    if json_out:
        items = [
            {"level": e.level, "file": e.file, "line": e.line,
             "path": e.path, "message": e.message}
            for e in report.errors + report.warnings
        ]
        return json.dumps({"errors": len(report.errors), "warnings": len(report.warnings),
                           "items": items}, ensure_ascii=False, indent=2)

    lines: list[str] = []
    if report.errors:
        lines.append(f"\n{'─'*60}")
        lines.append(f"ERRORS ({len(report.errors)})")
        lines.append(f"{'─'*60}")
        for e in report.errors:
            lines.append(f"  {e.file}:{e.line}  {e.message}")
    if report.warnings:
        lines.append(f"\n{'─'*60}")
        lines.append(f"WARNINGS ({len(report.warnings)})")
        lines.append(f"{'─'*60}")
        for w in report.warnings:
            lines.append(f"  {w.file}:{w.line}  {w.message}")
    if not report.errors and not report.warnings:
        lines.append("✅ Rust ルート ↔ MCP parity OK")
    else:
        lines.append(
            f"\n合計: {len(report.errors)} error(s), {len(report.warnings)} warning(s)"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Rust axum ↔ MCP parity checker")
    ap.add_argument("--errors-only", action="store_true", help="エラーのみ表示")
    ap.add_argument("--no-warnings", action="store_true", help="WARNING を抑制")
    ap.add_argument("--json", action="store_true", help="JSON 出力")
    args = ap.parse_args(argv)

    include_warnings = not (args.errors_only or args.no_warnings)
    report = run_rust_parity_check(include_warnings=include_warnings)

    print(format_rust_report(report, json_out=args.json))

    return 1 if report.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
