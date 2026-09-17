//! SQLite online backup, via the same C API Python's `sqlite3.Connection.backup`
//! uses (`sqlite3_backup_init` / `_step` / `_finish`).
//!
//! `sqlx` has no binding for it, but it does hand out the raw `sqlite3*`
//! (`LockedSqliteHandle::as_raw_handle`), and `libsqlite3-sys` — already a
//! dependency, built with bundled SQLCipher — exports the three functions. So
//! no new dependency is needed, and, more importantly, the handle comes from a
//! connection sqlx has already keyed and set `mmap_size=0` on. Opening a second
//! connection by hand would mean re-applying both, and getting either wrong
//! writes a file that looks fine until someone tries to restore it.
//!
//! `VACUUM INTO` was the obvious safe alternative and does not work here: it
//! cannot express the restore direction (backup file *into* the live
//! database), and a port whose create and restore use different mechanisms is
//! the one that diverges.

use std::ffi::CStr;
use std::path::Path;

use libsqlite3_sys as ffi;
use sqlx::sqlite::SqliteConnectOptions;
use sqlx::{ConnectOptions, SqliteConnection};

/// Why an online backup failed. The messages are the caller's to wrap; the
/// route layer maps them into Python's `Backup failed: {exc}` shape.
#[derive(Debug)]
pub enum BackupError {
    /// Could not open (or create) the destination database.
    OpenDestination(String),
    /// `sqlite3_backup_init` returned null — the message comes from the
    /// destination handle, which is where SQLite records the reason.
    Init(String),
    /// `sqlite3_backup_step` did not reach `SQLITE_DONE`.
    Step(String),
    /// sqlx could not hand over a raw handle.
    Handle(String),
}

impl std::fmt::Display for BackupError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        // Every variant renders as its own message; the variants exist to say
        // *where* the failure came from, which the caller's context supplies.
        let (BackupError::OpenDestination(message)
        | BackupError::Init(message)
        | BackupError::Step(message)
        | BackupError::Handle(message)) = self;
        write!(f, "{message}")
    }
}

/// Build connect options carrying the SQLCipher key and the `mmap_size=0`
/// discipline the rest of the server uses.
///
/// `mmap_size=0` is not a tuning choice: `core/services_core/db_cipher.py`
/// sets it to block the mmap+SQLCipher torn-write corruption documented in
/// `SQLCIPHER_MMAP_CORRUPTION.md`, and `state.rs` mirrors it for every pool.
/// A backup connection that omitted it would be the one place the guard is
/// missing, on the file whose whole purpose is to survive corruption.
pub fn keyed_options(path: &Path, key: &str, create: bool) -> Result<SqliteConnectOptions, String> {
    let mut options = SqliteConnectOptions::new()
        .filename(path)
        .pragma("mmap_size", "0")
        .create_if_missing(create);
    if !key.is_empty() {
        // Single quotes are doubled the same way `state.rs` and
        // `tagdb_core::connect_encrypted` do it; the pragma value is a SQL
        // string literal, not a bound parameter.
        let escaped = key.replace('\'', "''");
        options = options
            .pragma("cipher_memory_security", "OFF")
            .pragma("key", format!("'{escaped}'"));
    }
    Ok(options)
}

/// Copy `source` into a fresh database at `dest_path` using SQLite's online
/// backup API.
///
/// `source` stays usable afterwards; the backup runs against a consistent
/// snapshot even under WAL, which is the property that makes this preferable
/// to copying the file.
pub async fn backup_to_path(
    source: &mut SqliteConnection,
    dest_path: &Path,
    key: &str,
) -> Result<(), BackupError> {
    let options = keyed_options(dest_path, key, true).map_err(BackupError::OpenDestination)?;
    let mut dest = options
        .connect()
        .await
        .map_err(|e| BackupError::OpenDestination(format!("{e}")))?;
    copy_between(source, &mut dest).await
}

/// Copy the whole `main` database of `source` over `dest`'s `main`.
///
/// Split from `backup_to_path` so restore — which opens the backup file as the
/// source and the live database as the destination — reuses the identical
/// step/finish handling rather than growing a second copy of it.
pub async fn copy_between(
    source: &mut SqliteConnection,
    dest: &mut SqliteConnection,
) -> Result<(), BackupError> {
    // Both locks are taken *before* either raw pointer is produced, and both
    // are held until the copy finishes. Taking a pointer and dropping its
    // handle first would release the connection's lock while SQLite is still
    // reading through it. It also keeps the handler future `Send`: a raw
    // pointer is `!Send`, so none may be alive across an `.await`, and there
    // are no awaits below this point.
    let mut source_handle = source
        .lock_handle()
        .await
        .map_err(|e| BackupError::Handle(format!("source handle unavailable: {e}")))?;
    let mut dest_handle = dest
        .lock_handle()
        .await
        .map_err(|e| BackupError::Handle(format!("destination handle unavailable: {e}")))?;
    let source_raw = source_handle.as_raw_handle().as_ptr();
    let dest_raw = dest_handle.as_raw_handle().as_ptr();

    // SAFETY: both pointers come from `LockedSqliteHandle`s that stay alive
    // for the whole of this block, so neither connection can be closed or used
    // concurrently. `main` is a static C string. Every exit path runs
    // `sqlite3_backup_finish` before returning: it must not leak, and it is
    // also what commits the destination transaction.
    unsafe {
        // A C-string literal: the name is fixed and cannot carry an interior
        // nul, so there is nothing to fall back to at runtime. The previous
        // `CString::new("main").expect(...)` allocated on every call to prove a
        // property the literal already has.
        const MAIN: &CStr = c"main";
        let backup = ffi::sqlite3_backup_init(dest_raw, MAIN.as_ptr(), source_raw, MAIN.as_ptr());
        if backup.is_null() {
            // SQLite records the reason on the *destination* handle.
            return Err(BackupError::Init(last_error(dest_raw)));
        }
        // -1 copies every remaining page in one step; this is what Python's
        // `Connection.backup()` does by default (`pages=-1`).
        let step = ffi::sqlite3_backup_step(backup, -1);
        let finish = ffi::sqlite3_backup_finish(backup);
        if step != ffi::SQLITE_DONE {
            return Err(BackupError::Step(format!(
                "backup step failed ({step}): {}",
                last_error(dest_raw)
            )));
        }
        if finish != ffi::SQLITE_OK {
            return Err(BackupError::Step(format!(
                "backup finish failed ({finish}): {}",
                last_error(dest_raw)
            )));
        }
    }
    Ok(())
}

