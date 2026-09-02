"""Redaction utilities for diagnostics repair bundles."""

from __future__ import annotations

import hashlib
import ipaddress
import re
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from core.web.error_bundle_shared import _SECRET_KEY_RE, _normalize_path_text

REQUIRED_REDACTION_WARNINGS = (
    "Binary EXIF/metadata in PNG/JPEG or other images is not redacted.",
    "Personal-name-like strings are not detected by this redactor.",
    "Text embedded inside screenshots or images is not OCR-redacted.",
    "Log files larger than 1 MB are partially processed and may omit older sensitive data.",
)

VALUE_SECRET_PATTERNS: dict[str, re.Pattern[str]] = {
    "ANTHROPIC": re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}\b"),
    "OPENAI_PROJECT": re.compile(r"\bsk-proj-[A-Za-z0-9_-]{20,}\b"),
    "OPENAI": re.compile(r"\bsk-[A-Za-z0-9]{20,}\b"),
    "BEARER": re.compile(r"\bBearer\s+[A-Za-z0-9._-]{20,}\b"),
    "SLACK_TOKEN": re.compile(r"\bxox[bpoa]-[A-Za-z0-9-]{10,}\b"),
    "GITHUB_PAT": re.compile(r"\bghp_[A-Za-z0-9]{30,}\b"),
    "AWS_ACCESS_KEY": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "GOOGLE_API_KEY": re.compile(r"\bAIza[0-9A-Za-z_-]{35}\b"),
}

_URL_QUERY_SECRET_RE = re.compile(r"([?&](?:api_key|apikey|token|access_token|key)=)([^&\s\"'<>]+)", re.IGNORECASE)
_EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b")
_IPV4_RE = re.compile(r"\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b")
_IPV6_CANDIDATE_RE = re.compile(r"\b[0-9A-Fa-f:]*:[0-9A-Fa-f:.]*\b")
_WINDOWS_HOME_RE = re.compile(r"([A-Za-z]:\\Users\\)[^\\\s\"'<>]+")
_POSIX_HOME_RE = re.compile(r"(/(?:home|Users)/)[^/\s\"'<>]+")
_ABS_PATH_RE = re.compile(
    r"(?<![A-Za-z0-9:<])("
    r"[A-Za-z]:\\(?:[^\s\"'<>|]+\\?)+"
    r"|/(?:var|tmp|etc|opt|usr|mnt|media|Volumes|workspace|srv)/(?:[^\s\"'<>]+/?)+"
    r")"
)
_IMAGE_FILENAME_RE = re.compile(
    r"(?<![A-Za-z0-9_.-])([A-Za-z0-9][A-Za-z0-9_. -]{0,120})\.(png|jpe?g|webp|gif|bmp|tiff?)\b",
    re.IGNORECASE,
)


def _count(counts: dict[str, int], kind: str, amount: int = 1) -> None:
    if amount:
        counts[kind] = counts.get(kind, 0) + amount


def _hash_text(value: str, length: int = 12) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()[:length]


def _replace_with_count(pattern: re.Pattern[str], text: str, kind: str, repl: str, counts: dict[str, int]) -> str:
    def _sub(match: re.Match[str]) -> str:
        _count(counts, kind)
        return repl

    return pattern.sub(_sub, text)


def redact_path(p: str | Path) -> str:
    """Normalize known home path forms using the shared error-bundle helper."""
    normalized = _normalize_path_text(str(p)).replace("<home>", "<USER_HOME>")
    normalized = _WINDOWS_HOME_RE.sub(r"\1<USER_HOME>", normalized)
    return _POSIX_HOME_RE.sub(r"<USER_HOME>", normalized)


def _redact_home_paths(text: str, counts: dict[str, int]) -> str:
    before = text
    text = redact_path(text)
    count = text.count("<USER_HOME>") - before.count("<USER_HOME>")
    _count(counts, "USER_HOME", max(0, count))
    return text


