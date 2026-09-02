//! tools_ops.rs — tools page operation handlers (clear-cache, dnd-inbox, register-path, etc.)

use axum::{
    extract::{ConnectInfo, Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};
use std::collections::HashMap;
use std::net::SocketAddr;
use std::path::Path;

use super::tag_normalize::split_normalized_tag;
use super::tools_fs::is_local;
use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::prompt_sim_core::read_config_json;
use crate::state::SharedState;

/// Strips the Windows `\\?\` verbatim path prefix (and `\\?\UNC\` for network
/// shares) that `std::fs::canonicalize` returns. Without this, a file registered
/// here is stored under a different string than the raw path the scanner/watcher
/// write for the same file, so the `files.path` UNIQUE constraint never catches
/// the duplicate and the same file ends up as two rows. No-op on non-Windows.
/// See docs/development/development_docs/WINDOWS_VERBATIM_PATH_PITFALL.md.
#[cfg(windows)]
fn de_verbatim(path: &Path) -> std::path::PathBuf {
    let s = path.to_string_lossy();
    if let Some(rest) = s.strip_prefix(r"\\?\UNC\") {
        std::path::PathBuf::from(format!(r"\\{rest}"))
    } else if let Some(rest) = s.strip_prefix(r"\\?\") {
        std::path::PathBuf::from(rest)
    } else {
        path.to_path_buf()
    }
}

#[cfg(not(windows))]
fn de_verbatim(path: &Path) -> std::path::PathBuf {
    path.to_path_buf()
}

fn admin(s: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(s.config.pin_auth_enabled, auth.map(|e| &e.0))
}

fn unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "unavailable"})),
    )
        .into_response()
}

fn resolve_thumbnail_cache(s: &SharedState) -> std::path::PathBuf {
    // Default: <config.json directory>/thumbnails
    let config_dir = s.config.config_path.parent().unwrap_or(Path::new("."));
    // Check if config.json specifies a cache_dir
    let cfg = read_config_json(s.config.config_path.to_str().unwrap_or(""));
    if let Some(cache_dir) = cfg["cache_dir"].as_str().filter(|s| !s.is_empty()) {
        return std::path::PathBuf::from(cache_dir).join("thumbnails");
    }
    config_dir.join("thumbnails")
}

/// POST /api/tools/clear-cache
pub async fn clear_cache(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }

    let cache_dir = resolve_thumbnail_cache(&s);

    if cache_dir.exists() {
        if let Err(e) = std::fs::remove_dir_all(&cache_dir) {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": e.to_string()})),
            )
                .into_response();
        }
    }
    if let Err(e) = std::fs::create_dir_all(&cache_dir) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": e.to_string()})),
        )
            .into_response();
    }

    let _ = sqlx::query("UPDATE files SET is_thumbnail_cached = 0 WHERE is_thumbnail_cached = 1")
        .execute(&s.db)
        .await;

    Json(json!({"ok": true})).into_response()
}

/// POST /api/tools/rebuild-groups
pub async fn rebuild_groups(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }

    s.groups_index_cache.invalidate();

    match s.groups_index_cache.get(&s.db_read).await {
        Ok(idx) => Json(json!({
            "status": "rebuilt",
            "folders": idx.folders.len(),
            "zips": idx.zips.len(),
            "file_count": idx.file_count,
        }))
        .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// POST /api/tools/compute-hashes
pub async fn compute_hashes(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    if !s.config.python_url.is_empty() {
        let url = format!(
            "{}/api/tools/compute-hashes",
            s.config.python_url.trim_end_matches('/')
        );
        let body_bytes = serde_json::to_vec(&body).unwrap_or_default();
        return match s
            .python_client
            .post(&url)
            .header("Content-Type", "application/json")
            .header("X-Remote-User", "yu-proxy-auth")
            .body(body_bytes)
            .send()
            .await
        {
            Ok(r) => {
                let st = r.status();
                r.bytes().await.map_or_else(
                    |_| StatusCode::BAD_GATEWAY.into_response(),
                    |b| (st, b).into_response(),
                )
            }
            Err(_) => unavailable(),
        };
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({
            "error": "compute-hashes requires Python backend (background job manager)",
            "code": "python_required"
        })),
    )
        .into_response()
}

/// GET /api/dnd-inbox
pub async fn dnd_inbox(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect_info: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    if !is_local(connect_info.as_ref().map(|e| &e.0)) {
        return (StatusCode::FORBIDDEN, Json(json!({"error": "local_only"}))).into_response();
    }

    let cfg = read_config_json(s.config.config_path.to_str().unwrap_or(""));
    let explicit_dir = cfg["drop_inbox_dir"]
        .as_str()
        .map(|s| s.trim().to_string())
        .filter(|s| !s.is_empty());

    let inbox = if let Some(ref dir) = explicit_dir {
        let p = Path::new(dir);
        if p.is_dir() {
            Some(p.to_path_buf())
        } else {
            None
        }
    } else {
        // Default: first scan root if configured
        let scan_roots = cfg["scan_roots"].as_array();
        scan_roots
            .and_then(|roots| {
                roots.iter().find_map(|r| {
                    r.as_str()
                        .or_else(|| r["path"].as_str())
                        .map(std::path::PathBuf::from)
                })
            })
            .filter(|p| p.is_dir())
    };

    match inbox {
        Some(p) => Json(json!({
            "ok": true,
            "inbox": p.to_string_lossy(),
            "explicit": explicit_dir.is_some(),
        }))
        .into_response(),
        None => Json(json!({
            "ok": false,
            "code": "no_inbox",
            "error": "inbox unresolved",
        }))
        .into_response(),
    }
}

/// POST /api/dnd-upload
pub async fn dnd_upload(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    req: axum::extract::Request,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    // ponytail: dnd-upload needs the Python scan pipeline; proxy when available
    if !s.config.python_url.is_empty() {
        let url = format!(
            "{}/api/dnd-upload",
            s.config.python_url.trim_end_matches('/')
        );
        let headers = req.headers().clone();
        let Ok(body) = axum::body::to_bytes(req.into_body(), 500 * 1024 * 1024).await else {
            return (
                StatusCode::PAYLOAD_TOO_LARGE,
                Json(json!({"error": "Upload too large"})),
            )
                .into_response();
        };
        // Forward only application-level headers; skip hop-by-hop and routing headers
        const SKIP: &[&str] = &[
            "host",
            "content-length",
            "transfer-encoding",
            "connection",
            "keep-alive",
            "proxy-connection",
            "te",
            "trailer",
            "upgrade",
        ];
        let mut builder = s.python_client.post(&url).body(body.to_vec());
        for (k, v) in &headers {
            if SKIP.contains(&k.as_str().to_lowercase().as_str()) {
                continue;
            }
            if let Ok(val) = v.to_str() {
                builder = builder.header(k.as_str(), val);
            }
        }
        return match builder.send().await {
            Ok(r) => {
                let st = r.status();
                r.bytes().await.map_or_else(
                    |_| StatusCode::BAD_GATEWAY.into_response(),
                    |b| (st, b).into_response(),
                )
            }
            Err(_) => unavailable(),
        };
    }
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({
            "error": "Drop upload requires Python backend (scan pipeline)",
            "code": "python_required"
        })),
    )
        .into_response()
}

