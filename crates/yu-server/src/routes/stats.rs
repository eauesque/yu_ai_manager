use std::collections::{BTreeMap, HashMap};

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const CACHE_VERSION: i64 = 10;
const AI_WHERE: &str = "(
        f.is_deleted=0
        AND f.meta_source IS NOT NULL
        AND f.meta_source NOT IN ('', 'unknown', 'not_modified')
        AND f.meta_source NOT LIKE 'media_%'
    )";
const TZ_MODIFIER: &str = "localtime";

// Python may serve stale disk-cache snapshots while it rebuilds in the
// background. Rust computes every response fresh but preserves the metadata
// fields that clients and compatibility goldens expect.

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return Json(json!({
                "ok": true,
                "error": null,
                "data": other,
            }))
            .into_response();
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(error: sqlx::Error) -> Response {
    tracing::error!(?error, "failed to build stats response");
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({
            "ok": false,
            "error": "internal_server_error",
        })),
    )
        .into_response()
}

async fn table_sig(pool: &SqlitePool, table: &str, value_expr: &str) -> (i64, i64, i64) {
    let sql = format!(
        "SELECT COUNT(*), COALESCE(MAX(rowid), 0), COALESCE(SUM({value_expr}), 0) FROM {table}"
    );
    match sqlx::query(&sql).fetch_one(pool).await {
        Ok(row) => (
            row.get::<i64, _>(0),
            row.get::<i64, _>(1),
            row.get::<i64, _>(2),
        ),
        Err(_) => (0, 0, 0),
    }
}

async fn table_exists(db: &SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

/// Always computed fresh (uncached): its whole purpose is to be the current
/// signature of the DB, so caching it would let a stale value claim to
/// describe the live state. See `build_stats_all`'s `_stale` computation for
/// how it is combined with the (cached) aggregate blocks instead.
async fn db_signature(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(
            json!({"signature": "", "file_count": 0, "meta_count": 0, "mtime_sum": 0, "mtime_max": 0}),
        );
    }
    let row = sqlx::query(
        "SELECT COUNT(*), COALESCE(MAX(mtime), 0), COALESCE(SUM(mtime), 0),
                  SUM(CASE WHEN is_deleted = 0
                            AND meta_source IS NOT NULL
                            AND meta_source NOT IN ('', 'unknown', 'not_modified')
                            AND meta_source NOT LIKE 'media_%'
                           THEN 1 ELSE 0 END)
           FROM files
           WHERE is_deleted = 0",
    )
    .fetch_one(pool)
    .await?;
    let file_tags_sig = table_sig(pool, "file_tags", "file_id + tag_id").await;
    let tags_sig = table_sig(
        pool,
        "tags",
        "id + length(COALESCE(tag, '')) + length(COALESCE(namespace, ''))",
    )
    .await;
    let monthly_cache_sig = table_sig(pool, "monthly_stats_cache", "updated_at").await;

    Ok(json!([
        row.get::<i64, _>(0),
        row.get::<i64, _>(1),
        row.get::<i64, _>(2),
        row.try_get::<Option<i64>, _>(3)?.unwrap_or(0),
        [file_tags_sig.0, file_tags_sig.1, file_tags_sig.2],
        [tags_sig.0, tags_sig.1, tags_sig.2],
        [
            monthly_cache_sig.0,
            monthly_cache_sig.1,
            monthly_cache_sig.2
        ],
    ]))
}

fn file_count_sig(db_sig: &Value) -> i64 {
    db_sig[0].as_i64().unwrap_or(0)
}

fn max_mtime_sig(db_sig: &Value) -> i64 {
    db_sig[1].as_i64().unwrap_or(0)
}

async fn build_basic_stats(
    pool: &SqlitePool,
    cache: &crate::state::TtlCache<Value>,
) -> Result<(Value, bool), sqlx::Error> {
    cache
        .get_or_try_insert_with_status(|| build_basic_stats_uncached(pool))
        .await
}

