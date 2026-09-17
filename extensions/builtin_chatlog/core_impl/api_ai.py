"""Chatlog API: AI preprocessing-related endpoints.

Summary retrieval, batch reprocessing, topic and decision search.
"""

from __future__ import annotations

import logging
import threading

from quart import jsonify, request

from core.event_bus import emit
from core.event_bus.event_types import (
    CHATLOG_REPROCESS_COMPLETE,
    CHATLOG_REPROCESS_ERROR,
    CHATLOG_REPROCESS_PROGRESS,
    CHATLOG_REPROCESS_START,
)
from core.services_core.db_state import get_readonly_db
from core.services_core.db_write import submit_db_write

from . import store
from .chatlog_ai import process_conversation
from .store_ai import (
    get_decisions,
    get_summary,
    get_topics,
    get_unprocessed_count,
    get_unprocessed_ids,
    search_by_topic,
    search_decisions,
)

logger = logging.getLogger(__name__)

# Reprocessing job management
_reprocess_lock = threading.Lock()
_reprocess_running = False


def api_conversation_summary(conv_id: int):
    """GET /api/conversations/<id>/summary"""
    store.ensure_tables()
    con = get_readonly_db()

    conv = store.get_conversation(con, conv_id)
    if not conv:
        return jsonify({"error": "not found"}), 404

    summary = get_summary(con, conv_id)
    topics = get_topics(con, conv_id)
    decisions_list = get_decisions(con, conv_id)

    result = {
        "conversation_id": conv_id,
        "title": conv.get("title", ""),
        "summary": summary,
        "topics": topics,
        "decisions": decisions_list,
        "ai_processed": summary is not None,
    }

    # On-demand generation: generate=1 parameter + unprocessed
    if not summary and request.args.get("generate") == "1":
        messages = conv.get("messages", [])
        if messages:
            try:
                ai_result = process_conversation(messages)
                submit_db_write(
                    lambda: _save_ai_result(
                        conv_id,
                        ai_result.summary,
                        ai_result.topics,
                        ai_result.decisions,
                        ai_result.model,
                    )
                )
                result["summary"] = ai_result.summary
                result["topics"] = ai_result.topics
                result["decisions"] = [
                    {"decision_text": d} for d in ai_result.decisions
                ]
                result["ai_processed"] = True
            except Exception as exc:
                logger.warning("On-demand summary failed for conv %d: %s", conv_id, exc)
                result["ai_error"] = str(exc)

    return jsonify(result)


async def api_chat_reprocess():
    """POST /api/chat/reprocess -- batch reprocessing."""
    global _reprocess_running

    with _reprocess_lock:
        if _reprocess_running:
            return jsonify({"error": "reprocess already running"}), 409
        _reprocess_running = True

    body = await request.get_json(silent=True) or {}
    target = body.get("target", "unprocessed")

    def _run():
        global _reprocess_running
        try:
            store.ensure_tables()
            con = get_readonly_db()

            if target == "all":
                total_row = con.execute(
                    "SELECT COUNT(*) FROM chat_conversations"
                ).fetchone()
                total = total_row[0] if total_row else 0
                conv_ids = (
                    r[0]
                    for r in con.execute("SELECT id FROM chat_conversations ORDER BY id")
                )
            elif isinstance(target, int) or (isinstance(target, str) and target.isdigit()):
                conv_ids = [int(target)]
                total = 1
            else:
                conv_ids = get_unprocessed_ids(con, limit=1000)
                total = len(conv_ids)
            emit(CHATLOG_REPROCESS_START, {"total": total})

            processed = 0
            errors = 0
            for i, cid in enumerate(conv_ids):
                try:
                    conv = store.get_conversation(con, cid)
                    if not conv:
                        continue
                    messages = conv.get("messages", [])
                    if not messages:
                        continue

                    ai_result = process_conversation(messages)
                    submit_db_write(
                        lambda cid=cid, ai_result=ai_result: _save_ai_result(
                            cid,
                            ai_result.summary,
                            ai_result.topics,
                            ai_result.decisions,
                            ai_result.model,
                        )
                    )
                    processed += 1
                except Exception as exc:
                    logger.warning("Reprocess failed for conv %d: %s", cid, exc)
                    errors += 1

                if (i + 1) % 5 == 0 or i == total - 1:
                    emit(CHATLOG_REPROCESS_PROGRESS, {
                        "current": i + 1, "total": total,
                        "processed": processed, "errors": errors,
                    })

            emit(CHATLOG_REPROCESS_COMPLETE, {
                "processed": processed, "errors": errors, "total": total,
            })
            logger.info(
                "Chatlog reprocess complete: %d/%d processed, %d errors",
                processed, total, errors,
            )
        except Exception as exc:
            logger.error("Chatlog reprocess failed: %s", exc)
            emit(CHATLOG_REPROCESS_ERROR, {"error": str(exc)})
        finally:
            _reprocess_running = False

    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return jsonify({"status": "started", "target": target})


def api_chat_reprocess_status():
    """GET /api/chat/reprocess/status"""
    store.ensure_tables()
    con = get_readonly_db()
    unprocessed = get_unprocessed_count(con)
    return jsonify({
        "running": _reprocess_running,
        "unprocessed_count": unprocessed,
    })


def api_topics_search():
    """GET /api/chat/topics/search?q=keyword"""
    store.ensure_tables()
    con = get_readonly_db()

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "q is required"}), 400

    limit = _int_param("limit", 50, 1, 200)
    results = search_by_topic(con, query, limit)
    return jsonify({"results": results, "query": query, "total": len(results)})


def api_chat_decisions():
    """GET /api/chat/decisions?conversation_id=N"""
    store.ensure_tables()
    con = get_readonly_db()

    conv_id_str = request.args.get("conversation_id", "").strip()
    if not conv_id_str:
        return jsonify({"error": "conversation_id is required"}), 400

    try:
        conv_id = int(conv_id_str)
    except ValueError:
        return jsonify({"error": "conversation_id must be an integer"}), 400

    decisions_list = get_decisions(con, conv_id)
    return jsonify({"decisions": decisions_list, "conversation_id": conv_id})


def api_decisions_search():
    """GET /api/chat/decisions/search?q=keyword"""
    store.ensure_tables()
    con = get_readonly_db()

    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "q is required"}), 400

    limit = _int_param("limit", 50, 1, 200)
    results = search_decisions(con, query, limit)
    return jsonify({"results": results, "query": query, "total": len(results)})


def _int_param(name: str, default: int, min_val: int = 0, max_val: int = 10000) -> int:
    try:
        val = int(request.args.get(name, default))
        return max(min_val, min(val, max_val))
    except (ValueError, TypeError):
        return default


def _save_ai_result(
    conv_id: int,
    summary: str,
    topics: list[str],
    decisions: list[str],
    model: str,
) -> None:
    from core.services_core.chatlog_write_service import save_chatlog_ai_result

    save_chatlog_ai_result(conv_id, summary, topics, decisions, model)
