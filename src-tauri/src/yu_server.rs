use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[allow(unused_imports)]
use crate::log;

/// Find the yu-server binary adjacent to the current executable.
pub fn find_yu_server_bin() -> Option<PathBuf> {
    let exe_dir = std::env::current_exe().ok()?.parent()?.to_path_buf();
    let name = if cfg!(windows) {
        "yu-server.exe"
    } else {
        "yu-server"
    };
    let candidate = exe_dir.join(name);
    candidate.exists().then_some(candidate)
}

/// The application's SQLCipher key, matching `core/services_core/db_cipher.py`.
///
/// This is obfuscation at rest against a copied file, not a secret: it is
/// already hardcoded in the Python source, which ships with the application.
/// It lives here rather than in `crates/` on purpose --
/// `scripts/internal/sync_yu_server_mirror.sh` publishes `crates/` to a public
/// review repository, and a hardcoded key sitting in a crate meant to be read
/// on its own invites being mistaken for a security measure. yu-server itself
/// has no default: every launcher passes the key, and genesis refuses without
/// one.
const DB_KEY: &str = "yu-ai-manager-v1-cipher-2026";

fn resolve_db_path(project_root: &Path) -> PathBuf {
    let data_dir = crate::app_dirs::ensure_data_dir();
    let db_in_data = data_dir.as_ref().map(|d| d.join("tags.db"));
    if db_in_data.as_ref().is_some_and(|p| p.exists()) {
        db_in_data.unwrap()
    } else if project_root.join("tags.db").exists() {
        project_root.join("tags.db")
    } else if project_root.join("data/tags.db").exists() {
        project_root.join("data/tags.db")
    } else {
        db_in_data.unwrap_or_else(|| project_root.join("data/tags.db"))
    }
}

fn drain_output(child: &mut Child, log_path: &Path) {
    if let Some(stderr) = child.stderr.take() {
        let dest = log_path.to_path_buf();
        std::thread::Builder::new()
            .name("yu-server-stderr".into())
            .spawn(move || {
                BufReader::new(stderr).lines().for_each(|line| {
                    if let Ok(l) = line {
                        crate::logging::log_to_file(&dest, &format!("[yu-server] {}", l));
                    }
                });
            })
            .ok();
    }
    if let Some(stdout) = child.stdout.take() {
        let dest = log_path.to_path_buf();
        std::thread::Builder::new()
            .name("yu-server-stdout".into())
            .spawn(move || {
                BufReader::new(stdout).lines().for_each(|line| {
                    if let Ok(l) = line {
                        crate::logging::log_to_file(&dest, &format!("[yu-server] {}", l));
                    }
                });
            })
            .ok();
    }
}

/// Start yu-server in standalone mode on the given port.
pub fn start_yu_server(
    bin: &Path,
    project_root: &Path,
    port: u16,
    log_path: &Path,
) -> std::io::Result<Child> {
    let db_path = resolve_db_path(project_root);
    let data_dir = crate::app_dirs::ensure_data_dir();

    let mut cmd = Command::new(bin);
    cmd.current_dir(project_root)
        .arg("--db")
        .arg(&db_path)
        .arg("--db-key")
        .arg(DB_KEY)
        .arg("--host")
        .arg("127.0.0.1")
        .arg("--port")
        .arg(port.to_string())
        .arg("--standalone")
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(ref dd) = data_dir {
        cmd.env("TAGDB_DATA_DIR", dd.join("data"))
            .env("TAGDB_CACHE_DIR", dd.join("cache"))
            .env("TAGDB_LOG_DIR", dd.join("logs"))
            .env("TAGDB_PROFILES_DIR", dd.join("profiles"));
    }

    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn()?;
    drain_output(&mut child, log_path);
    Ok(child)
}

/// Outcome of an attempt to run in fast mode (bundled yu-server), decided
/// after both the spawn attempt and the readiness wait.
///
/// This is extracted out of `main.rs`'s inline branching so the actual
/// fast-mode-vs-Python-mode decision -- not just `start_yu_server`'s
/// `Result` type -- can be unit tested without spawning a process or
/// running the full Tauri app (which this crate cannot compile/test in a
/// sandboxed CI-less environment; `main.rs` is a binary-only entry point).
/// `main.rs` routes strictly through this function's answer: it must not
/// independently call `show_error_and_exit` when `spawn_succeeded` is
/// `false` or `became_ready` is `false`.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FastModeOutcome {
    UseYuServer,
    DegradeToPython,
}

