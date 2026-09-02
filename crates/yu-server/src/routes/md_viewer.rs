use std::{
    collections::{HashMap, HashSet},
    path::Path,
};

use axum::{
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    ext_config,
    state::SharedState,
};

const EXT_NAME: &str = "builtin-md-viewer";
const ROOTS_KEY: &str = "md_scan_roots";

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{message}");
    api_error("internal_server_error", StatusCode::INTERNAL_SERVER_ERROR)
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn ensure_tables(state: &SharedState) -> Result<(), sqlx::Error> {
    sqlx::raw_sql(
        "
        CREATE TABLE IF NOT EXISTS md_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            mtime REAL NOT NULL DEFAULT 0,
            size INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            lang TEXT NOT NULL DEFAULT '',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            indexed_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_md_files_path ON md_files(path);
        CREATE INDEX IF NOT EXISTS idx_md_files_is_deleted ON md_files(is_deleted);",
    )
    .execute(&state.db)
    .await?;
    // lang column was added later; existing DBs may not have it
    let _ = sqlx::raw_sql("ALTER TABLE md_files ADD COLUMN lang TEXT NOT NULL DEFAULT ''")
        .execute(&state.db)
        .await;
    sqlx::raw_sql(
        "CREATE INDEX IF NOT EXISTS idx_md_files_lang ON md_files(lang);
        CREATE VIRTUAL TABLE IF NOT EXISTS md_files_fts
        USING fts5(title, content, content=md_files, content_rowid=id);
        CREATE TRIGGER IF NOT EXISTS md_files_fts_ai
        AFTER INSERT ON md_files BEGIN
            INSERT INTO md_files_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS md_files_fts_au
        AFTER UPDATE ON md_files BEGIN
            INSERT INTO md_files_fts(md_files_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO md_files_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS md_files_fts_ad
        AFTER DELETE ON md_files BEGIN
            INSERT INTO md_files_fts(md_files_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
        END;",
    )
    .execute(&state.db)
    .await?;
    Ok(())
}

fn int_param(
    params: &HashMap<String, String>,
    name: &str,
    default: i64,
    min: i64,
    max: i64,
) -> i64 {
    params
        .get(name)
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(default)
        .clamp(min, max)
}

fn meta_from_row(row: &sqlx::sqlite::SqliteRow) -> Value {
    json!({
        "id": row.get::<i64, _>("id"),
        "path": row.get::<String, _>("path"),
        "mtime": row.get::<f64, _>("mtime"),
        "size": row.get::<i64, _>("size"),
        "title": row.get::<String, _>("title"),
        "lang": row.get::<String, _>("lang"),
        "indexed_at": row.get::<i64, _>("indexed_at"),
    })
}

pub async fn files(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize md viewer tables");
    }
    let query = params.get("query").map(String::as_str).unwrap_or("").trim();
    let path_filter = params
        .get("path_filter")
        .map(String::as_str)
        .unwrap_or("")
        .trim();
    let lang_filter = params.get("lang").map(String::as_str).unwrap_or("").trim();
    let sort = params.get("sort").map(String::as_str).unwrap_or("mtime");
    let sort_col = match sort {
        "title" => "title",
        "size" => "size",
        "path" => "path",
        _ => "mtime",
    };
    let order_dir = if params
        .get("order")
        .is_some_and(|order| order.eq_ignore_ascii_case("asc"))
    {
        "ASC"
    } else {
        "DESC"
    };
    let limit = int_param(&params, "limit", 50, 1, 500);
    let offset = int_param(&params, "offset", 0, 0, i64::MAX);

    let rows = if query.is_empty() {
        let mut builder = QueryBuilder::<Sqlite>::new(
            "SELECT id, path, mtime, size, title, lang, indexed_at FROM md_files WHERE is_deleted = 0",
        );
        if !path_filter.is_empty() {
            builder
                .push(" AND path LIKE ")
                .push_bind(format!("%{path_filter}%"));
        }
        if !lang_filter.is_empty() {
            builder.push(" AND lang = ").push_bind(lang_filter);
        }
        builder
            .push(format!(" ORDER BY {sort_col} {order_dir} LIMIT "))
            .push_bind(limit)
            .push(" OFFSET ")
            .push_bind(offset);
        builder.build().fetch_all(&state.db_read).await
    } else {
        let mut builder = QueryBuilder::<Sqlite>::new(
            "SELECT m.id, m.path, m.mtime, m.size, m.title, m.lang, m.indexed_at, bm25(md_files_fts) AS score
             FROM md_files_fts f JOIN md_files m ON m.id = f.rowid
             WHERE md_files_fts MATCH ",
        );
        builder.push_bind(query).push(" AND m.is_deleted = 0");
        if !path_filter.is_empty() {
            builder
                .push(" AND m.path LIKE ")
                .push_bind(format!("%{path_filter}%"));
        }
        if !lang_filter.is_empty() {
            builder.push(" AND m.lang = ").push_bind(lang_filter);
        }
        builder
            .push(" ORDER BY score LIMIT ")
            .push_bind(limit)
            .push(" OFFSET ")
            .push_bind(offset);
        builder.build().fetch_all(&state.db_read).await
    };
    let rows = match rows {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list md files"),
    };
    let files = rows.iter().map(meta_from_row).collect::<Vec<_>>();
    let total = match count_files(&state, query, path_filter, lang_filter).await {
        Ok(total) => total,
        Err(error) => return internal_error(error, "failed to count md files"),
    };
    Json(json!({"files": files, "total": total})).into_response()
}

async fn count_files(
    state: &SharedState,
    query: &str,
    path_filter: &str,
    lang_filter: &str,
) -> Result<i64, sqlx::Error> {
    let mut builder = if query.is_empty() {
        QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM md_files WHERE is_deleted = 0")
    } else {
        let mut builder = QueryBuilder::<Sqlite>::new(
            "SELECT COUNT(*) FROM md_files_fts f JOIN md_files m ON m.id = f.rowid
             WHERE md_files_fts MATCH ",
        );
        builder.push_bind(query).push(" AND m.is_deleted = 0");
        builder
    };
    if !path_filter.is_empty() {
        builder.push(" AND ");
        if query.is_empty() {
            builder.push("path LIKE ");
        } else {
            builder.push("m.path LIKE ");
        }
        builder.push_bind(format!("%{path_filter}%"));
    }
    if !lang_filter.is_empty() {
        builder.push(" AND ");
        if query.is_empty() {
            builder.push("lang = ");
        } else {
            builder.push("m.lang = ");
        }
        builder.push_bind(lang_filter);
    }
    let row = builder.build().fetch_one(&state.db_read).await?;
    Ok(row.get::<i64, _>(0))
}

pub async fn file_detail(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize md viewer tables");
    }
    let row = match sqlx::query(
        "SELECT id, path, mtime, size, title, content, lang, indexed_at
         FROM md_files WHERE id = ? AND is_deleted = 0",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(row) => row,
        Err(error) => return internal_error(error, "failed to get md file"),
    };
    let Some(row) = row else {
        return (StatusCode::NOT_FOUND, Json(json!({"error": "not found"}))).into_response();
    };
    Json(json!({
        "id": row.get::<i64, _>("id"),
        "path": row.get::<String, _>("path"),
        "mtime": row.get::<f64, _>("mtime"),
        "size": row.get::<i64, _>("size"),
        "title": row.get::<String, _>("title"),
        "content": row.get::<String, _>("content"),
        "lang": row.get::<String, _>("lang"),
        "indexed_at": row.get::<i64, _>("indexed_at"),
    }))
    .into_response()
}

