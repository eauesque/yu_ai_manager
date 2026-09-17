import logging
import re

from .web_search_detect import is_cn_result, is_japanese_query

log = logging.getLogger(__name__)

_DEFAULT_MAX_RESULTS = 5
_SNIPPET_MAX_LEN = 200


def ddgs_search(query: str, *, region: str, max_results: int) -> list[dict]:
    try:
        from ddgs import DDGS
        use_new_api = True
    except ImportError:
        try:
            from duckduckgo_search import DDGS
            use_new_api = False
        except ImportError:
            log.warning("ddgs not installed: uv pip install ddgs")
            return []

    results = []
    try:
        if use_new_api:
            raw = DDGS().text(query, max_results=max_results)
        else:
            with DDGS() as ddgs:
                raw = list(ddgs.text(query, region=region, max_results=max_results))
        for r in raw:
            results.append({
                "title": r.get("title", ""),
                "url": r.get("href", ""),
                "snippet": (r.get("body") or "")[:_SNIPPET_MAX_LEN],
            })
    except Exception as exc:
        log.warning("Web search failed: %s", exc)
    return results


def search_web(query: str, *, max_results: int = _DEFAULT_MAX_RESULTS, region: str = "wt-wt") -> list[dict]:
    if not is_japanese_query(query):
        return ddgs_search(query, region=region, max_results=max_results)

    en_keywords = ja_to_en_keywords(query)
    en_results = ddgs_search(en_keywords, region="wt-wt", max_results=max_results)
    log.info("JA query '%s' -> EN '%s': %d results", query, en_keywords, len(en_results))
    if len(en_results) >= max_results:
        return en_results[:max_results]

    ja_query = query
    hiragana_count = sum(1 for c in query if "\u3040" <= c <= "\u309f")
    if hiragana_count < 3:
        ja_query = query + " について"

    ja_results = ddgs_search(ja_query, region="jp-jp", max_results=max_results)
    merged = list(en_results)
    seen_urls = {r["url"] for r in en_results}
    for result in (r for r in ja_results if not is_cn_result(r)):
        if result["url"] in seen_urls:
            continue
        merged.append(result)
        seen_urls.add(result["url"])
    return merged[:max_results]


def ja_to_en_keywords(query: str) -> str:
    keyword_map = [
        ("仮想通貨", "cryptocurrency"), ("ビットコイン", "bitcoin"), ("半導体", "semiconductor"),
        ("原油価格", "crude oil price"), ("石油価格", "crude oil price"), ("原油", "crude oil"),
        ("石油", "crude oil"), ("ガソリン", "gasoline"), ("天然ガス", "natural gas"),
        ("株価", "stock price"), ("為替レート", "exchange rate"), ("為替", "exchange rate"),
        ("金価格", "gold price"), ("金利", "interest rate"), ("天気予報", "weather forecast"),
        ("天気", "weather"), ("ニュース", "news"), ("最新", "latest"), ("本日", "today"),
        ("今日", "today"), ("明日", "tomorrow"), ("昨日", "yesterday"), ("推移", "trend"),
        ("価格", "price"), ("レシピ", "recipe"), ("ドル", "USD"), ("円安", "yen weak"),
        ("円高", "yen strong"), ("円", "yen"), ("金", "gold"), ("銀", "silver"),
        ("地震", "earthquake"), ("台風", "typhoon"), ("選挙", "election"), ("結果", "results"),
        ("スポーツ", "sports"), ("サッカー", "soccer"), ("野球", "baseball"), ("映画", "movie"),
        ("アニメ", "anime"), ("ゲーム", "game"), ("日本", "Japan"), ("東京", "Tokyo"),
        ("大阪", "Osaka"), ("京都", "Kyoto"), ("北海道", "Hokkaido"), ("沖縄", "Okinawa"),
    ]
    en_parts = []
    remaining = query
    for ja, en in keyword_map:
        if ja in remaining:
            en_parts.append(en)
            remaining = remaining.replace(ja, " ")
    en_parts.extend(re.findall(r"[A-Za-z0-9]+", remaining))
    return " ".join(en_parts) if en_parts else query
