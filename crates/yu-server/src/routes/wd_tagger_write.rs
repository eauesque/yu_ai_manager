use sqlx::SqlitePool;

use crate::routes::tag_reads::delete_wd_tags_for_files_tx;
use crate::routes::wd_tagger::ACTIVE_MODEL_KEY;
use crate::routes::wd_tagger_normalize::{
    confidence_to_milli, normalize_tag_name, normalize_tag_name_canonical,
};

/// WD-Taggerの推論結果をDBへ書込む。単一トランザクションで
/// DELETE→辞書resolve-or-insert→INSERTを行い、実挿入タグ数を返す。
/// DELETEとINSERTは同一トランザクション内でcommitされるため、
/// 途中でプロセスが落ちても旧タグが消えたまま新タグが未書込という
/// 中間状態は発生しない(rollbackされる)。
/// `wd_tag_stats_cache`には触れない(Python版単発tagエンドポイントとのパリティ、
/// 仕様書「Phase2」参照)。
pub(crate) async fn write_wd_tags(
    pool: &SqlitePool,
    file_id: i64,
    model: &str,
    tags: &[(String, f64, String)],
) -> Result<i64, sqlx::Error> {
    let mut tx = pool.begin().await?;

    delete_wd_tags_for_files_tx(&mut tx, &[file_id], Some(model)).await?;

    let model_id: i64 = {
        sqlx::query("INSERT OR IGNORE INTO wd_model_dict(model) VALUES(?)")
            .bind(model)
            .execute(&mut *tx)
            .await?;
        sqlx::query_scalar("SELECT id FROM wd_model_dict WHERE model = ?")
            .bind(model)
            .fetch_one(&mut *tx)
            .await?
    };

    let mut inserted: i64 = 0;
    for (raw_tag, confidence, category) in tags {
        let tag_name = normalize_tag_name(raw_tag);
        if tag_name.is_empty() {
            continue;
        }
        let tag_name_normalized = normalize_tag_name_canonical(&tag_name);

        sqlx::query(
            "INSERT OR IGNORE INTO wd_tag_dict(tag_name, tag_name_normalized) VALUES(?, ?)",
        )
        .bind(&tag_name)
        .bind(&tag_name_normalized)
        .execute(&mut *tx)
        .await?;
        let tag_id: i64 = sqlx::query_scalar("SELECT id FROM wd_tag_dict WHERE tag_name = ?")
            .bind(&tag_name)
            .fetch_one(&mut *tx)
            .await?;

        sqlx::query("INSERT OR IGNORE INTO wd_category_dict(category) VALUES(?)")
            .bind(category)
            .execute(&mut *tx)
            .await?;
        let category_id: i64 =
            sqlx::query_scalar("SELECT id FROM wd_category_dict WHERE category = ?")
                .bind(category)
                .fetch_one(&mut *tx)
                .await?;

        let confidence_milli = confidence_to_milli(*confidence);

        let result = sqlx::query(
            "INSERT OR IGNORE INTO file_wd_tags
                (file_id, tag_id, confidence_milli, category_id, model_id)
             VALUES (?, ?, ?, ?, ?)",
        )
        .bind(file_id)
        .bind(tag_id)
        .bind(confidence_milli)
        .bind(category_id)
        .bind(model_id)
        .execute(&mut *tx)
        .await?;
        inserted += result.rows_affected() as i64;
    }

    tx.commit().await?;
    Ok(inserted)
}