/// Read the last error message off a raw handle.
///
/// # Safety
/// `handle` must be a live `sqlite3*`.
unsafe fn last_error(handle: *mut ffi::sqlite3) -> String {
    let raw = ffi::sqlite3_errmsg(handle);
    if raw.is_null() {
        return "unknown SQLite error".to_string();
    }
    std::ffi::CStr::from_ptr(raw).to_string_lossy().into_owned()
}

#[cfg(test)]
mod tests {
    use sqlx::Executor;

    use super::*;

    async fn seed(path: &Path, key: &str, rows: i64) -> SqliteConnection {
        let mut conn = keyed_options(path, key, true)
            .unwrap()
            .connect()
            .await
            .unwrap();
        conn.execute("CREATE TABLE files (id INTEGER PRIMARY KEY, name TEXT)")
            .await
            .unwrap();
        for i in 1..=rows {
            conn.execute(&*format!(
                "INSERT INTO files (id, name) VALUES ({i}, 'f{i}')"
            ))
            .await
            .unwrap();
        }
        conn
    }

    async fn count(path: &Path, key: &str) -> i64 {
        let mut conn = keyed_options(path, key, false)
            .unwrap()
            .connect()
            .await
            .unwrap();
        sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM files")
            .fetch_one(&mut conn)
            .await
            .unwrap()
    }

    #[tokio::test]
    async fn an_unencrypted_database_round_trips_through_a_backup() {
        let dir = tempfile::tempdir().unwrap();
        let live = dir.path().join("tags.db");
        let backup = dir.path().join("backup.db");
        let mut source = seed(&live, "", 3).await;

        backup_to_path(&mut source, &backup, "").await.unwrap();
        assert_eq!(count(&backup, "").await, 3);
    }

    #[tokio::test]
    async fn an_encrypted_backup_is_readable_with_the_same_key() {
        // The defect this port exists to fix: Python writes the backup with
        // the key applied, so a backup that could only be opened *without* a
        // key would be unrestorable. Reading it back with the key is the
        // check that the key actually reached the destination connection.
        let dir = tempfile::tempdir().unwrap();
        let live = dir.path().join("tags.db");
        let backup = dir.path().join("backup.db");
        let key = "test-cipher-key";
        let mut source = seed(&live, key, 5).await;

        backup_to_path(&mut source, &backup, key).await.unwrap();
        assert_eq!(count(&backup, key).await, 5);
    }

    #[tokio::test]
    async fn an_encrypted_backup_is_not_readable_without_the_key() {
        // Proves the previous test is not passing because encryption silently
        // did nothing: without the key the same file must fail to open.
        let dir = tempfile::tempdir().unwrap();
        let live = dir.path().join("tags.db");
        let backup = dir.path().join("backup.db");
        let key = "test-cipher-key";
        let mut source = seed(&live, key, 2).await;
        backup_to_path(&mut source, &backup, key).await.unwrap();

        let opened = keyed_options(&backup, "", false).unwrap().connect().await;
        let readable = match opened {
            Err(_) => false,
            Ok(mut conn) => sqlx::query_scalar::<_, i64>("SELECT COUNT(*) FROM files")
                .fetch_one(&mut conn)
                .await
                .is_ok(),
        };
        assert!(
            !readable,
            "an encrypted backup must not open without its key"
        );
    }

    #[tokio::test]
    async fn restore_copies_the_backup_back_over_the_live_database() {
        // The reverse direction, which is why `VACUUM INTO` was rejected.
        let dir = tempfile::tempdir().unwrap();
        let live = dir.path().join("tags.db");
        let backup = dir.path().join("backup.db");
        let key = "test-cipher-key";

        let mut source = seed(&live, key, 4).await;
        backup_to_path(&mut source, &backup, key).await.unwrap();
        // Diverge the live database after the backup was taken.
        source
            .execute("INSERT INTO files (id, name) VALUES (99, 'later')")
            .await
            .unwrap();
        assert_eq!(count(&live, key).await, 5);

        let mut from_backup = keyed_options(&backup, key, false)
            .unwrap()
            .connect()
            .await
            .unwrap();
        copy_between(&mut from_backup, &mut source).await.unwrap();
        assert_eq!(
            count(&live, key).await,
            4,
            "the row added after the backup must be gone"
        );
    }

    #[tokio::test]
    async fn a_key_containing_a_quote_is_escaped_rather_than_breaking_the_pragma() {
        // The pragma value is a SQL string literal; an unescaped quote would
        // either fail to open or, worse, key the file with a truncated key.
        let dir = tempfile::tempdir().unwrap();
        let live = dir.path().join("tags.db");
        let backup = dir.path().join("backup.db");
        let key = "it's-a-key";
        let mut source = seed(&live, key, 1).await;

        backup_to_path(&mut source, &backup, key).await.unwrap();
        assert_eq!(count(&backup, key).await, 1);
    }
}
