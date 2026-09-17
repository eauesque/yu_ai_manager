"""Market overview fetcher (for boss mode)"""

import json
import logging
import threading
import time
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

_market_cache_lock = threading.Lock()
_market_cache_data = None
_market_cache_ts = 0.0
# Wall-clock cap on one refresh of the whole symbol list. Mirrors the Rust
# side's OVERALL_FETCH_BUDGET so both answer within a caller's patience.
_OVERALL_FETCH_BUDGET_SECS = 6.0


def _fallback_payload(now: float) -> dict:
    return {
        "source": "fallback",
        "updated_at": int(now),
        "quotes": [
            {"label": "DOW", "value": "+0.21%"},
            {"label": "NAS", "value": "+0.34%"},
            {"label": "SPX", "value": "+0.18%"},
            {"label": "FTSE", "value": "+0.11%"},
            {"label": "USDX", "value": "-0.09%"},
        ],
    }


def _fetch_one_chart(sym: str, timeout: float = 2.5) -> dict:
    """Fetch the daily change rate for a single symbol via the v8 chart API."""
    url = (
        "https://query1.finance.yahoo.com/v8/finance/chart/"
        + urllib.parse.quote(sym, safe="")
        + "?range=1d&interval=1d"
    )
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8", errors="ignore"))


def market_quotes_fallback_payload(now: float | None = None) -> dict:
    """The static rows, for callers that gave up waiting on the live fetch."""
    return _fallback_payload(time.time() if now is None else now)


def _fetch_quotes(now: float) -> dict:
    fallback = _fallback_payload(now)
    symbol_map: list = [
        ("DOW", "^DJI"),
        ("NAS", "^IXIC"),
        ("SPX", "^GSPC"),
        ("FTSE", "^FTSE"),
        ("USDX", "DX-Y.NYB"),
    ]

    # Per-symbol budgets do not bound the loop: five symbols at 2.5s each is
    # 12.5s, and `urlopen`'s timeout does not cover `getaddrinfo` at all, so a
    # host with an unreachable resolver stalls far longer than that. Stop at the
    # deadline with whatever came back -- a ticker widget must not hold the
    # request open. The caller's `asyncio.wait_for` is the outer bound for the
    # case where a single lookup outlasts even this.
    deadline = now + _OVERALL_FETCH_BUDGET_SECS
    try:
        quotes = []
        for label, sym in symbol_map:
            if time.time() >= deadline:
                break
            try:
                data = _fetch_one_chart(sym)
                meta = data["chart"]["result"][0]["meta"]
                price = float(meta.get("regularMarketPrice", 0))
                prev = float(meta.get("chartPreviousClose") or meta.get("previousClose", 0))
                if not prev:
                    continue
                pct = (price - prev) / prev * 100
                sign = "+" if pct >= 0 else "-"
                quotes.append({"label": label, "value": f"{sign}{abs(pct):.2f}%"})
            except Exception as exc:
                logger.debug("quote row skipped: %s", exc)
                continue
        return {
            "source": "yahoo",
            "updated_at": int(now),
            "quotes": quotes if quotes else fallback["quotes"],
        }
    except Exception:
        return fallback


def get_market_quotes_payload() -> dict:
    """Return market overview with caching."""
    global _market_cache_data, _market_cache_ts

    now = time.time()
    with _market_cache_lock:
        if _market_cache_data and (now - _market_cache_ts) < 60:
            return _market_cache_data

    payload = _fetch_quotes(now)

    # Add real news headlines
    try:
        from core.web.pages import _fetch_real_headlines
        headlines = _fetch_real_headlines()
        if headlines:
            import random
            payload["headlines"] = random.sample(headlines, min(3, len(headlines)))
    except Exception:
        logger.warning("service step failed", exc_info=True)

    with _market_cache_lock:
        _market_cache_data = payload
        _market_cache_ts = now
    return payload
