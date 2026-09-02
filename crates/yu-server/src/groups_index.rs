#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::{json, Number};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;
    use tempfile::TempDir;

    async fn files_pool(seed: &str) -> sqlx::SqlitePool {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT,
               mtime,
               is_deleted INTEGER NOT NULL DEFAULT 0
             );",
        )
        .execute(&pool)
        .await
        .unwrap();
        if !seed.is_empty() {
            sqlx::raw_sql(seed).execute(&pool).await.unwrap();
        }
        pool
    }

    #[tokio::test]
    async fn builder_classifies_archives_folders_roots_and_backslashes() {
        let pool = files_pool(
            "INSERT INTO files(id, path, mtime, is_deleted) VALUES
             (1, 'a.zip!x/y.png', 10, 0),
             (2, 'b.RAR', 11, 0),
             (3, 'Dir/Sub/f.png', 12, 0),
             (4, 'Dir/Sub/g.png', 13, 0),
             (5, 'f.png', 14, 0),
             (6, 'g.png', 15, 0),
             (7, 'Dir\\f.png', 16, 0),
             (8, 'Dir\\g.png', 17, 0);",
        )
        .await;

        let index = build_groups_index(&pool).await.unwrap();

        assert!(index.zips.contains_key("archive:a.zip"));
        assert!(index.zips.contains_key("archive:b.rar"));
        assert_eq!(index.folders["folder:dir/sub"].ids, vec![3, 4]);
        assert_eq!(index.folders["folder:."].ids, vec![5, 6]);
        assert_eq!(index.folders["folder:dir"].ids, vec![7, 8]);
    }

    #[tokio::test]
    async fn builder_filters_singleton_folders_keeps_zips_and_truncates_reps() {
        let pool = files_pool(
            "INSERT INTO files(id, path, mtime, is_deleted) VALUES
             (1, 'single/a.png', 1, 0),
             (2, 'arc.zip', 2, 0),
             (3, 'many/1.png', 3, 0),
             (4, 'many/2.png', 4, 0),
             (5, 'many/3.png', 5, 0),
             (6, 'many/4.png', 6, 0),
             (7, 'many/5.png', 7, 0),
             (8, 'many/6.png', 8, 0),
             (9, 'many/7.png', 9, 0),
             (10, 'many/8.png', 10, 0),
             (11, 'many/9.png', 11, 0);",
        )
        .await;

        let index = build_groups_index(&pool).await.unwrap();

        assert!(!index.folders.contains_key("folder:single"));
        assert_eq!(index.zips["archive:arc.zip"].label, "arc.zip");
        assert_eq!(index.folders["folder:many"].label, "many");
        assert_eq!(
            index.folders["folder:many"].reps,
            vec![3, 4, 5, 6, 7, 8, 9, 10]
        );
    }

    #[test]
    fn archive_part_uses_first_archive_boundary_only() {
        assert_eq!(archive_part("outer.zip!inner.zip!x.png"), "outer.zip");
        assert_eq!(
            archive_part("name!without_archive.txt"),
            "name!without_archive.txt"
        );
    }

    #[tokio::test]
    async fn cache_roundtrip_validates_and_mismatch_rebuilds() {
        let pool = files_pool(
            "INSERT INTO files(id, path, mtime, is_deleted) VALUES
             (1, 'a/1.png', 1, 0),
             (2, 'a/2.png', 2, 0);",
        )
        .await;
        let temp = TempDir::new().unwrap();
        let cache = GroupsIndexCache::new(temp.path().to_path_buf());

        let first = cache.get(&pool).await.unwrap();
        let second = cache.get(&pool).await.unwrap();
        assert_eq!(second.file_count, first.file_count);

        sqlx::query("INSERT INTO files(id, path, mtime, is_deleted) VALUES (3, 'a/3.png', 3, 0)")
            .execute(&pool)
            .await
            .unwrap();
        let rebuilt = GroupsIndexCache::new(temp.path().to_path_buf())
            .get(&pool)
            .await
            .unwrap();
        assert_eq!(rebuilt.file_count, 3);
    }

    #[tokio::test]
    async fn numeric_signature_tolerates_integer_real_json_difference() {
        let pool = files_pool(
            "INSERT INTO files(id, path, mtime, is_deleted) VALUES
             (1, 'a/1.png', 123, 0),
             (2, 'a/2.png', 123, 0);",
        )
        .await;
        let temp = TempDir::new().unwrap();
        let cache_path = temp.path().join("groups_index.json");
        std::fs::write(
            &cache_path,
            r#"{"file_count":2,"max_mtime":123.0,"cache_version":4,"folders":{"folder:a":{"ids":[1,2],"label":"a","reps":[1,2],"max_mtime":123}},"zips":{}}"#,
        )
        .unwrap();
        let cache = GroupsIndexCache::new(temp.path().to_path_buf());

        let index = cache.get(&pool).await.unwrap();

        assert_eq!(index.file_count, 2);
        assert_eq!(index.folders["folder:a"].ids, vec![1, 2]);
    }

    #[test]
    fn limit_parse_and_mtime_string_match_python_edges() {
        assert_eq!(parse_thumb_limit(None), 500);
        assert_eq!(parse_thumb_limit(Some("")), 500);
        assert_eq!(parse_thumb_limit(Some("abc")), 500);
        assert_eq!(parse_thumb_limit(Some("-5")), 1);
        assert_eq!(parse_thumb_limit(Some("99999")), 2000);
        assert_eq!(parse_thumb_limit(Some("5.0")), 500);
        assert_eq!(mtime_string(&SqliteNumber::Integer(123)), "123");
        assert_eq!(mtime_string(&SqliteNumber::Real(123.0)), "123.0");
        assert_eq!(mtime_string(&SqliteNumber::Real(123.45)), "123.45");
    }

    #[test]
    fn blake2b_cache_key_matches_python_vector() {
        assert_eq!(
            thumbnail_cache_key("p", &SqliteNumber::Integer(1)).len(),
            32
        );
        assert_eq!(
            thumbnail_cache_key("p", &SqliteNumber::Integer(1)),
            "4c62561cdb5bf12e007799941ed57f3a"
        );
    }

    #[test]
    fn blake2b_boundary_vectors_match_python_hashlib() {
        // Expected values generated with:
        //   hashlib.blake2b(data, digest_size=16).hexdigest()
        assert_eq!(
            hex::encode(blake2b_128(b"")),
            "cae66941d9efbd404e4d88758ea67670"
        );
        assert_eq!(
            hex::encode(blake2b_128(&[b'x'; 128])),
            "874acca82a22239ec64a3e70c3ae494e"
        );
        assert_eq!(
            hex::encode(blake2b_128(&[b'y'; 129])),
            "1387a72eb29ba78bf6693c16ba54611b"
        );
        assert_eq!(
            hex::encode(blake2b_128(
                "日本語パス/ファイル.png:1700000000.5".as_bytes()
            )),
            "b789d3f48e1cfe426c3fb566b9e582e1"
        );
    }

    #[tokio::test]
    async fn container_thumb_response_preserves_order_and_counts_returned_total() {
        let pool = files_pool(
            "INSERT INTO files(id, path, mtime, is_deleted) VALUES
             (1, 'a/1.png', 1, 0),
             (2, 'a/2.png', 2, 0),
             (3, 'b.zip', 3, 0);",
        )
        .await;
        let temp = TempDir::new().unwrap();
        let cache = GroupsIndexCache::new(temp.path().to_path_buf());
        let key = thumbnail_cache_key("a/1.png", &SqliteNumber::Integer(1));
        let sharded = temp
            .path()
            .join("thumbnails")
            .join(&key[0..2])
            .join(&key[2..4])
            .join(format!("{key}.webp"));
        std::fs::create_dir_all(sharded.parent().unwrap()).unwrap();
        std::fs::write(sharded, b"x").unwrap();

        let payload = build_container_thumb_ids_response(&pool, &cache, 2)
            .await
            .unwrap();

        assert_eq!(payload, json!({"ids":[2,3],"total":2,"cached":1}));
    }

    #[test]
    fn json_numbers_preserve_integer_and_real_representations() {
        assert_eq!(
            number_from_sqlite(&SqliteNumber::Integer(123)),
            Number::from(123)
        );
        assert_eq!(
            number_from_sqlite(&SqliteNumber::Real(123.45)),
            Number::from_f64(123.45).unwrap()
        );
    }
}
use std::{
    collections::{HashMap, HashSet},
    path::{Path, PathBuf},
    sync::Mutex,
    time::{SystemTime, UNIX_EPOCH},
};

