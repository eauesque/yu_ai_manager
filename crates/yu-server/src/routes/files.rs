use axum::{
    body::Body,
    extract::{Path, State},
    http::{header, HeaderMap, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use base64::{engine::general_purpose::STANDARD, Engine as _};
use encoding_rs::{BIG5, EUC_JP, EUC_KR, GBK, ISO_2022_JP, SHIFT_JIS};
use font8x8::{UnicodeFonts, BASIC_FONTS};
use pdfium_render::prelude::*;
use serde::Serialize;
use sha2::{Digest, Sha256};
use std::{
    collections::HashMap,
    path::{Path as FsPath, PathBuf},
    sync::{Mutex, OnceLock},
    time::Duration,
};
use tokio::io::{AsyncReadExt, AsyncSeekExt};
use tokio_util::io::ReaderStream;
use unicode_normalization::UnicodeNormalization;

use crate::state::SharedState;

const CP437_EXTENDED: &str = "ÇüéâäàåçêëèïîìÄÅÉæÆôöòûùÿÖÜ¢£¥₧ƒáíóúñÑªº¿⌐¬½¼¡«»░▒▓│┤╡╢╖╕╣║╗╝╜╛┐└┴┬├─┼╞╟╚╔╩╦╠═╬╧╨╤╥╙╘╒╓╫╪┘┌█▄▌▐▀αßΓπΣσµτΦΘΩδ∞φε∩≡±≥≤⌠⌡÷≈°∙·√ⁿ²■ ";

#[derive(Debug, Serialize, sqlx::FromRow)]
pub struct FileEntry {
    pub id: i64,
    pub path: String,
    pub mtime: i64,
}

pub async fn list_files(State(state): State<SharedState>) -> Response {
    match sqlx::query_as::<_, FileEntry>(
        "SELECT id, path, mtime FROM files ORDER BY path LIMIT 500",
    )
    .fetch_all(&state.db)
    .await
    {
        Ok(files) => Json(files).into_response(),
        Err(error) => {
            tracing::error!(?error, "failed to list files");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(serde_json::json!({
                    "error": "internal_server_error",
                })),
            )
                .into_response()
        }
    }
}

fn guess_mime(path: &str) -> &'static str {
    match path
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase()
        .as_str()
    {
        "png" => "image/png",
        "jpg" | "jpeg" => "image/jpeg",
        "webp" => "image/webp",
        "gif" => "image/gif",
        "avif" => "image/avif",
        "svg" => "image/svg+xml",
        "pdf" => "application/pdf",
        "mp4" | "m4v" => "video/mp4",
        "webm" => "video/webm",
        "mov" => "video/quicktime",
        "avi" => "video/x-msvideo",
        "mkv" => "video/x-matroska",
        "ogv" => "video/ogg",
        "mp3" => "audio/mpeg",
        "wav" => "audio/wav",
        "ogg" => "audio/ogg",
        "opus" => "audio/opus",
        "m4a" | "aac" => "audio/aac",
        "flac" => "audio/flac",
        _ => "application/octet-stream",
    }
}

fn is_audio_or_video(ext: &str) -> bool {
    matches!(
        ext,
        "webm"
            | "mp4"
            | "mov"
            | "m4v"
            | "ogv"
            | "avi"
            | "mkv"
            | "mp3"
            | "wav"
            | "ogg"
            | "opus"
            | "m4a"
            | "aac"
            | "flac"
    )
}

fn parse_range(s: &str, size: u64) -> Option<(u64, u64)> {
    let s = s.strip_prefix("bytes=")?;
    let (a, b) = s.split_once('-')?;
    let start: u64 = a.parse().ok()?;
    let end: u64 = if b.is_empty() {
        size - 1
    } else {
        b.parse().ok()?
    };
    (start <= end && end < size).then_some((start, end))
}

async fn serve_range(
    path: PathBuf,
    mime: &'static str,
    etag: String,
    req_headers: &HeaderMap,
) -> Response {
    let file = match tokio::fs::File::open(&path).await {
        Ok(f) => f,
        Err(e) if e.kind() == std::io::ErrorKind::NotFound => {
            return StatusCode::NOT_FOUND.into_response();
        }
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    };
    let size = match file.metadata().await {
        Ok(m) => m.len(),
        Err(_) => return StatusCode::INTERNAL_SERVER_ERROR.into_response(),
    };

    if req_headers
        .get(header::IF_NONE_MATCH)
        .and_then(|v| v.to_str().ok())
        .is_some_and(|v| v == etag)
    {
        return StatusCode::NOT_MODIFIED.into_response();
    }

    if let Some(range_val) = req_headers.get(header::RANGE) {
        if let Some((start, end)) = range_val.to_str().ok().and_then(|s| parse_range(s, size)) {
            let length = end - start + 1;
            let mut f = file;
            let _ = f.seek(std::io::SeekFrom::Start(start)).await;
            let body = Body::from_stream(ReaderStream::new(f.take(length)));
            return Response::builder()
                .status(StatusCode::PARTIAL_CONTENT)
                .header(header::CONTENT_TYPE, mime)
                .header(header::ETAG, &etag)
                .header(header::ACCEPT_RANGES, "bytes")
                .header(header::CONTENT_RANGE, format!("bytes {start}-{end}/{size}"))
                .body(body)
                .unwrap();
        }
        return StatusCode::RANGE_NOT_SATISFIABLE.into_response();
    }

    Response::builder()
        .status(StatusCode::OK)
        .header(header::CONTENT_TYPE, mime)
        .header(header::ETAG, &etag)
        .header(header::ACCEPT_RANGES, "bytes")
        .header(header::CONTENT_LENGTH, size.to_string())
        .body(Body::from_stream(ReaderStream::new(file)))
        .unwrap()
}

async fn lookup_file(state: &SharedState, file_id: i64) -> Result<(String, i64), Response> {
    match sqlx::query_as::<_, (String, i64)>("SELECT path, mtime FROM files WHERE id = ?")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
    {
        Ok(Some(row)) => Ok(row),
        Ok(None) => Err((
            StatusCode::NOT_FOUND,
            Json(serde_json::json!({"error": "not_found"})),
        )
            .into_response()),
        Err(e) => {
            tracing::error!(?e, "db lookup failed in files route");
            Err(StatusCode::INTERNAL_SERVER_ERROR.into_response())
        }
    }
}

/// Python `ARCHIVE_MAX_ENTRY_SIZE` (core/infra_core/timeout.py:28).
const ARCHIVE_MAX_ENTRY_SIZE: u64 = 512 * 1024 * 1024;

/// Split `archive.zip!inner/file.png` at the **first** archive boundary,
/// mirroring Python `split_archive_path()`
/// (core/helpers_core/helpers_text_path.py:46). A bare `path.split('!')`
/// mis-handles ordinary files whose name contains `!`, which this repo has
/// real-world data for (`"...エルフ! [同人cg集]/img.jpg"`).
/// Returns `None` when there is no archive boundary.
fn split_archive_path(path: &str) -> Option<(&str, &str)> {
    let lower = path.to_lowercase();
    let mut best: Option<(usize, usize)> = None;
    for ext in [".zip!", ".7z!", ".rar!"] {
        if let Some(idx) = lower.find(ext) {
            if best.is_none_or(|(b, _)| idx < b) {
                best = Some((idx, ext.len()));
            }
        }
    }
    let (idx, ext_len) = best?;
    let sep = idx + ext_len - 1;
    Some((&path[..sep], &path[sep + 1..]))
}

/// Mirrors Python `resolve_zip_target()` (core/files_core/media_zip.py:17):
/// normalized match, then exact match, then the first entry sharing the
/// basename. POSIX semantics — only `/` separates, as `Path(...).name` does on
/// the platform this server runs on.
fn normalize_separators(path: &str) -> String {
    let path = path.replace('\\', "/").replace('\0', "");
    let path = path.trim_start_matches("./");
    path.trim_start_matches('/')
        .split('/')
        .filter(|part| !part.is_empty() && *part != "..")
        .collect::<Vec<_>>()
        .join("/")
}

/// `CP437_EXTENDED` holds exactly the 128 high half of code page 437, so a
/// `position()` hit is in `0..128` and `index + 128` is in `128..256` — inside
/// `u8` by construction. A character not in the table returns early instead.
#[allow(clippy::cast_possible_truncation)]
fn repair_cp437_name(name: &str) -> Vec<String> {
    let mut raw = Vec::with_capacity(name.len());
    for ch in name.chars() {
        if ch.is_ascii() {
            raw.push(ch as u8);
        } else if let Some(index) = CP437_EXTENDED.chars().position(|mapped| mapped == ch) {
            raw.push((index + 128) as u8);
        } else {
            return Vec::new();
        }
    }

    // encoding_rs exposes WHATWG decoders, so Python aliases share compatible decoders:
    // cp932/shift_jis, euc-kr/cp949, gb2312/gbk, and big5/cp950 each collapse here.
    // The strict API still rejects malformed byte sequences like Python's decoder does.
    let encodings = [
        SHIFT_JIS,
        EUC_JP,
        ISO_2022_JP,
        EUC_KR,
        EUC_KR,
        GBK,
        GBK,
        BIG5,
        BIG5,
        SHIFT_JIS,
    ];
    let mut results = Vec::new();
    for encoding in encodings {
        if let Some(decoded) = encoding.decode_without_bom_handling_and_without_replacement(&raw) {
            if decoded.as_ref() != name && !results.iter().any(|result| result == decoded.as_ref())
            {
                results.push(decoded.into_owned());
            }
        }
    }
    results
}

fn name_variants(name: &str) -> Vec<String> {
    let base = normalize_separators(name);
    // Python uses a set here. Keep its priority order while deduplicating so a
    // file-serving route never makes a randomized HashSet iteration choice.
    let mut variants = Vec::new();
    let mut add = |variant: String| {
        if !variant.is_empty() && !variants.iter().any(|existing| existing == &variant) {
            variants.push(variant);
        }
    };
    add(base.clone());
    add(base.nfc().collect());
    add(base.nfkc().collect());
    for repaired in repair_cp437_name(&base) {
        let repaired = normalize_separators(&repaired);
        add(repaired.clone());
        add(repaired.nfc().collect());
        add(repaired.nfkc().collect());
    }
    variants
}

// Ports core/zip_core/zip_path_resolve.py::_resolve_entry_name. Unlike
// resolve_zip_target, its basename fallback accepts only a unique match.
fn resolve_entry_name(names: &[String], inner_path: &str) -> Option<String> {
    if names.iter().any(|n| n == inner_path) {
        return Some(inner_path.to_string());
    }

    let mut variant_to_actual = HashMap::new();
    for actual in names {
        for variant in name_variants(actual) {
            variant_to_actual.entry(variant).or_insert(actual);
        }
    }
    for variant in name_variants(inner_path) {
        if let Some(actual) = variant_to_actual.get(&variant) {
            return Some((*actual).clone());
        }
    }

    let normalized_path = normalize_separators(inner_path);
    let target_name = normalized_path.rsplit('/').next().unwrap_or("");
    if target_name.is_empty() {
        return None;
    }
    let candidates: Vec<_> = names
        .iter()
        .filter(|name| normalize_separators(name).rsplit('/').next() == Some(target_name))
        .collect();
    (candidates.len() == 1).then(|| candidates[0].clone())
}

// Ports core/files_core/media_zip.py::resolve_zip_target. Unlike
// resolve_entry_name, its basename fallback deliberately takes the first match.
fn resolve_zip_target(names: &[String], inner_path: &str) -> Option<String> {
    let normalized = inner_path.replace('\\', "/");
    if names.iter().any(|name| name == &normalized) {
        return Some(normalized);
    }
    if names.iter().any(|name| name == inner_path) {
        return Some(inner_path.to_string());
    }
    fn basename(path: &str) -> &str {
        path.rsplit('/').next().unwrap_or(path)
    }
    let wanted = basename(inner_path);
    names.iter().find(|name| basename(name) == wanted).cloned()
}

/// Extract a `.zip!` member into the media cache and return its on-disk path,
/// so the ordinary file-serving path can take over. Handles both plain members
/// and one level of nesting (`outer.zip!inner.zip!img.png`), which is exactly
/// what the scanner produces — `list_images_in_zip`
/// (core/zip_core/zip_listing.py:41) expands nested ZIPs one level and stops.
///
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum ArchiveMemberError {
    MissingArchive,
    MissingEntry,
    CorruptArchive,
    ExtractionFailed,
    InvalidExtension,
}

fn archive_member_error_response(error: ArchiveMemberError) -> Response {
    // Python's preview.py::serve_preview passes serve_original's FileError through unchanged.
    // Python keeps the detailed Japanese `zip_error_text` messages; native keeps
    // only stable machine codes so this port does not duplicate localized prose.
    let (status, code) = match error {
        ArchiveMemberError::MissingArchive => (StatusCode::NOT_FOUND, "archive_missing"),
        ArchiveMemberError::MissingEntry => (StatusCode::NOT_FOUND, "archive_entry_missing"),
        ArchiveMemberError::CorruptArchive => (StatusCode::UNPROCESSABLE_ENTITY, "archive_corrupt"),
        ArchiveMemberError::ExtractionFailed => {
            (StatusCode::UNPROCESSABLE_ENTITY, "archive_extract_failed")
        }
        ArchiveMemberError::InvalidExtension => (
            StatusCode::UNPROCESSABLE_ENTITY,
            "archive_invalid_extension",
        ),
    };
    (
        status,
        Json(serde_json::json!({"error": "archive member unavailable", "code": code})),
    )
        .into_response()
}