pub async fn stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize md viewer tables");
    }
    let row = match sqlx::query(
        "SELECT COUNT(*) AS total_files, COALESCE(SUM(size), 0) AS total_size
         FROM md_files WHERE is_deleted = 0",
    )
    .fetch_one(&state.db_read)
    .await
    {
        Ok(row) => row,
        Err(error) => return internal_error(error, "failed to get md stats"),
    };
    Json(json!({
        "total_files": row.get::<i64, _>("total_files"),
        "total_size": row.get::<i64, _>("total_size"),
    }))
    .into_response()
}

pub async fn languages(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize md viewer tables");
    }
    let rows = match sqlx::query(
        "SELECT lang, COUNT(*) AS count FROM md_files
         WHERE is_deleted = 0 AND lang != ''
         GROUP BY lang ORDER BY count DESC",
    )
    .fetch_all(&state.db_read)
    .await
    {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list md languages"),
    };
    let languages = rows
        .iter()
        .map(|row| json!({"lang": row.get::<String, _>("lang"), "count": row.get::<i64, _>("count")}))
        .collect::<Vec<_>>();
    Json(json!({"languages": languages})).into_response()
}

fn sanitize_user_path(raw: &str) -> String {
    let trimmed = raw.trim();
    if let Some(rest) = trimmed.strip_prefix('~') {
        if let Some(home) = std::env::var_os("HOME") {
            return format!("{}{}", home.to_string_lossy(), rest);
        }
    }
    trimmed.to_string()
}

