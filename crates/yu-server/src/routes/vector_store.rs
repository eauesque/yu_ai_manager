//! Python-compatible CRUD for CLIP embeddings in `vectors.db`.
//!
//! Vectors are stored as little-endian float16 BLOBs. Read APIs intentionally
//! page with a file-id cursor: a full float32 materialization is unsafe on the
//! Raspberry Pi at the expected 1.5M-file scale.

use half::f16;
use sqlx::{Row, SqlitePool};

pub const DEFAULT_MODEL: &str = "clip_vit_b_16";
const IN_CHUNK_SIZE: usize = 500;
const UNINDEXED_WINDOW_MULTIPLIER: i64 = 8;
const MIN_UNINDEXED_WINDOW: i64 = 4_000;

#[derive(Debug, thiserror::Error)]
pub enum VectorStoreError {
    #[error(transparent)]
    Sql(#[from] sqlx::Error),
    #[error("file_ids ({file_ids}) and vectors ({vectors}) have different lengths")]
    BatchLength { file_ids: usize, vectors: usize },
    #[error("invalid float16 vector blob length: {0}")]
    InvalidBlobLength(usize),
}

#[derive(Debug, Clone, PartialEq)]
pub struct StoredVector {
    pub file_id: i64,
    pub vector: Vec<f32>,
    pub created_at: i64,
}

pub async fn save_vector(
    vectors_db: &SqlitePool,
    file_id: i64,
    vector: &[f32],
    model: &str,
) -> Result<(), VectorStoreError> {
    let blob = encode_f16(vector);
    sqlx::query(
        "INSERT INTO file_vectors (file_id, model, vector) VALUES (?, ?, ?) \
         ON CONFLICT(file_id) DO UPDATE SET model=excluded.model, vector=excluded.vector, \
         created_at=strftime('%s','now')",
    )
    .bind(file_id)
    .bind(model)
    .bind(blob)
    .execute(vectors_db)
    .await?;
    Ok(())
}

pub async fn save_vectors_batch(
    vectors_db: &SqlitePool,
    file_ids: &[i64],
    vectors: &[Vec<f32>],
    model: &str,
) -> Result<usize, VectorStoreError> {
    if file_ids.len() != vectors.len() {
        return Err(VectorStoreError::BatchLength {
            file_ids: file_ids.len(),
            vectors: vectors.len(),
        });
    }
    let mut transaction = vectors_db.begin().await?;
    for (file_id, vector) in file_ids.iter().zip(vectors) {
        sqlx::query(
            "INSERT INTO file_vectors (file_id, model, vector) VALUES (?, ?, ?) \
             ON CONFLICT(file_id) DO UPDATE SET model=excluded.model, vector=excluded.vector, \
             created_at=strftime('%s','now')",
        )
        .bind(file_id)
        .bind(model)
        .bind(encode_f16(vector))
        .execute(&mut *transaction)
        .await?;
    }
    transaction.commit().await?;
    Ok(file_ids.len())
}

pub async fn load_vector(
    vectors_db_read: &SqlitePool,
    file_id: i64,
) -> Result<Option<Vec<f32>>, VectorStoreError> {
    let row = sqlx::query("SELECT vector FROM file_vectors WHERE file_id = ?")
        .bind(file_id)
        .fetch_optional(vectors_db_read)
        .await?;
    row.map(|row| decode_f16(&row.get::<Vec<u8>, _>("vector")))
        .transpose()
}

/// Fetches one bounded page of stored vectors after `after_file_id`.
///
/// This is the only whole-store read primitive used by the usearch builder.
pub async fn load_vectors_cursor(
    vectors_db_read: &SqlitePool,
    model: &str,
    after_file_id: i64,
    limit: i64,
) -> Result<Vec<StoredVector>, VectorStoreError> {
    let rows = sqlx::query(
        "SELECT file_id, vector, created_at FROM file_vectors \
         WHERE model = ? AND file_id > ? ORDER BY file_id LIMIT ?",
    )
    .bind(model)
    .bind(after_file_id)
    .bind(limit.max(1))
    .fetch_all(vectors_db_read)
    .await?;
    rows.into_iter()
        .map(|row| {
            Ok(StoredVector {
                file_id: row.get("file_id"),
                vector: decode_f16(&row.get::<Vec<u8>, _>("vector"))?,
                created_at: row.get("created_at"),
            })
        })
        .collect()
}

pub async fn count_indexed(
    vectors_db_read: &SqlitePool,
    model: &str,
) -> Result<i64, VectorStoreError> {
    let row = sqlx::query("SELECT COUNT(*) AS count FROM file_vectors WHERE model = ?")
        .bind(model)
        .fetch_one(vectors_db_read)
        .await?;
    Ok(row.get("count"))
}

pub async fn count_unindexed(
    tags_db_read: &SqlitePool,
    vectors_db_read: &SqlitePool,
    model: &str,
) -> Result<i64, VectorStoreError> {
    let eligible: i64 = sqlx::query(
        "SELECT COUNT(*) AS count FROM clip_eligible_files c \
         JOIN files f ON f.id = c.file_id \
         WHERE f.is_deleted = 0 \
           AND lower(f.path) NOT LIKE '%.webm' \
           AND lower(f.path) NOT LIKE '%.mp4' \
           AND lower(f.path) NOT LIKE '%.avi' \
           AND lower(f.path) NOT LIKE '%.mov' \
           AND lower(f.path) NOT LIKE '%.mkv' \
           AND lower(f.path) NOT LIKE '%.m4v' \
           AND lower(f.path) NOT LIKE '%.ogv'",
    )
    .fetch_one(tags_db_read)
    .await?
    .get("count");
    Ok((eligible - count_indexed(vectors_db_read, model).await?).max(0))
}

pub async fn delete_vectors(
    vectors_db: &SqlitePool,
    file_ids: &[i64],
) -> Result<u64, VectorStoreError> {
    let mut deleted = 0;
    let unique_ids = dedupe_ids(file_ids);
    let mut transaction = vectors_db.begin().await?;
    for ids in unique_ids.chunks(IN_CHUNK_SIZE) {
        let (query, binds) = in_query("DELETE FROM file_vectors WHERE file_id IN", ids);
        let mut query = sqlx::query(&query);
        for file_id in binds {
            query = query.bind(file_id);
        }
        deleted += query.execute(&mut *transaction).await?.rows_affected();
    }
    transaction.commit().await?;
    Ok(deleted)
}

pub async fn delete_all_vectors(
    vectors_db: &SqlitePool,
    model: &str,
) -> Result<u64, VectorStoreError> {
    Ok(sqlx::query("DELETE FROM file_vectors WHERE model = ?")
        .bind(model)
        .execute(vectors_db)
        .await?
        .rows_affected())
}

/// Returns a single cursor page of eligible file IDs without vectors.
///
/// tags.db and vectors.db are separate SQLite files, so this deliberately
/// performs two bounded range queries rather than attempting a cross-DB join.
pub async fn get_unindexed_file_ids_cursor(
    tags_db_read: &SqlitePool,
    vectors_db_read: &SqlitePool,
    model: &str,
    after_id: i64,
    limit: i64,
) -> Result<Vec<i64>, VectorStoreError> {
    let limit = limit.max(1);
    let window = (limit * UNINDEXED_WINDOW_MULTIPLIER).max(MIN_UNINDEXED_WINDOW);
    let mut current_after_id = after_id;
    loop {
        let candidates: Vec<i64> = sqlx::query(
            "SELECT c.file_id FROM clip_eligible_files c \
             JOIN files f ON f.id = c.file_id \
             WHERE c.file_id > ? AND f.is_deleted = 0 \
               AND lower(f.path) NOT LIKE '%.webm' \
               AND lower(f.path) NOT LIKE '%.mp4' \
               AND lower(f.path) NOT LIKE '%.avi' \
               AND lower(f.path) NOT LIKE '%.mov' \
               AND lower(f.path) NOT LIKE '%.mkv' \
               AND lower(f.path) NOT LIKE '%.m4v' \
               AND lower(f.path) NOT LIKE '%.ogv' \
             ORDER BY c.file_id LIMIT ?",
        )
        .bind(current_after_id)
        .bind(window)
        .fetch_all(tags_db_read)
        .await?
        .into_iter()
        .map(|row| row.get("file_id"))
        .collect();
        let Some(&max_id) = candidates.last() else {
            return Ok(Vec::new());
        };

        let indexed: std::collections::HashSet<i64> = sqlx::query(
            "SELECT file_id FROM file_vectors \
             WHERE model = ? AND file_id > ? AND file_id <= ?",
        )
        .bind(model)
        .bind(current_after_id)
        .bind(max_id)
        .fetch_all(vectors_db_read)
        .await?
        .into_iter()
        .map(|row| row.get("file_id"))
        .collect();

        let result: Vec<i64> = candidates
            .into_iter()
            .filter(|file_id| !indexed.contains(file_id))
            .take(usize::try_from(limit).unwrap_or(1))
            .collect();
        if !result.is_empty() {
            return Ok(result);
        }
        current_after_id = max_id;
    }
}

pub async fn get_file_paths_by_ids(
    tags_db_read: &SqlitePool,
    file_ids: &[i64],
) -> Result<std::collections::HashMap<i64, String>, VectorStoreError> {
    let mut paths = std::collections::HashMap::new();
    for ids in dedupe_ids(file_ids).chunks(IN_CHUNK_SIZE) {
        // `AND is_deleted = 0` matches every Python original this helper's
        // callers port (video_audio lookups, s2t's file_id lookup) --
        // without it, a soft-deleted file's path is still handed to
        // whatever caller asked (captioning, CLIP indexing, transcription),
        // silently reading and re-annotating a file the rest of the app
        // treats as gone.
        let (query, binds) = in_query(
            "SELECT id, path FROM files WHERE is_deleted = 0 AND id IN",
            ids,
        );
        let mut query = sqlx::query(&query);
        for file_id in binds {
            query = query.bind(file_id);
        }
        for row in query.fetch_all(tags_db_read).await? {
            paths.insert(row.get("id"), row.get("path"));
        }
    }
    Ok(paths)
}

pub async fn vector_snapshot(
    vectors_db_read: &SqlitePool,
    model: &str,
) -> Result<(i64, i64), VectorStoreError> {
    let row = sqlx::query(
        "SELECT COUNT(*) AS count, COALESCE(MAX(created_at), 0) AS latest_created_at \
         FROM file_vectors WHERE model = ?",
    )
    .bind(model)
    .fetch_one(vectors_db_read)
    .await?;
    Ok((row.get("count"), row.get("latest_created_at")))
}

fn encode_f16(vector: &[f32]) -> Vec<u8> {
    vector
        .iter()
        .flat_map(|value| f16::from_f32(*value).to_bits().to_le_bytes())
        .collect()
}

fn decode_f16(blob: &[u8]) -> Result<Vec<f32>, VectorStoreError> {
    if !blob.len().is_multiple_of(2) {
        return Err(VectorStoreError::InvalidBlobLength(blob.len()));
    }
    Ok(blob
        .as_chunks::<2>()
        .0
        .iter()
        .map(|&bytes| f16::from_bits(u16::from_le_bytes(bytes)).to_f32())
        .collect())
}

fn dedupe_ids(file_ids: &[i64]) -> Vec<i64> {
    let mut seen = std::collections::HashSet::new();
    file_ids
        .iter()
        .copied()
        .filter(|file_id| seen.insert(*file_id))
        .collect()
}

fn in_query(prefix: &str, ids: &[i64]) -> (String, Vec<i64>) {
    let placeholders = std::iter::repeat_n("?", ids.len())
        .collect::<Vec<_>>()
        .join(",");
    (format!("{prefix} ({placeholders})"), ids.to_vec())
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;

    async fn pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE file_vectors (file_id INTEGER PRIMARY KEY, model TEXT NOT NULL, vector BLOB NOT NULL, created_at INTEGER NOT NULL DEFAULT 0);\
             CREATE TABLE clip_eligible_files (file_id INTEGER PRIMARY KEY);\
             CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL, is_deleted INTEGER NOT NULL DEFAULT 0);",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    #[tokio::test]
    async fn crud_round_trip_preserves_float16_storage() {
        let vectors = pool().await;
        save_vector(&vectors, 7, &[0.25, -1.5, 3.0], DEFAULT_MODEL)
            .await
            .unwrap();
        let loaded = load_vector(&vectors, 7).await.unwrap().unwrap();
        assert_eq!(loaded.len(), 3);
        assert!((loaded[0] - 0.25).abs() < 0.001);
        assert!((loaded[1] + 1.5).abs() < 0.001);

        assert_eq!(
            save_vectors_batch(
                &vectors,
                &[8, 9],
                &[vec![1.0, 0.0], vec![0.0, 1.0]],
                DEFAULT_MODEL,
            )
            .await
            .unwrap(),
            2
        );
        assert_eq!(count_indexed(&vectors, DEFAULT_MODEL).await.unwrap(), 3);
        assert_eq!(delete_vectors(&vectors, &[7, 7, 9]).await.unwrap(), 2);
        assert_eq!(
            delete_all_vectors(&vectors, DEFAULT_MODEL).await.unwrap(),
            1
        );
    }

