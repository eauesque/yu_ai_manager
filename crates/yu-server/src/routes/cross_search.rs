use std::{
    collections::{HashMap, HashSet},
    path::{Component, Path, PathBuf},
    process::Command,
    sync::{Arc, OnceLock, RwLock},
};

use axum::{
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    ext_config,
    state::SharedState,
};

const EXT_NAME: &str = "builtin-cross-search";
const ROOTS_KEY: &str = "txt_scan_roots";

pub trait FileLauncher: Send + Sync {
    fn open(&self, path: &Path) -> Result<(), std::io::Error>;
}

struct SystemFileLauncher;

impl FileLauncher for SystemFileLauncher {
    fn open(&self, path: &Path) -> Result<(), std::io::Error> {
        #[cfg(target_os = "windows")]
        let mut command = {
            let mut command = Command::new("explorer.exe");
            command.arg(path);
            command
        };
        #[cfg(target_os = "macos")]
        let mut command = {
            let mut command = Command::new("open");
            command.arg(path);
            command
        };
        #[cfg(all(unix, not(target_os = "macos")))]
        let mut command = {
            let mut command = Command::new("xdg-open");
            command.arg(path);
            command
        };
        command.spawn().map(|_| ())
    }
}

static FILE_LAUNCHER: OnceLock<RwLock<Arc<dyn FileLauncher>>> = OnceLock::new();

fn launcher() -> Arc<dyn FileLauncher> {
    FILE_LAUNCHER
        .get_or_init(|| RwLock::new(Arc::new(SystemFileLauncher)))
        .read()
        .expect("launcher lock")
        .clone()
}

#[cfg(test)]
static LAUNCHER_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

/// Swap in a test launcher, holding a process-wide lock until the guard drops.
///
/// `FILE_LAUNCHER` is global, so two tests swapping it concurrently observe each
/// other's mock. The guard serialises the whole swap-use-restore window and puts the
/// previous launcher back even if the test panics.
#[cfg(test)]
struct LauncherGuard {
    previous: Option<Arc<dyn FileLauncher>>,
    _lock: std::sync::MutexGuard<'static, ()>,
}

#[cfg(test)]
impl Drop for LauncherGuard {
    fn drop(&mut self) {
        if let Some(previous) = self.previous.take() {
            let lock = FILE_LAUNCHER.get_or_init(|| RwLock::new(Arc::new(SystemFileLauncher)));
            let mut guard = lock.write().unwrap_or_else(|e| e.into_inner());
            *guard = previous;
        }
    }
}

#[cfg(test)]
fn set_launcher_for_test(test_launcher: Arc<dyn FileLauncher>) -> LauncherGuard {
    let _lock = LAUNCHER_TEST_LOCK.lock().unwrap_or_else(|e| e.into_inner());
    let lock = FILE_LAUNCHER.get_or_init(|| RwLock::new(Arc::new(SystemFileLauncher)));
    let mut guard = lock.write().unwrap_or_else(|e| e.into_inner());
    let previous = std::mem::replace(&mut *guard, test_launcher);
    drop(guard);
    LauncherGuard {
        previous: Some(previous),
        _lock,
    }
}

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
        CREATE TABLE IF NOT EXISTS text_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            mtime REAL NOT NULL DEFAULT 0,
            size INTEGER NOT NULL DEFAULT 0,
            title TEXT NOT NULL DEFAULT '',
            content TEXT NOT NULL DEFAULT '',
            is_deleted INTEGER NOT NULL DEFAULT 0,
            indexed_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS idx_text_files_path ON text_files(path);
        CREATE INDEX IF NOT EXISTS idx_text_files_is_deleted ON text_files(is_deleted);
        CREATE VIRTUAL TABLE IF NOT EXISTS text_files_fts
        USING fts5(title, content, content=text_files, content_rowid=id);
        CREATE TRIGGER IF NOT EXISTS text_files_fts_ai
        AFTER INSERT ON text_files BEGIN
            INSERT INTO text_files_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS text_files_fts_au
        AFTER UPDATE ON text_files BEGIN
            INSERT INTO text_files_fts(text_files_fts, rowid, title, content)
            VALUES ('delete', old.id, old.title, old.content);
            INSERT INTO text_files_fts(rowid, title, content)
            VALUES (new.id, new.title, new.content);
        END;
        CREATE TRIGGER IF NOT EXISTS text_files_fts_ad
        AFTER DELETE ON text_files BEGIN
            INSERT INTO text_files_fts(text_files_fts, rowid, title, content)
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