use indexmap::IndexMap;
use serde::{Deserialize, Serialize};
use serde_json::{json, Number, Value};
use sqlx::{Row, SqlitePool};
use tokio::sync::Mutex as AsyncMutex;

const CACHE_VERSION: i64 = 4;
const BATCH_SIZE: i64 = 50_000;
const IN_CHUNK_SIZE: usize = 500;

#[derive(Debug, Clone, PartialEq)]
pub enum SqliteNumber {
    Integer(i64),
    Real(f64),
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GroupEntry {
    pub ids: Vec<i64>,
    pub label: String,
    pub reps: Vec<i64>,
    pub max_mtime: Number,
}

#[derive(Debug, Serialize, Deserialize, Clone)]
pub struct GroupsIndex {
    pub file_count: i64,
    pub max_mtime: Number,
    pub cache_version: i64,
    pub folders: IndexMap<String, GroupEntry>,
    pub zips: IndexMap<String, GroupEntry>,
}

#[derive(Debug)]
pub struct GroupsIndexCache {
    cache_dir: PathBuf,
    memory: Mutex<Option<(f64, GroupsIndex)>>,
    rebuild_lock: AsyncMutex<()>,
}

#[derive(Clone)]
struct GroupMeta {
    first_path: String,
    max_mtime: SqliteNumber,
}

impl GroupsIndexCache {
    pub fn new(cache_dir: PathBuf) -> Self {
        Self {
            cache_dir,
            memory: Mutex::new(None),
            rebuild_lock: AsyncMutex::new(()),
        }
    }