/// How the readiness wait ended.
///
/// `Exited` is the case the old bool could not express. yu-server refuses a
/// database it cannot use within a fraction of a second, and a port-polling
/// wait cannot tell "died immediately" from "still starting" -- so the app sat
/// through the full timeout before degrading, every time, and the exit code
/// (78 = the database needs migrating, which the Python path then performs)
/// was thrown away along with it.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum ReadinessOutcome {
    Ready,
    /// The child exited before the port opened, with this status code (`None`
    /// when it was killed by a signal).
    Exited(Option<i32>),
    TimedOut,
}

/// yu-server's exit code for "the database is older than this build and
/// something else must migrate it".
///
/// Mirrors `EXIT_DB_SCHEMA_BEHIND` in `crates/yu-server/src/main.rs`. The
/// desktop app degrades to Python on it exactly like the shell launchers do --
/// Python owns the migration chain -- but it is worth naming so the log says
/// what happened instead of reporting a generic failure.
pub const EXIT_DB_SCHEMA_BEHIND: i32 = 78;

/// yu-server's exit code for "this database was written by a NEWER build".
///
/// Mirrors `EXIT_DB_RUST_SCHEMA_AHEAD` in `crates/yu-server/src/main.rs`.
///
/// The opposite of 78 in every way that matters. 78 has a repair the app
/// performs by itself -- Python owns the migration chain and runs it on the way
/// past. 65 has none: no migration runs backwards, so the app degrades to
/// Python and *stays* degraded, silently and for good, which is precisely what
/// the comment on `EXIT_DB_RUST_SCHEMA_AHEAD` forbids the launchers from doing.
///
/// The desktop keeps the degradation anyway, deliberately, and that exception
/// is written down at the constant in yu-server so the two decisions stop
/// contradicting each other: a shell launcher that stops leaves the operator a
/// message, while an app that refuses to open leaves a user with nothing they
/// can act on. What was missing was not the refusal -- it was telling them.
pub const EXIT_DB_RUST_SCHEMA_AHEAD: i32 = 65;

/// What to show the user when the desktop app degrades, or `None` when the
/// outcome needs no explanation beyond the log.
///
/// Only 65 qualifies. Every other degradation either repairs itself on this
/// same launch (78) or is a transient failure that the Python path hides
/// successfully; 65 is the one where the app keeps running on the slower path
/// **permanently** and nothing on screen would ever say so.
///
/// Returns the text rather than showing it, so the decision can be tested
/// without a window manager.
pub fn desktop_degradation_notice(outcome: &ReadinessOutcome) -> Option<String> {
    match outcome {
        ReadinessOutcome::Exited(Some(EXIT_DB_RUST_SCHEMA_AHEAD)) => Some(
            "このデータベースは、より新しい版の YU AI Manager が書き込んだものです。\n             アプリは起動しますが、高速な yu-server は使えず、低速な Python 経路で\n             動き続けます。移行は後ろへは進まないため、この状態は自動では直りません。\n             \n             直すには、次のいずれかを行ってください:\n             \u{20} ・ より新しい版の YU AI Manager を入れ直す（推奨）\n             \u{20} ・ 以前の版で作ったバックアップを復元する\n             \n             詳細は次の記録にあります:"
                .to_string(),
        ),
        _ => None,
    }
}

