//! Regression tests born from the stage-0 preflight for the standalone DB
//! genesis spec. They started as throwaway probes for two unresolved questions
//! and both turned into permanent guards.
//!
//!   U6 -- can the bundled SQLCipher create an fts5 virtual table with
//!         tokenize='trigram'? The genesis SQL depends on it in two places
//!         (templates_fts and files_path_fts). If it cannot, genesis is
//!         impossible as designed. Measured: yes, and the tokenizer works.
//!   U1 -- is there a population of databases the peers.inference_types repair
//!         never reaches? Measured: yes. A versioned migration cannot cover it,
//!         because the version is recorded even when the repair returns early
//!         for want of a peers table. The repair therefore runs unconditionally
//!         on every migration pass; this test is what holds it there.
//!
//! Run: CARGO_BUILD_JOBS=1 cargo test -p tagdb-core --test genesis_preflight -- --nocapture

use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::{Row, SqlitePool};
use std::str::FromStr;
use tempfile::NamedTempFile;

async fn fresh_pool(f: &NamedTempFile) -> SqlitePool {
    let opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", f.path().display()))
        .unwrap()
        .create_if_missing(true);
    SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await
        .unwrap()
}

/// U6: the exact fts5 shapes the genesis SQL will contain.
#[tokio::test]
async fn u6_trigram_fts5_is_available() {
    let f = NamedTempFile::new().unwrap();
    let pool = fresh_pool(&f).await;

    // Content tables the two virtual tables shadow.
    sqlx::raw_sql(
        "CREATE TABLE templates (
             id INTEGER PRIMARY KEY,
             raw_prompt TEXT, raw_negative TEXT,
             char_positive TEXT, char_negative TEXT
         );
         CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT);",
    )
    .execute(&pool)
    .await
    .expect("content tables");

    // Verbatim from core/schema_core/schema_sql_fts.py:4-13.
    sqlx::raw_sql(
        "CREATE VIRTUAL TABLE IF NOT EXISTS templates_fts
         USING fts5(
             raw_prompt, raw_negative, char_positive, char_negative,
             content='templates', content_rowid='id', tokenize='trigram'
         );",
    )
    .execute(&pool)
    .await
    .expect("templates_fts with tokenize='trigram' must be creatable");

    // The second trigram user (schema_sql_fts.py:84).
    sqlx::raw_sql(
        "CREATE VIRTUAL TABLE IF NOT EXISTS files_path_fts
         USING fts5(path, content='files', content_rowid='id', tokenize='trigram');",
    )
    .execute(&pool)
    .await
    .expect("files_path_fts with tokenize='trigram' must be creatable");

    // Prove the tokenizer actually tokenizes, not just that CREATE parsed.
    sqlx::query("INSERT INTO templates(id, raw_prompt) VALUES (1, 'masterpiece')")
        .execute(&pool)
        .await
        .unwrap();
    sqlx::query(
        "INSERT INTO templates_fts(rowid, raw_prompt, raw_negative, char_positive, char_negative)
         VALUES (1, 'masterpiece', NULL, NULL, NULL)",
    )
    .execute(&pool)
    .await
    .unwrap();
    let hits: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM templates_fts WHERE templates_fts MATCH 'terp'")
            .fetch_one(&pool)
            .await
            .expect("trigram MATCH must run");
    assert_eq!(hits, 1, "trigram tokenizer must match an inner substring");

    println!("U6: PASS -- tokenize='trigram' is available and functional");
}

