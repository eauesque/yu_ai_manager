//! Native GET /api/sweeps/history; Python source: routes/sweep_routes.py and routes/sweep_route_helpers.py.

use std::{
    collections::{BTreeMap, HashMap},
    time::{SystemTime, UNIX_EPOCH},
};

use axum::{
    extract::{Path as RoutePath, Query, State},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::state::SharedState;

#[derive(Default)]
struct SweepHistoryFilters {
    where_sql: Vec<String>,
    params: Vec<SqlParam>,
}

#[derive(Clone, Debug, PartialEq)]
enum SqlParam {
    I64(i64),
    F64(f64),
    String(String),
}

fn clamp_history_limit(limit: i64) -> i64 {
    limit.clamp(1, 500)
}

fn parse_history_limit(raw: Option<&String>) -> i64 {
    raw.and_then(|value| value.parse::<i64>().ok())
        .map(clamp_history_limit)
        .unwrap_or(50)
}

fn match_keys(raw: Option<&String>) -> Vec<String> {
    raw.map(|value| {
        value
            .split(',')
            .filter(|part| !part.trim().is_empty())
            .map(ToString::to_string)
            .collect()
    })
    .unwrap_or_default()
}

fn append_equal_filter(filters: &mut SweepHistoryFilters, column: &str, value: Option<Value>) {
    match value {
        Some(Value::String(value)) if !value.is_empty() => {
            filters.where_sql.push(format!("{column} = ?"));
            filters.params.push(SqlParam::String(value));
        }
        Some(Value::Number(value)) => {
            filters.where_sql.push(format!("{column} = ?"));
            if let Some(i) = value.as_i64() {
                filters.params.push(SqlParam::I64(i));
            } else if let Some(f) = value.as_f64() {
                filters.params.push(SqlParam::F64(f));
            }
        }
        _ => {}
    }
}

fn append_tolerant_filter(
    filters: &mut SweepHistoryFilters,
    column: &str,
    value: Option<f64>,
    tol: &str,
) {
    let Some(value) = value else {
        return;
    };
    let pct = if tol == "exact" {
        0.0
    } else {
        tol.parse::<f64>().unwrap_or(0.0)
    };
    if pct <= 0.0 {
        filters.where_sql.push(format!("{column} = ?"));
        filters.params.push(SqlParam::F64(value));
        return;
    }
    let eps = value.abs() * (pct / 100.0);
    filters.where_sql.push(format!("{column} BETWEEN ? AND ?"));
    filters.params.push(SqlParam::F64(value - eps));
    filters.params.push(SqlParam::F64(value + eps));
}

fn unix_now() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0)
}

#[derive(Default)]
struct SweepReference {
    bridge: Option<String>,
    checkpoint: Option<String>,
    vae: Option<String>,
    sampler: Option<String>,
    prompt_template: Option<String>,
    negative_template: Option<String>,
    width: Option<i64>,
    height: Option<i64>,
    base_seed: Option<i64>,
    steps: Option<i64>,
    cfg: Option<f64>,
}

fn append_reference_filters(
    filters: &mut SweepHistoryFilters,
    reference: &SweepReference,
    ref_axes: &[String],
    keys: &[String],
    tol_steps: &str,
    tol_cfg: &str,
) {
    for key in keys {
        match key.as_str() {
            "bridge" => append_equal_filter(
                filters,
                "s.bridge",
                reference.bridge.clone().map(Value::String),
            ),
            "checkpoint" => append_equal_filter(
                filters,
                "s.checkpoint",
                reference.checkpoint.clone().map(Value::String),
            ),
            "vae" => {
                append_equal_filter(filters, "s.vae", reference.vae.clone().map(Value::String))
            }
            "sampler" => append_equal_filter(
                filters,
                "s.sampler",
                reference.sampler.clone().map(Value::String),
            ),
            "positive" => append_equal_filter(
                filters,
                "s.prompt_template",
                reference.prompt_template.clone().map(Value::String),
            ),
            "negative" => append_equal_filter(
                filters,
                "s.negative_template",
                reference.negative_template.clone().map(Value::String),
            ),
            "resolution" => {
                if let (Some(width), Some(height)) = (reference.width, reference.height) {
                    if width != 0 && height != 0 {
                        filters
                            .where_sql
                            .push("s.width = ? AND s.height = ?".to_string());
                        filters.params.push(SqlParam::I64(width));
                        filters.params.push(SqlParam::I64(height));
                    }
                }
            }
            "baseSeed" => append_equal_filter(
                filters,
                "s.base_seed",
                reference.base_seed.map(|v| json!(v)),
            ),
            "steps" => append_tolerant_filter(
                filters,
                "s.steps",
                reference.steps.map(|v| v as f64),
                tol_steps,
            ),
            "cfg" => append_tolerant_filter(filters, "s.cfg", reference.cfg, tol_cfg),
            "axisX" | "axisY" | "axisZ" => {
                let pos = match key.as_str() {
                    "axisX" => 0,
                    "axisY" => 1,
                    _ => 2,
                };
                if let Some(param) = ref_axes.get(pos) {
                    filters.where_sql.push(
                        "EXISTS (SELECT 1 FROM sweep_axes a WHERE a.sweep_id = s.id AND a.axis_index = ? AND a.param = ?)".to_string(),
                    );
                    filters.params.push(SqlParam::I64(pos as i64));
                    filters.params.push(SqlParam::String(param.clone()));
                }
            }
            _ => {}
        }
    }
}