fn configured_roots(state: &SharedState) -> Result<(Vec<String>, bool), std::io::Error> {
    let config = ext_config::read_config(&state.config.config_path)?;
    if let Some(roots) =
        ext_config::string_roots(ext_config::extension_value(&config, EXT_NAME, ROOTS_KEY))
    {
        return Ok((roots, true));
    }
    let roots = ext_config::global_scan_roots(&config);
    if !roots.is_empty() {
        return Ok((roots, false));
    }
    let docs_dir = state.config.project_root.join("docs");
    if docs_dir.is_dir() {
        return Ok((vec![docs_dir.to_string_lossy().into_owned()], false));
    }
    Ok((vec![], false))
}

pub async fn scan_roots(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let (roots, is_custom) = match configured_roots(&state) {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to read md scan roots"),
    };
    let roots = roots
        .iter()
        .map(|root| json!({"path": root, "exists": Path::new(root).is_dir()}))
        .collect::<Vec<_>>();
    Json(json!({"roots": roots, "is_custom": is_custom})).into_response()
}

pub async fn save_scan_roots(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(raw_roots) = body.get("roots").and_then(Value::as_array) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "roots must be an array"})),
        )
            .into_response();
    };
    let mut seen = HashSet::new();
    let mut clean = Vec::new();
    for root in raw_roots {
        let Some(root) = root.as_str() else {
            continue;
        };
        let path = sanitize_user_path(root);
        if path.is_empty() {
            continue;
        }
        let key = normcase(&path);
        if seen.insert(key) {
            clean.push(path);
        }
    }
    let _guard = state.settings_lock.lock().await;
    if let Err(error) = ext_config::save_extension_value(
        &state.config.config_path,
        EXT_NAME,
        ROOTS_KEY,
        json!(clean),
    ) {
        return internal_error(error, "failed to save md scan roots");
    }
    Json(json!({"ok": true, "roots": clean})).into_response()
}

#[cfg(windows)]
fn normcase(path: &str) -> String {
    path.to_lowercase()
}

#[cfg(not(windows))]
fn normcase(path: &str) -> String {
    path.to_string()
}

pub async fn delete_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(index): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let (mut roots, _) = match configured_roots(&state) {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to read md scan roots"),
    };
    let Some(index) = usize::try_from(index)
        .ok()
        .filter(|index| *index < roots.len())
    else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "index out of range"})),
        )
            .into_response();
    };
    let removed = roots.remove(index);
    if let Err(error) = ext_config::save_extension_value(
        &state.config.config_path,
        EXT_NAME,
        ROOTS_KEY,
        json!(roots),
    ) {
        return internal_error(error, "failed to save md scan roots");
    }
    Json(json!({"ok": true, "removed": removed, "roots": roots})).into_response()
}

const MD_SCAN_JOB_ID: &str = "md_viewer_scan";