/// POST /api/files/register-path
pub async fn register_path(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }

    let raw_path = body["path"].as_str().unwrap_or("").trim().to_string();
    if raw_path.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "path is required"})),
        )
            .into_response();
    }

    // Canonicalize first — also serves as the existence check
    let canonical = match Path::new(&raw_path).canonicalize() {
        Ok(p) => p,
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": format!("File not found: {raw_path}")})),
            )
                .into_response()
        }
    };

    let meta = canonical.metadata().ok();
    if !meta.as_ref().is_some_and(|m| m.is_file()) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"error": "path is not a file"})),
        )
            .into_response();
    }

    let cfg = read_config_json(s.config.config_path.to_str().unwrap_or(""));
    let scan_roots = crate::ext_config::global_scan_roots(&cfg);
    let canonical_roots: Vec<_> = scan_roots
        .iter()
        .filter_map(|root| Path::new(root).canonicalize().ok())
        .collect();
    if canonical_roots.is_empty() && !scan_roots.is_empty() {
        tracing::warn!("register_path: all scan_roots failed to canonicalize");
    }
    if !canonical_roots
        .iter()
        .any(|root| crate::path_guard::path_is_within(&canonical, root))
    {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "error": "path is not inside any configured scan root",
                "code": "outside_scan_root"
            })),
        )
            .into_response();
    }

    let ext = canonical
        .extension()
        .and_then(|ext| ext.to_str())
        .filter(|ext| !ext.is_empty())
        .map(|ext| format!(".{}", ext.to_ascii_lowercase()));
    if !matches!(
        ext.as_deref(),
        Some(
            ".png"
                | ".jpg"
                | ".jpeg"
                | ".webp"
                | ".gif"
                | ".bmp"
                | ".tiff"
                | ".tif"
                | ".svg"
                | ".mp4"
                | ".webm"
                | ".mov"
                | ".avi"
                | ".mkv"
                | ".m4v"
        )
    ) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "error": format!("unsupported extension: {}", ext.as_deref().unwrap_or("(none)")),
                "code": "unsupported_type"
            })),
        )
            .into_response();
    }

    let verbatim = canonical.to_string_lossy().to_string();
    let canonical = de_verbatim(&canonical).to_string_lossy().to_string();
    let mtime = meta
        .as_ref()
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    let size = meta.map(|m| m.len() as i64).unwrap_or(0);

    // A row may already exist under the pre-fix verbatim form (`\\?\D:\...`)
    // from before de_verbatim() was added above. INSERT OR IGNORE alone would
    // not catch that — it only matches path values byte-for-byte — so this
    // file would silently get a second, de-verbatim'd row. Check both forms
    // first and treat either as "already registered".
    if verbatim != canonical {
        if let Some(existing_id) =
            sqlx::query_scalar::<_, i64>("SELECT id FROM files WHERE path = ?")
                .bind(&verbatim)
                .fetch_optional(&s.db_read)
                .await
                .unwrap_or(None)
        {
            return (
                StatusCode::CONFLICT,
                Json(json!({
                    "error": "already_registered",
                    "id": existing_id,
                })),
            )
                .into_response();
        }
    }

    // INSERT OR IGNORE atomically avoids TOCTOU between a separate SELECT and INSERT
    let result = sqlx::query(
        "INSERT OR IGNORE INTO files (path, mtime, size, scan_error) VALUES (?, ?, ?, NULL)",
    )
    .bind(&canonical)
    .bind(mtime)
    .bind(size)
    .execute(&s.db)
    .await;

    match result {
        Ok(r) if r.rows_affected() == 0 => {
            // Row already existed — look up its id for a useful 409 response
            let existing_id: Option<i64> =
                sqlx::query_scalar("SELECT id FROM files WHERE path = ?")
                    .bind(&canonical)
                    .fetch_optional(&s.db_read)
                    .await
                    .unwrap_or(None);
            (
                StatusCode::CONFLICT,
                Json(json!({
                    "error": "already_registered",
                    "id": existing_id,
                })),
            )
                .into_response()
        }
        Ok(r) => Json(json!({"ok": true, "id": r.last_insert_rowid(), "path": canonical}))
            .into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

/// POST /api/tools/delete-duplicates
pub async fn delete_duplicates(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }

    let groups = match body["groups"].as_array() {
        Some(g) => g,
        None => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "groups is required"})),
            )
                .into_response()
        }
    };
    let mode = body["mode"].as_str().unwrap_or("soft");
    let hard_delete = mode == "hard";

    // Collect scan roots for hard-delete path containment check
    let cfg = read_config_json(s.config.config_path.to_str().unwrap_or(""));
    let scan_roots_raw: Vec<std::path::PathBuf> = cfg["scan_roots"]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|r| {
                    r.as_str()
                        .or_else(|| r["path"].as_str())
                        .map(std::path::PathBuf::from)
                })
                .collect()
        })
        .unwrap_or_default();
    let canonical_roots: Vec<std::path::PathBuf> = scan_roots_raw
        .iter()
        .filter_map(|r| r.canonicalize().ok())
        .collect();
    if canonical_roots.is_empty() && !scan_roots_raw.is_empty() {
        tracing::warn!("delete_duplicates: all scan_roots failed to canonicalize");
    }

    let mut deleted = 0usize;
    let mut errors: Vec<String> = vec![];

    for group in groups {
        let files = match group.as_array() {
            Some(f) => f,
            None => continue,
        };
        // Delete all except the first (keep the first, delete rest)
        for file in files.iter().skip(1) {
            let path_str = file["path"].as_str().unwrap_or("");
            let file_id = file["id"].as_i64();
            if path_str.is_empty() {
                continue;
            }

            if hard_delete {
                // Validate that the file is under a known scan root to prevent path traversal
                let canonical_target = match std::path::Path::new(path_str).canonicalize() {
                    Ok(p) => p,
                    Err(e) => {
                        errors.push(format!("{path_str}: {e}"));
                        continue;
                    }
                };
                let under_root = canonical_roots
                    .iter()
                    .any(|root| canonical_target.starts_with(root));
                if !under_root {
                    errors.push(format!("{path_str}: outside configured scan roots"));
                    continue;
                }
                if let Err(e) = std::fs::remove_file(&canonical_target) {
                    errors.push(format!("{path_str}: {e}"));
                    continue;
                }
            }

            // Logical delete (arch-constraints: db_schema.logical_delete)
            if let Some(id) = file_id {
                let _ = sqlx::query("UPDATE files SET is_deleted=1 WHERE id = ?")
                    .bind(id)
                    .execute(&s.db)
                    .await;
            } else {
                let _ = sqlx::query("UPDATE files SET is_deleted=1 WHERE path = ?")
                    .bind(path_str)
                    .execute(&s.db)
                    .await;
            }
            deleted += 1;
        }
    }

    Json(json!({"deleted": deleted, "errors": errors})).into_response()
}

fn tools_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"error": message}))).into_response()
}

fn hamming_distance_hex(h1: &str, h2: &str) -> i64 {
    match (u64::from_str_radix(h1, 16), u64::from_str_radix(h2, 16)) {
        (Ok(a), Ok(b)) => (a ^ b).count_ones() as i64,
        _ => 999,
    }
}

#[derive(Deserialize)]
pub struct FindSimilarQuery {
    file_id: Option<String>,
    threshold: Option<String>,
}

const FIND_SIMILAR_FETCH_CHUNK: i64 = 1000;

