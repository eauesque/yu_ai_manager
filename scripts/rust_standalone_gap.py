"""Rust単独起動時にPythonへ転送されるaxumルートの静的レポート。

``check_rust_mcp_parity.py`` の ``collect_rust_routes`` をそのまま使い、各
``.route()`` のハンドラー名を登録行から取得して、同一Rustファイル内の名前付き
関数呼び出しを追跡する。``python_url`` からローカル変数への代入を追い、その変数を
URL引数に使うHTTPリクエストが ``send`` される処理へ到達したルートを転送とみなす。
``fwd_*`` という関数名や ``python_client`` というフィールド名だけでは転送とみなさない。

Forward classification is also a conservative syntactic heuristic. A handler whose tail is only
a forwarder call is ``no_native_path``. A conditional ``return forwarder(...)`` followed by more
work, or a native helper call followed by a tail forwarder, is ``native_fallback``. Inline forwarding
is ``no_native_path`` when the no-Python branch is a 503 or an explicit stub. Other cases, including
indirect notifications, complex matches, native attempts outside the naming convention, and
ambiguous no-Python branches, are ``unknown``.

これはRust構文解析器ではなく、現行コード配置に合わせた名前・局所データフローの
ヒューリスティックである。macro、closure、関数値、re-export、曖昧なimport、別ファイル
への曖昧な間接呼び出し、関数引数・戻り値を介すURL伝播、文字列中のbrace、条件の実行
可能性は正確に評価しない。別ファイルの修飾 ``fwd_*`` 呼び出しは関数名が全体で一意の
場合だけ追い、転送先も検証する。収集元と同様に ``#[cfg(test)]`` 内のルートも対象となる。
解決不能ルートは別途列挙し、native扱いを断定しない。

Usage:
  uv run python scripts/rust_standalone_gap.py
  uv run python scripts/rust_standalone_gap.py --json
  uv run python scripts/rust_standalone_gap.py --show-routes
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sys
from functools import cache
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
RUST_SRC = REPO / "crates" / "yu-server" / "src"
KEEP_FILE = REPO / "scripts" / "rust_proxy_keep.txt"
METHODS = "get|post|put|delete|patch|head|options"
METHOD_CALL_RE = re.compile(rf"\.?\b({METHODS})\s*\(", re.IGNORECASE)
HANDLER_RE = re.compile(r"(?:[A-Za-z_]\w*::)*[A-Za-z_]\w*")
FUNCTION_RE = re.compile(r"\b(?:async\s+)?fn\s+([A-Za-z_]\w*)\b")
CALL_RE = re.compile(r"\b([A-Za-z_]\w*)\s*\(")
LET_RE = re.compile(
    r"\blet\s+(?:mut\s+)?(?P<binding>[^=;]+?)\s*=\s*(?P<value>.*?);", re.DOTALL
)
IDENT_RE = re.compile(r"\b[A-Za-z_]\w*\b")
HTTP_URL_RE = re.compile(rf"\.(?:{METHODS})\s*\(\s*&?\s*(?P<url>[A-Za-z_]\w*)")
HTTP_REQUEST_URL_RE = re.compile(
    r"\.request\s*\([^,]+,\s*&?\s*(?P<url>[A-Za-z_]\w*)", re.DOTALL
)
HTTP_SEND_RE = re.compile(r"\.send\s*\(")
COMMENT_RE = re.compile(r"//[^\n]*|/\*.*?\*/", re.DOTALL)
RETURN_CALL_RE = re.compile(r"return\s+(?:(?:crate|self|super|[A-Za-z_]\w*)::)*$")
POSITIVE_PY_GUARD_RE = re.compile(r"if\s+[^{\n]*python_url\.is_empty\(\)")
NEGATIVE_PY_GUARD_RE = re.compile(r"if\s+!\s*[^{\n]*python_url\.is_empty\(\)")
NO_NATIVE_MARKER_RE = re.compile(
    r"SERVICE_UNAVAILABLE|python_required|standalone stub|\"started\"\s*:\s*false"
)
STRING_LITERAL_RE = re.compile(
    r'(?:b?r(?P<hashes>#{0,255})".*?"(?P=hashes)|b?"(?:\\.|[^"\\])*")',
    re.DOTALL,
)
NATIVE_CALL_RE = re.compile(r"\b[A-Za-z_]\w*_native\s*\(")


def _import_rust_parity():
    spec = importlib.util.spec_from_file_location(
        "check_rust_mcp_parity", REPO / "scripts" / "check_rust_mcp_parity.py"
    )
    mod = importlib.util.module_from_spec(spec)  # type: ignore[arg-type]
    sys.modules["check_rust_mcp_parity"] = mod
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


_rust = _import_rust_parity()


def _matching(text: str, start: int, opening: str, closing: str) -> int | None:
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return index
    return None


@cache
def _functions(path: Path) -> dict[str, tuple[str, ...]]:
    content = path.read_text(encoding="utf-8", errors="replace")
    bodies: dict[str, list[str]] = {}
    for match in FUNCTION_RE.finditer(content):
        brace = content.find("{", match.end())
        if brace < 0:
            continue
        semicolon = content.find(";", match.end(), brace)
        if semicolon >= 0:
            continue
        end = _matching(content, brace, "{", "}")
        if end is not None:
            bodies.setdefault(match.group(1), []).append(content[brace + 1 : end])
    return {name: tuple(parts) for name, parts in bodies.items()}


@cache
def _function_index() -> dict[str, tuple[Path, ...]]:
    found: dict[str, list[Path]] = {}
    for path in sorted(RUST_SRC.rglob("*.rs")):
        for name in _functions(path):
            found.setdefault(name, []).append(path)
    return {name: tuple(paths) for name, paths in found.items()}


def _module_parts(path: Path) -> tuple[str, ...]:
    parts = list(path.relative_to(RUST_SRC).with_suffix("").parts)
    if parts[-1] in ("main", "lib"):
        return ()
    if parts[-1] == "mod":
        parts.pop()
    return tuple(parts)


def _module_file(parts: tuple[str, ...]) -> Path | None:
    base = RUST_SRC.joinpath(*parts)
    candidates = (base.with_suffix(".rs"), base / "mod.rs")
    return next((path for path in candidates if path.is_file()), None)


def _resolve_handler(registration_file: Path, expression: str) -> tuple[Path, str] | None:
    expression = expression.strip()
    if not HANDLER_RE.fullmatch(expression):
        return None
    parts = expression.split("::")
    name = parts.pop()
    if not parts and name in _functions(registration_file):
        return registration_file, name

    current = list(_module_parts(registration_file))
    if parts[:1] == ["crate"]:
        candidates = [tuple(parts[1:])]
    elif parts[:1] == ["self"]:
        candidates = [tuple(current + parts[1:])]
    elif parts[:1] == ["super"]:
        while parts[:1] == ["super"]:
            parts.pop(0)
            if current:
                current.pop()
        candidates = [tuple(current + parts)]
    else:
        candidates = [tuple(parts), tuple(current + parts)]

    for module in candidates:
        path = _module_file(module)
        if path is not None and name in _functions(path):
            return path, name

    unique = _function_index().get(name, ())
    if len(unique) == 1:
        return unique[0], name
    return None


def _handler_expression(content: str, line: int, method: str) -> str | None:
    lines = content.splitlines(keepends=True)
    offset = sum(len(part) for part in lines[: line - 1])
    route_start = content.find(".route", offset)
    if route_start < 0:
        return None
    opening = content.find("(", route_start)
    closing = _matching(content, opening, "(", ")") if opening >= 0 else None
    if closing is None:
        return None
    route_call = content[opening + 1 : closing]
    for match in METHOD_CALL_RE.finditer(route_call):
        if match.group(1).upper() != method.upper():
            continue
        call_open = route_call.find("(", match.start())
        call_close = _matching(route_call, call_open, "(", ")")
        if call_close is not None:
            return route_call[call_open + 1 : call_close].strip()
    return None


def _sends_to_python(code: str) -> bool:
    if "python_url" not in code or not HTTP_SEND_RE.search(code):
        return False
    tainted = {"python_url"}
    for match in LET_RE.finditer(code):
        if any(re.search(rf"\b{re.escape(name)}\b", match["value"]) for name in tainted):
            tainted.update(IDENT_RE.findall(match["binding"]))
    return any(
        match["url"] in tainted and not _is_ignored_spawn_call(code, match.start())
        for pattern in (HTTP_URL_RE, HTTP_REQUEST_URL_RE)
        for match in pattern.finditer(code)
    )


def _is_ignored_spawn_call(code: str, call_start: int) -> bool:
    for spawn in re.finditer(r"\btokio::spawn\s*\(", code[:call_start]):
        opening = code.find("(", spawn.start())
        closing = _matching(code, opening, "(", ")")
        if closing is None or not opening < call_start < closing:
            continue
        statement_start = max(code.rfind(";", opening, call_start), code.rfind("{", opening, call_start))
        if re.search(r"\blet\s+_\s*=", code[statement_start + 1 : call_start]):
            return True
    return False


def _called_forwards(
    path: Path,
    name: str,
    qualified: bool,
    seen: set[tuple[Path, str]] | None = None,
) -> bool:
    if name in _functions(path):
        return _forwards(path, name, seen)
    targets = _function_index().get(name, ()) if qualified and name.startswith("fwd_") else ()
    return len(targets) == 1 and _forwards(targets[0], name, seen)


def _forwards(
    path: Path, name: str, seen: set[tuple[Path, str]] | None = None
) -> bool:
    seen = set() if seen is None else seen
    key = (path, name)
    if key in seen:
        return False
    seen.add(key)
    functions = _functions(path)
    for body in functions.get(name, ()):
        code = COMMENT_RE.sub("", body)
        if _sends_to_python(code):
            return True
        for match in CALL_RE.finditer(code):
            if _called_forwards(
                path, match.group(1), code[match.start() - 2 : match.start()] == "::", seen
            ):
                return True
    return False


def _call_is_tail(code: str, call_end: int) -> bool:
    return re.fullmatch(r"\s*\.await\s*\??\s*;?\s*", code[call_end + 1 :]) is not None


def _meaningful_after_call(code: str, call_end: int) -> bool:
    rest = re.sub(r"^\s*\.await\s*\??\s*;?", "", code[call_end + 1 :])
    return bool(rest.strip(" \t\r\n}"))


def _classify_body(path: Path, code: str) -> str:
    calls = []
    for match in CALL_RE.finditer(code):
        called = match.group(1)
        if not _called_forwards(
            path, called, code[match.start() - 2 : match.start()] == "::"
        ):
            continue
        opening = code.find("(", match.start())
        closing = _matching(code, opening, "(", ")")
        if closing is not None:
            calls.append((match.start(), closing))

    if any(_call_is_tail(code, end) for _, end in calls):
        if NATIVE_CALL_RE.search(COMMENT_RE.sub("", STRING_LITERAL_RE.sub("", code))):
            return "native_fallback"
        return "no_native_path"
    if any(
        RETURN_CALL_RE.search(code[max(0, start - 100) : start])
        and _meaningful_after_call(code, end)
        for start, end in calls
    ):
        return "native_fallback"

    if _sends_to_python(code):
        if NEGATIVE_PY_GUARD_RE.search(code):
            return "no_native_path" if NO_NATIVE_MARKER_RE.search(code) else "unknown"
        if POSITIVE_PY_GUARD_RE.search(code) or re.search(
            r"let\s+Some\([^)]*\)\s*=\s*python_url\([^)]*\)\s+else", code
        ):
            return "no_native_path"
    return "unknown"


def _classify_forwarding(path: Path, name: str) -> str:
    classes = {
        _classify_body(path, COMMENT_RE.sub("", body)) for body in _functions(path).get(name, ())
    }
    return classes.pop() if len(classes) == 1 else "unknown"


def _load_keep() -> set[str]:
    if not KEEP_FILE.exists():
        return set()
    return {
        line
        for raw in KEEP_FILE.read_text(encoding="utf-8").splitlines()
        if (line := raw.strip()) and not line.startswith("#")
    }


def collect_report() -> dict:
    keep = _load_keep()
    routes = _rust.collect_rust_routes(RUST_SRC)
    content_cache: dict[Path, str] = {}
    forwarding = []
    unresolved = []
    for route in routes:
        registration_file = REPO / route.file
        content = content_cache.setdefault(
            registration_file,
            registration_file.read_text(encoding="utf-8", errors="replace"),
        )
        expression = _handler_expression(content, route.line, route.method)
        resolved = _resolve_handler(registration_file, expression or "")
        base = {
            "method": route.method,
            "path": route.path,
            "file": route.file,
            "line": route.line,
        }
        if resolved is None:
            unresolved.append({**base, "handler": expression})
            continue
        handler_file, handler_name = resolved
        if _forwards(handler_file, handler_name):
            forwarding.append(
                {
                    **base,
                    "classification": _classify_forwarding(handler_file, handler_name),
                    "proxy_keep": any(
                        route.normalized == prefix or route.normalized.startswith(prefix)
                        for prefix in keep
                    ),
                }
            )

    forwarding.sort(key=lambda item: (item["file"], item["line"], item["method"]))
    unresolved.sort(key=lambda item: (item["file"], item["line"], item["method"]))
    proxy_keep = sum(item["proxy_keep"] for item in forwarding)
    remaining = [item for item in forwarding if not item["proxy_keep"]]
    return {
        "summary": {
            "total_routes": len(routes),
            "forward_to_python": len(forwarding),
            "deliberate_proxy_keep": proxy_keep,
            "remaining_work": len(remaining),
            "no_native_path": sum(
                item["classification"] == "no_native_path" for item in remaining
            ),
            "native_fallback": sum(
                item["classification"] == "native_fallback" for item in remaining
            ),
            "unclassified": sum(item["classification"] == "unknown" for item in remaining),
            "handler_resolution_failed": len(unresolved),
        },
        "routes": forwarding,
        "unresolved_routes": unresolved,
    }


def format_report(report: dict, *, show_routes: bool = False) -> str:
    summary = report["summary"]
    lines = [
        "Rust standalone gap",
        f"  total routes:            {summary['total_routes']}",
        f"  forward to Python:       {summary['forward_to_python']}",
        f"    deliberate proxy-keep: {summary['deliberate_proxy_keep']}",
        f"    remaining work:        {summary['remaining_work']}",
        f"      no native path:      {summary['no_native_path']}",
        f"      native + fallback:   {summary['native_fallback']}",
        f"      unclassified:        {summary['unclassified']}",
    ]
    if not show_routes:
        return "\n".join(lines)

    lines.extend(["", "Python-forwarding routes:"])
    for route in report["routes"]:
        status = "proxy-keep" if route["proxy_keep"] else "remaining"
        classification = {
            "no_native_path": "no native path",
            "native_fallback": "native + fallback",
            "unknown": "unclassified",
        }[route["classification"]]
        lines.append(
            f"  {route['method']} {route['path']} — {route['file']}:{route['line']}"
            f" — {status} — {classification}"
        )
    lines.extend(["", "Handler resolution failed:"])
    for route in report["unresolved_routes"]:
        lines.append(
            f"  {route['method']} {route['path']} — {route['file']}:{route['line']}"
            f" — handler: {route['handler'] or '(not parsed)'}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Rust単独起動時のPython転送ルート計測")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--show-routes", action="store_true", help="転送ルートと解決失敗を表示")
    args = parser.parse_args(argv)
    report = collect_report()
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else format_report(report, show_routes=args.show_routes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
