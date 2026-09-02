"""MCP ↔ HTTP API parity checker.

Detects two classes of mismatches:

  ERROR   MCP tool calls a path that has no matching @bp.route in the codebase.
          (Blocked at pre-push — tool is broken.)

  WARNING API route has no MCP tool referencing it.
          (Advisory only — route may intentionally lack an MCP surface.)

Usage:
  python scripts/check_mcp_parity.py             # human-readable report
  python scripts/check_mcp_parity.py --errors-only
  python scripts/check_mcp_parity.py --json
  python scripts/check_mcp_parity.py --no-warnings
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Exceptions / exclusion list
# ---------------------------------------------------------------------------

_EXCEPTIONS_FILE = REPO / "scripts" / "mcp_parity_exceptions.txt"
_NATIVE_ONLY_ENDPOINTS_FILE = REPO / "docs" / "development" / "native-only-endpoints.yaml"


def load_exceptions() -> set[str]:
    """Load path prefixes / exact paths to exclude from parity checks.

    Lines starting with '#' are comments.  Blank lines are ignored.
    Entries are matched as prefixes against both route paths and MCP paths.
    """
    if not _EXCEPTIONS_FILE.exists():
        return set()
    lines: set[str] = set()
    for raw in _EXCEPTIONS_FILE.read_text(encoding="utf-8").splitlines():
        stripped = raw.strip()
        if stripped and not stripped.startswith("#"):
            lines.add(stripped)
    return lines


def _is_excluded(path: str, exceptions: set[str]) -> bool:
    return any(path == exc or path.startswith(exc) for exc in exceptions)


# ---------------------------------------------------------------------------
# Route collection
# ---------------------------------------------------------------------------

_BP_ROUTE_RE = re.compile(
    r"""@\w+\.route\(\s*["']([^"']+)["']""",
)
# Also catch bp.add_url_rule("/path", ...) — spans multiple lines, so applied to full content
_ADD_URL_RULE_RE = re.compile(
    r"""\w+\.add_url_rule\s*\(\s*["']([^"']+)["']""",
    re.DOTALL,
)
_URL_PREFIX_RE = re.compile(
    r"""Blueprint\s*\([^)]*url_prefix\s*=\s*["']([^"']+)["']""",
)
# Detect module-level (non-indented) Blueprint definition
_MODULE_LEVEL_BP_RE = re.compile(r"""^bp\s*=\s*Blueprint\s*\(""", re.MULTILINE)
# Normalize Flask route params:  <int:name> / <string:name> / <name>  → {name}
_PARAM_RE = re.compile(r"<(?:[^:>]+:)?([^>]+)>")


def _normalize_route_path(path: str) -> str:
    """Replace Flask route parameters with {name} placeholders."""
    return _PARAM_RE.sub(r"{\1}", path)


def _route_to_regex(normalized: str) -> re.Pattern:
    """Convert a normalized route path (with {x} placeholders) to a regex."""
    escaped = re.escape(normalized)
    pattern = re.sub(r"\\{[^}]+\\}", r"[^/]+", escaped)
    return re.compile(r"^" + pattern + r"$")


@dataclass
class RouteEntry:
    file: str          # relative to repo root
    line: int
    path: str          # raw path from @bp.route(...)
    normalized: str    # after normalizing <int:x> → {x}
    full_path: str     # with blueprint prefix applied


def _find_extension_prefix(py_file: Path) -> str | None:
    """Walk up from py_file to find extension.json and return blueprint_prefix."""
    parts = py_file.parts
    # Look for 'extensions' in path, then find the extension root one level below
    try:
        ext_idx = parts.index("extensions")
    except ValueError:
        return None
    if ext_idx + 1 >= len(parts):
        return None
    ext_root = Path(*parts[: ext_idx + 2])
    manifest = ext_root / "extension.json"
    if not manifest.exists():
        return None
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
        prefix = data.get("blueprint_prefix")
        if prefix is None:
            # Auto-derive from name: "builtin-foo-bar" → "/ext/foo_bar"
            name: str = data.get("name", "")
            safe = name.replace("builtin-", "").replace("-", "_")
            return f"/ext/{safe}" if safe else ""
        # Normalize: "/" prefix means root-mounted (no prefix)
        if prefix == "/":
            return ""
        return prefix.rstrip("/")
    except Exception:
        return None


def _extract_blueprint_url_prefix(content: str) -> str:
    """Extract url_prefix from Blueprint(...) constructor in file content."""
    m = _URL_PREFIX_RE.search(content)
    if m:
        return m.group(1).rstrip("/")
    return ""


def collect_routes(repo: Path = REPO) -> list[RouteEntry]:
    """Collect Python and native-only API route declarations."""
    entries: list[RouteEntry] = []

    scan_dirs = [
        repo / "routes",
        repo / "extensions",
        repo / "core",
    ]

    for base in scan_dirs:
        if not base.exists():
            continue
        for py_file in base.rglob("*.py"):
            # Skip __pycache__ and venv
            if any(part in (".venv", "__pycache__", "venv", "tmp") for part in py_file.parts):
                continue
            try:
                content = py_file.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue

            # Determine blueprint prefix for this file
            rel = py_file.relative_to(repo)
            rel_str = str(rel).replace("\\", "/")

            if rel_str.startswith("extensions/"):
                # Extension files: two registration patterns exist.
                #
                # 1. Module-level `bp = Blueprint(...)` — the file owns its own
                #    blueprint and is imported directly (core-shim pattern).
                #    The blueprint is registered without the extension prefix.
                #    → Use the url_prefix from the Blueprint constructor (usually "").
                #
                # 2. Routes inside `def register_*(bp, ...)` functions — the bp
                #    is passed in from get_blueprint() and carries the extension prefix.
                #    → Use extension.json blueprint_prefix.
                if _MODULE_LEVEL_BP_RE.search(content):
                    file_prefix = _extract_blueprint_url_prefix(content)
                else:
                    ext_prefix = _find_extension_prefix(py_file)
                    file_prefix = ext_prefix if ext_prefix is not None else ""
            else:
                # routes/ or core/: check for Blueprint url_prefix in the same file
                file_prefix = _extract_blueprint_url_prefix(content)

            # Collect matches: (line_no, raw_path) from both patterns
            route_matches: list[tuple[int, str]] = []
            for match in _BP_ROUTE_RE.finditer(content):
                line_no = content[: match.start()].count("\n") + 1
                route_matches.append((line_no, match.group(1)))
            for match in _ADD_URL_RULE_RE.finditer(content):
                line_no = content[: match.start()].count("\n") + 1
                route_matches.append((line_no, match.group(1)))

            for line_no, raw_path in route_matches:
                normalized = _normalize_route_path(raw_path)
                # Build full path: prefix + path (avoid double slash)
                full_path = file_prefix + raw_path if file_prefix and not raw_path.startswith(file_prefix) else raw_path
                full_path = _normalize_route_path(full_path)

                entries.append(
                    RouteEntry(
                        file=rel_str,
                        line=line_no,
                        path=raw_path,
                        normalized=normalized,
                        full_path=full_path,
                    )
                )

    if _NATIVE_ONLY_ENDPOINTS_FILE.exists():
        manifest = yaml.safe_load(_NATIVE_ONLY_ENDPOINTS_FILE.read_text(encoding="utf-8")) or {}
        for endpoint in manifest.get("endpoints", []):
            path = endpoint["path"]
            entries.append(
                RouteEntry(
                    file=endpoint["rust_module"],
                    line=0,
                    path=path,
                    normalized=path,
                    full_path=path,
                )
            )

    return entries


# ---------------------------------------------------------------------------
# MCP path extraction
# ---------------------------------------------------------------------------

_CLIENT_CALL_RE = re.compile(
    r"""client\s*\.\s*(get|post|put|patch|delete|get_text|post_sse)\s*\(\s*"""
    r"""(f?["']([^"']+)["'])""",
)

# Resolve simple string assignments: _PFX = "/ext/something". Allows leading
# whitespace so function-local constants (e.g. `    _FAV_PFX = "..."` inside a
# tool function) resolve too, not just module-level ones.
_CONST_ASSIGN_RE = re.compile(
    r"""^[ \t]*(\w+)\s*=\s*["']([^"']+)["']\s*$""", re.MULTILINE
)
# Detect relative imports: from .module import X, Y  OR  from .module_common import X as Y
_REL_IMPORT_RE = re.compile(
    r"""^from\s+\.(\w+)\s+import\s+(.+)$""", re.MULTILINE
)


@dataclass
class MCPPathEntry:
    file: str
    line: int
    method: str
    raw_path: str          # raw argument to client.METHOD(...)
    static_path: str       # resolved static path (or prefix for f-strings)
    is_prefix: bool        # True if static_path is a prefix (f-string with vars)


def _resolve_fstring_path(raw: str, constants: dict[str, str]) -> tuple[str, bool]:
    """Resolve an f-string path to a static path or prefix.

    Returns (resolved_path, is_prefix).
    is_prefix=True means the path contains unresolved variables and should be
    treated as a prefix for matching purposes.
    """
    # Replace known constants: {_PFX} → "/ext/something"
    def replace_const(m: re.Match) -> str:
        name = m.group(1)
        return constants.get(name, m.group(0))  # leave unknown vars as-is

    resolved = re.sub(r"\{(\w+)\}", replace_const, raw)

    # Check if any variables remain
    if "{" in resolved:
        # Extract static prefix (up to first remaining {)
        idx = resolved.index("{")
        return resolved[:idx], True
    return resolved, False


def collect_mcp_paths(repo: Path = REPO) -> list[MCPPathEntry]:
    """Collect all client.METHOD(...) calls from mcp_server/."""
    entries: list[MCPPathEntry] = []
    mcp_dir = repo / "mcp_server"
    if not mcp_dir.exists():
        return entries

    for py_file in sorted(mcp_dir.rglob("*.py")):
        if any(part in (".venv", "__pycache__") for part in py_file.parts):
            continue
        try:
            content = py_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue

        rel = str(py_file.relative_to(repo)).replace("\\", "/")

        # Extract module-level string constants for f-string resolution.
        # Also follow relative imports to resolve constants defined in sibling files
        # (e.g. `from .chatlog_tools_common import _PFX`).
        constants: dict[str, str] = {}
        for m in _CONST_ASSIGN_RE.finditer(content):
            constants[m.group(1)] = m.group(2)

        # Resolve constants from relative imports within mcp_server/
        for imp_m in _REL_IMPORT_RE.finditer(content):
            sibling_mod = imp_m.group(1)  # e.g. "chatlog_tools_common"
            sibling_path = py_file.parent / f"{sibling_mod}.py"
            if sibling_path.exists():
                try:
                    sibling_content = sibling_path.read_text(encoding="utf-8", errors="replace")
                    for c in _CONST_ASSIGN_RE.finditer(sibling_content):
                        # Only add if not already defined locally (local wins)
                        if c.group(1) not in constants:
                            constants[c.group(1)] = c.group(2)
                except OSError:
                    pass

        for match in _CLIENT_CALL_RE.finditer(content):
            method = match.group(1)
            full_arg = match.group(2)   # f"..." or "..."
            path_raw = match.group(3)   # content inside quotes

            is_fstring = full_arg.startswith("f")
            line_no = content[: match.start()].count("\n") + 1

            if is_fstring:
                static_path, is_prefix = _resolve_fstring_path(path_raw, constants)
            else:
                static_path = path_raw
                is_prefix = False

            entries.append(
                MCPPathEntry(
                    file=rel,
                    line=line_no,
                    method=method,
                    raw_path=path_raw,
                    static_path=static_path,
                    is_prefix=is_prefix,
                )
            )

    return entries


# ---------------------------------------------------------------------------
# Parity checks
# ---------------------------------------------------------------------------

@dataclass
class ParityError:
    level: str  # "ERROR" or "WARNING"
    file: str
    line: int
    message: str
    path: str


def _route_matches_path(route: RouteEntry, path: str, is_prefix: bool) -> bool:
    """Test whether a route covers the given MCP path."""
    if not path:
        # Empty path means fully unresolvable f-string — cannot match
        return False
    if is_prefix:
        # Check if route's full_path starts with this prefix, or the prefix
        # covers the route's static portion (e.g. prefix=/api/x/ matches route=/api/x/{id})
        # Segment-boundary guard: next char after prefix must be '/' or EOS.
        def _seg_ok(s: str, prefix: str) -> bool:
            return s.startswith(prefix) and (
                len(s) == len(prefix) or s[len(prefix)] in ("/", "?")
            )

        route_static = route.full_path.split("{")[0]  # static part before first param
        return _seg_ok(route.full_path, path) or (
            bool(route_static) and _seg_ok(path, route_static)
        )
    # Exact match (with param wildcards)
    if route.full_path == path:
        return True
    # Pattern match: route has {x} placeholders
    if "{" in route.full_path:
        try:
            pattern = _route_to_regex(route.full_path)
            return bool(pattern.match(path))
        except re.error:
            return False
    return False


def check_broken_mcp_paths(
    routes: list[RouteEntry],
    mcp_paths: list[MCPPathEntry],
    exceptions: set[str],
) -> list[ParityError]:
    """ERROR: MCP tool calls a path that has no matching route."""
    errors: list[ParityError] = []

    for mp in mcp_paths:
        if _is_excluded(mp.static_path, exceptions):
            continue

        # Only check paths that look like API paths
        if not (mp.static_path.startswith("/api/") or mp.static_path.startswith("/ext/")):
            continue

        covered = any(_route_matches_path(r, mp.static_path, mp.is_prefix) for r in routes)
        if not covered:
            errors.append(
                ParityError(
                    level="ERROR",
                    file=mp.file,
                    line=mp.line,
                    message=f"MCP tool calls '{mp.raw_path}' but no matching @bp.route found",
                    path=mp.static_path,
                )
            )

    return errors


def check_uncovered_routes(
    routes: list[RouteEntry],
    mcp_paths: list[MCPPathEntry],
    exceptions: set[str],
) -> list[ParityError]:
    """WARNING: API route has no MCP tool referencing it."""
    warnings: list[ParityError] = []

    for route in routes:
        # Only warn about /api/ routes (skip HTML delivery, /ext/ UI pages, etc.)
        if not route.full_path.startswith("/api/"):
            continue
        if _is_excluded(route.full_path, exceptions):
            continue

        covered = any(_route_matches_path(route, mp.static_path, mp.is_prefix) for mp in mcp_paths)
        if not covered:
            warnings.append(
                ParityError(
                    level="WARNING",
                    file=route.file,
                    line=route.line,
                    message=f"Route '{route.full_path}' has no MCP tool",
                    path=route.full_path,
                )
            )

    return warnings


# ---------------------------------------------------------------------------
# Public API (used by tests and pre_push_check)
# ---------------------------------------------------------------------------

@dataclass
class ParityReport:
    errors: list[ParityError] = field(default_factory=list)
    warnings: list[ParityError] = field(default_factory=list)
    route_count: int = 0
    mcp_path_count: int = 0

    @property
    def has_errors(self) -> bool:
        return bool(self.errors)

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)


def run_parity_check(
    repo: Path = REPO,
    include_warnings: bool = True,
) -> ParityReport:
    """Run the full parity check and return a structured report."""
    exceptions = load_exceptions()
    routes = collect_routes(repo)
    mcp_paths = collect_mcp_paths(repo)

    errors = check_broken_mcp_paths(routes, mcp_paths, exceptions)
    warnings = check_uncovered_routes(routes, mcp_paths, exceptions) if include_warnings else []

    return ParityReport(
        errors=errors,
        warnings=warnings,
        route_count=len(routes),
        mcp_path_count=len(mcp_paths),
    )


def format_report(report: ParityReport) -> str:
    """Format the parity report as a human-readable string."""
    lines: list[str] = []

    if report.errors:
        lines.append(f"{'='*60}")
        lines.append(f"ERROR: {len(report.errors)} broken MCP→route reference(s)")
        lines.append(f"{'='*60}")
        for e in report.errors:
            lines.append(f"  {e.file}:{e.line}  {e.message}")
        lines.append("")

    if report.warnings:
        lines.append(f"{'='*60}")
        lines.append(f"WARNING: {len(report.warnings)} API route(s) without MCP tool")
        lines.append(f"{'='*60}")
        for w in report.warnings:
            lines.append(f"  {w.file}:{w.line}  {w.path}")
        lines.append("")

    summary_parts = [
        f"routes={report.route_count}",
        f"mcp_paths={report.mcp_path_count}",
        f"errors={len(report.errors)}",
        f"warnings={len(report.warnings)}",
    ]
    lines.append("MCP parity: " + "  ".join(summary_parts))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--errors-only", action="store_true", help="Only report ERROR level issues (skip warnings)")
    parser.add_argument("--no-warnings", action="store_true", help="Alias for --errors-only")
    parser.add_argument("--json", action="store_true", dest="json_output", help="Output JSON")
    args = parser.parse_args(argv)

    include_warnings = not (args.errors_only or args.no_warnings)
    report = run_parity_check(include_warnings=include_warnings)

    if args.json_output:
        data = {
            "errors": [
                {"file": e.file, "line": e.line, "message": e.message, "path": e.path}
                for e in report.errors
            ],
            "warnings": [
                {"file": w.file, "line": w.line, "message": w.message, "path": w.path}
                for w in report.warnings
            ],
            "route_count": report.route_count,
            "mcp_path_count": report.mcp_path_count,
        }
        print(json.dumps(data, indent=2, ensure_ascii=False))
    else:
        print(format_report(report))

    return 1 if report.has_errors else 0


if __name__ == "__main__":
    sys.exit(main())
