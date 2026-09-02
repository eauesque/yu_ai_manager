"""Redact secrets from log text before it reaches a reader.

The ring buffer is served to authorized viewers over `/api/logs/*` and, in the
fleet case, to a *remote peer*. Authorization says who may read the buffer; it
says nothing about whether a PIN or a peer token should have been in it. This
module is the second half.

Scrubbing happens on the write side (`LogRingBuffer.append`) rather than on the
read side: a secret that never enters the buffer cannot be handed out by a route
that forgets to call the scrubber.
"""

from __future__ import annotations

import re

MASK = "***"

# Keys whose value is a secret wherever it appears. Matched case-insensitively
# against a whole word, so `token_count` and `pinned` are not touched.
_SECRET_KEYS = (
    "api_key",
    "apikey",
    "authorization",
    "cookie",
    "db_key",
    "passphrase",
    "password",
    "pin",
    "secret",
    "session_key",
    "token",
)
_KEY_ALT = "|".join(_SECRET_KEYS)

# key=value / key: value / "key": "value" -- quoted or bare, JSON or logfmt.
_KV = re.compile(
    rf"""(?ix)
    (?P<key>(?<![A-Za-z0-9_])(?:{_KEY_ALT})(?![A-Za-z0-9_]))
    (?P<sep>\s*["']?\s*[=:]\s*["']?)
    (?P<value>[^\s,;&"'}}\]]+)
    """
)

# Authorization: Bearer <...> and the same shape inside a header dump.
_BEARER = re.compile(r"(?i)\b(bearer|basic)\s+([A-Za-z0-9._~+/=-]{8,})")

# Command lines: --pin 1234, --db-key hunter2 (the space form the KV rule misses).
_CLI_FLAG = re.compile(
    rf"(?i)(--(?:{_KEY_ALT}|db-key|session-key)(?:=|\s+))(?P<value>[^\s,;\"']+)"
)


def scrub_secrets(text: str) -> str:
    """Return *text* with secret-looking values replaced by ``***``.

    The key is kept so the reader still sees that a token was involved -- a line
    reading ``token=***`` is a usable log line, ``***`` alone is not.
    """
    if not text:
        return text
    out = _CLI_FLAG.sub(lambda m: f"{m.group(1)}{MASK}", text)
    out = _BEARER.sub(lambda m: f"{m.group(1)} {MASK}", out)
    return _KV.sub(lambda m: f"{m.group('key')}{m.group('sep')}{MASK}", out)