fn preflight_archive_member(
    archive: &str,
    inner: &str,
    nested: Option<(&str, &str)>,
    is_zip: bool,
    is_sevenz: bool,
) -> Result<(), ArchiveMemberError> {
    if !FsPath::new(archive).exists() {
        return Err(ArchiveMemberError::MissingArchive);
    }
    if is_zip {
        let mut zip = zip::ZipArchive::new(
            std::fs::File::open(archive).map_err(|_| ArchiveMemberError::ExtractionFailed)?,
        )
        .map_err(|_| ArchiveMemberError::CorruptArchive)?;
        let names: Vec<String> = zip.file_names().map(str::to_string).collect();
        if let Some((nested_archive, nested_member)) = nested {
            let outer = resolve_entry_name(&names, nested_archive)
                .ok_or(ArchiveMemberError::MissingEntry)?;
            let mut bytes = Vec::new();
            std::io::Read::read_to_end(
                &mut zip
                    .by_name(&outer)
                    .map_err(|_| ArchiveMemberError::ExtractionFailed)?,
                &mut bytes,
            )
            .map_err(|_| ArchiveMemberError::ExtractionFailed)?;
            let nested = zip::ZipArchive::new(std::io::Cursor::new(bytes))
                .map_err(|_| ArchiveMemberError::CorruptArchive)?;
            if resolve_zip_target(
                &nested.file_names().map(str::to_string).collect::<Vec<_>>(),
                nested_member,
            )
            .is_none()
            {
                return Err(ArchiveMemberError::MissingEntry);
            }
        } else {
            let target =
                resolve_zip_target(&names, inner).ok_or(ArchiveMemberError::MissingEntry)?;
            if zip
                .by_name(&target)
                .map_err(|_| ArchiveMemberError::ExtractionFailed)?
                .size()
                > ARCHIVE_MAX_ENTRY_SIZE
            {
                return Err(ArchiveMemberError::ExtractionFailed);
            }
        }
    } else if is_sevenz {
        let entries = list_sevenz_entries(FsPath::new(archive))
            .ok_or(ArchiveMemberError::ExtractionFailed)?;
        let names: Vec<String> = entries
            .iter()
            .filter(|entry| !entry.is_directory)
            .map(|entry| entry.path.clone())
            .collect();
        let target = resolve_entry_name(&names, inner).ok_or(ArchiveMemberError::MissingEntry)?;
        if entries
            .iter()
            .find(|entry| entry.path == target)
            .is_none_or(|entry| entry.size > ARCHIVE_MAX_ENTRY_SIZE)
        {
            return Err(ArchiveMemberError::ExtractionFailed);
        }
    } else {
        let entries =
            list_rar_entries(FsPath::new(archive)).ok_or(ArchiveMemberError::ExtractionFailed)?;
        let names: Vec<String> = entries
            .iter()
            .filter(|entry| !entry.is_directory)
            .map(|entry| entry.path.clone())
            .collect();
        let target = resolve_entry_name(&names, inner).ok_or(ArchiveMemberError::MissingEntry)?;
        if entries
            .iter()
            .find(|entry| entry.path == target)
            .is_none_or(|entry| entry.size > ARCHIVE_MAX_ENTRY_SIZE)
        {
            return Err(ArchiveMemberError::ExtractionFailed);
        }
    }
    Ok(())
}

/// Returns a typed Python-compatible cause when native extraction cannot serve it.
async fn materialize_archive_member(
    state: &SharedState,
    path_str: &str,
    mtime: i64,
) -> Result<PathBuf, ArchiveMemberError> {
    let (archive, inner) =
        split_archive_path(path_str).ok_or(ArchiveMemberError::ExtractionFailed)?;
    let archive_is_zip = archive.to_lowercase().ends_with(".zip");
    let archive_is_sevenz = archive.to_lowercase().ends_with(".7z");
    let archive_is_rar = archive.to_lowercase().ends_with(".rar");
    if !archive_is_zip && !archive_is_sevenz && !archive_is_rar {
        return Err(ArchiveMemberError::ExtractionFailed);
    }
    // Split at the FIRST `!` and treat it as nested only when the prefix is a
    // `.zip`, mirroring Python `_is_nested` (core/files_core/original_zip.py:48).
    // A member legitimately named `dir/foo.7z!image.jpg` is not nested, and
    // Python serves it from the outer archive, so deferring on any `!` would
    // diverge.
    let nested = (archive_is_zip && is_nested_zip(inner))
        .then(|| inner.split_once('!'))
        .flatten();

    // The extension that names the cache file comes from the member actually
    // being served, which for a nested path is the part after the last `!`.
    let member = nested.map_or(inner, |(_, tail)| tail);
    let ext = member.rsplit('.').next().unwrap_or("").to_ascii_lowercase();
    if ext.is_empty() || ext.len() > 8 || !ext.chars().all(|c| c.is_ascii_alphanumeric()) {
        // Indexed archive rows always have safe image extensions; this guard is
        // retained for direct/stale rows rather than being conflated with I/O.
        return Err(ArchiveMemberError::InvalidExtension);
    }

    preflight_archive_member(archive, inner, nested, archive_is_zip, archive_is_sevenz)?;

    let dir = state.config.cache_dir.join("zip_members");
    tokio::fs::create_dir_all(&dir)
        .await
        .map_err(|_| ArchiveMemberError::ExtractionFailed)?;
    let archive = archive.to_string();
    let path_str = path_str.to_string();
    let nested = nested.map(|(a, b)| (a.to_string(), b.to_string()));
    let inner = inner.to_string();
    if archive_is_sevenz {
        return cached_sevenz_member(
            &archive,
            &inner,
            &path_str,
            mtime,
            &dir,
            &ext,
            ARCHIVE_MAX_ENTRY_SIZE,
        )
        .await
        .ok_or(ArchiveMemberError::ExtractionFailed);
    }
    if archive_is_rar {
        return cached_rar_member(
            &archive,
            &inner,
            &path_str,
            mtime,
            &dir,
            &ext,
            ARCHIVE_MAX_ENTRY_SIZE,
        )
        .await
        .ok_or(ArchiveMemberError::ExtractionFailed);
    }
    tokio::task::spawn_blocking(move || match nested {
        Some((nested_archive, nested_member)) => cached_nested_zip_member(
            &archive,
            &nested_archive,
            &nested_member,
            &path_str,
            mtime,
            &dir,
            &ext,
            ARCHIVE_MAX_ENTRY_SIZE,
        ),
        None => cached_zip_member(
            &archive,
            &inner,
            &path_str,
            mtime,
            &dir,
            &ext,
            ARCHIVE_MAX_ENTRY_SIZE,
        ),
    })
    .await
    .ok()
    .flatten()
    .ok_or(ArchiveMemberError::ExtractionFailed)
}

/// Blocking ZIP body of [`materialize_archive_member`]: open the archive once, key the
/// cache on the entry's identity, and extract only on a miss.
///
/// Weaker identities were tried and are not sufficient:
///
/// * archive mtime + length — filesystem mtimes are second-resolution, so a
///   same-length replacement inside one second reuses the entry forever;
/// * the entry's CRC-32 + uncompressed size — CRC-32 is a linear checksum with
///   no collision resistance, and both fields come from the archive itself, so
///   whoever writes the archive can hold them fixed while changing the content;
/// * a SHA-256 of the stored bytes alone — the stored bytes only determine the
///   content *for a fixed compression method*. The method lives in the headers,
///   outside the bytes, so flipping it decodes the same bytes differently while
///   the digest is unchanged.
///
/// So the key covers the stored bytes **and every header field the crate
/// exposes**. Over-inclusion is deliberate: a field that turns out not to
/// affect decoding only costs an extra cache miss, whereas a missing one is a
/// stale-content bug. Adding a field is always safe; removing one is not.
/// The `size as usize` below only narrows on a 32-bit target, and `size` has
/// already been rejected above if it exceeds `max` — so the capacity hint is
/// bounded by the caller's cap rather than by an attacker-declared entry size.
#[allow(clippy::cast_possible_truncation)]
fn cached_zip_member(
    archive: &str,
    inner: &str,
    path_str: &str,
    db_mtime: i64,
    dir: &FsPath,
    ext: &str,
    max: u64,
) -> Option<PathBuf> {
    let mut zip = zip::ZipArchive::new(std::fs::File::open(archive).ok()?).ok()?;
    let names: Vec<String> = zip.file_names().map(str::to_string).collect();
    let target = resolve_zip_target(&names, inner)?;
    let entry = zip.by_name(&target).ok()?;
    if entry.size() > max {
        return None;
    }
    let key = member_cache_key(
        path_str,
        db_mtime,
        &entry.size().to_string(),
        &entry.crc32().to_string(),
    );
    let size = entry.size();
    drop(entry);
    let dest = dir.join(format!("{key}.{ext}"));
    if dest.exists() {
        return Some(dest);
    }
    let mut bytes = Vec::with_capacity(size as usize);
    std::io::Read::read_to_end(&mut zip.by_name(&target).ok()?, &mut bytes).ok()?;
    let tmp = temp_sibling(&dest);
    std::fs::write(&tmp, bytes).ok()?;
    std::fs::rename(tmp, &dest).ok()?;
    Some(dest)
}

/// Both `size as usize` casts below narrow only on a 32-bit target, and each is
/// preceded by its own `> max` rejection — outer entry and nested entry alike —
/// so neither capacity hint comes from an unchecked declared size.
#[allow(clippy::cast_possible_truncation)]
fn cached_nested_zip_member(
    archive: &str,
    nested_archive: &str,
    nested_member: &str,
    path_str: &str,
    db_mtime: i64,
    dir: &FsPath,
    ext: &str,
    max: u64,
) -> Option<PathBuf> {
    let mut outer = zip::ZipArchive::new(std::fs::File::open(archive).ok()?).ok()?;
    let outer_names: Vec<String> = outer.file_names().map(str::to_string).collect();
    let outer_target = resolve_entry_name(&outer_names, nested_archive)?;
    let outer_entry = outer.by_name(&outer_target).ok()?;
    if outer_entry.size() > max {
        return None;
    }
    let outer_size = outer_entry.size();
    drop(outer_entry);
    let mut outer_bytes = Vec::with_capacity(outer_size as usize);
    std::io::Read::read_to_end(&mut outer.by_name(&outer_target).ok()?, &mut outer_bytes).ok()?;
    let mut nested = zip::ZipArchive::new(std::io::Cursor::new(outer_bytes)).ok()?;
    let names: Vec<String> = nested.file_names().map(str::to_string).collect();
    let target = resolve_zip_target(&names, nested_member)?;
    let entry = nested.by_name(&target).ok()?;
    if entry.size() > max {
        return None;
    }
    let key = member_cache_key(
        path_str,
        db_mtime,
        &entry.size().to_string(),
        &entry.crc32().to_string(),
    );
    let size = entry.size();
    drop(entry);
    let dest = dir.join(format!("{key}.{ext}"));
    if dest.exists() {
        return Some(dest);
    }
    let mut bytes = Vec::with_capacity(size as usize);
    std::io::Read::read_to_end(&mut nested.by_name(&target).ok()?, &mut bytes).ok()?;
    let tmp = temp_sibling(&dest);
    std::fs::write(&tmp, bytes).ok()?;
    std::fs::rename(tmp, &dest).ok()?;
    Some(dest)
}

#[derive(Debug, PartialEq, Eq)]
struct SevenzEntry {
    path: String,
    size: u64,
    crc: Option<u64>,
    is_directory: bool,
}

fn entry_header(entry: &zip::read::ZipFile<'_>) -> String {
    format!(
        "name={};method={:?};size={};compressed_size={};crc={}",
        entry.name(),
        entry.compression(),
        entry.size(),
        entry.compressed_size(),
        entry.crc32(),
    )
}

fn list_sevenz_entries(archive: &FsPath) -> Option<Vec<SevenzEntry>> {
    let reader =
        sevenz_rust2::ArchiveReader::open(archive, sevenz_rust2::Password::empty()).ok()?;
    Some(
        reader
            .archive()
            .files
            .iter()
            .map(|entry| SevenzEntry {
                path: entry.name.clone(),
                size: entry.size,
                crc: entry.has_crc.then_some(entry.crc),
                is_directory: entry.is_directory,
            })
            .collect(),
    )
}

fn resolve_sevenz_entry<'a>(
    entries: &'a [SevenzEntry],
    inner: &str,
    max: u64,
) -> Option<&'a SevenzEntry> {
    let names: Vec<String> = entries
        .iter()
        .filter(|entry| !entry.is_directory)
        .map(|entry| entry.path.clone())
        .collect();
    let target = resolve_entry_name(&names, inner)?;
    let entry = entries.iter().find(|entry| entry.path == target)?;
    (entry.size <= max).then_some(entry)
}

