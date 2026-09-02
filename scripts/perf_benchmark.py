"""Unified performance benchmark: search + modal + grouped in one run.

Starts a single server and runs all scenarios sequentially, printing a
compact summary and a JSON snapshot for regression comparison.

Usage:
  python scripts/perf_benchmark.py --pin 1234 --query a
  python scripts/perf_benchmark.py --pin 1234 --query a --out results.json
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

# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _wait_for_server(url: str, timeout_sec: int = 60) -> None:
    deadline = time.time() + timeout_sec
    last_error = None
    while time.time() < deadline:
        try:
            with urlopen(url, timeout=5) as resp:
                if resp.status == 200:
                    return
        except Exception as exc:
            last_error = exc
        time.sleep(1.0)
    raise RuntimeError(f"Server did not start: {last_error}")


def _login_if_needed(page, pin: str | None) -> None:
    page.wait_for_timeout(600)
    selector = None
    if page.locator("#pinInput").count():
        selector = "#pinInput"
    elif page.locator("#lockPin").count():
        selector = "#lockPin"
    if not selector:
        return
    if not pin:
        raise RuntimeError("PIN page detected but no --pin was provided")
    page.fill(selector, pin)
    page.press(selector, "Enter")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(900)


def _prepare_page(page, base_url: str, pin: str | None) -> None:
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    _login_if_needed(page, pin)
    page.evaluate(
        "() => {"
        "  localStorage.setItem('yu_page_perf','1');"
        "  localStorage.removeItem('tagdb_search_state');"
        "  localStorage.removeItem('tagdb_search_committed');"
        "  sessionStorage.removeItem('scrollY');"
        "}"
    )
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    page.wait_for_selector("#tagQuery", timeout=20000)


def _delta(d: dict[str, Any], start: str, end: str) -> int | None:
    s = d.get(start)
    e = d.get(end)
    if not isinstance(s, int) or not isinstance(e, int):
        return None
    return e - s


def _fmt(v: int | None) -> str:
    return f"{v}ms" if v is not None else "n/a"


# ---------------------------------------------------------------------------
# Scenario 1: Home load
# ---------------------------------------------------------------------------


def _scenario_home(page, base_url: str, pin: str | None) -> dict[str, Any]:
    """Measure untouched home page load time."""
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    _login_if_needed(page, pin)
    page.evaluate("localStorage.setItem('yu_page_perf','1')")
    t0 = time.perf_counter()
    page.goto(base_url + "/?perf=1", wait_until="domcontentloaded")
    page.wait_for_selector("#tagQuery", timeout=20000)
    load_ms = round((time.perf_counter() - t0) * 1000)
    return {"load_ms": load_ms}


# ---------------------------------------------------------------------------
# Scenario 2: First search
# ---------------------------------------------------------------------------


def _scenario_search(page, query: str) -> dict[str, Any]:
    page.evaluate(
        "() => {"
        "  if (!window.__yuPagePerf) window.__yuPagePerf = {};"
        "  window.__yuPagePerf['search-actions'] = {};"
        "}"
    )
    page.fill("#tagQuery", query)
    page.locator("#searchBtn").click()
    page.wait_for_function(
        "() => !!window.__yuPagePerf?.['search-actions']?.search_success",
        timeout=30000,
    )
    page.wait_for_selector("#results .result-card", timeout=30000)
    page.wait_for_timeout(200)
    perf = page.evaluate("() => window.__yuPagePerf")
    actions = perf.get("search-actions", {})
    return {
        "network_ms": _delta(actions, "search_request_start", "search_response_received"),
        "paint_ms": _delta(actions, "search_json_ready", "results_painted"),
        "total_ms": _delta(actions, "search_request_start", "search_success"),
    }


# ---------------------------------------------------------------------------
# Scenario 3: First modal open
# ---------------------------------------------------------------------------


def _scenario_modal(page) -> dict[str, Any]:
    page.evaluate(
        "() => {"
        "  if (!window.__yuPagePerf) window.__yuPagePerf = {};"
        "  window.__yuPagePerf['detail-modal'] = {};"
        "}"
    )
    page.locator("#results .result-card").first.click()
    page.wait_for_function(
        "() => !!window.__yuPagePerf?.['detail-modal']?.render_done",
        timeout=30000,
    )
    page.wait_for_timeout(200)
    perf = page.evaluate("() => window.__yuPagePerf")
    modal = perf.get("detail-modal", {})
    return {
        "fetch_ms": _delta(modal, "fetch_start", "fetch_done"),
        "shell_ms": _delta(modal, "show_detail_start", "shell_opened"),
        "render_ms": _delta(modal, "show_detail_start", "render_done"),
    }


# ---------------------------------------------------------------------------
# Scenario 4: Grouped mode switch
# ---------------------------------------------------------------------------


def _scenario_grouped(page, query: str, wait_ms: int = 0) -> dict[str, Any]:
    _prepare_page(page, page.url.split("?")[0], None)
    page.fill("#tagQuery", query)
    page.locator("#searchBtn").click()
    page.wait_for_selector("#results .result-card", timeout=30000)
    page.wait_for_timeout(wait_ms)
    page.locator('#resultsGroupControls [data-mode="folder"]').click()
    page.wait_for_function(
        "() => !!window.__yuPagePerf?.['grouping-server']?.index_source",
        timeout=30000,
    )
    page.wait_for_timeout(200)
    perf = page.evaluate("() => window.__yuPagePerf")
    action = perf.get("grouping-action", {})
    server = perf.get("grouping-server", {})
    return {
        "response_ms": action.get("grouping_response_received"),
        "post_paint_ms": action.get("grouping_post_paint_ready"),
        "server_total_ms": server.get("total_ms"),
        "ids_cache_hit": server.get("ids_cache_hit", 0),
        "index_source": server.get("index_source", "unknown"),
    }


# ---------------------------------------------------------------------------
# Summary
# ---------------------------------------------------------------------------


def _print_summary(results: dict[str, Any]) -> None:
    q = results["query"]
    h = results["home"]
    s = results["search"]
    m1 = results["modal_first"]
    m2 = results["modal_second"]
    gc = results["grouped_cold"]
    gw = results["grouped_warm"]

    print("=" * 60)
    print(f"  Performance Benchmark  (query={q})")
    print("=" * 60)
    print(f"  home_load:       {_fmt(h.get('load_ms'))}")
    print(f"  search:          total={_fmt(s.get('total_ms'))}  network={_fmt(s.get('network_ms'))}  paint={_fmt(s.get('paint_ms'))}")
    print(f"  modal_first:     fetch={_fmt(m1.get('fetch_ms'))}  render={_fmt(m1.get('render_ms'))}")
    print(f"  modal_second:    fetch={_fmt(m2.get('fetch_ms'))}  render={_fmt(m2.get('render_ms'))}")
    print(f"  grouped_cold:    resp={_fmt(gc.get('response_ms'))}  server={_fmt(gc.get('server_total_ms'))}  post_paint={_fmt(gc.get('post_paint_ms'))}")
    print(f"  grouped_warm:    resp={_fmt(gw.get('response_ms'))}  server={_fmt(gw.get('server_total_ms'))}  post_paint={_fmt(gw.get('post_paint_ms'))}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description="Unified performance benchmark")
    parser.add_argument("--pin", default="", help="PIN for login pages")
    parser.add_argument("--query", default="a", help="Search query")
    parser.add_argument("--port", type=int, default=8842, help="Temporary local port")
    parser.add_argument("--out", default="", help="Write JSON results to file")
    args = parser.parse_args()

    base_url = f"http://127.0.0.1:{args.port}"
    proc = subprocess.Popen(
        [sys.executable, "web_ui.py", "--port", str(args.port)],
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
            pin = args.pin or None

            # 1. Home load
            home = _scenario_home(page, base_url, pin)

            # 2. First search
            _prepare_page(page, base_url, pin)
            search = _scenario_search(page, args.query)

            # 3. First modal open
            modal_first = _scenario_modal(page)

            # 4. Close modal, second modal open
            page.keyboard.press("Escape")
            page.wait_for_timeout(300)
            modal_second = _scenario_modal(page)

            # 5. Grouped cold (new page, click immediately)
            page2 = context.new_page()
            _prepare_page(page2, base_url, pin)
            grouped_cold = _scenario_grouped(page2, args.query, wait_ms=0)

            # 6. Grouped warm (new page, wait for warm cache)
            page3 = context.new_page()
            _prepare_page(page3, base_url, pin)
            grouped_warm = _scenario_grouped(page3, args.query, wait_ms=1200)

            results = {
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
                "query": args.query,
                "home": home,
                "search": search,
                "modal_first": modal_first,
                "modal_second": modal_second,
                "grouped_cold": grouped_cold,
                "grouped_warm": grouped_warm,
            }

            _print_summary(results)
            json_out = json.dumps(results, ensure_ascii=False, indent=2)
            print(json_out)

            if args.out:
                Path(args.out).write_text(json_out, encoding="utf-8")
                print(f"\nResults written to {args.out}")

            page.close()
            page2.close()
            page3.close()
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