async fn build_basic_stats_uncached(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(
            json!({"file_count": 0, "tag_count": 0, "ai_count": 0, "ai_type_counts": {}, "meta_count": 0, "by_source": {}}),
        );
    }
    let file_count =
        sqlx::query_scalar::<_, i64>(&format!("SELECT COUNT(*) FROM files f WHERE {AI_WHERE}"))
            .fetch_one(pool)
            .await?;
    let tag_count = match sqlx::query_scalar::<_, i64>(
        "SELECT CAST(stat_value AS INTEGER) FROM monthly_stats_cache
         WHERE month='_total' AND stat_key='unique_tag_count'",
    )
    .fetch_optional(pool)
    .await
    {
        Ok(Some(value)) => value,
        _ => {
            if !table_exists(pool, "file_tags").await? {
                0
            } else {
                sqlx::query_scalar::<_, i64>(&format!(
                    "SELECT COUNT(DISTINCT ft.tag_id)
                     FROM file_tags ft
                     JOIN files f ON f.id=ft.file_id
                     WHERE {AI_WHERE}"
                ))
                .fetch_one(pool)
                .await?
            }
        }
    };

    let mut sources = BTreeMap::new();
    for row in sqlx::query(&format!(
        "SELECT f.meta_source, COUNT(*) FROM files f WHERE {AI_WHERE} GROUP BY f.meta_source"
    ))
    .fetch_all(pool)
    .await?
    {
        let source = row
            .try_get::<Option<String>, _>(0)?
            .filter(|s| !s.is_empty())
            .unwrap_or_else(|| "unknown".to_string());
        sources.insert(source, row.get::<i64, _>(1));
    }

    let ranked_tags = sqlx::query(&format!(
        "SELECT ft.tag_id, COUNT(*) as cnt
         FROM file_tags ft
         WHERE ft.file_id IN (SELECT f.id FROM files f WHERE {AI_WHERE})
         GROUP BY ft.tag_id
         ORDER BY cnt DESC, ft.tag_id DESC
         LIMIT 20"
    ))
    .fetch_all(pool)
    .await?;
    let ranked: Vec<(i64, i64)> = ranked_tags
        .iter()
        .map(|row| (row.get::<i64, _>(0), row.get::<i64, _>(1)))
        .collect();
    let mut tag_names: HashMap<i64, (String, String)> = HashMap::new();
    if !ranked.is_empty() {
        let ids = ranked
            .iter()
            .map(|(tag_id, _)| tag_id.to_string())
            .collect::<Vec<_>>()
            .join(",");
        for row in sqlx::query(&format!(
            "SELECT id, tag, namespace FROM tags WHERE id IN ({ids})"
        ))
        .fetch_all(pool)
        .await?
        {
            tag_names.insert(
                row.get::<i64, _>(0),
                (
                    row.get::<String, _>(1),
                    row.try_get::<Option<String>, _>(2)
                        .ok()
                        .flatten()
                        .unwrap_or_default(),
                ),
            );
        }
    }
    let top_tags: Vec<Value> = ranked
        .into_iter()
        .filter_map(|(tag_id, count)| {
            let (tag, namespace) = tag_names.get(&tag_id)?;
            Some(json!({
                "tag": tag,
                "namespace": namespace,
                "count": count,
            }))
        })
        .collect();

    let total_files = sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM files WHERE is_deleted=0")
        .fetch_one(pool)
        .await?;
    Ok(json!({
        "file_count": file_count,
        "total_files": total_files,
        "excluded_files": total_files - file_count,
        "tag_count": tag_count,
        "sources": sources,
        "top_tags": top_tags,
    }))
}

fn personality(periods: &BTreeMap<&str, i64>, total: i64) -> Value {
    if total == 0 {
        return json!({"type_key": "unknown"});
    }
    let ratio = |key: &str| *periods.get(key).unwrap_or(&0) as f64 / total as f64;
    let type_key = if ratio("night") > 0.4 {
        "night_owl"
    } else if ratio("dawn") > 0.3 {
        "early_bird"
    } else if ratio("day") > 0.5 {
        "daytime"
    } else if ratio("evening") > 0.5 {
        "evening"
    } else {
        "balanced"
    };
    json!({ "type_key": type_key })
}

fn percentage(count: i64, total: i64) -> f64 {
    if total <= 0 {
        0.0
    } else {
        ((count as f64 / total as f64 * 100.0) * 10.0).round() / 10.0
    }
}

