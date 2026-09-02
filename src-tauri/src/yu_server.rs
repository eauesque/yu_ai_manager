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

fn resolve_db_path(project_root: &Path) -> PathBuf {    let data_dir = crate::app_dirs::ensure_data_dir();
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

pub fn decide_fast_mode_outcome(spawn_succeeded: bool, became_ready: bool) -> FastModeOutcome {
    if spawn_succeeded && became_ready {
        FastModeOutcome::UseYuServer
    } else {
        FastModeOutcome::DegradeToPython
    }
}

#[cfg(test)]
mod fallback_tests {
    use super::*;

    /// Starting yu-server can fail for reasons the user cannot act on -- a
    /// schema the bundled binary does not know, a port already taken. Before
    /// fast mode those were rare; bundling a binary makes them ordinary. The
    /// app must degrade to Python, not refuse to open.
    #[test]
    fn a_failed_start_is_recoverable_not_fatal() {
        let missing = std::path::Path::new("/definitely/not/a/binary");
        let log_path = std::env::temp_dir().join("yu_server_fallback_test.log");
        let result = start_yu_server(missing, std::path::Path::new("."), 0, &log_path);
        assert!(result.is_err(), "a missing binary must report an error, not panic");
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
        let path = std::env::temp_dir().join(format!(
            "yu_server_placeholder_test_{}",
            std::process::id()
        ));
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