pub async fn search(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let q = params.get("q").map(String::as_str).unwrap_or("").trim();
    if q.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "query is required"})),
        )
            .into_response();
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize cross search tables");
    }
    let limit = int_param(&params, "limit", 50, 1, 200);
    let target_set = params
        .get("target")
        .map(String::as_str)
        .unwrap_or("md,chat,prompt,txt")
        .split(',')
        .map(str::trim)
        .filter(|target| !target.is_empty())
        .collect::<HashSet<_>>();
    let mut results = Vec::new();
    if target_set.contains("md") {
        results.extend(search_md(&state, q, limit).await.unwrap_or_default());
    }
    if target_set.contains("chat") {
        results.extend(search_chat(&state, q, limit).await.unwrap_or_default());
    }
    if target_set.contains("prompt") {
        results.extend(search_prompt(&state, q, limit).await.unwrap_or_default());
    }
    if target_set.contains("txt") {
        results.extend(search_txt(&state, q, limit).await.unwrap_or_default());
    }
    results.sort_by(|a, b| {
        let av = a.get("score").and_then(Value::as_f64).unwrap_or(0.0);
        let bv = b.get("score").and_then(Value::as_f64).unwrap_or(0.0);
        av.partial_cmp(&bv).unwrap_or(std::cmp::Ordering::Equal)
    });
    results.truncate(usize::try_from(limit).unwrap_or(50));
    Json(json!({"results": results, "query": q, "total": results.len()})).into_response()
}

async fn table_exists(state: &SharedState, table: &str) -> Result<bool, sqlx::Error> {
    let count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM sqlite_master WHERE type IN ('table','view') AND name = ?",
    )
    .bind(table)
    .fetch_one(&state.db_read)
    .await?;
    Ok(count > 0)
}

fn is_cjk_query(query: &str) -> bool {
    query.chars().any(|c| {
        matches!(c,
            '\u{2E80}'..='\u{9FFF}'
            | '\u{F900}'..='\u{FAFF}'
            | '\u{AC00}'..='\u{D7AF}'
            | '\u{FF65}'..='\u{FF9F}'
        )
    })
}

fn html_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
}

fn find_ci(haystack: &str, needle_lower: &[char]) -> Option<(usize, usize)> {
    let n = needle_lower.len();
    if n == 0 {
        return None;
    }
    let chars: Vec<(usize, char)> = haystack.char_indices().collect();
    let len = chars.len();
    for i in 0..len.saturating_sub(n - 1) {
        let matches = (0..n).all(|j| {
            chars[i + j]
                .1
                .to_lowercase()
                .eq(std::iter::once(needle_lower[j]))
        });
        if matches {
            let byte_start = chars[i].0;
            let byte_end = if i + n < len {
                chars[i + n].0
            } else {
                haystack.len()
            };
            return Some((byte_start, byte_end));
        }
    }
    None
}

fn highlight_case_insensitive(text: &str, query: &str, max_count: usize) -> String {
    if query.is_empty() {
        return text.to_string();
    }
    let q_chars: Vec<char> = query.to_lowercase().chars().collect();
    let mut result = String::with_capacity(text.len() + query.len() * max_count * 13);
    let mut remaining = text;
    let mut count = 0;
    while count < max_count {
        match find_ci(remaining, &q_chars) {
            None => break,
            Some((byte_start, byte_end)) => {
                result.push_str(&remaining[..byte_start]);
                result.push_str("<mark>");
                result.push_str(&remaining[byte_start..byte_end]);
                result.push_str("</mark>");
                remaining = &remaining[byte_end..];
                count += 1;
            }
        }
    }
    result.push_str(remaining);
    result
}