pub async fn scan(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if state.job_manager.is_running(MD_SCAN_JOB_ID) {
        return Json(json!({"started": false, "job_id": MD_SCAN_JOB_ID, "running": true}))
            .into_response();
    }
    let roots = match configured_roots(&state) {
        Ok((r, _)) => r,
        Err(e) => return internal_error(e, "failed to read scan roots"),
    };
    if roots.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "no scan roots configured"})),
        )
            .into_response();
    }
    if let Err(e) = ensure_tables(&state).await {
        return internal_error(e, "failed to initialize md-viewer tables");
    }
    let _cancel = state
        .job_manager
        .start(MD_SCAN_JOB_ID, "Markdown file scan");
    let state2 = state.clone();
    tokio::spawn(async move {
        let records = tokio::task::spawn_blocking({
            let roots = roots.clone();
            move || -> Vec<(String, f64, i64, String, String, String)> {
                let mut paths = Vec::new();
                for root in &roots {
                    walk_md_files(Path::new(root), &mut paths);
                }
                paths
                    .into_iter()
                    .filter_map(|path| {
                        let meta = std::fs::metadata(&path).ok()?;
                        let content = std::fs::read_to_string(&path).ok()?;
                        let mtime = meta
                            .modified()
                            .ok()
                            .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                            .map(|d| d.as_secs_f64())
                            .unwrap_or(0.0);
                        let title = content
                            .lines()
                            .find(|l| l.starts_with("# "))
                            .map(|l| l.trim_start_matches('#').trim().to_string())
                            .unwrap_or_default();
                        let lang = path
                            .split('/')
                            .rev()
                            .skip(1)
                            .find(|&s| matches!(s, "ja" | "en" | "zh" | "ko" | "fr" | "de" | "es"))
                            .unwrap_or("")
                            .to_string();
                        Some((path, mtime, meta.len() as i64, title, content, lang))
                    })
                    .collect()
            }
        })
        .await
        .unwrap_or_default();

        let total = records.len() as u64;
        state2
            .job_manager
            .update_progress(MD_SCAN_JOB_ID, 0, total, None);
        for (i, (path, mtime, size, title, content, lang)) in records.iter().enumerate() {
            let _ = sqlx::query(
                "INSERT INTO md_files (path, mtime, size, title, content, lang, is_deleted, indexed_at)
                 VALUES (?, ?, ?, ?, ?, ?, 0, unixepoch())
                 ON CONFLICT(path) DO UPDATE SET
                     mtime=excluded.mtime, size=excluded.size,
                     title=excluded.title, content=excluded.content,
                     lang=excluded.lang, is_deleted=0, indexed_at=unixepoch()
                 WHERE excluded.mtime != md_files.mtime",
            )
            .bind(path)
            .bind(mtime)
            .bind(size)
            .bind(title)
            .bind(content)
            .bind(lang)
            .execute(&state2.db)
            .await;
            state2
                .job_manager
                .update_progress(MD_SCAN_JOB_ID, (i + 1) as u64, total, None);
        }
        state2
            .job_manager
            .finish(MD_SCAN_JOB_ID, Some(json!({"indexed": total})), None);
    });
    Json(json!({"started": true, "job_id": MD_SCAN_JOB_ID})).into_response()
}

fn walk_md_files(dir: &Path, out: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            walk_md_files(&path, out);
        } else {
            let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
            if matches!(ext, "md" | "mdx") {
                if let Some(s) = path.to_str() {
                    out.push(s.to_string());
                }
            }
        }
    }
}

pub async fn scan_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match state.job_manager.get_job(MD_SCAN_JOB_ID) {
        Some(job) => Json(serde_json::to_value(job).unwrap_or_else(|_| json!({}))).into_response(),
        None => Json(json!({"running": false, "job_id": MD_SCAN_JOB_ID})).into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state(config_path: PathBuf) -> SharedState {
        test_state_with_pin_auth(config_path, false).await
    }

    async fn test_state_with_pin_auth(config_path: PathBuf, pin_auth_enabled: bool) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
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
                    pin_auth_enabled,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path,
                    project_root: PathBuf::from("."),
                    app_config: json!({}),
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

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn save_scan_roots_rejects_non_array_with_python_shape() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().join("config.json")).await;

        let response = save_scan_roots(State(state), None, Json(json!({"roots": "bad"}))).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            json_body(response).await,
            json!({"error": "roots must be an array"})
        );
    }

    #[tokio::test]
    async fn save_scan_roots_requires_admin_scope_when_pin_auth_enabled() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state_with_pin_auth(dir.path().join("config.json"), true).await;
        let auth = Extension(AuthContext {
            reason: "api_key".to_string(),
            scopes: None,
        });

        let response = save_scan_roots(
            State(state),
            Some(auth),
            Json(json!({"roots": ["/tmp/docs"]})),
        )
        .await;

        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );
    }

    #[tokio::test]
    async fn save_and_delete_scan_roots_round_trip_config_json() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().join("config.json")).await;

        let response = save_scan_roots(
            State(Arc::clone(&state)),
            None,
            Json(json!({"roots": [" /tmp/docs ", "/tmp/docs", "/tmp/other"]})),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            json_body(response).await["roots"],
            json!(["/tmp/docs", "/tmp/other"])
        );

        let response = delete_scan_root(State(state), None, AxumPath(0)).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = json_body(response).await;
        assert_eq!(body["removed"], "/tmp/docs");
        assert_eq!(body["roots"], json!(["/tmp/other"]));
    }
}
