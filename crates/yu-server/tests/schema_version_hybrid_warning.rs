//! Hybrid must not stay silent about a schema-version mismatch.
//!
//! The standalone gate refuses to start on a mismatch, but hybrid deliberately
//! does not -- Python owns the migration chain and may be a version ahead. That
//! exemption used to mean hybrid skipped the check entirely, so a database
//! several versions behind produced a clean-looking start that answered every
//! query with nothing.
//!
//! This test drives the real binary, not a copy of the comparison, because the
//! defect being pinned was a missing *call*, not a wrong verdict: a unit test on
//! the verdict function stays green with the hybrid branch deleted.

use std::io::Read;
use std::process::{Command, Stdio};
use std::time::{Duration, Instant};

/// A database old enough to be a mismatch under any plausible bump of
/// `EXPECTED_PYTHON_SCHEMA_VERSION`, holding nothing but the table the check
/// reads.
fn write_stale_db(path: &std::path::Path) {
    let url = format!("sqlite://{}?mode=rwc", path.display());
    tokio::runtime::Builder::new_current_thread()
        .enable_all()
        .build()
        .expect("runtime")
        .block_on(async {
            let pool = sqlx::SqlitePool::connect(&url).await.expect("create db");
            // The read-only probe opens with `journal_mode(Wal)`, and switching
            // journal mode is itself a write. A fixture left in SQLite's default
            // DELETE mode is therefore unreadable to it -- real databases are
            // created in WAL, so match them rather than the driver default.
            sqlx::query("PRAGMA journal_mode=WAL")
                .execute(&pool)
                .await
                .expect("wal");
            sqlx::query(
                "CREATE TABLE schema_version (
                     version INTEGER PRIMARY KEY,
                     applied_at INTEGER NOT NULL,
                     note TEXT NOT NULL
                 )",
            )
            .execute(&pool)
            .await
            .expect("create schema_version");
            sqlx::query("INSERT INTO schema_version VALUES (1, 0, 'stale fixture')")
                .execute(&pool)
                .await
                .expect("seed version");
            pool.close().await;
        });
}

/// A port nothing else holds. Bound and released so the server can take it; the
/// server is killed before it serves anything, so a lost race only costs this
/// test its start-up, not its assertion (the warning precedes the bind).
fn free_port() -> u16 {
    std::net::TcpListener::bind("127.0.0.1:0")
        .expect("bind")
        .local_addr()
        .expect("addr")
        .port()
}

#[test]
fn hybrid_warns_about_a_stale_schema_version() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");
    write_stale_db(&db);

    // No --standalone: this is the hybrid path, the one that must warn rather
    // than refuse.
    let mut child = Command::new(env!("CARGO_BIN_EXE_yu-server"))
        .arg("--db")
        .arg(&db)
        .arg("--port")
        .arg(free_port().to_string())
        .env("RUST_LOG", "warn")
        .env_remove("YU_DB_KEY")
        .current_dir(dir.path())
        // `tracing_subscriber::fmt` writes to stdout; panics go to stderr. Both
        // are captured because the assertion needs the first and the failure
        // message is only useful with the second.
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn yu-server");

    let mut stdout = child.stdout.take().expect("piped stdout");
    let mut stderr = child.stderr.take().expect("piped stderr");
    let out_reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        // Ends when the child exits or is killed below and the pipe closes.
        let _ = stdout.read_to_end(&mut buf);
        String::from_utf8_lossy(&buf).into_owned()
    });
    let err_reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stderr.read_to_end(&mut buf);
        String::from_utf8_lossy(&buf).into_owned()
    });

    // The warning is emitted before the listener binds, so there is nothing to
    // wait *for* beyond start-up. Give it room on a cold filesystem, and stop
    // early if the server gave up on the deliberately minimal database.
    let deadline = Instant::now() + Duration::from_secs(30);
    while Instant::now() < deadline {
        if child.try_wait().expect("try_wait").is_some() {
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    let _ = child.kill();
    let _ = child.wait();
    let text = out_reader.join().expect("stdout reader");
    let errors = err_reader.join().expect("stderr reader");

    assert!(
        text.contains("schema v1"),
        "hybrid start did not report the stale schema version.\nstdout:\n{text}\nstderr:\n{errors}"
    );
    assert!(
        text.contains("Python owns this migration chain"),
        "the mismatch was reported with the standalone remedy, not the hybrid one.\nstdout:\n{text}"
    );
}