fn truncate_snippet(snippet: &str, query: &str) -> String {
    let char_count = snippet.chars().count();
    if char_count <= 300 || snippet.contains("<mark>") {
        return snippet.to_string();
    }
    let q_chars: Vec<char> = query.to_lowercase().chars().collect();
    let q_char_len = q_chars.len();
    let chars: Vec<char> = snippet.chars().collect();

    let (start_char, end_char, add_prefix, add_suffix) =
        if let Some((byte_start, _)) = find_ci(snippet, &q_chars) {
            let char_idx = snippet[..byte_start].chars().count();
            let start = char_idx.saturating_sub(100);
            let end = (char_idx + q_char_len + 200).min(char_count);
            (start, end, start > 0, end < char_count)
        } else {
            (0, 300.min(char_count), false, char_count > 300)
        };

    let excerpt: String = chars[start_char..end_char].iter().collect();
    let mut result = String::new();
    if add_prefix {
        result.push_str("...");
    }
    result.push_str(&excerpt);
    if add_suffix {
        result.push_str("...");
    }

    let escaped = html_escape(&result);
    let escaped_q = html_escape(query);
    highlight_case_insensitive(&escaped, &escaped_q, 3)
}

async fn search_md(state: &SharedState, q: &str, limit: i64) -> Result<Vec<Value>, sqlx::Error> {
    if !table_exists(state, "md_files_fts").await? || !table_exists(state, "md_files").await? {
        return Ok(vec![]);
    }
    if is_cjk_query(q) {
        let like_q = format!("%{}%", q);
        let rows = sqlx::query(
            "SELECT m.id, m.title, m.path,
                    m.content AS snippet,
                    0.0 AS score
             FROM md_files m
             WHERE (m.title LIKE $1 OR m.content LIKE $1) AND m.is_deleted = 0
             ORDER BY m.updated_at DESC
             LIMIT $2",
        )
        .bind(&like_q)
        .bind(limit)
        .fetch_all(&state.db_read)
        .await?;
        return Ok(rows
            .iter()
            .map(|row| {
                let snip = row.get::<String, _>("snippet");
                json!({
                    "type": "md",
                    "id": row.get::<i64, _>("id"),
                    "title": row.get::<String, _>("title"),
                    "path": row.get::<String, _>("path"),
                    "snippet": truncate_snippet(&snip, q),
                    "score": row.get::<f64, _>("score"),
                })
            })
            .collect());
    }
    let rows = sqlx::query(
        "SELECT m.id, m.title, m.path,
                snippet(md_files_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet,
                bm25(md_files_fts) AS score
         FROM md_files_fts f JOIN md_files m ON m.id = f.rowid
         WHERE md_files_fts MATCH ? AND m.is_deleted = 0
         ORDER BY score LIMIT ?",
    )
    .bind(q)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await?;
    Ok(rows
        .iter()
        .map(|row| {
            let snip = row.get::<String, _>("snippet");
            json!({
                "type": "md",
                "id": row.get::<i64, _>("id"),
                "title": row.get::<String, _>("title"),
                "path": row.get::<String, _>("path"),
                "snippet": truncate_snippet(&snip, q),
                "score": row.get::<f64, _>("score"),
            })
        })
        .collect())
}

async fn search_chat(state: &SharedState, q: &str, limit: i64) -> Result<Vec<Value>, sqlx::Error> {
    if !table_exists(state, "chat_messages_fts").await? {
        return Ok(vec![]);
    }
    if is_cjk_query(q) {
        let like_q = format!("%{}%", q);
        let rows = sqlx::query(
            "SELECT m.id, m.conversation_id, m.role,
                    m.content AS snippet,
                    0.0 AS score,
                    c.title AS conv_title, c.source AS conv_source
             FROM chat_messages m
             JOIN chat_conversations c ON c.id = m.conversation_id
             WHERE m.content LIKE $1
             ORDER BY m.created_at DESC
             LIMIT $2",
        )
        .bind(&like_q)
        .bind(limit)
        .fetch_all(&state.db_read)
        .await?;
        return Ok(rows
            .iter()
            .map(|row| {
                let snip = row.get::<String, _>("snippet");
                json!({
                    "type": "chat",
                    "id": row.get::<i64, _>("id"),
                    "conversation_id": row.get::<i64, _>("conversation_id"),
                    "role": row.get::<String, _>("role"),
                    "snippet": truncate_snippet(&snip, q),
                    "score": row.get::<f64, _>("score"),
                    "title": row.get::<String, _>("conv_title"),
                    "source": row.get::<String, _>("conv_source"),
                })
            })
            .collect());
    }
    let rows = sqlx::query(
        "SELECT m.id, m.conversation_id, m.role,
                snippet(chat_messages_fts, 0, '<mark>', '</mark>', '...', 40) AS snippet,
                bm25(chat_messages_fts) AS score,
                c.title AS conv_title, c.source AS conv_source
         FROM chat_messages_fts f
         JOIN chat_messages m ON m.id = f.rowid
         JOIN chat_conversations c ON c.id = m.conversation_id
         WHERE chat_messages_fts MATCH ?
         ORDER BY score LIMIT ?",
    )
    .bind(q)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await?;
    Ok(rows
        .iter()
        .map(|row| {
            let snip = row.get::<String, _>("snippet");
            json!({
                "type": "chat",
                "id": row.get::<i64, _>("id"),
                "conversation_id": row.get::<i64, _>("conversation_id"),
                "role": row.get::<String, _>("role"),
                "snippet": truncate_snippet(&snip, q),
                "score": row.get::<f64, _>("score"),
                "title": row.get::<String, _>("conv_title"),
                "source": row.get::<String, _>("conv_source"),
            })
        })
        .collect())
}

async fn search_prompt(
    state: &SharedState,
    q: &str,
    limit: i64,
) -> Result<Vec<Value>, sqlx::Error> {
    if !table_exists(state, "prompt_library_fts").await?
        || !table_exists(state, "prompt_library").await?
    {
        return Ok(vec![]);
    }
    if is_cjk_query(q) {
        let like_q = format!("%{}%", q);
        let rows = sqlx::query(
            "SELECT p.id, p.title,
                    p.content AS snippet,
                    0.0 AS score
             FROM prompt_library p
             WHERE p.title LIKE $1 OR p.content LIKE $1
             ORDER BY p.updated_at DESC
             LIMIT $2",
        )
        .bind(&like_q)
        .bind(limit)
        .fetch_all(&state.db_read)
        .await?;
        return Ok(rows
            .iter()
            .map(|row| {
                let snip = row.get::<String, _>("snippet");
                json!({
                    "type": "prompt",
                    "id": row.get::<i64, _>("id"),
                    "title": row.get::<String, _>("title"),
                    "snippet": truncate_snippet(&snip, q),
                    "score": row.get::<f64, _>("score"),
                })
            })
            .collect());
    }
    let rows = sqlx::query(
        "SELECT p.id, p.title,
                snippet(prompt_library_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet,
                bm25(prompt_library_fts) AS score
         FROM prompt_library_fts f JOIN prompt_library p ON p.id = f.rowid
         WHERE prompt_library_fts MATCH ?
         ORDER BY score LIMIT ?",
    )
    .bind(q)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await?;
    Ok(rows
        .iter()
        .map(|row| {
            let snip = row.get::<String, _>("snippet");
            json!({
                "type": "prompt",
                "id": row.get::<i64, _>("id"),
                "title": row.get::<String, _>("title"),
                "snippet": truncate_snippet(&snip, q),
                "score": row.get::<f64, _>("score"),
            })
        })
        .collect())
}

async fn search_txt(state: &SharedState, q: &str, limit: i64) -> Result<Vec<Value>, sqlx::Error> {
    if !table_exists(state, "text_files_fts").await? || !table_exists(state, "text_files").await? {
        return Ok(vec![]);
    }
    if is_cjk_query(q) {
        let like_q = format!("%{}%", q);
        let rows = sqlx::query(
            "SELECT t.id, t.title, t.path,
                    t.content AS snippet,
                    0.0 AS score
             FROM text_files t
             WHERE (t.title LIKE $1 OR t.content LIKE $1) AND t.is_deleted = 0
             ORDER BY t.indexed_at DESC
             LIMIT $2",
        )
        .bind(&like_q)
        .bind(limit)
        .fetch_all(&state.db_read)
        .await?;
        return Ok(rows
            .iter()
            .map(|row| {
                let snip = row.get::<String, _>("snippet");
                json!({
                    "type": "txt",
                    "id": row.get::<i64, _>("id"),
                    "title": row.get::<String, _>("title"),
                    "path": row.get::<String, _>("path"),
                    "snippet": truncate_snippet(&snip, q),
                    "score": row.get::<f64, _>("score"),
                })
            })
            .collect());
    }
    let rows = sqlx::query(
        "SELECT t.id, t.title, t.path,
                snippet(text_files_fts, 1, '<mark>', '</mark>', '...', 40) AS snippet,
                bm25(text_files_fts) AS score
         FROM text_files_fts f JOIN text_files t ON t.id = f.rowid
         WHERE text_files_fts MATCH ? AND t.is_deleted = 0
         ORDER BY score LIMIT ?",
    )
    .bind(q)
    .bind(limit)
    .fetch_all(&state.db_read)
    .await?;
    Ok(rows
        .iter()
        .map(|row| {
            let snip = row.get::<String, _>("snippet");
            json!({
                "type": "txt",
                "id": row.get::<i64, _>("id"),
                "title": row.get::<String, _>("title"),
                "path": row.get::<String, _>("path"),
                "snippet": truncate_snippet(&snip, q),
                "score": row.get::<f64, _>("score"),
            })
        })
        .collect())
}

pub async fn txt_detail(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize cross search tables");
    }
    let row = match sqlx::query(
        "SELECT id, path, mtime, size, title, content, indexed_at
         FROM text_files WHERE id = ? AND is_deleted = 0",
    )
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(row) => row,
        Err(error) => return internal_error(error, "failed to get text file"),
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
        "indexed_at": row.get::<i64, _>("indexed_at"),
    }))
    .into_response()
}

