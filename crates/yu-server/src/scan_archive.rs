//! Archive scanning: registers each image inside a `.zip`, `.7z` or `.rar` as
//! its own `files` row under the virtual path `archive.zip!inner/name.png`.
//!
//! A port of Python's `core/scan/{zip,sevenz,rar}_worker_*.py` plus the archive
//! branch of `core/scan_core/scanner_io_archive.py`. Members are stored with
//! `is_zip_member = 1`, which is how the rest of the system tells a virtual
//! path from a real one -- deletion sync in `scan_native` skips those rows
//! precisely because `Path::exists` can never find them.
//!
//! All three readers were already dependencies of this crate, used by
//! `routes::files` to serve archive members: `zip` (MIT), `sevenz-rust2`
//! (Apache-2.0, pure Rust -- unrelated to 7-Zip's own LGPL) and `unrar`
//! (whose vendored UnRAR source permits redistribution and use for reading,
//! forbidding only RAR-compatible *archivers*).

use std::io::Read;
use std::path::Path;

use sqlx::SqlitePool;
use tagdb_core::import::fallback_chain;
use tagdb_core::import::persist::persist_regular_scan_result;
use tagdb_core::import::version_authority::should_rescan;
use tagdb_core::{upsert_file, UpsertFileParams, CURRENT_PARSER_VERSION};

/// The separator between an archive path and its internal path, matching
/// Python's `split_archive_path`.
pub const ARCHIVE_SEP: char = '!';

/// Members larger than this are skipped rather than buffered whole. Python
/// reads members into memory too; the cap keeps one oversized entry from
/// taking the scan down with an allocation failure.
const MAX_MEMBER_BYTES: u64 = 256 * 1024 * 1024;

/// Image extensions worth extracting metadata from inside an archive.
const MEMBER_IMAGE_EXTS: &[&str] = &[
    "png", "jpg", "jpeg", "webp", "gif", "jxl", "avif", "heif", "heic",
];

/// Which reader opens this archive.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ArchiveKind {
    Zip,
    SevenZ,
    Rar,
}

/// The archive formats a scan walks into, as walk-filter extensions.
pub const ARCHIVE_EXTS: &[&str] = &["zip", "7z", "rar"];

pub fn archive_kind(path: &Path) -> Option<ArchiveKind> {
    let ext = path.extension().and_then(|e| e.to_str())?;
    if ext.eq_ignore_ascii_case("zip") {
        Some(ArchiveKind::Zip)
    } else if ext.eq_ignore_ascii_case("7z") {
        Some(ArchiveKind::SevenZ)
    } else if ext.eq_ignore_ascii_case("rar") {
        Some(ArchiveKind::Rar)
    } else {
        None
    }
}

fn member_ext(name: &str) -> Option<String> {
    let (_, ext) = name.rsplit_once('.')?;
    Some(ext.to_ascii_lowercase())
}

fn is_scannable_member(name: &str) -> bool {
    let Some(ext) = member_ext(name) else {
        return false;
    };
    MEMBER_IMAGE_EXTS.contains(&ext.as_str()) || meta_extract::ffprobe::is_media_extension(&ext)
}

/// `archive.zip` + `inner/name.png` -> `archive.zip!inner/name.png`.
pub fn virtual_path(archive: &str, internal: &str) -> String {
    format!("{archive}{ARCHIVE_SEP}{internal}")
}

/// One archive member, read into memory.
struct Member {
    internal: String,
    mtime: i64,
    size: i64,
    data: Vec<u8>,
}

/// Read every scannable member. Blocking I/O -- call from `spawn_blocking`.
fn read_members(archive: &Path, kind: ArchiveKind) -> Result<Vec<Member>, String> {
    match kind {
        ArchiveKind::Zip => read_zip_members(archive),
        ArchiveKind::SevenZ => read_sevenz_members(archive),
        ArchiveKind::Rar => read_rar_members(archive),
    }
}

fn oversized(archive: &Path, internal: &str, size: u64) -> bool {
    if size > MAX_MEMBER_BYTES {
        tracing::warn!(
            "archive: skipping oversized member {internal} ({size} bytes) in {}",
            archive.display()
        );
        return true;
    }
    false
}

