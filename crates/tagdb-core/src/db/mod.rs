pub mod custom_functions;
pub mod file;
pub mod genesis;
pub mod migrate;
pub mod tag;

pub use file::mark_deleted;

use crate::TagdbError;
use log::LevelFilter;
use sqlx::sqlite::{
    SqliteConnectOptions, SqliteJournalMode, SqlitePool, SqlitePoolOptions, SqliteSynchronous,
};
use sqlx::ConnectOptions;
use std::str::FromStr;
use std::time::Duration;

// sqlx default is 1s/WARN — too coarse to isolate WAL busy_timeout waits from
// genuinely slow queries across the three separate SQLite pools. Lower the
// bar so contention shows up promptly instead of blending into silence.
const SLOW_STATEMENT_THRESHOLD: Duration = Duration::from_millis(200);

// Python's core/schema_core/schema_constants.py currently pins
// CURRENT_PARSER_VERSION at 6 (v6: BUG-59 blocked namespaces, BUG-60
// break tag, plus full v3->v6 heuristics history). Rust's prompt_parse.rs
// port is verified against Python-generated goldens by
// crates/tagdb-core/tests/prompt_parse_conformance.rs. The active
// tests/compat_goldens/prompt_parse/ fixtures cover BUG-33~67 parser
// heuristics and passed on 2026-07-03, so Rust can claim the same parser
// version without making should_rescan() skip files parsed by an
// incomplete port. See
// docs/superpowers/specs/2026-07-01-rust-standalone-native-auto-import.md.
pub const CURRENT_PARSER_VERSION: i32 = 6;

pub async fn connect(path: &str) -> Result<SqlitePool, TagdbError> {
    let opts = SqliteConnectOptions::from_str(path)
        .map_err(TagdbError::Db)?
        .journal_mode(SqliteJournalMode::Wal)
        .busy_timeout(Duration::from_millis(5000))
        .synchronous(SqliteSynchronous::Normal)
        .foreign_keys(true)
        .create_if_missing(false)
        .log_slow_statements(LevelFilter::Warn, SLOW_STATEMENT_THRESHOLD);
    let pool = SqlitePoolOptions::new()
        .max_connections(5)
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                let mut handle = conn.lock_handle().await?;
                crate::db::custom_functions::install(handle.as_raw_handle())
                    .map_err(|e| sqlx::Error::Configuration(e.into()))
            })
        })
        .connect_with(opts)
        .await?;
    Ok(pool)
}

/// Read-only pool for query paths that must not contend for the write lock.
///
/// Deliberately does **not** set `journal_mode`: switching a database into WAL
/// is itself a write, and on a read-only connection SQLite answers it with
/// `attempt to write a readonly database`. A database already in WAL needs no
/// such request (the mode lives in the file header), and one in `delete` mode
/// -- which is what a freshly created database is until a writer converts it --
/// would fail the connection outright.
///
/// The failure this avoids was not a clean error: the pool came up, the plain
/// row reads still answered, and only the joined tag query came back empty, so
/// the file-detail route served a file with no tags and no error anywhere.
pub async fn connect_readonly(path: &str) -> Result<SqlitePool, TagdbError> {
    let opts = SqliteConnectOptions::from_str(path)
        .map_err(TagdbError::Db)?
        .read_only(true)
        .busy_timeout(Duration::from_millis(5000))
        .synchronous(SqliteSynchronous::Normal)
        .foreign_keys(true)
        .create_if_missing(false)
        .log_slow_statements(LevelFilter::Warn, SLOW_STATEMENT_THRESHOLD);
    let pool = SqlitePoolOptions::new()
        .max_connections(5)
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                let mut handle = conn.lock_handle().await?;
                crate::db::custom_functions::install(handle.as_raw_handle())
                    .map_err(|e| sqlx::Error::Configuration(e.into()))
            })
        })
        .connect_with(opts)
        .await?;
    Ok(pool)
}