pub async fn open_file(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(path) = body
        .get("path")
        .and_then(Value::as_str)
        .filter(|v| !v.is_empty())
    else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "path is required"})),
        )
            .into_response();
    };
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize cross search tables");
    }
    let real_path = realpath_lexical(Path::new(path));
    let allowed_roots = match configured_roots(&state) {
        Ok((roots, _)) => roots,
        Err(error) => return internal_error(error, "failed to read cross scan roots"),
    };
    if allowed_roots.is_empty()
        || !allowed_roots
            .iter()
            .any(|root| path_is_under(&real_path, root))
    {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({"error": "path is not within allowed scan roots"})),
        )
            .into_response();
    }
    if !real_path.exists() {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "file not found"})),
        )
            .into_response();
    }
    let db_path = match sqlx::query_scalar::<_, String>(
        "SELECT path FROM text_files WHERE path = ? AND is_deleted = 0",
    )
    .bind(path)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(Some(path)) => path,
        Ok(None) => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"error": "file not found"})),
            )
                .into_response()
        }
        Err(error) => return internal_error(error, "failed to get text path"),
    };
    if !Path::new(&db_path).exists() {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"error": "file not found"})),
        )
            .into_response();
    }
    match launcher().open(Path::new(&db_path)) {
        Ok(()) => Json(json!({"success": true})).into_response(),
        Err(error) => {
            tracing::error!(?error, "failed to open text file");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": "Failed to open file"})),
            )
                .into_response()
        }
    }
}