/// The capacity hint below is `entry.size().min(max)`, so the declared entry
/// size can only ever lower it — a 7z header claiming a huge member cannot make
/// this allocate more than the caller's cap. Narrows only on a 32-bit target.
#[allow(clippy::cast_possible_truncation)]
async fn cached_sevenz_member(
    archive: &str,
    inner: &str,
    path_str: &str,
    db_mtime: i64,
    dir: &FsPath,
    ext: &str,
    max: u64,
) -> Option<PathBuf> {
    let archive = FsPath::new(archive);
    let entries = list_sevenz_entries(archive)?;
    let entry = resolve_sevenz_entry(&entries, inner, max)?;
    // Archive length and mtime invalidate ordinary edits or replacement. An attacker can preserve
    // both during an in-place rewrite; this matches the surrounding db_mtime exposure. ZIP is
    // stronger because it can digest stored entry bytes cheaply, which this 7z reader cannot expose.
    let metadata = std::fs::metadata(archive).ok()?;
    let archive_mtime = metadata
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_nanos();
    let key = member_cache_key(
        path_str,
        db_mtime,
        &metadata.len().to_string(),
        &archive_mtime.to_string(),
    );
    let dest = dir.join(format!("{key}.{ext}"));
    if dest.exists() {
        return Some(dest);
    }
    let archive = archive.to_owned();
    let target = entry.path.clone();
    let bytes = tokio::task::spawn_blocking(move || {
        let mut reader =
            sevenz_rust2::ArchiveReader::open(archive, sevenz_rust2::Password::empty()).ok()?;
        let mut bytes = None;
        reader
            .for_each_entries(|entry, input| {
                if entry.name() == target {
                    let mut buffer = Vec::with_capacity(entry.size().min(max) as usize);
                    std::io::Read::read_to_end(
                        &mut std::io::Read::take(input, max.saturating_add(1)),
                        &mut buffer,
                    )?;
                    bytes = (buffer.len() as u64 <= max).then_some(buffer);
                    return Ok(false);
                }
                Ok(true)
            })
            .ok()?;
        bytes
    })
    .await
    .ok()??;
    let tmp = temp_sibling(&dest);
    std::fs::write(&tmp, bytes).ok()?;
    std::fs::rename(tmp, &dest).ok()?;
    Some(dest)
}

#[derive(Debug, PartialEq, Eq)]
struct RarEntry {
    path: String,
    size: u64,
    is_directory: bool,
}

fn list_rar_entries(archive: &FsPath) -> Option<Vec<RarEntry>> {
    unrar::Archive::new(archive)
        .open_for_listing()
        .ok()?
        .map(|entry| {
            let entry = entry.ok()?;
            Some(RarEntry {
                path: entry.filename.to_string_lossy().into_owned(),
                size: entry.unpacked_size,
                is_directory: entry.is_directory(),
            })
        })
        .collect()
}

fn resolve_rar_entry<'a>(entries: &'a [RarEntry], inner: &str, max: u64) -> Option<&'a RarEntry> {
    let names: Vec<String> = entries
        .iter()
        .filter(|entry| !entry.is_directory)
        .map(|entry| entry.path.clone())
        .collect();
    let target = resolve_entry_name(&names, inner)?;
    let entry = entries.iter().find(|entry| entry.path == target)?;
    (entry.size <= max).then_some(entry)
}

async fn cached_rar_member(
    archive: &str,
    inner: &str,
    path_str: &str,
    db_mtime: i64,
    dir: &FsPath,
    ext: &str,
    max: u64,
) -> Option<PathBuf> {
    let archive = FsPath::new(archive);
    let entries = list_rar_entries(archive)?;
    let entry = resolve_rar_entry(&entries, inner, max)?;
    // Archive length and mtime invalidate ordinary edits or replacement. An attacker can preserve
    // both during an in-place rewrite; this matches the surrounding db_mtime exposure. RAR cannot
    // expose stored entry bytes cheaply, so it cannot provide ZIP's stronger cache identity.
    let metadata = std::fs::metadata(archive).ok()?;
    let archive_mtime = metadata
        .modified()
        .ok()?
        .duration_since(std::time::UNIX_EPOCH)
        .ok()?
        .as_nanos();
    let key = member_cache_key(
        path_str,
        db_mtime,
        &metadata.len().to_string(),
        &archive_mtime.to_string(),
    );
    let dest = dir.join(format!("{key}.{ext}"));
    if dest.exists() {
        return Some(dest);
    }
    let archive = archive.to_owned();
    let target = entry.path.clone();
    let bytes = tokio::task::spawn_blocking(move || {
        let mut reader = unrar::Archive::new(&archive).open_for_processing().ok()?;
        while let Some(header) = reader.read_header().ok()? {
            let entry = header.entry();
            if !entry.is_directory() && entry.filename.to_string_lossy() == target {
                if entry.unpacked_size > max {
                    return None;
                }
                // unrar::read() returns the whole entry, so its declared size is the only
                // pre-read bound available; a dishonest size can still allocate too much.
                let (bytes, _) = header.read().ok()?;
                return (bytes.len() as u64 <= max).then_some(bytes);
            }
            reader = header.skip().ok()?;
        }
        None
    })
    .await
    .ok()??;
    let tmp = temp_sibling(&dest);
    std::fs::write(&tmp, bytes).ok()?;
    std::fs::rename(tmp, &dest).ok()?;
    Some(dest)
}

fn member_cache_key(path_str: &str, db_mtime: i64, stored: &str, header: &str) -> String {
    let mut h = Sha256::new();
    h.update(format!("zipmember:{path_str}:{db_mtime}:{stored}:{header}").as_bytes());
    hex::encode(&h.finalize()[..16])
}

/// How many stored bytes [`stored_bytes_digest`] may read for an entry whose
/// uncompressed size is within `max`.
///
/// The uncompressed cap cannot be applied to the stored form: a small entry's
/// deflate stream is routinely *larger* than its content. But leaving the read
/// unbounded is worse — the declared uncompressed size is checked first and can
/// be tiny while the stored extent is enormous, so every request would read the
/// whole thing. Deflate's worst case is a few percent of expansion plus a small
/// per-block constant, so this allows well beyond any honest entry and still
/// bounds the read.
fn stored_read_cap(max: u64) -> u64 {
    max.saturating_add(max / 16).saturating_add(64 * 1024)
}

/// SHA-256 over an entry's stored (compressed) bytes, hex-encoded.
///
/// Reads the raw member without inflating it, so a lying uncompressed-size
/// field cannot make this expand. `cap` bounds the read — see
/// [`stored_read_cap`] for why it is not the uncompressed cap.
fn stored_bytes_digest<R: std::io::Read + std::io::Seek>(
    zip: &mut zip::ZipArchive<R>,
    index: usize,
    cap: u64,
) -> Option<String> {
    use std::io::Read as _;

    let mut raw = zip.by_index_raw(index).ok()?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 64 * 1024];
    let mut total: u64 = 0;
    loop {
        let n = raw.read(&mut buf).ok()?;
        if n == 0 {
            break;
        }
        total += n as u64;
        if total > cap {
            return None;
        }
        hasher.update(&buf[..n]);
    }
    Some(hex::encode(hasher.finalize()))
}

/// ETag for a file being served from `path`.
///
/// The path is part of the tag because filesystem mtimes are second-resolution:
/// for an extracted archive member, a same-length replacement within the same
/// second yields identical `(len, mtime)` and the client would keep its stale
/// copy on a 304. The cache filename encodes the member's CRC-32, so folding
/// the path in makes the tag move whenever the content does.
fn file_etag(path: &str, len: u64, mtime: i64) -> String {
    let mut h = Sha256::new();
    h.update(format!("{path}:{len}:{mtime}").as_bytes());
    format!("\"{}\"", hex::encode(&h.finalize()[..12]))
}

/// A per-attempt temp sibling for `dest`. Concurrent extractions of the same
/// member must not share one, or either can publish the other's partial write.
fn temp_sibling(dest: &std::path::Path) -> PathBuf {
    static SEQ: std::sync::atomic::AtomicU64 = std::sync::atomic::AtomicU64::new(0);
    let seq = SEQ.fetch_add(1, std::sync::atomic::Ordering::Relaxed);
    dest.with_extension(format!("{}.{seq}.part", std::process::id()))
}

/// Mirrors Python `_is_nested` (core/files_core/original_zip.py:48).
fn is_nested_zip(inner_path: &str) -> bool {
    inner_path
        .split_once('!')
        .is_some_and(|(head, _)| head.to_lowercase().ends_with(".zip"))
}

/// Write one entry of an open archive to `dest`, via a private `.part` sibling
/// that is renamed into place, so a concurrent reader never observes a
/// half-written file and two racing extractions cannot share a temp path.
///
/// `entry.size()` is only the size *declared* in the central directory, so a
/// crafted archive can understate it. The caller rejects the obvious lie; here
/// the write itself is bounded and what was actually produced is re-checked.
fn write_zip_entry<R: std::io::Read + std::io::Seek>(
    zip: &mut zip::ZipArchive<R>,
    target: &str,
    dest: &std::path::Path,
    max: u64,
) -> bool {
    use std::io::Read as _;

    let Ok(mut entry) = zip.by_name(target) else {
        return false;
    };

    // Racing extractions of the same member would otherwise truncate each
    // other's `.part` file and publish the fragment.
    let tmp = temp_sibling(dest);

    let Ok(mut out) = std::fs::File::create(&tmp) else {
        return false;
    };
    let discard = |tmp: &std::path::Path| {
        let _ = std::fs::remove_file(tmp);
        false
    };
    // Read one byte past the cap so an over-long entry is detectable rather
    // than silently truncated to exactly the limit.
    match std::io::copy(&mut entry.take(max + 1), &mut out) {
        Ok(written) if written <= max => {}
        _ => return discard(&tmp),
    }
    drop(out);
    if std::fs::rename(&tmp, dest).is_err() {
        return discard(&tmp);
    }
    true
}

/// Resolve the on-disk path to serve for a DB `path` value, plus the mtime
/// that identifies its current contents.
///
/// Ordinary files pass through unchanged. Archive members are materialized into
/// the cache when Rust can read them, and report the **extracted** file's mtime
/// rather than the DB value: for a member the DB `mtime` is the timestamp
/// stored inside the archive (`ZipInfo.date_time`), which survives the archive
/// being rewritten. Callers fold this into ETags and preview cache keys, so
/// passing the DB value through would hand a client a matching ETag for
/// replaced content of the same length and answer 304 with stale bytes.
///
async fn servable_path(
    state: &SharedState,
    path_str: &str,
    mtime: i64,
) -> Result<(String, i64), ArchiveMemberError> {
    if split_archive_path(path_str).is_none() {
        return Ok((path_str.to_string(), mtime));
    }
    let extracted = materialize_archive_member(state, path_str, mtime).await?;
    let extracted_mtime = tokio::fs::metadata(&extracted)
        .await
        .ok()
        .and_then(|m| m.modified().ok())
        .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
        .map_or(mtime, |d| d.as_secs() as i64);
    Ok((extracted.to_string_lossy().into_owned(), extracted_mtime))
}

pub async fn serve_original(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    headers: HeaderMap,
) -> Response {
    let (path_str, mtime) = match lookup_file(&state, file_id).await {
        Ok(r) => r,
        Err(resp) => return resp,
    };

    let (path_str, mtime) = match servable_path(&state, &path_str, mtime).await {
        Ok(path) => path,
        Err(error) => return archive_member_error_response(error),
    };

    let ext = path_str
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();

    if matches!(ext.as_str(), "heif" | "heic" | "jxl") {
        return (
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "HEIF/JXL requires Python backend",
        )
            .into_response();
    }

    let file_path = PathBuf::from(&path_str);
    let Ok(meta) = tokio::fs::metadata(&file_path).await else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let etag = file_etag(&path_str, meta.len(), mtime);
    let mime = guess_mime(&path_str);

    let mut resp = serve_range(file_path, mime, etag, &headers).await;
    if ext == "svg" {
        let h = resp.headers_mut();
        h.insert(
            "content-security-policy",
            HeaderValue::from_static(
                "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
            ),
        );
        h.insert(
            "x-content-type-options",
            HeaderValue::from_static("nosniff"),
        );
    }
    resp
}

pub async fn serve_preview(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    headers: HeaderMap,
) -> Response {
    serve_preview_impl(state, file_id, headers, false).await
}

pub async fn serve_thumbnail(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    headers: HeaderMap,
) -> Response {
    serve_preview_impl(state, file_id, headers, true).await
}

