use axum::{
    extract::{Extension, Query, State},
    response::{IntoResponse, Response},
    Json,
};
use chrono::{Datelike, Local, NaiveDate, TimeZone};
use serde::Deserialize;
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const AI_WHERE: &str = "(
        f.is_deleted=0
        AND f.meta_source IS NOT NULL
        AND f.meta_source NOT IN ('', 'unknown', 'not_modified')
        AND f.meta_source NOT LIKE 'media_%'
    )";
const TZ_MODIFIER: &str = "localtime";

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

/// Returns (mstart_unix, mend_unix) inclusive bounds for YYYY-MM in local timezone.
fn month_range_unix(year: i32, month: u32) -> (i64, i64) {
    let last_day = last_day_of_month(year, month);
    let start = Local
        .with_ymd_and_hms(year, month, 1, 0, 0, 0)
        .single()
        .map(|dt| dt.timestamp())
        .unwrap_or(0);
    let end = Local
        .with_ymd_and_hms(year, month, last_day, 23, 59, 59)
        .single()
        .map(|dt| dt.timestamp())
        .unwrap_or(0);
    (start, end)
}

fn last_day_of_month(year: i32, month: u32) -> u32 {
    if month == 12 {
        NaiveDate::from_ymd_opt(year + 1, 1, 1)
    } else {
        NaiveDate::from_ymd_opt(year, month + 1, 1)
    }
    .and_then(|d| d.pred_opt())
    .map(|d| d.day())
    .unwrap_or(30)
}

fn prev_month(year: i32, month: u32) -> (i32, u32) {
    if month == 1 {
        (year - 1, 12)
    } else {
        (year, month - 1)
    }
}

