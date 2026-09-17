"""Help system data definitions and content reader.

Category/section definitions, path mapping, language detection,
and markdown file reading logic.
"""

from pathlib import Path

from quart import request

# Project root / docs directory
DOCS_DIR = Path(__file__).resolve().parents[2] / "docs"

# Supported languages
SUPPORTED_LANGS = ("ja", "en")
DEFAULT_LANG = "ja"

# Category definitions (slug, {lang: title})
CATEGORIES: list[tuple[str, dict[str, str]]] = [
    ("user", {"ja": "\u30e6\u30fc\u30b6\u30fc\u30ac\u30a4\u30c9", "en": "User Guide"}),
    ("lan", {"ja": "LAN\u30fbAI \u9023\u643a", "en": "LAN & AI"}),
    ("developer", {"ja": "\u958b\u767a\u8005\u30ac\u30a4\u30c9", "en": "Developer Guide"}),
]

# Section definitions (per category, display order)
USER_SECTIONS: list[tuple[str, dict[str, str]]] = [
    ("getting-started", {"ja": "\u306f\u3058\u3081\u306b", "en": "Getting Started"}),
    ("quickstart", {"ja": "\u30af\u30a4\u30c3\u30af\u30b9\u30bf\u30fc\u30c8", "en": "Quickstart"}),
    ("use-cases", {"ja": "\u30e6\u30fc\u30b9\u30b1\u30fc\u30b9\u96c6", "en": "Use Cases"}),
    ("search", {"ja": "\u691c\u7d22", "en": "Search"}),
    ("scan", {"ja": "\u30b9\u30ad\u30e3\u30f3", "en": "Scan"}),
    ("scheduler", {"ja": "\u30bf\u30b9\u30af\u30b9\u30b1\u30b8\u30e5\u30fc\u30e9", "en": "Task Scheduler"}),
    ("bridges", {"ja": "Bridge \u9023\u643a", "en": "Bridge Integration"}),
    ("social", {"ja": "SNS\u30fb\u5916\u90e8\u9023\u643a", "en": "SNS & External"}),
    ("sns", {"ja": "SNS \u5171\u6709\u30fbBluesky", "en": "SNS Share & Bluesky"}),
    ("github", {"ja": "GitHub \u9023\u643a", "en": "GitHub Integration"}),
    ("lora-training-guide", {"ja": "LoRA \u5b66\u7fd2", "en": "LoRA Training"}),
    ("deployment", {"ja": "\u30c7\u30d7\u30ed\u30a4\u30e1\u30f3\u30c8\u30fb\u904b\u7528", "en": "Deployment"}),
    ("performance-tuning", {"ja": "\u30d1\u30d5\u30a9\u30fc\u30de\u30f3\u30b9\u8abf\u6574", "en": "Performance Tuning"}),
    ("hailo-setup", {"ja": "Hailo-10H \u30bb\u30c3\u30c8\u30a2\u30c3\u30d7", "en": "Hailo-10H Setup"}),
    ("os-isolation", {"ja": "OS \u30ec\u30d9\u30eb\u9694\u96e2", "en": "OS Isolation"}),
    ("settings", {"ja": "\u8a2d\u5b9a", "en": "Settings"}),
    ("troubleshooting", {"ja": "\u30c8\u30e9\u30d6\u30eb\u30b7\u30e5\u30fc\u30c6\u30a3\u30f3\u30b0", "en": "Troubleshooting"}),
]

LAN_SECTIONS: list[tuple[str, dict[str, str]]] = [
    ("llm-router", {"ja": "LLM Router \u6982\u8981", "en": "LLM Router Overview"}),
    ("llm-router-setup", {"ja": "LLM Router \u30bb\u30c3\u30c8\u30a2\u30c3\u30d7", "en": "LLM Router Setup"}),
    ("gateway", {"ja": "Gateway", "en": "Gateway"}),
    ("lan-cowork", {"ja": "LAN Cowork \u6982\u8981", "en": "LAN Cowork Overview"}),
    ("lan-cowork-auth", {"ja": "\u30d4\u30a2\u8a8d\u8a3c\u30fb\u30da\u30a2\u30ea\u30f3\u30b0", "en": "Peer Auth & Pairing"}),
    ("distributed-inference", {"ja": "\u5206\u6563\u63a8\u8ad6 \u30bb\u30c3\u30c8\u30a2\u30c3\u30d7", "en": "Distributed Inference Setup"}),
]

