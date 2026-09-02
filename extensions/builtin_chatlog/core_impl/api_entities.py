"""Chatlog API: entity-related endpoints.

Function group called from create_chatlog_blueprint().
Exposed as routing functions without direct Blueprint registration.
"""

from __future__ import annotations

import logging
import threading

from quart import jsonify, request

from core.services_core.db_state import get_readonly_db
from core.services_core.db_write import submit_db_write

from . import store
from .entity_extractor import extract_from_conversation
from .store_entities import (
    find_conversations_by_entity,
    find_conversations_by_entity_like,
    get_entities_for_conversation,
    get_related_conversations,
)

logger = logging.getLogger(__name__)


def api_entity_search():
    """GET /api/entities/search?type=bug&value=BUG-62"""
    store.ensure_tables()
    con = get_readonly_db()

    entity_type = request.args.get("type", "").strip()
    entity_value = request.args.get("value", "").strip()
    if not entity_type or not entity_value:
        return jsonify({"error": "type and value are required"}), 400

    limit = _int_param("limit", 50, 1, 200)
    exact = request.args.get("exact", "1").strip()

    if exact == "1":
        convs = find_conversations_by_entity(con, entity_type, entity_value, limit)
    else:
        convs = find_conversations_by_entity_like(con, entity_type, entity_value, limit)

    return jsonify({"conversations": convs, "total": len(convs)})


def api_conversation_entities(conv_id: int):
    """GET /api/conversations/<id>/entities"""
    store.ensure_tables()
    con = get_readonly_db()

    conv = store.get_conversation(con, conv_id)
    if not conv:
        return jsonify({"error": "not found"}), 404

    entities = get_entities_for_conversation(con, conv_id)
    return jsonify({"entities": entities, "conversation_id": conv_id})


def api_related_conversations(conv_id: int):
    """GET /api/conversations/<id>/related?limit=5"""
    store.ensure_tables()
    con = get_readonly_db()

    limit = _int_param("limit", 10, 1, 50)
    related = get_related_conversations(con, conv_id, limit)
    return jsonify({"related": related, "conversation_id": conv_id})


def api_entities_reindex():
    """POST /api/entities/reindex -- bulk entity re-extraction from existing data."""
    store.ensure_tables()

    def _reindex():
        con_bg = get_readonly_db()
        rows = con_bg.execute(
            "SELECT id FROM chat_conversations ORDER BY id"
        )
        reindexed = 0
        for row in rows:
            cid = row[0]
            try:
                msg_rows = con_bg.execute(
                    "SELECT id, content FROM chat_messages "
                    "WHERE conversation_id = ? ORDER BY seq",
                    (cid,),
                )
                messages = [
                    {"id": r[0], "content": r[1]} for r in msg_rows
                ]
                entities = extract_from_conversation(messages)
                submit_db_write(
                    lambda cid=cid, entities=entities: _replace_entities(cid, entities)
                )
                reindexed += 1
            except Exception as exc:
                logger.warning("Reindex failed for conv %d: %s", cid, exc)
        logger.info("Entity reindex complete: %d conversations", reindexed)

    t = threading.Thread(target=_reindex, daemon=True)
    t.start()
    return jsonify({"status": "started"})


def _int_param(name: str, default: int, min_val: int = 0, max_val: int = 10000) -> int:
    try:
        val = int(request.args.get(name, default))
        return max(min_val, min(val, max_val))
    except (ValueError, TypeError):
        return default


def _replace_entities(conv_id: int, entities: list[dict]) -> None:
    from core.services_core.chatlog_write_service import replace_chatlog_entities

    replace_chatlog_entities(conv_id, entities)