async fn build_hourly_stats(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(json!({
            "periods": {
                "night": {"label_key": "stats.period.night", "count": 0, "percentage": 0.0},
                "dawn": {"label_key": "stats.period.dawn", "count": 0, "percentage": 0.0},
                "day": {"label_key": "stats.period.day", "count": 0, "percentage": 0.0},
                "evening": {"label_key": "stats.period.evening", "count": 0, "percentage": 0.0},
            },
            "heatmap": vec![0_i64; 24],
            "personality": {"type_key": "unknown"},
        }));
    }
    let rows = sqlx::query(&format!(
        "WITH hourly AS (
            SELECT CAST(strftime('%H', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) AS INTEGER) as hour
            FROM files f
            WHERE {AI_WHERE}
        )
        SELECT hour, COUNT(*) as count
        FROM hourly
        GROUP BY hour
        ORDER BY hour"
    ))
    .fetch_all(pool)
    .await?;
    let mut heatmap = vec![0_i64; 24];
    let mut period_data = BTreeMap::from([("night", 0), ("dawn", 0), ("day", 0), ("evening", 0)]);
    for row in rows {
        let hour = row.get::<i64, _>(0);
        let count = row.get::<i64, _>(1);
        if (0..24).contains(&hour) {
            if let Ok(hour) = usize::try_from(hour) {
                heatmap[hour] = count;
            }
        }
        let key = if !(3..21).contains(&hour) {
            "night"
        } else if hour < 9 {
            "dawn"
        } else if hour < 15 {
            "day"
        } else {
            "evening"
        };
        *period_data.entry(key).or_insert(0) += count;
    }
    let total: i64 = period_data.values().sum();
    Ok(json!({
        "periods": {
            "night": {"label_key": "stats.period.night", "count": period_data["night"], "percentage": percentage(period_data["night"], total)},
            "dawn": {"label_key": "stats.period.dawn", "count": period_data["dawn"], "percentage": percentage(period_data["dawn"], total)},
            "day": {"label_key": "stats.period.day", "count": period_data["day"], "percentage": percentage(period_data["day"], total)},
            "evening": {"label_key": "stats.period.evening", "count": period_data["evening"], "percentage": percentage(period_data["evening"], total)},
        },
        "heatmap": heatmap,
        "personality": personality(&period_data, total),
    }))
}

async fn build_timeline_stats(
    pool: &SqlitePool,
    granularity: &str,
    cache: &crate::state::TtlCache<Value>,
) -> Result<(Value, bool), sqlx::Error> {
    // Only the dashboard's default granularity is cached: the cache holds a
    // single value, and "month" is the one every caller (build_stats_all and
    // the bare /api/stats/timeline) asks for. A non-default granularity is a
    // deliberate, infrequent user choice, so it skips the cache rather than
    // evicting the hot value other requests rely on.
    if granularity == "month" {
        return cache
            .get_or_try_insert_with_status(|| build_timeline_stats_uncached(pool, granularity))
            .await;
    }
    Ok((
        build_timeline_stats_uncached(pool, granularity).await?,
        false,
    ))
}

async fn build_timeline_stats_uncached(
    pool: &SqlitePool,
    granularity: &str,
) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(json!({}));
    }
    let format_str = match granularity {
        "day" => "%Y-%m-%d",
        "week" => "%Y-%W",
        "year" => "%Y",
        _ => "%Y-%m",
    };
    let rows = sqlx::query(&format!(
        "SELECT strftime('{format_str}', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as period,
                COUNT(*) as count
         FROM files f
         WHERE {AI_WHERE}
         GROUP BY period
         ORDER BY period"
    ))
    .fetch_all(pool)
    .await?;
    Ok(Value::Array(
        rows.into_iter()
            .map(|row| json!({"period": row.get::<String, _>(0), "count": row.get::<i64, _>(1)}))
            .collect(),
    ))
}

async fn build_model_stats(
    pool: &SqlitePool,
    cache: &crate::state::TtlCache<Value>,
) -> Result<(Value, bool), sqlx::Error> {
    cache
        .get_or_try_insert_with_status(|| build_model_stats_uncached(pool))
        .await
}

async fn build_model_stats_uncached(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(json!({}));
    }
    if !table_exists(pool, "templates").await? {
        return Ok(json!({"timeline": {}, "top_models": [], "total_models": 0}));
    }
    let known = sqlx::query(&format!(
        "SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month,
                tm.model_name as model,
                COUNT(*) as count
         FROM files f
         INNER JOIN templates tm ON tm.file_id = f.id
         WHERE {AI_WHERE}
           AND tm.model_name IS NOT NULL
         GROUP BY month, model"
    ))
    .fetch_all(pool)
    .await?;
    let unknown = sqlx::query(&format!(
        "SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month,
                CASE
                    WHEN f.meta_source IN ('novelai_v4_webp','novelai_v4_png','novelai_v4')
                    THEN 'NovelAI Diffusion V4.5'
                    ELSE 'Unknown'
                END as model,
                COUNT(*) as count
         FROM files f
         WHERE {AI_WHERE}
           AND NOT EXISTS (
               SELECT 1 FROM templates tm
               WHERE tm.file_id = f.id AND tm.model_name IS NOT NULL
           )
         GROUP BY month, model"
    ))
    .fetch_all(pool)
    .await?;

    let mut timeline: BTreeMap<String, BTreeMap<String, i64>> = BTreeMap::new();
    let mut totals: HashMap<String, i64> = HashMap::new();
    for row in known.into_iter().chain(unknown) {
        let month = row
            .try_get::<Option<String>, _>(0)?
            .unwrap_or_else(|| "unknown".to_string());
        let model = row
            .try_get::<Option<String>, _>(1)?
            .filter(|m| !m.is_empty() && m != "Unknown")
            .unwrap_or_else(|| "Unknown".to_string());
        let count = row.get::<i64, _>(2);
        timeline
            .entry(month)
            .or_default()
            .insert(model.clone(), count);
        *totals.entry(model).or_insert(0) += count;
    }
    let total_models = totals.len();
    let mut top_models: Vec<_> = totals.into_iter().collect();
    top_models.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| b.0.cmp(&a.0)));
    top_models.truncate(10);

    Ok(json!({
        "timeline": timeline,
        "top_models": top_models.into_iter().map(|(model, count)| json!({"model": model, "count": count})).collect::<Vec<_>>(),
        "total_models": total_models,
    }))
}

