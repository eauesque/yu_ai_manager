use std::{
    collections::{HashMap, HashSet},
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::{Path, PathBuf},
};

use axum::{
    body::Body,
    extract::{Extension, Query, State},
    http::{header, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use chrono::Local;
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite, SqlitePool};
use tokio_util::io::ReaderStream;
use zip::{write::SimpleFileOptions, CompressionMethod, ZipArchive, ZipWriter};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const IN_CHUNK_SIZE: usize = 500;
const ARCHIVE_MAX_ENTRY_SIZE: u64 = 512 * 1024 * 1024;
const ARCHIVE_MAX_EXPORT_BYTES: u64 = 2 * 1024 * 1024 * 1024;

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    api_error("internal_server_error", StatusCode::INTERNAL_SERVER_ERROR)
}

fn parse_collection_id(value: Option<&Value>, default_one: bool) -> Option<i64> {
    match value.and_then(Value::as_i64).filter(|id| *id >= 1) {
        Some(id) => Some(id),
        None if default_one => Some(1),
        None => None,
    }
}

fn parse_query_collection_id(params: &HashMap<String, String>) -> Option<i64> {
    params
        .get("collection_id")
        .filter(|v| !v.is_empty())
        .and_then(|v| v.parse::<i64>().ok())
}

fn parse_file_ids(body: &Value) -> Result<Vec<i64>, Response> {
    let Some(ids) = body
        .get("file_ids")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    else {
        return Err(api_error("file_ids list required", StatusCode::BAD_REQUEST));
    };
    Ok(ids.iter().filter_map(Value::as_i64).collect())
}

pub async fn batch_add(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let file_ids = match parse_file_ids(&body) {
        Ok(ids) => ids,
        Err(response) => return response,
    };
    let collection_id = parse_collection_id(body.get("collection_id"), true).unwrap_or(1);
    let added = match batch_insert_favorites(&state.db, &file_ids, collection_id).await {
        Ok(added) => added,
        Err(error) => return internal_error(error, "failed to batch add favorites"),
    };
    Json(json!({"ok": true, "added": added, "already_existed": file_ids.len().saturating_sub(usize::try_from(added).unwrap_or(0))})).into_response()
}

pub async fn batch_remove(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let file_ids = match parse_file_ids(&body) {
        Ok(ids) => ids,
        Err(response) => return response,
    };
    let collection_id = parse_collection_id(body.get("collection_id"), false);
    let removed = match batch_delete_favorites(&state.db, &file_ids, collection_id).await {
        Ok(removed) => removed,
        Err(error) => return internal_error(error, "failed to batch remove favorites"),
    };
    Json(json!({"ok": true, "removed": removed})).into_response()
}

pub async fn images(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let collection_id = parse_query_collection_id(&params);
    let pairs = match favorite_paths(&state.db_read, collection_id).await {
        Ok(pairs) => pairs,
        Err(error) => return internal_error(error, "failed to list favorite images"),
    };
    let images = pairs
        .into_iter()
        .map(|(id, path)| json!({"id": id, "path": path}))
        .collect::<Vec<_>>();
    let total = images.len();
    Json(json!({"ok": true, "images": images, "total": total})).into_response()
}

pub async fn export_zip(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let collection_id = parse_query_collection_id(&params);
    let pairs = match favorite_paths(&state.db_read, collection_id).await {
        Ok(pairs) => pairs,
        Err(error) => return internal_error(error, "failed to list favorite zip paths"),
    };
    let name = match export_zip_filename(&state.db_read, collection_id).await {
        Ok(name) => name,
        Err(error) => return internal_error(error, "failed to build favorites zip filename"),
    };
    match build_zip_file(pairs).await {
        Ok(Some(zip_file)) => {
            let content_length = match zip_file.metadata() {
                Ok(metadata) => metadata.len(),
                Err(error) => return internal_error(error, "failed to stat favorites zip"),
            };
            let stream = ReaderStream::new(tokio::fs::File::from_std(zip_file));
            let mut response = Response::new(Body::from_stream(stream));
            response.headers_mut().insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/zip"),
            );
            response.headers_mut().insert(
                header::CONTENT_DISPOSITION,
                HeaderValue::from_str(&format!("attachment; filename=\"{name}\""))
                    .expect("valid content disposition"),
            );
            response.headers_mut().insert(
                header::CONTENT_LENGTH,
                HeaderValue::from_str(&content_length.to_string()).expect("valid content length"),
            );
            response
        }
        Ok(None) => api_error("No files to export", StatusCode::NOT_FOUND),
        Err(error) => internal_error(error, "failed to build favorites zip"),
    }
}

