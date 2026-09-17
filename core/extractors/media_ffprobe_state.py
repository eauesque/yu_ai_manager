"""State helpers for ffprobe extraction results."""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from typing import Any

from core.extractors.media_ffprobe_constants import MEDIA_METADATA_SCHEMA_VERSION


def now_ts() -> int:
    return int(time.time())


def get_ffprobe_source_version() -> str:
    if shutil.which("ffprobe") is None:
        return ""
    try:
        proc = subprocess.run(["ffprobe", "-version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=2)
        line = (proc.stdout or "").splitlines()[0] if proc.returncode == 0 else ""
        if line.startswith("ffprobe version "):
            return line.replace("ffprobe version ", "", 1).strip()
        return line.strip()
    except Exception:
        return ""


def build_state_envelope(
    *,
    cache_state: str,
    source_version: str,
    error_code: str | None,
    fingerprint_mtime: int | None,
    fingerprint_size: int | None,
    fingerprint_hash: str | None,
    next_retry_after: int | None = None,
) -> dict[str, Any]:
    ts = now_ts()
    return {
        "schema": "media_readonly_v1",
        "metadata_schema_version": MEDIA_METADATA_SCHEMA_VERSION,
        "metadata_extracted_at": ts,
        "metadata_source": "ffprobe",
        "metadata_source_version": source_version or "",
        "cache_state": cache_state,
        "error_code": error_code,
        "error_at": ts if error_code else None,
        "next_retry_after": next_retry_after,
        "fingerprint": {
            "mtime": fingerprint_mtime,
            "size": fingerprint_size,
            "hash": fingerprint_hash,
        },
    }


def build_failure_result(
    *,
    error_code: str,
    source_version: str,
    fingerprint_mtime: int | None,
    fingerprint_size: int | None,
    fingerprint_hash: str | None,
) -> dict[str, Any]:
    next_retry_after = now_ts() + 24 * 60 * 60
    env = build_state_envelope(
        cache_state="error",
        source_version=source_version,
        error_code=error_code,
        fingerprint_mtime=fingerprint_mtime,
        fingerprint_size=fingerprint_size,
        fingerprint_hash=fingerprint_hash,
        next_retry_after=next_retry_after,
    )
    return {
        "success": False,
        "meta_source": "media_error_ffprobe",
        "format": "media",
        "raw_prompt": None,
        "raw_negative": None,
        "raw_meta_json": json.dumps(env, ensure_ascii=False),
        "tag_source": None,
        "error_code": error_code,
    }
