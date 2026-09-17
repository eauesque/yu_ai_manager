use std::{
    collections::{HashMap, HashSet},
    fs::File,
    io::{Read, Seek, SeekFrom},
    path::Path,
};

use axum::{
    body::Body,
    extract::{rejection::JsonRejection, State},
    http::{header, HeaderName, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use chrono::Local;
use serde_json::{json, Value};
use sqlx::{QueryBuilder, Row, Sqlite, SqlitePool};
use tokio_util::io::ReaderStream;
use zip::{write::SimpleFileOptions, CompressionMethod, ZipArchive, ZipWriter};

use crate::state::SharedState;

const MAX_IDS: usize = 500;
const IN_CHUNK_SIZE: usize = 500;
const ARCHIVE_MAX_ENTRY_SIZE: u64 = 512 * 1024 * 1024;
const ARCHIVE_MAX_EXPORT_BYTES: u64 = 2 * 1024 * 1024 * 1024;

pub async fn batch_zip(
    State(state): State<SharedState>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    let data = match body {
        Ok(Json(Value::Object(map))) => map,
        _ => return api_error("JSON object required", StatusCode::BAD_REQUEST),
    };
    let Some(file_ids_value) = data.get("file_ids") else {
        return api_error(
            "file_ids (non-empty array) required",
            StatusCode::BAD_REQUEST,
        );
    };
    let Some(file_ids_array) = file_ids_value.as_array() else {
        return api_error(
            "file_ids (non-empty array) required",
            StatusCode::BAD_REQUEST,
        );
    };
    if file_ids_array.is_empty() {
        return api_error(
            "file_ids (non-empty array) required",
            StatusCode::BAD_REQUEST,
        );
    }
    let mut file_ids = Vec::with_capacity(file_ids_array.len());
    for value in file_ids_array {
        match json_int(value) {
            Some(file_id) => file_ids.push(file_id),
            None => return api_error("file_ids must be integers", StatusCode::BAD_REQUEST),
        }
    }
    if file_ids.len() > MAX_IDS {
        return api_error(
            &format!("Too many IDs (max {MAX_IDS})"),
            StatusCode::BAD_REQUEST,
        );
    }

    match has_unsupported_archive_member(&state.db_read, &file_ids).await {
        Ok(true) => return proxy_batch_zip(&state, &file_ids).await,
        Ok(false) => {}
        Err(error) => {
            tracing::error!(?error, "failed to inspect batch zip paths");
            return api_error(
                "Failed to build batch zip",
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    }

    match build_batch_zip_file(&state.db_read, &file_ids).await {
        Ok(Some(zip_file)) => {
            let filename = build_batch_zip_filename();
            let content_length = match zip_file.metadata() {
                Ok(metadata) => metadata.len(),
                Err(error) => {
                    tracing::error!(?error, "failed to stat batch zip");
                    return api_error(
                        "Failed to build batch zip",
                        StatusCode::INTERNAL_SERVER_ERROR,
                    );
                }
            };
            let tokio_file = tokio::fs::File::from_std(zip_file);
            let stream = ReaderStream::new(tokio_file);
            let mut response = Response::new(Body::from_stream(stream));
            response.headers_mut().insert(
                header::CONTENT_TYPE,
                HeaderValue::from_static("application/zip"),
            );
            response.headers_mut().insert(
                header::CONTENT_DISPOSITION,
                HeaderValue::from_str(&format!("attachment; filename=\"{filename}\""))
                    .expect("valid content disposition"),
            );
            response.headers_mut().insert(
                header::CONTENT_LENGTH,
                HeaderValue::from_str(&content_length.to_string()).expect("valid content length"),
            );
            response
        }
        Ok(None) => api_error("No downloadable files found", StatusCode::NOT_FOUND),
        Err(error) => {
            tracing::error!(?error, "failed to build batch zip");
            api_error(
                "Failed to build batch zip",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn json_int(value: &Value) -> Option<i64> {
    match value {
        Value::Number(number) => number
            .as_i64()
            .or_else(|| number.as_u64().and_then(|value| i64::try_from(value).ok()))
            .or_else(|| number.as_f64().map(crate::num::sat_i64)),
        Value::String(text) => text.parse::<i64>().ok(),
        Value::Bool(value) => Some(i64::from(*value)),
        _ => None,
    }
}

fn build_batch_zip_filename() -> String {
    format!("batch_{}.zip", Local::now().format("%Y%m%d_%H%M%S"))
}

async fn has_unsupported_archive_member(
    pool: &SqlitePool,
    file_ids: &[i64],
) -> Result<bool, sqlx::Error> {
    let unique_file_ids = unique_preserve_order(file_ids);
    for chunk in unique_file_ids.chunks(IN_CHUNK_SIZE) {
        let mut builder = QueryBuilder::<Sqlite>::new("SELECT path FROM files WHERE id IN (");
        let mut separated = builder.separated(",");
        for file_id in chunk {
            separated.push_bind(file_id);
        }
        separated.push_unseparated(") AND is_deleted=0");
        for row in builder.build().fetch_all(pool).await? {
            let path: String = row.get("path");
            if let Some((archive_path, _)) = split_archive_path(&path) {
                if !archive_path.to_lowercase().ends_with(".zip") {
                    return Ok(true);
                }
            }
        }
    }
    Ok(false)
}

async fn proxy_batch_zip(state: &SharedState, file_ids: &[i64]) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok": false, "error": "archive_unavailable"})),
        )
            .into_response();
    }
    let url = format!(
        "{}/api/download/batch-zip",
        state.config.python_url.trim_end_matches('/')
    );
    match state
        .python_client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .json(&json!({"file_ids": file_ids}))
        .send()
        .await
    {
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

async fn build_batch_zip_file(
    pool: &SqlitePool,
    file_ids: &[i64],
) -> Result<Option<File>, Box<dyn std::error::Error + Send + Sync>> {
    if file_ids.is_empty() {
        return Ok(None);
    }

    let unique_file_ids = unique_preserve_order(file_ids);
    let mut path_by_id = HashMap::new();
    for chunk in unique_file_ids.chunks(IN_CHUNK_SIZE) {
        let mut builder = QueryBuilder::<Sqlite>::new("SELECT id, path FROM files WHERE id IN (");
        let mut separated = builder.separated(",");
        for file_id in chunk {
            separated.push_bind(file_id);
        }
        separated.push_unseparated(") AND is_deleted=0");
        for row in builder.build().fetch_all(pool).await? {
            path_by_id.insert(row.get::<i64, _>("id"), row.get::<String, _>("path"));
        }
    }

    let result =
        tokio::task::spawn_blocking(move || build_batch_zip_file_sync(unique_file_ids, path_by_id))
            .await
            .map_err(|error| {
                std::io::Error::other(format!("batch zip worker join failed: {error}"))
            })??;
    Ok(result)
}

fn build_batch_zip_file_sync(
    unique_file_ids: Vec<i64>,
    path_by_id: HashMap<i64, String>,
) -> Result<Option<File>, Box<dyn std::error::Error + Send + Sync>> {
    let file = tempfile::tempfile()?;
    let mut writer = ZipWriter::new(file);

    let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
    let mut used_names = HashSet::new();
    let mut count = 0_usize;
    let mut accumulated = 0_u64;

    for file_id in unique_file_ids {
        let Some(path) = path_by_id.get(&file_id) else {
            continue;
        };
        let Some(entry) = ZipEntrySource::from_path(path) else {
            continue;
        };
        let entry_size = entry.size();
        if entry_size > ARCHIVE_MAX_ENTRY_SIZE {
            tracing::warn!(
                path,
                size = entry_size,
                "skipping oversized file in batch zip"
            );
            continue;
        }
        if accumulated + entry_size > ARCHIVE_MAX_EXPORT_BYTES {
            tracing::warn!(accumulated, "batch zip export size limit reached");
            break;
        }

        let arcname = unique_arcname(entry.arcname(), &mut used_names);
        if let Err(error) = write_entry(&mut writer, options, &arcname, entry) {
            tracing::warn!(?error, path, "skipping unreadable batch zip entry");
            continue;
        }
        accumulated += entry_size;
        count += 1;
    }

    if count == 0 {
        return Ok(None);
    }
    let mut file = writer.finish()?;
    file.seek(SeekFrom::Start(0))?;
    Ok(Some(file))
}

fn unique_preserve_order(file_ids: &[i64]) -> Vec<i64> {
    let mut seen = HashSet::new();
    let mut unique = Vec::new();
    for file_id in file_ids {
        if seen.insert(*file_id) {
            unique.push(*file_id);
        }
    }
    unique
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
}

impl ZipEntrySource {
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
            let mut file = File::open(path)?;
            std::io::copy(&mut file, writer)?;
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
    let mut basename_match = None;
    for idx in 0..archive.len() {
        let name = archive.by_index(idx)?.name().to_string();
        if normalize_zip_name(&name) == normalized_target {
            return Ok(name);
        }
        let name_base = Path::new(&normalize_zip_name(&name))
            .file_name()
            .and_then(|value| value.to_str())
            .map(str::to_string);
        let target_base = Path::new(&normalized_target)
            .file_name()
            .and_then(|value| value.to_str());
        if name_base.as_deref() == target_base {
            if basename_match.is_some() {
                basename_match = None;
                break;
            }
            basename_match = Some(name);
        }
    }
    basename_match.ok_or_else(|| format!("entry not found: {internal_path}").into())
}

fn normalize_zip_name(path: &str) -> String {
    let mut value = path.replace('\\', "/").replace('\0', "");
    while value.starts_with("./") {
        value = value[2..].to_string();
    }
    value = value.trim_start_matches('/').to_string();
    value
        .split('/')
        .filter(|part| !part.is_empty() && *part != "..")
        .collect::<Vec<_>>()
        .join("/")
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn unique_names_match_python_suffixing() {
        let mut used = HashSet::new();
        assert_eq!(unique_arcname("a.txt", &mut used), "a.txt");
        assert_eq!(unique_arcname("a.txt", &mut used), "a_2.txt");
        assert_eq!(unique_arcname("a.txt", &mut used), "a_3.txt");
    }

    #[test]
    fn splits_archive_at_first_supported_boundary() {
        assert_eq!(
            split_archive_path("/tmp/a!b.zip!inner.zip!x.png"),
            Some(("/tmp/a!b.zip", "inner.zip!x.png"))
        );
    }
}