async fn build_resolution_stats(
    pool: &SqlitePool,
    cache: &crate::state::TtlCache<Value>,
) -> Result<(Value, bool), sqlx::Error> {
    cache
        .get_or_try_insert_with_status(|| build_resolution_stats_uncached(pool))
        .await
}

async fn build_resolution_stats_uncached(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(json!({}));
    }
    let rows = sqlx::query(&format!(
        "SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month,
                CASE
                    WHEN f.width > 0 AND f.height > 0
                    THEN (f.width || 'x' || f.height)
                    ELSE NULL
                END as resolution,
                COUNT(*) as count
         FROM files f
         WHERE {AI_WHERE}
         GROUP BY month, resolution
         HAVING resolution IS NOT NULL
         ORDER BY month, count DESC"
    ))
    .fetch_all(pool)
    .await?;
    let mut timeline: BTreeMap<String, BTreeMap<String, i64>> = BTreeMap::new();
    let mut totals: HashMap<String, i64> = HashMap::new();
    for row in rows {
        let month = row.get::<String, _>(0);
        let Some(raw) = row.try_get::<Option<String>, _>(1)? else {
            continue;
        };
        let resolution = raw.trim().to_string();
        if resolution.is_empty() || resolution.len() > 20 {
            continue;
        }
        let count = row.get::<i64, _>(2);
        timeline
            .entry(month)
            .or_default()
            .insert(resolution.clone(), count);
        *totals.entry(resolution).or_insert(0) += count;
    }
    let mut top_resolutions: Vec<_> = totals.into_iter().collect();
    top_resolutions.sort_by(|a, b| b.1.cmp(&a.1).then_with(|| b.0.cmp(&a.0)));
    top_resolutions.truncate(10);
    Ok(json!({
        "timeline": timeline,
        "top_resolutions": top_resolutions.into_iter().map(|(resolution, count)| json!({"resolution": resolution, "count": count})).collect::<Vec<_>>(),
        "turning_points": [],
    }))
}

async fn monthly_file_counts(pool: &SqlitePool) -> Result<BTreeMap<String, i64>, sqlx::Error> {
    let rows = sqlx::query(&format!(
        "SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month,
                COUNT(*) as cnt
         FROM files f WHERE {AI_WHERE}
         GROUP BY month ORDER BY month"
    ))
    .fetch_all(pool)
    .await?;
    Ok(rows
        .into_iter()
        .filter_map(|row| {
            Some((
                row.try_get::<Option<String>, _>(0).ok()??,
                row.get::<i64, _>(1),
            ))
        })
        .collect())
}

async fn monthly_unique_tags(pool: &SqlitePool) -> Result<BTreeMap<String, i64>, sqlx::Error> {
    let fresh = sqlx::query_scalar::<_, i64>(
        "SELECT COALESCE(MAX(updated_at), 0) FROM monthly_stats_cache",
    )
    .fetch_optional(pool)
    .await
    .ok()
    .flatten()
    .is_some_and(|updated_at| {
        std::time::SystemTime::now()
            .duration_since(std::time::UNIX_EPOCH)
            .map(|d| d.as_secs() as i64 - updated_at < 7200)
            .unwrap_or(false)
    });
    if fresh {
        if let Ok(rows) = sqlx::query(
            "SELECT month, CAST(stat_value AS INTEGER) FROM monthly_stats_cache WHERE stat_key='unique_tags'",
        )
        .fetch_all(pool)
        .await
        {
            let cached: BTreeMap<String, i64> = rows
                .into_iter()
                .map(|row| (row.get::<String, _>(0), row.get::<i64, _>(1)))
                .collect();
            if !cached.is_empty() {
                return Ok(cached);
            }
        }
    }

    if !table_exists(pool, "file_tags").await? {
        return Ok(BTreeMap::new());
    }
    let rows = sqlx::query(&format!(
        "SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month,
                COUNT(DISTINCT ft.tag_id) as cnt
         FROM files f
         JOIN file_tags ft ON ft.file_id = f.id
         WHERE {AI_WHERE}
         GROUP BY month ORDER BY month"
    ))
    .fetch_all(pool)
    .await?;
    Ok(rows
        .into_iter()
        .filter_map(|row| {
            Some((
                row.try_get::<Option<String>, _>(0).ok()??,
                row.get::<i64, _>(1),
            ))
        })
        .collect())
}

