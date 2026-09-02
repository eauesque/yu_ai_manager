#!/usr/bin/env python3
"""MCP protocol parity check — Python direct vs Rust bridge.

Usage:
  uv run python scripts/verify_mcp_parity.py --python http://127.0.0.1:5000 --rust http://127.0.0.1:8080
  uv run python scripts/verify_mcp_parity.py --auto --db tags.db   # Rust auto-start, Python manual

Compares:
  - initialize
  - tools/list   (tool count + name set diff)
  - resources/list
  - tools/call   per tool with empty args (status / error shape only)
"""

from __future__ import annotations

import argparse
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

# ─────────────────────────────────────────────────────────────────────────────
# JSON-RPC helpers
# ─────────────────────────────────────────────────────────────────────────────

def _req(method: str, params: dict | None = None, id: int = 1) -> dict:
    return {"jsonrpc": "2.0", "id": id, "method": method, "params": params or {}}


def _post(client: httpx.Client, url: str, body: dict, timeout: float = 30.0) -> tuple[int, Any]:
    try:
        resp = client.post(url, json=body, timeout=timeout)
        try:
            data = resp.json()
        except Exception:
            data = resp.text
        return resp.status_code, data
    except httpx.TimeoutException:
        return -1, "TIMEOUT"
    except Exception as e:
        return -2, str(e)


# ─────────────────────────────────────────────────────────────────────────────
# Result
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CmpResult:
    method: str
    label: str
    python_status: int | None = None
    rust_status: int | None = None
    python_data: Any = None
    rust_data: Any = None
    notes: list[str] = field(default_factory=list)

    def ok(self) -> bool:
        return not self.notes

    def badge(self) -> str:
        return "✅" if self.ok() else "❌"


# ─────────────────────────────────────────────────────────────────────────────
# Comparison helpers
# ─────────────────────────────────────────────────────────────────────────────

def _check_reachability(r: CmpResult) -> bool:
    """Returns False (and adds notes) if either server is unreachable."""
    ok = True
    if r.python_status is not None and r.python_status < 0:
        r.notes.append(f"python server unreachable (status={r.python_status}): {r.python_data}")
        ok = False
    if r.rust_status is not None and r.rust_status < 0:
        r.notes.append(f"rust server unreachable (status={r.rust_status}): {r.rust_data}")
        ok = False
    return ok


def _extract_result(data: Any) -> Any:
    if isinstance(data, dict):
        return data.get("result")
    return None


def _extract_error(data: Any) -> Any:
    if isinstance(data, dict):
        return data.get("error")
    return None


def cmp_initialize(py_client: httpx.Client, rust_client: httpx.Client,
                   py_url: str, rust_url: str) -> CmpResult:
    body = _req("initialize", {
        "protocolVersion": "2024-11-05",
        "capabilities": {},
        "clientInfo": {"name": "parity-check", "version": "1.0"},
    })
    py_status, py_data = _post(py_client, f"{py_url}/mcp", body)
    rust_status, rust_data = _post(rust_client, f"{rust_url}/mcp", body)

    r = CmpResult("initialize", "POST /mcp — initialize",
                  py_status, rust_status, py_data, rust_data)

    if not _check_reachability(r):
        return r

    if py_status != rust_status:
        r.notes.append(f"status mismatch: python={py_status} rust={rust_status}")

    py_res = _extract_result(py_data)
    rust_res = _extract_result(rust_data)

    # protocolVersion
    if isinstance(py_res, dict) and isinstance(rust_res, dict):
        py_ver = py_res.get("protocolVersion")
        rust_ver = rust_res.get("protocolVersion")
        if py_ver != rust_ver:
            r.notes.append(f"protocolVersion diff: python={py_ver!r} rust={rust_ver!r}")

        py_info = py_res.get("serverInfo", {})
        rust_info = rust_res.get("serverInfo", {})
        if py_info.get("name") != rust_info.get("name"):
            r.notes.append(f"serverInfo.name diff: python={py_info.get('name')!r} rust={rust_info.get('name')!r}")

    return r