/// U1: reproduce the population Rust migration 006 leaves unrepaired, and prove
/// the unconditional repair covers it.
///
/// Shape: rust_schema_version already records the whole table, and peers is the
/// 13-column pre-migration-86 form. This is reachable because
/// apply_mesh_inference_migration returns early when peers does not exist yet,
/// while the loop still records the version -- so nothing versioned ever fires
/// again once peers finally appears.
#[tokio::test]
async fn u1_repair_covers_the_population_migration_006_skipped() {
    let f = NamedTempFile::new().unwrap();
    let pool = fresh_pool(&f).await;

    sqlx::raw_sql(
        "CREATE TABLE schema_version (
             version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, description TEXT
         );
         CREATE TABLE files (
             path TEXT PRIMARY KEY, meta_source TEXT,
             parser_version INTEGER NOT NULL DEFAULT 1
         );",
    )
    .execute(&pool)
    .await
    .unwrap();

    // Step 1: Rust runs first, on a DB that has no peers table yet. Every
    // versioned migration is recorded even though the peers repair could not run.
    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("first run");

    let recorded: i64 =
        sqlx::query_scalar("SELECT COALESCE(MAX(version), 0) FROM rust_schema_version")
            .fetch_one(&pool)
            .await
            .unwrap();
    assert!(
        recorded >= 6,
        "the loop records the versions even though the peers repair returned early"
    );

    // Step 2: someone else (Python, or lan-cowork's standalone schema) creates
    // the 13-column peers afterwards.
    sqlx::raw_sql(
        "CREATE TABLE peers (
             peer_id TEXT PRIMARY KEY, name TEXT, api_host TEXT, api_port INTEGER,
             token TEXT, token_expires_at INTEGER, token_issued_at INTEGER,
             pubkey BLOB, x25519_pk BLOB,
             created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
             last_reached_at INTEGER, last_attempted_at INTEGER
         );",
    )
    .execute(&pool)
    .await
    .unwrap();

    // Step 3: every subsequent start. No versioned migration fires -- the repair
    // has to be the unconditional one.
    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("second run");
    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("third run");

    let cols: Vec<String> = sqlx::query("PRAGMA table_info(peers)")
        .fetch_all(&pool)
        .await
        .unwrap()
        .iter()
        .map(|r| r.get::<String, _>("name"))
        .collect();

    println!("U1: peers columns after later starts = {cols:?}");
    assert!(
        cols.iter().any(|c| c == "inference_types"),
        "the unconditional repair must cover the population migration 006 skipped; got {cols:?}"
    );

    // The repair must not disturb the pre-existing columns or their order.
    assert_eq!(cols.len(), 14, "13 original columns plus the repaired one");
    assert_eq!(
        cols.last().map(String::as_str),
        Some("inference_types"),
        "the repaired column must land last, matching the BASE schema's column order"
    );

    // Idempotent: running again must not fail or duplicate.
    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("fourth run");

    println!(
        "U1: PASS -- the unconditional repair covers the skipped population and is idempotent"
    );
}

/// U4: an older binary must refuse a database a newer one wrote.
///
/// The migration loop skips everything `<= current`, so a database stamped with
/// a version this build has never heard of looks fully migrated: without a guard
/// the run reports success and the server then operates on a schema it cannot
/// reason about. The Python-side version gate does not cover this -- that gate
/// reads `schema_version`, a different table with a different owner.
#[tokio::test]
async fn u4_a_newer_rust_schema_is_refused() {
    let f = NamedTempFile::new().unwrap();
    let pool = fresh_pool(&f).await;

    sqlx::raw_sql(
        "CREATE TABLE schema_version (
             version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, description TEXT
         );
         CREATE TABLE files (
             path TEXT PRIMARY KEY, meta_source TEXT,
             parser_version INTEGER NOT NULL DEFAULT 1
         );",
    )
    .execute(&pool)
    .await
    .unwrap();

    // Bring the database up to date, then stamp a version from the future.
    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("baseline");
    let future = sqlx::query_scalar::<_, i64>("SELECT MAX(version) FROM rust_schema_version")
        .fetch_one(&pool)
        .await
        .unwrap()
        + 1;
    sqlx::query(
        "INSERT INTO rust_schema_version(version, applied_at, description) \
         VALUES (?, 0, 'written by a later build')",
    )
    .bind(future)
    .execute(&pool)
    .await
    .unwrap();

    let err = tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect_err("a newer Rust schema must be refused");
    let msg = format!("{err}");
    assert!(
        msg.contains("newer than this build"),
        "the message must say what happened: {msg}"
    );
    assert!(
        matches!(err, tagdb_core::TagdbError::IncompatibleSchema(_)),
        "callers distinguish this from a genuine failure to print it rather than panic"
    );

    // The refusal must leave the database alone: it is checked before the loop
    // and before the trailing DELETE on schema_version.
    let still_there: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM rust_schema_version WHERE version = ?")
            .bind(future)
            .fetch_one(&pool)
            .await
            .unwrap();
    assert_eq!(still_there, 1, "nothing may be modified on refusal");

    println!("U4: PASS -- an older build refuses a database a newer build wrote");
}
