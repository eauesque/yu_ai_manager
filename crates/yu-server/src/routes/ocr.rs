use axum::{
    extract::{Extension, Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::json;
use sqlx::Row;
use std::time::Duration;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

/// GET /api/ocr/engines
pub async fn ocr_engines(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }
    // ponytail: ai_servers is not wired here yet; Phase 2 can read config.
    Json(json!({"engines": [], "manga_ocr_available": false})).into_response()
}

/// GET /api/ocr/benchmark/report/{report_id}
pub async fn ocr_benchmark_report(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(report_id): Path<String>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }
    if report_id.contains('/') || report_id.contains('\\') || report_id.contains("..") {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "invalid_report_id"})),
        )
            .into_response();
    }
    let reports = state
        .config
        .project_root
        .join("extensions/builtin_ocr/benchmarks/reports");
    match std::fs::read(reports.join(format!("{report_id}.json"))) {
        Ok(bytes) => match serde_json::from_slice::<serde_json::Value>(&bytes) {
            Ok(report) => Json(report).into_response(),
            Err(_) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "invalid_report"})),
            )
                .into_response(),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "report_not_found"})),
        )
            .into_response(),
        Err(_) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "report_read_failed"})),
        )
            .into_response(),
    }
}

#[derive(Deserialize, Default)]
pub struct ResultGetParams {
    pub task: Option<String>,
    pub engine: Option<String>,
    pub all: Option<String>,
}

#[derive(Deserialize, Default)]
pub struct ResultDeleteParams {
    pub task: Option<String>,
    pub engine: Option<String>,
}

#[derive(Deserialize, Default)]
pub struct TranslationsParams {
    pub target_lang: Option<String>,
}

const RESULT_COLS: &str =
    "id, file_id, engine, task, regions_json, full_text, language, structured_json, created_at";

fn row_to_result(row: &sqlx::sqlite::SqliteRow) -> serde_json::Value {
    let regions: serde_json::Value = row
        .try_get::<Option<String>, _>("regions_json")
        .ok()
        .flatten()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!([]));
    let structured: serde_json::Value = row
        .try_get::<Option<String>, _>("structured_json")
        .ok()
        .flatten()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}));

    json!({
        "ok": true,
        "error": null,
        "data": null,
        "id": row.get::<i64, _>("id"),
        "file_id": row.get::<i64, _>("file_id"),
        "engine": row.get::<String, _>("engine"),
        "task": row.get::<String, _>("task"),
        "regions": regions,
        "full_text": row.try_get::<Option<String>, _>("full_text").ok().flatten().unwrap_or_default(),
        "language": row.try_get::<Option<String>, _>("language").ok().flatten().unwrap_or_default(),
        "headings": structured.get("headings").cloned().unwrap_or_else(|| json!([])),
        "tables": structured.get("tables").cloned().unwrap_or_else(|| json!([])),
        "page_layout": structured.get("page_layout").cloned().unwrap_or_else(|| json!("")),
        "created_at": row.get::<i64, _>("created_at"),
    })
}

