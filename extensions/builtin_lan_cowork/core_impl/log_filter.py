"""Log filter that redacts Authorization Bearer tokens and 6-digit PINs."""
from __future__ import annotations

import logging
import re

_BEARER_RE = re.compile(r"(Bearer\s+)[A-Za-z0-9_\-\.]+", re.IGNORECASE)
_AUTH_KV_RE = re.compile(r"(['\"]?Authorization['\"]?\s*[:=]\s*['\"]?)([^'\"\,\}\s]+)", re.IGNORECASE)
_PIN_KV_RE = re.compile(r"\bpin\s*=\s*\d{6}\b", re.IGNORECASE)


class AuthHeaderRedactFilter(logging.Filter):
    """Redact secrets from log messages before formatting."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
        except Exception:
            return True
        redacted = _BEARER_RE.sub(r"\1[REDACTED]", msg)
        redacted = _AUTH_KV_RE.sub(r"\1[REDACTED]", redacted)
        redacted = _PIN_KV_RE.sub("pin=[REDACTED]", redacted)
        if redacted != msg:
            record.msg = redacted
            record.args = ()
        return True


def install_global_filter() -> None:
    """Install the redaction filter on the root logger (applies to all handlers, including future ones)."""
    logging.getLogger().addFilter(AuthHeaderRedactFilter())
