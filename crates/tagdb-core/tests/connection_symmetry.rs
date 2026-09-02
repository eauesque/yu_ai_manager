//! The encrypted and plaintext connection paths must stay behaviourally equal.
//!
//! `connect` (db/mod.rs) spells out journal_mode / synchronous / foreign_keys;
//! `connect_encrypted` (lib.rs) spells out none of them. That asymmetry in the
//! *source* was read, more than once, as an asymmetry in *behaviour* -- the
//! claim being that encrypted connections run with foreign keys off, so
//! ON DELETE CASCADE (24 of them in the schema) would silently leave orphans.
//!
//! Measured, that is false: both paths report foreign_keys=1, and CASCADE works
//! on the encrypted connection. The only real difference is `synchronous`
//! (encrypted FULL, plaintext NORMAL), which is the more durable setting, not a
//! defect.
//!
//! These tests exist so the next reader does not have to re-derive that, and so
//! that if a future sqlx version stops enabling foreign keys by default, the
//! encrypted path fails here rather than silently dropping referential
//! integrity in production. Both deployment paths that matter --
//! `deploy/yu-server.service` and the desktop launcher -- pass `--db-key` and
//! therefore run on the encrypted path.

use sqlx::SqlitePool;
use std::str::FromStr;
use tempfile::TempDir;

const KEY: &str = "test-only-connection-symmetry-key";

async fn foreign_keys_on(pool: &SqlitePool) -> bool {
    sqlx::query_scalar::<_, i64>("PRAGMA foreign_keys")
        .fetch_one(pool)
        .await
        .unwrap()
        == 1
}

async fn journal_mode(pool: &SqlitePool) -> String {
    sqlx::query_scalar::<_, String>("PRAGMA journal_mode")
        .fetch_one(pool)
        .await
        .unwrap()
        .to_lowercase()
}

/// A plaintext database with the same schema, for side-by-side comparison.
/// Built by hand because genesis always encrypts.
async fn plaintext_db(path: &std::path::Path) -> SqlitePool {
    let opts = sqlx::sqlite::SqliteConnectOptions::from_str(&format!("sqlite:{}", path.display()))
        .unwrap()
        .create_if_missing(true);
    let seed = sqlx::sqlite::SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await
        .unwrap();
    seed.close().await;
    tagdb_core::connect(path.to_str().unwrap()).await.unwrap()
}

#[tokio::test]
async fn the_encrypted_path_enforces_foreign_keys() {
    let dir = TempDir::new().unwrap();
    let db = dir.path().join("enc.db");
    tagdb_core::create_fresh_database(db.to_str().unwrap(), KEY)
        .await
        .unwrap();

    let pool = tagdb_core::connect_encrypted(db.to_str().unwrap(), KEY)
        .await
        .unwrap();
    assert!(
        foreign_keys_on(&pool).await,
        "connect_encrypted does not set foreign_keys explicitly; if this fails the \
         default changed and 24 ON DELETE CASCADE clauses stopped working"
    );
    pool.close().await;
}

#[tokio::test]
async fn on_delete_cascade_works_on_an_encrypted_connection() {
    let dir = TempDir::new().unwrap();
    let db = dir.path().join("enc.db");
    tagdb_core::create_fresh_database(db.to_str().unwrap(), KEY)
        .await
        .unwrap();
    let pool = tagdb_core::connect_encrypted(db.to_str().unwrap(), KEY)
        .await
        .unwrap();

    sqlx::query("INSERT INTO files(id, path, mtime, size) VALUES (1, '/x', 0, 0)")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("INSERT INTO tags(id, tag) VALUES (1, 't')")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("INSERT INTO file_tags(file_id, tag_id) VALUES (1, 1)")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query("DELETE FROM files WHERE id = 1")
        .execute(&pool)
        .await
        .unwrap();

    let orphans: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM file_tags WHERE file_id = 1")
        .fetch_one(&pool)
        .await
        .unwrap();
    pool.close().await;

    assert_eq!(
        orphans, 0,
        "deleting a file must cascade to its tags on the encrypted path too"
    );
}

#[tokio::test]
async fn both_paths_agree_on_foreign_keys_and_journal_mode() {
    let dir = TempDir::new().unwrap();

    let enc = dir.path().join("enc.db");
    tagdb_core::create_fresh_database(enc.to_str().unwrap(), KEY)
        .await
        .unwrap();
    let enc_pool = tagdb_core::connect_encrypted(enc.to_str().unwrap(), KEY)
        .await
        .unwrap();
    let (enc_fk, enc_journal) = (
        foreign_keys_on(&enc_pool).await,
        journal_mode(&enc_pool).await,
    );
    enc_pool.close().await;

    let plain = dir.path().join("plain.db");
    let plain_pool = plaintext_db(&plain).await;
    let (plain_fk, plain_journal) = (
        foreign_keys_on(&plain_pool).await,
        journal_mode(&plain_pool).await,
    );
    plain_pool.close().await;

    assert_eq!(enc_fk, plain_fk, "foreign key enforcement must match");
    assert_eq!(enc_journal, plain_journal, "journal mode must match");
    assert_eq!(enc_journal, "wal", "both paths must end up in WAL");
}

#[tokio::test]
async fn the_readonly_encrypted_path_also_enforces_foreign_keys() {
    let dir = TempDir::new().unwrap();
    let db = dir.path().join("enc.db");
    tagdb_core::create_fresh_database(db.to_str().unwrap(), KEY)
        .await
        .unwrap();

    let pool = tagdb_core::connect_encrypted_readonly(db.to_str().unwrap(), KEY)
        .await
        .unwrap();
    assert!(foreign_keys_on(&pool).await);
    pool.close().await;
}