    pub async fn get(&self, pool: &SqlitePool) -> Result<GroupsIndex, GroupsIndexError> {
        let _guard = self.rebuild_lock.lock().await;
        let cache_path = self.cache_dir.join("groups_index.json");
        let current_mtime = file_mtime_secs(&cache_path);
        if let Some(index) = self.memory_hit(current_mtime) {
            return Ok(index);
        }

        let (file_count, max_mtime) = db_signature(pool).await?;
        if current_mtime != 0.0 {
            if let Ok(raw) = tokio::fs::read_to_string(&cache_path).await {
                if let Ok(index) = serde_json::from_str::<GroupsIndex>(&raw) {
                    if index.file_count == file_count
                        && numbers_equal(&index.max_mtime, &number_from_sqlite(&max_mtime))
                        && index.cache_version == CACHE_VERSION
                    {
                        self.store_memory(current_mtime, index.clone());
                        return Ok(index);
                    }
                }
            }
        }

        let index = build_groups_index(pool).await?;
        tokio::fs::create_dir_all(&self.cache_dir).await?;
        let raw = serde_json::to_string(&index)?;
        tokio::fs::write(&cache_path, raw).await?;
        let built_mtime = file_mtime_secs(&cache_path);
        self.store_memory(built_mtime, index.clone());
        Ok(index)
    }