/// GET /api/ocr/result/{file_id}
pub async fn ocr_result_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Query(params): Query<ResultGetParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let all_truthy = params
        .all
        .as_deref()
        .is_some_and(|v| !v.is_empty() && v != "0" && v != "false");
    if all_truthy {
        let rows = sqlx::query(&format!(
            "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC"
        ))
        .bind(file_id)
        .fetch_all(&state.db_read)
        .await;
        return match rows {
            Ok(rows) => Json(json!({
                "ok": true,
                "error": null,
                "data": null,
                "file_id": file_id,
                "results": rows.iter().map(row_to_result).collect::<Vec<_>>()
            }))
            .into_response(),
            Err(e) => {
                tracing::error!("ocr_result_get all: {e}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({"ok": false, "error": "db_error"})),
                )
                    .into_response()
            }
        };
    }

    let row = match (&params.task, &params.engine) {
        (Some(task), Some(engine)) => {
            sqlx::query(&format!(
                "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? AND task=? AND engine=? LIMIT 1"
            ))
            .bind(file_id)
            .bind(task)
            .bind(engine)
            .fetch_optional(&state.db_read)
            .await
        }
        (Some(task), None) => {
            sqlx::query(&format!(
                "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? AND task=? ORDER BY created_at DESC, id DESC LIMIT 1"
            ))
            .bind(file_id)
            .bind(task)
            .fetch_optional(&state.db_read)
            .await
        }
        _ => {
            sqlx::query(&format!(
                "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC LIMIT 1"
            ))
            .bind(file_id)
            .fetch_optional(&state.db_read)
            .await
        }
    };

    match row {
        Ok(Some(row)) => Json(row_to_result(&row)).into_response(),
        Ok(None) => Json(json!({"ok": true, "error": null, "data": null, "status": "not_found"}))
            .into_response(),
        Err(e) => {
            tracing::error!("ocr_result_get: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

/// GET /api/ocr/translations/{file_id}
pub async fn ocr_translations(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Query(params): Query<TranslationsParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let base_sql = r#"
        SELECT
            t.id,
            t.ocr_result_id,
            t.target_lang,
            t.translated_text,
            t.engine,
            t.region_translations_json,
            t.created_at,
            r.file_id,
            r.task,
            r.engine AS ocr_engine
        FROM file_translations t
        JOIN file_ocr_results r ON r.id = t.ocr_result_id
        WHERE r.file_id=?
    "#;

    let rows = if let Some(target_lang) = params.target_lang.as_deref().filter(|s| !s.is_empty()) {
        sqlx::query(&format!(
            "{base_sql} AND t.target_lang=? ORDER BY t.created_at DESC, t.id DESC"
        ))
        .bind(file_id)
        .bind(target_lang)
        .fetch_all(&state.db_read)
        .await
    } else {
        sqlx::query(&format!("{base_sql} ORDER BY t.created_at DESC, t.id DESC"))
            .bind(file_id)
            .fetch_all(&state.db_read)
            .await
    };

    match rows {
        Ok(rows) => {
            let translations: Vec<_> = rows
                .iter()
                .map(|row| {
                    let region_translations: serde_json::Value = row
                        .try_get::<Option<String>, _>("region_translations_json")
                        .ok()
                        .flatten()
                        .and_then(|s| serde_json::from_str(&s).ok())
                        .unwrap_or_else(|| json!([]));
                    json!({
                        "id": row.get::<i64, _>("id"),
                        "ocr_result_id": row.get::<i64, _>("ocr_result_id"),
                        "target_lang": row.get::<String, _>("target_lang"),
                        "translated_text": row.try_get::<Option<String>, _>("translated_text").ok().flatten(),
                        "engine": row.try_get::<Option<String>, _>("engine").ok().flatten().unwrap_or_default(),
                        "created_at": row.get::<i64, _>("created_at"),
                        "region_translations": region_translations,
                        "file_id": row.get::<i64, _>("file_id"),
                        "task": row.get::<String, _>("task"),
                        "ocr_engine": row.get::<String, _>("ocr_engine"),
                    })
                })
                .collect();
            Json(json!({
                "ok": true,
                "error": null,
                "data": null,
                "file_id": file_id,
                "translations": translations,
            }))
            .into_response()
        }
        Err(e) => {
            tracing::error!("ocr_translations: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

/// DELETE /api/ocr/result/{file_id}
pub async fn ocr_result_delete(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    Query(params): Query<ResultDeleteParams>,
) -> Response {
    let (trans_sql, results_sql) = match (&params.task, &params.engine) {
        (Some(_), Some(_)) => (
            "DELETE FROM file_translations WHERE ocr_result_id IN (SELECT id FROM file_ocr_results WHERE file_id=? AND task=? AND engine=?)",
            "DELETE FROM file_ocr_results WHERE file_id=? AND task=? AND engine=?",
        ),
        (Some(_), None) => (
            "DELETE FROM file_translations WHERE ocr_result_id IN (SELECT id FROM file_ocr_results WHERE file_id=? AND task=?)",
            "DELETE FROM file_ocr_results WHERE file_id=? AND task=?",
        ),
        _ => (
            "DELETE FROM file_translations WHERE ocr_result_id IN (SELECT id FROM file_ocr_results WHERE file_id=?)",
            "DELETE FROM file_ocr_results WHERE file_id=?",
        ),
    };

    let trans_result = match (&params.task, &params.engine) {
        (Some(task), Some(engine)) => {
            sqlx::query(trans_sql)
                .bind(file_id)
                .bind(task)
                .bind(engine)
                .execute(&state.db)
                .await
        }
        (Some(task), None) => {
            sqlx::query(trans_sql)
                .bind(file_id)
                .bind(task)
                .execute(&state.db)
                .await
        }
        _ => {
            sqlx::query(trans_sql)
                .bind(file_id)
                .execute(&state.db)
                .await
        }
    };
    if let Err(e) = trans_result {
        tracing::error!("ocr_result_delete translations: {e}");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "db_error"})),
        )
            .into_response();
    }

    let result = match (&params.task, &params.engine) {
        (Some(task), Some(engine)) => {
            sqlx::query(results_sql)
                .bind(file_id)
                .bind(task)
                .bind(engine)
                .execute(&state.db)
                .await
        }
        (Some(task), None) => {
            sqlx::query(results_sql)
                .bind(file_id)
                .bind(task)
                .execute(&state.db)
                .await
        }
        _ => {
            sqlx::query(results_sql)
                .bind(file_id)
                .execute(&state.db)
                .await
        }
    };

    match result {
        Ok(r) => Json(json!({"deleted": r.rows_affected()})).into_response(),
        Err(e) => {
            tracing::error!("ocr_result_delete: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

/// PUT /api/ocr/profiles/{model_prefix}
///
/// Ports `core/ocr_api/benchmark_ops.py::api_ocr_profile_update`.
///
/// Storage is the extension's own `profiles/model_profiles.json`, NOT the
/// unrelated `profiles_dir()` in auto_stubs.rs (which resolves
/// TAGDB_PROFILES_DIR / project_root/profiles and belongs to a different
/// feature). Writing there would silently split the store in two.
///
/// The Python side clamps each score to 0..=100 via `max(0, min(100, int(v)))`
/// and drops non-numeric values; the file carries `{version, updated_at,
/// profiles}` and the reader also accepts a bare mapping. Both behaviours are
/// reproduced here so a file written by either side stays readable by the other.
pub async fn ocr_profiles_update(
    State(state): State<SharedState>,
    Path(model_prefix): Path<String>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let scores = body.get("scores").and_then(|v| v.as_object());
    let Some(scores) = scores.filter(|m| !m.is_empty()) else {
        // Python: `if not scores: return api_error("scores is required", 400)`.
        // An empty object takes this branch there too, so it does here.
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "scores is required"})),
        )
            .into_response();
    };

    // Same clamp and same "numbers only" filter as update_model_profile().
    let mut clamped = serde_json::Map::new();
    for (k, v) in scores {
        if let Some(n) = v.as_f64() {
            let i = crate::num::sat_i64(n.trunc());
            clamped.insert(k.clone(), json!(i.clamp(0, 100)));
        }
    }

    let path = ocr_profiles_path(&state);
    let mut store = read_ocr_profiles(&path);
    store.insert(
        model_prefix.clone(),
        serde_json::Value::Object(clamped.clone()),
    );

    if let Err(e) = write_ocr_profiles(&path, &store) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("failed to save profiles: {e}")})),
        )
            .into_response();
    }

    Json(json!({"model": model_prefix, "scores": clamped})).into_response()
}