fn append_constraint_filters(
    filters: &mut SweepHistoryFilters,
    completed_only: bool,
    saved_only: bool,
    axis_count: &str,
    date_range: &str,
    now: i64,
) {
    if completed_only {
        filters.where_sql.push("s.status = 'completed'".to_string());
    }
    if saved_only {
        filters
            .where_sql
            .push("s.first_file_id IS NOT NULL".to_string());
    }
    if !axis_count.is_empty() && axis_count != "all" {
        if let Ok(value) = axis_count.parse::<i64>() {
            if (1..=3).contains(&value) {
                filters.where_sql.push("s.axis_count = ?".to_string());
                filters.params.push(SqlParam::I64(value));
            }
        }
    }
    if !date_range.is_empty() && date_range != "all" {
        let sec = match date_range {
            "today" => Some(86_400),
            "week" => Some(7 * 86_400),
            "month" => Some(30 * 86_400),
            _ => None,
        };
        if let Some(sec) = sec {
            filters.where_sql.push("s.created_at >= ?".to_string());
            filters.params.push(SqlParam::I64(now - sec));
        }
    }
}

async fn load_reference(
    pool: &SqlitePool,
    ref_id: Option<&str>,
    keys: &[String],
) -> Result<Option<(SweepReference, Vec<String>)>, sqlx::Error> {
    if ref_id.is_none() || keys.is_empty() {
        return Ok(None);
    }
    let ref_id = ref_id.unwrap_or_default();
    let Some(row) = sqlx::query("SELECT * FROM sweeps WHERE id = ?")
        .bind(ref_id)
        .fetch_optional(pool)
        .await?
    else {
        return Ok(None);
    };
    let axes = sqlx::query(
        "SELECT axis_index, param FROM sweep_axes WHERE sweep_id = ? ORDER BY axis_index",
    )
    .bind(ref_id)
    .fetch_all(pool)
    .await?
    .into_iter()
    .map(|row| row.get::<String, _>("param"))
    .collect::<Vec<_>>();
    Ok(Some((
        SweepReference {
            bridge: row.try_get::<Option<String>, _>("bridge").ok().flatten(),
            checkpoint: row
                .try_get::<Option<String>, _>("checkpoint")
                .ok()
                .flatten(),
            vae: row.try_get::<Option<String>, _>("vae").ok().flatten(),
            sampler: row.try_get::<Option<String>, _>("sampler").ok().flatten(),
            prompt_template: row
                .try_get::<Option<String>, _>("prompt_template")
                .ok()
                .flatten(),
            negative_template: row
                .try_get::<Option<String>, _>("negative_template")
                .ok()
                .flatten(),
            width: row.try_get::<Option<i64>, _>("width").ok().flatten(),
            height: row.try_get::<Option<i64>, _>("height").ok().flatten(),
            base_seed: row.try_get::<Option<i64>, _>("base_seed").ok().flatten(),
            steps: row.try_get::<Option<i64>, _>("steps").ok().flatten(),
            cfg: row.try_get::<Option<f64>, _>("cfg").ok().flatten(),
        },
        axes,
    )))
}

fn bind_params<'q>(
    mut query: sqlx::query::Query<'q, sqlx::Sqlite, sqlx::sqlite::SqliteArguments<'q>>,
    params: &'q [SqlParam],
) -> sqlx::query::Query<'q, sqlx::Sqlite, sqlx::sqlite::SqliteArguments<'q>> {
    for param in params {
        query = match param {
            SqlParam::I64(value) => query.bind(*value),
            SqlParam::F64(value) => query.bind(*value),
            SqlParam::String(value) => query.bind(value),
        };
    }
    query
}

