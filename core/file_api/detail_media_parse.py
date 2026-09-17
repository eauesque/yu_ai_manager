"""Read-only media metadata parse/resolve helpers."""

from __future__ import annotations

import json
import time
from typing import Any

from core.extractors.media_ffprobe import MEDIA_METADATA_SCHEMA_VERSION


def _to_int(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except Exception:
        return None


def _normalize_from_legacy_meta(raw: dict[str, Any]) -> dict[str, Any]:
    tags = {}
    for key in ("title", "artist", "album", "genre", "comment", "date"):
        value = raw.get(key)
        if value is not None and str(value).strip():
            tags["creation_time" if key == "date" else key] = str(value).strip()
    duration_ms = None
    try:
        raw_duration = raw.get("duration_sec")
        if raw_duration is not None and raw_duration != "":
            duration_ms = int(float(raw_duration) * 1000.0)
    except Exception:
        duration_ms = None
    return {
        "schema": "media_readonly_v1",
        "source": "mutagen_legacy",
        "container": None,
        "duration_ms": duration_ms,
        "filesize": None,
        "overall_bitrate": None,
        "video": None,
        "audio": None,
        "tags_readonly": tags,
        "chapters": [],
    }


def parse_readonly_media_metadata(meta_source: str, raw_meta_json: str | None) -> dict[str, Any] | None:
    if not str(meta_source or "").startswith("media_"):
        return None
    if not raw_meta_json:
        return None
    try:
        raw = json.loads(raw_meta_json)
    except Exception:
        return None
    if not isinstance(raw, dict):
        return None
    if raw.get("schema") == "media_readonly_v1":
        return raw
    return _normalize_from_legacy_meta(raw)


def resolve_readonly_media_metadata(meta_source: str, raw_meta_json: str | None) -> dict[str, Any]:
    """Resolve read-only metadata with v1 schema upgrade policy."""
    if not str(meta_source or "").startswith("media_"):
        return {"metadata": None, "normalized_json": None, "schedule_reextract": False}
    if not raw_meta_json:
        return {"metadata": None, "normalized_json": None, "schedule_reextract": True}

    try:
        raw = json.loads(raw_meta_json)
    except Exception:
        return {"metadata": None, "normalized_json": None, "schedule_reextract": True}
    if not isinstance(raw, dict):
        return {"metadata": None, "normalized_json": None, "schedule_reextract": True}

    if raw.get("schema") == "media_readonly_v1":
        meta = dict(raw)
        changed = False
        ver = _to_int(meta.get("metadata_schema_version"))
        if ver is None or ver < MEDIA_METADATA_SCHEMA_VERSION:
            meta["metadata_schema_version"] = MEDIA_METADATA_SCHEMA_VERSION
            changed = True
        if not _to_int(meta.get("metadata_extracted_at")):
            meta["metadata_extracted_at"] = int(time.time())
            changed = True
        if not str(meta.get("metadata_source") or "").strip():
            meta["metadata_source"] = "ffprobe"
            changed = True
        normalized_json = json.dumps(meta, ensure_ascii=False) if changed else None
        return {"metadata": meta, "normalized_json": normalized_json, "schedule_reextract": False}

    normalized = _normalize_from_legacy_meta(raw)
    normalized["metadata_schema_version"] = MEDIA_METADATA_SCHEMA_VERSION
    normalized["metadata_extracted_at"] = int(time.time())
    normalized["metadata_source"] = "mutagen_legacy"
    normalized_json = json.dumps(normalized, ensure_ascii=False)
    return {"metadata": normalized, "normalized_json": normalized_json, "schedule_reextract": False}