/// GET /api/ocr/profiles
pub async fn ocr_profiles_list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let local = read_ocr_profiles(&ocr_profiles_path(&state));
    let mut profiles = builtin_ocr_profiles();
    profiles.extend(local.clone());
    let mut profiles = profiles.into_iter().collect::<Vec<_>>();
    profiles.sort_unstable_by(|(model, _), (other, _)| model.cmp(other));

    Json(
        json!({"profiles": profiles.into_iter().map(|(model, scores)| {
        json!({
            "model": model,
            "scores": scores,
            "source": if local.contains_key(&model) { "local" } else { "builtin" },
        })
    }).collect::<Vec<_>>() }),
    )
    .into_response()
}

/// POST /api/ocr/profiles/fetch
pub async fn ocr_profiles_fetch(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<serde_json::Value>>,
) -> Response {
    ocr_profiles_fetch_with_policy(
        state,
        auth_context,
        body.map(|Json(body)| body).unwrap_or_default(),
        false,
    )
    .await
}

async fn ocr_profiles_fetch_with_policy(
    state: SharedState,
    auth_context: Option<Extension<AuthContext>>,
    body: serde_json::Value,
    allow_local: bool,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let url = body
        .get("url")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    if url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "url is required"})),
        )
            .into_response();
    }
    if let Some(error) = crate::routes::analysis_net::validate_openai_compat_url(url, allow_local) {
        let status = if error == "Blocked address" || error.to_lowercase().contains("http/https") {
            StatusCode::BAD_REQUEST
        } else {
            StatusCode::INTERNAL_SERVER_ERROR
        };
        return (status, Json(json!({"ok": false, "error": error}))).into_response();
    }

    let fetched = async {
        let client = crate::analysis_engines::http_client::build_pinned_client(
            url,
            allow_local,
            Duration::from_secs(15),
        )
        .await?;
        let response = client
            .get(url)
            .header(reqwest::header::USER_AGENT, "YU-AI-Manager")
            .header(reqwest::header::ACCEPT, "application/json")
            .send()
            .await
            .map_err(|error| {
                crate::analysis_engines::EngineError::msg(format!(
                    "Failed to fetch profiles: {error}"
                ))
            })?
            .error_for_status()
            .map_err(|error| {
                crate::analysis_engines::EngineError::msg(format!(
                    "Failed to fetch profiles: {error}"
                ))
            })?;
        let body =
            crate::analysis_engines::http_client::read_response_capped(response, 1_048_576).await?;
        serde_json::from_str::<serde_json::Value>(&body).map_err(|error| {
            crate::analysis_engines::EngineError::msg(format!("Failed to fetch profiles: {error}"))
        })
    }
    .await;

    let data = match fetched {
        Ok(data) => data,
        Err(error) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": error.to_string()})),
            )
                .into_response()
        }
    };
    let profiles = match data {
        serde_json::Value::Object(mut data) => match data.remove("profiles") {
            Some(serde_json::Value::Object(profiles)) => profiles,
            Some(_) => return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "Invalid profile format: expected JSON object"})),
            )
                .into_response(),
            None => data,
        },
        _ => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "Invalid profile format: expected JSON object"})),
            )
                .into_response()
        }
    };

    let mut fetched = serde_json::Map::new();
    for (model, scores) in profiles {
        let Some(scores) = scores.as_object() else {
            continue;
        };
        let mut clamped = serde_json::Map::new();
        for (name, score) in scores {
            if let Some(score) = score.as_f64() {
                clamped.insert(
                    name.clone(),
                    json!(crate::num::sat_i64(score.trunc()).clamp(0, 100)),
                );
            }
        }
        fetched.insert(model, serde_json::Value::Object(clamped));
    }

    let path = ocr_profiles_path(&state);
    let existing = read_ocr_profiles(&path);
    let new_models = fetched
        .keys()
        .filter(|model| !existing.contains_key(*model))
        .count();
    let updated_models = fetched.len() - new_models;
    let mut merged = existing;
    merged.extend(fetched.clone());
    if let Err(error) = write_ocr_profiles(&path, &merged) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": format!("failed to save profiles: {error}")})),
        )
            .into_response();
    }

    let fetched_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    Json(json!({
        "profiles": fetched,
        "source": url,
        "fetched_at": fetched_at,
        "model_count": fetched.len(),
        "merged_count": merged.len(),
        "new_models": new_models,
        "updated_models": updated_models,
    }))
    .into_response()
}

