"""WebUI login PIN policy with source-aware migration behavior."""
from __future__ import annotations

import logging
import sys

_MIN_PIN_DIGITS = 8
_WEBUI_CHANGEABLE_SOURCES = frozenset({"config"})

logger = logging.getLogger(__name__)
_pin_none_bypass_logged = False


def classify_pin_action(*, pin: str | None, pin_source: str) -> str:
    """Return one of: "ok", "warn", "block"."""
    global _pin_none_bypass_logged
    if pin_source == "none":
        if not _pin_none_bypass_logged:
            logger.warning("PIN policy floor bypassed: pin_source=none")
            _pin_none_bypass_logged = True
        return "ok"
    if not pin:
        return "ok"
    if len(pin) >= _MIN_PIN_DIGITS:
        return "ok"
    if pin_source in _WEBUI_CHANGEABLE_SOURCES:
        return "warn"
    return "block"


def enforce_startup_pin_policy(*, pin: str | None, pin_source: str) -> bool:
    """Apply startup PIN policy and return True when UI should warn."""
    action = classify_pin_action(pin=pin, pin_source=pin_source)
    if action == "block":
        pin_len = len(pin or "")
        print(
            f"ERROR: --pin が {_MIN_PIN_DIGITS}桁未満です（現在: {pin_len}桁）。\n"
            "起動するには launch-args.txt の --pin を 8桁以上に変更してください。",
            file=sys.stderr,
        )
        raise SystemExit(1)
    return action == "warn"