fn read_zip_members(archive: &Path) -> Result<Vec<Member>, String> {
    let file = std::fs::File::open(archive).map_err(|e| e.to_string())?;
    let mut zip = zip::ZipArchive::new(file).map_err(|e| e.to_string())?;
    let mut out = Vec::new();
    for i in 0..zip.len() {
        let mut entry = match zip.by_index(i) {
            Ok(entry) => entry,
            Err(e) => {
                tracing::debug!("zip: unreadable entry {i} in {}: {e}", archive.display());
                continue;
            }
        };
        if !entry.is_file() {
            continue;
        }
        let internal = entry.name().to_string();
        if !is_scannable_member(&internal) || oversized(archive, &internal, entry.size()) {
            continue;
        }
        // Bounded by MAX_MEMBER_BYTES just above, so this always fits; the
        // fallback keeps a 32-bit target from over-reserving rather than
        // truncating silently.
        let mut data = Vec::with_capacity(usize::try_from(entry.size()).unwrap_or(0));
        if let Err(e) = entry.read_to_end(&mut data) {
            tracing::debug!("zip: failed to read {internal}: {e}");
            continue;
        }
        // Zip stores a local timestamp with no zone. Python's
        // `get_mtime_and_size_from_zip` takes it at face value and corrects
        // later only for UTC-writing producers, so we do the same rather than
        // guessing an offset here.
        let mtime = entry.last_modified().map(zip_datetime_to_unix).unwrap_or(0);
        out.push(Member {
            internal,
            mtime,
            size: i64::try_from(entry.size()).unwrap_or(i64::MAX),
            data,
        });
    }
    Ok(out)
}

fn read_sevenz_members(archive: &Path) -> Result<Vec<Member>, String> {
    let mut reader = sevenz_rust2::ArchiveReader::open(archive, sevenz_rust2::Password::empty())
        .map_err(|e| e.to_string())?;
    let mut out: Vec<Member> = Vec::new();
    let mut failed: Option<String> = None;
    reader
        .for_each_entries(|entry, input| {
            if entry.is_directory() {
                return Ok(true);
            }
            let internal = entry.name().to_string();
            if !is_scannable_member(&internal) || oversized(archive, &internal, entry.size()) {
                return Ok(true);
            }
            let mut data = Vec::with_capacity(usize::try_from(entry.size()).unwrap_or(0));
            // Read past the cap by one byte so a header that under-declares the
            // size cannot slip an unbounded member through.
            if let Err(e) = std::io::Read::read_to_end(
                &mut std::io::Read::take(input, MAX_MEMBER_BYTES.saturating_add(1)),
                &mut data,
            ) {
                failed = Some(e.to_string());
                return Ok(true);
            }
            if data.len() as u64 > MAX_MEMBER_BYTES {
                tracing::warn!(
                    "7z: member {internal} exceeded the cap while reading in {}",
                    archive.display()
                );
                return Ok(true);
            }
            let size = i64::try_from(data.len()).unwrap_or(i64::MAX);
            out.push(Member {
                internal,
                mtime: nt_time_to_unix(&entry.last_modified_date),
                size,
                data,
            });
            Ok(true)
        })
        .map_err(|e| e.to_string())?;
    if let Some(e) = failed {
        tracing::debug!("7z: a member failed to read in {}: {e}", archive.display());
    }
    Ok(out)
}

fn read_rar_members(archive: &Path) -> Result<Vec<Member>, String> {
    let mut reader = unrar::Archive::new(archive)
        .open_for_processing()
        .map_err(|e| e.to_string())?;
    let mut out = Vec::new();
    while let Some(header) = reader.read_header().map_err(|e| e.to_string())? {
        let entry = header.entry();
        let internal = entry.filename.to_string_lossy().into_owned();
        let size = entry.unpacked_size;
        let mtime = dos_time_to_unix(entry.file_time);
        let wanted = !entry.is_directory()
            && is_scannable_member(&internal)
            && !oversized(archive, &internal, size);
        if !wanted {
            reader = header.skip().map_err(|e| e.to_string())?;
            continue;
        }
        let (data, next) = header.read().map_err(|e| e.to_string())?;
        reader = next;
        out.push(Member {
            internal,
            mtime,
            size: i64::try_from(size).unwrap_or(i64::MAX),
            data,
        });
    }
    Ok(out)
}

/// 7z stores an NT file time: 100-nanosecond ticks since 1601-01-01.
fn nt_time_to_unix(nt: &sevenz_rust2::NtTime) -> i64 {
    const NT_TO_UNIX_SECS: i64 = 11_644_473_600;
    let ticks = i64::try_from(u64::from(*nt)).unwrap_or(0);
    if ticks == 0 {
        return 0;
    }
    (ticks / 10_000_000).saturating_sub(NT_TO_UNIX_SECS)
}

