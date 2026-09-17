"""Markdown to HTML conversion and help content search.

Lightweight Markdown parser for the help system, plus keyword search
across all help categories.
"""

import re
from html import escape as _html_escape

from core.help_api.help_data import (
    CATEGORIES,
    CATEGORY_SECTIONS,
    get_title,
    read_section,
)


def escape_html(text: str) -> str:
    """HTML escape for XSS prevention."""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#039;")
    )


def inline_md(text: str) -> str:
    """Convert inline Markdown to HTML.

    Input text is escaped first, then Markdown notation is converted.
    """
    # Escape first to prevent XSS
    text = escape_html(text)
    # Code (escaped backticks)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    # Bold
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Italic
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Link (block javascript: / data: URIs)
    def _safe_link(m):
        label, href = m.group(1), m.group(2)
        if re.match(r"\s*(javascript|data|vbscript)\s*:", href, re.IGNORECASE):
            return label
        return f'<a href="{href}">{label}</a>'
    text = re.sub(r"\[([^\]]+)\]\(([^)]+)\)", _safe_link, text)
    return text


def md_to_html(md_text: str) -> str:
    """Simple Markdown to HTML conversion."""
    lines = md_text.split("\n")
    html_lines: list[str] = []
    in_code_block = False
    in_list = False
    in_ol = False
    in_table = False
    table_header_done = False

    def _close_list():
        nonlocal in_list, in_ol
        if in_list:
            html_lines.append("</ul>")
            in_list = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False

    for line in lines:
        # Code block
        if line.strip().startswith("```"):
            if in_code_block:
                html_lines.append("</code></pre>")
                in_code_block = False
            else:
                lang = line.strip()[3:].strip()
                cls = f' class="language-{_html_escape(lang)}"' if lang else ""
                html_lines.append(f"<pre><code{cls}>")
                in_code_block = True
            continue

        if in_code_block:
            html_lines.append(
                line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
            )
            continue

        stripped = line.strip()

        # Table
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                _close_list()
                in_table = True
                table_header_done = False
                html_lines.append('<div class="table-wrap"><table>')
            # Skip separator row
            if re.match(r"^\|[\s\-:|]+\|$", stripped):
                table_header_done = True
                continue
            cells = [c.strip() for c in stripped.strip("|").split("|")]
            tag = "th" if not table_header_done else "td"
            row = "".join(f"<{tag}>{inline_md(c)}</{tag}>" for c in cells)
            html_lines.append(f"<tr>{row}</tr>")
            continue
        elif in_table:
            html_lines.append("</table></div>")
            in_table = False
            table_header_done = False

        # Empty line
        if not stripped:
            _close_list()
            html_lines.append("")
            continue

        # Heading
        m = re.match(r"^(#{1,6})\s+(.+)$", stripped)
        if m:
            _close_list()
            level = len(m.group(1))
            text = inline_md(m.group(2))
            # Add id to h2 (for in-page anchors)
            slug_id = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
            if level == 2:
                html_lines.append(f'<h{level} id="{slug_id}">{text}</h{level}>')
            else:
                html_lines.append(f"<h{level}>{text}</h{level}>")
            continue

        # Blockquote (lines starting with > -> tip/note box)
        if stripped.startswith("> "):
            _close_list()
            bq_text = inline_md(stripped[2:])
            # Detect > **Note**: ... or > **Tip**: ... patterns
            if bq_text.startswith("<strong>Note</strong>") or bq_text.startswith("<strong>\u6ce8\u610f</strong>"):
                html_lines.append(f'<div class="help-note">{bq_text}</div>')
            elif bq_text.startswith("<strong>Tip</strong>") or bq_text.startswith("<strong>\u30d2\u30f3\u30c8</strong>"):
                html_lines.append(f'<div class="help-tip">{bq_text}</div>')
            elif bq_text.startswith("<strong>Warning</strong>") or bq_text.startswith("<strong>\u8b66\u544a</strong>"):
                html_lines.append(f'<div class="help-warning">{bq_text}</div>')
            else:
                html_lines.append(f"<blockquote>{bq_text}</blockquote>")
            continue

        # Ordered list
        m_ol = re.match(r"^\d+\.\s+(.+)$", stripped)
        if m_ol:
            if not in_ol:
                _close_list()
                html_lines.append("<ol>")
                in_ol = True
            html_lines.append(f"<li>{inline_md(m_ol.group(1))}</li>")
            continue

        # Unordered list
        if stripped.startswith("- ") or stripped.startswith("* "):
            if not in_list:
                _close_list()
                html_lines.append("<ul>")
                in_list = True
            html_lines.append(f"<li>{inline_md(stripped[2:])}</li>")
            continue

        _close_list()

        # Horizontal rule
        if re.match(r"^[-*_]{3,}$", stripped):
            html_lines.append("<hr>")
            continue

        # Normal text
        html_lines.append(f"<p>{inline_md(stripped)}</p>")

    _close_list()
    if in_table:
        html_lines.append("</table></div>")
    if in_code_block:
        html_lines.append("</code></pre>")

    return "\n".join(html_lines)