def cmp_tools_list(py_client: httpx.Client, rust_client: httpx.Client,
                   py_url: str, rust_url: str) -> tuple[CmpResult, list[str]]:
    body = _req("tools/list")
    py_status, py_data = _post(py_client, f"{py_url}/mcp", body)
    rust_status, rust_data = _post(rust_client, f"{rust_url}/mcp", body)

    r = CmpResult("tools/list", "POST /mcp — tools/list",
                  py_status, rust_status, py_data, rust_data)

    if not _check_reachability(r):
        return r, []

    py_tools: list[str] = []
    rust_tools: list[str] = []

    py_res = _extract_result(py_data)
    rust_res = _extract_result(rust_data)

    if isinstance(py_res, dict):
        py_tools = [t.get("name", "") for t in py_res.get("tools", [])]
    if isinstance(rust_res, dict):
        rust_tools = [t.get("name", "") for t in rust_res.get("tools", [])]

    if py_status != rust_status:
        r.notes.append(f"status mismatch: python={py_status} rust={rust_status}")

    py_set = set(py_tools)
    rust_set = set(rust_tools)
    only_python = py_set - rust_set
    only_rust = rust_set - py_set

    if only_python:
        r.notes.append(f"tools only in Python ({len(only_python)}): {sorted(only_python)[:10]}")
    if only_rust:
        r.notes.append(f"tools only in Rust ({len(only_rust)}): {sorted(only_rust)[:10]}")

    if py_tools and rust_tools and len(py_tools) != len(rust_tools):
        r.notes.append(f"tool count diff: python={len(py_tools)} rust={len(rust_tools)}")

    return r, sorted(py_set | rust_set)


def cmp_resources_list(py_client: httpx.Client, rust_client: httpx.Client,
                       py_url: str, rust_url: str) -> CmpResult:
    body = _req("resources/list")
    py_status, py_data = _post(py_client, f"{py_url}/mcp", body)
    rust_status, rust_data = _post(rust_client, f"{rust_url}/mcp", body)

    r = CmpResult("resources/list", "POST /mcp — resources/list",
                  py_status, rust_status, py_data, rust_data)

    if not _check_reachability(r):
        return r

    if py_status != rust_status:
        r.notes.append(f"status mismatch: python={py_status} rust={rust_status}")

    py_res = _extract_result(py_data)
    rust_res = _extract_result(rust_data)

    py_uris: set[str] = set()
    rust_uris: set[str] = set()
    if isinstance(py_res, dict):
        py_uris = {r_.get("uri", "") for r_ in py_res.get("resources", [])}
    if isinstance(rust_res, dict):
        rust_uris = {r_.get("uri", "") for r_ in rust_res.get("resources", [])}

    only_py = py_uris - rust_uris
    only_ru = rust_uris - py_uris
    if only_py:
        r.notes.append(f"resources only in Python: {sorted(only_py)[:5]}")
    if only_ru:
        r.notes.append(f"resources only in Rust: {sorted(only_ru)[:5]}")

    return r


def cmp_tool_call(py_client: httpx.Client, rust_client: httpx.Client,
                  py_url: str, rust_url: str,
                  tool_name: str, idx: int) -> CmpResult:
    body = _req("tools/call", {"name": tool_name, "arguments": {}}, id=idx)
    py_status, py_data = _post(py_client, f"{py_url}/mcp", body, timeout=15.0)
    rust_status, rust_data = _post(rust_client, f"{rust_url}/mcp", body, timeout=15.0)

    r = CmpResult(f"tools/call:{tool_name}", f"  tools/call {tool_name}",
                  py_status, rust_status, py_data, rust_data)

    if not _check_reachability(r):
        return r

    # ステータス差異
    if py_status != rust_status:
        r.notes.append(f"status={py_status}→{rust_status}")
        return r

    # result vs error の有無差異
    py_has_result = _extract_result(py_data) is not None
    rust_has_result = _extract_result(rust_data) is not None
    py_has_error = _extract_error(py_data) is not None
    rust_has_error = _extract_error(rust_data) is not None

    if py_has_result != rust_has_result:
        r.notes.append(f"result presence diff: python={py_has_result} rust={rust_has_result}")
    if py_has_error != rust_has_error:
        r.notes.append(f"error presence diff: python={py_has_error} rust={rust_has_error}")

    # エラーコード比較
    py_err = _extract_error(py_data)
    rust_err = _extract_error(rust_data)
    if isinstance(py_err, dict) and isinstance(rust_err, dict) and py_err.get("code") != rust_err.get("code"):
        r.notes.append(
            f"error.code diff: python={py_err.get('code')} rust={rust_err.get('code')}"
        )

    return r


# ─────────────────────────────────────────────────────────────────────────────
# Rust auto-start
# ─────────────────────────────────────────────────────────────────────────────