/// Describe a readiness outcome for the log and, when the Python path is not
/// available either, for the error the user sees.
pub fn describe_readiness(outcome: &ReadinessOutcome, timeout_secs: u64) -> String {
    match outcome {
        ReadinessOutcome::Ready => "yu-server は起動しました".to_string(),
        ReadinessOutcome::Exited(Some(EXIT_DB_SCHEMA_BEHIND)) => format!(
            "yu-server はデータベースの移行が必要なため終了しました (終了コード {EXIT_DB_SCHEMA_BEHIND})。\
             移行は Python 版が行います。"
        ),
        ReadinessOutcome::Exited(Some(EXIT_DB_RUST_SCHEMA_AHEAD)) => format!(
            "yu-server は、このデータベースがより新しい版で書かれているため終了しました              (終了コード {EXIT_DB_RUST_SCHEMA_AHEAD})。移行は後ろへ進まないため、             Python 経路での動作が続きます。"
        ),
        ReadinessOutcome::Exited(Some(code)) => {
            format!("yu-server は起動に失敗して終了しました (終了コード {code})")
        }
        ReadinessOutcome::Exited(None) => {
            "yu-server はシグナルで終了しました".to_string()
        }
        ReadinessOutcome::TimedOut => {
            format!("yu-server が {timeout_secs} 秒以内に起動しませんでした")
        }
    }
}

pub fn decide_fast_mode_outcome(spawn_succeeded: bool, became_ready: bool) -> FastModeOutcome {
    if spawn_succeeded && became_ready {
        FastModeOutcome::UseYuServer
    } else {
        FastModeOutcome::DegradeToPython
    }
}

/// Wait for the port to open **or** the child to exit, whichever comes first.
///
/// The old wait only polled the port, so a child that refused the database and
/// exited in 0.2s still cost the full timeout before the app degraded. Polling
/// the child as well turns that into an immediate answer and preserves the
/// exit code, which is the only thing that distinguishes "the database needs
/// migrating" from "the binary is broken".
pub fn wait_for_server_or_exit(
    port: u16,
    timeout: std::time::Duration,
    child: &mut std::process::Child,
) -> ReadinessOutcome {
    let start = std::time::Instant::now();
    while start.elapsed() < timeout {
        if std::net::TcpListener::bind(("127.0.0.1", port)).is_err() {
            return ReadinessOutcome::Ready;
        }
        // Checked after the port, not before: a server that bound the port and
        // then exited in the same tick should still count as having started.
        match child.try_wait() {
            Ok(Some(status)) => return ReadinessOutcome::Exited(status.code()),
            Ok(None) => {}
            // try_wait failing means the handle is unusable; the port poll
            // above is still meaningful, so keep waiting rather than guessing.
            Err(_) => {}
        }
        std::thread::sleep(std::time::Duration::from_millis(100));
    }
    ReadinessOutcome::TimedOut
}

#[cfg(test)]
mod fallback_tests {
    use super::*;

    /// A database older than the bundled binary is the one refusal the Python
    /// path repairs, so the message must name it rather than reporting a
    /// generic failure. Before the child's exit code was observed at all, this
    /// case was indistinguishable from "the binary is broken" -- and cost the
    /// full 30 second timeout to reach.
    /// The desktop keeps degrading on a binary downgrade, which
    /// `EXIT_DB_RUST_SCHEMA_AHEAD` in yu-server forbids the launchers from
    /// doing. The exception is only tolerable while the degradation is
    /// announced -- these pin the announcement, because without it the
    /// exception becomes the quiet permanent downgrade that comment forbids.
    #[test]
    fn a_binary_downgrade_is_announced_with_its_repair() {
        let notice =
            desktop_degradation_notice(&ReadinessOutcome::Exited(Some(EXIT_DB_RUST_SCHEMA_AHEAD)))
                .expect("65 must be announced");

        // What happened, in terms a user can act on.
        assert!(notice.contains("より新しい版"), "{notice}");
        // That it will not fix itself -- the whole reason to interrupt them.
        assert!(notice.contains("自動では直りません"), "{notice}");
        // And both repairs, neither of which the app can perform.
        assert!(notice.contains("入れ直す"), "{notice}");
        assert!(notice.contains("バックアップを復元"), "{notice}");
        // It must not claim the app is broken: it is running, just slower.
        assert!(notice.contains("アプリは起動します"), "{notice}");
    }

    #[test]
    fn nothing_else_interrupts_the_user() {
        // A dialog on every transient degradation trains people to dismiss the
        // one that matters. 78 repairs itself on this same launch; a timeout or
        // a signal is a failure the Python path hides successfully.
        for outcome in [
            ReadinessOutcome::Ready,
            ReadinessOutcome::TimedOut,
            ReadinessOutcome::Exited(None),
            ReadinessOutcome::Exited(Some(EXIT_DB_SCHEMA_BEHIND)),
            ReadinessOutcome::Exited(Some(1)),
            ReadinessOutcome::Exited(Some(127)),
        ] {
            assert!(
                desktop_degradation_notice(&outcome).is_none(),
                "{outcome:?} must not raise a dialog"
            );
        }
    }

