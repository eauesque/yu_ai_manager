"""Read-only media metadata section rendering."""

from __future__ import annotations

from typing import Any


def build_readonly_media_sections(meta: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(meta, dict):
        return []

    sections: list[dict[str, Any]] = []

    file_rows = []
    if meta.get("container"):
        file_rows.append({"Container": meta.get("container")})
    if meta.get("duration_ms") is not None:
        file_rows.append({"Duration(ms)": meta.get("duration_ms")})
    if meta.get("filesize") is not None:
        file_rows.append({"File size(bytes)": meta.get("filesize")})
    if meta.get("overall_bitrate") is not None:
        file_rows.append({"Bitrate(bps)": meta.get("overall_bitrate")})
    if file_rows:
        sections.append({"title": "Media Metadata (read-only) / File", "display_type": "table", "content": file_rows})

    video = meta.get("video")
    if isinstance(video, dict) and any(v is not None for v in video.values()):
        sections.append(
            {
                "title": "Media Metadata (read-only) / Video",
                "display_type": "table",
                "content": [{k: v for k, v in video.items() if v is not None}],
            }
        )

    audio = meta.get("audio")
    if isinstance(audio, dict) and any(v is not None for v in audio.values()):
        sections.append(
            {
                "title": "Media Metadata (read-only) / Audio",
                "display_type": "table",
                "content": [{k: v for k, v in audio.items() if v is not None}],
            }
        )

    tags = meta.get("tags_readonly")
    if isinstance(tags, dict) and tags:
        sections.append({"title": "Media Metadata (read-only) / Embedded tags", "display_type": "table", "content": [tags]})

    chapters = meta.get("chapters")
    if isinstance(chapters, list) and chapters:
        sections.append({"title": "Media Metadata (read-only) / Chapters", "display_type": "table", "content": chapters})

    return sections
