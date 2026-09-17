"""Chatlog API: Quart Blueprint factory.

Import routes and helpers are split into api_import.py.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from quart import Blueprint, jsonify, render_template, request

from core.services_core.db_state import get_readonly_db
from core.services_core.db_write import submit_db_write

from . import store
from .api_ai import (
    api_chat_decisions,
    api_chat_reprocess,
    api_chat_reprocess_status,
    api_conversation_summary,
    api_decisions_search,
    api_topics_search,
)
from .api_entities import (
    api_conversation_entities,
    api_entities_reindex,
    api_entity_search,
    api_related_conversations,
)
from .api_import import (  # noqa: F401 -- re-export for backward compat
    extract_json_from_zip as _extract_json_from_zip,
)
from .api_import import (
    int_param as _int_param,
)
from .api_import import (
    register_import_routes,
)
from .store_search import search_messages_grouped
from .text_search import search_all as text_search_all

logger = logging.getLogger(__name__)


from core.web.auth_helpers import require_admin_scope as _require_admin_scope


def _parse_date_param(name: str) -> int:
    """Convert an ISO 8601 date string to a UNIX timestamp.

    Accepts '2026-02-01', '2026-02-01T12:00:00', '2026-02-01T12:00:00Z', etc.
    Returns 0 if the parameter is empty or invalid.
    """
    val = request.args.get(name, "").strip()
    if not val:
        return 0
    try:
        # If numeric, treat directly as UNIX timestamp
        return int(val)
    except ValueError:
        pass
    try:
        val = val.replace("Z", "+00:00")
        dt = datetime.fromisoformat(val)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return int(dt.timestamp())
    except (ValueError, OverflowError):
        return 0


def create_chatlog_blueprint(import_name: str) -> Blueprint:
    """Create and return the Chatlog Quart Blueprint."""

    bp = Blueprint(
        "chatlog",
        import_name,
        template_folder="templates",
    )

    def _admin_guard(fn):
        async def _wrapped(*args, **kwargs):
            auth_err = _require_admin_scope()
            if auth_err:
                return auth_err
            result = fn(*args, **kwargs)
            if hasattr(result, "__await__"):
                return await result
            return result

        _wrapped.__name__ = getattr(fn, "__name__", "wrapped")
        return _wrapped

    # -- UI page --

    @bp.route("/")
    async def index():
        return await render_template("chatlog/chatlog.html")

    # -- API: conversation list --

    @bp.route("/api/conversations")
    async def api_conversations():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()

        source = request.args.get("source", "").strip()
        model = request.args.get("model", "").strip()
        query = request.args.get("query", "").strip()
        date_from = _int_param("date_from", 0, 0)
        date_to = _int_param("date_to", 0, 0)
        # ISO 8601 date parameters (after/before)
        after_ts = _parse_date_param("after")
        before_ts = _parse_date_param("before")
        if after_ts and not date_from:
            date_from = after_ts
        if before_ts and not date_to:
            date_to = before_ts
        sort = request.args.get("sort", "updated_at")
        limit = _int_param("limit", 50, 1, 500)
        offset = _int_param("offset", 0, 0)

        convs = store.list_conversations(
            con, source=source, model=model, query=query,
            date_from=date_from, date_to=date_to,
            sort=sort, limit=limit, offset=offset,
        )
        total = store.count_conversations(
            con, source=source, model=model, query=query,
        )

        return jsonify({"conversations": convs, "total": total})

    # -- API: conversation detail --

    @bp.route("/api/conversations/<int:conv_id>")
    async def api_conversation_detail(conv_id: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()

        conv = store.get_conversation(con, conv_id)
        if not conv:
            return jsonify({"error": "not found"}), 404
        return jsonify(conv)

    # -- API: message full-text search --

    @bp.route("/api/search")
    async def api_search():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()

        query = request.args.get("query", "").strip()
        if not query:
            return jsonify({"error": "query is required"}), 400

        source = request.args.get("source", "").strip()
        limit = _int_param("limit", 50, 1, 200)
        offset = _int_param("offset", 0, 0)
        group_by = request.args.get("group_by", "").strip()

        if group_by == "conversation":
            groups = search_messages_grouped(
                con, query, source=source, limit=limit,
            )
            return jsonify({"groups": groups, "query": query})

        results = store.search_messages(
            con, query, source=source, limit=limit, offset=offset,
        )
        return jsonify({"results": results, "query": query})

    # -- Import routes (multipart, path, status) --

    register_import_routes(bp)

    # -- API: delete conversation --

    @bp.route("/api/conversations/<int:conv_id>", methods=["DELETE"])
    async def api_delete_conversation(conv_id: int):
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        from core.services_core.chatlog_write_service import delete_chatlog_conversation

        ok = submit_db_write(lambda: delete_chatlog_conversation(conv_id))
        if not ok:
            return jsonify({"error": "not found"}), 404
        return jsonify({"status": "deleted", "id": conv_id})

    # -- API: statistics --

    @bp.route("/api/stats")
    async def api_stats():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()
        return jsonify(store.get_stats(con))

    # -- API: cross-text search --

    @bp.route("/api/text-search")
    async def api_text_search():
        auth_err = _require_admin_scope()
        if auth_err:
            return auth_err
        store.ensure_tables()
        con = get_readonly_db()

        query = request.args.get("q", "").strip()
        if not query:
            return jsonify({"error": "q is required"}), 400

        targets = request.args.get("target", "md,chat,prompt").strip()
        limit = _int_param("limit", 20, 1, 200)

        results = text_search_all(con, query, targets=targets, limit=limit)
        return jsonify({"results": results, "query": query, "total": len(results)})

    # -- API: entity search --
    bp.add_url_rule(
        "/api/entities/search", "api_entity_search",
        _admin_guard(api_entity_search),
    )
    bp.add_url_rule(
        "/api/conversations/<int:conv_id>/entities",
        "api_conversation_entities",
        _admin_guard(api_conversation_entities),
    )
    bp.add_url_rule(
        "/api/conversations/<int:conv_id>/related",
        "api_related_conversations",
        _admin_guard(api_related_conversations),
    )
    bp.add_url_rule(
        "/api/entities/reindex", "api_entities_reindex",
        _admin_guard(api_entities_reindex), methods=["POST"],
    )

    # -- API: AI preprocessing --
    bp.add_url_rule(
        "/api/conversations/<int:conv_id>/summary",
        "api_conversation_summary",
        _admin_guard(api_conversation_summary),
    )
    bp.add_url_rule(
        "/api/chat/reprocess", "api_chat_reprocess",
        _admin_guard(api_chat_reprocess), methods=["POST"],
    )
    bp.add_url_rule(
        "/api/chat/reprocess/status", "api_chat_reprocess_status",
        _admin_guard(api_chat_reprocess_status),
    )
    bp.add_url_rule(
        "/api/chat/topics/search", "api_topics_search",
        _admin_guard(api_topics_search),
    )
    bp.add_url_rule(
        "/api/chat/decisions", "api_chat_decisions",
        _admin_guard(api_chat_decisions),
    )
    bp.add_url_rule(
        "/api/chat/decisions/search", "api_decisions_search",
        _admin_guard(api_decisions_search),
    )

    return bp