    #[test]
    fn the_downgrade_still_degrades_rather_than_refusing_to_open() {
        // The decision the user made: keep the degradation, add the notice.
        // A refusal here would leave them with an app that does not open.
        assert_eq!(
            decide_fast_mode_outcome(true, false),
            FastModeOutcome::DegradeToPython
        );
        let described = describe_readiness(
            &ReadinessOutcome::Exited(Some(EXIT_DB_RUST_SCHEMA_AHEAD)),
            30,
        );
        assert!(described.contains("より新しい版"), "{described}");
        assert!(
            described.contains(&EXIT_DB_RUST_SCHEMA_AHEAD.to_string()),
            "{described}"
        );
    }

    #[test]
    fn the_two_schema_codes_are_not_confused_with_each_other() {
        // Opposite repairs: 78 is performed by the Python path this very
        // launch, 65 can only be repaired by a human with a newer build.
        assert_ne!(EXIT_DB_SCHEMA_BEHIND, EXIT_DB_RUST_SCHEMA_AHEAD);
        let behind = describe_readiness(&ReadinessOutcome::Exited(Some(EXIT_DB_SCHEMA_BEHIND)), 30);
        let ahead = describe_readiness(
            &ReadinessOutcome::Exited(Some(EXIT_DB_RUST_SCHEMA_AHEAD)),
            30,
        );
        assert!(behind.contains("移行は Python 版が行います"), "{behind}");
        assert!(!ahead.contains("移行は Python 版が行います"), "{ahead}");
    }

    #[test]
    fn the_migration_exit_code_is_described_as_a_migration() {
        let text = describe_readiness(&ReadinessOutcome::Exited(Some(EXIT_DB_SCHEMA_BEHIND)), 30);
        assert!(text.contains("移行"), "{text}");
        assert!(text.contains(&EXIT_DB_SCHEMA_BEHIND.to_string()), "{text}");
    }

    #[test]
    fn other_outcomes_do_not_claim_a_migration_is_needed() {
        // The whole point of reading the code is that 78 and 1 stop being the
        // same event. If every branch said "migration" the distinction would
        // be decorative.
        for outcome in [
            ReadinessOutcome::Exited(Some(1)),
            ReadinessOutcome::Exited(None),
            ReadinessOutcome::TimedOut,
            ReadinessOutcome::Ready,
        ] {
            let text = describe_readiness(&outcome, 30);
            assert!(
                !text.contains("移行"),
                "{outcome:?} must not be reported as a migration: {text}"
            );
        }
    }

    #[test]
    fn the_timeout_message_names_the_budget_it_spent() {
        let text = describe_readiness(&ReadinessOutcome::TimedOut, 30);
        assert!(text.contains("30"), "{text}");
    }

    #[test]
    fn a_child_that_exits_ends_the_wait_without_spending_the_timeout() {
        // The defect this pins: the old wait polled only the port, so a
        // yu-server that exited in 0.2s still cost the whole timeout. A
        // generous budget here would pass even with that bug, so the
        // assertion is on elapsed time, not just the verdict.
        let mut child = std::process::Command::new(if cfg!(windows) { "cmd" } else { "sh" })
            .args(if cfg!(windows) {
                vec!["/C", "exit 78"]
            } else {
                vec!["-c", "exit 78"]
            })
            .spawn()
            .expect("spawn a process that exits immediately");
        // A port nothing is listening on, so only the child can end the wait.
        let port = std::net::TcpListener::bind("127.0.0.1:0")
            .expect("bind")
            .local_addr()
            .expect("addr")
            .port();

        let start = std::time::Instant::now();
        let outcome = wait_for_server_or_exit(port, std::time::Duration::from_secs(30), &mut child);
        let elapsed = start.elapsed();

        assert_eq!(outcome, ReadinessOutcome::Exited(Some(78)));
        assert!(
            elapsed < std::time::Duration::from_secs(5),
            "the wait must end when the child does, not after the timeout: {elapsed:?}"
        );
    }