DEV_SECTIONS: list[tuple[str, dict[str, str]]] = [
    ("api", {"ja": "API \u6982\u8981", "en": "API Overview"}),
    ("api-security", {"ja": "API \u30bb\u30ad\u30e5\u30ea\u30c6\u30a3\u6307\u91dd", "en": "API Security Guidelines"}),
    ("api-reference", {"ja": "API \u30ea\u30d5\u30a1\u30ec\u30f3\u30b9", "en": "API Reference"}),
    ("mcp", {"ja": "MCP \u9023\u643a", "en": "MCP Integration"}),
    ("extensions", {"ja": "\u62e1\u5f35\u6a5f\u80fd", "en": "Extensions"}),
    ("extension-security", {"ja": "Extension \u30bb\u30ad\u30e5\u30ea\u30c6\u30a3", "en": "Extension Security"}),
    ("plugin-development", {"ja": "Extension \u958b\u767a", "en": "Extension Development"}),
    ("custom-ui", {"ja": "\u30ab\u30b9\u30bf\u30e0 UI", "en": "Custom UI"}),
    ("events", {"ja": "SSE \u30a4\u30d9\u30f3\u30c8", "en": "SSE Events"}),
    ("theming", {"ja": "\u30c6\u30fc\u30de\u958b\u767a", "en": "Theming"}),
    ("debugging", {"ja": "\u30c7\u30d0\u30c3\u30b0", "en": "Debugging"}),
    ("dev-docs", {"ja": "\u958b\u767a\u30c9\u30ad\u30e5\u30e1\u30f3\u30c8\u7d22\u5f15", "en": "Dev Documents Index"}),
]

CATEGORY_SECTIONS: dict[str, list[tuple[str, dict[str, str]]]] = {
    "user": USER_SECTIONS,
    "lan": LAN_SECTIONS,
    "developer": DEV_SECTIONS,
}

# slug -> relative path within docs/{lang}/ (language-independent)
# Slugs not registered here are searched from docs/{lang}/help/{cat}/{slug}.md
PATH_MAP: dict[str, str] = {
    "api-reference": "api/README.md",
    "plugin-development": "plugin-development/getting-started.md",
    "custom-ui": "custom-ui/README.md",
    "events": "api/events.md",
    "theming": "api/theming.md",
    # LAN & AI section
    "llm-router": "llm-router/README.md",
    "llm-router-setup": "llm-router/setup.md",
    "gateway": "guides/gateway.md",
    "lan-cowork": "lan-cowork/README.md",
    "lan-cowork-auth": "lan-cowork/peer-auth.md",
    "distributed-inference": "mesh-inference/setup.md",
}

# Flat map (slug -> category)
SECTION_FLAT: dict[str, str] = {}
for _cat, _secs in CATEGORY_SECTIONS.items():
    for _slug, _titles in _secs:
        SECTION_FLAT[_slug] = _cat


def detect_lang() -> str:
    """Detect language from request: ?lang= > Accept-Language > default."""
    # 1. Query parameter
    lang = request.args.get("lang", "").strip().lower()
    if lang in SUPPORTED_LANGS:
        return lang
    # 2. Accept-Language header
    accept = request.headers.get("Accept-Language", "")
    for part in accept.split(","):
        code = part.split(";")[0].strip().split("-")[0].lower()
        if code == "jp":
            code = "ja"
        if code in SUPPORTED_LANGS:
            return code
    return DEFAULT_LANG


def get_title(titles: dict[str, str], lang: str) -> str:
    """Return title for the given language."""
    return titles.get(lang, titles.get(DEFAULT_LANG, ""))


def read_section(slug: str, lang: str = DEFAULT_LANG) -> str | None:
    """Read markdown file content.

    Resolution order:
    1. If slug is in PATH_MAP -> docs/{lang}/{rel_path}
    2. docs/{lang}/help/{cat}/{slug}.md
    3. Fallback to docs/ja/... (default language)
    """
    def _try_path_map(l: str) -> str | None:
        if slug in PATH_MAP:
            p = DOCS_DIR / l / PATH_MAP[slug]
            if p.is_file():
                return p.read_text(encoding="utf-8")
        return None

    def _try_help(l: str) -> str | None:
        for cat in ("user", "developer"):
            p = DOCS_DIR / l / "help" / cat / f"{slug}.md"
            if p.is_file():
                return p.read_text(encoding="utf-8")
        return None

    # 1-2. Try requested language
    result = _try_path_map(lang) or _try_help(lang)
    if result:
        return result
    # 3. Fallback to default language
    if lang != DEFAULT_LANG:
        result = _try_path_map(DEFAULT_LANG) or _try_help(DEFAULT_LANG)
        if result:
            return result
    return None


def build_toc(lang: str = DEFAULT_LANG) -> list[dict]:
    """Build table of contents data for templates."""
    toc = []
    for cat, cat_titles in CATEGORIES:
        sections = []
        for slug, titles in CATEGORY_SECTIONS[cat]:
            sections.append({
                "slug": slug,
                "title": get_title(titles, lang),
            })
        toc.append({
            "category": cat,
            "category_title": get_title(cat_titles, lang),
            "sections": sections,
        })
    return toc


def get_section_title(slug: str, lang: str) -> str:
    """Get section title from slug."""
    cat = SECTION_FLAT.get(slug)
    if not cat:
        return ""
    for s, titles in CATEGORY_SECTIONS[cat]:
        if s == slug:
            return get_title(titles, lang)
    return ""