/// RAR reports an MS-DOS packed date/time, the same encoding zip uses on the
/// wire: seconds/2, minute, hour, day, month, year-1980.
fn dos_time_to_unix(dos: u32) -> i64 {
    let second = ((dos & 0x1f) * 2) as i64;
    let minute = ((dos >> 5) & 0x3f) as i64;
    let hour = ((dos >> 11) & 0x1f) as i64;
    let day = ((dos >> 16) & 0x1f) as i64;
    let month = ((dos >> 21) & 0x0f) as i64;
    let year = ((dos >> 25) & 0x7f) as i64 + 1980;
    if month == 0 || day == 0 {
        return 0;
    }
    civil_to_unix(year, month, day, hour, minute, second)
}

/// Convert a zip entry's local, zone-less timestamp to Unix seconds by
/// treating it as UTC -- the same face-value reading Python takes.
fn zip_datetime_to_unix(dt: zip::DateTime) -> i64 {
    civil_to_unix(
        i64::from(dt.year()),
        i64::from(dt.month()),
        i64::from(dt.day()),
        i64::from(dt.hour()),
        i64::from(dt.minute()),
        i64::from(dt.second()),
    )
}

fn civil_to_unix(y: i64, m: i64, d: i64, hour: i64, minute: i64, second: i64) -> i64 {
    // days_from_civil (Howard Hinnant's algorithm): calendar date -> days
    // since 1970-01-01, valid for any proleptic Gregorian date.
    let y = if m <= 2 { y - 1 } else { y };
    let era = if y >= 0 { y } else { y - 399 } / 400;
    let yoe = y - era * 400;
    let mp = (m + 9) % 12;
    let doy = (153 * mp + 2) / 5 + d - 1;
    let doe = yoe * 365 + yoe / 4 - yoe / 100 + doy;
    let days = era * 146_097 + doe - 719_468;
    days * 86_400 + hour * 3_600 + minute * 60 + second
}

/// How one archive's scan went.
#[derive(Default, Debug, PartialEq, Eq)]
pub struct ArchiveOutcome {
    pub imported: u64,
    pub skipped: u64,
    pub errors: u64,
}

/// Import every scannable member of one archive. `force` bypasses the
/// mtime/size/parser_version skip check, as elsewhere in the scan.
pub async fn import_archive(
    pool: &SqlitePool,
    archive: &Path,
    force: bool,
    toggles: meta_extract::ParserToggles,
) -> ArchiveOutcome {
    let Some(kind) = archive_kind(archive) else {
        return ArchiveOutcome::default();
    };
    let archive_owned = archive.to_path_buf();
    let members =
        match tokio::task::spawn_blocking(move || read_members(&archive_owned, kind)).await {
            Ok(Ok(members)) => members,
            Ok(Err(e)) => {
                tracing::warn!("archive: cannot open {}: {e}", archive.display());
                return ArchiveOutcome {
                    errors: 1,
                    ..Default::default()
                };
            }
            Err(e) => {
                tracing::warn!("archive: read task failed for {}: {e}", archive.display());
                return ArchiveOutcome {
                    errors: 1,
                    ..Default::default()
                };
            }
        };

    let archive_str = archive.to_string_lossy().into_owned();
    let mut outcome = ArchiveOutcome::default();
    for member in members {
        let path_str = virtual_path(&archive_str, &member.internal);
        match import_member(pool, &path_str, &member, force, toggles).await {
            Ok(true) => outcome.imported += 1,
            Ok(false) => outcome.skipped += 1,
            Err(e) => {
                tracing::debug!("archive: import failed for {path_str}: {e}");
                outcome.errors += 1;
            }
        }
    }
    outcome
}

