use crate::TagdbError;
use sqlx::SqlitePool;

/// Select-first tag upsert matching Python models_tags.py behavior.
pub async fn upsert_tag(
    pool: &SqlitePool,
    namespace: Option<&str>,
    tag: &str,
    first_seen_mtime: Option<i64>,
) -> Result<i64, TagdbError> {
    let existing: Option<(i64, Option<i64>)> =
        sqlx::query_as("SELECT id, first_seen_mtime FROM tags WHERE tag = ? AND namespace IS ?")
            .bind(tag)
            .bind(namespace)
            .fetch_optional(pool)
            .await?;

    if let Some((tag_id, existing_mtime)) = existing {
        if let Some(new_mtime) = first_seen_mtime {
            if existing_mtime.is_none_or(|em| new_mtime < em) {
                sqlx::query(
                    "UPDATE tags SET first_seen_mtime = ?
                     WHERE id = ? AND (first_seen_mtime IS NULL OR first_seen_mtime > ?)",
                )
                .bind(new_mtime)
                .bind(tag_id)
                .bind(new_mtime)
                .execute(pool)
                .await?;
            }
        }
        return Ok(tag_id);
    }

    let res = sqlx::query("INSERT INTO tags(tag, namespace, first_seen_mtime) VALUES(?,?,?)")
        .bind(tag)
        .bind(namespace)
        .bind(first_seen_mtime)
        .execute(pool)
        .await?;
    Ok(res.last_insert_rowid())
}

/// Insert or update a meta source file tag weight.
pub async fn insert_file_tag(
    pool: &SqlitePool,
    file_id: i64,
    tag_id: i64,
    weight: f64,
) -> Result<(), TagdbError> {
    // file_tags' real UNIQUE constraint is (file_id, tag_id) only (no source
    // column) — ON CONFLICT(file_id, tag_id, source) does not match any
    // constraint and errors at runtime once a conflicting row exists.
    sqlx::query(
        "INSERT INTO file_tags(file_id, tag_id, weight) VALUES(?,?,?)
         ON CONFLICT(file_id, tag_id) DO UPDATE SET weight = excluded.weight",
    )
    .bind(file_id)
    .bind(tag_id)
    .bind(weight)
    .execute(pool)
    .await?;
    Ok(())
}

/// Clear tags for a file from one source without touching other sources.
pub async fn clear_tags_for_file(
    pool: &SqlitePool,
    file_id: i64,
    source: &str,
) -> Result<(), TagdbError> {
    sqlx::query("DELETE FROM file_tags WHERE file_id = ? AND source = ?")
        .bind(file_id)
        .bind(source)
        .execute(pool)
        .await?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;
    use tempfile::NamedTempFile;

    async fn pool_with_tag_tables() -> (NamedTempFile, SqlitePool) {
        let f = NamedTempFile::new().unwrap();
        let path = format!("sqlite://{}", f.path().display());
        let opts = SqliteConnectOptions::from_str(&path)
            .unwrap()
            .create_if_missing(true);
        let pool = SqlitePoolOptions::new().connect_with(opts).await.unwrap();
        sqlx::raw_sql(
            "CREATE TABLE tags(
                id INTEGER PRIMARY KEY,
                tag TEXT NOT NULL,
                namespace TEXT,
                first_seen_mtime INTEGER,
                UNIQUE(tag, namespace)
             );
             CREATE TABLE files(
                id INTEGER PRIMARY KEY,
                path TEXT NOT NULL UNIQUE,
                mtime INTEGER NOT NULL,
                size INTEGER NOT NULL
             );
             CREATE TABLE file_tags(
                file_id INTEGER NOT NULL,
                tag_id INTEGER NOT NULL,
                weight REAL NOT NULL DEFAULT 1.0,
                source TEXT NOT NULL DEFAULT 'meta',
                UNIQUE(file_id, tag_id),
                FOREIGN KEY(file_id) REFERENCES files(id) ON DELETE CASCADE,
                FOREIGN KEY(tag_id) REFERENCES tags(id) ON DELETE CASCADE
             );",
        )
        .execute(&pool)
        .await
        .unwrap();
        (f, pool)
    }

    #[tokio::test]
    async fn test_upsert_tag_idempotent() {
        let (_f, pool) = pool_with_tag_tables().await;
        let id1 = upsert_tag(&pool, None, "solo", None).await.unwrap();
        let id2 = upsert_tag(&pool, None, "solo", None).await.unwrap();
        assert_eq!(id1, id2);
    }

    #[tokio::test]
    async fn test_updates_smaller_mtime() {
        let (_f, pool) = pool_with_tag_tables().await;
        upsert_tag(&pool, None, "tag_a", Some(2000)).await.unwrap();
        upsert_tag(&pool, None, "tag_a", Some(1000)).await.unwrap();
        let mtime: Option<i64> =
            sqlx::query_scalar("SELECT first_seen_mtime FROM tags WHERE tag='tag_a'")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(mtime, Some(1000));
    }

    #[tokio::test]
    async fn test_does_not_update_larger_mtime() {
        let (_f, pool) = pool_with_tag_tables().await;
        upsert_tag(&pool, None, "tag_b", Some(500)).await.unwrap();
        upsert_tag(&pool, None, "tag_b", Some(9999)).await.unwrap();
        let mtime: Option<i64> =
            sqlx::query_scalar("SELECT first_seen_mtime FROM tags WHERE tag='tag_b'")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(mtime, Some(500));
    }

    #[tokio::test]
    async fn clear_tags_for_file_only_removes_specified_source() {
        let (_f, pool) = pool_with_tag_tables().await;
        sqlx::raw_sql("INSERT INTO files(id,path,mtime,size) VALUES(1,'/a.png',0,0)")
            .execute(&pool)
            .await
            .unwrap();
        let meta_tag = upsert_tag(&pool, None, "meta_tag", None).await.unwrap();
        let wd_tag = upsert_tag(&pool, None, "wd_tag", None).await.unwrap();
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, ?, 1.0, 'meta')",
        )
        .bind(meta_tag)
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, ?, 1.0, 'wd14')",
        )
        .bind(wd_tag)
        .execute(&pool)
        .await
        .unwrap();

        clear_tags_for_file(&pool, 1, "meta").await.unwrap();

        let remaining: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM file_tags WHERE file_id=1")
            .fetch_one(&pool)
            .await
            .unwrap();
        let wd_remaining: i64 =
            sqlx::query_scalar("SELECT COUNT(*) FROM file_tags WHERE file_id=1 AND source='wd14'")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(remaining, 1);
        assert_eq!(wd_remaining, 1);
    }

    #[tokio::test]
    async fn test_insert_file_tag_updates_weight() {
        let (_f, pool) = pool_with_tag_tables().await;
        sqlx::raw_sql("INSERT INTO files(id,path,mtime,size) VALUES(1,'/a.png',0,0)")
            .execute(&pool)
            .await
            .unwrap();
        let tag_id = upsert_tag(&pool, None, "1girl", None).await.unwrap();
        insert_file_tag(&pool, 1, tag_id, 0.5).await.unwrap();
        insert_file_tag(&pool, 1, tag_id, 0.9).await.unwrap();
        let weight: f64 =
            sqlx::query_scalar("SELECT weight FROM file_tags WHERE file_id=1 AND tag_id=?")
                .bind(tag_id)
                .fetch_one(&pool)
                .await
                .unwrap();
        assert!((weight - 0.9).abs() < 1e-9);
    }
}
