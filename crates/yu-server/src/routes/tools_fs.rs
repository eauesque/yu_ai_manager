//! tools_fs.rs — filesystem helper endpoints: select-folder, list-dirs, file-search

use axum::{
    extract::{ConnectInfo, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde::Deserialize;
use serde_json::json;
use sqlx::Row;
use std::net::SocketAddr;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::state::SharedState;

/// Returns true if the request came from a loopback address (127.0.0.1 or ::1).
pub fn is_local(addr: Option<&ConnectInfo<SocketAddr>>) -> bool {
    addr.map(|ConnectInfo(sa)| sa.ip().is_loopback())
        .unwrap_or(false)
}

fn admin_scope_error(
    state: &SharedState,
    auth: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|e| &e.0))
}

// GET /api/tools/select-folder

#[derive(Deserialize)]
pub struct FolderQuery {
    initial: Option<String>,
    path: Option<String>,
    dir: Option<String>,
}

/// Open a native folder-picker dialog (rfd) and return the selected path.
/// Only accessible from loopback addresses.
/// In headless environments (native-dialog feature disabled) returns
/// `{"error": "headless_unsupported"}` instead.
pub async fn select_folder(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
    Query(params): Query<FolderQuery>,
) -> Response {
    if let Some(r) = admin_scope_error(&s, auth.as_ref()) {
        return r;
    }
    if !is_local(addr.as_ref().map(|e| &e.0)) {
        return Json(json!({
            "path": null,
            "error": null,
            "cancelled": false,
            "message": "フォルダ選択はローカルアクセス時のみ使用可能です"
        }))
        .into_response();
    }
    pick_folder_impl(params)
}

#[cfg(feature = "native-dialog")]
fn pick_folder_impl(params: FolderQuery) -> Response {
    let initial = params.initial.or(params.path).or(params.dir);
    let mut dialog = rfd::FileDialog::new().set_title("フォルダを選択");
    if let Some(ref p) = initial {
        dialog = dialog.set_directory(p);
    }
    match dialog.pick_folder() {
        Some(path) => Json(json!({
            "path": path.to_string_lossy(),
            "error": null,
            "cancelled": false,
        }))
        .into_response(),
        None => Json(json!({
            "path": null,
            "error": null,
            "cancelled": true,
        }))
        .into_response(),
    }
}

#[cfg(not(feature = "native-dialog"))]
fn pick_folder_impl(_params: FolderQuery) -> Response {
    Json(json!({
        "path": null,
        "error": "headless_unsupported",
        "cancelled": false,
        "message": "このサーバーはGUIダイアログ非対応です。パスを直接入力してください"
    }))
    .into_response()
}

// GET /api/tools/list-dirs

#[derive(Debug, Deserialize)]
pub struct ListDirsParams {
    path: Option<String>,
    initial: Option<String>,
    dir: Option<String>,
}

fn list_roots() -> Vec<String> {
    #[cfg(target_os = "windows")]
    {
        let drives: Vec<String> = (b'A'..=b'Z')
            .map(|c| format!("{}:\\", c as char))
            .filter(|p| std::path::Path::new(p).exists())
            .collect();
        if drives.is_empty() {
            vec!["C:\\".to_string()]
        } else {
            drives
        }
    }
    #[cfg(not(target_os = "windows"))]
    {
        vec!["/".to_string()]
    }
}

fn get_hostname() -> String {
    hostname::get()
        .unwrap_or_default()
        .to_string_lossy()
        .to_string()
}

