"""ffprobe extractor execution with retry/timeout handling."""

from __future__ import annotations

import json
import random
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from core.extractors.media_ffprobe_constants import (
    FFPROBE_BACKOFF_MS,
    FFPROBE_RETRY_COUNT,
    FFPROBE_TIMEOUT_MS,
)
from core.extractors.media_ffprobe_normalize import (
    derive_prompt_tags,
    has_readable_payload,
    normalize_ffprobe_payload,
)
from core.extractors.media_ffprobe_state import (
    build_failure_result,
    build_state_envelope,
    get_ffprobe_source_version,
)


def _get_fingerprint(path: Path) -> tuple[int | None, int | None]:
    try:
        st = path.stat()
        return int(st.st_mtime), int(st.st_size)
    except Exception:
        return None, None


def extract_with_ffprobe(path: Path) -> dict[str, Any]:
    source_version = get_ffprobe_source_version()
    if shutil.which("ffprobe") is None:
        return build_failure_result(
            error_code="missing_tool",
            source_version=source_version,
            fingerprint_mtime=None,
            fingerprint_size=None,
            fingerprint_hash=None,
        )

    fingerprint_mtime, fingerprint_size = _get_fingerprint(path)
    timeout_sec = max(1, int(FFPROBE_TIMEOUT_MS / 1000))
    last_error_code = "unknown"

    for attempt in range(FFPROBE_RETRY_COUNT + 1):
        try:
            proc = subprocess.run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-print_format",
                    "json",
                    "-show_format",
                    "-show_streams",
                    "-show_chapters",
                    str(path),
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
            )
            if proc.returncode != 0 or not proc.stdout.strip():
                last_error_code = "nonzero_exit"
            else:
                payload = json.loads(proc.stdout)
                normalized = normalize_ffprobe_payload(payload)
                if not has_readable_payload(normalized):
                    last_error_code = "parse_error"
                else:
                    env = build_state_envelope(
                        cache_state="ready",
                        source_version=source_version,
                        error_code=None,
                        fingerprint_mtime=fingerprint_mtime,
                        fingerprint_size=fingerprint_size,
                        fingerprint_hash=None,
                    )
                    normalized.update(env)
                    kind = "video" if normalized.get("video") else "audio" if normalized.get("audio") else "media"
                    raw_prompt, tag_source = derive_prompt_tags(normalized)
                    return {
                        "success": True,
                        "meta_source": f"media_{kind}_ffprobe",
                        "format": "media",
                        "raw_prompt": raw_prompt,
                        "raw_negative": None,
                        "raw_meta_json": json.dumps(normalized, ensure_ascii=False),
                        "tag_source": tag_source,
                    }
        except subprocess.TimeoutExpired:
            last_error_code = "timeout"
        except json.JSONDecodeError:
            last_error_code = "parse_error"
        except Exception:
            last_error_code = "unknown"

        if attempt < FFPROBE_RETRY_COUNT:
            delay_ms = FFPROBE_BACKOFF_MS + random.randint(0, 200)
            time.sleep(delay_ms / 1000.0)

    return build_failure_result(
        error_code=last_error_code,
        source_version=source_version,
        fingerprint_mtime=fingerprint_mtime,
        fingerprint_size=fingerprint_size,
        fingerprint_hash=None,
    )