/// Extract a member's metadata. Images are parsed straight from the bytes;
/// an audio or video member has to be spilled to a temp file first, because
/// ffprobe takes a path -- which is what Python's `extracted_zip_member_path`
/// does for the same reason.
fn extract_member_meta(
    internal: &str,
    data: &[u8],
    toggles: meta_extract::ParserToggles,
) -> fallback_chain::ExtractedMeta {
    let ext = member_ext(internal).unwrap_or_default();
    if !meta_extract::ffprobe::is_media_extension(&ext) {
        return fallback_chain::extract_metadata_from_bytes_with(
            Path::new(internal),
            data,
            toggles,
        );
    }

    let Ok(dir) = tempfile::tempdir() else {
        return fallback_chain::extract_metadata_from_bytes_with(
            Path::new(internal),
            data,
            toggles,
        );
    };
    // Keep the extension: ffprobe uses it as a demuxer hint, and our own
    // audio/video split reads it back off the path.
    let spilled = dir.path().join(format!("member.{ext}"));
    if std::fs::write(&spilled, data).is_err() {
        return fallback_chain::extract_metadata_from_bytes_with(
            Path::new(internal),
            data,
            toggles,
        );
    }
    let media = meta_extract::extract_with_ffprobe(&spilled);
    fallback_chain::ExtractedMeta {
        meta_source: media.meta_source,
        format: media.format,
        raw_prompt: media.raw_prompt,
        raw_negative: None,
        raw_meta_json: Some(media.raw_meta_json),
        tag_source: media.tag_source,
    }
}

/// Returns whether the member was (re)imported; `Ok(false)` means it was
/// unchanged and skipped.
async fn import_member(
    pool: &SqlitePool,
    path_str: &str,
    member: &Member,
    force: bool,
    toggles: meta_extract::ParserToggles,
) -> Result<bool, String> {
    let mut conn = pool.acquire().await.map_err(|e| e.to_string())?;

    let existing: Option<(i64, i64, i64, i64)> = sqlx::query_as(
        "SELECT id, mtime, size, COALESCE(parser_version, 1) FROM files WHERE path = ?",
    )
    .bind(path_str)
    .fetch_optional(&mut *conn)
    .await
    .map_err(|e| e.to_string())?;

    if let Some((_, old_mtime, old_size, old_parser_version)) = existing {
        if !should_rescan(
            old_mtime,
            old_size,
            old_parser_version,
            member.mtime,
            member.size,
            force,
        ) {
            return Ok(false);
        }
    }

    let extracted = extract_member_meta(&member.internal, &member.data, toggles);
    let (width, height) = fallback_chain::extract_resolution(
        extracted.raw_prompt.as_deref(),
        extracted.raw_meta_json.as_deref(),
    );

    // Unlike a regular file, an unrecognized member is still worth a row:
    // there is no later "rescan from disk" pass that would find it, and the
    // UI lists archive contents from these rows. Python registers it too.
    let file_id = upsert_file(
        pool,
        UpsertFileParams {
            path: path_str,
            mtime: member.mtime,
            size: member.size,
            meta_source: Some(&extracted.meta_source),
            content_hash: None,
            is_zip_member: true,
            width,
            height,
        },
    )
    .await
    .map_err(|e| e.to_string())?;

    sqlx::query("UPDATE files SET parser_version = ? WHERE id = ?")
        .bind(CURRENT_PARSER_VERSION)
        .bind(file_id)
        .execute(&mut *conn)
        .await
        .map_err(|e| e.to_string())?;

    persist_regular_scan_result(&mut conn, file_id, &extracted, member.mtime, true)
        .await
        .map_err(|e| e.to_string())?;
    Ok(true)
}

/// Mark members of archives that no longer exist as deleted.
///
/// `sync_deleted_files` cannot do this: it filters `is_zip_member = 0`
/// because a member's virtual path never exists on disk. The archive itself
/// does, so that is what gets checked here.
pub async fn sync_deleted_archive_members(pool: &SqlitePool, root: &str) -> u64 {
    // Escapes LIKE metacharacters *and* the ESCAPE character itself. Without
    // the `\` -> `\\` leg, every literal backslash in a Windows root (all of
    // them, since native paths use `\` throughout) is consumed by
    // `ESCAPE '\\'` as an escape-introducer instead of matching a literal
    // separator -- and the pattern's own trailing `\%` stops meaning
    // "separator then wildcard" and instead means "a literal % character",
    // which never matches anything. This silently broke the `bwd` branch's
    // matching for every real Windows deployment.
    fn escape_like(s: &str) -> String {
        s.replace('\\', "\\\\")
            .replace('%', "\\%")
            .replace('_', "\\_")
    }
    // Trim the raw (unescaped) separator first: a trailing `\` in the
    // escaped string would already be the first half of an escaped pair and
    // could not be distinguished from one by `trim_end_matches`.
    let fwd_root = root.replace('\\', "/");
    let fwd_root = fwd_root.trim_end_matches('/');
    let fwd = format!("{}/%", escape_like(fwd_root));

    let bwd_root = root.replace('/', "\\");
    let bwd_root = bwd_root.trim_end_matches('\\');
    // The literal separator is `\` here, which must itself be escaped to
    // survive as a literal under `ESCAPE '\\'` -- `\\\\%` in this Rust
    // string is two literal backslashes followed by an unescaped wildcard.
    let bwd = format!("{}\\\\%", escape_like(bwd_root));

    let rows: Vec<(i64, String)> = sqlx::query_as(
        "SELECT id, path FROM files \
         WHERE (path LIKE ? ESCAPE '\\' OR path LIKE ? ESCAPE '\\') \
           AND is_deleted = 0 AND is_zip_member = 1",
    )
    .bind(&fwd)
    .bind(&bwd)
    .fetch_all(pool)
    .await
    .unwrap_or_default();
    if rows.is_empty() {
        return 0;
    }

    let missing_ids: Vec<i64> = tokio::task::spawn_blocking(move || {
        rows.into_iter()
            .filter(|(_, path)| {
                let archive = archive_part(path);
                !archive.is_empty() && !Path::new(&archive).exists()
            })
            .map(|(id, _)| id)
            .collect()
    })
    .await
    .unwrap_or_default();

    let mut deleted = 0u64;
    for id in missing_ids {
        let result = sqlx::query("UPDATE files SET is_deleted = 1 WHERE id = ? AND is_deleted = 0")
            .bind(id)
            .execute(pool)
            .await;
        if let Ok(r) = result {
            deleted += r.rows_affected();
        }
    }
    deleted
}

