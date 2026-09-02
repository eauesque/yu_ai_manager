pub mod db;
pub mod error;
pub mod import;

use std::str::FromStr;
use std::time::Duration;

use sqlx::sqlite::{SqliteConnectOptions, SqlitePool, SqlitePoolOptions};

pub use db::file::{upsert_file, FileRow, UpsertFileParams};
pub use db::genesis::{create_fresh_database, is_sqlite_uri, GenesisOutcome};
pub use db::mark_deleted;
pub use db::migrate::{apply_pending_rust_migrations, apply_pending_rust_migrations_with_data_dir};
pub use db::CURRENT_PARSER_VERSION;
pub use db::{connect, connect_readonly};
pub use error::TagdbError;

/// The Python schema version a database must be at for this binary to use it.
///
/// Python owns `schema_version` and its migration chain; Rust never writes that
/// table. This constant is the version the generated genesis SQL produces and
/// the version the standalone start-up gate compares against. It is pinned to
/// `core/schema_core/schema_constants.py::CURRENT_SCHEMA_VERSION` by
/// `scripts/pre_push_check.py`, so the two cannot drift apart silently.
pub const EXPECTED_PYTHON_SCHEMA_VERSION: i64 = 88;

/// Connect to a SQLCipher-encrypted database, mirroring the Python
/// core/services_core/db_cipher.py behavior (key + mmap_size=0).
pub async fn connect_encrypted(path: &str, key: &str) -> Result<SqlitePool, sqlx::Error> {
    let escaped_key = key.replace('\'', "''");
    let key_pragma = format!("'{escaped_key}'");
    let opts = SqliteConnectOptions::from_str(path)?
        .pragma("cipher_memory_security", "OFF")
        .pragma("key", key_pragma)
        .pragma("mmap_size", "0")
        .busy_timeout(Duration::from_millis(5000))
        .create_if_missing(false);

    SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(opts)
        .await
}

pub async fn connect_encrypted_readonly(path: &str, key: &str) -> Result<SqlitePool, sqlx::Error> {
    let escaped_key = key.replace('\'', "''");
    let key_pragma = format!("'{escaped_key}'");
    let opts = SqliteConnectOptions::from_str(path)?
        .read_only(true)
        .pragma("cipher_memory_security", "OFF")
        .pragma("key", key_pragma)
        .pragma("mmap_size", "0")
        .busy_timeout(Duration::from_millis(5000))
        .create_if_missing(false);

    SqlitePoolOptions::new()
        .max_connections(5)
        .connect_with(opts)
        .await
}
