use axum::{
    extract::{Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde_json::{json, Value};
use sqlx::Row;
use std::collections::HashMap;
use std::path::Path;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(message: &str, status: StatusCode, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|c| &c.0))
}

struct A1111Parsed {
    positive: String,
    negative: String,
    params: HashMap<String, String>,
}

fn parse_a1111_full(raw: &str) -> A1111Parsed {
    let lines: Vec<&str> = raw.split('\n').collect();
    let mut pos: Vec<&str> = Vec::new();
    let mut neg: Vec<String> = Vec::new();
    let mut i = 0;

    while i < lines.len() {
        let t = lines[i].trim();
        if t.starts_with("Negative prompt:") || t.starts_with("Steps:") {
            break;
        }
        pos.push(lines[i]);
        i += 1;
    }

    if i < lines.len() && lines[i].trim().starts_with("Negative prompt:") {
        let first = lines[i].trim()["Negative prompt:".len()..]
            .trim()
            .to_string();
        if !first.is_empty() {
            neg.push(first);
        }
        i += 1;
        while i < lines.len() && !lines[i].trim().starts_with("Steps:") {
            neg.push(lines[i].trim().to_string());
            i += 1;
        }
    }

    let mut params: HashMap<String, String> = HashMap::new();
    if i < lines.len() && lines[i].trim().starts_with("Steps:") {
        let param_line = lines[i].trim();
        for entry in param_line.split(',') {
            let entry = entry.trim();
            if let Some((k, v)) = entry.split_once(':') {
                let k = k.trim();
                let v = v.trim();
                if !k.is_empty() && !v.is_empty() {
                    params.insert(k.to_string(), v.to_string());
                }
            }
        }
    }

    A1111Parsed {
        positive: pos.join("\n").trim().to_string(),
        negative: neg.join("\n").trim().to_string(),
        params,
    }
}

fn join_novelai_v4_negative(raw_meta_json: &str) -> Option<String> {
    let outer: Value = serde_json::from_str(raw_meta_json).ok()?;
    let comment_str = outer.get("Comment")?.as_str()?;
    let data: Value = serde_json::from_str(comment_str).ok()?;
    let v4neg = data.get("v4_negative_prompt")?;

    let mut parts: Vec<String> = Vec::new();
    if let Some(base) = v4neg
        .get("caption")
        .and_then(|c| c.get("base_caption"))
        .and_then(|v| v.as_str())
    {
        if !base.is_empty() {
            parts.push(base.to_owned());
        }
    }
    if let Some(chars) = v4neg.get("captions").and_then(|v| v.as_array()) {
        for ch in chars {
            if let Some(p) = ch
                .get("frames")
                .and_then(|f| f.as_array())
                .and_then(|f| f.first())
                .and_then(|f| f.get("char_caption"))
                .and_then(|v| v.as_str())
            {
                if !p.is_empty() {
                    parts.push(p.to_owned());
                }
            }
        }
    }
    if parts.is_empty() {
        None
    } else {
        Some(parts.join(", "))
    }
}