pub async fn export_folder(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let dest_path = body
        .get("dest_path")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let collection_id = parse_collection_id(body.get("collection_id"), false);
    let result = match export_folder_sync(&state, dest_path, collection_id).await {
        Ok(result) => result,
        Err(error) => return internal_error(error, "failed to export favorites folder"),
    };
    let status = if result.get("ok").and_then(Value::as_bool).unwrap_or(false) {
        StatusCode::OK
    } else {
        StatusCode::BAD_REQUEST
    };
    (status, Json(result)).into_response()
}

async fn batch_insert_favorites(
    pool: &SqlitePool,
    file_ids: &[i64],
    collection_id: i64,
) -> Result<u64, sqlx::Error> {
    if file_ids.is_empty() {
        return Ok(0);
    }
    let mut tx = pool.begin().await?;
    let mut added = 0;
    for file_id in file_ids {
        let result = sqlx::query(
            "INSERT OR IGNORE INTO favorites (file_id, collection_id, added_at) VALUES (?, ?, unixepoch())",
        )
        .bind(file_id)
        .bind(collection_id)
        .execute(&mut *tx)
        .await?;
        added += result.rows_affected();
    }
    tx.commit().await?;
    Ok(added)
}

async fn batch_delete_favorites(
    pool: &SqlitePool,
    file_ids: &[i64],
    collection_id: Option<i64>,
) -> Result<u64, sqlx::Error> {
    if file_ids.is_empty() {
        return Ok(0);
    }
    let mut query = QueryBuilder::<Sqlite>::new("DELETE FROM favorites WHERE file_id IN (");
    let mut separated = query.separated(",");
    for file_id in file_ids {
        separated.push_bind(file_id);
    }
    separated.push_unseparated(")");
    if let Some(collection_id) = collection_id {
        query.push(" AND collection_id=").push_bind(collection_id);
    }
    Ok(query.build().execute(pool).await?.rows_affected())
}

async fn favorite_paths(
    pool: &SqlitePool,
    collection_id: Option<i64>,
) -> Result<Vec<(i64, String)>, sqlx::Error> {
    let rows = if let Some(collection_id) = collection_id {
        sqlx::query(
            "SELECT f.id, f.path FROM favorites fav
             JOIN files f ON f.id=fav.file_id AND f.is_deleted=0
             WHERE fav.collection_id=?
             ORDER BY fav.added_at DESC, fav.file_id DESC",
        )
        .bind(collection_id)
        .fetch_all(pool)
        .await?
    } else {
        sqlx::query(
            "SELECT f.id, f.path, MAX(fav.added_at) AS added_at FROM favorites fav
             JOIN files f ON f.id=fav.file_id AND f.is_deleted=0
             GROUP BY f.id, f.path
             ORDER BY added_at DESC, f.id DESC",
        )
        .fetch_all(pool)
        .await?
    };
    Ok(rows
        .into_iter()
        .map(|row| (row.get::<i64, _>(0), row.get::<String, _>(1)))
        .collect())
}

async fn collection_name(
    pool: &SqlitePool,
    collection_id: Option<i64>,
) -> Result<String, sqlx::Error> {
    let raw = if let Some(collection_id) = collection_id {
        sqlx::query_scalar::<_, Option<String>>("SELECT name FROM collections WHERE id=?")
            .bind(collection_id)
            .fetch_optional(pool)
            .await?
            .flatten()
            .unwrap_or_else(|| format!("collection_{collection_id}"))
    } else {
        "favorites".to_string()
    };
    let clean = raw
        .chars()
        .map(|ch| {
            if ch.is_alphanumeric() || matches!(ch, '_' | '-' | '.' | ' ') {
                ch
            } else {
                '_'
            }
        })
        .collect::<String>()
        .trim_matches('_')
        .trim()
        .to_string();
    Ok(if clean.is_empty() {
        "favorites".to_string()
    } else {
        clean
    })
}

