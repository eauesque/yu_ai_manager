"""Measure search and detail-modal performance against a fresh local server.

Usage:
  python scripts/perf_search_modal.py --pin 1234 --query a

This script starts ``web_ui.py`` on a temporary local port and captures:
1. Initial search action timing.
2. First detail-modal open timing.
3. Second detail-modal open timing for the same result.
"""

from __future__ import annotations

import argparse
import json
import logging
import subprocess
import sys
import time
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse
from urllib.request import urlopen

from playwright.sync_api import sync_playwright

logger = logging.getLogger(__name__)

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


def _run_search(page, query: str) -> dict[str, Any]:
    captured_search_urls: list[str] = []
    captured_search_responses: list[dict[str, Any]] = []

    def _is_primary_search(url: str) -> bool:
        try:
            parsed = urlparse(url)
            if "/api/search" not in parsed.path:
                return False
            qs = parse_qs(parsed.query)
            q_val = (qs.get("q") or [""])[0]
            has_cursor = bool((qs.get("cursor") or [""])[0])
            offset_val = (qs.get("offset") or ["0"])[0]
            return q_val == query and not has_cursor and offset_val == "0"
        except Exception:
            return False

    def _capture_request(request) -> None:
        url = request.url
        if "/api/search?" in url:
            captured_search_urls.append(url)

    def _capture_response(response) -> None:
        url = response.url
        if "/api/search?" not in url:
            return
        try:
            payload = response.json()
        except Exception:
            return
        captured_search_responses.append({
            "url": url,
            "payload": payload,
        })

    page.on("request", _capture_request)
    page.on("response", _capture_response)
    page.evaluate(
        "() => {"
        "  if (!window.__yuPagePerf) window.__yuPagePerf = {};"
        "  window.__yuPagePerf['search-actions'] = {};"
        "  window.__yuPagePerf['search-server'] = {};"
        "}"
    )
    page.fill("#tagQuery", query)
    primary_response = None
    try:
        with page.expect_response(lambda response: _is_primary_search(response.url), timeout=30000) as response_info:
            page.locator("#searchBtn").click()
        response = response_info.value
        primary_response = {
            "url": response.url,
            "payload": response.json(),
        }
    except Exception:
        page.locator("#searchBtn").click()
    page.wait_for_function(
        "() => !!window.__yuPagePerf?.['search-actions']?.search_success",
        timeout=30000,
    )
    page.wait_for_selector("#results .result-card", timeout=30000)
    page.wait_for_timeout(200)
    perf = page.evaluate("() => window.__yuPagePerf")
    try:
        page.remove_listener("request", _capture_request)
        page.remove_listener("response", _capture_response)
    except Exception:
        logger.debug("step failed", exc_info=True)

    primary_request_url = None
    for url in captured_search_urls:
        if _is_primary_search(url):
            primary_request_url = url
            break
    if primary_response is None and primary_request_url:
        for item in captured_search_responses:
            if item.get("url") == primary_request_url:
                primary_response = item
                break
    if primary_response is None:
        for item in captured_search_responses:
            url = item.get("url", "")
            if _is_primary_search(url):
                primary_response = item
                break
    if primary_response is None and captured_search_responses:
        primary_response = captured_search_responses[-1]
    return {
        "request_url": primary_request_url or (captured_search_urls[-1] if captured_search_urls else None),
        "request_urls": captured_search_urls,
        "search-actions": perf.get("search-actions", {}),
        "search-server": (primary_response or {}).get("payload", {}).get("perf", perf.get("search-server", {})),
        "search-response-url": (primary_response or {}).get("url"),
    }


def _open_first_result(page) -> dict[str, Any]:
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
    return perf.get("detail-modal", {})


def _metric(run: dict[str, Any], key: str) -> int | None:
    value = run.get(key)
    return value if isinstance(value, int) else None


def _delta(run: dict[str, Any], start_key: str, end_key: str) -> int | None:
    start = _metric(run, start_key)
    end = _metric(run, end_key)
    if start is None or end is None:
        return None
    return end - start


