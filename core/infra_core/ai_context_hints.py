"""Config hints rules for /api/ai-context.

Rules: O(N settings), IO-free, in-memory snapshot only. No network, no DB queries.
Doctor integration: Phase 3+ (doctor will import this module at that point).
"""

from __future__ import annotations

from typing import Any


def get_config_hints(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Return config hint entries from an in-memory config snapshot.

    All rules are IO-free and operate on the already-loaded config dict.
    Rule 3 uses secret=True + default=None as a heuristic proxy for required
    fields — it may produce false positives (optional secrets) or miss
    non-secret required fields.
    """
    hints: list[dict[str, Any]] = []

    # Rule 1: LAN access enabled without PIN
    server = config.get("server") or {}
    if server.get("lan") and not server.get("pin"):
        hints.append({
            "key": "server.pin",
            "severity": "warning",
            "message": "PIN 未設定で LAN アクセスが有効です。PIN を設定することを推奨します",
        })

    # Rule 2: Claude API key not set
    ai = config.get("ai_analysis") or {}
    if not ai.get("api_key"):
        hints.append({
            "key": "ai_analysis.api_key",
            "severity": "info",
            "message": "Claude API キー未設定。AI 分析機能が無効になっています",
        })

    # Rule 3: Unset secret fields (heuristic: secret=True AND default=None)
    # Caveat: keychain-backed secrets not yet accessed may appear empty even when set.
    _RULE1_RULE2_KEYS = frozenset(("server.pin", "ai_analysis.api_key"))
    from core.settings_core.settings_schema import SETTINGS_SCHEMA, resolve_dotted_key

    for s in SETTINGS_SCHEMA:
        if not s.secret or s.default is not None:
            continue
        if s.key in _RULE1_RULE2_KEYS:
            continue
        val = resolve_dotted_key(config, s.key)
        if val is None or (isinstance(val, str) and not val.strip()):
            hints.append({
                "key": s.key,
                "severity": "info",
                "message": f"未設定のシークレット項目（ヒューリスティック）: {s.description}",
            })

    return hints