/// GET /api/tools/find-similar
///
/// Port of Python's `core/tools/similar_find.py::find_similar_to`. No scope
/// gate — Python's `get_required_scope` returns None for all GET requests.
pub async fn find_similar(
    State(s): State<SharedState>,
    Query(params): Query<FindSimilarQuery>,
) -> Response {
    let file_id_str = params.file_id.unwrap_or_default();
    if file_id_str.is_empty() {
        return tools_error("file_id required", StatusCode::BAD_REQUEST);
    }
    let file_id: i64 = match file_id_str.parse() {
        Ok(v) => v,
        Err(_) => return tools_error("invalid file_id", StatusCode::BAD_REQUEST),
    };
    let threshold: i64 = params
        .threshold
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(5)
        .clamp(1, 20);

    let target_phash: Option<String> = match sqlx::query_scalar::<_, Option<String>>(
        "SELECT phash FROM files WHERE id=? AND is_deleted=0",
    )
    .bind(file_id)
    .fetch_optional(&s.db_read)
    .await
    {
        Ok(Some(p)) => p,
        Ok(None) => {
            return tools_error(&format!("File {file_id} not found"), StatusCode::NOT_FOUND)
        }
        Err(e) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": e.to_string()})),
            )
                .into_response()
        }
    };

    let Some(target_phash) = target_phash.filter(|p| !p.is_empty()) else {
        return Json(json!({
            "file_id": file_id, "threshold": threshold, "results": [], "count": 0
        }))
        .into_response();
    };

    let max_results: i64 = 50;
    let collect_limit = max_results * 2;
    let mut results: Vec<(i64, String, i64, Option<i64>)> = Vec::new();
    let mut offset: i64 = 0;
    loop {
        let rows: Vec<(i64, String, String, Option<i64>)> = sqlx::query_as(
            "SELECT id, path, phash, mtime FROM files
             WHERE phash IS NOT NULL AND phash != '' AND id != ? AND is_deleted=0
             LIMIT ? OFFSET ?",
        )
        .bind(file_id)
        .bind(FIND_SIMILAR_FETCH_CHUNK)
        .bind(offset)
        .fetch_all(&s.db_read)
        .await
        .unwrap_or_default();

        let got = rows.len() as i64;
        if got == 0 {
            break;
        }
        for (id, path, phash, mtime) in rows {
            let dist = hamming_distance_hex(&target_phash, &phash);
            if dist <= threshold {
                results.push((id, path, dist, mtime));
            }
        }
        offset += got;
        if results.len() as i64 >= collect_limit || got < FIND_SIMILAR_FETCH_CHUNK {
            break;
        }
    }

    results.sort_by_key(|r| r.2);
    results.truncate(usize::try_from(max_results).unwrap_or(50));
    let results_json: Vec<Value> = results
        .into_iter()
        .map(|(id, path, dist, mtime)| {
            json!({"id": id, "path": path, "distance": dist, "mtime": mtime})
        })
        .collect();
    let count = results_json.len();
    Json(json!({
        "file_id": file_id,
        "threshold": threshold,
        "results": results_json,
        "count": count
    }))
    .into_response()
}

#[derive(Deserialize)]
pub struct FindDuplicatesQuery {
    cross_directory: Option<String>,
    method: Option<String>,
    threshold: Option<String>,
}

const DUPLICATES_GROUP_LIMIT: usize = 200;

fn filter_cross_directory_rows(
    rows: Vec<(String, i64, String, String)>,
    cross_directory: bool,
) -> Vec<(String, i64, String, String)> {
    if !cross_directory {
        return rows;
    }
    rows.into_iter()
        .filter(|(_, _, paths, _)| {
            let dirs: std::collections::HashSet<String> = paths
                .split("|||")
                .map(|p| {
                    std::path::Path::new(p)
                        .parent()
                        .map(|d| d.to_string_lossy().to_string())
                        .unwrap_or_default()
                })
                .collect();
            dirs.len() > 1
        })
        .collect()
}

/// Builds groups for the "hash"/"size" methods: `key` is the SQL GROUP BY key
/// (hash string, or size formatted as a string).
fn build_groups_hash_or_size(rows: Vec<(String, i64, String, String)>) -> (Vec<Value>, i64) {
    let mut total = 0i64;
    let groups = rows
        .into_iter()
        .map(|(key, count, paths, ids)| {
            total += count - 1;
            json!({
                "hash": key,
                "count": count,
                "files": paths.split("|||").collect::<Vec<_>>(),
                "ids": ids
                    .split("|||")
                    .filter(|s| !s.is_empty())
                    .filter_map(|s| s.parse::<i64>().ok())
                    .collect::<Vec<_>>(),
            })
        })
        .collect();
    (groups, total)
}

fn is_valid_uint64_hex(s: &str) -> bool {
    s.len() == 16 && u64::from_str_radix(s, 16).is_ok()
}

/// Port of Python's `core/tools/helpers_phash_group.py::find_phash_groups`.
/// `rows` (id, path, phash) must already be capped (Python: LIMIT 10000).
fn find_phash_groups(rows: &[(i64, String, String)], threshold: i64) -> (Vec<Value>, i64) {
    let n = rows.len();
    let valid: Vec<bool> = rows
        .iter()
        .map(|(_, _, p)| is_valid_uint64_hex(p))
        .collect();
    let values: Vec<u64> = rows
        .iter()
        .map(|(_, _, p)| u64::from_str_radix(p, 16).unwrap_or(0))
        .collect();

    let mut parent: Vec<usize> = (0..n).collect();
    fn find(parent: &mut [usize], x: usize) -> usize {
        let mut root = x;
        while parent[root] != root {
            root = parent[root];
        }
        let mut cur = x;
        while parent[cur] != root {
            let next = parent[cur];
            parent[cur] = root;
            cur = next;
        }
        root
    }
    fn union(parent: &mut [usize], a: usize, b: usize) {
        let pa = find(parent, a);
        let pb = find(parent, b);
        if pa != pb {
            parent[pa] = pb;
        }
    }

    let valid_indices: Vec<usize> = (0..n).filter(|&i| valid[i]).collect();

    if threshold >= 64 {
        if let Some(&first) = valid_indices.first() {
            for &idx in &valid_indices[1..] {
                union(&mut parent, first, idx);
            }
        }
    } else {
        for a_pos in 0..valid_indices.len() {
            let i = valid_indices[a_pos];
            for &j in &valid_indices[a_pos + 1..] {
                let dist = (values[i] ^ values[j]).count_ones() as i64;
                if dist <= threshold {
                    union(&mut parent, i, j);
                }
            }
        }
    }

    // Preserve first-seen root order (Python dict insertion order) so the
    // final stable sort's tie-break matches exactly.
    let mut group_order: Vec<usize> = Vec::new();
    let mut group_members: HashMap<usize, Vec<(i64, String)>> = HashMap::new();
    for (idx, (id, path, _phash)) in rows.iter().enumerate().take(n) {
        let root = find(&mut parent, idx);
        group_members
            .entry(root)
            .or_insert_with(|| {
                group_order.push(root);
                Vec::new()
            })
            .push((*id, path.clone()));
    }

    let mut groups: Vec<Value> = Vec::new();
    for root in group_order {
        let members = &group_members[&root];
        if members.len() > 1 {
            groups.push(json!({
                "hash": format!("phash_group_{}", groups.len()),
                "count": members.len(),
                "files": members.iter().map(|(_, p)| p.clone()).collect::<Vec<_>>(),
                "ids": members.iter().map(|(id, _)| *id).collect::<Vec<_>>(),
                "similarity": "perceptual",
            }));
        }
    }
    groups.sort_by_key(|g| -(g["count"].as_i64().unwrap_or(0)));
    let total_duplicates: i64 = groups
        .iter()
        .map(|g| g["count"].as_i64().unwrap_or(0) - 1)
        .sum();
    (groups, total_duplicates)
}

async fn ensure_phash_column(pool: &sqlx::SqlitePool) {
    let has_phash: bool = sqlx::query_scalar(
        "SELECT COUNT(*) > 0 FROM pragma_table_info('files') WHERE name = 'phash'",
    )
    .fetch_one(pool)
    .await
    .unwrap_or(true);
    if !has_phash {
        let _ = sqlx::raw_sql("ALTER TABLE files ADD COLUMN phash TEXT")
            .execute(pool)
            .await;
    }
}

async fn build_hash_stats(pool: &sqlx::SqlitePool) -> Value {
    let total_files: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM files WHERE is_deleted=0")
        .fetch_one(pool)
        .await
        .unwrap_or(0);
    let with_hash: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NOT NULL AND hash != ''",
    )
    .fetch_one(pool)
    .await
    .unwrap_or(0);
    let with_phash: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM files WHERE is_deleted=0 AND phash IS NOT NULL AND phash != ''",
    )
    .fetch_one(pool)
    .await
    .unwrap_or(0);
    json!({"total_files": total_files, "with_hash": with_hash, "with_phash": with_phash})
}

