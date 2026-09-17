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
            // Real databases are created in WAL, so match them rather than the
            // driver default: the fixture should look like what the gate meets
            // in production.
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

    // No --standalone, and --python-url declares a Python backend that owns
    // the migration chain: that declaration is what makes this the warn path.
    // Without it there is nobody to migrate and the same database is refused
    // instead (see the sibling test).
    let mut child = Command::new(env!("CARGO_BIN_EXE_yu-server"))
        .arg("--db")
        .arg(&db)
        .arg("--python-url")
        .arg("http://127.0.0.1:1")
        .arg("--port")
        .arg(free_port().to_string())
        .env("RUST_LOG", "warn")
        .env_remove("YU_DB_KEY")
        .env("YU_SKIP_DOTENV_FILES", "1")
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
        "the mismatch was reported with the refusing remedy, not the carrying-on one.\nstdout:\n{text}"
    );
}

#[test]
fn a_launch_with_no_declared_migrator_refuses() {
    // The defect this pins: a launch that passes neither --standalone nor
    // --python-url (deploy/*.service, a bare yu-server) used to warn and then
    // serve the stale database. Nobody was going to migrate it.
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");
    write_stale_db(&db);

    let mut child = Command::new(env!("CARGO_BIN_EXE_yu-server"))
        .arg("--db")
        .arg(&db)
        .arg("--port")
        .arg(free_port().to_string())
        .env("RUST_LOG", "warn")
        .env_remove("YU_DB_KEY")
        // Both are needed, and neither substitutes for the other: env_remove
        // drops what this process inherited, YU_SKIP_DOTENV_FILES stops
        // load_dotenv_files from reading ~/.config/yu/server.env and
        // set_var-ing it back before clap parses. Dropping either lets a
        // developer's own config turn this into the declared-migrator path,
        // where the assertion below would fail for the wrong reason.
        .env_remove("YU_PYTHON_URL")
        .env("YU_SKIP_DOTENV_FILES", "1")
        .current_dir(dir.path())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn()
        .expect("spawn yu-server");

    // Drained on threads for the same reason the sibling test does it: a full
    // pipe would block the child before it could exit.
    let mut stdout = child.stdout.take().expect("piped stdout");
    let mut stderr = child.stderr.take().expect("piped stderr");
    let out_reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stdout.read_to_end(&mut buf);
        String::from_utf8_lossy(&buf).into_owned()
    });
    let err_reader = std::thread::spawn(move || {
        let mut buf = Vec::new();
        let _ = stderr.read_to_end(&mut buf);
        String::from_utf8_lossy(&buf).into_owned()
    });

    // Not .output(): it waits for exit with no deadline, and the regression
    // this guards is exactly "the gate did not fire", in which case yu-server
    // binds and serves forever. A hang is a worse failure report than an
    // assertion.
    let deadline = Instant::now() + Duration::from_secs(30);
    let mut status = None;
    while Instant::now() < deadline {
        if let Some(found) = child.try_wait().expect("try_wait") {
            status = Some(found);
            break;
        }
        std::thread::sleep(Duration::from_millis(200));
    }
    // Reaped on both paths: a child left unwaited keeps a zombie around for the
    // rest of the test binary's run.
    let status = match status {
        Some(found) => Some(found),
        None => {
            let _ = child.kill();
            child.wait().ok()
        }
    };
    let out = out_reader.join().expect("stdout reader");
    let text = err_reader.join().expect("stderr reader");

    let status = status.expect("yu-server kept running instead of refusing");
    assert_eq!(
        status.code(),
        Some(78),
        "a stale database with no declared migrator must exit 78.\nstdout:\n{out}\nstderr:\n{text}"
    );
    assert!(
        text.contains("cannot migrate"),
        "check_genesis_acceptance.py matches on this phrase: {text}"
    );
    assert!(
        !text.contains("Standalone"),
        "this launch is not standalone; the wording must not say so: {text}"
    );
}
