pub mod db;
pub mod error;
pub mod import;

use std::str::FromStr;
use std::time::Duration;

use sqlx::sqlite::{SqliteConnectOptions, SqlitePool, SqlitePoolOptions};

pub use db::file::{upsert_file, FileRow, UpsertFileParams};
pub use db::genesis::{create_fresh_database, is_sqlite_uri, GenesisOutcome};
pub use db::mark_deleted;
pub use db::migrate::{
    apply_pending_rust_migrations, apply_pending_rust_migrations_with_data_dir,
    latest_migration_version as latest_rust_migration_version,
};
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
pub const EXPECTED_PYTHON_SCHEMA_VERSION: i64 = 89;

/// The key Python's server opens every database with.
///
/// Not a key this binary uses -- it is a fact about the other side.
/// `core/services_core/db_cipher.py::apply_key` defaults to `_APP_KEY` and the
/// Python *server* reads no environment variable at all, so it can open only
/// a database encrypted with this exact value. (The migration CLI is the
/// exception: it takes `YU_DB_KEY`.) A hybrid deployment whose operator
/// generated their own key therefore has a Python backend that cannot open
/// the database, however healthy it looks -- which is why the version gate
/// asks about the key before it trusts a declared migrator.
///
/// Pinned to the Python constant by `tests/test_db_key_validation_parity.py`.
pub const PYTHON_BUILTIN_DB_KEY: &str = "yu-ai-manager-v1-cipher-2026";

/// Characters an operator-supplied database key may not contain.
///
/// This list is not ours to choose: it is a copy of `_KEY_FORBIDDEN` in
/// `core/services_core/db_cipher.py`, and the copy is pinned by
/// `tests/test_db_key_validation_parity.py`. Python raises on these, so a key
/// this binary accepts but Python refuses produces a database that the
/// migration CLI -- the only migrator there is -- cannot open. That deployment
/// is not merely inconvenient, it is structurally unmigratable: it stops at the
/// version gate forever with no route forward.
///
/// The first four close the SQL literal (`PRAGMA key` is built by
/// interpolation on both sides). The rest are where the log scrubber's value
/// class ends (`logs/scrub.rs`), so a key holding one could be printed in part
/// by any line that carries it.
pub const DB_KEY_FORBIDDEN: &[char] = &['\'', '"', ';', '\\', '&', ',', '}', ']'];

/// Check an operator-supplied key against the rule Python enforces.
///
/// Returns the operator-facing sentence on refusal. Rejecting an empty key is
/// part of the mirrored rule; callers for which "no key" is a legitimate state
/// (a plaintext database, hybrid mode) test for it before calling.
pub fn validate_db_key(key: &str) -> Result<(), String> {
    if key.is_empty() {
        return Err("the database key must not be empty".to_string());
    }
    if key.chars().any(char::is_whitespace) {
        return Err("the database key must not contain whitespace".to_string());
    }
    let bad: Vec<char> = {
        let mut seen: Vec<char> = key
            .chars()
            .filter(|c| DB_KEY_FORBIDDEN.contains(c))
            .collect();
        seen.sort_unstable();
        seen.dedup();
        seen
    };
    if !bad.is_empty() {
        let found: Vec<String> = bad.iter().map(|c| format!("{c:?}")).collect();
        let forbidden: Vec<String> = DB_KEY_FORBIDDEN.iter().map(|c| format!("{c:?}")).collect();
        return Err(format!(
            "the database key must not contain any of {} (found {})",
            forbidden.join(" "),
            found.join(" ")
        ));
    }
    Ok(())
}

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
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                let mut handle = conn.lock_handle().await?;
                crate::db::custom_functions::install(handle.as_raw_handle())
                    .map_err(|e| sqlx::Error::Configuration(e.into()))
            })
        })
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
        .after_connect(|conn, _meta| {
            Box::pin(async move {
                let mut handle = conn.lock_handle().await?;
                crate::db::custom_functions::install(handle.as_raw_handle())
                    .map_err(|e| sqlx::Error::Configuration(e.into()))
            })
        })
        .connect_with(opts)
        .await
}

#[cfg(test)]
mod db_key_validation_tests {
    use super::{validate_db_key, DB_KEY_FORBIDDEN};

    #[test]
    fn the_documented_generator_output_is_accepted() {
        // `openssl rand -hex 32`, which deploy/server.env.example prescribes.
        assert!(validate_db_key(&"a1b2c3d4e5f6".repeat(5)).is_ok());
        // base64 is the other obvious choice and must also pass: none of
        // + / = is forbidden.
        assert!(validate_db_key("aB3+xY/9zQ==").is_ok());
    }

    #[test]
    fn every_forbidden_character_is_refused_one_at_a_time() {
        // Not a spot check: a key that Python refuses and this accepts is the
        // whole defect, so each character is exercised.
        for ch in DB_KEY_FORBIDDEN {
            let key = format!("good{ch}key");
            let err = validate_db_key(&key)
                .expect_err(&format!("{ch:?} was accepted but Python refuses it"));
            assert!(err.contains("must not contain any of"), "{err}");
        }
    }

    #[test]
    fn empty_and_whitespace_keys_are_refused() {
        assert!(validate_db_key("").is_err());
        assert!(validate_db_key("has space").is_err());
        assert!(validate_db_key("has\ttab").is_err());
        assert!(validate_db_key("trailing\n").is_err());
    }
}