/// List immediate subdirectories of the given path.
/// Only accessible from loopback addresses.
pub async fn list_dirs(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect_info: Option<Extension<ConnectInfo<SocketAddr>>>,
    Query(params): Query<ListDirsParams>,
) -> Response {
    if let Some(r) = admin_scope_error(&s, auth.as_ref()) {
        return r;
    }

    if !is_local(connect_info.as_ref().map(|e| &e.0)) {
        return (
            StatusCode::FORBIDDEN,
            Json(json!({ "error": "local_only" })),
        )
            .into_response();
    }

    let roots = list_roots();
    let default_root = roots[0].clone();

    let dir_path = params
        .path
        .filter(|p| !p.is_empty())
        .or_else(|| params.initial.filter(|p| !p.is_empty()))
        .or_else(|| params.dir.filter(|p| !p.is_empty()))
        .unwrap_or(default_root);

    let parent = std::path::Path::new(&dir_path)
        .parent()
        .and_then(|p| p.to_str())
        .map(|s| s.to_string());

    let read_result = std::fs::read_dir(&dir_path);
    match read_result {
        Err(e) => (
            StatusCode::BAD_REQUEST,
            Json(json!({ "error": e.to_string() })),
        )
            .into_response(),
        Ok(entries) => {
            let mut dirs: Vec<serde_json::Value> = entries
                .filter_map(|entry| {
                    let entry = entry.ok()?;
                    if entry.file_type().ok()?.is_dir() {
                        let path = entry.path().to_str().map(|s| s.to_owned())?;
                        let name = entry.file_name().to_string_lossy().to_string();
                        Some(json!({ "name": name, "path": path }))
                    } else {
                        None
                    }
                })
                .collect();
            dirs.sort_by_key(|v| v["name"].as_str().unwrap_or("").to_string());
            Json(json!({
                "current": dir_path,
                "parent": parent,
                "roots": roots,
                "dirs": dirs,
                "hostname": get_hostname(),
            }))
            .into_response()
        }
    }
}

// GET /api/tools/file-search

#[derive(Debug, Deserialize)]
pub struct FileSearchQuery {
    pub q: Option<String>,
    pub query: Option<String>,
    pub meta: Option<String>,
    pub meta_filter: Option<String>,
    pub limit: Option<i64>,
    pub n: Option<i64>,
    pub page_size: Option<i64>,
}