fn builtin_ocr_profiles() -> serde_json::Map<String, serde_json::Value> {
    serde_json::from_value(json!({
        "openbmb/minicpm-v4.5": {
            "ocr": 97, "ocr_document": 90, "ocr_manga": 70,
            "caption": 95, "tag": 93, "nsfw": 60,
        },
        "openbmb/minicpm-o4.5": {
            "ocr": 95, "ocr_document": 92, "ocr_manga": 65,
            "caption": 93, "tag": 90,
        },
        "huihui_ai/qwen2.5-vl-abliterated": {
            "ocr": 80, "ocr_document": 75, "ocr_manga": 50,
            "caption": 85, "tag": 85, "nsfw": 95,
        },
        "huihui_ai/qwen3-vl-abliterated": {
            "ocr": 85, "ocr_document": 80, "ocr_manga": 55,
            "caption": 88, "tag": 88, "nsfw": 95,
        },
        "qwen2.5vl": {
            "ocr": 80, "ocr_document": 78, "ocr_manga": 50,
            "caption": 85, "tag": 85,
        },
        "llama3.2-vision": {
            "ocr": 70, "ocr_document": 65, "ocr_manga": 30,
            "caption": 80, "tag": 78,
        },
    }))
    .expect("builtin OCR profiles are objects")
}