async fn query_history(
    pool: &SqlitePool,
    params: &HashMap<String, String>,
) -> Result<(Vec<Value>, i64), sqlx::Error> {
    let limit = parse_history_limit(params.get("limit"));
    let keys = match_keys(params.get("match"));
    let mut filters = SweepHistoryFilters {
        where_sql: vec!["1=1".to_string()],
        params: Vec::new(),
    };
    if let Some((reference, axes)) =
        load_reference(pool, params.get("ref").map(String::as_str), &keys).await?
    {
        append_reference_filters(
            &mut filters,
            &reference,
            &axes,
            &keys,
            params
                .get("tol_steps")
                .map(String::as_str)
                .unwrap_or("exact"),
            params.get("tol_cfg").map(String::as_str).unwrap_or("exact"),
        );
    }
    append_constraint_filters(
        &mut filters,
        params.get("completed_only").is_some_and(|v| v == "1"),
        params.get("saved_only").is_some_and(|v| v == "1"),
        params
            .get("axis_count")
            .map(String::as_str)
            .unwrap_or("all"),
        params
            .get("date_range")
            .map(String::as_str)
            .unwrap_or("all"),
        unix_now(),
    );
    let sql = format!(
        "SELECT s.*, (SELECT GROUP_CONCAT(a.param, ',') FROM sweep_axes a
         WHERE a.sweep_id = s.id ORDER BY a.axis_index) AS axes_params_csv
         FROM sweeps s WHERE {} ORDER BY s.created_at DESC, s.id LIMIT ?",
        filters.where_sql.join(" AND ")
    );
    let mut query = bind_params(sqlx::query(&sql), &filters.params);
    query = query.bind(limit);
    let rows = query.fetch_all(pool).await?;
    let entries = rows
        .into_iter()
        .map(|row| {
            let csv = row
                .try_get::<Option<String>, _>("axes_params_csv")
                .ok()
                .flatten();
            json!({
                "id": row.get::<String, _>("id"),
                "bridge": row.try_get::<Option<String>, _>("bridge").ok().flatten(),
                "base_seed": row.try_get::<Option<i64>, _>("base_seed").ok().flatten(),
                "created_at": row.try_get::<Option<i64>, _>("created_at").ok().flatten(),
                "prompt_template": row.try_get::<Option<String>, _>("prompt_template").ok().flatten(),
                "negative_template": row.try_get::<Option<String>, _>("negative_template").ok().flatten(),
                "checkpoint": row.try_get::<Option<String>, _>("checkpoint").ok().flatten(),
                "vae": row.try_get::<Option<String>, _>("vae").ok().flatten(),
                "sampler": row.try_get::<Option<String>, _>("sampler").ok().flatten(),
                "width": row.try_get::<Option<i64>, _>("width").ok().flatten(),
                "height": row.try_get::<Option<i64>, _>("height").ok().flatten(),
                "steps": row.try_get::<Option<i64>, _>("steps").ok().flatten(),
                "cfg": row.try_get::<Option<f64>, _>("cfg").ok().flatten(),
                "axis_count": row.try_get::<Option<i64>, _>("axis_count").ok().flatten(),
                "first_file_id": row.try_get::<Option<i64>, _>("first_file_id").ok().flatten(),
                "last_file_id": row.try_get::<Option<i64>, _>("last_file_id").ok().flatten(),
                "file_count": row.try_get::<Option<i64>, _>("file_count").ok().flatten(),
                "status": row.try_get::<Option<String>, _>("status").ok().flatten(),
                "updated_at": row.try_get::<Option<i64>, _>("updated_at").ok().flatten(),
                "axes_params": csv.map(|s| s.split(',').map(ToString::to_string).collect::<Vec<_>>()).unwrap_or_default(),
            })
        })
        .collect::<Vec<_>>();
    let total = sqlx::query_scalar("SELECT COUNT(*) AS n FROM sweeps")
        .fetch_one(pool)
        .await?;
    Ok((entries, total))
}

fn api_success_data(data: Value) -> Response {
    Json(json!({"ok": true, "error": null, "data": data})).into_response()
}

fn api_error(message: &str) -> Response {
    (
        axum::http::StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": message})),
    )
        .into_response()
}

/// Python `api_success(payload)` merges `payload` at the TOP level and leaves
/// `data` null — it is not the same shape as `api_success(data=...)`, which
/// `api_success_data` above covers. The sweep view reads `d.meta` / `d.matches`
/// directly off the root, so the distinction is load-bearing.
fn api_success_payload(payload: Value) -> Response {
    let mut body = json!({"ok": true, "error": null, "data": null});
    if let (Some(target), Some(extra)) = (body.as_object_mut(), payload.as_object()) {
        for (k, v) in extra {
            target.insert(k.clone(), v.clone());
        }
    }
    Json(body).into_response()
}