async fn serve_preview_impl(
    state: SharedState,
    file_id: i64,
    headers: HeaderMap,
    render_pdf: bool,
) -> Response {
    let (path_str, mtime) = match lookup_file(&state, file_id).await {
        Ok(r) => r,
        Err(resp) => return resp,
    };

    let (path_str, mtime) = match servable_path(&state, &path_str, mtime).await {
        Ok(path) => path,
        Err(error) => return archive_member_error_response(error),
    };

    let ext = path_str
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();

    // Video/audio previews are always their originals. PDFs are originals only at /api/preview.
    if is_audio_or_video(&ext) || (ext == "pdf" && !render_pdf) {
        let file_path = PathBuf::from(&path_str);
        let Ok(meta) = tokio::fs::metadata(&file_path).await else {
            return StatusCode::NOT_FOUND.into_response();
        };
        let etag = file_etag(&path_str, meta.len(), mtime);
        return serve_range(file_path, guess_mime(&path_str), etag, &headers).await;
    }

    // Cache key: sha256("preview:{path}:{mtime}")[:32 hex chars]
    let cache_key = {
        let mut h = Sha256::new();
        h.update(format!("preview:{path_str}:{mtime}").as_bytes());
        hex::encode(&h.finalize()[..16])
    };
    let cache_dir = state.config.cache_dir.join("previews");

    // Check disk cache (webp preferred, fall back to jpg)
    for cache_ext in ["webp", "jpg"] {
        let p = cache_dir.join(format!("{cache_key}.{cache_ext}"));
        if let Ok(meta) = tokio::fs::metadata(&p).await {
            let ts = meta
                .modified()
                .ok()
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            let etag = file_etag(&p.to_string_lossy(), meta.len(), ts as i64);
            let mime = if cache_ext == "webp" {
                "image/webp"
            } else {
                "image/jpeg"
            };
            let mut resp = serve_range(p, mime, etag, &headers).await;
            resp.headers_mut().insert(
                header::CACHE_CONTROL,
                HeaderValue::from_static("public, max-age=86400, stale-while-revalidate=604800"),
            );
            return resp;
        }
    }

    // Cache miss — check file on disk
    let file_path = PathBuf::from(&path_str);
    let Ok(meta) = tokio::fs::metadata(&file_path).await else {
        return StatusCode::NOT_FOUND.into_response();
    };
    let file_size = meta.len();
    let etag = file_etag(&path_str, file_size, mtime);
    let mime = guess_mime(&path_str);

    // Small file: serve directly without generating a preview
    if file_size < 200 * 1024 && ext != "pdf" {
        return serve_range(file_path, mime, etag, &headers).await;
    }

    if matches!(ext.as_str(), "heif" | "heic" | "jxl") {
        return (
            StatusCode::UNSUPPORTED_MEDIA_TYPE,
            "HEIF/JXL requires Python backend",
        )
            .into_response();
    }

    // Generate resized preview (blocking — CPU-bound image work)
    let _ = tokio::fs::create_dir_all(&cache_dir).await;
    let dest = cache_dir.join(format!("{cache_key}.webp"));
    let src = file_path.clone();
    let result = tokio::task::spawn_blocking(move || generate_preview_sync(&src, &dest)).await;

    match result {
        Ok(Ok(generated)) => {
            let Ok(gm) = std::fs::metadata(&generated) else {
                return serve_range(file_path, mime, etag, &headers).await;
            };
            let ts = gm
                .modified()
                .ok()
                .and_then(|t| t.duration_since(std::time::UNIX_EPOCH).ok())
                .map(|d| d.as_secs())
                .unwrap_or(0);
            let gen_etag = file_etag(&generated.to_string_lossy(), gm.len(), ts as i64);
            let gen_mime = match generated.extension().and_then(|e| e.to_str()) {
                Some("webp") => "image/webp",
                _ => "image/jpeg",
            };
            let mut resp = serve_range(generated, gen_mime, gen_etag, &headers).await;
            resp.headers_mut().insert(
                header::CACHE_CONTROL,
                HeaderValue::from_static("public, max-age=86400, stale-while-revalidate=604800"),
            );
            resp
        }
        _ => serve_range(file_path, mime, etag, &headers).await,
    }
}

fn generate_preview_sync(
    src: &std::path::Path,
    dest: &std::path::Path,
) -> Result<PathBuf, Box<dyn std::error::Error + Send + Sync>> {
    use image::GenericImageView;

    if src
        .extension()
        .is_some_and(|ext| ext.eq_ignore_ascii_case("pdf"))
    {
        return generate_pdf_thumbnail_sync(
            src,
            dest,
            FsPath::new("vendor/pdfium/linux-x64"),
            true,
        );
    }

    let img = image::open(src)?;
    let (w, h) = img.dimensions();
    if w.max(h) <= 1200 {
        return Ok(src.to_path_buf());
    }

    let max_dim = w.max(h) as f64;
    let resized = img.resize(
        crate::num::sat_u32(w as f64 * 1200.0 / max_dim).max(1),
        crate::num::sat_u32(h as f64 * 1200.0 / max_dim).max(1),
        image::imageops::FilterType::CatmullRom,
    );

    // Write to .tmp then rename for atomicity
    let tmp = dest.with_extension("webp.tmp");
    let mut buf = std::io::Cursor::new(Vec::<u8>::new());
    if resized.write_to(&mut buf, image::ImageFormat::WebP).is_ok() {
        std::fs::write(&tmp, buf.into_inner())?;
        std::fs::rename(&tmp, dest)?;
        return Ok(dest.to_path_buf());
    }

    // WebP failed — fall back to JPEG
    let jpg = dest.with_extension("jpg");
    let tmp_jpg = dest.with_extension("jpg.tmp");
    let mut f = std::fs::File::create(&tmp_jpg)?;
    image::codecs::jpeg::JpegEncoder::new_with_quality(&mut f, 82).encode_image(&resized)?;
    drop(f);
    std::fs::rename(&tmp_jpg, &jpg)?;
    Ok(jpg)
}

const PDF_PREVIEW_PAGE: usize = 3;
const PDF_RENDER_DPI: f32 = 144.0;

/// The one pdfium binding this process will ever have. See [`bind_pdfium`].
static PDFIUM: OnceLock<Pdfium> = OnceLock::new();
/// Serialises the bind attempt. `Pdfium::new` asserts that the library has not
/// been initialised yet, so two threads racing past an empty `PDFIUM` would
/// abort the process rather than lose a redundant binding.
static PDFIUM_BIND: Mutex<()> = Mutex::new(());

/// Bind pdfium, reusing the process-wide instance once one exists.
///
/// pdfium-render 0.9 keeps its bindings in a private global `OnceCell`: the
/// second `bind_to_library` (or `bind_to_system_library`) returns
/// `PdfiumLibraryBindingsAlreadyInitialized`, forever. Binding per call was
/// therefore not merely wasteful, it was a one-shot -- the first PDF the
/// process touched rendered, and every later one got `None` and a cached
/// "pdfium unavailable" placeholder written to the thumbnail cache. The same
/// one-shot is why the PDF tests failed: `testing::pdfium`'s loadability probe
/// spent it before the assertions ran.
///
/// A directory that does not hold the library still answers `None`, so
/// "pdfium is not installed here" stays a distinguishable answer after the
/// shared binding exists instead of silently borrowing someone else's library.
///
/// ponytail: the first library to bind wins for the whole process, so a second
/// `library_dir` is ignored. Only an upstream that can rebind would let two
/// coexist; nothing here needs that today.
pub(crate) fn bind_pdfium(library_dir: &FsPath, system_fallback: bool) -> Option<&'static Pdfium> {
    let library_path = Pdfium::pdfium_platform_library_name_at_path(library_dir);
    if !library_path.exists() && !system_fallback {
        return None;
    }
    if let Some(pdfium) = PDFIUM.get() {
        return Some(pdfium);
    }
    let _guard = PDFIUM_BIND
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    if let Some(pdfium) = PDFIUM.get() {
        return Some(pdfium);
    }
    let bindings = match Pdfium::bind_to_library(&library_path) {
        Ok(bindings) => bindings,
        Err(_) if system_fallback => Pdfium::bind_to_system_library().ok()?,
        Err(_) => return None,
    };
    // A failed bind is deliberately not cached: `library_dir` is relative in
    // `generate_preview_sync`, so an early call from the wrong working
    // directory must not disable PDF thumbnails for the rest of the run.
    let _ = PDFIUM.set(Pdfium::new(bindings));
    PDFIUM.get()
}

fn generate_pdf_thumbnail_sync(
    src: &FsPath,
    dest: &FsPath,
    library_dir: &FsPath,
    system_fallback: bool,
) -> Result<PathBuf, Box<dyn std::error::Error + Send + Sync>> {
    let rendered = render_pdf_page(src, library_dir, system_fallback);
    match rendered {
        Some(image) => save_pdf_thumbnail(image, dest),
        None => save_pdf_placeholder(dest),
    }
}

fn render_pdf_page(
    src: &FsPath,
    library_dir: &FsPath,
    system_fallback: bool,
) -> Option<image::DynamicImage> {
    let pdfium = bind_pdfium(library_dir, system_fallback)?;
    let document = pdfium.load_pdf_from_file(src, None).ok()?;
    let page = document
        .pages()
        .get(PDF_PREVIEW_PAGE.try_into().unwrap())
        .ok()?;
    let width = crate::num::sat_i32(f64::from(
        (page.width().value * PDF_RENDER_DPI / 72.0).round(),
    ));
    let bitmap = page
        .render_with_config(&PdfRenderConfig::new().set_target_width(width))
        .ok()?;
    bitmap.as_image().ok()
}

fn save_pdf_thumbnail(
    image: image::DynamicImage,
    dest: &FsPath,
) -> Result<PathBuf, Box<dyn std::error::Error + Send + Sync>> {
    let image = image
        .resize(280, 280, image::imageops::FilterType::Triangle)
        .to_rgb8();
    let tmp = dest.with_extension("webp.tmp");
    let mut bytes = std::io::Cursor::new(Vec::new());
    if image::DynamicImage::ImageRgb8(image.clone())
        .write_to(&mut bytes, image::ImageFormat::WebP)
        .is_ok()
    {
        std::fs::write(&tmp, bytes.into_inner())?;
        std::fs::rename(&tmp, dest)?;
        return Ok(dest.to_path_buf());
    }
    let jpg = dest.with_extension("jpg");
    let tmp_jpg = dest.with_extension("jpg.tmp");
    let mut file = std::fs::File::create(&tmp_jpg)?;
    image::codecs::jpeg::JpegEncoder::new_with_quality(&mut file, 78).encode_image(&image)?;
    drop(file);
    std::fs::rename(&tmp_jpg, &jpg)?;
    Ok(jpg)
}

fn save_pdf_placeholder(
    dest: &FsPath,
) -> Result<PathBuf, Box<dyn std::error::Error + Send + Sync>> {
    let mut image = image::RgbImage::from_pixel(400, 300, image::Rgb([40, 30, 30]));
    draw_pdf_placeholder_text(&mut image, "PDF", 108, [220, 180, 160]);
    // Deliberately differs from Python's poppler wording: this server uses PDFium.
    draw_pdf_placeholder_text(&mut image, "pdfium unavailable", 150, [160, 130, 120]);
    draw_pdf_placeholder_text(&mut image, "thumbnails disabled", 182, [140, 110, 100]);
    let jpg = dest.with_extension("jpg");
    let tmp = dest.with_extension("jpg.tmp");
    let mut file = std::fs::File::create(&tmp)?;
    image::codecs::jpeg::JpegEncoder::new_with_quality(&mut file, 85).encode_image(&image)?;
    drop(file);
    std::fs::rename(&tmp, &jpg)?;
    Ok(jpg)
}

/// The glyph coordinates below are narrowed from `usize` only to be compared
/// against the image bounds immediately: the `x >= 0 && y >= 0 && x < width &&
/// y < height` guard around `put_pixel` means a label long enough to overflow
/// `i32` draws nothing rather than writing outside the image.
#[allow(clippy::cast_possible_truncation)]
fn draw_pdf_placeholder_text(
    image: &mut image::RgbImage,
    text: &str,
    center_y: u32,
    color: [u8; 3],
) {
    let start_x = (image.width() as i32 - text.chars().count() as i32 * 8) / 2;
    let start_y = center_y as i32 - 4;
    for (offset, character) in text.chars().enumerate() {
        if let Some(glyph) = BASIC_FONTS.get(character) {
            for (row, bits) in glyph.iter().enumerate() {
                for column in 0..8 {
                    if bits & (1 << column) != 0 {
                        let x = start_x + offset as i32 * 8 + column;
                        let y = start_y + row as i32;
                        if x >= 0 && y >= 0 && x < image.width() as i32 && y < image.height() as i32
                        {
                            image.put_pixel(
                                crate::num::sat_u32(f64::from(x)),
                                crate::num::sat_u32(f64::from(y)),
                                image::Rgb(color),
                            );
                        }
                    }
                }
            }
        }
    }
}

/// Resolve the preview file path for a given source path + mtime.
/// Returns (path, mime) or None on error/unsupported.
async fn resolve_preview_path(
    state: &SharedState,
    path_str: &str,
    mtime: i64,
) -> Option<(PathBuf, &'static str)> {
    let (path_str, mtime) = servable_path(state, path_str, mtime).await.ok()?;
    let path_str = &path_str;
    let ext = path_str
        .rsplit('.')
        .next()
        .unwrap_or("")
        .to_ascii_lowercase();
    if is_audio_or_video(&ext) {
        let p = PathBuf::from(path_str);
        tokio::fs::metadata(&p).await.ok()?;
        return Some((p, guess_mime(path_str)));
    }
    if matches!(ext.as_str(), "heif" | "heic" | "jxl") {
        return None;
    }
    let cache_key = {
        let mut h = Sha256::new();
        h.update(format!("preview:{path_str}:{mtime}").as_bytes());
        hex::encode(&h.finalize()[..16])
    };
    let cache_dir = state.config.cache_dir.join("previews");
    for cache_ext in ["webp", "jpg"] {
        let p = cache_dir.join(format!("{cache_key}.{cache_ext}"));
        if tokio::fs::metadata(&p).await.is_ok() {
            let mime = if cache_ext == "webp" {
                "image/webp"
            } else {
                "image/jpeg"
            };
            return Some((p, mime));
        }
    }
    let file_path = PathBuf::from(path_str);
    let Ok(meta) = tokio::fs::metadata(&file_path).await else {
        return None;
    };
    if meta.len() < 200 * 1024 && ext != "pdf" {
        return Some((file_path, guess_mime(path_str)));
    }
    let _ = tokio::fs::create_dir_all(&cache_dir).await;
    let dest = cache_dir.join(format!("{cache_key}.webp"));
    let src = file_path.clone();
    match tokio::task::spawn_blocking(move || generate_preview_sync(&src, &dest)).await {
        Ok(Ok(generated)) if std::fs::metadata(&generated).is_ok() => {
            let mime = match generated.extension().and_then(|e| e.to_str()) {
                Some("webp") => "image/webp",
                _ => "image/jpeg",
            };
            Some((generated, mime))
        }
        _ => Some((file_path, guess_mime(path_str))),
    }
}

