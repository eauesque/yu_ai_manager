"""escape_logger.py — AI agent が escape を記録するためのシンプルなログヘルパー。

使い方（agent から呼び出す）:
    from escape_logger import log_escape, case_fingerprint
    log_escape(
        reason="no_matching_branch",
        rule_set_id="doc-format-charter/classification",
        case_fingerprint_token=case_fingerprint("the raw case text"),
    )
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_FILE = _REPO_ROOT / ".claude" / "escape-log.jsonl"

_SALT = "escape-trigger-hardening-v1"


def case_fingerprint(raw: str) -> str:
    """case 内容のオペーク fingerprint を返す（raw sha256 を避ける）。"""
    salted = f"{_SALT}:{raw}"
    return hashlib.sha256(salted.encode("utf-8")).hexdigest()[:16]


def log_escape(
    reason: str,
    rule_set_id: str,
    case_fingerprint_token: str,
    *,
    log_file: Path | None = None,
) -> None:
    """escape イベントを .claude/escape-log.jsonl に追記する。"""
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "reason": reason,
        "rule_set_id": rule_set_id,
        "case_fingerprint": case_fingerprint_token,
    }
    target = log_file or _LOG_FILE
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