fn api_error_status(message: &str, status: axum::http::StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn api_error_coded(message: &str, status: axum::http::StatusCode, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}

const IMAGE_SUFFIXES: [&str; 4] = ["png", "jpg", "jpeg", "webp"];
/// Python `SWEEP_FOLDER_SCAN_IMAGE_LIMIT`. Counts image *candidates*, so a
/// folder holding non-images does not eat into the budget.
const SWEEP_FOLDER_SCAN_IMAGE_LIMIT: usize = 1000;
const FILE_ID_CHUNK_SIZE: usize = 500;

fn lowercase_extension(path: &std::path::Path) -> String {
    path.extension()
        .and_then(|e| e.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase()
}

fn is_sweep_image(path: &std::path::Path) -> bool {
    IMAGE_SUFFIXES.contains(&lowercase_extension(path).as_str())
}

/// Mirrors Python `read_sweep_attrs`: read the file's XMP packet and take the
/// `sweep` namespace. Any failure yields an empty map — a file without XMP is
/// an ordinary outcome here, not an error.
fn read_sweep_attrs(path: &std::path::Path) -> BTreeMap<String, String> {
    let raw = match lowercase_extension(path).as_str() {
        "png" => xmp_core::io::png::read_xmp(path),
        "jpg" | "jpeg" => xmp_core::io::jpeg::read_xmp(path),
        "webp" => xmp_core::io::webp::read_xmp(path),
        _ => None,
    };
    raw.map(|xml| xmp_core::parse(&xml).get_attrs("sweep"))
        .unwrap_or_default()
}

fn int_attr(attrs: &BTreeMap<String, String>, key: &str, default: i64) -> i64 {
    attrs
        .get(key)
        .and_then(|v| v.trim().parse::<i64>().ok())
        .unwrap_or(default)
}

/// Python `_json_value`: parse as JSON, and on failure return the raw string.
fn json_value_str(raw: &str) -> Value {
    serde_json::from_str(raw).unwrap_or_else(|_| Value::String(raw.to_string()))
}

/// Python `_json_list`: JSON-parse, keep it only if it really is a list.
fn json_list(raw: &str) -> Value {
    if raw.is_empty() {
        return Value::Array(Vec::new());
    }
    match json_value_str(raw) {
        Value::Array(items) => Value::Array(items),
        _ => Value::Array(Vec::new()),
    }
}

/// Python `_float_or_str`. Non-finite floats stay strings: Python's `float()`
/// accepts "inf"/"nan" but the resulting JSON is not valid JSON, so emitting
/// the raw string is the only faithful-and-valid option.
fn float_or_str(raw: &str) -> Value {
    match raw.parse::<f64>() {
        Ok(parsed) if parsed.is_finite() => json!(parsed),
        _ => Value::String(raw.to_string()),
    }
}

fn optional_string(raw: Option<&String>) -> Value {
    raw.map(|s| Value::String(s.clone())).unwrap_or(Value::Null)
}

fn axis_attrs_to_meta(attrs: &BTreeMap<String, String>, axis: usize) -> Option<Value> {
    let prefix = format!("axis_{axis}_");
    let param = attrs
        .get(&format!("{prefix}param"))
        .filter(|value| !value.is_empty())?;
    let series_raw = attrs
        .get(&format!("{prefix}series"))
        .cloned()
        .unwrap_or_default();
    let value_raw = attrs.get(&format!("{prefix}value"));
    let (series, value) = if param == "_macros" {
        // Python: `_json_value(value_raw) if value_raw else value_raw` — an
        // empty string is falsy there, so it survives as "" rather than null.
        let value = match value_raw {
            Some(raw) if !raw.is_empty() => json_value_str(raw),
            other => optional_string(other),
        };
        (json_list(&series_raw), value)
    } else {
        let series: Vec<Value> = series_raw
            .split(',')
            .filter(|part| !part.is_empty())
            .map(float_or_str)
            .collect();
        (Value::Array(series), optional_string(value_raw))
    };
    Some(json!({
        "param": param,
        "index": int_attr(attrs, &format!("{prefix}index"), 0),
        "total": int_attr(attrs, &format!("{prefix}total"), 0),
        "value": value,
        "series": series,
    }))
}

/// Mirrors Python `attrs_to_meta`. `None` means "this file carries no sweep",
/// which the route turns into a 404 with code `no_sweep_xmp`.
fn attrs_to_meta(attrs: &BTreeMap<String, String>) -> Option<Value> {
    let id = attrs.get("id").filter(|value| !value.is_empty())?;
    let axis_count = usize::try_from(int_attr(attrs, "axis_count", 1).max(0)).unwrap_or(1);
    let axes: Vec<Value> = (0..axis_count)
        .filter_map(|axis| axis_attrs_to_meta(attrs, axis))
        .collect();
    let mut out = json!({
        "id": id,
        "bridge": attrs.get("bridge").cloned().unwrap_or_default(),
        "axes": axes,
        "base_seed": int_attr(attrs, "base_seed", -1),
        "created_at": int_attr(attrs, "created_at", 0),
    });
    if let Some(template) = attrs.get("prompt_template") {
        out["prompt_template"] = json!(template);
    }
    if let Some(template) = attrs.get("negative_template") {
        out["negative_template"] = json!(template);
    }
    Some(out)
}

fn sweep_record(path: &str, attrs: &BTreeMap<String, String>) -> Value {
    let mut record = json!({ "path": path });
    for axis in 0..3 {
        let index_key = format!("axis_{axis}_index");
        if !attrs.contains_key(&index_key) {
            continue;
        }
        let value_key = format!("axis_{axis}_value");
        let raw_value = attrs.get(&value_key);
        let is_macros = attrs
            .get(&format!("axis_{axis}_param"))
            .is_some_and(|param| param == "_macros");
        let value = match raw_value {
            Some(raw) if is_macros && !raw.is_empty() => json_value_str(raw),
            other => optional_string(other),
        };
        if let Some(object) = record.as_object_mut() {
            object.insert(index_key.clone(), json!(int_attr(attrs, &index_key, -1)));
            object.insert(value_key, value);
        }
    }
    record
}

fn record_axis_index(record: &Value, axis: usize) -> i64 {
    record
        .get(format!("axis_{axis}_index"))
        .and_then(Value::as_i64)
        .unwrap_or(-1)
}

/// Blocking: reads XMP from up to `SWEEP_FOLDER_SCAN_IMAGE_LIMIT` files.
/// Callers must put this on a blocking thread.
fn scan_folder_for_sweep(folder: &std::path::Path, sweep_id: &str) -> Vec<Value> {
    scan_folder_for_sweep_limited(folder, sweep_id, SWEEP_FOLDER_SCAN_IMAGE_LIMIT)
}

/// The limit is a parameter so a test can reach it without staging a thousand
/// files. Production always passes `SWEEP_FOLDER_SCAN_IMAGE_LIMIT`.
fn scan_folder_for_sweep_limited(
    folder: &std::path::Path,
    sweep_id: &str,
    limit: usize,
) -> Vec<Value> {
    let mut matches: Vec<Value> = Vec::new();
    let entries = match std::fs::read_dir(folder) {
        Ok(entries) => entries,
        Err(error) => {
            tracing::warn!(?error, ?folder, "sweep folder scan: read_dir failed");
            return matches;
        }
    };
    let mut image_candidates = 0usize;
    for entry in entries.flatten() {
        let path = entry.path();
        if !entry.file_type().map(|t| t.is_file()).unwrap_or(false) || !is_sweep_image(&path) {
            continue;
        }
        if image_candidates >= limit {
            tracing::warn!(limit, ?folder, "sweep folder scan reached image limit");
            break;
        }
        image_candidates += 1;
        let attrs = read_sweep_attrs(&path);
        if attrs.get("id").map(String::as_str) != Some(sweep_id) {
            continue;
        }
        matches.push(sweep_record(&path.to_string_lossy(), &attrs));
    }
    matches.sort_by(|a, b| {
        (
            record_axis_index(a, 0),
            record_axis_index(a, 1),
            record_axis_index(a, 2),
            a.get("path").and_then(Value::as_str).unwrap_or(""),
        )
            .cmp(&(
                record_axis_index(b, 0),
                record_axis_index(b, 1),
                record_axis_index(b, 2),
                b.get("path").and_then(Value::as_str).unwrap_or(""),
            ))
    });
    matches
}

/// Python `resolve_path`: a path containing `!` denotes a file inside an
/// archive, which has no on-disk XMP to read, so it is treated as absent.
async fn resolve_path(pool: &SqlitePool, file_id: i64) -> Result<Option<String>, sqlx::Error> {
    let row = sqlx::query("SELECT path FROM files WHERE id=?")
        .bind(file_id)
        .fetch_optional(pool)
        .await?;
    let Some(row) = row else {
        return Ok(None);
    };
    let path: String = row.try_get("path")?;
    Ok(if path.contains('!') { None } else { Some(path) })
}

async fn attach_file_ids(pool: &SqlitePool, matches: &mut [Value]) -> Result<(), sqlx::Error> {
    if matches.is_empty() {
        return Ok(());
    }
    let mut unique: Vec<String> = Vec::new();
    for record in matches.iter() {
        if let Some(path) = record.get("path").and_then(Value::as_str) {
            if !unique.iter().any(|seen| seen == path) {
                unique.push(path.to_string());
            }
        }
    }
    let mut by_path: HashMap<String, i64> = HashMap::new();
    for chunk in unique.chunks(FILE_ID_CHUNK_SIZE) {
        let placeholders = vec!["?"; chunk.len()].join(",");
        let sql = format!("SELECT id, path FROM files WHERE path IN ({placeholders})");
        let mut query = sqlx::query(&sql);
        for path in chunk {
            query = query.bind(path);
        }
        for row in query.fetch_all(pool).await? {
            by_path.insert(row.try_get("path")?, row.try_get("id")?);
        }
    }
    for record in matches.iter_mut() {
        let file_id = record
            .get("path")
            .and_then(Value::as_str)
            .and_then(|path| by_path.get(path))
            .copied();
        if let Some(object) = record.as_object_mut() {
            object.insert(
                "file_id".to_string(),
                file_id.map(|id| json!(id)).unwrap_or(Value::Null),
            );
        }
    }
    Ok(())
}

/// GET /api/sweep/info/{file_id} — Python `routes/sweep_routes.py::api_sweep_info`.
pub async fn info(
    State(state): State<SharedState>,
    RoutePath(file_id): RoutePath<i64>,
) -> Response {
    let path = match resolve_path(&state.db_read, file_id).await {
        Ok(Some(path)) => path,
        Ok(None) => {
            return api_error_status(
                "file not found or not on disk",
                axum::http::StatusCode::NOT_FOUND,
            )
        }
        Err(error) => {
            tracing::error!(?error, "sweep info: resolve_path failed");
            return api_error("Failed to resolve file path");
        }
    };
    if !is_sweep_image(std::path::Path::new(&path)) {
        return api_error_status(
            "unsupported file type for XMP",
            axum::http::StatusCode::BAD_REQUEST,
        );
    }
    let read_path = path.clone();
    let attrs = match tokio::task::spawn_blocking(move || {
        read_sweep_attrs(std::path::Path::new(&read_path))
    })
    .await
    {
        Ok(attrs) => attrs,
        Err(error) => {
            tracing::error!(?error, "sweep info: XMP read task failed");
            return api_error("Failed to read sweep metadata");
        }
    };
    match attrs_to_meta(&attrs) {
        Some(meta) => api_success_payload(json!({"meta": meta, "path": path})),
        None => api_error_coded(
            "no sweep metadata in this file",
            axum::http::StatusCode::NOT_FOUND,
            "no_sweep_xmp",
        ),
    }
}

/// GET /api/sweep/files/{sweep_id} — Python `api_sweep_files`. The `file_id`
/// query parameter is a folder hint, not the subject of the lookup.
pub async fn files(
    State(state): State<SharedState>,
    RoutePath(sweep_id): RoutePath<String>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if sweep_id.is_empty() {
        return api_error_status("sweep_id is required", axum::http::StatusCode::BAD_REQUEST);
    }
    let Some(hint_raw) = params.get("file_id").filter(|value| !value.is_empty()) else {
        return api_error_status(
            "file_id query parameter is required as folder hint",
            axum::http::StatusCode::BAD_REQUEST,
        );
    };
    let Ok(hint_id) = hint_raw.trim().parse::<i64>() else {
        return api_error_status(
            "file_id must be an integer",
            axum::http::StatusCode::BAD_REQUEST,
        );
    };
    let hint_path = match resolve_path(&state.db_read, hint_id).await {
        Ok(Some(path)) => path,
        Ok(None) => {
            return api_error_status("hint file not found", axum::http::StatusCode::NOT_FOUND)
        }
        Err(error) => {
            tracing::error!(?error, "sweep files: resolve_path failed");
            return api_error("Failed to resolve hint file path");
        }
    };
    let folder = std::path::Path::new(&hint_path)
        .parent()
        .map(|parent| parent.to_path_buf())
        .unwrap_or_default();
    let scan_folder = folder.clone();
    let scan_id = sweep_id.clone();
    let mut matches =
        match tokio::task::spawn_blocking(move || scan_folder_for_sweep(&scan_folder, &scan_id))
            .await
        {
            Ok(matches) => matches,
            Err(error) => {
                tracing::error!(?error, "sweep files: folder scan task failed");
                return api_error("Failed to scan sweep folder");
            }
        };
    if let Err(error) = attach_file_ids(&state.db_read, &mut matches).await {
        tracing::error!(?error, "sweep files: attach_file_ids failed");
        return api_error("Failed to resolve sweep file ids");
    }
    api_success_payload(json!({
        "sweep_id": sweep_id,
        "folder": folder.to_string_lossy(),
        "matches": matches,
    }))
}

pub async fn history(
    State(state): State<SharedState>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    match query_history(&state.db_read, &params).await {
        Ok((entries, total)) => api_success_data(json!({"entries": entries, "total": total})),
        Err(error) => {
            tracing::error!(?error, "sweeps history failed");
            api_error("Failed to load sweep history")
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clamps_history_limit_to_python_range() {
        assert_eq!(clamp_history_limit(-5), 1);
        assert_eq!(clamp_history_limit(0), 1);
        assert_eq!(clamp_history_limit(501), 500);
        assert_eq!(clamp_history_limit(50), 50);
    }

    #[test]
    fn tolerant_filter_uses_percent_epsilon() {
        let mut filters = SweepHistoryFilters::default();
        append_tolerant_filter(&mut filters, "s.cfg", Some(7.0), "10");
        assert_eq!(filters.where_sql, vec!["s.cfg BETWEEN ? AND ?"]);
        assert_eq!(filters.params, vec![SqlParam::F64(6.3), SqlParam::F64(7.7)]);
    }

    #[test]
    fn reference_and_constraint_filters_match_python_keys() {
        let reference = SweepReference {
            bridge: Some("bridge".to_string()),
            checkpoint: Some("ckpt".to_string()),
            vae: Some("vae".to_string()),
            sampler: Some("sampler".to_string()),
            prompt_template: Some("pos".to_string()),
            negative_template: Some("neg".to_string()),
            width: Some(512),
            height: Some(768),
            base_seed: Some(42),
            steps: Some(20),
            cfg: Some(7.0),
        };
        let keys = [
            "bridge",
            "checkpoint",
            "vae",
            "sampler",
            "positive",
            "negative",
            "resolution",
            "baseSeed",
            "steps",
            "cfg",
            "axisX",
            "axisY",
            "axisZ",
        ]
        .into_iter()
        .map(ToString::to_string)
        .collect::<Vec<_>>();
        let axes = vec!["x".to_string(), "y".to_string(), "z".to_string()];
        let mut filters = SweepHistoryFilters::default();
        append_reference_filters(&mut filters, &reference, &axes, &keys, "exact", "10");
        append_constraint_filters(&mut filters, true, true, "2", "week", 1_000_000);

        assert!(filters.where_sql.contains(&"s.bridge = ?".to_string()));
        assert!(filters
            .where_sql
            .contains(&"s.prompt_template = ?".to_string()));
        assert!(filters
            .where_sql
            .contains(&"s.width = ? AND s.height = ?".to_string()));
        assert!(filters.where_sql.contains(&"s.steps = ?".to_string()));
        assert!(filters
            .where_sql
            .contains(&"s.cfg BETWEEN ? AND ?".to_string()));
        assert_eq!(
            filters
                .where_sql
                .iter()
                .filter(|part| part.starts_with("EXISTS (SELECT 1 FROM sweep_axes"))
                .count(),
            3
        );
        assert!(filters
            .where_sql
            .contains(&"s.status = 'completed'".to_string()));
        assert!(filters
            .where_sql
            .contains(&"s.first_file_id IS NOT NULL".to_string()));
        assert!(filters.where_sql.contains(&"s.axis_count = ?".to_string()));
        assert!(filters.where_sql.contains(&"s.created_at >= ?".to_string()));
    }

    // --- /api/sweep/info and /api/sweep/files (ported from Python) ---

    fn attrs(pairs: &[(&str, &str)]) -> BTreeMap<String, String> {
        pairs
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_string()))
            .collect()
    }

    #[test]
    fn meta_requires_a_non_empty_id() {
        assert!(attrs_to_meta(&attrs(&[])).is_none());
        assert!(attrs_to_meta(&attrs(&[("id", "")])).is_none());
        assert!(attrs_to_meta(&attrs(&[("id", "s1")])).is_some());
    }

    #[test]
    fn meta_defaults_match_python() {
        let meta = attrs_to_meta(&attrs(&[("id", "s1")])).unwrap();
        assert_eq!(meta["base_seed"], -1);
        assert_eq!(meta["created_at"], 0);
        assert_eq!(meta["bridge"], "");
        // axis_count defaults to 1, but with no axis_0_param the axis drops out.
        assert_eq!(meta["axes"].as_array().unwrap().len(), 0);
        // Optional templates stay absent rather than becoming null.
        assert!(meta.get("prompt_template").is_none());
    }

    #[test]
    fn unparsable_ints_fall_back_to_the_default() {
        // Python's int("3.5") raises, so the default wins. A silent 3 here
        // would be a divergence.
        let meta = attrs_to_meta(&attrs(&[("id", "s1"), ("base_seed", "3.5")])).unwrap();
        assert_eq!(meta["base_seed"], -1);
    }

    #[test]
    fn negative_axis_count_yields_no_axes() {
        // Python range(-2) is empty; a naive `as usize` cast would wrap and
        // try to build billions of axes.
        let meta = attrs_to_meta(&attrs(&[
            ("id", "s1"),
            ("axis_count", "-2"),
            ("axis_0_param", "cfg"),
        ]))
        .unwrap();
        assert_eq!(meta["axes"].as_array().unwrap().len(), 0);
    }

    #[test]
    fn plain_axis_series_splits_on_comma_and_parses_numbers() {
        let meta = attrs_to_meta(&attrs(&[
            ("id", "s1"),
            ("axis_0_param", "cfg"),
            ("axis_0_series", "1,2.5,,abc"),
            ("axis_0_value", "2.5"),
            ("axis_0_index", "1"),
            ("axis_0_total", "3"),
        ]))
        .unwrap();
        let axis = &meta["axes"][0];
        assert_eq!(axis["param"], "cfg");
        assert_eq!(axis["index"], 1);
        assert_eq!(axis["total"], 3);
        // Empty segments are dropped; non-numeric parts stay strings.
        assert_eq!(axis["series"], json!([1.0, 2.5, "abc"]));
        // A plain axis keeps `value` as the raw string, never a number.
        assert_eq!(axis["value"], "2.5");
    }

    #[test]
    fn macros_axis_decodes_json_but_keeps_empty_string() {
        let decoded = attrs_to_meta(&attrs(&[
            ("id", "s1"),
            ("axis_0_param", "_macros"),
            ("axis_0_series", r#"[{"a":1}]"#),
            ("axis_0_value", r#"{"a":1}"#),
        ]))
        .unwrap();
        assert_eq!(decoded["axes"][0]["series"], json!([{"a": 1}]));
        assert_eq!(decoded["axes"][0]["value"], json!({"a": 1}));

        // Python's `if value_raw` is false for "", so it survives as "".
        let empty = attrs_to_meta(&attrs(&[
            ("id", "s1"),
            ("axis_0_param", "_macros"),
            ("axis_0_value", ""),
        ]))
        .unwrap();
        assert_eq!(empty["axes"][0]["value"], "");
    }

    #[test]
    fn malformed_macros_json_falls_back_to_the_raw_string() {
        let meta = attrs_to_meta(&attrs(&[
            ("id", "s1"),
            ("axis_0_param", "_macros"),
            ("axis_0_series", "not json"),
            ("axis_0_value", "not json"),
        ]))
        .unwrap();
        // A non-list parse result becomes [], not the raw string.
        assert_eq!(meta["axes"][0]["series"], json!([]));
        assert_eq!(meta["axes"][0]["value"], "not json");
    }

    #[test]
    fn sweep_record_only_emits_axes_that_are_present() {
        let record = sweep_record(
            "/img/a.png",
            &attrs(&[("axis_0_index", "2"), ("axis_0_value", "7")]),
        );
        assert_eq!(record["path"], "/img/a.png");
        assert_eq!(record["axis_0_index"], 2);
        assert_eq!(record["axis_0_value"], "7");
        assert!(record.get("axis_1_index").is_none());
    }

    #[test]
    fn sweep_record_index_defaults_to_minus_one() {
        let record = sweep_record("/img/a.png", &attrs(&[("axis_0_index", "oops")]));
        assert_eq!(record["axis_0_index"], -1);
        assert_eq!(record["axis_0_value"], Value::Null);
    }

    #[test]
    fn image_suffix_check_is_case_insensitive_and_rejects_others() {
        assert!(is_sweep_image(std::path::Path::new("/a/b.PNG")));
        assert!(is_sweep_image(std::path::Path::new("/a/b.jpeg")));
        assert!(!is_sweep_image(std::path::Path::new("/a/b.gif")));
        assert!(!is_sweep_image(std::path::Path::new("/a/b")));
    }

    #[tokio::test]
    async fn success_payload_merges_at_the_top_level_and_leaves_data_null() {
        // The sweep view reads `d.meta` off the root. Nesting it under `data`
        // would return HTTP 200 and still break the page, so assert the body,
        // not the status — the status alone cannot fail here.
        let response = api_success_payload(json!({"meta": {"id": "s1"}, "path": "/x.png"}));
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let bytes = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let body: Value = serde_json::from_slice(&bytes).unwrap();
        assert_eq!(body["ok"], true);
        assert_eq!(body["error"], Value::Null);
        assert_eq!(body["data"], Value::Null, "payload must not land in `data`");
        assert_eq!(body["meta"]["id"], "s1");
        assert_eq!(body["path"], "/x.png");
    }

    #[tokio::test]
    async fn folder_scan_matches_only_the_requested_sweep_and_sorts_by_axis() {
        let dir = tempfile::tempdir().unwrap();
        let write = |name: &str, sweep: &str, index: &str| {
            let path = dir.path().join(name);
            std::fs::write(&path, minimal_png()).unwrap();
            xmp_core::io::png::write_xmp(&path, &sweep_xmp(sweep, index)).unwrap();
            path
        };
        write("b.png", "target", "2");
        write("a.png", "target", "1");
        write("c.png", "other", "0");
        std::fs::write(dir.path().join("note.txt"), b"not an image").unwrap();

        let matches = scan_folder_for_sweep(dir.path(), "target");
        assert_eq!(matches.len(), 2, "only the target sweep's images match");
        // Sorted by axis_0_index, so a.png (1) precedes b.png (2).
        assert_eq!(matches[0]["axis_0_index"], 1);
        assert_eq!(matches[1]["axis_0_index"], 2);
    }

    #[test]
    fn folder_scan_on_a_missing_directory_returns_empty_not_an_error() {
        let matches = scan_folder_for_sweep(
            std::path::Path::new("/nonexistent-sweep-folder-xyz"),
            "target",
        );
        assert!(matches.is_empty());
    }

    #[tokio::test]
    async fn folder_scan_budget_counts_images_only_and_stops_there() {
        // Two claims from the comment on the constant, both measured here:
        // (1) non-images do not consume the budget, (2) the scan really stops.
        let dir = tempfile::tempdir().unwrap();
        for i in 0..4 {
            let path = dir.path().join(format!("{i}.png"));
            let xmp = sweep_xmp("target", &i.to_string());
            std::fs::write(&path, minimal_png()).unwrap();
            xmp_core::io::png::write_xmp(&path, &xmp).unwrap();
        }
        for i in 0..10 {
            std::fs::write(dir.path().join(format!("{i}.txt")), b"filler").unwrap();
        }

        // read_dir order is not guaranteed, so assert on the count, not on which.
        let limited = scan_folder_for_sweep_limited(dir.path(), "target", 2);
        assert_eq!(limited.len(), 2, "scan must stop at the image budget");
        let unlimited = scan_folder_for_sweep_limited(dir.path(), "target", 4);
        assert_eq!(
            unlimited.len(),
            4,
            "10 non-image files must not eat the budget"
        );
    }

    async fn files_table_pool(rows: &[(i64, &str)]) -> SqlitePool {
        let pool = sqlx::sqlite::SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(
                <sqlx::sqlite::SqliteConnectOptions as std::str::FromStr>::from_str(
                    "sqlite::memory:",
                )
                .unwrap(),
            )
            .await
            .unwrap();
        sqlx::raw_sql("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL);")
            .execute(&pool)
            .await
            .unwrap();
        for (id, path) in rows {
            sqlx::query("INSERT INTO files(id, path) VALUES (?, ?)")
                .bind(id)
                .bind(path)
                .execute(&pool)
                .await
                .unwrap();
        }
        pool
    }

    #[tokio::test]
    async fn resolve_path_hides_files_that_live_inside_an_archive() {
        // Python returns None when the path contains "!", because an entry
        // inside a zip has no on-disk XMP to read. Dropping this check would
        // hand a bogus path to the XMP reader.
        let pool = files_table_pool(&[(1, "/img/a.png"), (2, "/img/bundle.zip!inner.png")]).await;
        assert_eq!(
            resolve_path(&pool, 1).await.unwrap(),
            Some("/img/a.png".to_string())
        );
        assert_eq!(resolve_path(&pool, 2).await.unwrap(), None);
        assert_eq!(resolve_path(&pool, 999).await.unwrap(), None);
    }

    #[tokio::test]
    async fn attach_file_ids_fills_known_paths_and_nulls_the_rest() {
        let pool = files_table_pool(&[(11, "/img/a.png"), (12, "/img/b.png")]).await;
        let mut matches = vec![
            json!({"path": "/img/a.png"}),
            json!({"path": "/img/missing.png"}),
            json!({"path": "/img/b.png"}),
        ];
        attach_file_ids(&pool, &mut matches).await.unwrap();
        assert_eq!(matches[0]["file_id"], 11);
        assert_eq!(
            matches[1]["file_id"],
            Value::Null,
            "a path absent from the DB must be null, not omitted"
        );
        assert_eq!(matches[2]["file_id"], 12);
    }

    fn sweep_xmp(sweep_id: &str, axis_index: &str) -> String {
        format!(
            r#"<x:xmpmeta xmlns:x="adobe:ns:meta/"><rdf:RDF
               xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
               xmlns:sweep="http://ns.yu-ai-manager/sweep/1.0/">
               <rdf:Description sweep:id="{sweep_id}" sweep:axis_0_index="{axis_index}"/>
               </rdf:RDF></x:xmpmeta>"#
        )
    }

    /// Smallest PNG the XMP writer will accept: signature + IHDR + IEND.
    fn minimal_png() -> Vec<u8> {
        let mut out = vec![0x89, b'P', b'N', b'G', 0x0d, 0x0a, 0x1a, 0x0a];
        let ihdr_body = {
            let mut b = Vec::new();
            b.extend_from_slice(b"IHDR");
            b.extend_from_slice(&1u32.to_be_bytes()); // width
            b.extend_from_slice(&1u32.to_be_bytes()); // height
            b.extend_from_slice(&[8, 6, 0, 0, 0]); // bit depth, colour type, ...
            b
        };
        out.extend_from_slice(&((ihdr_body.len() - 4) as u32).to_be_bytes());
        out.extend_from_slice(&ihdr_body);
        out.extend_from_slice(&crc32(&ihdr_body).to_be_bytes());
        out.extend_from_slice(&0u32.to_be_bytes());
        out.extend_from_slice(b"IEND");
        out.extend_from_slice(&crc32(b"IEND").to_be_bytes());
        out
    }

    fn crc32(data: &[u8]) -> u32 {
        let mut crc = 0xffff_ffffu32;
        for byte in data {
            crc ^= *byte as u32;
            for _ in 0..8 {
                crc = if crc & 1 != 0 {
                    (crc >> 1) ^ 0xedb8_8320
                } else {
                    crc >> 1
                };
            }
        }
        !crc
    }
}