/// Retag-specific write semantics: optional same-model replacement, active
/// model update, and stats-cache invalidation are one transaction.
pub(crate) async fn write_wd_tags_for_retag(
    pool: &SqlitePool,
    file_id: i64,
    model: &str,
    tags: &[(String, f64, String)],
    overwrite: bool,
    set_active_to: Option<&str>,
) -> Result<i64, sqlx::Error> {
    let mut tx = pool.begin().await?;
    if overwrite {
        delete_wd_tags_for_files_tx(&mut tx, &[file_id], Some(model)).await?;
    }
    let model_id: i64 = {
        sqlx::query("INSERT OR IGNORE INTO wd_model_dict(model) VALUES(?)")
            .bind(model)
            .execute(&mut *tx)
            .await?;
        sqlx::query_scalar("SELECT id FROM wd_model_dict WHERE model = ?")
            .bind(model)
            .fetch_one(&mut *tx)
            .await?
    };
    let mut inserted = 0;
    for (raw_tag, confidence, category) in tags {
        let tag_name = normalize_tag_name(raw_tag);
        if tag_name.is_empty() {
            continue;
        }
        let normalized = normalize_tag_name_canonical(&tag_name);
        sqlx::query(
            "INSERT OR IGNORE INTO wd_tag_dict(tag_name, tag_name_normalized) VALUES(?, ?)",
        )
        .bind(&tag_name)
        .bind(&normalized)
        .execute(&mut *tx)
        .await?;
        let tag_id: i64 = sqlx::query_scalar("SELECT id FROM wd_tag_dict WHERE tag_name = ?")
            .bind(&tag_name)
            .fetch_one(&mut *tx)
            .await?;
        sqlx::query("INSERT OR IGNORE INTO wd_category_dict(category) VALUES(?)")
            .bind(category)
            .execute(&mut *tx)
            .await?;
        let category_id: i64 =
            sqlx::query_scalar("SELECT id FROM wd_category_dict WHERE category = ?")
                .bind(category)
                .fetch_one(&mut *tx)
                .await?;
        inserted += sqlx::query("INSERT OR IGNORE INTO file_wd_tags (file_id, tag_id, confidence_milli, category_id, model_id) VALUES (?, ?, ?, ?, ?)")
            .bind(file_id).bind(tag_id).bind(confidence_to_milli(*confidence)).bind(category_id).bind(model_id)
            .execute(&mut *tx).await?.rows_affected() as i64;
    }
    if let Some(model) = set_active_to {
        sqlx::query("INSERT INTO kv_state (key, value, updated_at) VALUES (?, ?, strftime('%s','now')) ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = excluded.updated_at")
            .bind(ACTIVE_MODEL_KEY).bind(model).execute(&mut *tx).await?;
    }
    sqlx::query("DELETE FROM wd_tag_stats_cache WHERE id = 1")
        .execute(&mut *tx)
        .await?;
    tx.commit().await?;
    Ok(inserted)
}

#[cfg(test)]
mod tests {
    use super::*;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;

