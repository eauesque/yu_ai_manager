//! T4: genesis and the LAN Cowork standalone schema must converge on `peers`.
//!
//! Two crates define `peers`: the generated genesis SQL (from Python's
//! BASE_SCHEMA_SQL) and `lan_cowork`'s `apply_standalone_schema`, which lives in
//! a pinned external crate this repo's push gates cannot scan. They were
//! byte-identical until BASE gained `inference_types`; now genesis writes 14
//! columns and lan-cowork writes 13, and `CREATE TABLE IF NOT EXISTS` never
//! upgrades an existing table.
//!
//! So "whichever runs first wins" is true, and the two winners differ. What
//! makes that safe is the unconditional repair at the end of the Rust migration
//! run, which adds the column to whichever `peers` ended up there. This test
//! pins that convergence: it compares the state after a full start-up sequence,
//! not after each schema application.
//!
//! It lives in yu-server because `lan-cowork` is a dependency of this crate
//! only. Adding it to tagdb-core as a dev-dependency would drag a pinned git
//! crate into the dependency graph of a crate that is mirrored publicly.

use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::{Row, SqlitePool};
use std::str::FromStr;

// Test-only. See the note in tagdb-core/tests/genesis.rs.
const GENESIS_KEY: &str = "test-only-genesis-key";

async fn empty_pool(path: &std::path::Path) -> SqlitePool {
    let opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", path.display()))
        .unwrap()
        .create_if_missing(true);
    SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await
        .unwrap()
}

/// The core tables every real database has before lan-cowork ever runs.
///
/// `peers` is deliberately absent -- that is the whole point of order B. But
/// `files` and `schema_version` are not: Python's schema and the genesis SQL
/// both create them, and Rust migration 4 issues `UPDATE files ...`. A bare
/// database with only the peer family is not a state that exists in production,
/// and building the test on one only proves that migrations need `files`.
async fn scaffold_core_tables(pool: &SqlitePool) {
    sqlx::raw_sql(
        "CREATE TABLE IF NOT EXISTS schema_version (
             version INTEGER PRIMARY KEY, applied_at INTEGER NOT NULL, description TEXT
         );
         CREATE TABLE IF NOT EXISTS files (
             path TEXT PRIMARY KEY, meta_source TEXT,
             parser_version INTEGER NOT NULL DEFAULT 1
         );",
    )
    .execute(pool)
    .await
    .unwrap();
}

async fn peers_columns(pool: &SqlitePool) -> Vec<String> {
    sqlx::query("PRAGMA table_info(peers)")
        .fetch_all(pool)
        .await
        .unwrap()
        .iter()
        .map(|r| r.get::<String, _>("name"))
        .collect()
}

/// Order A: genesis creates `peers` (14 columns), then lan-cowork no-ops.
#[tokio::test]
async fn genesis_first_converges() {
    let dir = tempfile::TempDir::new().unwrap();
    let path = dir.path().join("tags.db");

    tagdb_core::create_fresh_database(path.to_str().unwrap(), GENESIS_KEY)
        .await
        .expect("genesis");

    let opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", path.display()))
        .unwrap()
        .pragma("cipher_memory_security", "OFF")
        .pragma("key", format!("'{GENESIS_KEY}'"))
        .pragma("mmap_size", "0")
        .create_if_missing(false);
    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await
        .unwrap();

    lan_cowork::schema::apply_standalone_schema(&pool)
        .await
        .expect("lan-cowork standalone schema must be a no-op after genesis");
    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("rust migrations");

    let cols = peers_columns(&pool).await;
    assert!(
        cols.iter().any(|c| c == "inference_types"),
        "peers must end up with inference_types; got {cols:?}"
    );
    pool.close().await;
}

/// Order B: lan-cowork creates `peers` (13 columns) on a database genesis never
/// touched. The unconditional repair has to bring it to the same place.
#[tokio::test]
async fn lan_cowork_first_converges_to_the_same_columns() {
    let dir = tempfile::TempDir::new().unwrap();
    let path = dir.path().join("tags.db");
    let pool = empty_pool(&path).await;
    scaffold_core_tables(&pool).await;

    lan_cowork::schema::apply_standalone_schema(&pool)
        .await
        .expect("lan-cowork standalone schema");
    let before = peers_columns(&pool).await;
    assert!(
        !before.iter().any(|c| c == "inference_types"),
        "lan-cowork's peers is the 13-column form; if this changes the two \
         definitions have been reunited and this test should be revisited"
    );

    tagdb_core::apply_pending_rust_migrations(&pool)
        .await
        .expect("rust migrations");

    let after = peers_columns(&pool).await;
    assert!(
        after.iter().any(|c| c == "inference_types"),
        "the unconditional repair must add the column; got {after:?}"
    );
    assert_eq!(
        after.last().map(String::as_str),
        Some("inference_types"),
        "the repaired column lands last, matching genesis's column order"
    );
    pool.close().await;
}

/// The point of the pair: both orders end with the same column set.
#[tokio::test]
async fn both_orders_agree_on_the_peers_column_set() {
    let dir = tempfile::TempDir::new().unwrap();

    // Order A. Reached through create_fresh_database rather than by reading
    // tagdb-core's SQL file directly: crates must not reach outside their own
    // manifest directory (scripts/pre_push_check.py enforces it).
    let a_path = dir.path().join("a.db");
    tagdb_core::create_fresh_database(a_path.to_str().unwrap(), GENESIS_KEY)
        .await
        .unwrap();
    let a_opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", a_path.display()))
        .unwrap()
        .pragma("cipher_memory_security", "OFF")
        .pragma("key", format!("'{GENESIS_KEY}'"))
        .pragma("mmap_size", "0")
        .create_if_missing(false);
    let a = SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(a_opts)
        .await
        .unwrap();
    lan_cowork::schema::apply_standalone_schema(&a)
        .await
        .unwrap();
    tagdb_core::apply_pending_rust_migrations(&a).await.unwrap();
    let cols_a = peers_columns(&a).await;
    a.close().await;

    // Order B.
    let b_path = dir.path().join("b.db");
    let b = empty_pool(&b_path).await;
    scaffold_core_tables(&b).await;
    lan_cowork::schema::apply_standalone_schema(&b)
        .await
        .unwrap();
    tagdb_core::apply_pending_rust_migrations(&b).await.unwrap();
    let cols_b = peers_columns(&b).await;
    b.close().await;

    assert_eq!(
        cols_a, cols_b,
        "the peers column set must not depend on which writer ran first"
    );
}