fn path_is_under(path: &Path, root: &str) -> bool {
    let root_path = realpath_lexical(Path::new(root));
    path == root_path || path.starts_with(&root_path)
}

fn realpath_lexical(path: &Path) -> PathBuf {
    if let Ok(real) = std::fs::canonicalize(path) {
        return real;
    }
    let absolute = if path.is_absolute() {
        path.to_path_buf()
    } else {
        std::env::current_dir()
            .unwrap_or_else(|_| PathBuf::from("."))
            .join(path)
    };
    normalize_components(&absolute)
}

fn normalize_components(path: &Path) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            other => normalized.push(other.as_os_str()),
        }
    }
    normalized
}

fn configured_roots(state: &SharedState) -> Result<(Vec<String>, bool), std::io::Error> {
    let config = ext_config::read_config(&state.config.config_path)?;
    if let Some(custom) =
        ext_config::string_roots(ext_config::extension_value(&config, EXT_NAME, ROOTS_KEY))
    {
        let is_custom = !custom.is_empty();
        if is_custom {
            return Ok((custom, true));
        }
    }
    Ok((ext_config::global_scan_roots(&config), false))
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
        Err(error) => return internal_error(error, "failed to read cross scan roots"),
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
            Json(json!({"error": "roots must be a list"})),
        )
            .into_response();
    };
    let mut seen = HashSet::new();
    let mut clean = Vec::new();
    for root in raw_roots {
        let root = root.as_str().unwrap_or("").trim();
        if root.is_empty() {
            continue;
        }
        let normalized = normpath(root);
        if seen.insert(normalized.clone()) {
            clean.push(normalized);
        }
    }
    let _guard = state.settings_lock.lock().await;
    if let Err(error) = ext_config::save_extension_value(
        &state.config.config_path,
        EXT_NAME,
        ROOTS_KEY,
        json!(clean),
    ) {
        return internal_error(error, "failed to save cross scan roots");
    }
    Json(json!({"ok": true})).into_response()
}

