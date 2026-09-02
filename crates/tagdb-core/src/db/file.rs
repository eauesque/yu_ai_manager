use crate::{TagdbError, CURRENT_PARSER_VERSION};
use sqlx::SqlitePool;

#[derive(Debug, sqlx::FromRow)]
pub struct FileRow {
    pub id: i64,
    pub mtime: i64,
    pub size: i64,
    pub is_deleted: i64,
    pub hash: Option<String>,
    pub parser_version: i64,
}

pub struct UpsertFileParams<'a> {
    pub path: &'a str,
    pub mtime: i64,
    pub size: i64,
    pub meta_source: Option<&'a str>,
    pub content_hash: Option<&'a str>,
    pub is_zip_member: bool,
    pub width: Option<i64>,
    pub height: Option<i64>,
}

pub async fn get_file_row(pool: &SqlitePool, path: &str) -> Result<Option<FileRow>, TagdbError> {
    let row: Option<FileRow> = sqlx::query_as(
        "SELECT id, mtime, size, is_deleted, hash,
                COALESCE(parser_version, 1) AS parser_version
         FROM files WHERE path = ?",
    )
    .bind(path)
    .fetch_optional(pool)
    .await?;
    Ok(row)
}

/// Inserts or updates a file record.
///
/// The sole production caller, the watcher, does not parse files and always passes
/// `meta_source: None`; overwriting it would discard existing analysis results. This
/// matches Python's BUG-58 fix in `scanner_regular.py`. A `Some` value still updates
/// the source, but `None` therefore cannot be used to deliberately clear it.
pub async fn upsert_file(pool: &SqlitePool, p: UpsertFileParams<'_>) -> Result<i64, TagdbError> {
    let is_zip = p.is_zip_member as i64;
    let row: (i64,) = sqlx::query_as(
        "INSERT INTO files(path, mtime, size, hash, meta_source, is_deleted,
                           is_zip_member, parser_version, width, height)
         VALUES(?,?,?,?,?,0,?,?,?,?)
         ON CONFLICT(path) DO UPDATE SET
           mtime          = excluded.mtime,
           size           = excluded.size,
           hash           = COALESCE(excluded.hash, files.hash),
           meta_source    = COALESCE(excluded.meta_source, files.meta_source),
           is_deleted     = 0,
           is_zip_member  = excluded.is_zip_member,
           parser_version = excluded.parser_version,
           width          = COALESCE(excluded.width, files.width),
           height         = COALESCE(excluded.height, files.height)
         RETURNING id",
    )
    .bind(p.path)
    .bind(p.mtime)
    .bind(p.size)
    .bind(p.content_hash)
    .bind(p.meta_source)
    .bind(is_zip)
    .bind(CURRENT_PARSER_VERSION)
    .bind(p.width)
    .bind(p.height)
    .fetch_one(pool)
    .await?;
    Ok(row.0)
}

