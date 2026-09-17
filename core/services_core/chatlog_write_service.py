"""Synchronous write helpers for chatlog API routes."""

from __future__ import annotations


def delete_chatlog_conversation(conv_id: int) -> bool:
    from core.services_core.db_state import get_db
    from extensions.builtin_chatlog.core_impl import store

    con = get_db()
    try:
        result = store.delete_conversation(con, conv_id)
        con.commit()
        return result
    except Exception:
        con.rollback()
        raise


def save_chatlog_ai_result(
    conv_id: int,
    summary: str,
    topics: list[str],
    decisions: list[str],
    model: str,
) -> None:
    from core.services_core.db_state import get_db
    from extensions.builtin_chatlog.core_impl.store_ai import save_ai_result

    con = get_db()
    save_ai_result(con, conv_id, summary, topics, decisions, model)
    con.commit()


def replace_chatlog_entities(conv_id: int, entities: list[dict]) -> None:
    from core.services_core.db_state import get_db
    from extensions.builtin_chatlog.core_impl.store_entities import (
        delete_entities_for_conversation,
        insert_entities,
    )

    con = get_db()
    delete_entities_for_conversation(con, conv_id)
    if entities:
        insert_entities(con, conv_id, entities)
    con.commit()


def import_chatlog_payload(source: str, json_data, *, job=None):
    from core.services_core.db_state import get_db
    from extensions.builtin_chatlog.core_impl.importer import import_chatlog

    return import_chatlog(get_db(), source, json_data, job=job)
