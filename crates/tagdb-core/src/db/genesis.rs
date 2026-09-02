//! Database genesis: create `tags.db` from scratch for standalone deployments.
//!
//! Python owns database creation (`core/schema_core/schema_init.py::init_db`),
//! and `connect`/`connect_readonly` both open with `create_if_missing(false)`.
//! A standalone install -- no Python process at all -- therefore cannot start:
//! there is nothing to create the database. This module closes that gap by
//! executing the generated genesis SQL, which is emitted from Python's own
//! `init_db` (see `scripts/internal/gen_rust_genesis_sql.py`).
//!
//! What this module deliberately does NOT do:
//!
//! * It does not create the parent directory. Today `create_if_missing(false)`
//!   makes a wrong `--db` path fail loudly at start-up; creating directories
//!   would turn a typo into "an empty new library appeared", which a user cannot
//!   tell apart from losing everything. Creating the data directory is the
//!   installer's job (the desktop path already does it in
//!   `src-tauri/src/app_dirs.rs::ensure_data_dir`).
//! * It does not migrate. A database at some other schema version is refused by
//!   the caller, not upgraded here.
//! * It does not run without a key. Python opens tags.db through SQLCipher
//!   unconditionally, so a plaintext database created here would be one Python
//!   could never open again.

use crate::TagdbError;
use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
use sqlx::{Executor, SqlitePool};
use std::fs::OpenOptions;
use std::path::Path;
use std::str::FromStr;
use std::time::Duration;

/// The schema this file produces, mirroring Python's `CURRENT_SCHEMA_VERSION`.
/// `scripts/pre_push_check.py` pins the two together.
const GENESIS_SQL: &str = include_str!("../migrations/genesis_v88.sql");

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum GenesisOutcome {
    Created,
    /// The file already existed, so this call did nothing. Another process may
    /// have won the race, or the database was simply already there.
    Skipped,
}

/// True for `--db` values that are SQLite URIs rather than filesystem paths.
///
/// `Cli.db` accepts any string. `sqlite::memory:` and `sqlite://…?mode=…` have
/// no parent directory to check and nothing to exclusively create, so genesis
/// has no meaning for them.
pub fn is_sqlite_uri(db: &str) -> bool {
    db.starts_with("sqlite:") || db == ":memory:"
}

/// Create a fresh database at `path` and stamp it with the expected schema version.
///
/// `key` is required and must not be empty: see the module note on SQLCipher.
/// Returns [`GenesisOutcome::Skipped`] without touching anything if the file
/// already exists.
pub async fn create_fresh_database(path: &str, key: &str) -> Result<GenesisOutcome, TagdbError> {
    create_fresh_database_with_sql(path, key, GENESIS_SQL).await
}

/// The body of [`create_fresh_database`], with the SQL as a parameter.
///
/// This exists so tests can inject a failure part-way through. A static, valid
/// SQL file never fails, so without this seam the rollback and cleanup paths
/// could not be exercised at all -- they would be code no test ever reaches.
pub async fn create_fresh_database_with_sql(
    path: &str,
    key: &str,
    sql: &str,
) -> Result<GenesisOutcome, TagdbError> {
    if key.is_empty() {
        return Err(TagdbError::Genesis(
            "refusing to create an unencrypted database: Python opens tags.db through \
             SQLCipher unconditionally, so a plaintext file here could never be opened \
             by the Python version again"
                .to_string(),
        ));
    }
    if is_sqlite_uri(path) {
        return Err(TagdbError::Genesis(format!(
            "genesis needs a filesystem path, got the SQLite URI {path:?}"
        )));
    }

    let db_path = Path::new(path);
    let shown = db_path
        .canonicalize()
        .ok()
        .and_then(|p| p.to_str().map(str::to_owned))
        .unwrap_or_else(|| {
            std::env::current_dir()
                .map(|cwd| cwd.join(db_path).to_string_lossy().into_owned())
                .unwrap_or_else(|_| path.to_string())
        });

    let parent = db_path.parent().filter(|p| !p.as_os_str().is_empty());
    if let Some(parent) = parent {
        if !parent.is_dir() {
            return Err(TagdbError::Genesis(format!(
                "cannot create the database: its directory does not exist ({}). \
                 Genesis will not create directories -- a mistyped path must fail \
                 loudly rather than silently produce an empty library.",
                parent.display()
            )));
        }
    }

    // Claim the file. Losing this race is not an error: whoever won will have a
    // usable database, and the caller falls through to the normal open path.
    match OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(db_path)
    {
        Ok(file) => drop(file),
        Err(err) if err.kind() == std::io::ErrorKind::AlreadyExists => {
            return Ok(GenesisOutcome::Skipped)
        }
        Err(err) => {
            return Err(TagdbError::Genesis(format!(
                "cannot create the database file {shown}: {err}"
            )))
        }
    }

    match populate(path, key, sql).await {
        Ok(()) => Ok(GenesisOutcome::Created),
        Err(err) => {
            // Remove only what this call created. The pool is dropped inside
            // populate() before returning, which matters on Windows, where an
            // open handle makes the file undeletable.
            let cleanup = remove_database_files(db_path);
            match cleanup {
                Ok(()) => Err(err),
                Err(io_err) => Err(TagdbError::Genesis(format!(
                    "{err} -- and cleaning up the partial database at {shown} also failed: {io_err}"
                ))),
            }
        }
    }
}

