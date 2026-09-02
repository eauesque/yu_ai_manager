"""Event rule helpers for timeline-based story detection (file count / tag / source based)."""


def append_productivity_event_if_needed(events, month, prev_count, curr_count):
    """Append productivity up/down events based on monthly growth."""
    if prev_count <= 0:
        return

    growth_rate = (curr_count - prev_count) / prev_count
    if growth_rate > 0.5:
        events.append(
            {
                "date": month,
                "type": "productivity_up",
                "icon": "\U0001f4c8",
                "title_key": "story.event.productivity_up.title",
                "desc_key": "story.event.productivity_up.desc",
                "params": {"percent": f"{int(growth_rate * 100)}"},
            }
        )
    elif growth_rate < -0.3:
        events.append(
            {
                "date": month,
                "type": "productivity_down",
                "icon": "\U0001f4c9",
                "title_key": "story.event.productivity_down.title",
                "desc_key": "story.event.productivity_down.desc",
                "params": {"percent": f"{int(abs(growth_rate) * 100)}"},
            }
        )


_EXCLUDED_SOURCE_TYPES = (
    # internal extractor error markers — not "tools" the user adopted.
    "rar_error",
    "zip_error",
    "unknown",
    "not_modified",
    # generic file-format pseudo-sources rather than user-chosen tools.
    "txt",
    "webp_desc",
)


def _is_real_tool_source(src: str) -> bool:
    if not src:
        return False
    s = str(src).lower()
    if s in _EXCLUDED_SOURCE_TYPES:
        return False
    return not s.endswith("_error")


def append_new_source_event_if_needed(events, month, sources, seen_sources):
    """Append event when a new meta_source appears for the first time.

    Filters out internal error markers (e.g. ``rar_error``, ``zip_error``) and
    generic file-format pseudo-sources so the Story page does not surface them
    as if the user had adopted a new authoring tool.
    """
    for src in sources:
        if src in seen_sources:
            continue
        if not _is_real_tool_source(src):
            continue
        events.append(
            {
                "date": month,
                "type": "new_source",
                "icon": "\U0001f527",
                "title_key": "story.event.new_source.title",
                "desc_key": "story.event.new_source.desc",
                "params": {"source": src},
            }
        )


def append_tag_diversity_event_if_needed(events, month, unique_tags, max_tags_so_far):
    """Append event when monthly unique tag count exceeds previous record."""
    if unique_tags > max_tags_so_far and unique_tags > 10:
        events.append(
            {
                "date": month,
                "type": "tag_diversity",
                "icon": "\U0001f3a8",
                "title_key": "story.event.tag_diversity.title",
                "desc_key": "story.event.tag_diversity.desc",
                "params": {"count": f"{unique_tags:,}"},
            }
        )
