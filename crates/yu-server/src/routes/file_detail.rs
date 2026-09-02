//! Native GET /api/file/{file_id}: SQLite read, no Python bridge.
use axum::{
    extract::{Extension, Path, State},
    response::{IntoResponse, Response},
    Json,
};
use meta_extract::resolve_detail_fields;
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const FILE_DETAIL_SQL: &str = "SELECT f.id, f.path, f.mtime, f.size, f.meta_source, f.has_sweep, \
     tm.raw_prompt, tm.raw_negative, tm.format, tm.raw_meta_json, \
     tm.model_name, tm.prompt_lang, tm.prompt_lang_confidence \
     FROM files f \
     LEFT JOIN templates tm ON tm.file_id = f.id \
     WHERE f.id = ?";

const FILE_TAGS_SQL: &str = "SELECT t.tag, t.namespace, ft.weight, ft.source \
     FROM file_tags ft \
     JOIN tags t ON t.id = ft.tag_id \
     WHERE ft.file_id = ? \
     ORDER BY t.namespace, t.tag";

pub async fn get_file_detail(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }

    let pool = &state.db_read;

    let row = match sqlx::query(FILE_DETAIL_SQL)
        .bind(file_id)
        .fetch_optional(pool)
        .await
    {
        Ok(Some(r)) => r,
        Ok(None) => {
            return Json(json!({"ok": false, "error": "not_found"})).into_response();
        }
        Err(err) => {
            tracing::error!(?err, "file_detail: db query failed");
            return Json(json!({"ok": false, "error": "db_error"})).into_response();
        }
    };

    let id: i64 = row.get("id");
    let path: String = row.get("path");
    let mtime: i64 = row.get("mtime");
    let size: i64 = row.get("size");
    let meta_source: String = row
        .get::<Option<String>, _>("meta_source")
        .unwrap_or_default();
    let format: Option<String> = row.get("format");
    let has_sweep: Option<bool> = row.get::<Option<i64>, _>("has_sweep").map(|v| v != 0);
    let raw_prompt: String = row
        .get::<Option<String>, _>("raw_prompt")
        .unwrap_or_default();
    let raw_negative: String = row
        .get::<Option<String>, _>("raw_negative")
        .unwrap_or_default();
    let raw_meta_json: Option<String> = row.get("raw_meta_json");
    let model_name: Option<String> = row.get("model_name");
    let prompt_lang: Option<String> = row.get("prompt_lang");
    let prompt_lang_confidence: Option<f64> = row.get("prompt_lang_confidence");

    let tags: Vec<Value> = match sqlx::query(FILE_TAGS_SQL)
        .bind(file_id)
        .fetch_all(pool)
        .await
    {
        Ok(rows) => rows
            .into_iter()
            .map(|r| {
                json!({
                    "tag": r.get::<String, _>("tag"),
                    "namespace": r.get::<String, _>("namespace"),
                    "weight": r.get::<Option<f64>, _>("weight"),
                    "source": r.get::<Option<String>, _>("source"),
                })
            })
            .collect(),
        Err(err) => {
            tracing::error!(?err, "file_detail: tags query failed");
            vec![]
        }
    };

    let detail = resolve_detail_fields(
        &meta_source,
        &raw_prompt,
        &raw_negative,
        raw_meta_json.as_deref(),
        model_name.as_deref(),
    );

    let mut result = json!({
        "id": id,
        "path": path,
        "mtime": mtime,
        "size": size,
        "meta_source": meta_source,
        "positive": detail.positive,
        "negative": detail.negative,
        "format": format,
        "resolution": detail.resolution,
        "model": detail.model,
        "parameters": detail.parameters,
        "tags": tags,
        "raw_meta_json": raw_meta_json,
    });

    if let Some(v) = has_sweep {
        result["has_sweep"] = json!(v);
    }
    if let Some(lang) = prompt_lang {
        result["prompt_lang"] = json!(lang);
        result["prompt_lang_confidence"] = json!(prompt_lang_confidence.unwrap_or(0.0));
    }
    if let Some(nai) = detail.novelai_v4 {
        result["novelai_v4"] = nai;
    }

    Json(result).into_response()
}
