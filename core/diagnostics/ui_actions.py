"""In-memory UI action ring buffer for diagnostics."""

from __future__ import annotations

import datetime as dt
import json
from collections import deque
from typing import Any

_MAX_ITEMS = 200
_MAX_BYTES = 100 * 1024
_ACTIONS: deque[dict[str, Any]] = deque()


def _entry_size(entry: dict[str, Any]) -> int:
    return len(json.dumps(entry, ensure_ascii=False, separators=(",", ":")).encode("utf-8")) + 1


def _total_size() -> int:
    return sum(_entry_size(entry) for entry in _ACTIONS)


def record_action(action: dict[str, Any]) -> None:
    entry = {
        "time": action.get("time") or dt.datetime.now(dt.UTC).isoformat(timespec="seconds"),
        "type": str(action.get("type") or "unknown"),
        "target": str(action.get("target") or ""),
        "page": str(action.get("page") or ""),
    }
    for key, value in action.items():
        if key not in entry:
            entry[str(key)] = value
    _ACTIONS.append(entry)
    while len(_ACTIONS) > _MAX_ITEMS or _total_size() > _MAX_BYTES:
        _ACTIONS.popleft()


def dump_jsonl() -> str:
    return "".join(json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n" for entry in _ACTIONS)


def reset_actions_for_tests() -> None:
    _ACTIONS.clear()