def _speedup(first: int | None, second: int | None) -> str:
    if first is None or second is None or first <= 0:
        return "n/a"
    return f"{first / max(second, 1):.1f}x"


def _print_summary(
    query: str,
    search_run: dict[str, Any],
    repeat_search_run: dict[str, Any],
    first_modal: dict[str, Any],
    second_modal: dict[str, Any],
) -> None:
    search_actions = search_run.get("search-actions", {})
    search_server = search_run.get("search-server", {})
    repeat_search_actions = repeat_search_run.get("search-actions", {})
    repeat_search_server = repeat_search_run.get("search-server", {})
    request_url = search_run.get("request_url")
    response_url = search_run.get("search-response-url")
    search_network = _delta(search_actions, "search_request_start", "search_response_received")
    search_parse = _delta(search_actions, "search_response_received", "search_json_ready")
    search_paint = _delta(search_actions, "search_json_ready", "results_painted")
    search_total = _delta(search_actions, "search_request_start", "search_success")
    repeat_search_total = _delta(repeat_search_actions, "search_request_start", "search_success")

    first_fetch = _delta(first_modal, "fetch_start", "fetch_done")
    first_shell = _delta(first_modal, "show_detail_start", "shell_opened")
    first_render = _delta(first_modal, "show_detail_start", "render_done")

    second_fetch = _delta(second_modal, "fetch_start", "fetch_done")
    second_shell = _delta(second_modal, "show_detail_start", "shell_opened")
    second_render = _delta(second_modal, "show_detail_start", "render_done")

    print("Search/Modal Perf Summary")
    print(f"query: {query}")
    print(f"search_request_url: {request_url}")
    print(f"search_response_url: {response_url}")
    print(
        "search: "
        f"network={search_network}ms "
        f"parse={search_parse}ms "
        f"paint={search_paint}ms "
        f"total={search_total}ms"
    )
    print(
        "search_server: "
        f"cache_hit={search_server.get('cache_hit', 'n/a')} "
        f"page_cache_hit={search_server.get('page_cache_hit', 'n/a')} "
        f"cache={search_server.get('cache_ms', 'n/a')}ms "
        f"build={search_server.get('build_ms', 'n/a')}ms "
        f"sql={search_server.get('sql_ms', 'n/a')}ms "
        f"query={search_server.get('query_ms', 'n/a')}ms "
        f"rows={search_server.get('rows_ms', 'n/a')}ms "
        f"count={search_server.get('count_ms', 'n/a')}ms "
        f"total={search_server.get('total_ms', 'n/a')}ms"
    )
    print(
        "search_repeat: "
        f"total={repeat_search_total}ms "
        f"page_cache_hit={repeat_search_server.get('page_cache_hit', 'n/a')} "
        f"server_total={repeat_search_server.get('total_ms', 'n/a')}ms"
    )
    print(
        "modal_first: "
        f"fetch={first_fetch}ms "
        f"shell={first_shell}ms "
        f"render={first_render}ms"
    )
    print(
        "modal_second: "
        f"fetch={second_fetch}ms "
        f"shell={second_shell}ms "
        f"render={second_render}ms"
    )
    print(
        "speedup: "
        f"modal_fetch={_speedup(first_fetch, second_fetch)} "
        f"modal_render={_speedup(first_render, second_render)}"
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pin", default="", help="PIN for login pages")
    parser.add_argument("--query", default="a", help="Search query")
    parser.add_argument("--port", type=int, default=8841, help="Temporary local port")
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

            _prepare_page(page, base_url, args.pin or None)
            search_run = _run_search(page, args.query)
            first_modal = _open_first_result(page)

            second_page = context.new_page()
            _prepare_page(second_page, base_url, args.pin or None)
            repeat_search_run = _run_search(second_page, args.query)
            second_modal = _open_first_result(second_page)

            _print_summary(args.query, search_run, repeat_search_run, first_modal, second_modal)
            print(json.dumps({
                "base_url": base_url,
                "query": args.query,
                "search": search_run,
                "search_repeat": repeat_search_run,
                "modal_first": first_modal,
                "modal_second": second_modal,
            }, ensure_ascii=False, indent=2))

            second_page.close()
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