/// GET /api/tools/find-duplicates
///
/// Port of Python's `core/tools/duplicates_find_ops.py::find_duplicates`. No
/// scope gate — Python's `get_required_scope` returns None for all GET requests.
pub async fn find_duplicates_native(
    State(s): State<SharedState>,
    Query(params): Query<FindDuplicatesQuery>,
) -> Response {
    let cross_directory = params
        .cross_directory
        .map(|v| v.eq_ignore_ascii_case("true"))
        .unwrap_or(false);
    let method = params.method.unwrap_or_else(|| "hash".to_string());
    let threshold_str = params.threshold.unwrap_or_else(|| "5".to_string());
    let threshold: i64 = match threshold_str.parse::<i64>() {
        Ok(v) => v,
        Err(_) => {
            return tools_error(
                "Invalid threshold (must be an integer 0-64)",
                StatusCode::BAD_REQUEST,
            )
        }
    };
    if !(0..=64).contains(&threshold) {
        return tools_error("Invalid threshold (must be 0-64)", StatusCode::BAD_REQUEST);
    }

    let (mut groups, mut total_duplicates): (Vec<Value>, i64) = match method.as_str() {
        "hash" => {
            let rows: Vec<(String, i64, String, String)> = sqlx::query_as(
                "SELECT hash, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths, GROUP_CONCAT(id, '|||') as ids
                 FROM files WHERE hash IS NOT NULL AND hash != '' AND is_deleted = 0
                 GROUP BY hash HAVING count > 1 ORDER BY count DESC LIMIT 201",
            )
            .fetch_all(&s.db_read)
            .await
            .unwrap_or_default();
            let rows = filter_cross_directory_rows(rows, cross_directory);
            build_groups_hash_or_size(rows)
        }
        "size" => {
            let rows: Vec<(i64, i64, String, String)> = sqlx::query_as(
                "SELECT size, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths, GROUP_CONCAT(id, '|||') as ids
                 FROM files WHERE is_deleted = 0 AND size > 1024
                 GROUP BY size HAVING count > 1 AND count <= 20 ORDER BY size DESC LIMIT 201",
            )
            .fetch_all(&s.db_read)
            .await
            .unwrap_or_default();
            let rows: Vec<(String, i64, String, String)> = rows
                .into_iter()
                .map(|(sz, c, p, i)| (sz.to_string(), c, p, i))
                .collect();
            let rows = filter_cross_directory_rows(rows, cross_directory);
            build_groups_hash_or_size(rows)
        }
        "phash" => {
            ensure_phash_column(&s.db).await;
            if threshold == 0 {
                let rows: Vec<(String, i64, String, String)> = sqlx::query_as(
                    "SELECT phash, COUNT(*) as count, GROUP_CONCAT(path, '|||') as paths, GROUP_CONCAT(id, '|||') as ids
                     FROM files WHERE phash IS NOT NULL AND phash != '' AND is_deleted = 0
                     GROUP BY phash HAVING count > 1 ORDER BY count DESC LIMIT 201",
                )
                .fetch_all(&s.db_read)
                .await
                .unwrap_or_default();
                let mut total = 0i64;
                let groups = rows
                    .into_iter()
                    .map(|(phash, count, paths, ids)| {
                        total += count - 1;
                        json!({
                            "hash": format!("phash_exact_{phash}"),
                            "count": count,
                            "files": paths.split("|||").collect::<Vec<_>>(),
                            "ids": ids
                                .split("|||")
                                .filter(|s| !s.is_empty())
                                .filter_map(|s| s.parse::<i64>().ok())
                                .collect::<Vec<_>>(),
                            "similarity": "perceptual",
                        })
                    })
                    .collect();
                (groups, total)
            } else {
                let rows: Vec<(i64, String, String)> = sqlx::query_as(
                    "SELECT id, path, phash FROM files
                     WHERE phash IS NOT NULL AND phash != '' AND is_deleted = 0
                     ORDER BY id DESC LIMIT 10000",
                )
                .fetch_all(&s.db_read)
                .await
                .unwrap_or_default();
                find_phash_groups(&rows, threshold)
            }
        }
        _ => return tools_error("Invalid method", StatusCode::BAD_REQUEST),
    };
    let total_groups = groups.len();
    let truncated = total_groups > DUPLICATES_GROUP_LIMIT;
    groups.truncate(DUPLICATES_GROUP_LIMIT);

    let hash_stats = build_hash_stats(&s.db_read).await;

    Json(json!({
        "groups": groups,
        "total_duplicates": total_duplicates,
        "method": method,
        "hash_stats": hash_stats,
        "truncated": truncated,
        "group_limit": DUPLICATES_GROUP_LIMIT,
        "total_groups": total_groups,
    }))
    .into_response()
}

#[derive(Deserialize)]
pub struct NormalizeTagsQuery {
    dry_run: Option<String>,
}

/// GET /api/tools/normalize-tags
///
/// Port of Python's `core/cleanup_core/cleanup_tag_normalize.py::cleanup_normalize_tags`.
/// No scope gate — Python's `get_required_scope` returns None for all GET
/// requests, even though `dry_run=false` (the default!) mutates the DB.
///
/// The extension hook step (`normalize_via_hooks`) is intentionally omitted;
/// see `tag_normalize.rs` module docs.
pub async fn normalize_tags(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    Query(params): Query<NormalizeTagsQuery>,
) -> Response {
    let dry_run = params
        .dry_run
        .map(|v| v.eq_ignore_ascii_case("true"))
        .unwrap_or(false);

    // Security C-case fix: Python's get_required_scope() imposes no scope on
    // GET requests, but dry_run=false (the default!) performs a real DB
    // mutation. Gate the write path with admin scope on both sides -- the
    // read-only dry_run=true preview stays ungated, matching Python's GET
    // semantics.
    if !dry_run {
        if let Some(r) = admin(&s, auth.as_ref()) {
            return r;
        }
    }

    if dry_run {
        let rows: Vec<(String,)> = sqlx::query_as("SELECT DISTINCT tag FROM tags")
            .fetch_all(&s.db_read)
            .await
            .unwrap_or_default();
        let mut changes: Vec<Value> = Vec::new();
        for (tag,) in rows {
            // Python's dry-run preview calls normalize_tag_string directly (not
            // split_normalized_tag), so a tag that splits into multiple parts
            // shows only its unsplit normalized form here.
            let normalized = super::tag_normalize::normalize_tag_string(&tag);
            if tag != normalized {
                changes.push(json!({"before": tag, "after": normalized}));
            }
        }
        let examples: Vec<Value> = changes.iter().take(20).cloned().collect();
        return Json(json!({"changes": changes.len(), "examples": examples})).into_response();
    }

    match run_normalize_tags_write(&s).await {
        Ok(merge_count) => Json(json!({"normalized": merge_count})).into_response(),
        Err(e) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response(),
    }
}

