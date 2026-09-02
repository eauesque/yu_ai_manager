"""Model/resolution stats builders."""

from importlib import import_module

# Import from relocated stats extension
_stats_insights = import_module("extensions.builtin_stats.core_impl.stats_insights")
detect_resolution_changes = _stats_insights.detect_resolution_changes
from core.stats_api.models_resolutions_sql import get_model_stats_rows, get_resolution_stats_sql


def _build_model_timeline(rows):
    timeline = {}
    model_totals = {}
    for row in rows:
        month = row[0] or "unknown"
        model = row[1] if row[1] and row[1] != "Unknown" else "Unknown"
        count = row[2]
        timeline.setdefault(month, {})[model] = count
        model_totals[model] = model_totals.get(model, 0) + count
    top_models = sorted(model_totals.items(), key=lambda x: (x[1], x[0]), reverse=True)[:10]
    return timeline, top_models, len(model_totals)


def _build_resolution_timeline(rows):
    timeline = {}
    resolution_totals = {}
    for row in rows:
        month = row[0]
        raw = row[1]
        if raw is None:
            continue
        resolution = raw.strip()
        count = row[2]
        if not resolution or len(resolution) > 20:
            continue
        timeline.setdefault(month, {})[resolution] = count
        resolution_totals[resolution] = resolution_totals.get(resolution, 0) + count
    top_resolutions = sorted(
        resolution_totals.items(), key=lambda x: (x[1], x[0]), reverse=True
    )[:10]
    return timeline, top_resolutions


def build_model_stats(con):
    models = get_model_stats_rows(con)
    timeline, top_models, total_models = _build_model_timeline(models)
    return {
        "timeline": timeline,
        "top_models": [{"model": m[0], "count": m[1]} for m in top_models],
        "total_models": total_models,
    }


def build_resolution_stats(con):
    resolutions = con.execute(get_resolution_stats_sql())
    timeline, top_resolutions = _build_resolution_timeline(resolutions)
    return {
        "timeline": timeline,
        "top_resolutions": [{"resolution": r[0], "count": r[1]} for r in top_resolutions],
        "turning_points": detect_resolution_changes(timeline),
    }
