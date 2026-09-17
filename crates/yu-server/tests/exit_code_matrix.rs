//! The exit code depends on whether the version could be *read*.
//!
//! `deploy/README.md` carries this matrix, and a table nobody re-measures is a
//! table that drifts. 78 means "the database is behind and nothing can migrate
//! it"; a database this binary cannot open at all is a different answer -- exit
//! 1 -- because being unreadable is not the same as being proven behind. That
//! distinction matters to an operator: `RestartPreventExitStatus=78` holds the
//! first case and not the second, so a keyless machine retries until
//! `StartLimitBurst` gives up.
//!
//! Run against the real binary. The claim is about what an operator sees.

use std::process::Command;

const PYTHON_BUILTIN_KEY: &str = "yu-ai-manager-v1-cipher-2026";

/// Build a database at `version`, encrypted with `key` when one is given.
async fn seed(path: &std::path::Path, version: i64, key: Option<&str>) {
    let url = format!("sqlite://{}?mode=rwc", path.display());
    let opts: sqlx::sqlite::SqliteConnectOptions = url.parse().expect("options");
    let opts = match key {
        Some(k) => opts.pragma("key", format!("'{k}'")),
        None => opts,
    };
    let pool = sqlx::SqlitePool::connect_with(opts).await.expect("connect");
    sqlx::query("CREATE TABLE files (id INTEGER PRIMARY KEY)")
        .execute(&pool)
        .await
        .expect("files");
    sqlx::query("CREATE TABLE schema_version (version INTEGER)")
        .execute(&pool)
        .await
        .expect("schema_version");
    sqlx::query("INSERT INTO schema_version VALUES (?)")
        .bind(version)
        .execute(&pool)
        .await
        .expect("insert");
    pool.close().await;
}

fn start(db: &std::path::Path, key: Option<&str>) -> (Option<i32>, String) {
    let exe = env!("CARGO_BIN_EXE_yu-server");
    let dir = tempfile::tempdir().expect("cwd");
    let mut cmd = Command::new(exe);
    cmd.arg("--db")
        .arg(db)
        .arg("--port")
        .arg("0")
        .arg("--standalone")
        .current_dir(dir.path())
        .env("YU_SKIP_DOTENV_FILES", "1")
        .env("YU_SKIP_LAUNCH_ARGS_FILE", "1")
        .env_remove("YU_DB")
        .env_remove("YU_DB_KEY");
    if let Some(k) = key {
        cmd.arg("--db-key").arg(k);
    }
    let out = cmd.output().expect("run yu-server");
    let text = format!(
        "{}{}",
        String::from_utf8_lossy(&out.stdout),
        String::from_utf8_lossy(&out.stderr)
    );
    (out.status.code(), text)
}

#[tokio::test]
async fn a_behind_database_stops_at_78_when_the_key_lets_it_be_read() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");
    let behind = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION - 1;
    seed(&db, behind, Some(PYTHON_BUILTIN_KEY)).await;

    let (code, text) = start(&db, Some(PYTHON_BUILTIN_KEY));
    assert_eq!(code, Some(78), "{text}");
    assert!(text.contains("needs"), "{text}");
}

#[tokio::test]
async fn a_plaintext_behind_database_stops_at_78_with_no_key_at_all() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");
    seed(&db, tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION - 1, None).await;

    let (code, text) = start(&db, None);
    assert_eq!(code, Some(78), "{text}");
}

#[tokio::test]
async fn an_encrypted_database_without_a_key_exits_1_and_names_the_key() {
    // Not 78: nothing here knows the version, so nothing knows it is behind.
    // The operator has to be told which of the two situations they are in,
    // because only one of them is fixed by migrating.
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");
    seed(
        &db,
        tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION - 1,
        Some(PYTHON_BUILTIN_KEY),
    )
    .await;

    let (code, text) = start(&db, None);
    assert_eq!(code, Some(1), "{text}");
    assert!(text.contains("No key was supplied"), "{text}");
    assert!(!text.contains("panicked at"), "{text}");
}

#[tokio::test]
async fn a_current_database_without_its_key_fails_the_same_way() {
    // Being current changes nothing the binary can see, which is exactly why
    // "stops at 78" describes only the machines that pass a key.
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");
    seed(
        &db,
        tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION,
        Some(PYTHON_BUILTIN_KEY),
    )
    .await;

    let (code, text) = start(&db, None);
    assert_eq!(code, Some(1), "{text}");
    assert!(text.contains("No key was supplied"), "{text}");
}

#[tokio::test]
async fn a_binary_downgrade_exits_65_and_says_how_to_get_the_newer_build() {
    // The one start-up failure whose only repair is a newer binary. Run against
    // the real binary because what is under test is what an operator sees: the
    // refusal, the remedy, and the code — a unit test of the wording alone let
    // a fault injection remove the line that prints it.
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("tags.db");

    // Past the Python-chain gate, so the run reaches the Rust migrations.
    seed(&db, tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION, None).await;
    let url = format!("sqlite://{}", db.display());
    let pool = sqlx::SqlitePool::connect(&url).await.expect("connect");
    sqlx::query(
        "CREATE TABLE rust_schema_version (version INTEGER PRIMARY KEY,          applied_at INTEGER NOT NULL, description TEXT)",
    )
    .execute(&pool)
    .await
    .expect("table");
    sqlx::query("INSERT INTO rust_schema_version VALUES (?, 0, 'from a newer build')")
        .bind(tagdb_core::latest_rust_migration_version() + 1)
        .execute(&pool)
        .await
        .expect("insert");
    pool.close().await;

    let (code, text) = start(&db, None);
    assert_eq!(code, Some(65), "{text}");
    // The refusal, from tagdb-core.
    assert!(
        text.contains("written by a later version of yu-server"),
        "{text}"
    );
    // And the part that was missing: what to do about it on this machine.
    assert!(text.contains("To get a newer build here"), "{text}");
}
