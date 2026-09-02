"""Timeline event/turning-point detection for stats APIs."""

from .stats_insights_timeline_event_rules import (
    append_new_source_event_if_needed,
    append_productivity_event_if_needed,
    append_tag_diversity_event_if_needed,
)
from .stats_insights_timeline_milestones import append_milestone_events


def detect_resolution_changes(timeline):
    """Detect major resolution changes over timeline (legacy, returns empty)."""
    return []


def detect_story_events(timeline):
    """Detect story-like events from monthly timeline data.

    timeline format: {month: {count, unique_tags, sources: {src: n}}}
    Events use title_key/desc_key + params for i18n.
    """
    events = []
    months = sorted(timeline.keys())
    if not months:
        return events

    first_month = months[0]
    first_data = timeline[first_month]

    # First month event
    events.append(
        {
            "date": first_month,
            "type": "first_month",
            "icon": "\U0001f305",
            "title_key": "story.event.first_month.title",
            "desc_key": "story.event.first_month.desc",
            "params": {"count": f"{first_data['count']:,}"},
        }
    )

    prev_count = first_data["count"]
    seen_sources = set(first_data.get("sources", {}).keys())
    max_tags = first_data.get("unique_tags", 0)

    # Track monthly counts to find peak
    peak_month = first_month
    peak_count = first_data["count"]

    for month in months[1:]:
        data = timeline[month]
        curr_count = data["count"]
        unique_tags = data.get("unique_tags", 0)
        sources = data.get("sources", {})

        # Track peak
        if curr_count > peak_count:
            peak_month = month
            peak_count = curr_count

        # Productivity changes
        append_productivity_event_if_needed(events, month, prev_count, curr_count)

        # New source detection
        append_new_source_event_if_needed(events, month, sources, seen_sources)
        seen_sources.update(sources.keys())

        # Tag diversity record
        append_tag_diversity_event_if_needed(events, month, unique_tags, max_tags)
        if unique_tags > max_tags:
            max_tags = unique_tags

        prev_count = curr_count

    # Peak month event (only if we have 3+ months of data)
    if len(months) >= 3 and peak_month != months[-1]:
        events.append(
            {
                "date": peak_month,
                "type": "peak_month",
                "icon": "\U0001f525",
                "title_key": "story.event.peak_month.title",
                "desc_key": "story.event.peak_month.desc",
                "params": {"count": f"{peak_count:,}"},
            }
        )

    # Quiet month: find the month with minimum activity (excluding first/last)
    if len(months) >= 5:
        inner = months[1:-1]
        quiet_month = min(inner, key=lambda m: timeline[m]["count"])
        quiet_count = timeline[quiet_month]["count"]
        avg_count = sum(timeline[m]["count"] for m in months) / len(months)
        if quiet_count < avg_count * 0.3:
            events.append(
                {
                    "date": quiet_month,
                    "type": "quiet_month",
                    "icon": "\U0001f319",
                    "title_key": "story.event.quiet_month.title",
                    "desc_key": "story.event.quiet_month.desc",
                    "params": {"count": f"{quiet_count:,}"},
                }
            )

    # Milestones
    append_milestone_events(events, timeline, months)

    events.sort(key=lambda x: x["date"])
    return events
