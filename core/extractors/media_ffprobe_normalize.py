"""Normalization helpers for ffprobe payloads."""

from __future__ import annotations

from typing import Any


def _to_int(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v))
    except Exception:
        return None


def _to_ms(v: Any) -> int | None:
    try:
        if v is None or v == "":
            return None
        return int(float(v) * 1000.0)
    except Exception:
        return None


def _fps_from_ratio(value: Any) -> float | None:
    s = str(value or "").strip()
    if not s or s in {"0/0", "N/A"}:
        return None
    if "/" in s:
        a, b = s.split("/", 1)
        try:
            af = float(a)
            bf = float(b)
            if bf == 0:
                return None
            return round(af / bf, 3)
        except Exception:
            return None
    try:
        return round(float(s), 3)
    except Exception:
        return None


def _pick_stream(payload: dict[str, Any], codec_type: str) -> dict[str, Any]:
    for st in payload.get("streams", []) or []:
        if str(st.get("codec_type", "")).lower() == codec_type:
            return st
    return {}


def _extract_tags(format_tags: dict[str, Any]) -> dict[str, str]:
    aliases = {
        "title": ["title", "TITLE"],
        "comment": ["comment", "COMMENT", "description", "DESCRIPTION"],
        "creation_time": ["creation_time", "DATE", "date"],
        "artist": ["artist", "ARTIST"],
        "album": ["album", "ALBUM"],
        "encoder": ["encoder", "ENCODER"],
        "genre": ["genre", "GENRE"],
    }
    out: dict[str, str] = {}
    for key, keys in aliases.items():
        for k in keys:
            raw = format_tags.get(k)
            if raw is None:
                continue
            value = str(raw).strip()
            if value:
                out[key] = value
                break
    return out


def has_readable_payload(meta: dict[str, Any]) -> bool:
    if meta.get("duration_ms") or meta.get("container"):
        return True
    if isinstance(meta.get("video"), dict) and any(v is not None for v in meta["video"].values()):
        return True
    if isinstance(meta.get("audio"), dict) and any(v is not None for v in meta["audio"].values()):
        return True
    return bool(meta.get("tags_readonly") or meta.get("chapters"))


def derive_prompt_tags(meta: dict[str, Any]) -> tuple[str | None, str | None]:
    tags = meta.get("tags_readonly", {}) or {}
    prompt_parts = [tags.get("title"), tags.get("artist"), tags.get("album"), tags.get("genre")]
    prompt = ", ".join([p for p in prompt_parts if p]) or None
    tag_parts = [tags.get("title"), tags.get("artist"), tags.get("album"), tags.get("genre"), tags.get("comment")]
    tag_source = ", ".join([p for p in tag_parts if p]) or prompt
    return prompt, tag_source


def normalize_ffprobe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    fmt = payload.get("format", {}) or {}
    format_tags = fmt.get("tags", {}) or {}
    tags = _extract_tags(format_tags)

    video = _pick_stream(payload, "video")
    audio = _pick_stream(payload, "audio")

    video_obj = {
        "codec": str(video.get("codec_name") or "") or None,
        "width": _to_int(video.get("width")),
        "height": _to_int(video.get("height")),
        "fps_avg": _fps_from_ratio(video.get("avg_frame_rate")),
        "fps_nominal": _fps_from_ratio(video.get("r_frame_rate")),
        "bitrate": _to_int(video.get("bit_rate")),
        "pix_fmt": str(video.get("pix_fmt") or "") or None,
    }
    audio_obj = {
        "codec": str(audio.get("codec_name") or "") or None,
        "channels": _to_int(audio.get("channels")),
        "sample_rate": _to_int(audio.get("sample_rate")),
        "bitrate": _to_int(audio.get("bit_rate")),
    }
    chapters = []
    for ch in payload.get("chapters", []) or []:
        chapters.append(
            {
                "start_ms": _to_ms(ch.get("start_time")),
                "end_ms": _to_ms(ch.get("end_time")),
                "title": str((ch.get("tags", {}) or {}).get("title") or "") or None,
            }
        )

    format_name = str(fmt.get("format_name") or "")
    container = format_name.split(",")[0] if format_name else None
    return {
        "schema": "media_readonly_v1",
        "container": container,
        "duration_ms": _to_ms(fmt.get("duration")),
        "filesize": _to_int(fmt.get("size")),
        "overall_bitrate": _to_int(fmt.get("bit_rate")),
        "video": video_obj if any(v is not None for v in video_obj.values()) else None,
        "audio": audio_obj if any(v is not None for v in audio_obj.values()) else None,
        "tags_readonly": tags if tags else {},
        "chapters": chapters,
    }