async fn monthly_sources(
    pool: &SqlitePool,
) -> Result<BTreeMap<String, BTreeMap<String, i64>>, sqlx::Error> {
    let rows = sqlx::query(&format!(
        "SELECT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month,
                COALESCE(f.meta_source, 'other') as src,
                COUNT(*) as cnt
         FROM files f WHERE {AI_WHERE}
         GROUP BY month, src ORDER BY month"
    ))
    .fetch_all(pool)
    .await?;
    let mut result: BTreeMap<String, BTreeMap<String, i64>> = BTreeMap::new();
    for row in rows {
        let Some(month) = row.try_get::<Option<String>, _>(0)? else {
            continue;
        };
        result
            .entry(month)
            .or_default()
            .insert(row.get::<String, _>(1), row.get::<i64, _>(2));
    }
    Ok(result)
}

fn comma_count(count: i64) -> String {
    let s = count.to_string();
    let mut out = String::new();
    for (idx, ch) in s.chars().rev().enumerate() {
        if idx > 0 && idx % 3 == 0 {
            out.push(',');
        }
        out.push(ch);
    }
    out.chars().rev().collect()
}

fn detect_story_events(timeline: &BTreeMap<String, Value>) -> Vec<Value> {
    let months: Vec<_> = timeline.keys().cloned().collect();
    if months.is_empty() {
        return vec![];
    }
    let first_month = &months[0];
    let first_count = timeline[first_month]["count"].as_i64().unwrap_or(0);
    let mut events = vec![json!({
        "date": first_month,
        "type": "first_month",
        "icon": "\u{1f305}",
        "title_key": "story.event.first_month.title",
        "desc_key": "story.event.first_month.desc",
        "params": {"count": comma_count(first_count)},
    })];
    let mut prev_count = first_count;
    let mut seen_sources: std::collections::HashSet<String> = timeline[first_month]["sources"]
        .as_object()
        .map(|m| m.keys().cloned().collect())
        .unwrap_or_default();
    let mut max_tags = timeline[first_month]["unique_tags"].as_i64().unwrap_or(0);
    let mut peak_month = first_month.clone();
    let mut peak_count = first_count;

    for month in months.iter().skip(1) {
        let data = &timeline[month];
        let curr_count = data["count"].as_i64().unwrap_or(0);
        let unique_tags = data["unique_tags"].as_i64().unwrap_or(0);
        if curr_count > peak_count {
            peak_month = month.clone();
            peak_count = curr_count;
        }
        if prev_count > 0 {
            let growth_rate = (curr_count - prev_count) as f64 / prev_count as f64;
            if growth_rate > 0.5 {
                events.push(json!({
                    "date": month,
                    "type": "productivity_up",
                    "icon": "\u{1f4c8}",
                    "title_key": "story.event.productivity_up.title",
                    "desc_key": "story.event.productivity_up.desc",
                    "params": {"percent": format!("{}", crate::num::sat_i64(growth_rate * 100.0))},
                }));
            } else if growth_rate < -0.3 {
                events.push(json!({
                    "date": month,
                    "type": "productivity_down",
                    "icon": "\u{1f4c9}",
                    "title_key": "story.event.productivity_down.title",
                    "desc_key": "story.event.productivity_down.desc",
                    "params": {"percent": format!("{}", crate::num::sat_i64(growth_rate.abs() * 100.0))},
                }));
            }
        }
        if let Some(sources) = data["sources"].as_object() {
            for src in sources.keys() {
                let lower = src.to_lowercase();
                let excluded = matches!(
                    lower.as_str(),
                    "rar_error" | "zip_error" | "unknown" | "not_modified" | "txt" | "webp_desc"
                ) || lower.ends_with("_error");
                if !seen_sources.contains(src) && !excluded && !src.is_empty() {
                    events.push(json!({
                        "date": month,
                        "type": "new_source",
                        "icon": "\u{1f527}",
                        "title_key": "story.event.new_source.title",
                        "desc_key": "story.event.new_source.desc",
                        "params": {"source": src},
                    }));
                }
            }
            seen_sources.extend(sources.keys().cloned());
        }
        if unique_tags > max_tags && unique_tags > 10 {
            events.push(json!({
                "date": month,
                "type": "tag_diversity",
                "icon": "\u{1f3a8}",
                "title_key": "story.event.tag_diversity.title",
                "desc_key": "story.event.tag_diversity.desc",
                "params": {"count": comma_count(unique_tags)},
            }));
            max_tags = unique_tags;
        }
        prev_count = curr_count;
    }
    if months.len() >= 3 && peak_month != *months.last().unwrap() {
        events.push(json!({
            "date": peak_month,
            "type": "peak_month",
            "icon": "\u{1f525}",
            "title_key": "story.event.peak_month.title",
            "desc_key": "story.event.peak_month.desc",
            "params": {"count": comma_count(peak_count)},
        }));
    }
    if months.len() >= 5 {
        let inner = &months[1..months.len() - 1];
        if let Some(quiet_month) = inner
            .iter()
            .min_by_key(|month| timeline[*month]["count"].as_i64().unwrap_or(0))
        {
            let quiet_count = timeline[quiet_month]["count"].as_i64().unwrap_or(0);
            let avg_count = months
                .iter()
                .map(|month| timeline[month]["count"].as_i64().unwrap_or(0))
                .sum::<i64>() as f64
                / months.len() as f64;
            if (quiet_count as f64) < avg_count * 0.3 {
                events.push(json!({
                    "date": quiet_month,
                    "type": "quiet_month",
                    "icon": "\u{1f319}",
                    "title_key": "story.event.quiet_month.title",
                    "desc_key": "story.event.quiet_month.desc",
                    "params": {"count": comma_count(quiet_count)},
                }));
            }
        }
    }

    let mut cumulative = 0;
    let mut achieved = std::collections::HashSet::new();
    for month in &months {
        cumulative += timeline[month]["count"].as_i64().unwrap_or(0);
        for (threshold, event_type, icon) in [
            (100, "milestone_100", "\u{1f389}"),
            (500, "milestone_500", "\u{1f389}"),
            (1000, "milestone_1k", "\u{1f38a}"),
            (2000, "milestone_2k", "\u{1f38a}"),
            (5000, "milestone_5k", "\u{1f48e}"),
            (10000, "milestone_10k", "\u{1f48e}"),
            (50000, "milestone_50k", "\u{1f451}"),
            (100000, "milestone_100k", "\u{1f451}"),
        ] {
            if cumulative >= threshold && achieved.insert(event_type) {
                events.push(json!({
                    "date": month,
                    "type": event_type,
                    "icon": icon,
                    "title_key": format!("story.event.{event_type}.title"),
                    "desc_key": format!("story.event.{event_type}.desc"),
                    "params": {"total": comma_count(cumulative)},
                }));
            }
        }
    }
    events.sort_by(|a, b| a["date"].as_str().cmp(&b["date"].as_str()));
    events
}