def _start_rust(db: str) -> tuple[subprocess.Popen, str]:
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    url = f"http://127.0.0.1:{port}"
    proc = subprocess.Popen(
        ["cargo", "run", "--bin", "yu-server", "--release", "--",
         "--port", str(port), "--db", db, "--headless"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    # wait for ready
    for _ in range(60):
        try:
            httpx.get(f"{url}/api/health", timeout=1.0)
            break
        except Exception:
            time.sleep(1.0)
    else:
        proc.terminate()
        raise RuntimeError("Rust server did not start in time")
    return proc, url


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description="MCP parity check: Python vs Rust")
    ap.add_argument("--python", default="http://127.0.0.1:5000", metavar="URL",
                    help="Python server base URL")
    ap.add_argument("--rust", default=None, metavar="URL",
                    help="Rust server base URL (omit with --auto)")
    ap.add_argument("--auto", action="store_true",
                    help="Auto-start Rust server (requires --db)")
    ap.add_argument("--db", default="tags.db", help="DB path for --auto")
    ap.add_argument("--skip-tool-calls", action="store_true",
                    help="Skip per-tool tools/call comparison (faster)")
    args = ap.parse_args()

    rust_proc = None
    rust_url = args.rust
    if args.auto:
        print("🚀 Rust サーバーを起動中...")
        rust_proc, rust_url = _start_rust(args.db)
        print(f"   → {rust_url}")
    elif not rust_url:
        ap.error("--rust または --auto が必要です")

    py_url = args.python.rstrip("/")
    rust_url = rust_url.rstrip("/")

    results: list[CmpResult] = []

    with httpx.Client() as py_client, httpx.Client() as rust_client:
        print(f"\n比較対象:\n  Python: {py_url}\n  Rust:   {rust_url}\n")

        # 1. initialize
        print("─" * 60)
        r = cmp_initialize(py_client, rust_client, py_url, rust_url)
        results.append(r)
        print(f"{r.badge()} {r.label}")
        print(f"   python={r.python_status}  rust={r.rust_status}")
        for n in r.notes:
            print(f"   ⚠  {n}")

        # 2. tools/list
        print("─" * 60)
        r_tools, all_tools = cmp_tools_list(py_client, rust_client, py_url, rust_url)
        results.append(r_tools)
        py_res = _extract_result(r_tools.python_data)
        rust_res = _extract_result(r_tools.rust_data)
        py_count = len(py_res.get("tools", [])) if isinstance(py_res, dict) else "?"
        rust_count = len(rust_res.get("tools", [])) if isinstance(rust_res, dict) else "?"
        print(f"{r_tools.badge()} {r_tools.label}")
        print(f"   python={r_tools.python_status}({py_count}ツール)  rust={r_tools.rust_status}({rust_count}ツール)")
        for n in r_tools.notes:
            print(f"   ⚠  {n}")

        # 3. resources/list
        print("─" * 60)
        r_res = cmp_resources_list(py_client, rust_client, py_url, rust_url)
        results.append(r_res)
        print(f"{r_res.badge()} {r_res.label}")
        print(f"   python={r_res.python_status}  rust={r_res.rust_status}")
        for n in r_res.notes:
            print(f"   ⚠  {n}")

        # 4. tools/call (各ツール)
        if not args.skip_tool_calls and all_tools:
            print("─" * 60)
            print(f"🔧 tools/call 比較 ({len(all_tools)} ツール)...")
            tool_fails: list[CmpResult] = []
            for idx, tool_name in enumerate(all_tools, start=100):
                r_tc = cmp_tool_call(py_client, rust_client, py_url, rust_url, tool_name, idx)
                results.append(r_tc)
                if not r_tc.ok():
                    tool_fails.append(r_tc)
                    print(f"   {r_tc.badge()} {tool_name}")
                    for n in r_tc.notes:
                        print(f"        ⚠  {n}")
                else:
                    print(f"   {r_tc.badge()} {tool_name}  (py={r_tc.python_status} rust={r_tc.rust_status})")

    # Summary
    print("\n" + "=" * 60)
    total = len(results)
    failed = [r for r in results if not r.ok()]
    passed = total - len(failed)
    print(f"結果: {passed} PASS / {len(failed)} FAIL / {total} 合計")
    if failed:
        print("\nFAIL 一覧:")
        for r in failed:
            print(f"  ❌ {r.label}")
            for n in r.notes:
                print(f"     {n}")
        if rust_proc:
            rust_proc.terminate()
        return 1

    if rust_proc:
        rust_proc.terminate()
    return 0


if __name__ == "__main__":
    sys.exit(main())