fn normpath(raw: &str) -> String {
    let normalized = normalize_components(Path::new(raw));
    if normalized.as_os_str().is_empty() {
        ".".to_string()
    } else {
        normalized.to_string_lossy().into_owned()
    }
}

pub async fn delete_scan_root(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(idx): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let (mut roots, _) = match configured_roots(&state) {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to read cross scan roots"),
    };
    let Some(idx) = usize::try_from(idx).ok().filter(|idx| *idx < roots.len()) else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "index out of range"})),
        )
            .into_response();
    };
    roots.remove(idx);
    if let Err(error) = ext_config::save_extension_value(
        &state.config.config_path,
        EXT_NAME,
        ROOTS_KEY,
        json!(roots),
    ) {
        return internal_error(error, "failed to save cross scan roots");
    }
    Json(json!({"ok": true})).into_response()
}

pub async fn stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if let Err(error) = ensure_tables(&state).await {
        return internal_error(error, "failed to initialize cross search tables");
    }
    match sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM text_files WHERE is_deleted = 0")
        .fetch_one(&state.db_read)
        .await
    {
        Ok(count) => Json(json!({"txt_count": count})).into_response(),
        Err(error) => internal_error(error, "failed to count text files"),
    }
}

const SCAN_JOB_ID: &str = "cross_search_scan";

pub async fn scan(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    if state.job_manager.is_running(SCAN_JOB_ID) {
        return Json(json!({"started": false, "job_id": SCAN_JOB_ID, "running": true}))
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
        return internal_error(e, "failed to initialize cross-search tables");
    }
    let _cancel = state
        .job_manager
        .start(SCAN_JOB_ID, "Cross-search text scan");
    let state2 = state.clone();
    tokio::spawn(async move {
        let records = tokio::task::spawn_blocking({
            let roots = roots.clone();
            move || -> Vec<(String, f64, i64, String, String)> {
                let mut paths = Vec::new();
                for root in &roots {
                    walk_txt_files(Path::new(root), &mut paths);
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
                        let title = content.lines().next().unwrap_or("").to_string();
                        Some((path, mtime, meta.len() as i64, title, content))
                    })
                    .collect()
            }
        })
        .await
        .unwrap_or_default();

        let total = records.len() as u64;
        state2
            .job_manager
            .update_progress(SCAN_JOB_ID, 0, total, None);
        for (i, (path, mtime, size, title, content)) in records.iter().enumerate() {
            let _ = sqlx::query(
                "INSERT INTO text_files (path, mtime, size, title, content, is_deleted, indexed_at)
                 VALUES (?, ?, ?, ?, ?, 0, unixepoch())
                 ON CONFLICT(path) DO UPDATE SET
                     mtime=excluded.mtime, size=excluded.size,
                     title=excluded.title, content=excluded.content,
                     is_deleted=0, indexed_at=unixepoch()
                 WHERE excluded.mtime != text_files.mtime",
            )
            .bind(path)
            .bind(mtime)
            .bind(size)
            .bind(title)
            .bind(content)
            .execute(&state2.db)
            .await;
            state2
                .job_manager
                .update_progress(SCAN_JOB_ID, (i + 1) as u64, total, None);
        }
        state2
            .job_manager
            .finish(SCAN_JOB_ID, Some(json!({"indexed": total})), None);
    });
    Json(json!({"started": true, "job_id": SCAN_JOB_ID})).into_response()
}