async fn run_normalize_tags_write(s: &SharedState) -> Result<i64, sqlx::Error> {
    let mut tx = s.db.begin().await?;

    // --- split phase ---
    let split_candidates: Vec<(i64, String, Option<String>)> =
        sqlx::query_as("SELECT id, tag, namespace FROM tags")
            .fetch_all(&mut *tx)
            .await?;
    for (tag_id, tag, namespace) in &split_candidates {
        let parts = split_normalized_tag(tag);
        if parts.len() <= 1 {
            continue;
        }
        let namespace = namespace.clone().unwrap_or_default();
        let file_ids: Vec<(i64,)> = sqlx::query_as("SELECT file_id FROM file_tags WHERE tag_id=?")
            .bind(tag_id)
            .fetch_all(&mut *tx)
            .await?;
        for part in &parts {
            if part.is_empty() {
                continue;
            }
            let existing: Option<(i64,)> =
                sqlx::query_as("SELECT id FROM tags WHERE tag=? AND namespace=?")
                    .bind(part)
                    .bind(&namespace)
                    .fetch_optional(&mut *tx)
                    .await?;
            let new_tag_id = if let Some((id,)) = existing {
                id
            } else {
                sqlx::query("INSERT OR IGNORE INTO tags (tag, namespace) VALUES (?, ?)")
                    .bind(part)
                    .bind(&namespace)
                    .execute(&mut *tx)
                    .await?;
                let (id,): (i64,) =
                    sqlx::query_as("SELECT id FROM tags WHERE tag=? AND namespace=?")
                        .bind(part)
                        .bind(&namespace)
                        .fetch_one(&mut *tx)
                        .await?;
                id
            };
            for (file_id,) in &file_ids {
                sqlx::query("INSERT OR IGNORE INTO file_tags (file_id, tag_id) VALUES (?, ?)")
                    .bind(file_id)
                    .bind(new_tag_id)
                    .execute(&mut *tx)
                    .await?;
            }
        }
        sqlx::query("DELETE FROM file_tags WHERE tag_id=?")
            .bind(tag_id)
            .execute(&mut *tx)
            .await?;
        sqlx::query("DELETE FROM tags WHERE id=?")
            .bind(tag_id)
            .execute(&mut *tx)
            .await?;
    }

    // --- merge phase ---
    let mut merge_count: i64 = 0;
    let rows: Vec<(i64, String, Option<String>)> =
        sqlx::query_as("SELECT id, tag, namespace FROM tags")
            .fetch_all(&mut *tx)
            .await?;
    let mut normalize_map: indexmap::IndexMap<(String, String), Vec<(i64, String)>> =
        indexmap::IndexMap::new();
    let mut garbage_ids: Vec<(i64, String)> = Vec::new();
    for (tag_id, tag, namespace) in rows {
        let parts = split_normalized_tag(&tag);
        if parts.is_empty() {
            garbage_ids.push((tag_id, tag));
            continue;
        }
        let normalized = parts[0].clone();
        let key = (normalized, namespace.unwrap_or_default());
        normalize_map.entry(key).or_default().push((tag_id, tag));
    }

    for (tag_id, _tag) in &garbage_ids {
        sqlx::query("DELETE FROM file_tags WHERE tag_id=?")
            .bind(tag_id)
            .execute(&mut *tx)
            .await?;
        sqlx::query("DELETE FROM tags WHERE id=?")
            .bind(tag_id)
            .execute(&mut *tx)
            .await?;
        merge_count += 1;
    }

    for ((normalized_tag, namespace), tag_list) in normalize_map.into_iter() {
        if tag_list.len() <= 1 {
            let (tag_id, original_tag) = &tag_list[0];
            if original_tag != &normalized_tag {
                let existing: Option<(i64,)> =
                    sqlx::query_as("SELECT id FROM tags WHERE tag=? AND namespace=?")
                        .bind(&normalized_tag)
                        .bind(&namespace)
                        .fetch_optional(&mut *tx)
                        .await?;
                if let Some((existing_id,)) = existing {
                    if existing_id != *tag_id {
                        sqlx::query(
                            "UPDATE file_tags SET tag_id=?
                             WHERE tag_id=?
                             AND NOT EXISTS (
                                 SELECT 1 FROM file_tags ft2
                                 WHERE ft2.file_id=file_tags.file_id AND ft2.tag_id=?
                             )",
                        )
                        .bind(existing_id)
                        .bind(tag_id)
                        .bind(existing_id)
                        .execute(&mut *tx)
                        .await?;
                        sqlx::query("DELETE FROM file_tags WHERE tag_id=?")
                            .bind(tag_id)
                            .execute(&mut *tx)
                            .await?;
                        sqlx::query("DELETE FROM tags WHERE id=?")
                            .bind(tag_id)
                            .execute(&mut *tx)
                            .await?;
                        merge_count += 1;
                    }
                } else {
                    sqlx::query("UPDATE tags SET tag=? WHERE id=?")
                        .bind(&normalized_tag)
                        .bind(tag_id)
                        .execute(&mut *tx)
                        .await?;
                    merge_count += 1;
                }
            }
            continue;
        }

        let mut tag_usage: Vec<(i64, String, i64)> = Vec::new();
        for (tag_id, original_tag) in &tag_list {
            let (count,): (i64,) = sqlx::query_as("SELECT COUNT(*) FROM file_tags WHERE tag_id=?")
                .bind(tag_id)
                .fetch_one(&mut *tx)
                .await?;
            tag_usage.push((*tag_id, original_tag.clone(), count));
        }
        tag_usage.sort_by_key(|b| std::cmp::Reverse(b.2));
        let keep_id = tag_usage[0].0;
        let _ = sqlx::query("UPDATE tags SET tag=? WHERE id=?")
            .bind(&normalized_tag)
            .bind(keep_id)
            .execute(&mut *tx)
            .await;

        for (tag_id, _original_tag, _count) in &tag_usage[1..] {
            sqlx::query(
                "UPDATE file_tags SET tag_id=?
                 WHERE tag_id=?
                 AND NOT EXISTS (
                     SELECT 1 FROM file_tags ft2
                     WHERE ft2.file_id=file_tags.file_id AND ft2.tag_id=?
                 )",
            )
            .bind(keep_id)
            .bind(tag_id)
            .bind(keep_id)
            .execute(&mut *tx)
            .await?;
            sqlx::query("DELETE FROM file_tags WHERE tag_id=?")
                .bind(tag_id)
                .execute(&mut *tx)
                .await?;
            sqlx::query("DELETE FROM tags WHERE id=?")
                .bind(tag_id)
                .execute(&mut *tx)
                .await?;
            merge_count += 1;
        }
    }

    // --- orphan cleanup ---
    sqlx::query("DELETE FROM tags WHERE id NOT IN (SELECT DISTINCT tag_id FROM file_tags)")
        .execute(&mut *tx)
        .await?;

    tx.commit().await?;
    Ok(merge_count)
}

/// SSRF guard for user-supplied engine base URLs (ollama/openai_compat).
/// Only http/https schemes are allowed, and the resolved address must not be
/// loopback/private/link-local/unspecified/multicast — this mirrors the
/// `_is_blocked_address` guard in Python's
/// `extensions/builtin_analysis/core_impl/ollama_utils.py`, which the
/// archive-cleanup list-models payload path itself omits.
fn is_blocked_ip(ip: std::net::IpAddr) -> bool {
    // Normalize IPv4-mapped IPv6 (::ffff:a.b.c.d) to plain IPv4 first, so
    // ::ffff:127.0.0.1 etc. hit the v4 loopback/private checks below instead
    // of the v6 branch, which never checks v4 private ranges.
    let ip = match ip {
        std::net::IpAddr::V6(v6) => v6
            .to_ipv4_mapped()
            .map(std::net::IpAddr::V4)
            .unwrap_or(std::net::IpAddr::V6(v6)),
        v4 => v4,
    };
    match ip {
        std::net::IpAddr::V4(v4) => {
            v4.is_loopback()
                || v4.is_private()
                || v4.is_link_local()
                || v4.is_unspecified()
                || v4.is_broadcast()
                || v4.is_multicast()
        }
        std::net::IpAddr::V6(v6) => {
            v6.is_loopback()
                || v6.is_unspecified()
                || v6.is_multicast()
                || (v6.segments()[0] & 0xfe00) == 0xfc00 // fc00::/7 unique local
                || (v6.segments()[0] & 0xffc0) == 0xfe80 // fe80::/10 link-local
        }
    }
}

/// A domain host resolves to a validated address that must be pinned for the
/// actual connection (see `DnsPin` doc below); an IP-literal host needs no
/// pinning since reqwest never re-resolves it.
enum HostCheck {
    IpLiteralOk,
    Pin(String, std::net::SocketAddr),
}

