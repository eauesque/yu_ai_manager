//! `--compat-info` must answer without touching the database. The launcher
//! calls it to decide whether a binary is usable, and at that moment the
//! database may be encrypted with a key the launcher has not passed.

use std::process::Command;

#[test]
fn compat_info_answers_without_a_database() {
    let exe = env!("CARGO_BIN_EXE_yu-server");
    let dir = tempfile::tempdir().expect("tempdir");

    // No tags.db here at all. A binary that opens the database would fail.
    // --standalone is required to reach the DB-touching code paths
    // (standalone_db_preflight / check_schema_version) at all; without it
    // this test cannot grip the ordering it claims to verify.
    let out = Command::new(exe)
        .arg("--compat-info")
        .arg("--standalone")
        .arg("--db")
        .arg(dir.path().join("definitely-absent.db"))
        .current_dir(dir.path())
        .output()
        .expect("run yu-server");

    assert!(
        out.status.success(),
        "stderr: {}",
        String::from_utf8_lossy(&out.stderr)
    );
    let text = String::from_utf8(out.stdout).expect("utf8");
    let parsed: serde_json::Value = serde_json::from_str(text.trim()).expect("one JSON line");
    assert!(parsed.get("python_schema_version").is_some());
}