async fn build_monthly_report(pool: &SqlitePool, month_str: &str) -> Result<Value, sqlx::Error> {
    let parts: Vec<&str> = month_str.split('-').collect();
    if parts.len() != 2 {
        return Ok(json!({"error": "invalid month"}));
    }
    let year: i32 = parts[0].parse().unwrap_or(0);
    let month: u32 = parts[1].parse().unwrap_or(0);
    if year == 0 || month == 0 || month > 12 {
        return Ok(json!({"error": "invalid month"}));
    }

    let (mstart, mend) = month_range_unix(year, month);
    let (py, pm) = prev_month(year, month);
    let (pstart, pend) = month_range_unix(py, pm);

    // File count (current + prev)
    let count_row = sqlx::query(&format!(
        r#"SELECT
            SUM(CASE WHEN f.mtime >= ? AND f.mtime <= ? THEN 1 ELSE 0 END),
            SUM(CASE WHEN f.mtime >= ? AND f.mtime <= ? THEN 1 ELSE 0 END)
           FROM files f WHERE {AI_WHERE}"#
    ))
    .bind(mstart)
    .bind(mend)
    .bind(pstart)
    .bind(pend)
    .fetch_one(pool)
    .await?;
    let file_count: i64 = count_row.try_get::<Option<i64>, _>(0)?.unwrap_or(0);
    let prev_count: i64 = count_row.try_get::<Option<i64>, _>(1)?.unwrap_or(0);
    let mom_pct: Option<f64> = if prev_count > 0 {
        Some(((file_count - prev_count) as f64 / prev_count as f64 * 100.0 * 10.0).round() / 10.0)
    } else {
        None
    };

    // Unique tags
    let unique_tags: i64 = sqlx::query(&format!(
        r#"SELECT COUNT(DISTINCT ft.tag_id)
           FROM file_tags ft JOIN files f ON f.id = ft.file_id
           WHERE {AI_WHERE} AND f.mtime >= ? AND f.mtime <= ?"#
    ))
    .bind(mstart)
    .bind(mend)
    .fetch_one(pool)
    .await?
    .try_get(0)?;

    // Top tags (2-step: aggregate then resolve names)
    let top_agg_rows = sqlx::query(&format!(
        r#"SELECT ft.tag_id, COUNT(*) as cnt
           FROM file_tags ft JOIN files f ON f.id = ft.file_id
           WHERE {AI_WHERE} AND f.mtime >= ? AND f.mtime <= ?
           GROUP BY ft.tag_id ORDER BY cnt DESC LIMIT 20"#
    ))
    .bind(mstart)
    .bind(mend)
    .fetch_all(pool)
    .await?;

    // Same for prev month top tags (for rank comparison)
    let prev_agg_rows = sqlx::query(&format!(
        r#"SELECT ft.tag_id, COUNT(*) as cnt
           FROM file_tags ft JOIN files f ON f.id = ft.file_id
           WHERE {AI_WHERE} AND f.mtime >= ? AND f.mtime <= ?
           GROUP BY ft.tag_id ORDER BY cnt DESC LIMIT 20"#
    ))
    .bind(pstart)
    .bind(pend)
    .fetch_all(pool)
    .await?;

    // Collect all tag_ids to resolve
    let cur_ids: Vec<i64> = top_agg_rows.iter().map(|r| r.get::<i64, _>(0)).collect();
    let prev_rank_map: std::collections::HashMap<i64, usize> = prev_agg_rows
        .iter()
        .enumerate()
        .map(|(i, r)| (r.get::<i64, _>(0), i + 1))
        .collect();

    let top_tags = if cur_ids.is_empty() {
        vec![]
    } else {
        let placeholders = cur_ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
        let name_query = format!("SELECT id, tag FROM tags WHERE id IN ({placeholders})");
        let mut q = sqlx::query(&name_query);
        for id in &cur_ids {
            q = q.bind(id);
        }
        let name_rows = q.fetch_all(pool).await?;
        let name_map: std::collections::HashMap<i64, String> = name_rows
            .iter()
            .map(|r| (r.get::<i64, _>(0), r.get::<String, _>(1)))
            .collect();

        top_agg_rows
            .iter()
            .enumerate()
            .filter_map(|(i, r)| {
                let tid: i64 = r.get(0);
                let cnt: i64 = r.get(1);
                let tag = name_map.get(&tid)?.clone();
                let rank = i + 1;
                let prev_rank = prev_rank_map.get(&tid).copied();
                let rank_change = prev_rank.map(|p| p as i64 - rank as i64);
                Some(json!({
                    "tag": tag,
                    "count": cnt,
                    "rank": rank,
                    "prev_rank": prev_rank,
                    "rank_change": rank_change,
                }))
            })
            .collect::<Vec<_>>()
    };

    // New tags (first seen this month)
    let new_tag_candidates = sqlx::query(
        "SELECT id, tag FROM tags WHERE first_seen_mtime >= ? AND first_seen_mtime <= ?",
    )
    .bind(mstart)
    .bind(mend)
    .fetch_all(pool)
    .await?;

    let new_tags: Vec<String> = if new_tag_candidates.is_empty() {
        vec![]
    } else {
        let cand_ids: Vec<i64> = new_tag_candidates.iter().map(|r| r.get(0)).collect();
        let cand_map: std::collections::HashMap<i64, String> = new_tag_candidates
            .iter()
            .map(|r| (r.get::<i64, _>(0), r.get::<String, _>(1)))
            .collect();
        let placeholders = cand_ids.iter().map(|_| "?").collect::<Vec<_>>().join(",");
        let verify_query = format!(
            r#"SELECT ft.tag_id, COUNT(*) as cnt
               FROM file_tags ft JOIN files f ON f.id = ft.file_id
               WHERE ft.tag_id IN ({placeholders})
                 AND {AI_WHERE} AND f.mtime >= ? AND f.mtime <= ?
               GROUP BY ft.tag_id ORDER BY cnt DESC LIMIT 20"#
        );
        let mut q = sqlx::query(&verify_query);
        for id in &cand_ids {
            q = q.bind(id);
        }
        q = q.bind(mstart).bind(mend);
        q.fetch_all(pool)
            .await?
            .iter()
            .filter_map(|r| cand_map.get(&r.get::<i64, _>(0)).cloned())
            .collect()
    };

    // Source distribution
    let src_rows = sqlx::query(&format!(
        r#"SELECT COALESCE(f.meta_source, 'unknown') as src, COUNT(*) as cnt
           FROM files f WHERE {AI_WHERE} AND f.mtime >= ? AND f.mtime <= ?
           GROUP BY src ORDER BY cnt DESC"#
    ))
    .bind(mstart)
    .bind(mend)
    .fetch_all(pool)
    .await?;
    let sources: serde_json::Map<String, Value> = src_rows
        .iter()
        .map(|r| (r.get::<String, _>(0), json!(r.get::<i64, _>(1))))
        .collect();

    // Daily counts
    let daily_rows = sqlx::query(&format!(
        r#"SELECT date(f.mtime, 'unixepoch', '{TZ_MODIFIER}') as day, COUNT(*) as cnt
           FROM files f WHERE {AI_WHERE} AND f.mtime >= ? AND f.mtime <= ?
           GROUP BY day ORDER BY day"#
    ))
    .bind(mstart)
    .bind(mend)
    .fetch_all(pool)
    .await?;
    let daily_counts: Vec<Value> = daily_rows
        .iter()
        .map(|r| {
            json!({
                "date": r.get::<Option<String>, _>(0).unwrap_or_default(),
                "count": r.get::<i64, _>(1),
            })
        })
        .collect();
    let most_active_day = daily_counts
        .iter()
        .max_by_key(|d| d["count"].as_i64().unwrap_or(0))
        .map(|d| {
            json!({
                "date": d["date"],
                "count": d["count"],
            })
        });

    // Available months
    let month_rows = sqlx::query(&format!(
        r#"SELECT DISTINCT strftime('%Y-%m', datetime(f.mtime, 'unixepoch', '{TZ_MODIFIER}')) as month
           FROM files f WHERE {AI_WHERE} ORDER BY month DESC"#
    ))
    .fetch_all(pool)
    .await?;
    let available_months: Vec<String> = month_rows
        .iter()
        .filter_map(|r| r.try_get::<Option<String>, _>(0).ok().flatten())
        .collect();

    Ok(json!({
        "month": month_str,
        "file_count": file_count,
        "prev_month_count": prev_count,
        "mom_change_pct": mom_pct,
        "unique_tags": unique_tags,
        "new_tags": new_tags,
        "top_tags": top_tags,
        "sources": sources,
        "most_active_day": most_active_day,
        "daily_counts": daily_counts,
        "trophies": [],
        "available_months": available_months,
    }))
}

#[derive(Deserialize)]
pub struct MonthlyReportParams {
    month: Option<String>,
}

pub async fn monthly_report(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<MonthlyReportParams>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }

    let month = params.month.unwrap_or_else(|| {
        let now = Local::now();
        format!("{:04}-{:02}", now.year(), now.month())
    });

    // Validate YYYY-MM format
    let valid = month.len() == 7
        && month.chars().enumerate().all(|(i, c)| match i {
            0..=3 | 5..=6 => c.is_ascii_digit(),
            4 => c == '-',
            _ => false,
        });
    if !valid {
        return Json(json!({
            "ok": false,
            "error": "Invalid month format (expected YYYY-MM)",
            "data": null,
        }))
        .into_response();
    }

    match build_monthly_report(&state.db_read, &month).await {
        Ok(data) => Json(json!({"ok": true, "error": null, "data": data})).into_response(),
        Err(e) => {
            tracing::error!("monthly_report error: {e}");
            Json(json!({"ok": false, "error": "Database error", "data": null})).into_response()
        }
    }
}