/// Validates a user-supplied engine base URL and, for domain hosts, returns
/// the exact address to pin the real connection to.
///
/// Resolving here and then letting reqwest re-resolve the same hostname at
/// connect time would be DNS-rebinding-bypassable: an attacker's DNS server
/// can answer with a public IP for this check, then answer with a
/// loopback/private IP moments later when reqwest itself resolves the host
/// to actually connect — the two lookups are independent, so validating one
/// doesn't constrain the other. Instead, resolve exactly once here, validate
/// that address, and have the caller pin the connection to it via
/// `ClientBuilder::resolve()` so no second, unvalidated DNS lookup ever
/// happens for this request.
async fn validate_public_http_url(raw: &str) -> Result<HostCheck, &'static str> {
    let parsed = reqwest::Url::parse(raw).map_err(|_| "Invalid URL")?;
    if parsed.scheme() != "http" && parsed.scheme() != "https" {
        return Err("Only http/https URLs are allowed");
    }

    // IP-literal hosts (`http://127.0.0.1/`, `http://[::1]/`) are matched
    // directly via url::Host — no DNS lookup involved, so no rebinding risk.
    match parsed.host() {
        Some(url::Host::Ipv4(v4)) => {
            if is_blocked_ip(std::net::IpAddr::V4(v4)) {
                return Err("Blocked address");
            }
            return Ok(HostCheck::IpLiteralOk);
        }
        Some(url::Host::Ipv6(v6)) => {
            if is_blocked_ip(std::net::IpAddr::V6(v6)) {
                return Err("Blocked address");
            }
            return Ok(HostCheck::IpLiteralOk);
        }
        Some(url::Host::Domain(_)) => {}
        None => return Err("No hostname specified"),
    }

    let host = parsed
        .host_str()
        .ok_or("No hostname specified")?
        .to_string();
    let port = parsed.port_or_known_default().unwrap_or(80);

    let addrs: Vec<std::net::SocketAddr> =
        match tokio::net::lookup_host((host.as_str(), port)).await {
            Ok(iter) => iter.collect(),
            // DNS resolution failure: let the actual connection attempt fail
            // naturally rather than blocking here (matches Python's
            // `_is_blocked_address`, which also allows on `socket.gaierror`).
            Err(_) => return Ok(HostCheck::IpLiteralOk),
        };
    let Some(&first) = addrs.first() else {
        return Ok(HostCheck::IpLiteralOk);
    };

    // A hostname can resolve to multiple A/AAAA records; reject if *any* of
    // them is blocked rather than only the one we happen to pin to below —
    // otherwise an attacker could mix one public and one private answer.
    for addr in &addrs {
        if is_blocked_ip(addr.ip()) {
            return Err("Blocked address");
        }
    }
    Ok(HostCheck::Pin(host, first))
}

/// Applies the result of `validate_public_http_url` to a `ClientBuilder`,
/// pinning the connection to the exact validated address for domain hosts.
fn apply_host_check(builder: reqwest::ClientBuilder, check: HostCheck) -> reqwest::ClientBuilder {
    match check {
        HostCheck::IpLiteralOk => builder,
        HostCheck::Pin(host, addr) => builder.resolve(&host, addr),
    }
}

