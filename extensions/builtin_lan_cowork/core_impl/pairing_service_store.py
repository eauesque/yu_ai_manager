"""Persistence helpers for PairingService."""

from __future__ import annotations

import hashlib
import sqlite3

from core.services_core.db_write import submit_db_write

SCRYPT_N = 16384
SCRYPT_R = 8
SCRYPT_P = 1
SCRYPT_MAXMEM = 64 * 1024 * 1024


def hash_pin(pin: str, salt: bytes = b"yu-ai-pairing-pin") -> str:
    return hashlib.scrypt(
        pin.encode("utf-8"),
        salt=salt,
        n=SCRYPT_N,
        r=SCRYPT_R,
        p=SCRYPT_P,
        maxmem=SCRYPT_MAXMEM,
    ).hex()


def submit_write_with_fallback(fn):
    try:
        return submit_db_write(fn)
    except sqlite3.ProgrammingError as exc:
        if "same thread" not in str(exc).lower():
            raise
        return fn()


def provider_supports_cross_thread_execution(provider) -> bool:
    module = getattr(provider, "__module__", "") or ""
    name = getattr(provider, "__name__", "") or ""
    return module == "core.services_core.db_state" and name in {"get_db", "get_readonly_db"}