async fn populate(path: &str, key: &str, sql: &str) -> Result<(), TagdbError> {
    let pool = open_keyed(path, key).await?;
    let result = run_genesis(&pool, sql).await;
    // Close before any caller tries to delete the file.
    pool.close().await;
    result
}

async fn open_keyed(path: &str, key: &str) -> Result<SqlitePool, TagdbError> {
    let escaped_key = key.replace('\'', "''");
    // Pragma order mirrors `connect_encrypted` in lib.rs, which is the shape
    // already proven in production. The key must take effect before anything
    // touches the file; journal_mode and friends are issued as statements after
    // the connection is up rather than as typed options, so that sqlx cannot
    // reorder them ahead of the key on a freshly created file.
    let opts = SqliteConnectOptions::from_str(path)
        .map_err(TagdbError::Db)?
        .pragma("cipher_memory_security", "OFF")
        .pragma("key", format!("'{escaped_key}'"))
        .pragma("mmap_size", "0")
        .busy_timeout(Duration::from_millis(5000))
        .create_if_missing(true);

    let pool = SqlitePoolOptions::new()
        .max_connections(1)
        .connect_with(opts)
        .await
        .map_err(TagdbError::Db)?;

    // Match the plaintext `connect` path (db/mod.rs), which sets these three.
    // `connect_encrypted` spells out none of them, but that is a difference in
    // the source, not in behaviour: measured, both paths report foreign_keys=1
    // (sqlx enables them) and both end up in WAL, because journal_mode is set
    // here at creation and persists in the file. The only real difference is
    // `synchronous` -- FULL on the encrypted path, NORMAL here -- which is the
    // more durable setting. `crates/tagdb-core/tests/connection_symmetry.rs`
    // pins all of that so the asymmetry is not re-read as a defect again.
    for pragma in [
        "PRAGMA journal_mode=WAL;",
        "PRAGMA synchronous=NORMAL;",
        "PRAGMA foreign_keys=ON;",
    ] {
        pool.execute(pragma).await.map_err(TagdbError::Db)?;
    }
    Ok(pool)
}

async fn run_genesis(pool: &SqlitePool, sql: &str) -> Result<(), TagdbError> {
    let mut conn = pool.acquire().await?;
    sqlx::query("BEGIN IMMEDIATE").execute(&mut *conn).await?;

    // Every step is matched rather than `?`-propagated: an early return here
    // would leave the transaction open on a pooled connection.
    let result: Result<(), TagdbError> = async {
        sqlx::raw_sql(sql).execute(&mut *conn).await?;
        sqlx::query(
            "INSERT OR IGNORE INTO schema_version(version, applied_at, description) \
             VALUES(?, CAST(strftime('%s','now') AS INTEGER), 'Fresh database init')",
        )
        .bind(crate::EXPECTED_PYTHON_SCHEMA_VERSION)
        .execute(&mut *conn)
        .await?;
        Ok(())
    }
    .await;

    match result {
        Ok(()) => {
            sqlx::query("COMMIT").execute(&mut *conn).await?;
            Ok(())
        }
        Err(err) => {
            let _ = sqlx::query("ROLLBACK").execute(&mut *conn).await;
            Err(err)
        }
    }
}

/// Delete the database and its write-ahead sidecars, ignoring absent files.
fn remove_database_files(db_path: &Path) -> std::io::Result<()> {
    for suffix in ["", "-wal", "-shm"] {
        let mut name = db_path.as_os_str().to_os_string();
        name.push(suffix);
        match std::fs::remove_file(Path::new(&name)) {
            Ok(()) => {}
            Err(err) if err.kind() == std::io::ErrorKind::NotFound => {}
            Err(err) => return Err(err),
        }
    }
    Ok(())
}