async fn streak_days(pool: &SqlitePool) -> Result<i64, sqlx::Error> {
    let rows = sqlx::query(&format!(
        "WITH RECURSIVE days(n, d) AS (
             SELECT 0, date('now', '{TZ_MODIFIER}')
             UNION ALL
             SELECT n + 1, date(d, '-1 day') FROM days WHERE n < 399
         ),
         image_days AS (
             SELECT DISTINCT date(f.mtime, 'unixepoch', '{TZ_MODIFIER}') as d
             FROM files f WHERE {AI_WHERE}
         )
         SELECT days.n, CASE WHEN image_days.d IS NULL THEN 0 ELSE 1 END as present
         FROM days
         LEFT JOIN image_days ON image_days.d = days.d
         ORDER BY days.n"
    ))
    .fetch_all(pool)
    .await?;
    let present: Vec<bool> = rows
        .into_iter()
        .map(|row| row.get::<i64, _>(1) != 0)
        .collect();
    let start = if present.first().copied().unwrap_or(false) {
        0
    } else {
        1
    };
    let mut streak = 0;
    for has_images in present.into_iter().skip(start) {
        if has_images {
            streak += 1;
        } else {
            break;
        }
    }
    Ok(streak)
}

async fn build_story_stats(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    if !table_exists(pool, "files").await? {
        return Ok(json!({"timeline": {}, "on_this_day": null, "streak_days": 0}));
    }
    let counts = monthly_file_counts(pool).await?;
    let tags = monthly_unique_tags(pool).await?;
    let sources = monthly_sources(pool).await?;
    let mut timeline = BTreeMap::new();
    for (month, count) in counts {
        timeline.insert(
            month.clone(),
            json!({
                "count": count,
                "unique_tags": tags.get(&month).copied().unwrap_or(0),
                "sources": sources.get(&month).cloned().unwrap_or_default(),
            }),
        );
    }
    let row = sqlx::query(
        "SELECT date('now', 'localtime', '-1 year') as d,
                (SELECT COUNT(*) FROM files f
                 WHERE f.is_deleted=0
                   AND f.meta_source IS NOT NULL
                   AND f.meta_source NOT IN ('', 'unknown', 'not_modified')
                   AND f.meta_source NOT LIKE 'media_%'
                   AND f.mtime >= unixepoch(date('now', 'localtime', '-1 year'))
                   AND f.mtime <= unixepoch(date('now', 'localtime', '-1 year', '+1 day')) - 1)",
    )
    .fetch_one(pool)
    .await?;

    Ok(json!({
        "timeline": timeline,
        "story": detect_story_events(&timeline),
        "on_this_day": {
            "date": row.get::<String, _>(0),
            "count": row.get::<i64, _>(1),
        },
        "streak_days": streak_days(pool).await?,
    }))
}

