//! Native GET /api/file/{file_id}: SQLite read, no Python bridge.
use axum::{
    extract::{Extension, Path, State},
    http::StatusCode,
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

/// Insert an optional field into the payload.
///
/// `value[key] = v` would do the same, but indexing a `Value` is what
/// `clippy::indexing_slicing` flags; going through the map states that the
/// target is an object and drops the lint without an allow.
fn set(target: &mut Value, key: &str, value: Value) {
    if let Some(map) = target.as_object_mut() {
        map.insert(key.to_string(), value);
    }
}

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
        // Python answers a missing id with 404, wrapped by `api_error` into
        // `{ok: false, error, code}` (`core/infra_core/api_errors.py:35-40`;
        // the payload's own `{"error": "Not found", "code": "not_found"}` from
        // `detail_payload.py:79` supplies the message and code). Returning 200
        // here made every caller that branches on the status treat "no such
        // file" as a successful read of an empty detail.
        Ok(None) => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"ok": false, "error": "Not found", "code": "not_found"})),
            )
                .into_response();
        }
        Err(err) => {
            tracing::error!(?err, "file_detail: db query failed");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error", "code": "db_error"})),
            )
                .into_response();
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
                    // `tags.namespace` is nullable and the common case is NULL
                    // (Python returns it as `None`). Decoding it as `String`
                    // panics on those rows, which took the whole tag list with
                    // it -- the route answered 200 with `tags: []`.
                    "namespace": r.get::<Option<String>, _>("namespace"),
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

    // Python wraps every route payload in `api_result`, which prepends
    // `ok`/`error`/`data` and then flattens the payload over them
    // (`core/infra_core/api_errors.py:57-64`). The fields the UI reads stay at
    // the top level either way, but the three envelope keys are part of the
    // response contract -- `routes::file_trace` already emits them, and the
    // parity harness compares whole bodies now that this route no longer
    // skips body comparison.
    let mut result = json!({
        "ok": true,
        "error": Value::Null,
        "data": Value::Null,
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

    // Read-only media metadata and the sections built from it, then the
    // per-format sections. Core payload, not extension output in Rust's case:
    // Python emits both here and the UI renders `sections` verbatim, so
    // omitting them dropped the container/duration/codec tables for every
    // audio and video file and the LoRA/Embedding/workflow tables for every
    // generated image.
    //
    // Order matters and matches `core/file_api/detail_payload.py:112-119`:
    // container provenance first, parsed AI metadata after.
    let media_meta = super::file_detail_media::resolve_readonly_media_metadata(
        &meta_source,
        raw_meta_json.as_deref(),
    );
    let mut sections = Vec::new();
    if let Some(meta) = &media_meta {
        set(
            &mut result,
            "readonly_media_metadata",
            Value::Object(meta.clone()),
        );
        sections.extend(super::file_detail_media::build_readonly_media_sections(
            Some(meta),
        ));
    }
    sections.extend(super::file_detail_sections::build_format_sections(
        &meta_source,
        Some(detail.positive.as_str()),
        raw_meta_json.as_deref(),
        detail.novelai_v4.as_ref(),
    ));
    if !sections.is_empty() {
        set(&mut result, "sections", Value::Array(sections));
    }
    if let Some(animated) = super::file_detail_media::detect_animated(&path) {
        set(&mut result, "is_animated", json!(animated));
    }

    if let Some(v) = has_sweep {
        set(&mut result, "has_sweep", json!(v));
    }
    if let Some(lang) = prompt_lang {
        set(&mut result, "prompt_lang", json!(lang));
        set(
            &mut result,
            "prompt_lang_confidence",
            json!(prompt_lang_confidence.unwrap_or(0.0)),
        );
    }
    if let Some(nai) = detail.novelai_v4 {
        set(&mut result, "novelai_v4", nai);
    }

    Json(result).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    /// The schema columns this route actually reads. Kept minimal on purpose:
    /// a full genesis would hide which column the handler depends on.
    const SCHEMA: &str = "
        CREATE TABLE files(
          id INTEGER PRIMARY KEY, path TEXT, mtime INTEGER, size INTEGER,
          meta_source TEXT, has_sweep INTEGER, is_deleted INTEGER DEFAULT 0
        );
        CREATE TABLE tags(id INTEGER PRIMARY KEY, tag TEXT NOT NULL, namespace TEXT);
        CREATE TABLE file_tags(
          file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL,
          weight REAL DEFAULT 1.0, source TEXT DEFAULT 'meta'
        );
        CREATE TABLE templates(
          file_id INTEGER PRIMARY KEY, raw_prompt TEXT, raw_negative TEXT,
          format TEXT, raw_meta_json TEXT, model_name TEXT,
          prompt_lang TEXT, prompt_lang_confidence REAL
        );
    ";

    async fn test_state(seed: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(SCHEMA).execute(&pool).await.unwrap();
        if !seed.is_empty() {
            sqlx::raw_sql(seed).execute(&pool).await.unwrap();
        }
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
                    rate_limit_trusted_proxies: HashSet::new(),
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
                    wd_tagger_root: std::path::PathBuf::from("."),
                    clip_model_dir: std::path::PathBuf::from("."),
                },
                // Both pools point at the same in-memory DB, as production
                // points both at the same file.
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    /// A tag whose `namespace` is NULL -- the ordinary case in real data -- must
    /// still reach the payload. Decoding that column as `String` silently
    /// emptied the whole list, so the detail view showed no tags at all while
    /// `/api/files/{id}/tags` (a different pool and decoder) showed them.
    #[tokio::test]
    async fn tags_with_a_null_namespace_are_returned() {
        let state = test_state(
            "INSERT INTO files(id, path, mtime, size, meta_source) \
               VALUES (1, '/lib/a.png', 100, 10, 'a1111_png');
             INSERT INTO tags(id, tag, namespace) VALUES (1, '1girl', NULL), (2, 'ns', 'char');
             INSERT INTO file_tags(file_id, tag_id, weight, source) \
               VALUES (1, 1, 1.0, 'meta'), (1, 2, 0.5, 'manual');",
        )
        .await;

        let response = get_file_detail(State(state), None, Path(1)).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;

        let tags = body["tags"].as_array().expect("tags array");
        assert_eq!(tags.len(), 2, "got {tags:?}");
        assert_eq!(tags[0]["tag"], serde_json::json!("1girl"));
        assert_eq!(tags[0]["namespace"], Value::Null);
        assert_eq!(tags[0]["weight"], serde_json::json!(1.0));
        assert_eq!(tags[0]["source"], serde_json::json!("meta"));
        assert_eq!(tags[1]["namespace"], serde_json::json!("char"));
    }

    /// Python answers a missing id with 404 and `{ok:false, error, code}`;
    /// answering 200 made "no such file" indistinguishable from an empty read.
    #[tokio::test]
    async fn a_missing_file_is_a_404_not_an_empty_200() {
        let state = test_state("").await;
        let response = get_file_detail(State(state), None, Path(999)).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let body = json_body(response).await;
        assert_eq!(
            body,
            serde_json::json!({"ok": false, "error": "Not found", "code": "not_found"})
        );
    }

    /// The envelope Python's `api_result` prepends is part of the contract.
    #[tokio::test]
    async fn a_successful_read_carries_the_python_envelope() {
        let state = test_state(
            "INSERT INTO files(id, path, mtime, size, meta_source) \
               VALUES (1, '/lib/a.png', 100, 10, 'a1111_png');",
        )
        .await;
        let body = json_body(get_file_detail(State(state), None, Path(1)).await).await;
        assert_eq!(body["ok"], serde_json::json!(true));
        assert_eq!(body["error"], Value::Null);
        assert_eq!(body["data"], Value::Null);
        assert_eq!(body["id"], serde_json::json!(1));
    }

    /// Production gives this route a **read-only** pool (`db_read`), and the
    /// database it opens is in `delete` journal mode until a writer converts
    /// it -- which is what a freshly created or freshly seeded database is.
    ///
    /// `connect_readonly` used to request `journal_mode=WAL`, a write, and
    /// SQLite answered `attempt to write a readonly database`. The failure was
    /// silent where it mattered: plain row reads still answered, so the detail
    /// route returned the file with `tags: []` and no error, while
    /// `/api/files/{id}/tags` (which reads through the read-write pool) listed
    /// them. Reverting the `journal_mode` line reproduces the empty list.
    #[tokio::test]
    async fn a_read_only_pool_sees_tags_in_a_non_wal_database() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("detail.db");

        // Default journal mode, exactly as `parity_seed_helper` leaves it
        // (measured: `PRAGMA journal_mode` -> "delete").
        let rw = SqlitePoolOptions::new()
            .connect_with(
                SqliteConnectOptions::from_str(&format!("sqlite:{}", db_path.display()))
                    .unwrap()
                    .create_if_missing(true),
            )
            .await
            .unwrap();
        sqlx::raw_sql(SCHEMA).execute(&rw).await.unwrap();
        sqlx::raw_sql(
            "INSERT INTO files(id, path, mtime, size, meta_source) \
               VALUES (1, '/lib/a.png', 100, 10, 'a1111_png');
             INSERT INTO tags(id, tag, namespace) VALUES (1, '1girl', NULL);
             INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES (1, 1, 1.0, 'meta');",
        )
        .execute(&rw)
        .await
        .unwrap();
        rw.close().await;

        let read_pool = tagdb_core::connect_readonly(db_path.to_str().unwrap())
            .await
            .expect("read-only pool");

        let rows: Vec<(String, Option<String>)> = sqlx::query_as(
            "SELECT t.tag, t.namespace FROM file_tags ft \
             JOIN tags t ON t.id = ft.tag_id WHERE ft.file_id = ?",
        )
        .bind(1_i64)
        .fetch_all(&read_pool)
        .await
        .expect("tag query on the read-only pool");

        assert_eq!(rows.len(), 1, "read-only pool lost the tag rows: {rows:?}");
        assert_eq!(rows[0].0, "1girl");
    }
}
