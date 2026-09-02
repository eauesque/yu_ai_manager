use crate::db::CURRENT_PARSER_VERSION;
use crate::TagdbError;
use sqlx::SqliteConnection;

pub const PARSER_VERSION_SENTINEL: i64 = 0;

pub fn should_rescan(
    old_mtime: i64,
    old_size: i64,
    old_parser_version: i64,
    new_mtime: i64,
    new_size: i64,
    force: bool,
) -> bool {
    force
        || old_mtime != new_mtime
        || old_size != new_size
        || old_parser_version == PARSER_VERSION_SENTINEL
        || old_parser_version < i64::from(CURRENT_PARSER_VERSION)
}

pub async fn needs_template_repair(
    conn: &mut SqliteConnection,
    file_id: i64,
) -> Result<bool, TagdbError> {
    let has_meta_tag: i64 = sqlx::query_scalar(
        "SELECT EXISTS(SELECT 1 FROM file_tags WHERE file_id = ? AND source = 'meta' LIMIT 1)",
    )
    .bind(file_id)
    .fetch_one(&mut *conn)
    .await?;

    if has_meta_tag == 0 {
        return Ok(false);
    }

    let has_template: i64 =
        sqlx::query_scalar("SELECT EXISTS(SELECT 1 FROM templates WHERE file_id = ? LIMIT 1)")
            .bind(file_id)
            .fetch_one(&mut *conn)
            .await?;

    Ok(has_template == 0)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;
    use tempfile::NamedTempFile;

    async fn pool_with_partial_import_tables() -> (NamedTempFile, sqlx::SqlitePool) {
        let f = NamedTempFile::new().unwrap();
        let path = format!("sqlite:{}", f.path().display());
        let opts = SqliteConnectOptions::from_str(&path)
            .unwrap()
            .create_if_missing(true);
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(opts)
            .await
            .unwrap();

        sqlx::raw_sql(
            "
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
                source TEXT NOT NULL DEFAULT 'meta'
            );
            CREATE TABLE templates(
                id INTEGER PRIMARY KEY,
                file_id INTEGER NOT NULL UNIQUE,
                raw_prompt TEXT
            );
            INSERT INTO files(id, path, mtime, size) VALUES(1, '/a.png', 0, 0);
            ",
        )
        .execute(&pool)
        .await
        .unwrap();

        (f, pool)
    }

    #[test]
    fn should_rescan_true_when_mtime_changed() {
        assert!(should_rescan(1000, 500, 6, 2000, 500, false));
    }

    #[test]
    fn should_rescan_true_when_parser_version_below_current() {
        assert!(should_rescan(
            1000,
            500,
            PARSER_VERSION_SENTINEL,
            1000,
            500,
            false
        ));
    }

    #[test]
    fn should_rescan_false_when_unchanged_and_current() {
        assert!(!should_rescan(1000, 500, 6, 1000, 500, false));
    }

    #[test]
    fn should_rescan_always_true_when_forced() {
        assert!(should_rescan(1000, 500, 6, 1000, 500, true));
    }

    #[tokio::test]
    async fn needs_template_repair_true_when_meta_tags_without_template() {
        let (_f, pool) = pool_with_partial_import_tables().await;
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, 10, 1.0, 'meta')",
        )
        .execute(&pool)
        .await
        .unwrap();

        let mut conn = pool.acquire().await.unwrap();
        assert!(needs_template_repair(&mut conn, 1).await.unwrap());
    }

    #[tokio::test]
    async fn needs_template_repair_false_when_template_exists() {
        let (_f, pool) = pool_with_partial_import_tables().await;
        sqlx::raw_sql(
            "
            INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, 10, 1.0, 'meta');
            INSERT INTO templates(file_id, raw_prompt) VALUES(1, 'cat');
            ",
        )
        .execute(&pool)
        .await
        .unwrap();

        let mut conn = pool.acquire().await.unwrap();
        assert!(!needs_template_repair(&mut conn, 1).await.unwrap());
    }

    #[tokio::test]
    async fn needs_template_repair_false_without_meta_tags() {
        let (_f, pool) = pool_with_partial_import_tables().await;
        sqlx::query(
            "INSERT INTO file_tags(file_id, tag_id, weight, source) VALUES(1, 10, 1.0, 'wd14')",
        )
        .execute(&pool)
        .await
        .unwrap();

        let mut conn = pool.acquire().await.unwrap();
        assert!(!needs_template_repair(&mut conn, 1).await.unwrap());
    }
}
