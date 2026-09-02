//! Native GET /api/files/{file_id}/analysis-trace; Python source: routes/file_trace.py.

use axum::{
    extract::{Extension, Path as AxumPath, State},
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

fn sort_engines_stable(mut engines: Vec<Value>) -> Vec<Value> {
    engines.sort_by(|left, right| {
        let left_at = left.get("analyzed_at").and_then(Value::as_i64).unwrap_or(0);
        let right_at = right
            .get("analyzed_at")
            .and_then(Value::as_i64)
            .unwrap_or(0);
        right_at.cmp(&left_at)
    });
    engines
}

fn api_success(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(message: &str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({
            "ok": false,
            "error": message,
        })),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn build_trace(pool: &SqlitePool, file_id: i64) -> Result<Option<Value>, sqlx::Error> {
    let row = sqlx::query("SELECT meta_source FROM files WHERE id=? AND is_deleted=0")
        .bind(file_id)
        .fetch_optional(pool)
        .await?;
    let Some(row) = row else {
        return Ok(None);
    };
    let meta_source = row
        .try_get::<Option<String>, _>("meta_source")
        .ok()
        .flatten()
        .filter(|value| !value.is_empty())
        .unwrap_or_else(|| "unknown".to_string());
    let mut engines = Vec::new();

    let wd_rows = sqlx::query(
        "SELECT md.model, COUNT(*) as tag_count, MAX(fwt.created_at) as last_at
         FROM file_wd_tags fwt JOIN wd_model_dict md ON md.id=fwt.model_id
         WHERE fwt.file_id=? GROUP BY fwt.model_id ORDER BY md.model",
    )
    .bind(file_id)
    .fetch_all(pool)
    .await?;
    for row in wd_rows {
        engines.push(json!({
            "engine": "wd_tagger",
            "model": row.get::<String, _>("model"),
            "tag_count": row.get::<i64, _>("tag_count"),
            "analyzed_at": row.try_get::<Option<i64>, _>("last_at").ok().flatten(),
            "source": "file_wd_tags",
        }));
    }

    let hailo_rows = sqlx::query(
        "SELECT source, COUNT(*) as tag_count, MAX(created_at) as last_at
         FROM file_hailo_tags WHERE file_id=? GROUP BY source ORDER BY source",
    )
    .bind(file_id)
    .fetch_all(pool)
    .await?;
    for row in hailo_rows {
        engines.push(json!({
            "engine": "hailo_tagger",
            "source_label": row.get::<String, _>("source"),
            "tag_count": row.get::<i64, _>("tag_count"),
            "analyzed_at": row.try_get::<Option<i64>, _>("last_at").ok().flatten(),
            "source": "file_hailo_tags",
        }));
    }

    let analysis_rows = sqlx::query(
        "SELECT engine, quality_score, analyzed_at FROM analysis WHERE file_id=? ORDER BY id",
    )
    .bind(file_id)
    .fetch_all(pool)
    .await?;
    for row in analysis_rows {
        engines.push(json!({
            "engine": row.get::<String, _>("engine"),
            "quality_score": row.try_get::<Option<f64>, _>("quality_score").ok().flatten(),
            "analyzed_at": row.try_get::<Option<i64>, _>("analyzed_at").ok().flatten(),
            "source": "analysis",
        }));
    }

    Ok(Some(json!({
        "meta_source": meta_source,
        "engines": sort_engines_stable(engines),
    })))
}

pub async fn analysis_trace(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_trace(&state.db_read, file_id).await {
        Ok(Some(value)) => api_success(value),
        Ok(None) => api_error(
            &format!("file_id={file_id} が見つかりません"),
            StatusCode::NOT_FOUND,
        ),
        Err(error) => {
            tracing::error!(?error, file_id, "analysis trace failed");
            api_error(
                "Failed to get analysis trace",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn stable_sort_keeps_insertion_order_for_equal_analyzed_at() {
        let engines = sort_engines_stable(vec![
            json!({"engine": "wd_tagger", "analyzed_at": 10}),
            json!({"engine": "hailo_tagger", "analyzed_at": 10}),
            json!({"engine": "analysis", "analyzed_at": 20}),
        ]);
        let names = engines
            .iter()
            .map(|v| v["engine"].as_str().unwrap())
            .collect::<Vec<_>>();
        assert_eq!(names, vec!["analysis", "wd_tagger", "hailo_tagger"]);
    }
}