    #[tokio::test]
    async fn get_file_paths_by_ids_excludes_soft_deleted_files() {
        let tags = pool().await;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (1, 'a.png', 0)")
            .execute(&tags)
            .await
            .unwrap();
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (2, 'b.png', 1)")
            .execute(&tags)
            .await
            .unwrap();
        let paths = get_file_paths_by_ids(&tags, &[1, 2]).await.unwrap();
        assert_eq!(paths.len(), 1);
        assert_eq!(paths.get(&1).map(String::as_str), Some("a.png"));
        assert!(!paths.contains_key(&2));
    }

    #[tokio::test]
    async fn cursor_skips_full_indexed_windows_and_keeps_boundaries() {
        let tags = pool().await;
        let vectors = pool().await;
        for id in 1..=4_001 {
            sqlx::query("INSERT INTO clip_eligible_files(file_id) VALUES (?)")
                .bind(id)
                .execute(&tags)
                .await
                .unwrap();
            sqlx::query("INSERT INTO files(id, path) VALUES (?, ?)")
                .bind(id)
                .bind(format!("{id}.png"))
                .execute(&tags)
                .await
                .unwrap();
        }
        let indexed_ids: Vec<i64> = (1..=4_000).collect();
        let indexed_vectors = indexed_ids.iter().map(|_| vec![1.0]).collect::<Vec<_>>();
        save_vectors_batch(&vectors, &indexed_ids, &indexed_vectors, DEFAULT_MODEL)
            .await
            .unwrap();

        assert_eq!(
            get_unindexed_file_ids_cursor(&tags, &vectors, DEFAULT_MODEL, 0, 1)
                .await
                .unwrap(),
            vec![4_001]
        );
        assert!(
            get_unindexed_file_ids_cursor(&tags, &vectors, DEFAULT_MODEL, 4_001, 10)
                .await
                .unwrap()
                .is_empty()
        );
    }

    #[tokio::test]
    async fn cursor_and_count_exclude_videos() {
        let tags = pool().await;
        let vectors = pool().await;
        for (id, path) in [(1, "still.png"), (2, "movie.MP4"), (3, "also.jpg")] {
            sqlx::query("INSERT INTO clip_eligible_files(file_id) VALUES (?)")
                .bind(id)
                .execute(&tags)
                .await
                .unwrap();
            sqlx::query("INSERT INTO files(id, path) VALUES (?, ?)")
                .bind(id)
                .bind(path)
                .execute(&tags)
                .await
                .unwrap();
        }
        assert_eq!(
            count_unindexed(&tags, &vectors, DEFAULT_MODEL)
                .await
                .unwrap(),
            2
        );
        assert_eq!(
            get_unindexed_file_ids_cursor(&tags, &vectors, DEFAULT_MODEL, 0, 10)
                .await
                .unwrap(),
            vec![1, 3]
        );
    }
}
