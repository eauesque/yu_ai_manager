//! T3: the genesis code path.
//!
//! Schema equivalence with Python is proven elsewhere, by
//! `tests/test_rust_genesis_parity.py` running Python's real `init_db`. What is
//! left for Rust to hold is everything the SQL file cannot say by itself:
//! the file is claimed exclusively, the database comes out encrypted and in WAL,
//! the version row is stamped, and a failure part-way through leaves nothing
//! behind.

use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::{Row, SqlitePool};
use std::path::{Path, PathBuf};
use std::str::FromStr;
use tagdb_core::{create_fresh_database, GenesisOutcome, EXPECTED_PYTHON_SCHEMA_VERSION};
use tempfile::TempDir;

// Any key works here: these tests create their own databases and never open one
// the application made. Deliberately NOT the real application key -- crates/ is
// mirrored to a public repository and the key belongs in src-tauri, not here.
const KEY: &str = "test-only-genesis-key";

fn db_path(dir: &TempDir) -> PathBuf {
    dir.path().join("tags.db")
}

/// Open and actually read a page.
///
/// Establishing the connection is not enough: sqlx will hand back a pool for an
/// encrypted file opened with no key, and SQLCipher only reports the mismatch
/// when something reads. The first version of this helper stopped at connect and
/// reported an encrypted database as plaintext.
async fn open(path: &Path, key: Option<&str>) -> Result<SqlitePool, sqlx::Error> {
    let mut opts = SqliteConnectOptions::from_str(&format!("sqlite:{}", path.display()))?
        .create_if_missing(false);
    if let Some(key) = key {
        opts = opts
            .pragma("cipher_memory_security", "OFF")
            .pragma("key", format!("'{key}'"))
            .pragma("mmap_size", "0");
    }
    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await?;
    match sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM sqlite_master")
        .fetch_one(&pool)
        .await
    {
        Ok(_) => Ok(pool),
        Err(err) => {
            pool.close().await;
            Err(err)
        }
    }
}

#[tokio::test]
async fn creates_a_database_stamped_with_the_expected_schema_version() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);

    let outcome = create_fresh_database(path.to_str().unwrap(), KEY)
        .await
        .expect("genesis");
    assert_eq!(outcome, GenesisOutcome::Created);

    let pool = open(&path, Some(KEY)).await.expect("open with key");
    let rows: Vec<(i64, String)> = sqlx::query("SELECT version, description FROM schema_version")
        .fetch_all(&pool)
        .await
        .unwrap()
        .iter()
        .map(|r| {
            (
                r.get::<i64, _>("version"),
                r.get::<String, _>("description"),
            )
        })
        .collect();
    assert_eq!(
        rows,
        vec![(
            EXPECTED_PYTHON_SCHEMA_VERSION,
            "Fresh database init".to_string()
        )],
        "exactly the row Python's fresh-database path writes"
    );
    pool.close().await;
}

#[tokio::test]
async fn the_created_database_is_encrypted() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);
    create_fresh_database(path.to_str().unwrap(), KEY)
        .await
        .expect("genesis");

    // Opening without a key must fail. If this ever passes, genesis produced a
    // plaintext file and the Python version could never open it.
    let plain = open(&path, None).await;
    assert!(
        plain.is_err(),
        "genesis must not produce a plaintext database"
    );
    let wrong = open(&path, Some("not-the-key")).await;
    assert!(wrong.is_err(), "a wrong key must not open the database");
}

#[tokio::test]
async fn the_created_database_is_in_wal_mode() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);
    create_fresh_database(path.to_str().unwrap(), KEY)
        .await
        .expect("genesis");

    let pool = open(&path, Some(KEY)).await.unwrap();
    let mode: String = sqlx::query_scalar("PRAGMA journal_mode")
        .fetch_one(&pool)
        .await
        .unwrap();
    assert_eq!(mode.to_lowercase(), "wal");
    pool.close().await;
}