async fn export_zip_filename(
    pool: &SqlitePool,
    collection_id: Option<i64>,
) -> Result<String, sqlx::Error> {
    Ok(format!(
        "{}_{}.zip",
        collection_name(pool, collection_id).await?,
        Local::now().format("%Y%m%d_%H%M%S")
    ))
}

async fn build_zip_file(
    pairs: Vec<(i64, String)>,
) -> Result<Option<File>, Box<dyn std::error::Error + Send + Sync>> {
    if pairs.is_empty() {
        return Ok(None);
    }
    tokio::task::spawn_blocking(move || build_zip_file_sync(pairs))
        .await
        .map_err(|error| {
            std::io::Error::other(format!("favorites zip worker join failed: {error}"))
        })?
}

fn build_zip_file_sync(
    pairs: Vec<(i64, String)>,
) -> Result<Option<File>, Box<dyn std::error::Error + Send + Sync>> {
    let file = tempfile::tempfile()?;
    let mut writer = ZipWriter::new(file);
    let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
    let mut used_names = HashSet::new();
    let mut accumulated = 0_u64;
    let mut count = 0_usize;
    for (_file_id, path) in pairs {
        let Some(entry) = ZipEntrySource::from_path(&path) else {
            continue;
        };
        let size = entry.size();
        if size > ARCHIVE_MAX_ENTRY_SIZE {
            continue;
        }
        if accumulated + size > ARCHIVE_MAX_EXPORT_BYTES {
            break;
        }
        let arcname = unique_arcname(entry.arcname(), &mut used_names);
        if write_entry(&mut writer, options, &arcname, entry).is_ok() {
            accumulated += size;
            count += 1;
        }
    }
    if count == 0 {
        return Ok(None);
    }
    let mut file = writer.finish()?;
    file.seek(SeekFrom::Start(0))?;
    Ok(Some(file))
}

fn unique_arcname(base: &str, used_names: &mut HashSet<String>) -> String {
    let mut arcname = base.to_string();
    let mut counter = 2;
    while used_names.contains(&arcname) {
        let path = Path::new(base);
        let stem = path.file_stem().and_then(|s| s.to_str()).unwrap_or(base);
        let ext = path.extension().and_then(|s| s.to_str()).unwrap_or("");
        arcname = if ext.is_empty() {
            format!("{stem}_{counter}")
        } else {
            format!("{stem}_{counter}.{ext}")
        };
        counter += 1;
    }
    used_names.insert(arcname.clone());
    arcname
}

fn split_archive_path(path: &str) -> Option<(&str, &str)> {
    let lower = path.to_lowercase();
    let mut first: Option<(usize, usize)> = None;
    for ext in [".zip!", ".7z!", ".rar!"] {
        if let Some(idx) = lower.find(ext) {
            if first.is_none_or(|(first_idx, _)| idx < first_idx) {
                first = Some((idx, ext.len()));
            }
        }
    }
    first.map(|(idx, ext_len)| {
        let sep = idx + ext_len - 1;
        (&path[..sep], &path[sep + 1..])
    })
}

enum ZipEntrySource {
    File {
        path: String,
        arcname: String,
        size: u64,
    },
    ZipMember {
        archive_path: String,
        internal_path: String,
        arcname: String,
        size: u64,
    },
}

impl ZipEntrySource {
    fn from_path(path: &str) -> Option<Self> {
        if let Some((archive_path, internal_path)) = split_archive_path(path) {
            if !archive_path.to_lowercase().ends_with(".zip") {
                return None;
            }
            let size = zip_member_size(archive_path, internal_path).ok()?;
            let arcname = Path::new(internal_path)
                .file_name()
                .and_then(|name| name.to_str())
                .unwrap_or(internal_path)
                .to_string();
            return Some(Self::ZipMember {
                archive_path: archive_path.to_string(),
                internal_path: internal_path.to_string(),
                arcname,
                size,
            });
        }
        let metadata = std::fs::metadata(path).ok()?;
        if !metadata.is_file() {
            return None;
        }
        let arcname = Path::new(path)
            .file_name()
            .and_then(|name| name.to_str())
            .unwrap_or(path)
            .to_string();
        Some(Self::File {
            path: path.to_string(),
            arcname,
            size: metadata.len(),
        })
    }

