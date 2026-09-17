"""Chatlog import orchestration.

Parser selection -> intermediate format conversion -> duplicate check -> DB insert -> statistics return
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from . import store
from .entity_extractor import extract_from_conversation
from .parser_chatgpt import parse_chatgpt_json
from .parser_claude import ParsedConversation, parse_claude_json
from .parser_openwebui import parse_openwebui_json
from .store_entities import insert_entities

logger = logging.getLogger(__name__)

_IMPORT_COMMIT_INTERVAL = 25


def _detect_conversation_lang(messages) -> tuple:
    """Detect language from user messages in a conversation. Returns (lang, confidence)."""
    try:
        from core.tools.lang_detect import detect_language

        # Concatenate user messages (max 1000 chars)
        user_texts = []
        total = 0
        for m in messages:
            if m.role == "user" and m.content:
                user_texts.append(m.content)
                total += len(m.content)
                if total >= 1000:
                    break

        if not user_texts:
            return ("", 0.0)

        combined = "\n".join(user_texts)[:1000]
        result = detect_language(combined)
        return (result.lang, result.confidence)
    except Exception:
        return ("", 0.0)


@dataclass
class ImportResult:
    added: int = 0
    skipped: int = 0
    errors: list[str] = field(default_factory=list)
    total: int = 0


class ImportJob:
    """Import progress tracker."""

    def __init__(self) -> None:
        self.phase: str = "idle"
        self.current: int = 0
        self.total: int = 0
        self.message: str = ""
        self.running: bool = False
        self.error: str | None = None
        self.result: ImportResult | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "phase": self.phase,
            "current": self.current,
            "total": self.total,
            "message": self.message,
            "running": self.running,
            "error": self.error,
            "percent": int(self.current / self.total * 100) if self.total else 0,
        }
        if self.result:
            d["result"] = {
                "added": self.result.added,
                "skipped": self.result.skipped,
                "errors": self.result.errors[:10],
                "total": self.result.total,
            }
        return d


_PARSERS = {
    "claude": parse_claude_json,
    "chatgpt": parse_chatgpt_json,
    "openwebui": parse_openwebui_json,
}

VALID_SOURCES = tuple(_PARSERS.keys())


def import_chatlog(
    con: sqlite3.Connection,
    source: str,
    json_data: Any,
    job: ImportJob | None = None,
    use_ai: bool = False,
    ai_config: dict | None = None,
) -> ImportResult:
    """Parse JSON data and import into DB."""
    store.ensure_tables(con)
    result = ImportResult()

    parser = _PARSERS.get(source)
    if not parser:
        result.errors.append(f"Unknown source: {source}")
        return result

    if job:
        job.phase = "parsing"
        job.message = "Parsing JSON..."
        job.running = True

    conversations: list[ParsedConversation] = parser(json_data)
    result.total = len(conversations)

    if job:
        job.total = result.total
        job.phase = "importing"

    for i, conv in enumerate(conversations):
        if job:
            job.current = i + 1
            job.message = f"Importing: {i + 1}/{result.total}"

        try:
            _import_single(con, source, conv, result,
                           use_ai=use_ai, ai_config=ai_config)
            if (i + 1) % _IMPORT_COMMIT_INTERVAL == 0:
                con.commit()
        except Exception as exc:
            result.errors.append(f"{conv.external_id}: {exc}")

    con.commit()

    if job:
        job.phase = "done"
        job.running = False
        job.result = result
        job.message = (
            f"Done: {result.added} added, {result.skipped} skipped"
        )

    return result


def _import_single(
    con: sqlite3.Connection,
    source: str,
    conv: ParsedConversation,
    result: ImportResult,
    use_ai: bool = False,
    ai_config: dict | None = None,
) -> None:
    """Import one conversation with duplicate checking."""
    existing = store.find_by_external_id(con, source, conv.external_id)
    if existing:
        result.skipped += 1
        return

    # Auto-detect conversation language (by concatenating user messages)
    lang, lang_conf = _detect_conversation_lang(conv.messages)

    conv_data = {
        "source": source,
        "external_id": conv.external_id,
        "title": conv.title,
        "model": conv.model,
        "created_at": conv.created_at,
        "updated_at": conv.updated_at,
        "message_count": len(conv.messages),
        "language": lang,
        "language_confidence": lang_conf,
    }

    conv_id = store.insert_conversation(con, conv_data)
    if not conv_id:
        result.errors.append(f"{conv.external_id}: insert failed")
        return

    messages = [
        {
            "role": m.role,
            "content": m.content,
            "created_at": m.created_at,
            "seq": m.seq,
        }
        for m in conv.messages
    ]
    store.insert_messages(con, conv_id, messages)

    # Automatic entity extraction
    try:
        entities = extract_from_conversation(messages)
        if entities:
            insert_entities(con, conv_id, entities)
    except Exception as exc:
        logger.warning("Entity extraction failed for conv %s: %s", conv_id, exc)

    # AI preprocessing (optional)
    if use_ai:
        try:
            from .chatlog_ai import process_conversation
            from .store_ai import save_ai_result
            ai_result = process_conversation(messages, config=ai_config)
            save_ai_result(
                con, conv_id,
                ai_result.summary, ai_result.topics,
                ai_result.decisions, ai_result.model,
            )
        except Exception as exc:
            logger.warning("AI processing failed for conv %s: %s", conv_id, exc)

    result.added += 1
