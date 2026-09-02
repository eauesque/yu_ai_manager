"""Help page and API endpoint routes.

User guide (user/) and developer guide (developer/) two-category structure.
Merges docs/{lang}/help/ files with existing docs under docs/{lang}/ via path mapping.
No symlinks (Windows incompatible).

i18n: docs/{lang}/... preferred, fallback to docs/ja/...

Actual data definitions and markdown conversion are in help_data and help_md modules.
"""

from quart import Blueprint, render_template, request

from core.help_api.help_data import (
    CATEGORY_SECTIONS,
    SECTION_FLAT,
    USER_SECTIONS,
    build_toc,
    detect_lang,
    get_section_title,
    read_section,
)
from core.help_api.help_md import md_to_html, search_content
from core.infra_core.api_errors import api_error, api_success
from core.services_core.db_async import run_db_sync

bp = Blueprint("help", __name__)


# -- Page routes ---------------------------------------------------------------

@bp.route("/help")
async def help_index():
    """Help top page (show first section of user guide)."""
    lang = detect_lang()
    toc = build_toc(lang)
    first = USER_SECTIONS[0][0] if USER_SECTIONS else ""
    content_html = ""
    if first:
        md = await run_db_sync(read_section, first, lang)
        if md:
            content_html = md_to_html(md)
    return await render_template(
        "help.html",
        active="help",
        toc=toc,
        current_section=first,
        current_category="user",
        current_lang=lang,
        content_html=content_html,
    )


@bp.route("/help/<section>")
async def help_section(section: str):
    """Section page."""
    lang = detect_lang()
    if section not in SECTION_FLAT:
        return await render_template(
            "help.html",
            active="help",
            toc=build_toc(lang),
            current_section="",
            current_category="",
            current_lang=lang,
            content_html="<p>\u30bb\u30af\u30b7\u30e7\u30f3\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002</p>",
        ), 404
    cat = SECTION_FLAT[section]
    md = await run_db_sync(read_section, section, lang)
    content_html = md_to_html(md) if md else "<p>\u30b3\u30f3\u30c6\u30f3\u30c4\u304c\u898b\u3064\u304b\u308a\u307e\u305b\u3093\u3002</p>"
    return await render_template(
        "help.html",
        active="help",
        toc=build_toc(lang),
        current_section=section,
        current_category=cat,
        current_lang=lang,
        content_html=content_html,
    )


# -- API routes ----------------------------------------------------------------

@bp.route("/api/help/toc")
async def api_help_toc():
    """Table of contents JSON (with categories, language-aware)."""
    lang = detect_lang()
    return api_success({"toc": build_toc(lang), "lang": lang})


@bp.route("/api/help/content/<section>")
async def api_help_content(section: str):
    """Section content JSON."""
    lang = detect_lang()
    if section not in SECTION_FLAT:
        return api_error("Section not found", 404)
    cat = SECTION_FLAT[section]
    md = await run_db_sync(read_section, section, lang)
    if not md:
        return api_error("Content not found", 404)
    title = get_section_title(section, lang)
    # Calculate previous/next sections within the same category
    cat_sections = CATEGORY_SECTIONS[cat]
    slugs = [s for s, _ in cat_sections]
    idx = slugs.index(section)
    related = []
    if idx > 0:
        related.append(slugs[idx - 1])
    if idx < len(slugs) - 1:
        related.append(slugs[idx + 1])
    return api_success({
        "section": section,
        "category": cat,
        "title": title,
        "lang": lang,
        "content": md,
        "content_html": md_to_html(md),
        "related": related,
    })


@bp.route("/api/help/search")
async def api_help_search():
    """Help content search."""
    lang = detect_lang()
    query = request.args.get("q", "").strip()
    if not query:
        return api_error("Query parameter 'q' is required", 400)
    limit = min(int(request.args.get("limit", "5")), 20)
    results = await run_db_sync(search_content, query, lang, limit)
    return api_success({"query": query, "lang": lang, "results": results})