fn ocr_profiles_path(state: &SharedState) -> std::path::PathBuf {
    state
        .config
        .project_root
        .join("extensions/builtin_ocr/profiles/model_profiles.json")
}

/// Read the profile map, tolerating both the wrapped and the bare shape.
fn read_ocr_profiles(path: &std::path::Path) -> serde_json::Map<String, serde_json::Value> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return serde_json::Map::new();
    };
    let Ok(data) = serde_json::from_str::<serde_json::Value>(&text) else {
        // Python logs and returns {} rather than failing the request.
        return serde_json::Map::new();
    };
    match data.get("profiles") {
        Some(profiles) => profiles.as_object().cloned().unwrap_or_default(),
        None => data.as_object().cloned().unwrap_or_default(),
    }
}

fn write_ocr_profiles(
    path: &std::path::Path,
    profiles: &serde_json::Map<String, serde_json::Value>,
) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let updated_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let doc = json!({
        "version": 1,
        "updated_at": updated_at,
        "profiles": profiles,
    });
    std::fs::write(path, serde_json::to_string_pretty(&doc)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::semantic_test_state_with_root;
    use axum::{body::to_bytes, http::header::LOCATION, routing::get, Router};
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };

    async fn body_json(response: Response) -> serde_json::Value {
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    async fn test_state(root: &tempfile::TempDir) -> SharedState {
        semantic_test_state_with_root(false, String::new(), root.path().to_path_buf()).await
    }

    async fn test_server(app: Router) -> Option<(String, tokio::task::JoinHandle<()>)> {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.ok()?;
        let address = listener.local_addr().ok()?;
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Some((format!("http://{address}/"), server))
    }

    #[tokio::test]
    async fn ocr_profiles_roundtrip_returns_written_profile() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let updated = ocr_profiles_update(
            State(state.clone()),
            Path("test-model".to_string()),
            None,
            Json(json!({"scores": {"ocr": 91}})),
        )
        .await;
        assert_eq!(updated.status(), StatusCode::OK);

        let body = body_json(ocr_profiles_list(State(state), None).await).await;
        assert_eq!(body["profiles"].as_array().unwrap().len(), 7);
        assert!(body["profiles"].as_array().unwrap().iter().any(|profile| {
            profile == &json!({"model": "test-model", "scores": {"ocr": 91}, "source": "local"})
        }));
    }

    #[tokio::test]
    async fn ocr_profiles_keeps_builtins_when_one_is_overridden_locally() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let path = ocr_profiles_path(&state);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, r#"{"profiles":{"qwen2.5vl":{"ocr":99}}}"#).unwrap();

        let body = body_json(ocr_profiles_list(State(state), None).await).await;
        let profiles = body["profiles"].as_array().unwrap();
        assert_eq!(profiles.len(), 6);
        assert_eq!(profiles[0]["model"], "huihui_ai/qwen2.5-vl-abliterated");
        assert_eq!(profiles[5]["model"], "qwen2.5vl");
        assert!(profiles.iter().all(|profile| {
            profile["source"]
                == if profile["model"] == "qwen2.5vl" {
                    "local"
                } else {
                    "builtin"
                }
        }));
        assert_eq!(
            profiles[5],
            json!({"model": "qwen2.5vl", "scores": {"ocr": 99}, "source": "local"})
        );
    }

    #[tokio::test]
    async fn ocr_profiles_tolerates_missing_or_malformed_local_file() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let missing = ocr_profiles_list(State(state.clone()), None).await;
        assert_eq!(missing.status(), StatusCode::OK);
        assert_eq!(
            body_json(missing).await["profiles"]
                .as_array()
                .unwrap()
                .len(),
            6
        );

        let path = ocr_profiles_path(&state);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, "{bad json").unwrap();
        let malformed = ocr_profiles_list(State(state), None).await;
        assert_eq!(malformed.status(), StatusCode::OK);
        assert_eq!(
            body_json(malformed).await["profiles"]
                .as_array()
                .unwrap()
                .len(),
            6
        );
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_merges_and_returns_seven_keys() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let path = ocr_profiles_path(&state);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(
            &path,
            r#"{"profiles":{"existing":{"ocr":1},"kept":{"ocr":2}}}"#,
        )
        .unwrap();
        let Some((url, server)) = test_server(Router::new().route(
            "/",
            get(|| async {
                Json(json!({"profiles":{"existing":{"ocr":101},"new":{"ocr":-2,"skip":"x"}}}))
            }),
        ))
        .await
        else {
            return;
        };

        let response = ocr_profiles_fetch_with_policy(state, None, json!({"url": url}), true).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = body_json(response).await;
        assert_eq!(body.as_object().unwrap().len(), 7);
        assert_eq!(body["model_count"], 2);
        assert_eq!(body["merged_count"], 3);
        assert_eq!(body["new_models"], 1);
        assert_eq!(body["updated_models"], 1);
        assert_eq!(
            body["profiles"],
            json!({"existing":{"ocr":100},"new":{"ocr":0}})
        );
        server.abort();
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_does_not_follow_redirects() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let target_hits = Arc::new(AtomicUsize::new(0));
        let target_hits_for_route = target_hits.clone();
        let Some((url, server)) = test_server(
            Router::new()
                .route(
                    "/",
                    get(|| async { (StatusCode::FOUND, [(LOCATION, "/target")]) }),
                )
                .route(
                    "/target",
                    get(move || {
                        let target_hits = target_hits_for_route.clone();
                        async move {
                            target_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"redirected":{"ocr":50}}))
                        }
                    }),
                ),
        )
        .await
        else {
            return;
        };

        let response = ocr_profiles_fetch_with_policy(state, None, json!({"url": url}), true).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(target_hits.load(Ordering::SeqCst), 0);
        server.abort();
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_rejects_oversized_response() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let Some((url, server)) =
            test_server(Router::new().route("/", get(|| async { "x".repeat(1_048_577) }))).await
        else {
            return;
        };

        let response = ocr_profiles_fetch_with_policy(state, None, json!({"url": url}), true).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(body_json(response).await["error"], "response_too_large");
        server.abort();
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_rejects_loopback() {
        let root = tempfile::tempdir().unwrap();
        let response = ocr_profiles_fetch(
            State(test_state(&root).await),
            None,
            Some(Json(json!({"url":"http://127.0.0.1:8080/profiles.json"}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            body_json(response).await,
            json!({"ok":false,"error":"Blocked address"})
        );
    }
}
