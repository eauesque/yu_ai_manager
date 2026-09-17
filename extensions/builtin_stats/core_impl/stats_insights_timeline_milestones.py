"""Milestone event helpers for timeline insights."""


_MILESTONE_DEFS = [
    (100, "milestone_100", "\U0001f389"),
    (500, "milestone_500", "\U0001f389"),
    (1000, "milestone_1k", "\U0001f38a"),
    (2000, "milestone_2k", "\U0001f38a"),
    (5000, "milestone_5k", "\U0001f48e"),
    (10000, "milestone_10k", "\U0001f48e"),
    (50000, "milestone_50k", "\U0001f451"),
    (100000, "milestone_100k", "\U0001f451"),
]


def append_milestone_events(events, timeline, months):
    """Append cumulative count milestone events in chronological order."""
    achieved = {event.get("type") for event in events}
    cumulative = 0

    for month in months:
        cumulative += timeline[month]["count"]
        for threshold, event_type, icon in _MILESTONE_DEFS:
            if cumulative >= threshold and event_type not in achieved:
                events.append(
                    {
                        "date": month,
                        "type": event_type,
                        "icon": icon,
                        "title_key": "story.event." + event_type + ".title",
                        "desc_key": "story.event." + event_type + ".desc",
                        "params": {"total": f"{cumulative:,}"},
                    }
                )
                achieved.add(event_type)