    /// Starting yu-server can fail for reasons the user cannot act on -- a
    /// schema the bundled binary does not know, a port already taken. Before
    /// fast mode those were rare; bundling a binary makes them ordinary. The
    /// app must degrade to Python, not refuse to open.
    #[test]
    fn a_failed_start_is_recoverable_not_fatal() {
        let missing = std::path::Path::new("/definitely/not/a/binary");
        let log_path = std::env::temp_dir().join("yu_server_fallback_test.log");
        let result = start_yu_server(missing, std::path::Path::new("."), 0, &log_path);
        assert!(
            result.is_err(),
            "a missing binary must report an error, not panic"
        );
    }

    /// build.rs writes a placeholder in place of yu-server.exe so that Tauri's
    /// resource validation passes before prepare-tauri-bundle.py has run. If
    /// that placeholder is ever the file that ends up shipped (bundling step
    /// skipped), find_yu_server_bin() still finds it -- it has the right name
    /// and location -- but it is not a valid executable, so spawning it must
    /// fail the same way a missing binary does, and degrade rather than panic
    /// or hang.
    #[test]
    fn a_placeholder_binary_is_recoverable_not_fatal() {
        let path =
            std::env::temp_dir().join(format!("yu_server_placeholder_test_{}", std::process::id()));
        std::fs::write(&path, b"YU_AI_MANAGER_PLACEHOLDER_NOT_A_REAL_BINARY\n").unwrap();
        #[cfg(unix)]
        {
            use std::os::unix::fs::PermissionsExt;
            let mut perms = std::fs::metadata(&path).unwrap().permissions();
            perms.set_mode(0o755);
            std::fs::set_permissions(&path, perms).unwrap();
        }

        let log_path = std::env::temp_dir().join("yu_server_placeholder_test.log");
        let result = start_yu_server(&path, std::path::Path::new("."), 0, &log_path);

        let _ = std::fs::remove_file(&path);
        assert!(
            result.is_err(),
            "a placeholder file with no valid executable format must report an error, not panic"
        );
    }

    /// `a_failed_start_is_recoverable_not_fatal` and
    /// `a_placeholder_binary_is_recoverable_not_fatal` only pin
    /// `start_yu_server`'s `Result` type; neither exercises `main.rs`'s
    /// branching. The two tests below pin `decide_fast_mode_outcome`'s truth
    /// table -- they prove the pure function returns the right
    /// `FastModeOutcome` for each (spawn_succeeded, became_ready) pair.
    ///
    /// They do NOT pin what `main.rs` does with that answer. `main.rs` is a
    /// binary-only crate this isolated harness cannot load (no `[lib]`
    /// target, and `src-tauri` cannot be compiled at all in this sandbox --
    /// see prepare-tauri-bundle.py's staging comment), so its `match` arms
    /// could be replaced -- e.g. the `DegradeToPython` arm swapped for
    /// `logging::show_error_and_exit(...)` -- without failing any test in
    /// this module. The reviewer demonstrated exactly that gap. It is
    /// covered separately, not here, by the source-scan test
    /// `test_main_rs_degrade_to_python_arm_falls_through_without_exiting` in
    /// tests/test_prepare_tauri_bundle.py, which reads main.rs as text and
    /// asserts the `DegradeToPython` arm contains neither an exit call nor a
    /// `return`. That test only catches arm replacement/deletion at the text
    /// level; it cannot catch a meaning-changing rewrite that keeps the same
    /// surface tokens.
    #[test]
    fn degrades_to_python_when_spawn_fails() {
        assert_eq!(
            decide_fast_mode_outcome(false, false),
            FastModeOutcome::DegradeToPython
        );
    }

    #[test]
    fn degrades_to_python_when_spawn_succeeds_but_never_becomes_ready() {
        assert_eq!(
            decide_fast_mode_outcome(true, false),
            FastModeOutcome::DegradeToPython
        );
    }

    #[test]
    fn uses_yu_server_when_spawn_succeeds_and_becomes_ready() {
        assert_eq!(
            decide_fast_mode_outcome(true, true),
            FastModeOutcome::UseYuServer
        );
    }
}
