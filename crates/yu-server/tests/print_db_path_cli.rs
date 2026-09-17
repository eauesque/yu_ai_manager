//! `--print-db-path` must answer with the path the server would actually open.
//!
//! The migration unit has to migrate the database the server opens. It cannot
//! work that out from a unit file: `--db` beats config's `db`, which beats
//! `YU_DB`, and a profile overrides all three. A unit that guessed migrated a
//! database nobody opened -- reported success, and the server still stopped at
//! 78 with the real database untouched.
//!
//! These run the real binary, because the point is the whole invocation
//! (argv + cwd + environment), not the resolver in isolation.

use std::process::Command;

fn print_db_path(dir: &std::path::Path, args: &[&str], env: &[(&str, &str)]) -> String {
    let exe = env!("CARGO_BIN_EXE_yu-server");
    let mut cmd = Command::new(exe);
    cmd.arg("--print-db-path")
        .args(args)
        .current_dir(dir)
        // Otherwise the operator's own ~/.config/yu/server.env is read and
        // decides the answer instead of this test.
        .env("YU_SKIP_DOTENV_FILES", "1")
        .env("YU_SKIP_LAUNCH_ARGS_FILE", "1")
        .env_remove("YU_DB")
        .env_remove("TAGDB_DB");
    for (key, value) in env {
        cmd.env(key, value);
    }
    let out = cmd.output().expect("run yu-server");
    assert!(
        out.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    String::from_utf8(out.stdout)
        .expect("utf8")
        .trim()
        .to_string()
}

#[test]
fn it_reports_the_path_and_creates_nothing() {
    let dir = tempfile::tempdir().expect("tempdir");
    let db = dir.path().join("named-on-argv.db");

    let answer = print_db_path(dir.path(), &["--db", db.to_str().expect("utf-8")], &[]);

    assert_eq!(answer, db.to_str().expect("utf-8"));
    // Reporting a path must not bring it into existence: the migration unit
    // runs this before the server has ever started.
    assert!(!db.exists(), "--print-db-path created the database");
}

#[test]
fn config_outranks_the_environment_and_the_answer_says_so() {
    // This is the whole reason the flag exists. The `--lan` unit passes no
    // `--db`, so config's `db` wins over YU_DB -- a unit that assumed YU_DB
    // would migrate the wrong file.
    let dir = tempfile::tempdir().expect("tempdir");
    std::fs::write(
        dir.path().join("config.json"),
        r#"{"db": "/from-config/tags.db"}"#,
    )
    .expect("write config");

    let answer = print_db_path(dir.path(), &[], &[("YU_DB", "/from-env/tags.db")]);
    assert_eq!(answer, "/from-config/tags.db");
}

#[test]
fn an_explicit_db_flag_outranks_config() {
    let dir = tempfile::tempdir().expect("tempdir");
    std::fs::write(
        dir.path().join("config.json"),
        r#"{"db": "/from-config/tags.db"}"#,
    )
    .expect("write config");

    let answer = print_db_path(dir.path(), &["--db", "/from-argv/tags.db"], &[]);
    assert_eq!(answer, "/from-argv/tags.db");
}

#[test]
fn the_answer_follows_the_working_directory() {
    // The caveat the README has to state: this reads config.json from the
    // current directory, so the query must run where the server runs.
    let with_config = tempfile::tempdir().expect("tempdir");
    std::fs::write(
        with_config.path().join("config.json"),
        r#"{"db": "/here/tags.db"}"#,
    )
    .expect("write config");
    let without_config = tempfile::tempdir().expect("tempdir");

    assert_eq!(print_db_path(with_config.path(), &[], &[]), "/here/tags.db");
    assert_ne!(
        print_db_path(without_config.path(), &[], &[]),
        "/here/tags.db",
        "the answer must depend on where it is asked"
    );
}

#[test]
fn the_lan_flag_does_not_change_the_answer() {
    // The `--lan` unit passes it; the query has to be able to include it
    // without changing what is reported.
    let dir = tempfile::tempdir().expect("tempdir");
    std::fs::write(
        dir.path().join("config.json"),
        r#"{"db": "/lan/tags.db", "server": {"pin": ""}}"#,
    )
    .expect("write config");

    assert_eq!(print_db_path(dir.path(), &["--lan"], &[]), "/lan/tags.db");
    assert_eq!(print_db_path(dir.path(), &[], &[]), "/lan/tags.db");
}