/// The archive half of a member path, split at the first `.zip!` boundary.
///
/// Splitting on a bare `!` would break on real folders that contain one
/// (Python hit exactly that and fixed it the same way), and splitting at the
/// *first* boundary is what makes nested archives resolvable by the caller.
pub fn archive_part(path: &str) -> String {
    let lower = path.to_ascii_lowercase();
    for marker in [".zip!", ".7z!", ".rar!"] {
        if let Some(idx) = lower.find(marker) {
            // Keep the extension, drop the '!'.
            return path[..idx + marker.len() - 1].to_string();
        }
    }
    String::new()
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::io::Write;
    use std::str::FromStr;

    const TEST_KEY: &str = "scan-zip-test-key";

    async fn test_pool(dir: &Path) -> SqlitePool {
        let db_path = dir.join("tags.db");
        tagdb_core::create_fresh_database(db_path.to_str().unwrap(), TEST_KEY)
            .await
            .expect("genesis");
        let opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", db_path.display()))
            .unwrap()
            .pragma("cipher_memory_security", "OFF")
            .pragma("key", format!("'{TEST_KEY}'"))
            .pragma("mmap_size", "0")
            .create_if_missing(false);
        let pool = SqlitePoolOptions::new()
            .max_connections(2)
            .connect_with(opts)
            .await
            .unwrap();
        tagdb_core::apply_pending_rust_migrations(&pool)
            .await
            .expect("rust migrations");
        pool
    }

    /// A minimal PNG carrying one tEXt chunk, enough for the A1111 parser to
    /// recognize it.
    fn png_with_parameters(text: &str) -> Vec<u8> {
        fn chunk(kind: &[u8; 4], body: &[u8]) -> Vec<u8> {
            let mut out = (body.len() as u32).to_be_bytes().to_vec();
            out.extend_from_slice(kind);
            out.extend_from_slice(body);
            out.extend_from_slice(&0u32.to_be_bytes()); // CRC is not verified by the reader
            out
        }
        let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
        out.extend_from_slice(&chunk(b"IHDR", &[0u8; 13]));
        let mut text_body = b"parameters".to_vec();
        text_body.push(0);
        text_body.extend_from_slice(text.as_bytes());
        out.extend_from_slice(&chunk(b"tEXt", &text_body));
        out.extend_from_slice(&chunk(b"IEND", b""));
        out
    }

    fn write_sevenz(path: &Path, entries: &[(&str, Vec<u8>)]) {
        let mut writer = sevenz_rust2::ArchiveWriter::create(path).expect("create 7z");
        for (name, data) in entries {
            let entry = sevenz_rust2::ArchiveEntry::new_file(name);
            writer
                .push_archive_entry(entry, Some(std::io::Cursor::new(data.clone())))
                .expect("push 7z entry");
        }
        writer.finish().expect("finish 7z");
    }

    fn write_zip(path: &Path, entries: &[(&str, Vec<u8>)]) {
        let file = std::fs::File::create(path).unwrap();
        let mut writer = zip::ZipWriter::new(file);
        let options: zip::write::FileOptions<'_, ()> =
            zip::write::FileOptions::default().compression_method(zip::CompressionMethod::Stored);
        for (name, data) in entries {
            writer.start_file(*name, options).unwrap();
            writer.write_all(data).unwrap();
        }
        writer.finish().unwrap();
    }

    /// Members must land as `is_zip_member` rows under the virtual path, with
    /// their prompt tags -- not merely be counted. Non-image entries are left
    /// out entirely.
    #[tokio::test]
    async fn zip_members_are_imported_with_tags_and_marked_as_members() {
        let dir = tempfile::TempDir::new().unwrap();
        let pool = test_pool(dir.path()).await;
        let archive = dir.path().join("pack.zip");
        write_zip(
            &archive,
            &[
                (
                    "inner/a.png",
                    png_with_parameters("1girl, solo\nSteps: 20, Sampler: Euler a, Size: 512x768"),
                ),
                ("inner/readme.txt", b"not an image".to_vec()),
            ],
        );

        let outcome = import_archive(
            &pool,
            &archive,
            false,
            meta_extract::ParserToggles::default(),
        )
        .await;
        assert_eq!(
            outcome,
            ArchiveOutcome {
                imported: 1,
                skipped: 0,
                errors: 0
            }
        );

        let expected_path = virtual_path(&archive.to_string_lossy(), "inner/a.png");
        let (is_member, meta_source): (i64, Option<String>) =
            sqlx::query_as("SELECT is_zip_member, meta_source FROM files WHERE path = ?")
                .bind(&expected_path)
                .fetch_one(&pool)
                .await
                .expect("member row");
        assert_eq!(is_member, 1);
        assert!(
            meta_source.as_deref().is_some_and(|s| s != "unknown"),
            "expected a recognized meta_source, got {meta_source:?}"
        );

        let tags: Vec<String> = sqlx::query_scalar(
            "SELECT t.tag FROM tags t
               JOIN file_tags ft ON ft.tag_id = t.id
               JOIN files f ON f.id = ft.file_id
              WHERE f.path = ?",
        )
        .bind(&expected_path)
        .fetch_all(&pool)
        .await
        .unwrap();
        assert!(tags.iter().any(|t| t == "1girl"), "got {tags:?}");

        // The .txt entry must not have been registered.
        let txt_rows: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM files WHERE path LIKE '%readme.txt'")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(txt_rows, 0);

        // A second pass with no changes must skip, not re-import.
        let again = import_archive(
            &pool,
            &archive,
            false,
            meta_extract::ParserToggles::default(),
        )
        .await;
        assert_eq!(again.imported, 0);
        assert_eq!(again.skipped, 1);
    }

    /// When the archive itself is gone, its member rows must be marked
    /// deleted -- `sync_deleted_files` cannot do it, since a virtual path
    /// never exists on disk.
    #[tokio::test]
    async fn members_of_a_removed_archive_are_marked_deleted() {
        let dir = tempfile::TempDir::new().unwrap();
        let pool = test_pool(dir.path()).await;
        let archive = dir.path().join("pack.zip");
        write_zip(&archive, &[("a.png", png_with_parameters("cat, Steps: 1"))]);
        import_archive(
            &pool,
            &archive,
            false,
            meta_extract::ParserToggles::default(),
        )
        .await;

        let root = dir.path().to_string_lossy().into_owned();
        // Still present: nothing to delete.
        assert_eq!(sync_deleted_archive_members(&pool, &root).await, 0);

        std::fs::remove_file(&archive).unwrap();
        assert_eq!(sync_deleted_archive_members(&pool, &root).await, 1);
        let alive: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM files WHERE is_deleted = 0 AND is_zip_member = 1",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(alive, 0);
    }

    /// A 7z archive must go through the same path as a zip: real members,
    /// real tags, `is_zip_member = 1`. Written with the same crate the reader
    /// uses, since there is no 7z fixture in the tree.
    #[tokio::test]
    async fn sevenz_members_are_imported_like_zip_members() {
        let dir = tempfile::TempDir::new().unwrap();
        let pool = test_pool(dir.path()).await;

        let archive = dir.path().join("pack.7z");
        write_sevenz(
            &archive,
            &[
                ("a.png", png_with_parameters("1girl, solo\nSteps: 20")),
                ("readme.txt", b"not an image".to_vec()),
            ],
        );

        let outcome = import_archive(
            &pool,
            &archive,
            false,
            meta_extract::ParserToggles::default(),
        )
        .await;
        assert_eq!(outcome.imported, 1, "got {outcome:?}");
        assert_eq!(outcome.errors, 0);

        let expected_path = virtual_path(&archive.to_string_lossy(), "a.png");
        let is_member: i64 = sqlx::query_scalar("SELECT is_zip_member FROM files WHERE path = ?")
            .bind(&expected_path)
            .fetch_one(&pool)
            .await
            .expect("member row");
        assert_eq!(is_member, 1);

        let tags: Vec<String> = sqlx::query_scalar(
            "SELECT t.tag FROM tags t
               JOIN file_tags ft ON ft.tag_id = t.id
               JOIN files f ON f.id = ft.file_id
              WHERE f.path = ?",
        )
        .bind(&expected_path)
        .fetch_all(&pool)
        .await
        .unwrap();
        assert!(tags.iter().any(|t| t == "1girl"), "got {tags:?}");

        // The archive is one of the three the deletion sync recognizes.
        let root = dir.path().to_string_lossy().into_owned();
        std::fs::remove_file(&archive).unwrap();
        assert_eq!(sync_deleted_archive_members(&pool, &root).await, 1);
    }

    /// The `extract_a1111` / `extract_comfyui` settings must reach the parser,
    /// not merely exist. With A1111 off, an A1111-only PNG comes back
    /// unrecognized and carries no tags; with it on (the default) it parses.
    /// Hard-coding `ParserToggles::default()` in `import_member` fails this.
    #[tokio::test]
    async fn parser_toggles_reach_archive_members() {
        let dir = tempfile::TempDir::new().unwrap();
        let pool = test_pool(dir.path()).await;
        let archive = dir.path().join("pack.zip");
        write_zip(
            &archive,
            &[("a.png", png_with_parameters("1girl, solo\nSteps: 20"))],
        );

        let off = meta_extract::ParserToggles {
            a1111: false,
            comfyui: true,
        };
        assert_eq!(
            import_archive(&pool, &archive, false, off).await.imported,
            1
        );

        let path = virtual_path(&archive.to_string_lossy(), "a.png");
        let meta_source: Option<String> =
            sqlx::query_scalar("SELECT meta_source FROM files WHERE path = ?")
                .bind(&path)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(meta_source.as_deref(), Some("unknown"));
        let tags: i64 = sqlx::query_scalar(
            "SELECT COUNT(*) FROM file_tags ft JOIN files f ON f.id = ft.file_id
              WHERE f.path = ?",
        )
        .bind(&path)
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(tags, 0, "a disabled parser must not yield tags");

        // Same member, parser enabled: now it is recognized. `force` because
        // nothing about the file changed -- only the setting did.
        let on = meta_extract::ParserToggles::default();
        assert_eq!(import_archive(&pool, &archive, true, on).await.imported, 1);
        let meta_source: Option<String> =
            sqlx::query_scalar("SELECT meta_source FROM files WHERE path = ?")
                .bind(&path)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_ne!(meta_source.as_deref(), Some("unknown"));
    }

    /// An audio member has no file behind it, so the media stage has to spill
    /// it to a temp file before ffprobe can describe it. Injecting the plain
    /// `extract_metadata_from_bytes` in `extract_member_meta` fails this on
    /// meta_source.
    #[tokio::test]
    async fn media_members_are_probed_after_a_temp_spill() {
        if std::process::Command::new("ffprobe")
            .arg("-version")
            .output()
            .is_err()
        {
            eprintln!("ffprobe not installed; skipping");
            return;
        }
        let dir = tempfile::TempDir::new().unwrap();
        let pool = test_pool(dir.path()).await;
        let archive = dir.path().join("sounds.zip");
        write_zip(&archive, &[("tone.wav", minimal_wav())]);

        let outcome = import_archive(
            &pool,
            &archive,
            false,
            meta_extract::ParserToggles::default(),
        )
        .await;
        assert_eq!(outcome.imported, 1, "got {outcome:?}");

        let expected_path = virtual_path(&archive.to_string_lossy(), "tone.wav");
        let (meta_source, raw_meta): (Option<String>, Option<String>) = sqlx::query_as(
            "SELECT f.meta_source, t.raw_meta_json FROM files f
               LEFT JOIN templates t ON t.file_id = f.id
              WHERE f.path = ?",
        )
        .bind(&expected_path)
        .fetch_one(&pool)
        .await
        .expect("member row");
        assert_eq!(meta_source.as_deref(), Some("media_audio_ffprobe"));
        let env: serde_json::Value =
            serde_json::from_str(raw_meta.as_deref().expect("raw_meta_json")).unwrap();
        assert_eq!(env["container"], serde_json::json!("wav"));
        assert_eq!(env["cache_state"], serde_json::json!("ready"));
    }

    /// 8 kHz mono 16-bit PCM, one sample -- the smallest thing ffprobe will
    /// still parse as a WAV.
    fn minimal_wav() -> Vec<u8> {
        let sample_rate: u32 = 8000;
        let data: [u8; 2] = [0, 0];
        let mut out = Vec::new();
        out.extend_from_slice(b"RIFF");
        out.extend_from_slice(&(36u32 + data.len() as u32).to_le_bytes());
        out.extend_from_slice(b"WAVEfmt ");
        out.extend_from_slice(&16u32.to_le_bytes());
        out.extend_from_slice(&1u16.to_le_bytes());
        out.extend_from_slice(&1u16.to_le_bytes());
        out.extend_from_slice(&sample_rate.to_le_bytes());
        out.extend_from_slice(&(sample_rate * 2).to_le_bytes());
        out.extend_from_slice(&2u16.to_le_bytes());
        out.extend_from_slice(&16u16.to_le_bytes());
        out.extend_from_slice(b"data");
        out.extend_from_slice(&(data.len() as u32).to_le_bytes());
        out.extend_from_slice(&data);
        out
    }

    #[test]
    fn archive_part_splits_at_the_extension_not_at_any_bang() {
        assert_eq!(
            archive_part("/lib/pack.zip!inner/a.png"),
            "/lib/pack.zip".to_string()
        );
        // A '!' in a folder name must not be mistaken for a boundary.
        assert_eq!(archive_part("/lib/elf!/a.png"), String::new());
        // Nested archives split at the first boundary.
        assert_eq!(
            archive_part("/lib/outer.zip!inner.zip!a.png"),
            "/lib/outer.zip".to_string()
        );
        assert_eq!(archive_part("/lib/plain.png"), String::new());
    }

    #[test]
    fn member_filter_accepts_images_and_media_only() {
        assert!(is_scannable_member("a/b.PNG"));
        assert!(is_scannable_member("a/b.jpeg"));
        // Media members go through ffprobe after a temp spill, so they count.
        assert!(is_scannable_member("a/b.mp4"));
        assert!(is_scannable_member("a/b.FLAC"));
        assert!(!is_scannable_member("a/b.txt"));
        assert!(!is_scannable_member("noext"));
    }

    #[test]
    fn archive_kinds_are_detected_case_insensitively() {
        assert_eq!(archive_kind(Path::new("/x/a.ZIP")), Some(ArchiveKind::Zip));
        assert_eq!(
            archive_kind(Path::new("/x/a.7z")),
            Some(ArchiveKind::SevenZ)
        );
        assert_eq!(archive_kind(Path::new("/x/a.RaR")), Some(ArchiveKind::Rar));
        assert_eq!(archive_kind(Path::new("/x/a.png")), None);
    }

    /// NT file time is 100ns ticks since 1601-01-01; DOS packs the fields into
    /// one u32. Both must land on the same instant as the zip path.
    #[test]
    fn archive_timestamps_convert_to_unix_seconds() {
        // 2024-02-29T12:34:56Z, the same instant in all three encodings.
        let expected = 1_709_251_200 - 41_104;
        let zip_dt = zip::DateTime::from_date_and_time(2024, 2, 29, 12, 34, 56).unwrap();
        assert_eq!(zip_datetime_to_unix(zip_dt), expected);

        let nt_ticks = u64::try_from((expected + 11_644_473_600) * 10_000_000).unwrap();
        assert_eq!(
            nt_time_to_unix(&sevenz_rust2::NtTime::from(nt_ticks)),
            expected
        );

        let dos =
            (56u32 / 2) | (34 << 5) | (12 << 11) | (29 << 16) | (2 << 21) | ((2024 - 1980) << 25);
        assert_eq!(dos_time_to_unix(dos), expected);

        // An unset timestamp must stay 0, not become the 1601 or 1980 epoch.
        assert_eq!(nt_time_to_unix(&sevenz_rust2::NtTime::from(0u64)), 0);
        assert_eq!(dos_time_to_unix(0), 0);
    }

    #[test]
    fn virtual_paths_use_the_bang_separator() {
        assert_eq!(virtual_path("/x/a.zip", "in/b.png"), "/x/a.zip!in/b.png");
    }
}