def _redact_image_filenames(text: str, counts: dict[str, int]) -> str:
    def _sub(match: re.Match[str]) -> str:
        _count(counts, "IMAGE_FILENAME")
        basename = f"{match.group(1)}.{match.group(2)}"
        return f"<FILE_{_hash_text(basename, 10)}>." + match.group(2).lower()

    return _IMAGE_FILENAME_RE.sub(_sub, text)


def _redact_abs_paths(text: str, counts: dict[str, int]) -> str:
    def _sub(match: re.Match[str]) -> str:
        value = match.group(1)
        if len(value) < 3:
            return value
        _count(counts, "ABS_PATH")
        return f"<ABS_PATH:{_hash_text(value)}>"

    return _ABS_PATH_RE.sub(_sub, text)


def _redact_ipv6(text: str, counts: dict[str, int]) -> str:
    def _sub(match: re.Match[str]) -> str:
        value = match.group(0)
        try:
            if ipaddress.ip_address(value).version != 6:
                return value
        except ValueError:
            return value
        _count(counts, "IPV6")
        return "<REDACTED:IPV6>"

    return _IPV6_CANDIDATE_RE.sub(_sub, text)


def redact_text(text: str) -> tuple[str, dict[str, int]]:
    counts: dict[str, int] = {}
    redacted = _redact_home_paths(text, counts)
    for kind, pattern in VALUE_SECRET_PATTERNS.items():
        redacted = _replace_with_count(pattern, redacted, kind, f"<REDACTED:{kind}>", counts)
    redacted = _URL_QUERY_SECRET_RE.sub(lambda m: _query_repl(m, counts), redacted)
    redacted = _replace_with_count(_EMAIL_RE, redacted, "EMAIL", "<REDACTED:EMAIL>", counts)
    redacted = _redact_ipv6(redacted, counts)
    redacted = _replace_with_count(_IPV4_RE, redacted, "IPV4", "<REDACTED:IPV4>", counts)
    redacted = _redact_image_filenames(redacted, counts)
    redacted = _redact_abs_paths(redacted, counts)
    return redacted, counts


def _query_repl(match: re.Match[str], counts: dict[str, int]) -> str:
    _count(counts, "URL_QUERY_SECRET")
    return f"{match.group(1)}<REDACTED_QUERY>"


def redact_dict(obj: Any, redacted_counts: dict[str, int]) -> Any:
    if obj is None or isinstance(obj, bool | int | float):
        return obj
    if isinstance(obj, str):
        redacted, counts = redact_text(obj)
        for kind, count in counts.items():
            _count(redacted_counts, kind, count)
        return redacted
    if isinstance(obj, Mapping):
        out: dict[str, Any] = {}
        for key, value in obj.items():
            key_text = str(key)
            if _SECRET_KEY_RE.search(key_text):
                out[key_text] = "<REDACTED:SECRET_KEY>"
                _count(redacted_counts, "SECRET_KEY")
            else:
                out[key_text] = redact_dict(value, redacted_counts)
        return out
    if isinstance(obj, Sequence) and not isinstance(obj, bytes | bytearray):
        return [redact_dict(item, redacted_counts) for item in obj]
    return redact_dict(str(obj), redacted_counts)


def merge_counts(target: dict[str, int], source: Mapping[str, int]) -> None:
    for kind, count in source.items():
        _count(target, kind, count)


def counts_to_report(counts: Mapping[str, int]) -> list[dict[str, int | str]]:
    return [{"type": kind, "count": counts[kind]} for kind in sorted(counts) if counts[kind] > 0]


def compute_warnings(targets: list[Path]) -> list[str]:
    warnings: list[str] = list(REQUIRED_REDACTION_WARNINGS)
    for target in targets:
        try:
            if target.is_file() and target.stat().st_size > 1024 * 1024:
                break
        except OSError:
            continue
    return warnings