fn walk_txt_files(dir: &Path, out: &mut Vec<String>) {
    let Ok(entries) = std::fs::read_dir(dir) else {
        return;
    };
    for entry in entries.flatten() {
        let path = entry.path();
        if path.is_dir() {
            walk_txt_files(&path, out);
        } else if path.extension().and_then(|e| e.to_str()) == Some("txt") {
            if let Some(s) = path.to_str() {
                out.push(s.to_string());
            }
        }
    }
}

pub async fn scan_stop(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let cancelled = state.job_manager.cancel_job(SCAN_JOB_ID);
    Json(json!({"cancelled": cancelled})).into_response()
}

pub async fn scan_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match state.job_manager.get_job(SCAN_JOB_ID) {
        Some(job) => Json(serde_json::to_value(job).unwrap_or_else(|_| json!({}))).into_response(),
        None => Json(json!({"running": false, "job_id": SCAN_JOB_ID})).into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, str::FromStr, sync::Mutex};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    #[derive(Default)]
    struct MockLauncher {
        opened: Mutex<Vec<PathBuf>>,
    }

    impl FileLauncher for MockLauncher {
        fn open(&self, path: &Path) -> Result<(), std::io::Error> {
            self.opened.lock().unwrap().push(path.to_path_buf());
            Ok(())
        }
    }

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
    async fn search_requires_query_error_shape() {
        let dir = tempfile::tempdir().unwrap();
        let state = test_state(dir.path().join("config.json")).await;

        let response = search(State(state), None, Query(HashMap::new())).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            json_body(response).await,
            json!({"error": "query is required"})
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
    async fn open_file_uses_db_record_path_and_ignores_user_path() {
        let dir = tempfile::tempdir().unwrap();
        let file_path = dir.path().join("note.txt");
        std::fs::write(&file_path, "hello").unwrap();
        let config_path = dir.path().join("config.json");
        std::fs::write(
            &config_path,
            json!({"extensions": {"builtin-cross-search": {"txt_scan_roots": [dir.path().to_string_lossy()]}}}).to_string(),
        )
        .unwrap();
        let state = test_state(config_path).await;
        ensure_tables(&state).await.unwrap();
        sqlx::query(
            "INSERT INTO text_files(id, path, mtime, size, title, content, is_deleted, indexed_at)
             VALUES (7, ?, 1, 5, 'note', 'hello', 0, 1)",
        )
        .bind(file_path.to_string_lossy().as_ref())
        .execute(&state.db)
        .await
        .unwrap();
        let mock = Arc::new(MockLauncher::default());
        let _launcher_guard = set_launcher_for_test(mock.clone());

        let response = open_file(
            State(state),
            None,
            Json(json!({"path": file_path.to_string_lossy()})),
        )
        .await;

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(json_body(response).await, json!({"success": true}));
        assert_eq!(mock.opened.lock().unwrap().as_slice(), &[file_path]);
    }

    #[tokio::test]
    async fn open_file_rejects_path_not_in_db_without_launching() {
        let dir = tempfile::tempdir().unwrap();
        let file_path = dir.path().join("not-indexed.txt");
        std::fs::write(&file_path, "hello").unwrap();
        let config_path = dir.path().join("config.json");
        std::fs::write(
            &config_path,
            json!({"extensions": {"builtin-cross-search": {"txt_scan_roots": [dir.path().to_string_lossy()]}}}).to_string(),
        )
        .unwrap();
        let state = test_state(config_path).await;
        ensure_tables(&state).await.unwrap();
        let mock = Arc::new(MockLauncher::default());
        let _launcher_guard = set_launcher_for_test(mock.clone());

        let response = open_file(
            State(state),
            None,
            Json(json!({"path": file_path.to_string_lossy()})),
        )
        .await;

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            json_body(response).await,
            json!({"error": "file not found"})
        );
        assert!(mock.opened.lock().unwrap().is_empty());
    }
}
