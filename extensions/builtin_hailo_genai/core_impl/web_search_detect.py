import re

_JA_PATTERN = re.compile(r"[\u3040-\u309f\u30a0-\u30ff]")
_CN_DOMAINS = frozenset({
    "zhihu.com", "baidu.com", "bilibili.com", "163.com",
    "sohu.com", "qq.com", "sina.com.cn", "csdn.net",
    "douban.com", "weibo.com", "toutiao.com",
})


def has_cjk(text: str) -> bool:
    return any("\u4e00" <= c <= "\u9fff" for c in text)


def is_japanese_query(text: str) -> bool:
    if _JA_PATTERN.search(text):
        return True
    if not has_cjk(text):
        return False
    try:
        from core.tools.lang_detect import detect_language

        result = detect_language(text)
        if result.lang in ("ja", "unknown"):
            return True
        if result.lang in ("zh", "ko") and result.confidence < 0.8:
            return True
        return result.lang in ("zh", "ko")
    except Exception:
        return True


def is_cn_result(result: dict) -> bool:
    url = result.get("url", "")
    return any(domain in url for domain in _CN_DOMAINS)


def cn_ratio(results: list[dict]) -> float:
    if not results:
        return 0.0
    return sum(1 for r in results if is_cn_result(r)) / len(results)