/// POST /api/tools/archive-cleanup/list-models
///
/// Port of Python's `core/tools_api/archive_cleanup_ops.py::list_models_payload`.
/// Python gates this route with `_require_local()` only (no scope check in
/// the route itself); the `admin` gate here matches the fallback rule in
/// `key_scopes.py::get_required_scope` ("unregistered mutation endpoints
/// require admin scope") that already applies to sibling POST tool routes
/// (`compute-hashes`, `delete-duplicates`) in this file.
pub async fn archive_cleanup_list_models(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    connect_info: Option<Extension<ConnectInfo<SocketAddr>>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(r) = admin(&s, auth.as_ref()) {
        return r;
    }
    if !is_local(connect_info.as_ref().map(|e| &e.0)) {
        return tools_error(
            "Archive cleanup list models is only available from localhost",
            StatusCode::FORBIDDEN,
        );
    }

    let engine = body["engine"].as_str().unwrap_or("").trim().to_string();
    let base_url = body["base_url"].as_str().unwrap_or("").trim().to_string();

    match engine.as_str() {
        "ollama" => {
            if base_url.is_empty() {
                return tools_error("base_url is required", StatusCode::BAD_REQUEST);
            }
            let host_check = match validate_public_http_url(&base_url).await {
                Ok(c) => c,
                Err(msg) => return tools_error(msg, StatusCode::BAD_REQUEST),
            };
            let url = format!("{}/api/tags", base_url.trim_end_matches('/'));
            let builder = apply_host_check(
                reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(10))
                    .redirect(reqwest::redirect::Policy::none()),
                host_check,
            );
            let client = builder.build().unwrap_or_default();
            match client
                .get(&url)
                .header("Accept", "application/json")
                .send()
                .await
            {
                Ok(resp) => match resp.json::<Value>().await {
                    Ok(body) => {
                        let names: Vec<Value> = body["models"]
                            .as_array()
                            .cloned()
                            .unwrap_or_default()
                            .into_iter()
                            .filter_map(|m| m.get("name").cloned())
                            .collect();
                        Json(json!({"models": names})).into_response()
                    }
                    Err(e) => {
                        Json(json!({"error": format!("Connection failed: {e}")})).into_response()
                    }
                },
                Err(e) => Json(json!({"error": format!("Connection failed: {e}")})).into_response(),
            }
        }
        "openai_compat" => {
            if base_url.is_empty() {
                return tools_error("base_url is required", StatusCode::BAD_REQUEST);
            }
            let host_check = match validate_public_http_url(&base_url).await {
                Ok(c) => c,
                Err(msg) => return tools_error(msg, StatusCode::BAD_REQUEST),
            };
            let api_key = body["api_key"].as_str().unwrap_or("").trim().to_string();
            let url = format!("{}/v1/models", base_url.trim_end_matches('/'));
            let builder = apply_host_check(
                reqwest::Client::builder()
                    .timeout(std::time::Duration::from_secs(10))
                    .redirect(reqwest::redirect::Policy::none()),
                host_check,
            );
            let client = builder.build().unwrap_or_default();
            let mut req = client.get(&url).header("Accept", "application/json");
            if !api_key.is_empty() {
                req = req.header("Authorization", format!("Bearer {api_key}"));
            }
            match req.send().await {
                Ok(resp) => match resp.json::<Value>().await {
                    Ok(body) => {
                        let ids: Vec<Value> = body["data"]
                            .as_array()
                            .cloned()
                            .unwrap_or_default()
                            .into_iter()
                            .filter_map(|m| m.get("id").cloned())
                            .collect();
                        Json(json!({"models": ids})).into_response()
                    }
                    Err(e) => {
                        Json(json!({"error": format!("Connection failed: {e}")})).into_response()
                    }
                },
                Err(e) => Json(json!({"error": format!("Connection failed: {e}")})).into_response(),
            }
        }
        _ => tools_error(
            &format!("Unsupported engine: {engine}"),
            StatusCode::BAD_REQUEST,
        ),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state() -> SharedState {
        test_state_with_pin_auth(false).await
    }

    async fn test_state_with_pin_auth(pin_auth_enabled: bool) -> SharedState {
        test_state_with_config_path(pin_auth_enabled, PathBuf::from("config.json")).await
    }

    async fn test_state_with_config_path(
        pin_auth_enabled: bool,
        config_path: PathBuf,
    ) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               mtime INTEGER,
               size INTEGER,
               scan_error TEXT,
               hash TEXT,
               phash TEXT,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE tags (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               tag TEXT NOT NULL,
               namespace TEXT,
               UNIQUE(tag, namespace)
             );
             CREATE TABLE file_tags (
               file_id INTEGER NOT NULL,
               tag_id INTEGER NOT NULL,
               UNIQUE(file_id, tag_id)
             );",
        )
        .execute(&pool)
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

    async fn test_state_with_config(config_path: &Path, config: Value) -> SharedState {
        std::fs::write(config_path, serde_json::to_string(&config).unwrap()).unwrap();
        test_state_with_config_path(false, config_path.to_path_buf()).await
    }

    async fn register_test_path(state: SharedState, path: &Path) -> (StatusCode, Value) {
        let response = register_path(State(state), None, Json(json!({"path": path}))).await;
        let status = response.status();
        (status, json_body(response).await)
    }

    #[tokio::test]
    async fn register_path_accepts_scan_root_files_and_uppercase_extensions() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("root");
        std::fs::create_dir(&root).unwrap();
        let file = root.join("inside.jpg");
        let uppercase = root.join("uppercase.JPG");
        std::fs::write(&file, b"test").unwrap();
        std::fs::write(&uppercase, b"test").unwrap();
        let config = dir.path().join("config.json");
        let state = test_state_with_config(&config, json!({"scan_roots": [root]})).await;

        assert_eq!(
            register_test_path(state.clone(), &file).await.0,
            StatusCode::OK
        );
        assert_eq!(
            register_test_path(state, &uppercase).await.0,
            StatusCode::OK
        );
    }

    #[tokio::test]
    async fn register_path_rejects_files_outside_scan_roots() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("root");
        std::fs::create_dir(&root).unwrap();
        let file = dir.path().join("outside.jpg");
        std::fs::write(&file, b"test").unwrap();
        let config = dir.path().join("config.json");
        let state = test_state_with_config(&config, json!({"scan_roots": [root]})).await;

        let (status, body) = register_test_path(state, &file).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "outside_scan_root");
    }

    #[tokio::test]
    async fn register_path_rejects_disabled_scan_roots() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("root");
        std::fs::create_dir(&root).unwrap();
        let file = root.join("inside.jpg");
        std::fs::write(&file, b"test").unwrap();
        let config = dir.path().join("config.json");
        let state = test_state_with_config(
            &config,
            json!({"scan_roots": [{"path": root, "enabled": false}]}),
        )
        .await;

        let (status, body) = register_test_path(state, &file).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "outside_scan_root");
    }

    #[tokio::test]
    async fn register_path_rejects_unsupported_extensions() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("root");
        std::fs::create_dir(&root).unwrap();
        let config = dir.path().join("config.json");
        let state = test_state_with_config(&config, json!({"scan_roots": [root]})).await;

        for name in ["file.txt", "file", "file."] {
            let file = root.join(name);
            std::fs::write(&file, b"test").unwrap();
            let (status, body) = register_test_path(state.clone(), &file).await;
            assert_eq!(status, StatusCode::BAD_REQUEST);
            assert_eq!(body["code"], "unsupported_type");
        }
    }

    #[tokio::test]
    async fn register_path_rejects_directories() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("root");
        std::fs::create_dir(&root).unwrap();
        let config = dir.path().join("config.json");
        let state = test_state_with_config(&config, json!({"scan_roots": [root]})).await;

        assert_eq!(
            register_test_path(state, &root).await.0,
            StatusCode::BAD_REQUEST
        );
    }

    #[tokio::test]
    async fn register_path_does_not_match_root_prefixes() {
        let dir = tempfile::tempdir().unwrap();
        let root = dir.path().join("root");
        let rootfoo = dir.path().join("rootfoo");
        std::fs::create_dir(&root).unwrap();
        std::fs::create_dir(&rootfoo).unwrap();
        let file = rootfoo.join("outside.jpg");
        std::fs::write(&file, b"test").unwrap();
        let config = dir.path().join("config.json");
        let state = test_state_with_config(&config, json!({"scan_roots": [root]})).await;

        let (status, body) = register_test_path(state, &file).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["code"], "outside_scan_root");
    }

    #[tokio::test]
    async fn find_similar_requires_file_id() {
        let state = test_state().await;
        let resp = find_similar(
            State(state),
            Query(FindSimilarQuery {
                file_id: None,
                threshold: None,
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn find_similar_rejects_invalid_file_id() {
        let state = test_state().await;
        let resp = find_similar(
            State(state),
            Query(FindSimilarQuery {
                file_id: Some("not-a-number".to_string()),
                threshold: None,
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn find_similar_404_when_file_missing() {
        let state = test_state().await;
        let resp = find_similar(
            State(state),
            Query(FindSimilarQuery {
                file_id: Some("999".to_string()),
                threshold: None,
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn find_similar_returns_matches_sorted_by_distance() {
        let state = test_state().await;
        sqlx::query(
            "INSERT INTO files (id, path, phash) VALUES
               (1, '/a.png', '0000000000000000'),
               (2, '/b.png', '0000000000000001'),
               (3, '/c.png', 'ffffffffffffffff'),
               (4, '/d.png', NULL)",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let resp = find_similar(
            State(Arc::clone(&state)),
            Query(FindSimilarQuery {
                file_id: Some("1".to_string()),
                threshold: Some("2".to_string()),
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = json_body(resp).await;
        assert_eq!(body["count"], 1);
        assert_eq!(body["results"][0]["id"], 2);
    }

    #[tokio::test]
    async fn find_duplicates_rejects_invalid_method() {
        let state = test_state().await;
        let resp = find_duplicates_native(
            State(state),
            Query(FindDuplicatesQuery {
                cross_directory: None,
                method: Some("bogus".to_string()),
                threshold: None,
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn find_duplicates_rejects_out_of_range_threshold() {
        let state = test_state().await;
        let resp = find_duplicates_native(
            State(state),
            Query(FindDuplicatesQuery {
                cross_directory: None,
                method: Some("phash".to_string()),
                threshold: Some("65".to_string()),
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn find_duplicates_groups_by_hash() {
        let state = test_state().await;
        sqlx::query(
            "INSERT INTO files (id, path, hash, size, is_deleted) VALUES
               (1, '/a.png', 'deadbeef', 2000, 0),
               (2, '/b.png', 'deadbeef', 2000, 0),
               (3, '/c.png', 'cafebabe', 2000, 0)",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let resp = find_duplicates_native(
            State(state),
            Query(FindDuplicatesQuery {
                cross_directory: None,
                method: None,
                threshold: None,
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = json_body(resp).await;
        assert_eq!(body["total_groups"], 1);
        assert_eq!(body["groups"][0]["hash"], "deadbeef");
        assert_eq!(body["groups"][0]["count"], 2);
        assert_eq!(body["total_duplicates"], 1);
    }

    #[tokio::test]
    async fn find_duplicates_groups_by_phash_hamming_distance() {
        let state = test_state().await;
        sqlx::query(
            "INSERT INTO files (id, path, phash, is_deleted) VALUES
               (1, '/a.png', '0000000000000000', 0),
               (2, '/b.png', '0000000000000001', 0),
               (3, '/c.png', 'ffffffffffffffff', 0)",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let resp = find_duplicates_native(
            State(state),
            Query(FindDuplicatesQuery {
                cross_directory: None,
                method: Some("phash".to_string()),
                threshold: Some("2".to_string()),
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);
        let body = json_body(resp).await;
        assert_eq!(body["total_groups"], 1);
        assert_eq!(body["groups"][0]["count"], 2);
    }

    #[tokio::test]
    async fn normalize_tags_dry_run_previews_without_mutating() {
        let state = test_state().await;
        sqlx::query("INSERT INTO tags (id, tag, namespace) VALUES (1, '(masterpiece)', NULL)")
            .execute(&state.db)
            .await
            .unwrap();

        let resp = normalize_tags(
            State(Arc::clone(&state)),
            None,
            Query(NormalizeTagsQuery {
                dry_run: Some("true".to_string()),
            }),
        )
        .await;
        let body = json_body(resp).await;
        assert_eq!(body["changes"], 1);
        assert_eq!(body["examples"][0]["before"], "(masterpiece)");
        assert_eq!(body["examples"][0]["after"], "masterpiece");

        // dry_run must not have mutated the tags table
        let (still_there,): (String,) = sqlx::query_as("SELECT tag FROM tags WHERE id=1")
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        assert_eq!(still_there, "(masterpiece)");
    }

    #[tokio::test]
    async fn normalize_tags_merges_duplicate_normalized_tags() {
        let state = test_state().await;
        sqlx::query(
            "INSERT INTO tags (id, tag, namespace) VALUES
               (1, '(masterpiece)', NULL),
               (2, 'masterpiece', NULL);
             INSERT INTO files (id, path) VALUES (1, '/a.png'), (2, '/b.png');
             INSERT INTO file_tags (file_id, tag_id) VALUES (1, 1), (2, 2);",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let resp = normalize_tags(
            State(Arc::clone(&state)),
            None,
            Query(NormalizeTagsQuery { dry_run: None }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);

        let remaining: Vec<(i64, String)> = sqlx::query_as("SELECT id, tag FROM tags")
            .fetch_all(&state.db_read)
            .await
            .unwrap();
        assert_eq!(remaining.len(), 1);
        assert_eq!(remaining[0].1, "masterpiece");

        // both files must now point at the single surviving tag row
        let file_tag_count: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM file_tags WHERE tag_id=?")
                .bind(remaining[0].0)
                .fetch_one(&state.db_read)
                .await
                .unwrap();
        assert_eq!(file_tag_count, 2);
    }

    #[tokio::test]
    async fn normalize_tags_splits_multi_part_tags() {
        let state = test_state().await;
        sqlx::query(
            "INSERT INTO tags (id, tag, namespace) VALUES (1, '(a|b)', NULL);
             INSERT INTO files (id, path) VALUES (1, '/a.png');
             INSERT INTO file_tags (file_id, tag_id) VALUES (1, 1);",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let resp = normalize_tags(
            State(Arc::clone(&state)),
            None,
            Query(NormalizeTagsQuery { dry_run: None }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);

        let mut remaining: Vec<String> = sqlx::query_as::<_, (String,)>("SELECT tag FROM tags")
            .fetch_all(&state.db_read)
            .await
            .unwrap()
            .into_iter()
            .map(|(t,)| t)
            .collect();
        remaining.sort();
        assert_eq!(remaining, vec!["a".to_string(), "b".to_string()]);
    }

    #[tokio::test]
    async fn normalize_tags_removes_orphan_tags() {
        let state = test_state().await;
        // A tag with no file_tags row at all — split/merge phases won't touch
        // it (it normalizes to itself, len(tag_list)==1, no rename needed),
        // but orphan cleanup must remove it.
        sqlx::query("INSERT INTO tags (id, tag, namespace) VALUES (1, 'orphan', NULL)")
            .execute(&state.db)
            .await
            .unwrap();

        let resp = normalize_tags(
            State(Arc::clone(&state)),
            None,
            Query(NormalizeTagsQuery { dry_run: None }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);

        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM tags")
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        assert_eq!(count, 0);
    }

    #[tokio::test]
    async fn normalize_tags_write_path_requires_admin_scope_when_pin_auth_enabled() {
        // Exercises the C-case gate added for the "mutating GET with no
        // scope check" finding: dry_run=true stays ungated (read-only,
        // matching Python's GET semantics), dry_run=false requires admin.
        let state = test_state_with_pin_auth(true).await;

        sqlx::query("INSERT INTO tags (id, tag, namespace) VALUES (1, '(masterpiece)', NULL)")
            .execute(&state.db)
            .await
            .unwrap();

        let resp = normalize_tags(
            State(Arc::clone(&state)),
            None,
            Query(NormalizeTagsQuery {
                dry_run: Some("true".to_string()),
            }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::OK);

        let resp = normalize_tags(
            State(Arc::clone(&state)),
            None,
            Query(NormalizeTagsQuery { dry_run: None }),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);

        // tags table must be untouched by the rejected write attempt
        let (still_there,): (String,) = sqlx::query_as("SELECT tag FROM tags WHERE id=1")
            .fetch_one(&state.db_read)
            .await
            .unwrap();
        assert_eq!(still_there, "(masterpiece)");
    }

    #[tokio::test]
    async fn archive_cleanup_list_models_rejects_non_local_requests() {
        let state = test_state().await;
        let resp =
            archive_cleanup_list_models(State(state), None, None, Json(json!({"engine": "bogus"})))
                .await;
        assert_eq!(resp.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn archive_cleanup_list_models_rejects_unsupported_engine() {
        let state = test_state().await;
        let connect_info = Extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 0))));
        let resp = archive_cleanup_list_models(
            State(state),
            None,
            Some(connect_info),
            Json(json!({"engine": "bogus"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn archive_cleanup_list_models_requires_base_url_for_ollama() {
        let state = test_state().await;
        let connect_info = Extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 0))));
        let resp = archive_cleanup_list_models(
            State(state),
            None,
            Some(connect_info),
            Json(json!({"engine": "ollama"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn archive_cleanup_list_models_rejects_loopback_base_url() {
        let state = test_state().await;
        let connect_info = Extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 0))));
        let resp = archive_cleanup_list_models(
            State(state),
            None,
            Some(connect_info),
            Json(json!({"engine": "ollama", "base_url": "http://127.0.0.1:11434"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn archive_cleanup_list_models_rejects_non_http_scheme() {
        let state = test_state().await;
        let connect_info = Extension(ConnectInfo(SocketAddr::from(([127, 0, 0, 1], 0))));
        let resp = archive_cleanup_list_models(
            State(state),
            None,
            Some(connect_info),
            Json(json!({"engine": "ollama", "base_url": "file:///etc/passwd"})),
        )
        .await;
        assert_eq!(resp.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn validate_public_http_url_blocks_metadata_and_link_local() {
        assert!(validate_public_http_url("http://169.254.169.254/")
            .await
            .is_err());
        assert!(validate_public_http_url("http://10.0.0.5/").await.is_err());
        assert!(validate_public_http_url("http://192.168.1.1/")
            .await
            .is_err());
        assert!(validate_public_http_url("ftp://example.com/")
            .await
            .is_err());
    }

    #[tokio::test]
    async fn validate_public_http_url_blocks_ipv4_mapped_ipv6() {
        // ::ffff:127.0.0.1 must be normalized to 127.0.0.1 and blocked,
        // not fall through the v6 branch (which doesn't check v4 ranges).
        assert!(validate_public_http_url("http://[::ffff:127.0.0.1]/")
            .await
            .is_err());
        assert!(validate_public_http_url("http://[::ffff:169.254.169.254]/")
            .await
            .is_err());
        assert!(validate_public_http_url("http://[::1]/").await.is_err());
    }

    #[tokio::test]
    async fn validate_public_http_url_blocks_and_pins_domain_hosts() {
        // Exercises the *domain name* code path (not an IP literal), which
        // is exactly where DNS-rebinding matters: "localhost" resolves via
        // the OS resolver/hosts file to a loopback address and must be
        // rejected, proving the resolved address (not just literal syntax)
        // is what gets checked.
        assert!(validate_public_http_url("http://localhost/").await.is_err());

        // A domain that resolves to a safe address must return a Pin variant
        // carrying the exact validated address, so the caller can force the
        // real HTTP connection to that same address via ClientBuilder::resolve()
        // instead of letting reqwest re-resolve (and potentially get a
        // different, unvalidated answer).
        match validate_public_http_url("http://example.com/").await {
            Ok(HostCheck::Pin(host, addr)) => {
                assert_eq!(host, "example.com");
                assert!(!is_blocked_ip(addr.ip()));
            }
            // No network access in this environment — acceptable, the
            // rejection-path assertion above already covers the security
            // property; this branch just can't add anything further.
            Err(_) => {}
            Ok(HostCheck::IpLiteralOk) => panic!("example.com is not an IP literal"),
        }
    }

    #[cfg(windows)]
    #[test]
    fn de_verbatim_strips_windows_prefixes() {
        assert_eq!(
            de_verbatim(Path::new(r"\\?\D:\images\a.png")),
            std::path::PathBuf::from(r"D:\images\a.png")
        );
        assert_eq!(
            de_verbatim(Path::new(r"\\?\UNC\server\share\a.png")),
            std::path::PathBuf::from(r"\\server\share\a.png")
        );
        // already-raw paths pass through unchanged
        assert_eq!(
            de_verbatim(Path::new(r"D:\images\a.png")),
            std::path::PathBuf::from(r"D:\images\a.png")
        );
    }
}