    fn arcname(&self) -> &str {
        match self {
            Self::File { arcname, .. } | Self::ZipMember { arcname, .. } => arcname,
        }
    }

    fn size(&self) -> u64 {
        match self {
            Self::File { size, .. } | Self::ZipMember { size, .. } => *size,
        }
    }
}

fn write_entry(
    writer: &mut ZipWriter<File>,
    options: SimpleFileOptions,
    arcname: &str,
    entry: ZipEntrySource,
) -> Result<(), Box<dyn std::error::Error + Send + Sync>> {
    writer.start_file(arcname, options)?;
    match entry {
        ZipEntrySource::File { path, .. } => {
            std::io::copy(&mut File::open(path)?, writer)?;
        }
        ZipEntrySource::ZipMember {
            archive_path,
            internal_path,
            ..
        } => {
            let mut archive = ZipArchive::new(File::open(archive_path)?)?;
            let resolved = resolve_zip_entry_name(&mut archive, &internal_path)?;
            let mut source = archive.by_name(&resolved)?;
            std::io::copy(&mut source, writer)?;
        }
    }
    Ok(())
}

fn zip_member_size(
    archive_path: &str,
    internal_path: &str,
) -> Result<u64, Box<dyn std::error::Error + Send + Sync>> {
    let mut archive = ZipArchive::new(File::open(archive_path)?)?;
    let resolved = resolve_zip_entry_name(&mut archive, internal_path)?;
    let size = archive.by_name(&resolved)?.size();
    Ok(size)
}

fn resolve_zip_entry_name<R: Read + std::io::Seek>(
    archive: &mut ZipArchive<R>,
    internal_path: &str,
) -> Result<String, Box<dyn std::error::Error + Send + Sync>> {
    if archive.by_name(internal_path).is_ok() {
        return Ok(internal_path.to_string());
    }
    let normalized_target = normalize_zip_name(internal_path);
    for idx in 0..archive.len() {
        let name = archive.by_index(idx)?.name().to_string();
        if normalize_zip_name(&name) == normalized_target {
            return Ok(name);
        }
    }
    Err(format!("entry not found: {internal_path}").into())
}

fn normalize_zip_name(path: &str) -> String {
    path.replace('\\', "/")
        .replace('\0', "")
        .trim_start_matches('/')
        .split('/')
        .filter(|part| !part.is_empty() && *part != "." && *part != "..")
        .collect::<Vec<_>>()
        .join("/")
}

async fn export_folder_sync(
    state: &SharedState,
    dest_path: &str,
    collection_id: Option<i64>,
) -> Result<Value, sqlx::Error> {
    if dest_path.trim().is_empty() {
        return Ok(json!({"ok": false, "error": "dest_path required"}));
    }
    let dest = match std::fs::canonicalize(dest_path).or_else(|_| {
        let path = PathBuf::from(dest_path);
        std::fs::create_dir_all(&path)?;
        std::fs::canonicalize(path)
    }) {
        Ok(path) => path,
        Err(_) => return Ok(json!({"ok": false, "error": "Invalid path"})),
    };
    let allowed = scan_roots(&state.config.app_config);
    if !allowed
        .iter()
        .any(|root| dest == *root || dest.starts_with(root))
    {
        return Ok(
            json!({"ok": false, "error": "dest_path must be within a configured scan root"}),
        );
    }
    let pairs = favorite_paths(&state.db_read, collection_id).await?;
    let dest_clone = dest.clone();
    let result = tokio::task::spawn_blocking(move || create_symlinks(dest_clone, pairs))
        .await
        .map_err(|error| {
            sqlx::Error::Protocol(format!("favorites folder worker join failed: {error}"))
        })?;
    Ok(result)
}