pub async fn mark_deleted(pool: &SqlitePool, path: &str) -> Result<bool, TagdbError> {
    let rows = sqlx::query("UPDATE files SET is_deleted = 1 WHERE path = ? AND is_deleted = 0")
        .bind(path)
        .execute(pool)
        .await?
        .rows_affected();
    Ok(rows > 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;
    use tempfile::NamedTempFile;

    async fn pool_with_files_table() -> (NamedTempFile, SqlitePool) {
        let f = NamedTempFile::new().unwrap();
        let path = format!("sqlite:{}", f.path().display());
        let opts = SqliteConnectOptions::from_str(&path)
            .unwrap()
            .create_if_missing(true);
        let pool = SqlitePoolOptions::new().connect_with(opts).await.unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL UNIQUE,
               mtime INTEGER NOT NULL,
               size INTEGER NOT NULL,
               hash TEXT,
               phash TEXT,
               is_deleted INTEGER NOT NULL DEFAULT 0,
               meta_source TEXT,
               not_modified INTEGER NOT NULL DEFAULT 0,
               parser_version INTEGER NOT NULL DEFAULT 1,
               is_zip_member INTEGER NOT NULL DEFAULT 0,
               extracted_from_zip TEXT,
               extracted_from_internal TEXT,
               extraction_date INTEGER,
               extracted_to_file_id INTEGER,
               width INTEGER,
               height INTEGER,
               imported_from_peer TEXT,
               has_sweep INTEGER NOT NULL DEFAULT 0
             )",
        )
        .execute(&pool)
        .await
        .unwrap();
        (f, pool)
    }

    fn params(path: &str) -> UpsertFileParams<'_> {
        UpsertFileParams {
            path,
            mtime: 1000,
            size: 512,
            meta_source: None,
            content_hash: None,
            is_zip_member: false,
            width: None,
            height: None,
        }
    }

    #[tokio::test]
    async fn test_insert_returns_id() {
        let (_f, pool) = pool_with_files_table().await;
        let id = upsert_file(&pool, params("/img/a.png")).await.unwrap();
        assert!(id > 0);
    }

    #[tokio::test]
    async fn test_upsert_same_id() {
        let (_f, pool) = pool_with_files_table().await;
        let id1 = upsert_file(&pool, params("/img/a.png")).await.unwrap();
        let id2 = upsert_file(
            &pool,
            UpsertFileParams {
                mtime: 2000,
                ..params("/img/a.png")
            },
        )
        .await
        .unwrap();
        assert_eq!(id1, id2);
    }

    #[tokio::test]
    async fn test_get_file_row_found() {
        let (_f, pool) = pool_with_files_table().await;
        upsert_file(
            &pool,
            UpsertFileParams {
                content_hash: Some("deadbeef"),
                mtime: 9000,
                ..params("/img/b.png")
            },
        )
        .await
        .unwrap();
        let row = get_file_row(&pool, "/img/b.png").await.unwrap().unwrap();
        assert_eq!(row.mtime, 9000);
        assert_eq!(row.hash.as_deref(), Some("deadbeef"));
        assert_eq!(row.is_deleted, 0);
    }

    #[tokio::test]
    async fn test_get_file_row_missing() {
        let (_f, pool) = pool_with_files_table().await;
        let row = get_file_row(&pool, "/nonexistent.png").await.unwrap();
        assert!(row.is_none());
    }

    #[tokio::test]
    async fn test_upsert_preserves_existing_hash_when_null() {
        let (_f, pool) = pool_with_files_table().await;
        upsert_file(
            &pool,
            UpsertFileParams {
                content_hash: Some("abc"),
                ..params("/img/c.png")
            },
        )
        .await
        .unwrap();
        upsert_file(
            &pool,
            UpsertFileParams {
                content_hash: None,
                mtime: 2000,
                ..params("/img/c.png")
            },
        )
        .await
        .unwrap();
        let row = get_file_row(&pool, "/img/c.png").await.unwrap().unwrap();
        assert_eq!(row.hash.as_deref(), Some("abc"));
    }

    #[tokio::test]
    async fn test_upsert_preserves_existing_meta_source_when_null_and_updates_non_null_value() {
        let (_f, pool) = pool_with_files_table().await;
        upsert_file(
            &pool,
            UpsertFileParams {
                meta_source: Some("novelai"),
                ..params("/img/meta.png")
            },
        )
        .await
        .unwrap();
        sqlx::query("UPDATE files SET parser_version = 0 WHERE path = ?")
            .bind("/img/meta.png")
            .execute(&pool)
            .await
            .unwrap();

        upsert_file(
            &pool,
            UpsertFileParams {
                mtime: 2000,
                size: 1024,
                meta_source: None,
                ..params("/img/meta.png")
            },
        )
        .await
        .unwrap();
        let row: (Option<String>, i64, i64, i64) = sqlx::query_as(
            "SELECT meta_source, mtime, size, parser_version FROM files WHERE path = ?",
        )
        .bind("/img/meta.png")
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(
            row,
            (
                Some("novelai".into()),
                2000,
                1024,
                CURRENT_PARSER_VERSION as i64,
            )
        );

        upsert_file(
            &pool,
            UpsertFileParams {
                meta_source: Some("stable-diffusion"),
                ..params("/img/meta.png")
            },
        )
        .await
        .unwrap();
        let meta_source: (Option<String>,) =
            sqlx::query_as("SELECT meta_source FROM files WHERE path = ?")
                .bind("/img/meta.png")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(meta_source.0.as_deref(), Some("stable-diffusion"));
    }
}