pub async fn thumbnails_warmup(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> Response {
    let data = match serde_json::from_slice::<serde_json::Value>(&body) {
        Ok(serde_json::Value::Object(data)) => data,
        Ok(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({
                    "error": "JSON object body is required",
                    "code": "invalid_json_object"
                })),
            )
                .into_response()
        }
        Err(_) => {
            return (
                StatusCode::BAD_REQUEST,
                Json(serde_json::json!({
                    "error": "Invalid JSON body",
                    "code": "invalid_json"
                })),
            )
                .into_response()
        }
    };
    let Some(values) = data
        .get("file_ids")
        .and_then(serde_json::Value::as_array)
        .filter(|values| !values.is_empty())
    else {
        return (
            StatusCode::BAD_REQUEST,
            Json(serde_json::json!({"error": "file_ids required"})),
        )
            .into_response();
    };
    let file_ids: Vec<i64> = values
        .iter()
        .take(2000)
        .filter_map(|value| match value {
            serde_json::Value::Number(number) => {
                number.as_i64().filter(|id| *id > 0).or_else(|| {
                    number
                        .as_f64()
                        .filter(|id| *id > 0.0)
                        .map(crate::num::sat_i64)
                })
            }
            serde_json::Value::Bool(true) => Some(1),
            _ => None,
        })
        .collect();
    let count = file_ids.len();
    let mut key_ids = file_ids.iter().copied().take(100).collect::<Vec<_>>();
    key_ids.sort_unstable();
    let mut hasher = Sha256::new();
    for id in key_ids {
        hasher.update(id.to_le_bytes());
    }
    let job_id = format!("thumbnail-warmup:{}", hex::encode(hasher.finalize()));
    let started = state
        .job_manager
        .start_if_idle(&job_id, "Thumbnail warmup")
        .is_some();
    if started {
        let state = state.clone();
        tokio::spawn(async move {
            for id in file_ids {
                if let Ok((path, mtime)) = lookup_file(&state, id).await {
                    let _ = resolve_preview_path(&state, &path, mtime).await;
                }
            }
            state.job_manager.finish(&job_id, None, None);
        });
    }
    (
        StatusCode::ACCEPTED,
        Json(serde_json::json!({"ok": true, "started": started, "count": count})),
    )
        .into_response()
}