    async fn test_pool() -> SqlitePool {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::query(
            "CREATE TABLE files (id INTEGER PRIMARY KEY, is_deleted INTEGER NOT NULL DEFAULT 0);
             CREATE TABLE wd_tag_dict (id INTEGER PRIMARY KEY, tag_name TEXT NOT NULL UNIQUE, tag_name_normalized TEXT NOT NULL);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL UNIQUE);
             CREATE TABLE wd_category_dict (id INTEGER PRIMARY KEY, category TEXT NOT NULL UNIQUE);
              CREATE TABLE file_wd_tags (
                 id INTEGER PRIMARY KEY,
                 file_id INTEGER NOT NULL REFERENCES files(id) ON DELETE CASCADE,
                 tag_id INTEGER NOT NULL REFERENCES wd_tag_dict(id),
                 confidence_milli INTEGER NOT NULL CHECK(confidence_milli BETWEEN 0 AND 1000),
                 category_id INTEGER NOT NULL REFERENCES wd_category_dict(id),
                 model_id INTEGER NOT NULL REFERENCES wd_model_dict(id),
                 created_at INTEGER NOT NULL DEFAULT (strftime('%s','now')),
                  UNIQUE(file_id, tag_id, model_id)
              );
              CREATE TABLE kv_state (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER);
              CREATE TABLE wd_tag_stats_cache (id INTEGER PRIMARY KEY, stats_json TEXT, computed_at INTEGER);",
        )
        .execute(&pool)
        .await
        .unwrap();
        sqlx::query("INSERT INTO files (id, is_deleted) VALUES (1, 0)")
            .execute(&pool)
            .await
            .unwrap();
        pool
    }

    #[tokio::test]
    async fn write_wd_tags_inserts_rows_and_resolves_dictionaries() {
        let pool = test_pool().await;
        let tags = vec![
            ("Blue Eyes".to_string(), 0.9123, "general".to_string()),
            ("Smile".to_string(), 0.75, "general".to_string()),
        ];
        let count = write_wd_tags(&pool, 1, "wd-swinv2", &tags).await.unwrap();
        assert_eq!(count, 2);

        let tag_name: String =
            sqlx::query_scalar("SELECT tag_name FROM wd_tag_dict WHERE tag_name = 'blue_eyes'")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(tag_name, "blue_eyes");

        let normalized: String = sqlx::query_scalar(
            "SELECT tag_name_normalized FROM wd_tag_dict WHERE tag_name = 'blue_eyes'",
        )
        .fetch_one(&pool)
        .await
        .unwrap();
        assert_eq!(normalized, "blue eyes");
    }

    #[tokio::test]
    async fn write_wd_tags_replaces_existing_tags_for_same_model() {
        let pool = test_pool().await;
        write_wd_tags(
            &pool,
            1,
            "wd-swinv2",
            &[("Old".to_string(), 0.5, "general".to_string())],
        )
        .await
        .unwrap();
        write_wd_tags(
            &pool,
            1,
            "wd-swinv2",
            &[("New".to_string(), 0.5, "general".to_string())],
        )
        .await
        .unwrap();

        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM file_wd_tags WHERE file_id = 1")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(count, 1, "old tag must be replaced, not accumulated");
    }

    #[tokio::test]
    async fn delete_wd_tags_for_files_tx_rolls_back_without_commit() {
        // Verifies the property write_wd_tags now relies on for atomicity:
        // delete_wd_tags_for_files_tx does NOT commit on its own. If the
        // caller's transaction is dropped (e.g. process crash) before
        // tx.commit() runs, the DELETE never takes effect -- so a crash
        // between delete and insert cannot leave old tags gone with no
        // new tags written.
        let pool = test_pool().await;
        write_wd_tags(
            &pool,
            1,
            "wd-swinv2",
            &[("Old".to_string(), 0.5, "general".to_string())],
        )
        .await
        .unwrap();

        {
            let mut tx = pool.begin().await.unwrap();
            delete_wd_tags_for_files_tx(&mut tx, &[1], Some("wd-swinv2"))
                .await
                .unwrap();
            // tx dropped here without calling commit() -> implicit rollback.
        }

        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM file_wd_tags WHERE file_id = 1")
            .fetch_one(&pool)
            .await
            .unwrap();
        assert_eq!(
            count, 1,
            "delete inside an uncommitted transaction must not persist"
        );
    }

    #[tokio::test]
    async fn write_wd_tags_does_not_touch_wd_tag_stats_cache() {
        let pool = test_pool().await;
        sqlx::query("INSERT INTO wd_tag_stats_cache (id, stats_json, computed_at) VALUES (1, '{\"total\":5}', 123)")
            .execute(&pool)
            .await
            .unwrap();

        write_wd_tags(
            &pool,
            1,
            "wd-swinv2",
            &[("Tag".to_string(), 0.5, "general".to_string())],
        )
        .await
        .unwrap();

        let stats_json: String =
            sqlx::query_scalar("SELECT stats_json FROM wd_tag_stats_cache WHERE id = 1")
                .fetch_one(&pool)
                .await
                .unwrap();
        assert_eq!(
            stats_json, "{\"total\":5}",
            "wd_tag_stats_cache must remain untouched"
        );
    }

    #[tokio::test]
    async fn retag_without_overwrite_keeps_confidence_adds_tags_and_sets_active() {
        let pool = test_pool().await;
        write_wd_tags(
            &pool,
            1,
            "wd-swinv2",
            &[("Old".into(), 0.5, "general".into())],
        )
        .await
        .unwrap();
        sqlx::query(
            "INSERT INTO wd_tag_stats_cache (id, stats_json, computed_at) VALUES (1, '{}', 1)",
        )
        .execute(&pool)
        .await
        .unwrap();
        assert_eq!(
            write_wd_tags_for_retag(
                &pool,
                1,
                "wd-swinv2",
                &[
                    ("Old".into(), 0.9, "general".into()),
                    ("New".into(), 0.7, "general".into())
                ],
                false,
                Some("wd-swinv2")
            )
            .await
            .unwrap(),
            1
        );
        let old_confidence: i64 = sqlx::query_scalar("SELECT confidence_milli FROM file_wd_tags JOIN wd_tag_dict ON wd_tag_dict.id = file_wd_tags.tag_id WHERE tag_name = 'old'")
            .fetch_one(&pool).await.unwrap();
        assert_eq!(old_confidence, 500);
        assert_eq!(
            sqlx::query_scalar::<_, String>("SELECT value FROM kv_state WHERE key = ?")
                .bind(ACTIVE_MODEL_KEY)
                .fetch_one(&pool)
                .await
                .unwrap(),
            "wd-swinv2"
        );
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM wd_tag_stats_cache")
                .fetch_one(&pool)
                .await
                .unwrap(),
            0
        );
    }

    #[tokio::test]
    async fn retag_failure_rolls_back_active_model_update() {
        let pool = test_pool().await;
        sqlx::query("DROP TABLE wd_tag_stats_cache")
            .execute(&pool)
            .await
            .unwrap();
        assert!(write_wd_tags_for_retag(
            &pool,
            1,
            "new-model",
            &[("Tag".into(), 0.5, "general".into())],
            true,
            Some("new-model")
        )
        .await
        .is_err());
        assert_eq!(
            sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM kv_state WHERE key = ?")
                .bind(ACTIVE_MODEL_KEY)
                .fetch_one(&pool)
                .await
                .unwrap(),
            0
        );
    }
}