    fn memory_hit(&self, current_mtime: f64) -> Option<GroupsIndex> {
        let guard = self.memory.lock().ok()?;
        let (cached_mtime, index) = guard.as_ref()?;
        // Cache identity, not a numeric comparison: the entry is valid only for
        // the exact mtime it was built from. A tolerance here would serve a
        // stale index for a file written within epsilon of the cached time.
        #[allow(clippy::float_cmp, reason = "cache key identity, not a measurement")]
        let hit = *cached_mtime == current_mtime;
        if hit {
            Some(index.clone())
        } else {
            None
        }
    }

    fn store_memory(&self, mtime: f64, index: GroupsIndex) {
        if let Ok(mut guard) = self.memory.lock() {
            *guard = Some((mtime, index));
        }
    }

    pub fn invalidate(&self) {
        if let Ok(mut g) = self.memory.lock() {
            *g = None;
        }
        let _ = std::fs::remove_file(self.cache_dir.join("groups_index.json"));
    }
}

#[derive(Debug, thiserror::Error)]
pub enum GroupsIndexError {
    #[error("database error: {0}")]
    Sqlx(#[from] sqlx::Error),
    #[error("io error: {0}")]
    Io(#[from] std::io::Error),
    #[error("json error: {0}")]
    Json(#[from] serde_json::Error),
}

pub async fn build_groups_index(pool: &SqlitePool) -> Result<GroupsIndex, sqlx::Error> {
    let mut file_count = 0_i64;
    let mut max_mtime = SqliteNumber::Integer(0);
    let mut folder_groups: IndexMap<String, Vec<i64>> = IndexMap::new();
    let mut archive_groups: IndexMap<String, Vec<i64>> = IndexMap::new();
    let mut folder_meta: HashMap<String, GroupMeta> = HashMap::new();
    let mut archive_meta: HashMap<String, GroupMeta> = HashMap::new();
    let mut last_id = 0_i64;

    loop {
        let rows = sqlx::query(
            "SELECT id, path, mtime FROM files
             WHERE is_deleted=0 AND id > ? ORDER BY id LIMIT ?",
        )
        .bind(last_id)
        .bind(BATCH_SIZE)
        .fetch_all(pool)
        .await?;
        let batch_count = rows.len();
        for row in rows {
            let fid = row.get::<i64, _>("id");
            let path = row
                .try_get::<Option<String>, _>("path")?
                .unwrap_or_default();
            let mtime = row_sqlite_number(&row, "mtime").unwrap_or(SqliteNumber::Integer(0));
            file_count += 1;
            if sqlite_number_as_f64(&mtime) > sqlite_number_as_f64(&max_mtime) {
                max_mtime = mtime.clone();
            }
            if is_archive_member(&path) {
                let key = format!("archive:{}", archive_part(&path).to_lowercase());
                append_group(
                    &mut archive_groups,
                    &mut archive_meta,
                    key,
                    fid,
                    path,
                    mtime,
                );
            } else if is_archive_file(&path) {
                let key = format!("archive:{}", path.to_lowercase());
                append_group(
                    &mut archive_groups,
                    &mut archive_meta,
                    key,
                    fid,
                    path,
                    mtime,
                );
            } else {
                let norm = path.replace('\\', "/");
                let idx = norm.rfind('/');
                let dirname_lower = if idx.is_some_and(|idx| idx > 0) {
                    norm[..idx.unwrap()].to_lowercase()
                } else {
                    ".".to_string()
                };
                let key = format!("folder:{dirname_lower}");
                append_group(&mut folder_groups, &mut folder_meta, key, fid, path, mtime);
            }
            last_id = fid;
        }
        if batch_count < usize::try_from(BATCH_SIZE).unwrap_or(usize::MAX) {
            break;
        }
    }

    Ok(GroupsIndex {
        file_count,
        max_mtime: number_from_sqlite(&max_mtime),
        cache_version: CACHE_VERSION,
        folders: build_entries(folder_groups, folder_meta, 2),
        zips: build_entries(archive_groups, archive_meta, 1),
    })
}

pub async fn db_signature(pool: &SqlitePool) -> Result<(i64, SqliteNumber), sqlx::Error> {
    let row = sqlx::query(
        "SELECT COUNT(*) AS file_count, MAX(mtime) AS max_mtime FROM files WHERE is_deleted = 0",
    )
    .fetch_one(pool)
    .await?;
    let file_count = row.get::<i64, _>("file_count");
    let max_mtime = row_sqlite_number(&row, "max_mtime").unwrap_or(SqliteNumber::Integer(0));
    Ok((file_count, max_mtime))
}

pub async fn build_container_thumb_ids_response(
    pool: &SqlitePool,
    cache: &GroupsIndexCache,
    limit: i64,
) -> Result<Value, GroupsIndexError> {
    let index = cache.get(pool).await?;
    let rep_ids = all_rep_ids(&index);
    if rep_ids.is_empty() {
        return Ok(json!({"ids": [], "total": 0, "cached": 0}));
    }

    let mut file_info = HashMap::<i64, (String, SqliteNumber)>::new();
    for chunk in rep_ids.chunks(IN_CHUNK_SIZE) {
        let placeholders = std::iter::repeat_n("?", chunk.len())
            .collect::<Vec<_>>()
            .join(",");
        let sql = format!(
            "SELECT id, path, mtime FROM files WHERE id IN ({placeholders}) AND is_deleted = 0"
        );
        let mut query = sqlx::query(&sql);
        for fid in chunk {
            query = query.bind(fid);
        }
        for row in query.fetch_all(pool).await? {
            let fid = row.get::<i64, _>("id");
            let path = row
                .try_get::<Option<String>, _>("path")?
                .unwrap_or_default();
            let mtime = row_sqlite_number(&row, "mtime").unwrap_or(SqliteNumber::Integer(0));
            file_info.insert(fid, (path, mtime));
        }
    }

    let thumb_dir = cache.cache_dir.join("thumbnails");
    tokio::fs::create_dir_all(&thumb_dir).await?;
    let mut ids = Vec::new();
    let mut cached = 0_i64;
    for fid in rep_ids {
        let Some((path, mtime)) = file_info.get(&fid) else {
            continue;
        };
        let key = thumbnail_cache_key(path, mtime);
        if thumbnail_exists(&thumb_dir, &key) {
            cached += 1;
        } else {
            ids.push(fid);
            if ids.len() >= usize::try_from(limit).unwrap_or(500) {
                break;
            }
        }
    }
    Ok(json!({"ids": ids, "total": ids.len(), "cached": cached}))
}

pub fn parse_thumb_limit(raw: Option<&str>) -> i64 {
    match raw.unwrap_or("500").trim().parse::<i64>() {
        Ok(value) => value.clamp(1, 2000),
        Err(_) => 500,
    }
}

pub fn all_rep_ids(index: &GroupsIndex) -> Vec<i64> {
    let mut seen = HashSet::new();
    let mut result = Vec::new();
    for groups in [&index.folders, &index.zips] {
        for entry in groups.values() {
            for fid in &entry.reps {
                if seen.insert(*fid) {
                    result.push(*fid);
                }
            }
        }
    }
    result
}

pub fn thumbnail_cache_key(path: &str, mtime: &SqliteNumber) -> String {
    hex::encode(blake2b_128(
        format!("{path}:{}", mtime_string(mtime)).as_bytes(),
    ))
}

pub fn mtime_string(mtime: &SqliteNumber) -> String {
    match mtime {
        SqliteNumber::Integer(value) => value.to_string(),
        SqliteNumber::Real(value)
            if value.is_finite() && value.fract() == 0.0 && value.abs() < 1e16 =>
        {
            format!("{value:.1}")
        }
        SqliteNumber::Real(value) => value.to_string(),
    }
}

pub fn number_from_sqlite(value: &SqliteNumber) -> Number {
    match value {
        SqliteNumber::Integer(value) => Number::from(*value),
        SqliteNumber::Real(value) => Number::from_f64(*value).unwrap_or_else(|| Number::from(0)),
    }
}

pub fn archive_part(path: &str) -> String {
    [".zip!", ".7z!", ".rar!"]
        .iter()
        .filter_map(|pattern| {
            find_ascii_case_insensitive(path, pattern).map(|idx| (idx, pattern.len()))
        })
        .min_by_key(|(idx, _)| *idx)
        .map(|(idx, len)| path[..idx + len - 1].to_string())
        .unwrap_or_else(|| path.to_string())
}

fn append_group(
    groups: &mut IndexMap<String, Vec<i64>>,
    meta_map: &mut HashMap<String, GroupMeta>,
    key: String,
    fid: i64,
    path: String,
    mtime: SqliteNumber,
) {
    groups.entry(key.clone()).or_default().push(fid);
    match meta_map.get_mut(&key) {
        Some(meta) if sqlite_number_as_f64(&mtime) > sqlite_number_as_f64(&meta.max_mtime) => {
            meta.max_mtime = mtime;
        }
        Some(_) => {}
        None => {
            meta_map.insert(
                key,
                GroupMeta {
                    first_path: path,
                    max_mtime: mtime,
                },
            );
        }
    }
}

fn build_entries(
    groups: IndexMap<String, Vec<i64>>,
    meta_map: HashMap<String, GroupMeta>,
    min_members: usize,
) -> IndexMap<String, GroupEntry> {
    let mut out = IndexMap::new();
    for (key, ids) in groups {
        if ids.len() < min_members {
            continue;
        }
        let Some(meta) = meta_map.get(&key) else {
            continue;
        };
        out.insert(
            key.clone(),
            GroupEntry {
                label: group_label(&key, &meta.first_path),
                reps: ids.iter().take(8).copied().collect(),
                ids,
                max_mtime: number_from_sqlite(&meta.max_mtime),
            },
        );
    }
    out
}

fn group_label(key: &str, first_path: &str) -> String {
    if key.starts_with("archive:") {
        return basename(
            &container_path(first_path)
                .filter(|p| !p.is_empty())
                .unwrap_or_else(|| first_path.to_string()),
        );
    }
    if key.starts_with("folder:") {
        let dir = dirname(first_path);
        let parts = dir.replace('\\', "/");
        return parts
            .split('/')
            .next_back()
            .filter(|part| !part.is_empty())
            .unwrap_or(&dir)
            .to_string();
    }
    basename(first_path)
}

fn container_path(path: &str) -> Option<String> {
    if is_archive_member(path) {
        Some(archive_part(path))
    } else if is_archive_file(path) {
        Some(path.to_string())
    } else {
        Some(String::new())
    }
}

fn dirname(path: &str) -> String {
    let norm = path.replace('\\', "/");
    match norm.rfind('/') {
        Some(idx) if idx > 0 => norm[..idx].to_string(),
        _ => ".".to_string(),
    }
}

fn basename(path: &str) -> String {
    let norm = path.replace('\\', "/");
    match norm.rfind('/') {
        Some(idx) => norm[idx + 1..].to_string(),
        None => norm,
    }
}

fn is_archive_member(path: &str) -> bool {
    path.chars().next().is_some()
        && [".zip!", ".7z!", ".rar!"].iter().any(|pattern| {
            find_ascii_case_insensitive(path, pattern)
                .is_some_and(|idx| idx > 0 && idx + pattern.len() < path.len())
        })
}

fn is_archive_file(path: &str) -> bool {
    let lower = path.to_ascii_lowercase();
    lower.ends_with(".zip") || lower.ends_with(".7z") || lower.ends_with(".rar")
}

fn find_ascii_case_insensitive(haystack: &str, needle: &str) -> Option<usize> {
    let hay = haystack.as_bytes();
    let nee = needle.as_bytes();
    if nee.is_empty() || hay.len() < nee.len() {
        return None;
    }
    hay.windows(nee.len()).position(|window| {
        window
            .iter()
            .zip(nee)
            .all(|(a, b)| a.eq_ignore_ascii_case(b))
    })
}

fn row_sqlite_number(row: &sqlx::sqlite::SqliteRow, column: &str) -> Option<SqliteNumber> {
    match row.try_get::<Option<i64>, _>(column) {
        Ok(Some(value)) => return Some(SqliteNumber::Integer(value)),
        Ok(None) => return None,
        Err(_) => {}
    }
    match row.try_get::<Option<f64>, _>(column) {
        Ok(Some(value)) => Some(SqliteNumber::Real(value)),
        _ => None,
    }
}

fn sqlite_number_as_f64(value: &SqliteNumber) -> f64 {
    match value {
        SqliteNumber::Integer(value) => *value as f64,
        SqliteNumber::Real(value) => *value,
    }
}

fn numbers_equal(left: &Number, right: &Number) -> bool {
    match (left.as_f64(), right.as_f64()) {
        // Value equality of two JSON numbers, which is what the callers ask
        // for. A tolerance would make 1.0 and 1.0000001 the same tag value.
        #[allow(clippy::float_cmp, reason = "JSON number equality, not a measurement")]
        (Some(left), Some(right)) => left == right,
        _ => left == right,
    }
}

fn file_mtime_secs(path: &Path) -> f64 {
    std::fs::metadata(path)
        .and_then(|meta| meta.modified())
        .ok()
        .and_then(system_time_secs)
        .unwrap_or(0.0)
}

fn system_time_secs(value: SystemTime) -> Option<f64> {
    value.duration_since(UNIX_EPOCH).ok().map(|duration| {
        duration.as_secs() as f64 + f64::from(duration.subsec_nanos()) / 1_000_000_000.0
    })
}

fn thumbnail_exists(cache_dir: &Path, key: &str) -> bool {
    // Python gates JPEG fallback on Pillow WebP support; deployment enables WebP, so Rust checks all legacy paths.
    [
        cache_dir
            .join(&key[0..2])
            .join(&key[2..4])
            .join(format!("{key}.webp")),
        cache_dir
            .join(&key[0..2])
            .join(&key[2..4])
            .join(format!("{key}.jpg")),
        cache_dir.join(format!("{key}.webp")),
        cache_dir.join(format!("{key}.jpg")),
    ]
    .iter()
    .any(|path| path.exists())
}

fn blake2b_128(input: &[u8]) -> [u8; 16] {
    const IV: [u64; 8] = [
        0x6a09e667f3bcc908,
        0xbb67ae8584caa73b,
        0x3c6ef372fe94f82b,
        0xa54ff53a5f1d36f1,
        0x510e527fade682d1,
        0x9b05688c2b3e6c1f,
        0x1f83d9abfb41bd6b,
        0x5be0cd19137e2179,
    ];
    let mut h = IV;
    h[0] ^= 0x0101_0010;
    let mut offset = 0_usize;
    while input.len().saturating_sub(offset) > 128 {
        let mut block = [0_u8; 128];
        block.copy_from_slice(&input[offset..offset + 128]);
        offset += 128;
        blake2b_compress(&mut h, &block, offset as u128, false);
    }
    let mut block = [0_u8; 128];
    block[..input.len() - offset].copy_from_slice(&input[offset..]);
    blake2b_compress(&mut h, &block, input.len() as u128, true);
    let mut out = [0_u8; 16];
    for (chunk, word) in out.chunks_mut(8).zip(h) {
        chunk.copy_from_slice(&word.to_le_bytes());
    }
    out
}

fn blake2b_compress(h: &mut [u64; 8], block: &[u8; 128], counter: u128, last: bool) {
    const IV: [u64; 8] = [
        0x6a09e667f3bcc908,
        0xbb67ae8584caa73b,
        0x3c6ef372fe94f82b,
        0xa54ff53a5f1d36f1,
        0x510e527fade682d1,
        0x9b05688c2b3e6c1f,
        0x1f83d9abfb41bd6b,
        0x5be0cd19137e2179,
    ];
    const SIGMA: [[usize; 16]; 12] = [
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
        [11, 8, 12, 0, 5, 2, 15, 13, 10, 14, 3, 6, 7, 1, 9, 4],
        [7, 9, 3, 1, 13, 12, 11, 14, 2, 6, 5, 10, 4, 0, 15, 8],
        [9, 0, 5, 7, 2, 4, 10, 15, 14, 1, 11, 12, 6, 8, 3, 13],
        [2, 12, 6, 10, 0, 11, 8, 3, 4, 13, 7, 5, 15, 14, 1, 9],
        [12, 5, 1, 15, 14, 13, 4, 10, 0, 7, 6, 3, 9, 2, 8, 11],
        [13, 11, 7, 14, 12, 1, 3, 9, 5, 0, 15, 4, 8, 6, 2, 10],
        [6, 15, 14, 9, 11, 3, 0, 8, 12, 2, 13, 7, 1, 4, 10, 5],
        [10, 2, 8, 4, 7, 6, 1, 5, 15, 11, 9, 14, 3, 12, 13, 0],
        [0, 1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15],
        [14, 10, 4, 8, 9, 15, 13, 6, 1, 12, 0, 2, 11, 7, 5, 3],
    ];
    let mut m = [0_u64; 16];
    for (idx, chunk) in block.as_chunks::<8>().0.iter().enumerate() {
        m[idx] = u64::from_le_bytes(*chunk);
    }
    let mut v = [0_u64; 16];
    v[..8].copy_from_slice(h);
    v[8..].copy_from_slice(&IV);
    // BLAKE2b mixes its 128-bit counter in as two 64-bit halves: the low half
    // discarding the high bits is the specified operation, not a lossy cast,
    // and the shifted line below supplies exactly the bits dropped here.
    #[allow(clippy::cast_possible_truncation)]
    {
        v[12] ^= counter as u64;
        v[13] ^= (counter >> 64) as u64;
    }
    if last {
        v[14] = !v[14];
    }
    for sigma in SIGMA {
        blake2b_g(&mut v, 0, 4, 8, 12, m[sigma[0]], m[sigma[1]]);
        blake2b_g(&mut v, 1, 5, 9, 13, m[sigma[2]], m[sigma[3]]);
        blake2b_g(&mut v, 2, 6, 10, 14, m[sigma[4]], m[sigma[5]]);
        blake2b_g(&mut v, 3, 7, 11, 15, m[sigma[6]], m[sigma[7]]);
        blake2b_g(&mut v, 0, 5, 10, 15, m[sigma[8]], m[sigma[9]]);
        blake2b_g(&mut v, 1, 6, 11, 12, m[sigma[10]], m[sigma[11]]);
        blake2b_g(&mut v, 2, 7, 8, 13, m[sigma[12]], m[sigma[13]]);
        blake2b_g(&mut v, 3, 4, 9, 14, m[sigma[14]], m[sigma[15]]);
    }
    for idx in 0..8 {
        h[idx] ^= v[idx] ^ v[idx + 8];
    }
}

fn blake2b_g(v: &mut [u64; 16], a: usize, b: usize, c: usize, d: usize, x: u64, y: u64) {
    v[a] = v[a].wrapping_add(v[b]).wrapping_add(x);
    v[d] = (v[d] ^ v[a]).rotate_right(32);
    v[c] = v[c].wrapping_add(v[d]);
    v[b] = (v[b] ^ v[c]).rotate_right(24);
    v[a] = v[a].wrapping_add(v[b]).wrapping_add(y);
    v[d] = (v[d] ^ v[a]).rotate_right(16);
    v[c] = v[c].wrapping_add(v[d]);
    v[b] = (v[b] ^ v[c]).rotate_right(63);
}