pub async fn thumbnails_batch(
    State(state): State<SharedState>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    let ids: Vec<i64> = body
        .get("ids")
        .and_then(|v| v.as_array())
        .map(|arr| arr.iter().filter_map(|v| v.as_i64()).take(50).collect())
        .unwrap_or_default();

    let mut handles = Vec::with_capacity(ids.len());
    for &id in &ids {
        let state2 = state.clone();
        handles.push(tokio::spawn(async move {
            let (path_str, mtime) = lookup_file(&state2, id).await.ok()?;
            let (preview_path, mime) = resolve_preview_path(&state2, &path_str, mtime).await?;
            let bytes = tokio::fs::read(&preview_path).await.ok()?;
            Some((
                id,
                format!("data:{mime};base64,{}", STANDARD.encode(&bytes)),
            ))
        }));
    }

    let mut thumbnails = serde_json::Map::new();
    for handle in handles {
        if let Ok(Some((id, data_url))) = handle.await {
            thumbnails.insert(id.to_string(), serde_json::Value::String(data_url));
        }
    }
    Json(serde_json::json!({ "thumbnails": thumbnails })).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use image::GenericImageView as _;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    static PDFIUM_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    async fn test_state_with_cache(cache_dir: PathBuf) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL UNIQUE,
               mtime INTEGER NOT NULL
             );
             INSERT INTO files(id, path, mtime) VALUES
               (1, '/z.png', 300),
               (2, '/a.png', 100);",
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
                    app_config: serde_json::json!({}),
                    cache_dir,
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

    async fn test_state() -> SharedState {
        test_state_with_cache(PathBuf::from(".")).await
    }

    async fn response_json(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    /// Build `<dir>/bundle.zip` holding one entry with the given name/bytes.
    fn write_zip(dir: &std::path::Path, entry: &str, bytes: &[u8]) -> String {
        use std::io::Write as _;
        let path = dir.join("bundle.zip");
        let mut writer = zip::ZipWriter::new(std::fs::File::create(&path).unwrap());
        writer
            .start_file(
                entry,
                zip::write::SimpleFileOptions::default()
                    .compression_method(zip::CompressionMethod::Deflated),
            )
            .unwrap();
        writer.write_all(bytes).unwrap();
        writer.finish().unwrap();
        path.to_string_lossy().into_owned()
    }

    fn write_sevenz(dir: &std::path::Path, entry: &str, bytes: &[u8]) -> String {
        let archive = dir.join("archive.7z");
        let mut writer = sevenz_rust2::ArchiveWriter::create(&archive).unwrap();
        writer
            .push_archive_entry(
                sevenz_rust2::ArchiveEntry::new_file(entry),
                Some(std::io::Cursor::new(bytes)),
            )
            .unwrap();
        writer.finish().unwrap();
        archive.to_string_lossy().into_owned()
    }

    fn write_sevenz_with_method(
        dir: &std::path::Path,
        name: &str,
        method: sevenz_rust2::EncoderMethod,
    ) -> String {
        let archive = dir.join(format!("{name}.7z"));
        let mut writer = sevenz_rust2::ArchiveWriter::create(&archive).unwrap();
        writer.set_content_methods(vec![method.into()]);
        writer
            .push_archive_entry(
                sevenz_rust2::ArchiveEntry::new_file("codec.bin"),
                Some(std::io::Cursor::new(b"codec round trip")),
            )
            .unwrap();
        writer.finish().unwrap();
        archive.to_string_lossy().into_owned()
    }

    fn write_sevenz_directory_collision(dir: &std::path::Path) -> String {
        let archive = dir.join("directory-collision.7z");
        let mut writer = sevenz_rust2::ArchiveWriter::create(&archive).unwrap();
        writer
            .push_archive_entry(
                sevenz_rust2::ArchiveEntry::new_directory("img.png/"),
                None::<std::io::Cursor<&[u8]>>,
            )
            .unwrap();
        writer
            .push_archive_entry(
                sevenz_rust2::ArchiveEntry::new_file("sub/img.png"),
                Some(std::io::Cursor::new(b"REAL")),
            )
            .unwrap();
        writer.finish().unwrap();
        archive.to_string_lossy().into_owned()
    }

    /// Build `<dir>/<name>` holding the given entries, each Deflated.
    fn write_zip_multi(dir: &std::path::Path, name: &str, entries: &[(&str, &[u8])]) -> String {
        use std::io::Write as _;
        let path = dir.join(name);
        let mut writer = zip::ZipWriter::new(std::fs::File::create(&path).unwrap());
        for (entry, bytes) in entries {
            writer
                .start_file(
                    *entry,
                    zip::write::SimpleFileOptions::default()
                        .compression_method(zip::CompressionMethod::Deflated),
                )
                .unwrap();
            writer.write_all(bytes).unwrap();
        }
        writer.finish().unwrap();
        path.to_string_lossy().into_owned()
    }

    /// Build `<dir>/outer.zip` containing `nested_name`, itself a ZIP holding
    /// `inner_entries`. Mirrors what `list_images_in_zip` indexes one level deep.
    fn write_nested_zip(
        dir: &std::path::Path,
        nested_name: &str,
        inner_entries: &[(&str, &[u8])],
    ) -> String {
        let staging = dir.join("staging");
        std::fs::create_dir_all(&staging).unwrap();
        let inner = write_zip_multi(&staging, "inner_build.zip", inner_entries);
        let inner_bytes = std::fs::read(&inner).unwrap();
        write_zip_multi(dir, "outer.zip", &[(nested_name, &inner_bytes)])
    }

    #[test]
    fn split_archive_path_ignores_bangs_outside_an_archive_boundary() {
        // The production case this replaced a bare `contains('!')` for.
        assert_eq!(split_archive_path("/x/エルフ! [cg]/img.jpg"), None);
        assert_eq!(
            split_archive_path("/x/bundle.zip!dir/img.png"),
            Some(("/x/bundle.zip", "dir/img.png"))
        );
        // First boundary wins, so the nested remainder stays intact.
        assert_eq!(
            split_archive_path("/x/outer.zip!inner.zip!img.png"),
            Some(("/x/outer.zip", "inner.zip!img.png"))
        );
        assert_eq!(
            split_archive_path("/x/pack.7z!img.png"),
            Some(("/x/pack.7z", "img.png"))
        );
    }

    #[test]
    fn resolve_zip_target_follows_pythons_three_step_relaxation() {
        let names = vec!["dir/img.png".to_string(), "other/pic.jpg".to_string()];
        // 1. backslashes normalized
        assert_eq!(
            resolve_zip_target(&names, "dir\\img.png"),
            Some("dir/img.png".to_string())
        );
        // 2. exact
        assert_eq!(
            resolve_zip_target(&names, "dir/img.png"),
            Some("dir/img.png".to_string())
        );
        // 3. basename fallback when the stored directory no longer matches
        assert_eq!(
            resolve_zip_target(&names, "moved/pic.jpg"),
            Some("other/pic.jpg".to_string())
        );
        assert_eq!(resolve_zip_target(&names, "absent.png"), None);
        assert_eq!(
            resolve_zip_target(
                &["one/pic.jpg".into(), "two/pic.jpg".into()],
                "moved/pic.jpg"
            ),
            Some("one/pic.jpg".into())
        );
        assert_eq!(
            resolve_zip_target(&["dir/é.png".into()], "dir/e\u{301}.png"),
            None
        );
    }

    #[test]
    fn resolve_entry_name_matches_python_normalization_and_unique_basename() {
        let names = vec!["dir/e\u{301}.png".to_string(), "other/pic.jpg".to_string()];
        assert_eq!(
            resolve_entry_name(&names, "./dir/é.png\0"),
            Some("dir/e\u{301}.png".to_string())
        );
        assert_eq!(
            resolve_entry_name(&names, "../moved/pic.jpg"),
            Some("other/pic.jpg".to_string())
        );
        assert_eq!(
            resolve_entry_name(
                &["one/pic.jpg".to_string(), "two/pic.jpg".to_string()],
                "moved/pic.jpg"
            ),
            None
        );
        assert_eq!(resolve_entry_name(&["/".to_string()], "../"), None);
    }

    #[test]
    fn resolve_entry_name_uses_nfkc_variants() {
        assert_eq!(
            resolve_entry_name(&["file.png".into()], "ﬁle.png"),
            Some("file.png".into())
        );
    }

    #[test]
    fn resolve_entry_name_keeps_first_variant_collision_in_name_order() {
        let decomposed = "e\u{301}.png".to_string();
        let composed = "é.png".to_string();
        assert_eq!(
            resolve_entry_name(&[decomposed.clone(), composed.clone()], "./é.png"),
            // The normalized query's base is the shared NFC variant.
            Some(decomposed.clone())
        );
        assert_eq!(
            resolve_entry_name(&[composed.clone(), decomposed.clone()], "./é.png"),
            Some(composed.clone())
        );
        // This pins variant ordering, not a separate correctness case.
        for _ in 0..8 {
            assert_eq!(
                resolve_entry_name(&[composed.clone(), decomposed.clone()], "./é.png"),
                Some(composed.clone())
            );
        }
    }

    #[test]
    fn resolve_entry_name_drops_parent_segments_without_collapsing_paths() {
        assert_eq!(
            resolve_entry_name(&["a/b.png".into(), "other/b.png".into()], "a/../b.png"),
            Some("a/b.png".into())
        );
    }

    #[test]
    fn sevenz_size_cap_rejects_before_extraction() {
        let entries = vec![SevenzEntry {
            path: "large.png".into(),
            size: ARCHIVE_MAX_ENTRY_SIZE + 1,
            crc: None,
            is_directory: false,
        }];
        assert!(resolve_sevenz_entry(&entries, "large.png", ARCHIVE_MAX_ENTRY_SIZE).is_none());
    }

    #[test]
    fn cp437_repair_uses_the_real_cp437_table() {
        assert_eq!(CP437_EXTENDED.chars().next(), Some('Ç')); // 0x80
        assert_eq!(CP437_EXTENDED.chars().nth(0xE0 - 128), Some('α'));
        assert_eq!(CP437_EXTENDED.chars().nth(0xFF - 128), Some('\u{00a0}'));
        assert_eq!(
            resolve_entry_name(&["画像.png".into()], "ëµæ£.png"),
            Some("画像.png".into())
        );
    }

    #[test]
    fn cp437_repair_rejects_invalid_fallback_decodes() {
        assert!(repair_cp437_name("é")
            .iter()
            .all(|name| !name.contains('\u{fffd}')));
        assert!(repair_cp437_name("é").is_empty());
    }

    #[test]
    fn archive_entry_cap_matches_python() {
        // core/infra_core/timeout.py:28 — the production calls pass this value,
        // while the bound-enforcement tests below use a small explicit cap.
        assert_eq!(ARCHIVE_MAX_ENTRY_SIZE, 512 * 1024 * 1024);
    }

    /// Run the whole cache+extract path the routes use, into `dir`.
    fn cached(zip_path: &str, inner: &str, dir: &std::path::Path, max: u64) -> Option<PathBuf> {
        cached_zip_member(zip_path, inner, "db/path.zip!img.png", 100, dir, "png", max)
    }

    #[test]
    fn extract_refuses_an_entry_longer_than_the_cap() {
        let dir = tempfile::tempdir().unwrap();
        let out = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "img.png", b"0123456789");

        // A declared size over the cap is rejected outright...
        assert!(cached(&zip_path, "img.png", out.path(), 4).is_none());
        let published: Vec<_> = std::fs::read_dir(out.path())
            .unwrap()
            .filter_map(|e| e.ok())
            .map(|e| e.file_name().to_string_lossy().into_owned())
            .collect();
        // ...publishing nothing and leaving no `.part` debris behind.
        assert!(published.is_empty(), "cache dir not empty: {published:?}");

        // A cap that fits still succeeds, so the check is not vacuous.
        let dest = cached(&zip_path, "img.png", out.path(), 10).expect("extracted");
        assert_eq!(std::fs::read(&dest).unwrap(), b"0123456789");
    }

    /// Overwrite the uncompressed-size field in both the local file header and
    /// the central directory entry, leaving the deflate stream untouched. The
    /// archive then *declares* `declared` bytes while inflating to its real
    /// length — the shape a size check on `entry.size()` alone cannot catch.

    #[test]
    fn temp_sibling_is_unique_per_attempt() {
        // Two extractions racing on one destination must not share a `.part`
        // path, or either can publish the other's half-written file.
        let dest = std::path::Path::new("/cache/zip_members/abc.png");
        let a = temp_sibling(dest);
        let b = temp_sibling(dest);
        assert_ne!(a, b);
        assert_eq!(a.parent(), dest.parent());
        assert!(a.to_string_lossy().ends_with(".part"));
    }

    #[test]
    fn is_nested_zip_only_defers_for_a_nested_zip() {
        // Python `_is_nested` splits at the first `!` and requires `.zip`.
        assert!(is_nested_zip("inner.zip!dir/img.png"));
        assert!(is_nested_zip("Inner.ZIP!img.png"));
        // A member legitimately named `foo.7z!image.jpg` is NOT nested; Python
        // reads it straight out of the outer archive.
        assert!(!is_nested_zip("dir/foo.7z!image.jpg"));
        assert!(!is_nested_zip("dir/img.png"));
    }

    #[tokio::test]
    async fn cache_key_tracks_the_archive_not_just_the_member_timestamp() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let zip_path = write_zip(dir.path(), "img.png", b"FIRST");
        let member = format!("{zip_path}!img.png");
        let (first, _) = servable_path(&state, &member, 100).await.unwrap();
        assert_eq!(std::fs::read(&first).unwrap(), b"FIRST");

        // Rewrite the archive with different content. The DB mtime is the
        // member's stored timestamp and does not change, so only the archive's
        // own identity can invalidate the cache.
        let zip_path2 = write_zip(dir.path(), "img.png", b"SECOND-LONGER");
        assert_eq!(zip_path2, zip_path);
        let (second, _) = servable_path(&state, &member, 100).await.unwrap();
        assert_ne!(second, first, "a rewritten archive must not reuse the key");
        assert_eq!(std::fs::read(&second).unwrap(), b"SECOND-LONGER");
    }

    /// CRC-32 (reflected, poly 0xEDB88320) with init 0 and no final xor.
    fn crc32_bare(data: &[u8]) -> u32 {
        let mut crc = 0u32;
        for &byte in data {
            crc ^= u32::from(byte);
            for _ in 0..8 {
                crc = if crc & 1 != 0 {
                    (crc >> 1) ^ 0xEDB8_8320
                } else {
                    crc >> 1
                };
            }
        }
        crc
    }

    /// Build a second message of the same length as `base` that shares its
    /// CRC-32 — a *genuine* collision, not a forged header field.
    ///
    /// CRC-32 is linear: for equal-length messages the difference of their CRCs
    /// is the bare CRC of their XOR difference. So any difference `d` with
    /// `crc32_bare(d) == 0` yields a colliding partner, and appending the bare
    /// remainder of a prefix produces exactly such a `d`.
    fn crc_collision_partner(base: &[u8]) -> Vec<u8> {
        assert!(base.len() >= 8, "need room for a 4-byte prefix + remainder");
        let mut d = vec![0u8; base.len()];
        d[0..4].copy_from_slice(&[0x01, 0x02, 0x03, 0x04]);
        let remainder = crc32_bare(&d[0..4]);
        d[4..8].copy_from_slice(&remainder.to_le_bytes());
        assert_eq!(
            crc32_bare(&d[0..8]),
            0,
            "difference must have a zero bare CRC for the collision to hold"
        );
        base.iter().zip(&d).map(|(b, x)| b ^ x).collect()
    }

    #[test]
    fn cache_key_moves_for_every_exposed_header_field() {
        // `entry_header` is what the key sees. Perturb one field at a time in
        // the rendered form and require a different key each time: a field the
        // key ignores is a field an archive can change while the viewer keeps
        // the previously extracted bytes.
        let base = "name=img.png|method=Deflated|enc=false|csize=12|size=10\
                    |crc=deadbeef|mtime=None|mode=None";
        let variants = [
            "name=other.png|method=Deflated|enc=false|csize=12|size=10|crc=deadbeef|mtime=None|mode=None",
            "name=img.png|method=Stored|enc=false|csize=12|size=10|crc=deadbeef|mtime=None|mode=None",
            "name=img.png|method=Deflated|enc=true|csize=12|size=10|crc=deadbeef|mtime=None|mode=None",
            "name=img.png|method=Deflated|enc=false|csize=13|size=10|crc=deadbeef|mtime=None|mode=None",
            "name=img.png|method=Deflated|enc=false|csize=12|size=11|crc=deadbeef|mtime=None|mode=None",
            "name=img.png|method=Deflated|enc=false|csize=12|size=10|crc=deadbeee|mtime=None|mode=None",
            "name=img.png|method=Deflated|enc=false|csize=12|size=10|crc=deadbeef|mtime=Some(x)|mode=None",
            "name=img.png|method=Deflated|enc=false|csize=12|size=10|crc=deadbeef|mtime=None|mode=Some(420)",
        ];
        let key_of = |header: &str| member_cache_key("row", 100, "storeddigest", header);
        let base_key = key_of(base);
        for variant in variants {
            assert_ne!(
                key_of(variant),
                base_key,
                "key ignored a header change: {variant}"
            );
        }
        // The stored-bytes digest must matter too.
        assert_ne!(
            member_cache_key("row", 100, "other", base),
            base_key,
            "key ignored the stored bytes"
        );
    }

    #[test]
    fn entry_header_reports_the_compression_method() {
        // Ties `entry_header` to a real archive, so the string the previous test
        // perturbs is the string production actually builds.
        let dir = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "img.png", b"0123456789");
        let mut zip = zip::ZipArchive::new(std::fs::File::open(&zip_path).unwrap()).unwrap();
        let header = entry_header(&zip.by_index_raw(0).unwrap());
        assert!(header.contains("name=img.png"), "{header}");
        assert!(header.contains("method=Deflated"), "{header}");
        assert!(header.contains("size=10"), "{header}");
    }

    #[test]
    fn stored_read_cap_allows_deflate_expansion_but_stays_bounded() {
        // A tiny entry's deflate stream exceeds its content, so the cap must sit
        // above `max` — but it must remain finite, or a small declared size with
        // a huge stored extent would be read in full on every request.
        assert!(stored_read_cap(10) > 10);
        assert!(stored_read_cap(ARCHIVE_MAX_ENTRY_SIZE) > ARCHIVE_MAX_ENTRY_SIZE);
        assert!(stored_read_cap(ARCHIVE_MAX_ENTRY_SIZE) < ARCHIVE_MAX_ENTRY_SIZE * 2);
        assert_eq!(stored_read_cap(u64::MAX), u64::MAX, "must not overflow");
    }

    #[test]
    fn stored_bytes_digest_refuses_to_read_past_the_cap() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "img.png", b"0123456789");
        let mut zip = zip::ZipArchive::new(std::fs::File::open(&zip_path).unwrap()).unwrap();
        assert!(
            stored_bytes_digest(&mut zip, 0, 1).is_none(),
            "a cap below the stored extent must stop the read"
        );
        let mut zip = zip::ZipArchive::new(std::fs::File::open(&zip_path).unwrap()).unwrap();
        assert!(
            stored_bytes_digest(&mut zip, 0, 1 << 20).is_some(),
            "a generous cap must still hash the entry"
        );
    }

    #[tokio::test]
    async fn sevenz_members_have_distinct_cache_entries() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let archive = write_sevenz(dir.path(), "first.png", b"FIRST");
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let first = servable_path(&state, &format!("{archive}!first.png"), 100)
            .await
            .expect("first extracted")
            .0;

        // CRC-32 has no collision resistance and both CRC and size come from the archive.
        // Member paths distinguish entries while archive metadata invalidates ordinary edits.
        let second_archive = write_sevenz(dir.path(), "second.png", b"SECOND");
        let second = servable_path(&state, &format!("{second_archive}!second.png"), 100)
            .await
            .expect("second extracted")
            .0;
        assert_ne!(first, second);
    }

    #[tokio::test]
    async fn replacing_an_archive_invalidates_the_client_etag() {
        // Same-length replacement is the dangerous shape: the DB mtime is the
        // member's stored timestamp and does not move, and the extracted length
        // is unchanged, so an ETag built from those two alone would still match
        // and answer 304 with the previous image.
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "img.png", b"AAAAA");
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        sqlx::query("INSERT INTO files(id, path, mtime) VALUES (11, ?, 100)")
            .bind(format!("{zip_path}!img.png"))
            .execute(&state.db_read)
            .await
            .unwrap();

        let first = serve_original(State(state.clone()), Path(11), HeaderMap::new()).await;
        assert_eq!(first.status(), StatusCode::OK);
        let etag = first
            .headers()
            .get(header::ETAG)
            .expect("etag")
            .to_str()
            .unwrap()
            .to_string();
        let body = to_bytes(first.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"AAAAA");

        // The client comes back with the ETag it was given.
        let mut conditional = HeaderMap::new();
        conditional.insert(header::IF_NONE_MATCH, etag.parse().unwrap());
        let unchanged = serve_original(State(state.clone()), Path(11), conditional.clone()).await;
        assert_eq!(
            unchanged.status(),
            StatusCode::NOT_MODIFIED,
            "an unchanged archive should still revalidate cheaply"
        );

        // Replace the archive with different content of the same length.
        let replaced = write_zip(dir.path(), "img.png", b"BBBBB");
        assert_eq!(replaced, zip_path);

        let after = serve_original(State(state), Path(11), conditional).await;
        assert_eq!(
            after.status(),
            StatusCode::OK,
            "replaced content must not be answered with 304"
        );
        let body = to_bytes(after.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"BBBBB");
    }

    #[tokio::test]
    async fn servable_path_passes_ordinary_paths_through_untouched() {
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        // A `!` in the filename must not be mistaken for an archive boundary,
        // and the DB mtime must pass through untouched.
        for path in ["/x/plain.png", "/x/エルフ! [cg]/img.jpg"] {
            assert_eq!(
                servable_path(&state, path, 100).await,
                Ok((path.to_string(), 100))
            );
        }
    }

    #[tokio::test]
    async fn servable_path_extracts_a_zip_member_into_the_cache() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "dir/img.png", b"PNGDATA");
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let member = format!("{zip_path}!dir/img.png");
        let (resolved, resolved_mtime) = servable_path(&state, &member, 100)
            .await
            .expect("extracted");
        assert_eq!(std::fs::read(&resolved).unwrap(), b"PNGDATA");
        assert!(
            resolved.ends_with(".png"),
            "extension preserved: {resolved}"
        );
        assert!(
            std::path::Path::new(&resolved).starts_with(cache.path().join("zip_members")),
            "written inside the cache dir: {resolved}"
        );
        // The reported mtime describes the extracted file, not the DB row.
        assert_ne!(resolved_mtime, 100, "extracted mtime, not the stored one");
        // Second call is served from cache and must agree.
        assert_eq!(
            servable_path(&state, &member, 100).await,
            Ok((resolved, resolved_mtime))
        );
    }

    #[tokio::test]
    async fn pdf_thumbnail_renders_the_fourth_page_at_thumbnail_size() {
        let _pdfium = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let root = FsPath::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let Some(library_dir) = crate::testing::pdfium::library_dir_or_skip(
            "pdf_thumbnail_renders_the_fourth_page_at_thumbnail_size",
        ) else {
            return;
        };
        let _ = root;
        let source =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/pdf/four_pages.pdf");
        let rendered = render_pdf_page(&source, &library_dir, false).expect("rendered at 144 DPI");
        assert!(rendered.width() > 280 || rendered.height() > 280);
        let cache = tempfile::tempdir().unwrap();
        let generated = save_pdf_thumbnail(rendered, &cache.path().join("preview.webp")).unwrap();
        let image = image::open(generated).unwrap().to_rgb8();
        assert!(image.width() <= 280 && image.height() <= 280);
        let pixel = image.get_pixel(image.width() / 2, image.height() / 2).0;
        assert!(
            pixel[0] > 180 && pixel[1] > 180 && pixel[2] < 100,
            "{pixel:?}"
        );
    }

    /// The whole point of the shared binding: pdfium is a one-shot per process,
    /// so a second render used to fail and serve a placeholder. Two renders in
    /// one process is exactly the production sequence (two PDFs in a library).
    #[test]
    fn a_second_pdf_still_renders_in_the_same_process() {
        let _pdfium = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let Some(library_dir) = crate::testing::pdfium::library_dir_or_skip(
            "a_second_pdf_still_renders_in_the_same_process",
        ) else {
            return;
        };
        let fixtures = FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/pdf");
        let first = render_pdf_page(&fixtures.join("four_pages.pdf"), &library_dir, false);
        assert!(first.is_some(), "first render");
        let second = render_pdf_page(&fixtures.join("four_pages.pdf"), &library_dir, false);
        assert!(second.is_some(), "second render in the same process");
    }

    /// The shared binding must not answer for a directory that has no library:
    /// `generate_pdf_thumbnail_sync` relies on `None` to draw its placeholder,
    /// and returning the cached instance would make that path unreachable.
    #[test]
    fn a_directory_without_pdfium_never_binds() {
        let _pdfium = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let missing = tempfile::tempdir().unwrap();
        assert!(bind_pdfium(missing.path(), false).is_none());
    }

    #[tokio::test]
    async fn pdf_preview_stays_raw_while_thumbnail_is_an_image() {
        let _pdfium = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let source =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/pdf/four_pages.pdf");
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        sqlx::query("INSERT INTO files(id, path, mtime) VALUES (99, ?, 100)")
            .bind(source.to_string_lossy().into_owned())
            .execute(&state.db_read)
            .await
            .unwrap();

        let preview = serve_preview(State(state.clone()), Path(99), HeaderMap::new()).await;
        assert_eq!(
            preview.headers().get(header::CONTENT_TYPE).unwrap(),
            "application/pdf"
        );
        let thumbnail = serve_thumbnail(State(state), Path(99), HeaderMap::new()).await;
        assert!(thumbnail
            .headers()
            .get(header::CONTENT_TYPE)
            .unwrap()
            .to_str()
            .unwrap()
            .starts_with("image/"));
    }

    #[test]
    fn pdf_thumbnail_uses_a_placeholder_for_short_corrupt_or_unavailable_pdfium() {
        let _pdfium = PDFIUM_TEST_LOCK
            .lock()
            .unwrap_or_else(|poisoned| poisoned.into_inner());
        let root = FsPath::new(env!("CARGO_MANIFEST_DIR"))
            .ancestors()
            .nth(2)
            .unwrap();
        let fixtures = FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/pdf");
        for (name, library_dir) in [
            ("one_page.pdf", root.join("vendor/pdfium/linux-x64")),
            ("corrupt.pdf", root.join("vendor/pdfium/linux-x64")),
            ("four_pages.pdf", root.join("missing-pdfium")),
        ] {
            let cache = tempfile::tempdir().unwrap();
            let generated = generate_pdf_thumbnail_sync(
                &fixtures.join(name),
                &cache.path().join("preview.webp"),
                &library_dir,
                false,
            )
            .unwrap();
            let image = image::open(generated).unwrap();
            assert_eq!(image.dimensions(), (400, 300), "{name}");
        }
    }

    #[tokio::test]
    async fn sevenz_optional_codecs_round_trip() {
        for (name, method) in [
            ("bzip2", sevenz_rust2::EncoderMethod::BZIP2),
            ("brotli", sevenz_rust2::EncoderMethod::BROTLI),
            ("deflate", sevenz_rust2::EncoderMethod::DEFLATE),
            ("lz4", sevenz_rust2::EncoderMethod::LZ4),
            ("ppmd", sevenz_rust2::EncoderMethod::PPMD),
            ("zstd", sevenz_rust2::EncoderMethod::ZSTD),
        ] {
            let dir = tempfile::tempdir().unwrap();
            let cache = tempfile::tempdir().unwrap();
            let archive = write_sevenz_with_method(dir.path(), name, method);
            let state = test_state_with_cache(cache.path().to_path_buf()).await;
            let (resolved, _) = servable_path(&state, &format!("{archive}!codec.bin"), 100)
                .await
                .unwrap_or_else(|_| panic!("{name} did not round-trip"));
            assert_eq!(
                std::fs::read(resolved).unwrap(),
                b"codec round trip",
                "{name}"
            );
        }
    }

    #[tokio::test]
    async fn servable_path_extracts_a_rar_member() {
        let archive =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rar/version.rar");
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let (resolved, _) = servable_path(&state, &format!("{}!VERSION", archive.display()), 100)
            .await
            .expect("extracted");
        assert_eq!(std::fs::read(resolved).unwrap(), b"unrar-0.4.0");
    }

    #[tokio::test]
    async fn rar_members_use_unicode_entry_resolution() {
        let archive =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rar/unicode.rar");
        let cache = tempfile::tempdir().unwrap();
        let resolved = cached_rar_member(
            &archive.to_string_lossy(),
            "te...\u{2015}st✌",
            "row",
            100,
            cache.path(),
            "bin",
            ARCHIVE_MAX_ENTRY_SIZE,
        )
        .await
        .expect("Unicode-normalized entry extracted");
        assert!(!std::fs::read(resolved).unwrap().is_empty());
    }

    #[test]
    fn rar_directory_names_do_not_shadow_files() {
        let entries = [
            RarEntry {
                path: "dir/img.png".to_string(),
                size: 0,
                is_directory: true,
            },
            RarEntry {
                path: "other/img.png".to_string(),
                size: 4,
                is_directory: false,
            },
        ];
        assert_eq!(
            resolve_rar_entry(&entries, "img.png", 4).map(|entry| entry.path.as_str()),
            Some("other/img.png")
        );
    }

    #[tokio::test]
    async fn rar_fixture_parses_directory_flags_and_excludes_directories_from_resolution() {
        let archive =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rar/rar3-subdirs.rar");
        let entries = list_rar_entries(&archive).expect("listed");
        let directories: HashSet<String> = entries
            .iter()
            .filter(|entry| entry.is_directory)
            // UnRAR strips the archive's trailing slash from directory header names.
            .map(|entry| format!("{}/", entry.path.trim_end_matches('/')))
            .collect();
        assert_eq!(
            directories,
            [
                "sub/",
                "sub/dir1/",
                "sub/dir2/",
                "sub/empty/",
                "sub/with space/",
                "sub/üȵĩöḋè/",
            ]
            .into_iter()
            .map(str::to_owned)
            .collect()
        );
        assert_eq!(
            entries.iter().filter(|entry| !entry.is_directory).count(),
            4
        );
        assert!(resolve_rar_entry(&entries, "empty", ARCHIVE_MAX_ENTRY_SIZE).is_none());
        assert_eq!(
            resolve_rar_entry(&entries, "file.txt", ARCHIVE_MAX_ENTRY_SIZE)
                .map(|entry| entry.path.as_str()),
            Some("sub/üȵĩöḋè/file.txt")
        );

        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let (resolved, _) = servable_path(&state, &format!("{}!file.txt", archive.display()), 100)
            .await
            .expect("unique file basename extracted");
        assert_eq!(std::fs::metadata(resolved).unwrap().len(), 5);
    }

    // The synthetic collision pins the resolver filter; this fixture proves UnRAR sets the flag.
    #[tokio::test]
    async fn rar_size_cap_writes_no_cache_file() {
        let archive =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rar/version.rar");
        let cache = tempfile::tempdir().unwrap();
        let entries = list_rar_entries(&archive).expect("listed");
        assert!(resolve_rar_entry(&entries, "VERSION", 4).is_none());
        assert!(cached_rar_member(
            &archive.to_string_lossy(),
            "VERSION",
            "row",
            100,
            cache.path(),
            "bin",
            4,
        )
        .await
        .is_none());
        assert_eq!(std::fs::read_dir(cache.path()).unwrap().count(), 0);
    }

    #[tokio::test]
    async fn rar_member_cache_is_reused() {
        let archive =
            FsPath::new(env!("CARGO_MANIFEST_DIR")).join("tests/fixtures/rar/version.rar");
        let cache = tempfile::tempdir().unwrap();
        let first = cached_rar_member(
            &archive.to_string_lossy(),
            "VERSION",
            "row",
            100,
            cache.path(),
            "bin",
            ARCHIVE_MAX_ENTRY_SIZE,
        )
        .await
        .expect("extracted");
        let modified = std::fs::metadata(&first).unwrap().modified().unwrap();
        let second = cached_rar_member(
            &archive.to_string_lossy(),
            "VERSION",
            "row",
            100,
            cache.path(),
            "bin",
            ARCHIVE_MAX_ENTRY_SIZE,
        )
        .await
        .expect("cached");
        assert_eq!(first, second);
        assert_eq!(
            std::fs::metadata(second).unwrap().modified().unwrap(),
            modified
        );
    }

    #[tokio::test]
    async fn corrupt_or_absent_rar_reports_a_native_error() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let absent = dir.path().join("absent.rar");
        let corrupt = dir.path().join("corrupt.rar");
        std::fs::write(&corrupt, b"not a rar archive").unwrap();
        assert!(matches!(
            servable_path(&state, &format!("{}!file.png", absent.display()), 100).await,
            Err(ArchiveMemberError::MissingArchive)
        ));
        assert!(matches!(
            servable_path(&state, &format!("{}!file.png", corrupt.display()), 100).await,
            Err(ArchiveMemberError::ExtractionFailed)
        ));
    }

    #[tokio::test]
    async fn servable_path_extracts_a_sevenz_member_with_unicode_resolution() {
        let dir = tempfile::tempdir().unwrap();
        let archive = write_sevenz(dir.path(), "e\u{301}.png", b"7ZDATA");
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let member = format!("{archive}!é.png");
        let (resolved, _) = servable_path(&state, &member, 100)
            .await
            .expect("extracted");
        assert_eq!(std::fs::read(resolved).unwrap(), b"7ZDATA");
    }

    #[tokio::test]
    async fn sevenz_directory_basename_does_not_shadow_a_file() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let archive = write_sevenz_directory_collision(dir.path());
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let (resolved, _) = servable_path(&state, &format!("{archive}!img.png"), 100)
            .await
            .expect("file extracted");
        assert_eq!(std::fs::read(resolved).unwrap(), b"REAL");
    }

    #[tokio::test]
    async fn sevenz_parent_member_never_writes_outside_the_cache() {
        let dir = tempfile::tempdir().unwrap();
        let archive = write_sevenz(dir.path(), "../escape.png", b"ESCAPE");
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let (resolved, _) = servable_path(&state, &format!("{archive}!../escape.png"), 100)
            .await
            .expect("extracted");
        assert_eq!(std::fs::read(resolved).unwrap(), b"ESCAPE");
        assert_eq!(
            std::fs::read_dir(cache.path().join("zip_members"))
                .unwrap()
                .count(),
            1
        );
    }

    #[tokio::test]
    async fn sevenz_size_cap_writes_no_cache_file() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let archive = write_sevenz(dir.path(), "large.png", &[0; 101]);

        assert!(
            cached_sevenz_member(&archive, "large.png", "row", 100, cache.path(), "png", 100)
                .await
                .is_none()
        );
        assert_eq!(std::fs::read_dir(cache.path()).unwrap().count(), 0);
    }

    #[tokio::test]
    async fn sevenz_member_cache_is_reused() {
        let dir = tempfile::tempdir().unwrap();
        let archive = write_sevenz(dir.path(), "cached.png", b"CACHED");
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let member = format!("{archive}!cached.png");
        let (first, _) = servable_path(&state, &member, 100)
            .await
            .expect("extracted");
        let modified = std::fs::metadata(&first).unwrap().modified().unwrap();
        let (second, _) = servable_path(&state, &member, 100).await.expect("cached");

        assert_eq!(first, second);
        assert_eq!(
            std::fs::metadata(second).unwrap().modified().unwrap(),
            modified
        );
    }

    #[tokio::test]
    async fn corrupt_or_absent_sevenz_reports_a_native_error() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let absent = dir.path().join("absent.7z");
        let corrupt = dir.path().join("corrupt.7z");
        std::fs::write(&corrupt, b"not a 7z archive").unwrap();

        assert!(matches!(
            servable_path(&state, &format!("{}!file.png", absent.display()), 100).await,
            Err(ArchiveMemberError::MissingArchive)
        ));
        assert!(matches!(
            servable_path(&state, &format!("{}!file.png", corrupt.display()), 100).await,
            Err(ArchiveMemberError::ExtractionFailed)
        ));
    }

    #[tokio::test]
    async fn servable_path_reports_native_causes_for_unavailable_entries() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "dir/img.png", b"PNGDATA");
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        for member in [
            // Two levels. The scanner only ever produces one, and Python's
            // reader stops there too, so this stays a deferral.
            format!("{zip_path}!inner.zip!deeper.zip!img.png"),
            format!("{zip_path}!absent.png"), // no such entry
            "/x/pack.7z!img.png".to_string(), // archive absent
            "/x/pack.rar!img.png".to_string(),
            "/x/missing.zip!img.png".to_string(), // archive absent
        ] {
            assert!(
                servable_path(&state, &member, 100).await.is_err(),
                "expected native error for {member}"
            );
        }
    }

    #[test]
    fn nested_read_is_bounded_by_the_uncompressed_cap() {
        // The nested archive is held in memory, so an outer entry larger than
        // the cap must be refused rather than inflated. Python's
        // `_read_zip_entry_checked` applies the same bound before reading.
        //
        // The member is deliberately tiny: `max` bounds BOTH levels, so a
        // large member would trip the inner check instead and this would pass
        // for the wrong reason.
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let outer = write_nested_zip(dir.path(), "inner.zip", &[("img.png", b"P")]);
        let nested_len = {
            let mut z = zip::ZipArchive::new(std::fs::File::open(&outer).unwrap()).unwrap();
            let entry = z.by_name("inner.zip").unwrap();
            entry.size()
        };
        assert!(nested_len > 64, "fixture must exceed the tight cap");

        let call = |max| {
            cached_nested_zip_member(
                &outer,
                "inner.zip",
                "img.png",
                "db/outer.zip!inner.zip!img.png",
                100,
                cache.path(),
                "png",
                max,
            )
        };
        assert_eq!(call(64), None, "nested archive over the cap must defer");
        assert!(
            call(nested_len).is_some(),
            "exactly at the cap it is still served"
        );
    }

    #[tokio::test]
    async fn servable_path_extracts_a_nested_zip_member() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let outer = write_nested_zip(dir.path(), "inner.zip", &[("dir/img.png", b"NESTED")]);
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let member = format!("{outer}!inner.zip!dir/img.png");
        let (resolved, _) = servable_path(&state, &member, 100)
            .await
            .expect("extracted");
        assert_eq!(std::fs::read(&resolved).unwrap(), b"NESTED");
        assert!(resolved.ends_with(".png"), "extension from the member");
        assert!(
            std::path::Path::new(&resolved).starts_with(cache.path().join("zip_members")),
            "written inside the cache dir: {resolved}"
        );
    }

    #[tokio::test]
    async fn nested_extraction_does_not_fall_back_to_a_same_named_outer_entry() {
        // The whole hazard of nesting: the outer archive also holds `img.png`.
        // Serving that in place of the nested one is silent wrong content, so
        // this must come from *inside* `inner.zip`.
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let staging = dir.path().join("stage");
        std::fs::create_dir_all(&staging).unwrap();
        let inner = write_zip_multi(&staging, "inner_build.zip", &[("img.png", b"INNERBYTES")]);
        let inner_bytes = std::fs::read(&inner).unwrap();
        let outer = write_zip_multi(
            dir.path(),
            "outer.zip",
            &[("img.png", b"OUTERBYTES"), ("inner.zip", &inner_bytes)],
        );
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let (resolved, _) = servable_path(&state, &format!("{outer}!inner.zip!img.png"), 100)
            .await
            .expect("extracted");
        assert_eq!(std::fs::read(&resolved).unwrap(), b"INNERBYTES");
    }

    #[tokio::test]
    async fn nested_outer_name_uses_python_variant_resolution() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let outer = write_nested_zip(
            dir.path(),
            "pack/inne\u{301}r.zip",
            &[("img.png", b"NESTED")],
        );
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let (resolved, _) = servable_path(&state, &format!("{outer}!pack/innér.zip!img.png"), 100)
            .await
            .expect("Unicode-normalized outer name resolves");
        assert_eq!(std::fs::read(resolved).unwrap(), b"NESTED");
    }

    #[tokio::test]
    async fn nested_member_uses_pythons_basename_relaxation() {
        // Inside the nested archive the member goes through the same
        // `resolve_zip_target` Python uses, so a stale directory still resolves.
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let outer = write_nested_zip(dir.path(), "inner.zip", &[("real/img.png", b"NESTED")]);
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let (resolved, _) = servable_path(&state, &format!("{outer}!inner.zip!moved/img.png"), 100)
            .await
            .expect("basename relaxation applies to the member");
        assert_eq!(std::fs::read(&resolved).unwrap(), b"NESTED");
    }

    #[tokio::test]
    async fn nested_cache_key_changes_when_the_nested_archive_is_replaced() {
        // The outer entry's stored bytes determine every inner byte, so a
        // rewritten `inner.zip` must not be served from the previous cache
        // file even though the DB path and mtime are unchanged.
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;

        let outer = write_nested_zip(dir.path(), "inner.zip", &[("img.png", b"FIRST")]);
        let member = format!("{outer}!inner.zip!img.png");
        let (first, _) = servable_path(&state, &member, 100).await.unwrap();
        assert_eq!(std::fs::read(&first).unwrap(), b"FIRST");

        std::fs::remove_dir_all(dir.path().join("staging")).unwrap();
        let rebuilt = write_nested_zip(dir.path(), "inner.zip", &[("img.png", b"SECOND")]);
        assert_eq!(rebuilt, outer, "same archive path, rewritten");
        let (second, _) = servable_path(&state, &member, 100).await.unwrap();
        assert_ne!(first, second, "cache key must track the nested archive");
        assert_eq!(std::fs::read(&second).unwrap(), b"SECOND");
    }

    #[tokio::test]
    async fn serve_original_returns_zip_member_bytes_without_python() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let zip_path = write_zip(dir.path(), "img.png", b"PNGDATA");
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        sqlx::query("INSERT INTO files(id, path, mtime) VALUES (9, ?, 100)")
            .bind(format!("{zip_path}!img.png"))
            .execute(&state.db_read)
            .await
            .unwrap();

        // `python_url` is empty here, so a forwarded request would be 503.
        let response = serve_original(State(state), Path(9), HeaderMap::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"PNGDATA");
    }

    #[tokio::test]
    async fn serve_original_reports_missing_nested_archive_member_without_python() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        // The archive holds no `inner.zip` at all, but it does hold an entry
        // sharing the remainder's basename. Relaxing the outer name would
        // serve THIS file in place of a nested member, so the exact-match rule
        // must send the request to Python instead.
        let zip_path = write_zip(dir.path(), "img.png", b"OUTER");
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        sqlx::query("INSERT INTO files(id, path, mtime) VALUES (10, ?, 100)")
            .bind(format!("{zip_path}!inner.zip!dir/img.png"))
            .execute(&state.db_read)
            .await
            .unwrap();

        let response = serve_original(State(state), Path(10), HeaderMap::new()).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            response_json(response).await["code"],
            "archive_entry_missing"
        );
    }

    #[tokio::test]
    async fn archive_failures_keep_python_statuses_without_a_python_backend() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        let zip = write_zip(dir.path(), "real.png", b"PNG");
        let corrupt = dir.path().join("corrupt.zip");
        std::fs::write(&corrupt, b"not a zip").unwrap();
        for (id, path) in [
            (
                31,
                format!("{}!img.png", dir.path().join("missing.zip").display()),
            ),
            (32, format!("{zip}!missing.png")),
            (33, format!("{}!img.png", corrupt.display())),
            (34, format!("{zip}!no-suffix")),
        ] {
            sqlx::query("INSERT INTO files(id, path, mtime) VALUES (?, ?, 100)")
                .bind(id)
                .bind(path)
                .execute(&state.db_read)
                .await
                .unwrap();
        }
        for (id, status, code) in [
            (31, StatusCode::NOT_FOUND, "archive_missing"),
            (32, StatusCode::NOT_FOUND, "archive_entry_missing"),
            (33, StatusCode::UNPROCESSABLE_ENTITY, "archive_corrupt"),
            (
                34,
                StatusCode::UNPROCESSABLE_ENTITY,
                "archive_invalid_extension",
            ),
        ] {
            let response = serve_original(State(state.clone()), Path(id), HeaderMap::new()).await;
            assert_eq!(response.status(), status, "id {id}");
            assert_eq!(response_json(response).await["code"], code, "id {id}");
        }
        let original = serve_original(State(state.clone()), Path(33), HeaderMap::new()).await;
        let original_status = original.status();
        let original_body = response_json(original).await;
        let preview = serve_preview(State(state), Path(33), HeaderMap::new()).await;
        assert_eq!(preview.status(), original_status);
        assert_eq!(response_json(preview).await, original_body);
    }

    #[tokio::test]
    async fn serve_original_returns_nested_zip_member_bytes_without_python() {
        let dir = tempfile::tempdir().unwrap();
        let cache = tempfile::tempdir().unwrap();
        let outer = write_nested_zip(dir.path(), "inner.zip", &[("dir/img.png", b"NESTEDPNG")]);
        let state = test_state_with_cache(cache.path().to_path_buf()).await;
        sqlx::query("INSERT INTO files(id, path, mtime) VALUES (11, ?, 100)")
            .bind(format!("{outer}!inner.zip!dir/img.png"))
            .execute(&state.db_read)
            .await
            .unwrap();

        // `python_url` is empty here, so a forwarded request would be 503.
        let response = serve_original(State(state), Path(11), HeaderMap::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(&body[..], b"NESTEDPNG");
    }

    #[tokio::test]
    async fn thumbnails_warmup_requires_nonempty_file_ids_list() {
        for body in [
            serde_json::json!({}),
            serde_json::json!({"file_ids": []}),
            serde_json::json!({"file_ids": "1"}),
        ] {
            let response = thumbnails_warmup(
                State(test_state().await),
                serde_json::to_vec(&body).unwrap().into(),
            )
            .await;
            assert_eq!(response.status(), StatusCode::BAD_REQUEST);
            assert_eq!(
                response_json(response).await,
                serde_json::json!({"error": "file_ids required"})
            );
        }
    }

    #[tokio::test]
    async fn thumbnails_warmup_reports_malformed_json_separately() {
        let response = thumbnails_warmup(State(test_state().await), "{".into()).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            response_json(response).await,
            serde_json::json!({"error": "Invalid JSON body", "code": "invalid_json"})
        );
    }

    #[tokio::test]
    async fn thumbnails_warmup_truncates_to_2000_ids() {
        let body = serde_json::json!({"file_ids": (1..=3000).collect::<Vec<_>>()});
        let response = thumbnails_warmup(
            State(test_state().await),
            serde_json::to_vec(&body).unwrap().into(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::ACCEPTED);
        assert_eq!(response_json(response).await["count"], 2000);
    }

    #[tokio::test]
    async fn thumbnails_warmup_filters_ids_before_counting() {
        let body = serde_json::json!({"file_ids": [0, -1, "2", null, {}, 3.9, 2]});
        let response = thumbnails_warmup(
            State(test_state().await),
            serde_json::to_vec(&body).unwrap().into(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::ACCEPTED);
        assert_eq!(response_json(response).await["count"], 2);
    }

    #[tokio::test]
    async fn thumbnails_warmup_deduplicates_an_in_flight_set() {
        let state = test_state().await;
        let body: axum::body::Bytes = serde_json::to_vec(&serde_json::json!({
            "file_ids": [2, 1]
        }))
        .unwrap()
        .into();
        let first = thumbnails_warmup(State(state.clone()), body.clone()).await;
        let second = thumbnails_warmup(State(state), body).await;

        assert_eq!(first.status(), StatusCode::ACCEPTED);
        assert_eq!(second.status(), StatusCode::ACCEPTED);
        assert_eq!(response_json(first).await["started"], true);
        assert_eq!(response_json(second).await["started"], false);
    }

    #[tokio::test]
    async fn thumbnails_warmup_allows_different_sets_in_flight() {
        let state = test_state().await;
        let first = thumbnails_warmup(
            State(state.clone()),
            serde_json::to_vec(&serde_json::json!({"file_ids": [1]}))
                .unwrap()
                .into(),
        )
        .await;
        let second = thumbnails_warmup(
            State(state),
            serde_json::to_vec(&serde_json::json!({"file_ids": [2]}))
                .unwrap()
                .into(),
        )
        .await;

        assert_eq!(response_json(first).await["started"], true);
        assert_eq!(response_json(second).await["started"], true);
    }

    #[tokio::test]
    async fn thumbnails_warmup_populates_preview_cache() {
        let temp = tempfile::tempdir().unwrap();
        let source = temp.path().join("source.bmp");
        image::RgbImage::new(1201, 1201).save(&source).unwrap();
        let cache_dir = temp.path().join("cache");
        let state = test_state_with_cache(cache_dir.clone()).await;
        sqlx::query("UPDATE files SET path = ?, mtime = 123 WHERE id = 1")
            .bind(source.to_string_lossy().as_ref())
            .execute(&state.db)
            .await
            .unwrap();

        let response = thumbnails_warmup(
            State(state),
            serde_json::to_vec(&serde_json::json!({"file_ids": [1]}))
                .unwrap()
                .into(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::ACCEPTED);
        assert_eq!(response_json(response).await["started"], true);

        let path = source.to_string_lossy();
        let mut hasher = Sha256::new();
        hasher.update(format!("preview:{path}:123").as_bytes());
        let cache_key = hex::encode(&hasher.finalize()[..16]);
        let preview = cache_dir.join("previews").join(format!("{cache_key}.webp"));
        tokio::time::timeout(std::time::Duration::from_secs(10), async {
            while tokio::fs::metadata(&preview).await.is_err() {
                tokio::task::yield_now().await;
            }
        })
        .await
        .expect("preview cache was not populated");
    }

    #[tokio::test]
    async fn list_files_returns_files_ordered_by_path() {
        let response = list_files(State(test_state().await)).await;
        assert_eq!(response.status(), StatusCode::OK);

        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let files: serde_json::Value = serde_json::from_slice(&body).unwrap();

        assert_eq!(files[0]["id"], 2);
        assert_eq!(files[0]["path"], "/a.png");
        assert_eq!(files[0]["mtime"], 100);
        assert_eq!(files[1]["path"], "/z.png");
    }

    #[tokio::test]
    async fn list_files_returns_500_json_on_query_error() {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        let state = Arc::new(
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
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );

        let response = list_files(State(state)).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);

        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let error: serde_json::Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(error["error"], "internal_server_error");
    }
}