# Keyword alias map: query term -> list of section slugs to boost
_SEARCH_ALIASES: dict[str, list[str]] = {
    "port": ["getting-started"],
    "url": ["getting-started"],
    "5000": ["getting-started"],
    "address": ["getting-started"],
    "localhost": ["getting-started"],
    "start": ["getting-started"],
    "install": ["getting-started"],
    "setup": ["getting-started"],
    "uv": ["getting-started"],
    "pip": ["getting-started"],
    "pin": ["settings", "getting-started"],
    "password": ["settings"],
    "lan": ["getting-started", "settings"],
    "network": ["settings", "getting-started"],
    "bluesky": ["social"],
    "github": ["social"],
    "bsky": ["social"],
}


def search_content(query: str, lang: str, limit: int = 5) -> list[dict]:
    """Search help content by keyword across all categories."""
    query_lower = query.lower().strip()
    # Split into tokens for AND search; fall back to full-string if single token
    tokens = [t for t in query_lower.split() if t]
    if not tokens:
        return []
    results = []

    # Priority slugs from alias map
    priority_slugs = set()
    for alias, slugs in _SEARCH_ALIASES.items():
        if alias in query_lower:
            priority_slugs.update(slugs)

    def _search_sections(sections_iter, skip_slugs=None):
        for cat, sections in sections_iter:
            cat_titles = dict(CATEGORIES).get(cat, {})
            for slug, titles in sections:
                if skip_slugs and slug in skip_slugs:
                    continue
                content = read_section(slug, lang)
                if not content:
                    continue
                content_lower = content.lower()
                # All tokens must appear (AND logic)
                if not all(t in content_lower for t in tokens):
                    continue
                # Build snippet around the first token occurrence
                idx = content_lower.index(tokens[0])
                start = max(0, idx - 50)
                end = min(len(content), idx + len(tokens[0]) + 100)
                snippet = content[start:end].replace("\n", " ").strip()
                if start > 0:
                    snippet = "..." + snippet
                if end < len(content):
                    snippet = snippet + "..."
                results.append({
                    "section": slug,
                    "category": cat,
                    "category_title": escape_html(
                        get_title(cat_titles, lang)
                        if isinstance(cat_titles, dict)
                        else cat_titles
                    ),
                    "title": escape_html(get_title(titles, lang)),
                    "snippet": escape_html(snippet),
                })
                if len(results) >= limit:
                    return

    # First pass: priority slugs from alias map
    if priority_slugs:
        priority_sections = [
            (cat, [(slug, titles) for slug, titles in secs if slug in priority_slugs])
            for cat, secs in CATEGORY_SECTIONS.items()
        ]
        _search_sections(priority_sections)

    # Second pass: remaining sections
    if len(results) < limit:
        _search_sections(CATEGORY_SECTIONS.items(), skip_slugs=priority_slugs)

    return results