pub async fn api_share_data(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }

    let file_row = sqlx::query("SELECT id, path FROM files WHERE id=? AND is_deleted=0")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await;
    let file_row = match file_row {
        Ok(Some(r)) => r,
        Ok(None) => {
            return api_error("Not found", StatusCode::NOT_FOUND, "not_found");
        }
        Err(e) => {
            tracing::error!(?e, "share data db error");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "internal_server_error"})),
            )
                .into_response();
        }
    };

    let file_path: String = file_row.get("path");
    let filename = Path::new(&file_path)
        .file_name()
        .and_then(|n| n.to_str())
        .unwrap_or("")
        .to_string();

    let tmpl = sqlx::query(
        "SELECT file_id, raw_prompt, raw_negative, model_name, raw_meta_json \
         FROM templates WHERE file_id=?",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await;

    let tmpl = match tmpl {
        Ok(r) => r,
        Err(e) => {
            tracing::error!(?e, "share template db error");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "internal_server_error"})),
            )
                .into_response();
        }
    };

    let Some(tmpl) = tmpl else {
        return api_result(json!({
            "file_id": file_id,
            "filename": filename,
            "positive": "",
            "negative": "",
            "model": "",
            "parameters": {},
            "has_metadata": false,
            "message": "No metadata available for this file."
        }));
    };

    let raw_prompt: String = tmpl
        .get::<Option<String>, _>("raw_prompt")
        .unwrap_or_default();
    let raw_negative: String = tmpl
        .get::<Option<String>, _>("raw_negative")
        .unwrap_or_default();
    let mut model: String = tmpl
        .get::<Option<String>, _>("model_name")
        .unwrap_or_default();
    let raw_meta_json: Option<String> = tmpl.get("raw_meta_json");

    let parsed = parse_a1111_full(&raw_prompt);
    let mut positive = parsed.positive;
    let mut negative = if parsed.negative.is_empty() {
        raw_negative.clone()
    } else {
        parsed.negative
    };
    let mut params = parsed.params;
    if model.is_empty() {
        if let Some(m) = params.get("Model") {
            model = m.clone();
        }
    }

    // meta JSON overlay
    if let Some(ref meta_str) = raw_meta_json {
        if let Ok(meta) = serde_json::from_str::<Value>(meta_str) {
            if model.is_empty() {
                model = meta
                    .get("model")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
            }
            if !params.contains_key("Seed") {
                if let Some(s) = meta.get("seed").and_then(|v| v.as_i64()) {
                    params.insert("Seed".to_string(), s.to_string());
                }
            }
            if !params.contains_key("Steps") {
                if let Some(s) = meta.get("steps").and_then(|v| v.as_i64()) {
                    params.insert("Steps".to_string(), s.to_string());
                }
            }
            if !params.contains_key("CFG scale") {
                if let Some(s) = meta.get("cfg_scale").and_then(|v| v.as_f64()) {
                    params.insert("CFG scale".to_string(), s.to_string());
                }
            }
            if !params.contains_key("Sampler") {
                if let Some(s) = meta.get("sampler").and_then(|v| v.as_str()) {
                    params.insert("Sampler".to_string(), s.to_string());
                }
            }
            if !params.contains_key("Size") {
                if let (Some(w), Some(h)) = (
                    meta.get("width").and_then(|v| v.as_i64()),
                    meta.get("height").and_then(|v| v.as_i64()),
                ) {
                    params.insert("Size".to_string(), format!("{}x{}", w, h));
                }
            }
        }
    }

    // NAI V4 negative fallback
    if negative.is_empty() {
        if let Some(ref meta_str) = raw_meta_json {
            if let Some(v4neg) = join_novelai_v4_negative(meta_str) {
                negative = v4neg;
            }
        }
    }

    let positive_truncated: String = positive.chars().take(2000).collect();
    let negative_truncated: String = negative.chars().take(1000).collect();

    let mut share_data = json!({
        "v": "1.0",
        "t": "prompt",
        "p": positive_truncated,
        "n": negative_truncated,
        "src": "TagDB"
    });
    let obj = share_data.as_object_mut().unwrap();
    if !model.is_empty() {
        obj.insert("m".to_string(), json!(model));
    }
    if let Some(s) = params.get("Seed") {
        obj.insert("s".to_string(), json!(s));
    }
    if let Some(s) = params.get("Steps") {
        obj.insert("st".to_string(), json!(s));
    }
    if let Some(s) = params.get("CFG scale") {
        obj.insert("cfg".to_string(), json!(s));
    }
    if let Some(s) = params.get("Sampler") {
        obj.insert("sa".to_string(), json!(s));
    }
    if let Some(s) = params.get("Size") {
        obj.insert("sz".to_string(), json!(s));
    }

    api_result(share_data)
}
