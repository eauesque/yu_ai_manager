//! Persistent usearch index for CLIP vectors.
//!
//! Construction reads vectors.db in fixed-size cursor pages. The active index
//! is an `Arc` behind an `RwLock`, so a completed rebuild swaps it only after
//! every persistence step succeeds; searches continue on the previous index.

use std::path::{Path, PathBuf};
use std::sync::{Arc, RwLock};

use serde::{Deserialize, Serialize};
use sqlx::SqlitePool;
use usearch::{Index, IndexOptions, MetricKind, ScalarKind};

use super::vector_store::{self, StoredVector, VectorStoreError, DEFAULT_MODEL};

const INDEX_SCHEMA_VERSION: u32 = 1;
const DEFAULT_DIMENSIONS: usize = 512;
const DEFAULT_BUILD_BATCH_SIZE: i64 = 2_000;

#[derive(Debug, thiserror::Error)]
pub enum ClipIndexError {
    #[error(transparent)]
    VectorStore(#[from] VectorStoreError),
    #[error(transparent)]
    Io(#[from] std::io::Error),
    #[error(transparent)]
    Json(#[from] serde_json::Error),
    #[error("usearch error: {0}")]
    Usearch(String),
    #[error("model name contains an unsafe path component: {0}")]
    UnsafeModel(String),
    #[error("vector dimension mismatch: expected {expected}, got {actual}")]
    DimensionMismatch { expected: usize, actual: usize },
    #[error("vectors.db changed during index construction; retained the previous index")]
    ChangedDuringBuild,
    #[error("invalid ids.bin length: {0}")]
    InvalidIdsLength(usize),
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub struct IndexMeta {
    /// Monotonically increasing identifier for the immutable index files this
    /// metadata points to.
    pub generation: u64,
    pub schema_version: u32,
    pub model: String,
    pub dimensions: usize,
    pub vector_count: i64,
    /// `MAX(file_vectors.created_at)` at a successful build. Together with
    /// count this catches replacement drift that a count-only check misses.
    pub latest_created_at: i64,
}

struct LoadedClipIndex {
    index: Index,
    meta: IndexMeta,
}

pub struct ClipIndex {
    cache_dir: PathBuf,
    model: String,
    dimensions: usize,
    active: RwLock<Option<Arc<LoadedClipIndex>>>,
    rebuild_lock: tokio::sync::Mutex<()>,
}

impl ClipIndex {
    pub fn new(
        cache_dir: impl Into<PathBuf>,
        model: impl Into<String>,
        dimensions: usize,
    ) -> Result<Self, ClipIndexError> {
        let model = model.into();
        if !is_safe_model_name(&model) {
            return Err(ClipIndexError::UnsafeModel(model));
        }
        Ok(Self {
            cache_dir: cache_dir.into(),
            model,
            dimensions: dimensions.max(1),
            active: RwLock::new(None),
            rebuild_lock: tokio::sync::Mutex::new(()),
        })
    }

    pub fn new_default(cache_dir: impl Into<PathBuf>) -> Result<Self, ClipIndexError> {
        Self::new(cache_dir, DEFAULT_MODEL, DEFAULT_DIMENSIONS)
    }

    /// Loads the durable index only when its vectors.db snapshot still matches.
    /// Returns `true` when an index was loaded and atomically made active.
    pub async fn load_if_current(
        &self,
        vectors_db_read: &SqlitePool,
    ) -> Result<bool, ClipIndexError> {
        let paths = self.paths();
        if !paths.current.exists() {
            return Ok(false);
        }
        let meta: IndexMeta = serde_json::from_slice(&std::fs::read(&paths.current)?)?;
        let generation_paths = paths.generation(meta.generation);
        if meta.generation == 0
            || !generation_paths.index.exists()
            || !generation_paths.ids.exists()
            || meta.schema_version != INDEX_SCHEMA_VERSION
            || meta.model != self.model
            || meta.dimensions != self.dimensions
            || self.is_drifted(vectors_db_read, &meta).await?
        {
            return Ok(false);
        }
        let ids = read_ids(&generation_paths.ids)?;
        if ids.len() as i64 != meta.vector_count {
            return Ok(false);
        }
        let index = restore_index_view(&generation_paths.index)?;
        if index.size() as i64 != meta.vector_count {
            return Ok(false);
        }
        self.replace_active(LoadedClipIndex { index, meta });
        cleanup_old_generations(&paths, generation_paths.generation);
        Ok(true)
    }

    /// Builds a new usearch index from bounded cursor pages and atomically
    /// replaces the active mmap-backed index after persistence succeeds.
    pub async fn rebuild(
        &self,
        vectors_db_read: &SqlitePool,
        batch_size: Option<i64>,
    ) -> Result<IndexMeta, ClipIndexError> {
        let _guard = self.rebuild_lock.lock().await;
        let before = vector_store::vector_snapshot(vectors_db_read, &self.model).await?;
        let batch_size = batch_size
            .unwrap_or(DEFAULT_BUILD_BATCH_SIZE)
            .clamp(1, 16_384);
        let (index, ids) = build_index(
            vectors_db_read,
            &self.model,
            self.dimensions,
            before.0,
            batch_size,
        )
        .await?;
        let after = vector_store::vector_snapshot(vectors_db_read, &self.model).await?;
        if before != after {
            return Err(ClipIndexError::ChangedDuringBuild);
        }

        let paths = self.paths();
        let meta = IndexMeta {
            generation: paths.next_generation()?,
            schema_version: INDEX_SCHEMA_VERSION,
            model: self.model.clone(),
            dimensions: self.dimensions,
            vector_count: after.0,
            latest_created_at: after.1,
        };
        let generation_paths = paths.generation(meta.generation);
        persist_index(&paths, &generation_paths, &index, &ids, &meta)?;
        // The construction index owns all HNSW data in process memory. Reopen
        // the durable file as a read-only mmap view before publication, then
        // release that construction allocation before acquiring the active lock.
        let active_index = restore_index_view(&generation_paths.index)?;
        drop(index);
        self.replace_active(LoadedClipIndex {
            index: active_index,
            meta: meta.clone(),
        });
        cleanup_old_generations(&paths, generation_paths.generation);
        Ok(meta)
    }

    pub async fn is_drifted(
        &self,
        vectors_db_read: &SqlitePool,
        meta: &IndexMeta,
    ) -> Result<bool, ClipIndexError> {
        Ok(
            vector_store::vector_snapshot(vectors_db_read, &self.model).await?
                != (meta.vector_count, meta.latest_created_at),
        )
    }

    pub fn active_meta(&self) -> Option<IndexMeta> {
        self.active
            .read()
            .expect("clip index lock poisoned")
            .as_ref()
            .map(|loaded| loaded.meta.clone())
    }

    /// Removes the active and durable native index. `vectors.db` is managed
    /// separately by the caller so clearing remains an explicit two-step API.
    pub async fn clear(&self) -> Result<(), ClipIndexError> {
        let _guard = self.rebuild_lock.lock().await;
        *self.active.write().expect("clip index lock poisoned") = None;
        let paths = self.paths();
        // A just-released mmap can still hold a Windows file handle briefly.
        // Clear is therefore complete once the in-process index and pointer
        // are removed; stale generation files are retried by later cleanup.
        remove_file_best_effort(&paths.current);
        remove_all_generations(&paths);
        Ok(())
    }

    /// Searches the current index. USearch cosine distance is converted to a
    /// cosine similarity score (`1.0 - distance`) before threshold filtering.
    pub fn search(
        &self,
        query_vec: &[f32],
        limit: usize,
        threshold: f32,
    ) -> Result<Vec<(i64, f32)>, ClipIndexError> {
        if query_vec.len() != self.dimensions {
            return Err(ClipIndexError::DimensionMismatch {
                expected: self.dimensions,
                actual: query_vec.len(),
            });
        }
        if limit == 0 || !threshold.is_finite() {
            return Ok(Vec::new());
        }
        let active = self
            .active
            .read()
            .expect("clip index lock poisoned")
            .clone();
        let Some(loaded) = active else {
            return Ok(Vec::new());
        };
        let matches = loaded
            .index
            .search(query_vec, limit)
            .map_err(|error| ClipIndexError::Usearch(error.to_string()))?;
        Ok(matches
            .keys
            .iter()
            .zip(matches.distances.iter())
            .filter_map(|(key, distance)| {
                let file_id = i64::try_from(*key).ok()?;
                let score = 1.0 - *distance;
                (score >= threshold).then_some((file_id, score))
            })
            .collect())
    }

    fn replace_active(&self, new_index: LoadedClipIndex) {
        *self.active.write().expect("clip index lock poisoned") = Some(Arc::new(new_index));
    }

    fn paths(&self) -> IndexPaths {
        let dir = self
            .cache_dir
            .join("clip_search")
            .join("usearch")
            .join(&self.model);
        IndexPaths {
            current: dir.join("current.json"),
            dir,
        }
    }
}

struct IndexPaths {
    dir: PathBuf,
    current: PathBuf,
}

impl IndexPaths {
    fn generation(&self, generation: u64) -> GenerationPaths {
        GenerationPaths {
            generation,
            index: self.dir.join(format!("index.g{generation}.usearch")),
            ids: self.dir.join(format!("ids.g{generation}.bin")),
        }
    }

    fn next_generation(&self) -> Result<u64, ClipIndexError> {
        let entries = match std::fs::read_dir(&self.dir) {
            Ok(entries) => entries,
            Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(1),
            Err(error) => return Err(error.into()),
        };
        let mut highest = 0;
        for entry in entries {
            let entry = entry?;
            let Some(name) = entry.file_name().to_str().map(str::to_owned) else {
                continue;
            };
            if let Some(generation) = generation_from_file_name(&name) {
                highest = highest.max(generation);
            }
        }
        highest
            .checked_add(1)
            .ok_or_else(|| ClipIndexError::Usearch("index generation exhausted".to_string()))
    }
}

struct GenerationPaths {
    generation: u64,
    index: PathBuf,
    ids: PathBuf,
}

async fn build_index(
    vectors_db_read: &SqlitePool,
    model: &str,
    dimensions: usize,
    capacity: i64,
    batch_size: i64,
) -> Result<(Index, Vec<i64>), ClipIndexError> {
    let options = IndexOptions {
        dimensions,
        metric: MetricKind::Cos,
        quantization: ScalarKind::F32,
        ..Default::default()
    };
    let index = Index::new(&options).map_err(|error| ClipIndexError::Usearch(error.to_string()))?;
    index
        .reserve(usize::try_from(capacity.max(1)).unwrap_or(1))
        .map_err(|error| ClipIndexError::Usearch(error.to_string()))?;

    let mut after_file_id = 0;
    let mut ids = Vec::with_capacity(usize::try_from(capacity.max(0)).unwrap_or(0));
    loop {
        let batch =
            vector_store::load_vectors_cursor(vectors_db_read, model, after_file_id, batch_size)
                .await?;
        let Some(last) = batch.last() else {
            break;
        };
        after_file_id = last.file_id;
        ids.extend(batch.iter().map(|stored| stored.file_id));
        add_batch(&index, batch, dimensions)?;
    }
    Ok((index, ids))
}

fn add_batch(
    index: &Index,
    batch: Vec<StoredVector>,
    dimensions: usize,
) -> Result<(), ClipIndexError> {
    for stored in batch {
        if stored.vector.len() != dimensions {
            return Err(ClipIndexError::DimensionMismatch {
                expected: dimensions,
                actual: stored.vector.len(),
            });
        }
        let key = u64::try_from(stored.file_id)
            .map_err(|_| ClipIndexError::Usearch("negative file_id".to_string()))?;
        index
            .add(key, &stored.vector)
            .map_err(|error| ClipIndexError::Usearch(error.to_string()))?;
    }
    Ok(())
}

fn persist_index(
    paths: &IndexPaths,
    generation_paths: &GenerationPaths,
    index: &Index,
    ids: &[i64],
    meta: &IndexMeta,
) -> Result<(), ClipIndexError> {
    std::fs::create_dir_all(&paths.dir)?;
    if generation_paths.index.exists() || generation_paths.ids.exists() {
        return Err(ClipIndexError::Io(std::io::Error::new(
            std::io::ErrorKind::AlreadyExists,
            format!(
                "index generation {} already exists",
                generation_paths.generation
            ),
        )));
    }
    let temp_dir = tempfile::Builder::new()
        .prefix(".usearch-")
        .tempdir_in(&paths.dir)?;
    let temp_index = temp_dir.path().join("index.usearch");
    let temp_ids = temp_dir.path().join("ids.bin");
    let temp_current = temp_dir.path().join("current.json");
    index
        .save(path_string(&temp_index)?)
        .map_err(|error| ClipIndexError::Usearch(error.to_string()))?;
    write_ids(&temp_ids, ids)?;
    std::fs::write(&temp_current, serde_json::to_vec_pretty(meta)?)?;

    // Generation files are immutable, so an active mmap never blocks these
    // renames on Windows. The fixed pointer is replaced last and is never
    // memory-mapped, so it publishes a complete generation atomically.
    std::fs::rename(&temp_index, &generation_paths.index)?;
    std::fs::rename(&temp_ids, &generation_paths.ids)?;
    std::fs::rename(&temp_current, &paths.current)?;
    Ok(())
}

fn cleanup_old_generations(paths: &IndexPaths, current_generation: u64) {
    for_generation_file(paths, |generation, path| {
        if generation < current_generation {
            remove_file_best_effort(path);
        }
    });
}

fn remove_all_generations(paths: &IndexPaths) {
    for_generation_file(paths, |_generation, path| remove_file_best_effort(path));
}

fn for_generation_file(paths: &IndexPaths, mut operation: impl FnMut(u64, &Path)) {
    let entries = match std::fs::read_dir(&paths.dir) {
        Ok(entries) => entries,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return,
        Err(error) => {
            tracing::warn!(error = %error, path = %paths.dir.display(), "failed to scan CLIP index generations for cleanup");
            return;
        }
    };
    for entry in entries {
        let entry = match entry {
            Ok(entry) => entry,
            Err(error) => {
                tracing::warn!(error = %error, "failed to inspect a CLIP index generation for cleanup");
                continue;
            }
        };
        let path = entry.path();
        let Some(name) = path.file_name().and_then(|name| name.to_str()) else {
            continue;
        };
        if let Some(generation) = generation_from_file_name(name) {
            operation(generation, &path);
        }
    }
}

fn generation_from_file_name(name: &str) -> Option<u64> {
    name.strip_prefix("index.g")
        .and_then(|generation| generation.strip_suffix(".usearch"))
        .or_else(|| {
            name.strip_prefix("ids.g")
                .and_then(|generation| generation.strip_suffix(".bin"))
        })
        .and_then(|generation| generation.parse().ok())
}

fn remove_file_best_effort(path: &Path) {
    match std::fs::remove_file(path) {
        Ok(()) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {}
        Err(error) => {
            tracing::warn!(error = %error, path = %path.display(), "failed to remove stale CLIP index file")
        }
    }
}

/// Opens an immutable on-disk index without copying its HNSW data into the
/// process heap. `Index::search` is supported for indexes opened this way.
fn restore_index_view(path: &Path) -> Result<Index, ClipIndexError> {
    Index::restore_view(path_string(path)?)
        .map_err(|error| ClipIndexError::Usearch(error.to_string()))
}

fn write_ids(path: &Path, file_ids: &[i64]) -> Result<(), ClipIndexError> {
    let mut ids = Vec::with_capacity(std::mem::size_of_val(file_ids));
    // Keys are file IDs, but preserve a separate Python-compatible lookup
    // artifact for validation and future non-file-id key strategies.
    for file_id in file_ids {
        ids.extend_from_slice(&file_id.to_le_bytes());
    }
    std::fs::write(path, ids)?;
    Ok(())
}

fn read_ids(path: &Path) -> Result<Vec<i64>, ClipIndexError> {
    let bytes = std::fs::read(path)?;
    if bytes.len() % std::mem::size_of::<i64>() != 0 {
        return Err(ClipIndexError::InvalidIdsLength(bytes.len()));
    }
    Ok(bytes
        .as_chunks::<{ std::mem::size_of::<i64>() }>()
        .0
        .iter()
        .map(|&bytes| i64::from_le_bytes(bytes))
        .collect())
}

fn path_string(path: &Path) -> Result<&str, ClipIndexError> {
    path.to_str().ok_or_else(|| {
        ClipIndexError::Io(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "non-UTF-8 index path",
        ))
    })
}

fn is_safe_model_name(model: &str) -> bool {
    !model.is_empty()
        && model
            .bytes()
            .all(|byte| byte.is_ascii_alphanumeric() || matches!(byte, b'_' | b'-' | b'.'))
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;

    async fn vectors_pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE file_vectors (file_id INTEGER PRIMARY KEY, model TEXT NOT NULL, vector BLOB NOT NULL, created_at INTEGER NOT NULL DEFAULT 0);",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    #[tokio::test]
    async fn builds_searches_persists_and_detects_drift() {
        let vectors = vectors_pool().await;
        vector_store::save_vectors_batch(
            &vectors,
            &[11, 22],
            &[vec![1.0, 0.0], vec![0.0, 1.0]],
            DEFAULT_MODEL,
        )
        .await
        .unwrap();
        let cache = tempfile::tempdir().unwrap();
        let index = ClipIndex::new(cache.path(), DEFAULT_MODEL, 2).unwrap();
        let meta = index.rebuild(&vectors, Some(1)).await.unwrap();
        assert_eq!(meta.vector_count, 2);
        assert_eq!(index.search(&[1.0, 0.0], 2, 0.5).unwrap()[0].0, 11);
        let paths = index.paths();
        let generation_paths = paths.generation(meta.generation);
        assert!(generation_paths.index.exists());
        assert!(generation_paths.ids.exists());
        assert!(paths.current.exists());

        let reloaded = ClipIndex::new(cache.path(), DEFAULT_MODEL, 2).unwrap();
        assert!(reloaded.load_if_current(&vectors).await.unwrap());
        assert_eq!(
            reloaded.search(&[1.0, 0.0], 2, 0.5).unwrap()[0].0,
            11,
            "the restore_view-backed index remains searchable"
        );
        vector_store::save_vector(&vectors, 11, &[0.0, 1.0], DEFAULT_MODEL)
            .await
            .unwrap();
        assert!(reloaded.is_drifted(&vectors, &meta).await.unwrap());
    }

    #[tokio::test]
    async fn rebuild_uses_new_generation_and_cleans_old_files() {
        let vectors = vectors_pool().await;
        vector_store::save_vectors_batch(
            &vectors,
            &[11, 22],
            &[vec![1.0, 0.0], vec![0.0, 1.0]],
            DEFAULT_MODEL,
        )
        .await
        .unwrap();
        let cache = tempfile::tempdir().unwrap();
        let index = ClipIndex::new(cache.path(), DEFAULT_MODEL, 2).unwrap();

        let first = index.rebuild(&vectors, Some(1)).await.unwrap();
        let paths = index.paths();
        let first_paths = paths.generation(first.generation);
        assert!(first_paths.index.exists());
        assert!(first_paths.ids.exists());

        let second = index.rebuild(&vectors, Some(1)).await.unwrap();
        let second_paths = paths.generation(second.generation);
        assert!(second.generation > first.generation);
        assert!(second_paths.index.exists());
        assert!(second_paths.ids.exists());
        assert!(!first_paths.index.exists());
        assert!(!first_paths.ids.exists());
        assert_eq!(generation_file_count(&paths), 2);

        let current: IndexMeta =
            serde_json::from_slice(&std::fs::read(&paths.current).unwrap()).unwrap();
        assert_eq!(current.generation, second.generation);
        assert_eq!(index.search(&[1.0, 0.0], 2, 0.5).unwrap()[0].0, 11);
    }

    fn generation_file_count(paths: &IndexPaths) -> usize {
        std::fs::read_dir(&paths.dir)
            .unwrap()
            .filter_map(Result::ok)
            .filter(|entry| {
                entry
                    .file_name()
                    .to_str()
                    .and_then(generation_from_file_name)
                    .is_some()
            })
            .count()
    }
}