fn scan_roots(config: &Value) -> Vec<PathBuf> {
    config
        .get("scan_roots")
        .and_then(Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|entry| entry.get("path").and_then(Value::as_str))
        .filter_map(|path| std::fs::canonicalize(path).ok())
        .collect()
}

fn create_symlinks(dest: PathBuf, pairs: Vec<(i64, String)>) -> Value {
    let mut created = 0;
    let mut skipped = 0;
    let mut errors = 0;
    for (_fid, path) in pairs {
        if split_archive_path(&path).is_some() {
            skipped += 1;
            continue;
        }
        let src = match std::fs::canonicalize(&path) {
            Ok(path) if path.is_file() => path,
            _ => {
                skipped += 1;
                continue;
            }
        };
        let Some(name) = src.file_name().and_then(|v| v.to_str()) else {
            skipped += 1;
            continue;
        };
        let mut link_path = dest.join(name);
        let base = link_path.clone();
        let mut counter = 2;
        while link_path.exists() {
            let stem = base.file_stem().and_then(|v| v.to_str()).unwrap_or(name);
            let ext = base.extension().and_then(|v| v.to_str()).unwrap_or("");
            link_path = if ext.is_empty() {
                dest.join(format!("{stem}_{counter}"))
            } else {
                dest.join(format!("{stem}_{counter}.{ext}"))
            };
            counter += 1;
        }
        #[cfg(unix)]
        let outcome = std::os::unix::fs::symlink(&src, &link_path);
        #[cfg(not(unix))]
        let outcome = std::fs::hard_link(&src, &link_path);
        match outcome {
            Ok(()) => created += 1,
            Err(_) => errors += 1,
        }
    }
    json!({"ok": true, "created": created, "skipped": skipped, "errors": errors, "dest_path": dest.to_string_lossy()})
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    async fn test_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );
             CREATE TABLE favorites (
               file_id INTEGER NOT NULL,
               collection_id INTEGER NOT NULL DEFAULT 1,
               added_at INTEGER,
               PRIMARY KEY(file_id, collection_id)
             );
             CREATE TABLE collections (
               id INTEGER PRIMARY KEY,
               name TEXT NOT NULL
             );
             INSERT INTO files(id, path, is_deleted) VALUES
               (1, '/tmp/a.png', 0),
               (2, '/tmp/b.png', 0),
               (3, '/tmp/deleted.png', 1);
             INSERT INTO collections(id, name) VALUES (1, 'default'), (2, 'work');",
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
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("config.json"),
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

    #[test]
    fn unique_names_match_python_suffixing() {
        let mut used = HashSet::new();
        assert_eq!(unique_arcname("a.txt", &mut used), "a.txt");
        assert_eq!(unique_arcname("a.txt", &mut used), "a_2.txt");
    }

    #[tokio::test]
    async fn favorites_manager_batch_add_images_and_remove_round_trip() {
        let state = test_state().await;

        let added = json_body(
            batch_add(
                State(Arc::clone(&state)),
                None,
                Json(json!({"file_ids": [1, 2], "collection_id": 2})),
            )
            .await,
        )
        .await;
        assert_eq!(added["ok"], true);
        assert_eq!(added["added"], 2);

        let listed = json_body(
            images(
                State(Arc::clone(&state)),
                None,
                Query(HashMap::from([(
                    "collection_id".to_string(),
                    "2".to_string(),
                )])),
            )
            .await,
        )
        .await;
        assert_eq!(listed["total"], 2);
        assert_eq!(listed["images"][0]["id"], 2);

        let removed = json_body(
            batch_remove(
                State(Arc::clone(&state)),
                None,
                Json(json!({"file_ids": [1], "collection_id": 2})),
            )
            .await,
        )
        .await;
        assert_eq!(removed["removed"], 1);

        let after = json_body(
            images(
                State(state),
                None,
                Query(HashMap::from([(
                    "collection_id".to_string(),
                    "2".to_string(),
                )])),
            )
            .await,
        )
        .await;
        assert_eq!(after["total"], 1);
        assert_eq!(after["images"][0]["id"], 2);
    }
}