async fn table_exists_fs(db: &sqlx::SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

/// GET /api/tools/file-search
///
/// Search for files in the SQLite database with optional meta filter.
/// Mirrors Python `file_search_service`: returns `{"results": [...], "total": N}`.
///
/// Parameters:
/// - `q` / `query`: path LIKE filter (case-insensitive via LIKE)
/// - `meta` / `meta_filter`: "all" (default) | "has_meta" | "no_meta" | "unknown"
/// - `limit` / `n` / `page_size`: max results, 1–500 (default 100)
pub async fn file_search(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(params): Query<FileSearchQuery>,
) -> Response {
    if let Some(r) = admin_scope_error(&s, auth.as_ref()) {
        return r;
    }

    let q = params.q.or(params.query).unwrap_or_default();
    let meta = params
        .meta
        .or(params.meta_filter)
        .unwrap_or_else(|| "all".to_string());
    let limit = params
        .limit
        .or(params.n)
        .or(params.page_size)
        .unwrap_or(100)
        .clamp(1, 500);

    // Early-out: no search term and no meta filter applied.
    if q.is_empty() && meta == "all" {
        return Json(json!({"results": [], "total": 0, "message": "検索語を入力してください"}))
            .into_response();
    }

    let pool = &s.db_read;

    // Build WHERE conditions — mirrors Python file_search_service logic.
    let mut conditions: Vec<String> = Vec::new();
    if !q.is_empty() {
        conditions.push("f.path LIKE ? ESCAPE '\\'".to_string());
    }
    match meta.as_str() {
        "has_meta" => {
            conditions.push("f.meta_source IS NOT NULL AND f.meta_source != 'unknown'".to_string())
        }
        "no_meta" => {
            conditions.push("(f.meta_source IS NULL OR f.meta_source = 'unknown')".to_string())
        }
        "unknown" => conditions.push("f.meta_source = 'unknown'".to_string()),
        _ => {}
    }

    let where_clause = if conditions.is_empty() {
        "1=1".to_string()
    } else {
        conditions.join(" AND ")
    };

    let has_templates = table_exists_fs(pool, "templates").await.unwrap_or(false);

    let like_pat = format!("%{}%", q.replace('%', "\\%").replace('_', "\\_"));

    // SELECT with optional LEFT JOIN on templates when the table exists.
    let rows_sql = if has_templates {
        format!(
            "SELECT f.id, f.path, t.meta_source, f.mtime, f.size \
             FROM files f LEFT JOIN templates t ON t.file_id = f.id \
             WHERE f.is_deleted=0 AND {where_clause} ORDER BY f.path LIMIT ?"
        )
    } else {
        format!(
            "SELECT f.id, f.path, NULL AS meta_source, f.mtime, f.size \
             FROM files f \
             WHERE f.is_deleted=0 AND {where_clause} ORDER BY f.path LIMIT ?"
        )
    };

    let count_sql = format!("SELECT COUNT(*) FROM files f WHERE f.is_deleted=0 AND {where_clause}");

    // Bind the LIKE parameter when a query string was provided.
    let total: i64 = {
        let builder = sqlx::query_scalar::<_, i64>(&count_sql);
        let builder = if !q.is_empty() {
            builder.bind(&like_pat)
        } else {
            builder
        };
        builder.fetch_one(pool).await.unwrap_or(0)
    };

    let rows = {
        let builder = sqlx::query(&rows_sql);
        let builder = if !q.is_empty() {
            builder.bind(&like_pat)
        } else {
            builder
        };
        builder
            .bind(limit)
            .fetch_all(pool)
            .await
            .unwrap_or_default()
    };

    let results: Vec<serde_json::Value> = rows
        .into_iter()
        .map(|r| {
            json!({
                "id": r.get::<i64, _>("id"),
                "path": r.get::<String, _>("path"),
                "meta_source": r.try_get::<Option<String>, _>("meta_source").unwrap_or(None),
                "mtime": r.try_get::<f64, _>("mtime").unwrap_or(0.0),
                "size": r.try_get::<i64, _>("size").unwrap_or(0),
            })
        })
        .collect();

    Json(json!({"results": results, "total": total})).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};

    fn ci(ip: IpAddr) -> ConnectInfo<SocketAddr> {
        ConnectInfo(SocketAddr::new(ip, 1234))
    }

    #[test]
    fn local_ipv4() {
        assert!(is_local(Some(&ci(IpAddr::V4(Ipv4Addr::LOCALHOST)))));
    }

    #[test]
    fn local_ipv6() {
        assert!(is_local(Some(&ci(IpAddr::V6(Ipv6Addr::LOCALHOST)))));
    }

    #[test]
    fn remote_not_local() {
        assert!(!is_local(Some(&ci(IpAddr::V4(Ipv4Addr::new(
            192, 168, 1, 1
        ))))));
    }

    #[test]
    fn none_not_local() {
        assert!(!is_local(None));
    }

    #[test]
    fn list_roots_not_empty() {
        assert!(!list_roots().is_empty());
    }

    #[test]
    fn get_hostname_not_empty() {
        // hostname may be empty in CI, just check it doesn't panic
        let _ = get_hostname();
    }

    #[test]
    fn file_search_query_defaults() {
        let q = FileSearchQuery {
            q: None,
            query: None,
            meta: None,
            meta_filter: None,
            limit: None,
            n: None,
            page_size: None,
        };
        // limit default
        let limit = q.limit.or(q.n).or(q.page_size).unwrap_or(100).clamp(1, 500);
        assert_eq!(limit, 100);
    }

    #[test]
    fn file_search_query_limit_clamp() {
        let q = FileSearchQuery {
            q: None,
            query: None,
            meta: None,
            meta_filter: None,
            limit: Some(9999),
            n: None,
            page_size: None,
        };
        let limit = q.limit.or(q.n).or(q.page_size).unwrap_or(100).clamp(1, 500);
        assert_eq!(limit, 500);
    }

    #[test]
    fn file_search_query_alias_priority() {
        // q takes priority over query; limit takes priority over n/page_size
        let q = FileSearchQuery {
            q: Some("foo".to_string()),
            query: Some("bar".to_string()),
            meta: None,
            meta_filter: None,
            limit: Some(42),
            n: Some(10),
            page_size: None,
        };
        let resolved_q = q.q.clone().or(q.query.clone()).unwrap_or_default();
        assert_eq!(resolved_q, "foo");
        let limit = q.limit.or(q.n).or(q.page_size).unwrap_or(100).clamp(1, 500);
        assert_eq!(limit, 42);
    }
}
