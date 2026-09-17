"""Measure grouped-mode cold/warm performance against a fresh local server.

Usage:
  python scripts/perf_grouped_mode.py --pin 1234 --query a

This script starts ``web_ui.py`` on a temporary local port, performs:
1. A cold grouped-mode click immediately after search results appear.
2. A warm grouped-mode click after the grouped warm path has had time to run.

It prints a human-readable summary first, then a JSON object with both scenarios.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def _wait_for_server(url: str, timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    last_error = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:  # pragma: no cover - diagnostic path
            last_error = exc
        time.sleep(1.0)
    raise RuntimeError(f"Server did not start: {last_error}")


def _login_if_needed(page, pin: str | None) -> None:
    page.wait_for_timeout(600)
    pin_selector = None
    if page.locator("#pinInput").count():
        pin_selector = "#pinInput"
    elif page.locator("#lockPin").count():
        pin_selector = "#lockPin"
    if not pin_selector:
        return
    if not pin:
        raise RuntimeError("PIN page detected but no --pin was provided")
    page.fill(pin_selector, pin)
    page.press(pin_selector, "Enter")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(900)


def _goto_perf_home(page, base_url: str) -> None:
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    _login_if_needed(page, None)
    page.evaluate("localStorage.setItem('yu_page_perf','1')")
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    page.wait_for_selector("#tagQuery", timeout=20000)


def _prepare_page(page, base_url: str, pin: str | None) -> None:
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    _login_if_needed(page, pin)
    page.evaluate("localStorage.setItem('yu_page_perf','1')")
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    page.wait_for_selector("#tagQuery", timeout=20000)


def _run_search(page, query: str) -> None:
    page.fill("#tagQuery", query)
    page.locator("#searchBtn").click()
    page.wait_for_selector("#results .result-card", timeout=30000)


def _capture_grouped(page, wait_before_click_ms: int) -> dict[str, Any]:
    page.wait_for_timeout(wait_before_click_ms)
    page.locator('#resultsGroupControls [data-mode="folder"]').click()
    page.wait_for_function(
        "() => !!window.__yuPagePerf?.['grouping-server']?.index_source",
        timeout=30000,
    )
    page.wait_for_timeout(200)
    perf = page.evaluate("() => window.__yuPagePerf")
    return {
        "grouping-action": perf.get("grouping-action", {}),
        "grouping-server": perf.get("grouping-server", {}),
        "resultsCount": page.locator("#resultsCount").text_content(),
        "cards": page.locator("#results .result-card").count(),
    }


def _metric(run: dict[str, Any], group: str, key: str) -> int | None:
    value = run.get(group, {}).get(key)
    return value if isinstance(value, int) else None


def _speedup(cold: int | None, warm: int | None) -> str:
    if cold is None or warm is None or cold <= 0:
        return "n/a"
    return f"{cold / max(warm, 1):.1f}x"


def _print_summary(query: str, cold: dict[str, Any], warm: dict[str, Any]) -> None:
    cold_resp = _metric(cold, "grouping-action", "grouping_response_received")
    warm_resp = _metric(warm, "grouping-action", "grouping_response_received")
    cold_done = _metric(cold, "grouping-action", "grouping_post_paint_ready")
    warm_done = _metric(warm, "grouping-action", "grouping_post_paint_ready")
    cold_total = _metric(cold, "grouping-server", "total_ms")
    warm_total = _metric(warm, "grouping-server", "total_ms")
    cold_ids = _metric(cold, "grouping-server", "search_ids_ms")
    warm_ids = _metric(warm, "grouping-server", "search_ids_ms")
    cold_hit = cold.get("grouping-server", {}).get("ids_cache_hit", 0)
    warm_hit = warm.get("grouping-server", {}).get("ids_cache_hit", 0)
    cold_src = cold.get("grouping-server", {}).get("index_source", "unknown")
    warm_src = warm.get("grouping-server", {}).get("index_source", "unknown")

    print("Grouped Perf Summary")
    print(f"query: {query}")
    print(
        "cold: "
        f"resp={cold_resp}ms total={cold_total}ms ids={cold_ids}ms "
        f"post_paint={cold_done}ms ids_cache_hit={cold_hit} index_source={cold_src}"
    )
    print(
        "warm: "
        f"resp={warm_resp}ms total={warm_total}ms ids={warm_ids}ms "
        f"post_paint={warm_done}ms ids_cache_hit={warm_hit} index_source={warm_src}"
    )
    print(
        "speedup: "
        f"response={_speedup(cold_resp, warm_resp)} "
        f"server_total={_speedup(cold_total, warm_total)} "
        f"search_ids={_speedup(cold_ids, warm_ids)} "
        f"post_paint={_speedup(cold_done, warm_done)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", default="", help="PIN for login pages")
    parser.add_argument("--query", default="a", help="Search query")
    parser.add_argument("--port", type=int, default=8840, help="Temporary local port")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    server_cmd = [
        sys.executable,
        "web_ui.py",
        "--port",
        str(args.port),
    ]

    proc = subprocess.Popen(
        server_cmd,
        cwd=str(ROOT),
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        _wait_for_server(base_url + "/")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(
                headless=True,
                args=["--no-sandbox", "--disable-setuid-sandbox", "--disable-dev-shm-usage"],
            )
            context = browser.new_context(
                viewport={"width": 1440, "height": 900},
                ignore_https_errors=True,
            )
            page = context.new_page()

            _prepare_page(page, base_url, args.pin or None)
            _run_search(page, args.query)
            cold = _capture_grouped(page, wait_before_click_ms=0)

            _prepare_page(page, base_url, args.pin or None)
            _run_search(page, args.query)
            warm = _capture_grouped(page, wait_before_click_ms=1200)

            _print_summary(args.query, cold, warm)

            print(json.dumps({
                "base_url": base_url,
                "query": args.query,
                "cold": cold,
                "warm": warm,
            }, ensure_ascii=False, indent=2))

            context.close()
            browser.close()
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