async fn build_stats_all(state: &SharedState) -> Result<Value, sqlx::Error> {
    let pool = &state.db_read;
    if !table_exists(pool, "files").await? {
        let empty_basic = json!({"file_count": 0, "total_files": 0, "excluded_files": 0, "tag_count": 0, "ai_count": 0, "ai_type_counts": {}, "meta_count": 0, "by_source": {}, "top_tags": []});
        let empty_periods = json!({"night": {"label_key": "stats.period.night", "count": 0, "percentage": 0.0}, "dawn": {"label_key": "stats.period.dawn", "count": 0, "percentage": 0.0}, "day": {"label_key": "stats.period.day", "count": 0, "percentage": 0.0}, "evening": {"label_key": "stats.period.evening", "count": 0, "percentage": 0.0}});
        let empty_hourly = json!({"periods": empty_periods, "heatmap": vec![0_i64; 24], "personality": {"type_key": "unknown"}});
        return Ok(
            json!({"_stale": false, "file_count_sig": 0, "max_mtime_sig": 0, "db_sig": {}, "cache_version": CACHE_VERSION, "basic": empty_basic, "hourly": empty_hourly, "timeline": [], "models": {"top_models": []}, "resolutions": {"top_resolutions": [], "turning_points": []}}),
        );
    }
    let db_sig = db_signature(pool).await?;
    let (basic, basic_stale) = build_basic_stats(pool, &state.stats_basic_cache).await?;
    let (timeline, timeline_stale) =
        build_timeline_stats(pool, "month", &state.stats_timeline_cache).await?;
    let (models, models_stale) = build_model_stats(pool, &state.stats_models_cache).await?;
    let (resolutions, resolutions_stale) =
        build_resolution_stats(pool, &state.stats_resolutions_cache).await?;
    // db_sig above is always computed fresh (see db_signature's doc comment),
    // so it is never itself the source of staleness -- only whether any of
    // the cached aggregate blocks below served a stale (up to TTL-old) value
    // decides whether this snapshot is internally consistent.
    let stale = basic_stale || timeline_stale || models_stale || resolutions_stale;
    Ok(json!({
        "_stale": stale,
        "file_count_sig": file_count_sig(&db_sig),
        "max_mtime_sig": max_mtime_sig(&db_sig),
        "db_sig": db_sig,
        "cache_version": CACHE_VERSION,
        "basic": basic,
        "hourly": build_hourly_stats(pool).await?,
        "timeline": timeline,
        "models": models,
        "resolutions": resolutions,
    }))
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

pub async fn stats_all(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_stats_all(&state).await {
        Ok(value) => api_result(value),
        Err(error) => api_error(error),
    }
}

pub async fn stats_basic(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_basic_stats(&state.db_read, &state.stats_basic_cache).await {
        Ok((mut basic, stale)) => {
            if stale {
                if let Value::Object(ref mut map) = basic {
                    map.insert("_stale".to_string(), Value::Bool(true));
                }
            }
            api_result(basic)
        }
        Err(error) => api_error(error),
    }
}

pub async fn stats_timeline(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let granularity = params
        .get("granularity")
        .or_else(|| params.get("g"))
        .or_else(|| params.get("interval"))
        .map(String::as_str)
        .unwrap_or("month");
    match build_timeline_stats(&state.db_read, granularity, &state.stats_timeline_cache).await {
        Ok((value, _stale)) => api_result(value),
        Err(error) => api_error(error),
    }
}

pub async fn stats_hourly(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_hourly_stats(&state.db_read).await {
        Ok(value) => api_result(value),
        Err(error) => api_error(error),
    }
}

pub async fn stats_models(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_model_stats(&state.db_read, &state.stats_models_cache).await {
        Ok((value, _stale)) => api_result(value),
        Err(error) => api_error(error),
    }
}

pub async fn stats_resolutions(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_resolution_stats(&state.db_read, &state.stats_resolutions_cache).await {
        Ok((value, _stale)) => api_result(value),
        Err(error) => api_error(error),
    }
}

pub async fn stats_story(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match async {
        let mut story = build_story_stats(&state.db_read).await?;
        let db_sig = db_signature(&state.db_read).await?;
        if let Value::Object(ref mut map) = story {
            map.insert("_stale".to_string(), Value::Bool(false));
            map.insert("file_count_sig".to_string(), json!(file_count_sig(&db_sig)));
            map.insert("max_mtime_sig".to_string(), json!(max_mtime_sig(&db_sig)));
            map.insert("db_sig".to_string(), db_sig);
            map.insert("cache_version".to_string(), json!(CACHE_VERSION));
        }
        Ok::<_, sqlx::Error>(story)
    }
    .await
    {
        Ok(value) => api_result(value),
        Err(error) => api_error(error),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{body::to_bytes, extract::State, http::StatusCode};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL UNIQUE,
               mtime INTEGER NOT NULL,
               is_deleted INTEGER NOT NULL DEFAULT 0,
               meta_source TEXT,
               width INTEGER NOT NULL DEFAULT 0,
               height INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE file_tags (file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL);
             CREATE TABLE tags (id INTEGER PRIMARY KEY, tag TEXT NOT NULL, namespace TEXT);
             CREATE TABLE templates (file_id INTEGER NOT NULL, model_name TEXT);
             CREATE TABLE monthly_stats_cache (month TEXT, stat_key TEXT, stat_value INTEGER, updated_at INTEGER);
             INSERT INTO files(id, path, mtime, is_deleted, meta_source, width, height) VALUES
               (1, '/a.png', 1704067200, 0, 'novelai_v4_png', 832, 1216),
               (2, '/b.png', 1704070800, 0, 'novelai_v4_png', 832, 1216),
               (3, '/ignored.png', 1704074400, 0, 'unknown', 512, 512),
               (4, '/deleted.png', 1704078000, 1, 'novelai_v4_png', 512, 512);
             INSERT INTO tags(id, tag, namespace) VALUES
               (10, '1girl', ''),
               (11, 'artist-name', 'artist'),
               (12, 'later-tie', '');
             INSERT INTO file_tags(file_id, tag_id) VALUES
               (1, 10), (2, 10), (1, 12), (2, 12), (2, 11);
             INSERT INTO templates(file_id, model_name) VALUES
               (1, 'Model A');",
        )
        .execute(&pool)
        .await
        .unwrap();

        Arc::new(
            AppState::new(
                Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("config.json"),
                    project_root: PathBuf::from("."),
                    app_config: serde_json::json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    #[tokio::test]
    async fn stats_all_includes_cache_metadata_and_basic_counts() {
        let response = stats_all(State(test_state().await), None).await;
        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();

        assert_eq!(value["ok"], true);
        assert_eq!(value["data"], serde_json::Value::Null);
        assert_eq!(value["_stale"], false);
        assert_eq!(value["cache_version"], 10);
        assert_eq!(value["file_count_sig"], 3);
        assert_eq!(value["max_mtime_sig"], 1704074400);
        assert_eq!(value["basic"]["file_count"], 2);
        assert_eq!(value["basic"]["total_files"], 3);
        assert_eq!(value["basic"]["excluded_files"], 1);
        assert_eq!(value["basic"]["tag_count"], 3);
        assert_eq!(value["basic"]["top_tags"][0]["tag"], "later-tie");
        assert_eq!(value["basic"]["top_tags"][1]["tag"], "1girl");
    }

    #[tokio::test]
    async fn stats_models_separates_template_and_novelai_fallback_models() {
        let state = test_state().await;
        sqlx::query(
            "INSERT INTO files(id, path, mtime, is_deleted, meta_source) VALUES
               (5, '/v4.gif', 1704078000, 0, 'novelai_v4'),
               (6, '/v3.png', 1704078000, 0, 'novelai_png')",
        )
        .execute(&state.db_read)
        .await
        .unwrap();

        let response = stats_models(State(state), None).await;
        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let value: serde_json::Value = serde_json::from_slice(&body).unwrap();

        assert_eq!(value["timeline"]["2024-01"]["Model A"], 1);
        assert_eq!(value["timeline"]["2024-01"]["Unknown"], 1);
        assert_eq!(value["timeline"]["2024-01"]["NovelAI Diffusion V4.5"], 2);
        assert_eq!(value["top_models"][0]["model"], "NovelAI Diffusion V4.5");
        assert_eq!(value["total_models"], 3);
    }
}
