"""Personality inference from stats time-period distributions."""


def analyze_personality(period_data, total):
    """Analyze personality from time-period activity data.

    Returns i18n key-based result for frontend translation.
    Keys follow the pattern: stats.personality.<key_name>.<type|description|advice>
    """
    if total == 0:
        return {"type_key": "unknown"}

    night_ratio = period_data.get("night", 0) / total
    dawn_ratio = period_data.get("dawn", 0) / total
    day_ratio = period_data.get("day", 0) / total
    evening_ratio = period_data.get("evening", 0) / total

    if night_ratio > 0.4:
        return {"type_key": "night_owl"}
    if dawn_ratio > 0.3:
        return {"type_key": "early_bird"}
    if day_ratio > 0.5:
        return {"type_key": "daytime"}
    if evening_ratio > 0.5:
        return {"type_key": "evening"}
    return {"type_key": "balanced"}