#[tokio::test]
async fn fts5_virtual_tables_survive_into_the_created_database() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);
    create_fresh_database(path.to_str().unwrap(), KEY)
        .await
        .expect("genesis");

    let pool = open(&path, Some(KEY)).await.unwrap();
    let count: i64 = sqlx::query_scalar(
        "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND sql LIKE 'CREATE VIRTUAL TABLE%'",
    )
    .fetch_one(&pool)
    .await
    .unwrap();
    assert!(count > 0, "genesis SQL must create the fts5 virtual tables");

    // And they must actually be queryable, not merely present.
    let hits: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM templates_fts WHERE templates_fts MATCH 'zzz'")
            .fetch_one(&pool)
            .await
            .expect("trigram fts5 must be queryable in the created database");
    assert_eq!(hits, 0);
    pool.close().await;
}

#[tokio::test]
async fn an_existing_file_is_left_alone() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);
    std::fs::write(&path, b"not a database").unwrap();

    let outcome = create_fresh_database(path.to_str().unwrap(), KEY)
        .await
        .expect("genesis must not error when the file already exists");
    assert_eq!(outcome, GenesisOutcome::Skipped);
    assert_eq!(
        std::fs::read(&path).unwrap(),
        b"not a database",
        "genesis must not overwrite an existing file"
    );
}

#[tokio::test]
async fn an_empty_key_is_refused() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);
    let err = create_fresh_database(path.to_str().unwrap(), "")
        .await
        .expect_err("an empty key must be refused");
    assert!(
        format!("{err}").contains("unencrypted"),
        "the error should say why: {err}"
    );
    assert!(
        !path.exists(),
        "nothing may be created when the key is refused"
    );
}

#[tokio::test]
async fn a_missing_parent_directory_is_refused_without_creating_it() {
    let dir = TempDir::new().unwrap();
    let path = dir.path().join("no-such-dir").join("tags.db");

    let err = create_fresh_database(path.to_str().unwrap(), KEY)
        .await
        .expect_err("a missing directory must be refused");
    let msg = format!("{err}");
    assert!(
        msg.contains("does not exist"),
        "the error should name the problem: {msg}"
    );
    assert!(
        !path.parent().unwrap().exists(),
        "genesis must not create directories"
    );
}

#[tokio::test]
async fn a_failure_part_way_through_leaves_no_files_behind() {
    let dir = TempDir::new().unwrap();
    let path = db_path(&dir);

    // Valid enough to start, invalid before COMMIT. Without the injection seam
    // this path is unreachable: the shipped SQL never fails.
    let broken = "CREATE TABLE ok (id INTEGER PRIMARY KEY);\nTHIS IS NOT SQL;\n";
    let err = tagdb_core::db::genesis::create_fresh_database_with_sql(
        path.to_str().unwrap(),
        KEY,
        broken,
    )
    .await
    .expect_err("broken genesis SQL must fail");
    // Name the failure, not merely its existence: the caller has to be able to
    // tell a malformed-SQL genesis apart from an I/O or key failure.
    let text = format!("{err}");
    assert!(text.contains("syntax"), "unexpected error text: {text}");

    for suffix in ["", "-wal", "-shm"] {
        let mut name = path.clone().into_os_string();
        name.push(suffix);
        assert!(
            !Path::new(&name).exists(),
            "genesis must not leave {} behind on failure",
            Path::new(&name).display()
        );
    }
}

#[tokio::test]
async fn a_sqlite_uri_is_refused() {
    for uri in ["sqlite::memory:", ":memory:", "sqlite://tags.db?mode=rwc"] {
        let err = create_fresh_database(uri, KEY)
            .await
            .expect_err("a SQLite URI is not a path genesis can claim");
        assert!(
            format!("{err}").contains("filesystem path"),
            "unexpected error for {uri}: {err}"
        );
    }
}
