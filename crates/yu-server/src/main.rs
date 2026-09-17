#![allow(
    dead_code,
    unexpected_cfgs,
    unused_imports,
    unused_must_use,
    unused_mut,
    unused_variables
)]
// Structurally accepted clippy lints (2026-08-11 決定). These are not deferred
// work: each was evaluated and kept. Everything else in this crate is expected
// to be clippy-clean, so a new warning here is a real finding.
//
// - result_large_err: 8 sites, all `Result<T, Response>`. axum's `Response`
//   exceeds the 128-byte threshold by construction. This is the crate-wide
//   idiom for early-return inside handlers; boxing the error would break every
//   `?` at the call sites and buy nothing — the value is returned, not stored.
// - await_holding_lock: 7 sites, all inside `#[cfg(test)]`. They hold a
//   process-global seam lock (`ENV_MUTATION_TEST_LOCK`, the hailo registry
//   guards) across await to serialize env mutation while tests run in parallel
//   threads. Same call as `crates/lan-cowork/src/lib.rs` made for its own seam
//   lock; the lint cannot reach production code here.
// - too_many_arguments / type_complexity: handler signatures are dictated by
//   axum extractors; splitting them would hide the wiring rather than simplify it.
#![allow(
    clippy::result_large_err,
    clippy::await_holding_lock,
    clippy::too_many_arguments,
    clippy::type_complexity
)]

mod analysis_engines;
mod approval_gate;
mod auth;
mod compat_info;
mod config_io;
mod config_migrate;
mod csrf;
mod db_backup;
mod ext_config;
mod frontend;
mod groups_index;
mod infer_auth;
mod infer_client;
mod infer_manager;
mod jobs;
mod logs;
mod main_env_order_guard;
mod mcp;
mod num;
#[cfg(feature = "ocr")]
mod ocr;
mod pages;
mod pages_boss;
mod paths;
mod rate_limit_layer_order_guard;
mod tagger_batch;
mod tagger_peer_client;
mod work_steal;
pub(crate) use ::lan_cowork::path_guard;
mod prompt_sim_core;
mod restart;
mod routes;
mod scan_archive;
mod scan_manager;
mod scan_native;
mod scan_queue;
mod scheduler;
mod sd_nai;
mod secret_store;
mod security;
mod sse;
mod state;
#[cfg(test)]
mod testing;
mod watcher;
mod wd_profile_wire;

/// Guards every test in this crate that mutates a process-global env var
/// (`HOME`, `HAILO_HEF_DIR`, etc.) -- the default parallel test-execution
/// mode runs all unit tests in one process, so any two such tests
/// can race unless they share ONE lock, regardless of which module or
/// feature area they belong to. Poison-recovery via `unwrap_or_else` so
/// one panicking test can't cascade-fail the rest.
#[cfg(test)]
pub(crate) static ENV_MUTATION_TEST_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

use std::collections::HashSet;
use std::net::{IpAddr, SocketAddr};
use std::path::{Path, PathBuf};
use std::sync::Arc;

use tracing_subscriber::{layer::SubscriberExt, util::SubscriberInitExt, Layer};

use axum::{
    middleware,
    routing::{any, delete, get, post, put},
    Router,
};
use clap::Parser;
use tower_http::services::ServeDir;
use tower_sessions::{MemoryStore, SessionManagerLayer};

use auth::middleware::auth_middleware;
use auth::routes::{
    get_auth_status, get_lock_status, get_pin_page, post_auth_logout, post_lock_activate,
    post_lock_unlock, post_pin_check,
};
use auth::{hash_pin, make_token};
use state::{AppState, Config, SharedState};

#[derive(Parser)]
#[command(name = "yu-server", about = "yu image manager auth server")]
struct Cli {
    #[arg(long, default_value = "127.0.0.1", env = "YU_HOST")]
    host: String,
    #[arg(long, default_value_t = 5000, env = "YU_PORT")]
    port: u16,
    /// Bind to 0.0.0.0 (LAN access; --pin required).
    #[arg(long)]
    lan: bool,
    #[arg(long, env = "YU_PIN")]
    pin: Option<String>,
    #[arg(long, env = "YU_SECRET", default_value = "default-secret")]
    secret: String,
    #[arg(long)]
    trusted_proxy_auth: bool,
    /// Comma-separated trusted proxy IPs/CIDRs.
    #[arg(long, env = "YU_TRUSTED_IPS", default_value = "")]
    trusted_ips: String,
    /// Comma-separated trusted peer IPs/CIDRs (for /ext/<name>/v1/ routes).
    #[arg(long, env = "YU_TRUSTED_PEER_IPS", default_value = "")]
    trusted_peer_ips: String,
    #[arg(long, default_value_t = false)]
    no_quick_lock: bool,
    #[arg(long, env = "YU_DB", default_value = "data/tags.db")]
    db: String,
    #[arg(long, env = "YU_DB_KEY", default_value = "")]
    db_key: String,
    /// Python backend URL for unimplemented route fallback.
    /// Leave empty to disable the Python fallback proxy.
    #[arg(long, env = "YU_PYTHON_URL", default_value = "")]
    python_url: String,
    /// Config JSON path, matching Python --config / YU_CONFIG.
    #[arg(long, env = "YU_CONFIG")]
    config: Option<PathBuf>,
    /// Repository root containing ui/default/templates. Defaults to the
    /// current working directory. Set YU_PROJECT_ROOT when running the
    /// binary from a directory other than the repo root.
    #[arg(long, env = "YU_PROJECT_ROOT")]
    project_root: Option<PathBuf>,
    /// Server mode: full | gateway | server (default: full).
    /// env: TAGDB_MODE は Config 構築側で読むため clap env 属性なし
    #[arg(long)]
    mode: Option<String>,
    /// Start in headless mode (no browser-accessible UI).
    /// env: TAGDB_HEADLESS は env_truthy で読むため clap env 属性なし
    #[arg(long)]
    headless: bool,
    /// Start in safe mode (no destructive operations).
    #[arg(long)]
    safe_mode: bool,
    /// Start in standalone mode without the Python backend.
    /// env: YU_STANDALONE is read with env_truthy during Config construction.
    #[arg(long)]
    standalone: bool,
    /// Explicitly opt in to the native LAN Cowork discovery daemon. Requires
    /// --standalone; YU_LAN_COWORK_NATIVE_DAEMON is read with env_truthy.
    #[arg(long)]
    native_daemon: bool,
    /// Explicitly disable the native LAN Cowork discovery daemon.
    #[arg(long)]
    no_native_daemon: bool,
    /// Activate a named profile (overrides db path and merges config settings).
    #[arg(long, env = "YU_PROFILE")]
    profile: Option<String>,
    /// Python 実行ファイルパス（scan worker 起動用）。
    /// Windows では python3 が存在しない場合があるため env で上書き可能。
    #[arg(long, env = "YU_PYTHON_EXECUTABLE", default_value_t = default_python_executable())]
    python_executable: String,
    /// Print machine-readable compatibility information and exit.
    /// The launcher uses this to decide whether this binary may be used,
    /// without opening the database.
    #[arg(long)]
    compat_info: bool,

    /// Print the database path this invocation resolves to, then exit.
    ///
    /// The migration unit has to migrate the database the *server* will open,
    /// and it cannot work that out for itself: `--db` beats config's `db`,
    /// which beats `YU_DB`, and a profile can override all three. Guessing at
    /// that in a unit file means migrating a database nobody opens -- the
    /// migration reports success and the server still stops at 78.
    ///
    /// Answered by the same `resolve_db_path` the server uses, so there is no
    /// second resolver to drift. The answer depends on the whole invocation:
    /// give this the same working directory, argv and environment as the
    /// server, or it answers a different question.
    #[arg(long)]
    print_db_path: bool,
}

/// Windows commonly lacks a `python3` binary, so fall back to "python" there
/// (same default as src-tauri/flask_python.rs::find_python).
fn default_python_executable() -> String {
    if cfg!(target_os = "windows") {
        "python".to_string()
    } else {
        "python3".to_string()
    }
}

fn env_truthy(name: &str) -> bool {
    let raw = std::env::var(name).unwrap_or_default();
    let lower = raw.trim().to_lowercase();
    matches!(lower.as_str(), "1" | "true" | "yes")
}

/// Like env_truthy but defaults to true when the variable is unset or empty.
/// Set to "0", "false", or "no" to disable.
fn env_default_true(name: &str) -> bool {
    let raw = std::env::var(name).unwrap_or_default();
    let lower = raw.trim().to_lowercase();
    !matches!(lower.as_str(), "0" | "false" | "no")
}

fn is_loopback_host(host: &str) -> bool {
    let host = host.trim().trim_matches(['[', ']']);
    host.eq_ignore_ascii_case("localhost")
        || matches!(host.parse::<IpAddr>(), Ok(address) if address.is_loopback())
}

fn parse_ip_set(s: &str) -> HashSet<String> {
    s.split(',')
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(String::from)
        .collect()
}

/// Mirror Python: resolve_profile_config() — merge a named profile into config.
/// Create the database if standalone needs one. The version gate is separate:
/// see [`db_version_gate`].
///
/// Ordering matters twice over. It runs before the pools because the read-only
/// pool opens with `create_if_missing(false)`, and it runs before
/// `apply_standalone_schema` / `ensure_local_identity` / the Rust migrations,
/// all of which write.
///
/// Only standalone reaches here. Hybrid never creates a database -- Python owns
/// creation there -- so there is nothing for this to do.
async fn standalone_genesis(
    db_path: &str,
    db_key: &str,
    profile_requested_but_missing: bool,
) -> Result<(), PreflightRefusal> {
    // A SQLite URI has no parent to check and no file to claim. Leave it to the
    // normal open path.
    if tagdb_core::is_sqlite_uri(db_path) {
        return Ok(());
    }

    if !Path::new(db_path).exists() {
        if profile_requested_but_missing {
            return Err(PreflightRefusal::fatal(format!(
                "refusing to create a database: the requested profile was not found, so the \
                 path fell back to the default ({db_path}). Creating one here would look \
                 exactly like losing your library. Check the profile name."
            )));
        }
        if db_key.is_empty() {
            return Err(PreflightRefusal::fatal(format!(
                "refusing to create a database at {db_path} without --db-key (or YU_DB_KEY).\n\
                 The Python version opens tags.db through SQLCipher unconditionally, so an \
                 unencrypted database created here could never be opened by it again.\n\
                 The launcher is expected to supply the key."
            )));
        }
        // A key this binary accepts but Python refuses creates a database
        // that the migration CLI can never open -- and that CLI is the only
        // migrator there is, so the deployment would stop at the version gate
        // forever. Refuse here, where nothing has been written yet and the
        // remedy is to generate another key.
        if let Err(reason) = tagdb_core::validate_db_key(db_key) {
            return Err(PreflightRefusal::fatal(format!(
                "refusing to create a database at {db_path}: {reason}.\n\
                 The Python migration CLI enforces the same rule \
                 (core/services_core/db_cipher.py), and it is the only migrator \
                 there is: a database created with this key could never be \
                 migrated. Generate one with: openssl rand -hex 32"
            )));
        }
        match tagdb_core::create_fresh_database(db_path, db_key).await {
            Ok(tagdb_core::GenesisOutcome::Created) => {
                tracing::info!("created a new database at {db_path}");
                return Ok(());
            }
            // Another process won the race and has, or is building, a database.
            // The version gate below sees whatever it produced.
            Ok(tagdb_core::GenesisOutcome::Skipped) => {}
            Err(err) => return Err(PreflightRefusal::fatal(format!("{err}"))),
        }
    }

    // The version gate is no longer part of this function: it runs for every
    // mode, not just standalone. See db_version_gate.
    Ok(())
}

/// Warn when the running key is one the Python migration CLI would refuse.
///
/// Deliberately a warning and not a refusal. Such a database already exists and
/// already cannot be migrated; refusing to start would take a working server
/// down and fix nothing. Genesis is where this is fatal, because there the
/// remedy still exists.
///
/// An empty key is not a violation here -- it means a plaintext database or
/// hybrid mode, both legitimate -- so it is skipped rather than passed to a
/// validator that rejects it.
fn warn_if_the_key_is_one_python_would_refuse(db_key: &str) {
    if db_key.is_empty() {
        return;
    }
    if let Err(reason) = tagdb_core::validate_db_key(db_key) {
        // The reason names character classes, never the key itself.
        tracing::warn!(
            "the database key {reason}. The Python migration CLI enforces this \
             rule and would refuse it, so this database cannot be migrated by \
             `uv run python scripts/migrate_db_cli.py`. Serving continues; \
             migrating will require re-keying the database first."
        );
    }
}

/// Read `MAX(schema_version.version)` out of the database without modifying it.
///
/// The error string is the operator-facing sentence for "the version could not
/// be read at all", which both the standalone gate and the hybrid warning
/// report verbatim.
async fn read_schema_version(db_path: &str, db_key: &str) -> Result<i64, String> {
    let pool = if db_key.is_empty() {
        tagdb_core::connect_readonly(db_path).await
    } else {
        tagdb_core::connect_encrypted_readonly(db_path, db_key)
            .await
            .map_err(tagdb_core::TagdbError::Db)
    };
    let pool = match pool {
        Ok(pool) => pool,
        Err(err) => {
            // Only one thing is certain here: whether a key was supplied at
            // all. Do not assert the database is encrypted -- a corrupt
            // plaintext file, a permission error and an IO error all land in
            // this same branch. Name the missing input, offer the likely
            // cause, and keep the other causes on the list.
            //
            // Measured 2026-09-10: an encrypted database opened with no key
            // fails HERE, at connect, with "(code: 26) file is not a database"
            // -- connect_readonly sets synchronous=NORMAL, which needs the
            // schema. With a key it establishes and fails at the SELECT below
            // instead, which is why only this branch names the key.
            let cause = if db_key.is_empty() {
                "No key was supplied (--db-key or YU_DB_KEY). If this database is \
                 encrypted, that is the cause; it may also be damaged, unreadable, \
                 or denied by file permissions."
            } else {
                "The database may be encrypted with a different key, damaged, or \
                 denied by file permissions."
            };
            return Err(format!(
                "cannot read the schema version of {db_path}: {err}\n\
                 {cause} Nothing has been modified."
            ));
        }
    };

    // `SELECT version` would return an arbitrary one of the ~90 rows: the table
    // records every applied migration, not just the current one.
    let found: Result<Option<i64>, _> =
        sqlx::query_scalar("SELECT MAX(version) FROM schema_version")
            .fetch_one(&pool)
            .await;
    pool.close().await;

    match found {
        Ok(Some(version)) => Ok(version),
        Ok(None) | Err(_) => Err(format!(
            "cannot determine the schema version of {db_path}: the schema_version table is \
             missing or unreadable.\n\
             This does not look like a yu database. Nothing has been modified."
        )),
    }
}

/// Whether something has declared a Python backend that owns the migration
/// chain and will bring a stale database up.
///
/// `standalone` wins over the URL on purpose. `--standalone` is an explicit
/// assertion that no Python is present; `python_url` also arrives from the
/// environment (`clap`'s `env = "YU_PYTHON_URL"`), and `load_dotenv_files`
/// injects that from `~/.config/yu/server.env` with `set_var` *before* clap
/// parses. Without the `!standalone` term, one line in that file would flip
/// every launcher path -- all of which pass `--standalone` -- from refusing a
/// stale database to serving it. The same precedence already exists below,
/// where `Config::python_url` is forced empty in standalone.
/// Why this launch does or does not have a migrator it can believe in.
///
/// One function rather than a bool and a separate warning: the reason was
/// being recomputed at the call site, which is how a message and the decision
/// it explains drift apart.
///
/// The strings are operator-facing and appear in `server-info`, so they say
/// what is true of *this* launch, not which branch of the code ran.
fn migrator_declaration_reason(standalone: bool, python_url: &str, db_key: &str) -> &'static str {
    if !cfg!(feature = "python-backend") {
        return "this build has no Python backend compiled in";
    }
    if standalone {
        return "started with --standalone";
    }
    if python_url.is_empty() {
        return "no Python backend URL was given";
    }
    if !db_key.is_empty() && db_key != tagdb_core::PYTHON_BUILTIN_DB_KEY {
        return "the Python server cannot open a database with an operator-supplied key";
    }
    "a Python backend is declared and can open this database"
}

fn migrator_declared(standalone: bool, python_url: &str, db_key: &str) -> bool {
    // A build without the `python-backend` feature cannot reach a Python
    // backend at all: every forwarding route is compiled out and answers 503
    // (`routes/auto_stubs.rs`). So a declaration is false by construction
    // here, and trusting it would serve a stale database on the strength of a
    // migrator that this binary could not call even if it were running --
    // exactly the silent wrong answer the version gate exists to prevent.
    //
    // Checked at compile time rather than probed: the answer cannot change at
    // runtime, so this costs nothing and cannot misfire on a slow-starting
    // Python (a liveness probe would).
    if !cfg!(feature = "python-backend") {
        return false;
    }
    // The same question, asked of the key. Python's server opens every
    // connection with its built-in key and reads no environment variable, so
    // a deployment with an operator-generated key has a Python that cannot
    // open *this* database -- reachable, healthy, and useless as a migrator.
    // Trusting the declaration there serves a stale database on the strength
    // of a migration that can never run.
    //
    // An empty key means a plaintext database, which Python opens through the
    // same call; only a non-empty key that is not Python's own is fatal here.
    if !db_key.is_empty() && db_key != tagdb_core::PYTHON_BUILTIN_DB_KEY {
        return false;
    }
    !standalone && !python_url.is_empty()
}

/// Which side of the expected version the database sits on.
///
/// Carried out of [`schema_version_verdict`] as a value rather than left to be
/// recovered from the message, because the caller picks the process exit code
/// from it and the messages are a contract surface the acceptance gate matches
/// on (see the note in the function body). A predicate that reads its own
/// error prose is one reword away from silently inverting.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum SchemaDrift {
    /// The database is older than this build. Python's migration chain can
    /// bring it up, so the launchers fall back to the Python path on this.
    Behind,
    /// The database is newer than this build. Python cannot undo a migration,
    /// so falling back would loop forever -- this stays a plain failure.
    Ahead,
}

/// The single comparison behind every caller of the version gate.
/// `None` means the database is at the version this build was made for.
///
/// `refusing` only picks the remediation sentence: true when the caller is
/// about to exit, false when it will warn and carry on. It is NOT the
/// standalone flag -- a hybrid launch with no declared migrator refuses too,
/// and the refusing wording must therefore not claim this process is
/// standalone or that a launcher is watching its exit code. The verdict
/// itself -- which versions are a mismatch -- must not depend on it, or
/// callers would disagree about the same database.
fn schema_version_verdict(
    version: i64,
    db_path: &str,
    refusing: bool,
) -> Option<(SchemaDrift, String)> {
    let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
    if version == expected {
        return None;
    }
    // The two opening sentences are the wording `check_genesis_acceptance.py`
    // matches on ("newer than this build" for the ahead case). Keep them
    // verbatim: collapsing both directions into one sentence reads tidier and
    // silently breaks that gate.
    let (drift, headline, remedy) = if version < expected {
        let remedy = if refusing {
            format!(
                "This build cannot migrate the database, and nothing declared a Python \
                 backend that could (--python-url or YU_PYTHON_URL).\n\
                 Run the migration once, from a checkout of the Python tree:\n\
                 \u{20}   uv run python scripts/migrate_db_cli.py --db <database>\n\
                 It takes the key from $YU_DB_KEY. On a systemd deployment \
                 yu-db-migrate.service runs it before every start; a launcher that acts \
                 on exit 78 does the same. Once it reports v{expected}, start again."
            )
        } else {
            format!(
                "Python owns this migration chain; it has not brought the database up to \
                 v{expected} yet. Until it does, tables this build expects may be missing and \
                 queries against them can come back empty."
            )
        };
        (
            SchemaDrift::Behind,
            format!("this database is at schema v{version}, but this build needs v{expected}."),
            remedy,
        )
    } else {
        let remedy = if refusing {
            format!(
                "Use a newer build, or restore a database at v{expected}. Nothing has been \
                 modified."
            )
        } else {
            format!(
                "Python has migrated past this build. Columns added after v{expected} are \
                 invisible here; update the binary to match."
            )
        };
        (
            SchemaDrift::Ahead,
            format!(
                "this database is at schema v{version}, which is newer than this build \
                 (v{expected})."
            ),
            remedy,
        )
    };
    Some((drift, format!("{headline}\nPath: {db_path}\n{remedy}")))
}

/// How to obtain a newer yu-server, said in terms of what is on this machine.
///
/// The refusal itself ("use a newer build") lives in `tagdb-core`, which is
/// mirrored publicly and has no business knowing how this application is
/// deployed -- so the deployment-specific half is built here and printed after
/// it. Nothing is fetched or run: this is the sentence an operator was
/// previously left to work out alone.
///
/// The shapes are told apart by what is present, because that is all this
/// process can know: a source checkout can rebuild, an installed binary
/// without one cannot. Neither branch promises success -- a checkout still
/// needs cargo, and a packaged install still needs a newer package.
fn how_to_get_a_newer_build() -> String {
    let checkout = std::env::current_dir()
        .ok()
        .filter(|dir| dir.join("crates").join("yu-server").is_dir());
    match checkout {
        Some(dir) => format!(
            "To get a newer build here: this looks like a source checkout ({}).\n\
             \u{20}   git pull && cargo build --release -p yu-server\n\
             or run the launcher (start.sh / start.ps1), which downloads a \
             published build and falls back to compiling one.",
            dir.display()
        ),
        None => "To get a newer build here: this is an installed binary with no source \
             tree beside it, so nothing on this machine can compile one. Install a \
             newer release (the desktop installer, or `make install` from a \
             checkout), or put back the yu-server that wrote this database."
            .to_string(),
    }
}

/// Exit code for "the database was written by a newer build of this binary".
///
/// `EX_DATAERR` from sysexits.h. Distinct from `FAILURE` so an operator (or a
/// script) can tell a binary downgrade apart from every other start-up failure,
/// and distinct from [`EXIT_DB_SCHEMA_BEHIND`] because the remedies are
/// opposites: 78 asks for the *Python* version to run once, this asks for the
/// *newer yu-server* to be put back.
///
/// Deliberately NOT in the launchers' fallback set. Falling back to Python
/// would start the app -- Python never reads `rust_schema_version` -- but it
/// would also make a binary downgrade permanently and silently serve from the
/// slower path. The newer binary that wrote this database still exists; using
/// it is the repair, and a refusal that names it is more useful than a quiet
/// degradation. `check_launcher_fallback_exit_codes` pins that the launchers
/// carry only {78, 126, 127}, so adding this there would have to be deliberate.
///
/// **The desktop app is an explicit exception, and the word that matters is
/// "silently".** `src-tauri` degrades to Python on this code and keeps
/// running, because a shell launcher that stops leaves an operator a message
/// on a terminal they are already looking at, while an app that refuses to
/// open leaves a user with nothing they can act on. The exception is only
/// tolerable because the degradation is *announced*: `desktop_degradation_notice`
/// puts the condition and its repair in front of the user. Remove that notice
/// and the exception becomes the quiet downgrade this paragraph forbids.
const EXIT_DB_RUST_SCHEMA_AHEAD: u8 = 65;

/// Exit code for "the database is behind this build, and Python can migrate it".
///
/// `EX_CONFIG` from sysexits.h. `start.sh` and `start.ps1` add this to the same
/// fallback condition they already use for 126/127 and launch the Python
/// server, whose migration chain brings the database up; the next launch then
/// passes this gate. Distinct from `FAILURE` (1) on purpose: every other
/// standalone refusal survives a Python launch, so falling back for those would
/// only add a wasted start.
///
/// Values already spoken for on this path: 0, 1, 2 (clap usage), 75
/// (`EX_TEMPFAIL`, web_ui.py's stale-bundle retry), 126/127 (exec failures).
const EXIT_DB_SCHEMA_BEHIND: u8 = 78;

/// Why standalone refused the database, and whether a Python launch repairs it.
///
/// Only a behind-version database is repairable: Python's migration chain
/// brings it up, so the launchers fall back to the Python path (exit code
/// [`EXIT_DB_SCHEMA_BEHIND`]) instead of leaving the user stuck. Every other
/// refusal here -- a mistyped profile, a missing key, a genesis failure, an
/// unreadable version, a database ahead of this build -- survives a Python
/// launch untouched, so falling back for those would only add a wasted start.
struct PreflightRefusal {
    message: String,
    python_can_migrate: bool,
}

impl PreflightRefusal {
    /// A refusal a Python launch cannot fix. The default: `python_can_migrate`
    /// is set at exactly one site, the behind-version arm below.
    fn fatal(message: String) -> Self {
        Self {
            message,
            python_can_migrate: false,
        }
    }
}

/// The version gate, evaluated in every mode.
///
/// `migrator_declared` -- not the standalone flag -- picks how strict this is.
/// Each mode keeps the behaviour it has today; only the selector changed:
///
/// | drift       | declared | outcome                            |
/// |-------------|----------|------------------------------------|
/// | behind      | no       | refuse, exit EXIT_DB_SCHEMA_BEHIND |
/// | behind      | yes      | warn, carry on (Python migrates)   |
/// | ahead       | no       | refuse, exit 1                     |
/// | ahead       | yes      | warn, carry on                     |
/// | cannot read | no       | refuse, exit 1                     |
/// | cannot read | yes      | warn, carry on                     |
///
/// The `declared` column is what the earlier design called hybrid. Refusing
/// when a migrator IS declared would take the server down the moment Python
/// moved a version ahead, which is exactly what the standalone-only gate was
/// there to avoid; that exemption is preserved, it just no longer keys off a
/// flag nothing sets deliberately.
///
/// Staying *silent* is the other failure the declared side guards against: a
/// database several versions behind serves empty results from a server that
/// reported a clean start, which reads as "the database is broken" rather than
/// "this binary and this database disagree". Say it once, loudly, and carry on.
/// What the start-up gate saw, for `server-info` to report.
///
/// A drift that is warned about and carried on with -- a behind database with
/// a declared migrator -- exists only as one log line at boot, which nobody
/// reads once the server is up. The same is true of a declaration dropped
/// because the key or the build makes it false. Both change what the operator
/// should do, so both belong where they can be looked at.
///
/// Set once at start-up, never re-read from the database: this reports what
/// the gate decided on, not a live reading.
pub static SCHEMA_STATUS: std::sync::OnceLock<serde_json::Value> = std::sync::OnceLock::new();

/// Read `MAX(rust_schema_version.version)`, or `None` when there is nothing to
/// report.
///
/// A missing table, an unreadable database and one written before Rust had
/// migrations all mean the same thing here, so every failure collapses to
/// `None` rather than disturbing the Python-chain read the gate decides on.
/// `None` is never "version 0".
///
/// Its own connection rather than a second query on the gate's: a function
/// that takes a path and a key can be pointed at a seeded database by a test,
/// and the wiring from disk to `server-info` is exactly what was going
/// untested -- a fault injection that discarded the reading passed every test.
/// One extra read-only open at start-up is the price.
pub async fn read_rust_schema_version(db_path: &str, db_key: &str) -> Option<i64> {
    let pool = if db_key.is_empty() {
        tagdb_core::connect_readonly(db_path).await.ok()?
    } else {
        tagdb_core::connect_encrypted_readonly(db_path, db_key)
            .await
            .ok()?
    };
    let found: Option<i64> = sqlx::query_scalar("SELECT MAX(version) FROM rust_schema_version")
        .fetch_one(&pool)
        .await
        .ok()
        .flatten();
    pool.close().await;
    found
}

/// Shape the status value. Separate from the gate so every combination can be
/// tested without a database.
fn drift_of(expected: i64, actual: Option<i64>) -> &'static str {
    match actual {
        None => "unreadable",
        Some(v) if v < expected => "behind",
        Some(v) if v > expected => "ahead",
        Some(_) => "match",
    }
}

/// Read the Rust chain off `db_path` and shape the whole status in one step.
///
/// Deliberately not "read here, shape there": while the reading was passed in
/// as an argument, a fault injection that replaced it with `None` at the call
/// site passed every test -- the last hop from disk to `server-info` had no
/// test of its own, and a global cell made one order-dependent. With the read
/// inside, the only way to break the hop is to break this function, which is
/// tested against a seeded database.
pub async fn schema_status_for(
    db_path: &str,
    db_key: &str,
    expected: i64,
    actual: Option<i64>,
    migrator_declared: bool,
    migrator_reason: &str,
) -> serde_json::Value {
    let rust_actual = read_rust_schema_version(db_path, db_key).await;
    schema_status_value(
        expected,
        actual,
        migrator_declared,
        migrator_reason,
        rust_actual,
    )
}

pub fn schema_status_value(
    expected: i64,
    actual: Option<i64>,
    migrator_declared: bool,
    migrator_reason: &str,
    rust_actual: Option<i64>,
) -> serde_json::Value {
    let drift = drift_of(expected, actual);
    // The second chain. Reporting only the Python one described half the
    // schema state while claiming to describe it: the exit code for a binary
    // downgrade (65) comes from `rust_schema_version`, and none of it appeared
    // here. A database whose Rust chain is ahead cannot start at all, so what
    // this reports is the *before* -- enough to see a downgrade coming, and to
    // tell which chain a disagreement lives in.
    let rust_expected = tagdb_core::latest_rust_migration_version();
    // "behind" is normal and momentary for this chain: the Rust migrations run
    // at start-up and bring it level, so a reading below the build's own is a
    // database that has not been opened yet rather than a finding.
    let rust_drift = drift_of(rust_expected, rust_actual);
    serde_json::json!({
        "expected": expected,
        "actual": actual,
        "drift": drift,
        // Only these two are serving despite a disagreement; "match" is not a
        // finding and "unreadable" without a migrator never gets this far.
        "serving_with_drift": migrator_declared && (drift == "behind" || drift == "ahead"),
        "migrator_declared": migrator_declared,
        "migrator_reason": migrator_reason,
        "rust_expected": rust_expected,
        "rust_actual": rust_actual,
        "rust_drift": rust_drift,
    })
}

async fn db_version_gate(
    db_path: &str,
    db_key: &str,
    migrator_declared: bool,
    migrator_reason: &str,
) -> Result<(), PreflightRefusal> {
    // A SQLite URI (`:memory:` and friends) has no Python-owned schema to be
    // behind, and a database that does not exist yet has no version to read.
    if tagdb_core::is_sqlite_uri(db_path) || !Path::new(db_path).exists() {
        return Ok(());
    }
    let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
    let version = match read_schema_version(db_path, db_key).await {
        Ok(version) => version,
        Err(message) => {
            if migrator_declared {
                let _ = SCHEMA_STATUS.set(
                    schema_status_for(
                        db_path,
                        db_key,
                        expected,
                        None,
                        migrator_declared,
                        migrator_reason,
                    )
                    .await,
                );
                tracing::warn!("{message}");
                return Ok(());
            }
            return Err(PreflightRefusal::fatal(message));
        }
    };
    let _ = SCHEMA_STATUS.set(
        schema_status_for(
            db_path,
            db_key,
            expected,
            Some(version),
            migrator_declared,
            migrator_reason,
        )
        .await,
    );
    match schema_version_verdict(version, db_path, !migrator_declared) {
        None => Ok(()),
        // Someone will migrate it. Say so once and carry on.
        Some((_, message)) if migrator_declared => {
            tracing::warn!("{message}");
            Ok(())
        }
        // The one repairable refusal: Python's chain migrates it forward, and
        // the launchers fall back to Python on this exit code.
        Some((SchemaDrift::Behind, message)) => Err(PreflightRefusal {
            message,
            python_can_migrate: true,
        }),
        Some((SchemaDrift::Ahead, message)) => Err(PreflightRefusal::fatal(message)),
    }
}

/// `merge_profile` now lives in `ext_config` so routes that re-read config.json
/// after boot apply the same profile overlay this startup path does.
use crate::ext_config::merge_profile;

/// Scan a token list for a flag value without invoking clap (used beside Cli::parse_from).
///
/// `args` must be the same token list clap parsed -- launch-args.txt tokens
/// included. Scanning `std::env::args()` here instead would make every flag
/// written only in launch-args.txt read as "not specified", so config.toml /
/// config.json would silently override it. Python resolves these from the
/// merged list (`parse_args(file_args + sys.argv[1:])`, runtime_runner.py),
/// and launch-args.txt.example documents the file as CLI arguments that only
/// real CLI arguments outrank -- not the config file.
fn argv_flag(args: &[String], flag: &str) -> Option<String> {
    let prefix = format!("{}=", flag);
    let mut iter = args.iter().peekable();
    while let Some(arg) = iter.next() {
        if arg == flag {
            return iter.next().cloned();
        }
        if let Some(val) = arg.strip_prefix(&prefix) {
            return Some(val.to_string());
        }
    }
    None
}

/// Settings that config.json may also supply, resolved against the merged
/// token list.
///
/// Precedence, highest first:
///   1. `--flag` anywhere in `merged_args` (launch-args.txt or real argv; when
///      both name it, real argv wins because it comes last and clap keeps the
///      last occurrence)
///   2. the config file's "server" table
///   3. `cli_value` -- what clap already resolved from the `env = "YU_*"`
///      attribute, a .env file, or the hardcoded default
///
/// Tier 1 must be asked of `merged_args`, not of `std::env::args()`: a flag
/// written only in launch-args.txt would otherwise read as "not specified"
/// and tier 2 would silently override it, which is neither what
/// launch-args.txt.example promises nor what the Python launcher does
/// (runtime_runner.py parses `file_args + sys.argv[1:]` as one list).
fn resolve_host(
    merged_args: &[String],
    server_cfg: &serde_json::Map<String, serde_json::Value>,
    cli_value: &str,
) -> String {
    if argv_flag(merged_args, "--host").is_some() {
        return cli_value.to_string();
    }
    server_cfg
        .get("host")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string())
        .unwrap_or_else(|| cli_value.to_string())
}

/// See [`resolve_host`] for the precedence this shares.
fn resolve_port(
    merged_args: &[String],
    server_cfg: &serde_json::Map<String, serde_json::Value>,
    cli_value: u16,
) -> u16 {
    if argv_flag(merged_args, "--port").is_some() {
        return cli_value;
    }
    server_cfg
        .get("port")
        .and_then(|v| v.as_u64())
        // `as u16` wrapped instead of rejecting: a configured port of 70000
        // became 4464, and 65536 became 0 -- which asks the OS for *any* free
        // port. Either way the server came up somewhere other than where it
        // was configured and said nothing. An out-of-range value now falls
        // back to the CLI value, exactly like a missing key.
        .and_then(|p| u16::try_from(p).ok())
        .unwrap_or(cli_value)
}

/// See [`resolve_host`] for the precedence this shares. Reads "db" from the
/// config root rather than its "server" table, and ignores an empty string
/// there the way Python's `config.get("db")` truthiness check does.
fn resolve_db_path(
    merged_args: &[String],
    app_config: &serde_json::Value,
    cli_value: &str,
) -> String {
    if argv_flag(merged_args, "--db").is_some() {
        return cli_value.to_string();
    }
    app_config
        .get("db")
        .and_then(|v| v.as_str())
        .filter(|s| !s.is_empty())
        .map(|s| s.to_string())
        .unwrap_or_else(|| cli_value.to_string())
}

/// Read launch-args.txt from `dir`, returning extra argv tokens (file args lose to real CLI args).
/// Skips blank lines and `#` comments. Honors YU_SKIP_LAUNCH_ARGS_FILE=1.
fn load_launch_args_file(dir: &Path) -> Vec<String> {
    if std::env::var("YU_SKIP_LAUNCH_ARGS_FILE").as_deref() == Ok("1") {
        return vec![];
    }
    let path = dir.join("launch-args.txt");
    let Ok(text) = std::fs::read_to_string(&path) else {
        return vec![];
    };
    let mut args = Vec::new();
    for line in text.lines() {
        let line = line.trim();
        if line.is_empty() || line.starts_with('#') {
            continue;
        }
        args.extend(line.split_whitespace().map(String::from));
    }
    if !args.is_empty() {
        eprintln!("[yu-server] launch-args.txt: {}", args.join(" "));
    }
    args
}

/// Load .env files before Cli::parse() so clap's env = "YU_*" annotations see them.
///
/// Priority (highest → lowest, loaded lowest-first with override):
///   1. Directory of --config / YU_CONFIG file
///   2. ~/.config/yu/server.env
///   3. Current working directory (.env)
///   4. Directory of --db / YU_DB (.env)
///
/// Honors YU_SKIP_DOTENV_FILES=1 to skip entirely (used by test harnesses that
/// auto-start a Rust server and must not inherit an operator's real dotenv
/// config, e.g. ~/.config/yu/server.env re-injecting YU_PIN/YU_DB_KEY).
/// Which value `YU_DB` should carry, given what the two names hold now.
///
/// Python and this binary use different names for the same setting -- web_ui.py
/// reads `TAGDB_DB`, clap here reads `YU_DB` -- and the name is all that
/// differs. Both treat it as a *default* that config.json then overrides:
/// `resolve_db_path` below only returns early when `--db` appears in argv, and
/// `runtime_runner.py` overrides with config's `db` exactly when
/// `args.db == _default_db`, whose default is `TAGDB_DB` itself.
///
/// The launcher used to translate the name by appending `--db` to argv. That
/// changed the setting's *rank*, not its name: with `--db` present
/// `resolve_db_path` returns before it ever looks at config.json. So
/// "Settings > Change DB" -- which writes config's `db` -- silently stopped
/// taking effect under fast mode while the Python launch still honoured it,
/// and the two launches then grew two databases apart. Worse, the schema gate
/// would report on one of them while the next start served the other.
///
/// Bridging the name here keeps the rank, because an environment-provided
/// value does not make `argv_flag("--db")` true.
///
/// `YU_DB` wins when both are set, matching the order
/// `apply_tagdb_env_overrides` documents for every other pair
/// (`YU_* > TAGDB_* > config.json > default`). An empty `TAGDB_DB` is left
/// alone: Python compares `args.db == _default_db` with both empty and lets
/// config win, and not bridging reaches the same answer here.
fn bridged_db_value(
    yu_db: Option<&std::ffi::OsStr>,
    tagdb_db: Option<&std::ffi::OsStr>,
) -> Option<std::ffi::OsString> {
    if yu_db.is_some() {
        return None;
    }
    tagdb_db
        .filter(|value| !value.is_empty())
        .map(std::ffi::OsString::from)
}

/// Set `YU_DB` from `TAGDB_DB` when only the latter is present.
///
/// Called before `load_dotenv_files` on purpose: that function discovers
/// `.env` next to whatever names the database, so bridging first keeps the
/// discovery fast mode used to get from its `--db` argument. It also leaves a
/// `.env` that sets `YU_DB` overriding the bridged value, since those files
/// load with override semantics.
///
/// Its own function, and named, because `main_env_order_guard.rs` allows
/// `set_var` only at sites it can name and prove the ordering of. See
/// `bridged_db_value` for why the bridge exists at all.
fn apply_db_name_bridge() {
    if let Some(value) = bridged_db_value(
        std::env::var_os("YU_DB").as_deref(),
        std::env::var_os("TAGDB_DB").as_deref(),
    ) {
        std::env::set_var("YU_DB", value);
    }
}

fn load_dotenv_files() {
    if std::env::var("YU_SKIP_DOTENV_FILES").as_deref() == Ok("1") {
        return;
    }
    // Raw argv, deliberately not the launch-args.txt-merged list the bind
    // settings below use: this runs before .env is loaded, and
    // load_launch_args_file() reads YU_SKIP_LAUNCH_ARGS_FILE from the
    // environment. Merging here would move that read ahead of the .env files
    // that may set it. A --config/--db written only in launch-args.txt
    // therefore does not steer .env discovery; it still steers everything
    // else, because Cli::parse_from() below sees the merged list.
    let raw_argv: Vec<String> = std::env::args().collect();
    let config_val = argv_flag(&raw_argv, "--config").or_else(|| std::env::var("YU_CONFIG").ok());
    let db_val = argv_flag(&raw_argv, "--db")
        .or_else(|| std::env::var("YU_DB").ok())
        .unwrap_or_default();

    let mut candidates: Vec<PathBuf> = Vec::new();

    // 4. YU_DB directory (lowest priority — loaded first, overwritten by later)
    if !db_val.is_empty() {
        if let Some(parent) = Path::new(&db_val).parent() {
            candidates.push(parent.join(".env"));
        }
    }

    // 3. Current working directory
    candidates.push(PathBuf::from(".env"));

    // 2. ~/.config/yu/server.env
    if let Some(home) = dirs::home_dir() {
        candidates.push(home.join(".config").join("yu").join("server.env"));
    }

    // 1. --config file's directory (highest priority — loaded last, wins)
    if let Some(ref cfg) = config_val {
        if let Some(parent) = Path::new(cfg).parent() {
            candidates.push(parent.join(".env"));
        }
    }

    for path in candidates {
        if path.exists() {
            load_env_file_override(&path);
        }
    }
}

/// Load a .env file line-by-line with override semantics.
/// A bad line (e.g. unquoted Windows path with backslash) is skipped with a warning
/// instead of aborting the entire file.
/// Environment names whose value is a secret worth protecting on disk.
///
/// Not every `.env` deserves a permissions warning -- a project-local one
/// holding a port and a cache path is nobody's business. These are the names
/// that make the file worth reading by someone else.
const SECRET_ENV_NAMES: &[&str] = &["YU_DB_KEY", "YU_PIN", "YU_SECRET", "YU_API_KEY"];

/// The warning an env file's permissions deserve, or `None` when they are fine.
///
/// Separated from the IO so the rule can be tested against every mode rather
/// than against whichever mode this machine happens to produce.
///
/// Deliberately a warning and not a refusal: the file is already written and
/// already readable, so refusing to start would take the service down without
/// un-reading anything. `deploy/server.env.example` asks for `chmod 600` and
/// nothing checked that it happened -- this is the check, and it names the
/// remedy.
fn env_file_exposure_warning(path: &Path, mode: u32, holds_secret: bool) -> Option<String> {
    if !holds_secret || mode & 0o077 == 0 {
        return None;
    }
    // Written as a total expression rather than a match with an impossible
    // arm: `clippy::unreachable` is denied here, and rightly -- an invariant
    // asserted in one function while it is established in another is how a
    // start-up path acquires a panic nobody expected.
    let group = mode & 0o070 != 0;
    let who = if group && mode & 0o007 != 0 {
        "the group and everyone else"
    } else if group {
        "the group"
    } else {
        "everyone else"
    };
    Some(format!(
        "[yu-server] {} is readable by {} (mode {:o}) and holds a secret. \
         Fix with: chmod 600 {}",
        path.display(),
        who,
        mode & 0o777,
        path.display()
    ))
}

fn load_env_file_override(path: &Path) {
    match dotenvy::from_path_iter(path) {
        Err(e) => eprintln!("[yu-server] env load skipped {}: {e}", path.display()),
        Ok(iter) => {
            let mut count = 0usize;
            let mut holds_secret = false;
            for item in iter {
                match item {
                    Ok((k, v)) => {
                        if SECRET_ENV_NAMES.contains(&k.as_str()) && !v.is_empty() {
                            holds_secret = true;
                        }
                        std::env::set_var(&k, &v);
                        count += 1;
                    }
                    Err(e) => eprintln!("[yu-server] env line skipped in {}: {e}", path.display()),
                }
            }
            eprintln!("[yu-server] loaded env: {} ({count} vars)", path.display());
            // Unix only: Windows protects files by ACL, and mode bits read
            // back there describe nothing an operator can act on.
            #[cfg(unix)]
            {
                use std::os::unix::fs::PermissionsExt;
                if let Ok(meta) = std::fs::metadata(path) {
                    if let Some(warning) =
                        env_file_exposure_warning(path, meta.permissions().mode(), holds_secret)
                    {
                        eprintln!("{warning}");
                    }
                }
            }
            #[cfg(not(unix))]
            let _ = holds_secret;
        }
    }
}

/// Copy *.example templates to their real names on first launch (mirrors Python _seed_example_files).
///
/// config.toml is skipped when config.json already exists: config.json is the file the
/// Python build (and extension config read/write, e.g. wildcard_dirs) still uses exclusively,
/// so seeding config.toml on top of an existing config.json would make `load_config`
/// silently prefer the fresh, empty config.toml and orphan all settings already saved
/// in config.json (split-brain config).
/// Keep config.json before config.toml below: the guard relies on JSON being seeded first;
/// reversing that order lets both files be created on a fresh install.
fn seed_example_files(dir: &Path) {
    for (src_name, dst_name) in [
        ("launch-args.txt.example", "launch-args.txt"),
        ("config.json.example", "config.json"),
        ("config.toml.example", "config.toml"),
    ] {
        let src = dir.join(src_name);
        let dst = dir.join(dst_name);
        if dst.exists() || !src.exists() {
            continue;
        }
        if dst_name == "config.toml" && dir.join("config.json").exists() {
            continue;
        }
        match std::fs::copy(&src, &dst) {
            Ok(_) => eprintln!("[yu-server] seeded {dst_name} from {src_name}"),
            Err(e) => eprintln!("[yu-server] failed to seed {dst_name}: {e}"),
        }
    }
}

fn load_config(config_path: Option<&Path>) -> serde_json::Value {
    // Try TOML first (new format), then JSON (legacy).
    if let Some(path) = config_path {
        if let Some(v) = try_load_config(path) {
            return v;
        }
        return serde_json::json!({"scan_roots": []});
    }
    for path in [
        PathBuf::from("config.toml"),
        PathBuf::from("config.json"),
        PathBuf::from("tagdb_config.json"),
    ] {
        if let Some(v) = try_load_config(&path) {
            return v;
        }
    }
    serde_json::json!({"scan_roots": []})
}

fn try_load_config(path: &Path) -> Option<serde_json::Value> {
    if !path.exists() {
        return None;
    }
    let raw = std::fs::read_to_string(path).ok()?;
    if path.extension().and_then(|e| e.to_str()) == Some("toml") {
        let table: toml::Table = toml::from_str(&raw).ok()?;
        serde_json::to_value(table).ok()
    } else {
        serde_json::from_str(&raw).ok()
    }
}

/// Mirror Python core/configuration/env_override.py — apply TAGDB_* env vars to config.
/// Priority: YU_* (clap) > TAGDB_* (this fn) > config.json value > built-in default.
/// The optional third field is the YU_* env var that blocks this entry when explicitly set,
/// ensuring YU_* always wins even when set to the clap default value.
fn apply_tagdb_env_overrides(config: &mut serde_json::Value) {
    const MAP: &[(&str, Option<&str>, &[&str], &str)] = &[
        ("TAGDB_HOST", Some("YU_HOST"), &["server", "host"], "str"),
        ("TAGDB_PORT", Some("YU_PORT"), &["server", "port"], "int"),
        ("TAGDB_LAN", None, &["server", "lan"], "bool"),
        ("TAGDB_PIN", Some("YU_PIN"), &["server", "pin"], "str"),
        (
            "TAGDB_PIN_BOSS_LOGIN_UI",
            None,
            &["server", "pin_boss_login_ui"],
            "bool",
        ),
        ("TAGDB_EXTRACT_A1111", None, &["extract_a1111"], "bool"),
        ("TAGDB_EXTRACT_COMFYUI", None, &["extract_comfyui"], "bool"),
        ("TAGDB_LOWERCASE_TAGS", None, &["lowercase_tags"], "bool"),
        ("TAGDB_COMPUTE_HASH", None, &["compute_hash"], "bool"),
        ("TAGDB_ENABLE_FTS", None, &["enable_fts"], "bool"),
        (
            "TAGDB_MEDIA_CACHE_MAX_ITEMS",
            None,
            &["media_cache", "l1_max_items"],
            "int",
        ),
        (
            "TAGDB_MEDIA_CACHE_MAX_MB",
            None,
            &["media_cache", "l1_max_mb"],
            "int",
        ),
        (
            "TAGDB_REMOTE_FS_PROBE_RETRIES",
            None,
            &["remote_fs", "probe_retries"],
            "int",
        ),
        (
            "TAGDB_REMOTE_FS_PROBE_WAIT",
            None,
            &["remote_fs", "probe_wait"],
            "f64",
        ),
        (
            "TAGDB_REMOTE_FS_ENUMERATE_RETRIES",
            None,
            &["remote_fs", "enumerate_retries"],
            "int",
        ),
        (
            "TAGDB_REMOTE_FS_ENUMERATE_WAIT",
            None,
            &["remote_fs", "enumerate_wait"],
            "f64",
        ),
        ("TAGDB_WEBHOOK_SECRET", None, &["webhook_secret"], "str"),
    ];
    if config.as_object().is_none() {
        return;
    }
    for (var, yu_blocker, path, ty) in MAP {
        // Skip when the higher-priority YU_* var is explicitly present in the environment.
        if yu_blocker
            .map(|v| std::env::var(v).is_ok())
            .unwrap_or(false)
        {
            continue;
        }
        let Ok(raw) = std::env::var(var) else {
            continue;
        };
        let val = match *ty {
            "bool" => match raw.trim().to_lowercase().as_str() {
                "1" | "true" | "yes" | "on" => serde_json::Value::Bool(true),
                "0" | "false" | "no" | "off" => serde_json::Value::Bool(false),
                _ => continue,
            },
            "int" => {
                let Ok(n) = raw.trim().parse::<i64>() else {
                    continue;
                };
                serde_json::Value::Number(n.into())
            }
            "f64" => {
                let Ok(f) = raw.trim().parse::<f64>() else {
                    continue;
                };
                let Some(n) = serde_json::Number::from_f64(f) else {
                    continue;
                };
                serde_json::Value::Number(n)
            }
            _ => serde_json::Value::String(raw.trim().to_string()),
        };
        let last = path.last().unwrap();
        // Navigate/create nested path from root on each iteration
        let mut cur = config.as_object_mut().unwrap();
        for seg in &path[..path.len() - 1] {
            let entry = cur.entry(*seg).or_insert_with(|| serde_json::json!({}));
            cur = entry.as_object_mut().unwrap();
        }
        cur.insert(last.to_string(), val);
    }
}

/// Everything that touches the environment, done while the process is still
/// single-threaded, then the runtime.
///
/// `load_dotenv_files` and the `YU_DB` name bridge above it call
/// `std::env::set_var`, the only such calls outside `#[cfg(test)]`. glibc's
/// `setenv` can reallocate the environ block, so it is sound only while
/// nothing else can be reading it -- which is why edition 2024 makes it
/// `unsafe`, and why both happen here rather than anywhere later.
///
/// It used to run inside `#[tokio::main]`, and that macro builds the runtime
/// before the body starts: measured on this machine, `Builder::build()` takes
/// the process from 1 thread to 13, so every one of those `set_var` calls ran
/// with twelve worker threads already live. Building the runtime by hand keeps
/// the ordering explicit and visible instead of hiding it in an attribute.
fn main() -> std::process::ExitCode {
    let cwd = std::env::current_dir().unwrap_or_default();
    seed_example_files(&cwd);
    apply_db_name_bridge();
    load_dotenv_files();

    let runtime = match tokio::runtime::Builder::new_multi_thread()
        .enable_all()
        .build()
    {
        Ok(runtime) => runtime,
        Err(e) => {
            eprintln!("[yu-server] failed to build the tokio runtime: {e}");
            return std::process::ExitCode::FAILURE;
        }
    };
    runtime.block_on(run(cwd))
}

/// `main`'s body, split out so the env loading above can precede the runtime.
///
/// Returns the process exit code rather than calling `process::exit`: moving
/// this code out of `main` moved it out of the one place clippy exempts from
/// `clippy::exit`, and the ratchet denies that lint everywhere else because
/// `exit` skips every destructor and every graceful-shutdown path. Handing the
/// code back to `main` keeps the startup failures fatal without that.
async fn run(cwd: std::path::PathBuf) -> std::process::ExitCode {
    let log_ring = Arc::new(logs::LogRingBuffer::new(1000));

    tracing_subscriber::registry()
        .with(
            tracing_subscriber::fmt::layer().with_filter(
                tracing_subscriber::EnvFilter::try_from_default_env()
                    .unwrap_or_else(|_| "yu_server=info".into()),
            ),
        )
        .with(logs::tracing_layer::TracingLayer::new(
            Arc::clone(&log_ring),
            tracing::Level::INFO,
        ))
        .init();

    // Merge launch-args.txt (lower priority) with real argv (higher priority).
    // Equivalent to Python: parser.parse_args(file_args + sys.argv[1:])
    let file_args = load_launch_args_file(&cwd);
    let argv0 = std::env::args()
        .next()
        .unwrap_or_else(|| "yu-server".to_string());
    // Built unconditionally, not only when the file has tokens: argv_flag()
    // below reads this same list, so it must exist on every path.
    let merged_args: Vec<String> = std::iter::once(argv0)
        .chain(file_args)
        .chain(std::env::args().skip(1))
        .collect();
    let cli = Cli::parse_from(&merged_args);

    // Answer without opening the database: the launcher calls --compat-info to
    // decide whether this binary is usable, and at that moment it has not
    // passed the encryption key. Must run before standalone_genesis and
    // db_version_gate, the first functions below that touch the DB.
    if cli.compat_info {
        // stdout IS this flag's output contract: the launcher parses it.
        #[allow(
            clippy::print_stdout,
            reason = "--compat-info writes to stdout by contract"
        )]
        {
            println!("{}", compat_info::render_compat_info());
        }
        return std::process::ExitCode::SUCCESS;
    }

    let config_path = cli.config.clone().unwrap_or_else(|| {
        // Prefer config.toml (new); fall back to config.json (legacy).
        let toml = PathBuf::from("config.toml");
        if toml.exists() {
            toml
        } else {
            PathBuf::from("config.json")
        }
    });
    if config_migrate::should_auto_migrate(cli.config.is_some()) {
        let outcome = config_migrate::migrate_legacy_config(&config_path);
        if let Some(error) = outcome.error {
            tracing::warn!(%error, primary = %config_path.display(), "legacy config migration failed");
        } else if outcome.migrated {
            tracing::info!(keys = ?outcome.merged_keys, backup = ?outcome.backup, "legacy config migrated");
        }
    }
    let fixed_roots = config_migrate::normalize_scan_root_quotes(&config_path);
    if fixed_roots > 0 {
        tracing::info!(
            count = fixed_roots,
            "stripped quotes from stored scan roots"
        );
    }
    let app_config = {
        let mut cfg = load_config(cli.config.as_deref());
        apply_tagdb_env_overrides(&mut cfg);
        cfg
    };
    // Python resolves this from the raw config before profile merging; keep both sides identical.
    let vdevice_group_id = infer_manager::resolve_vdevice_group_id(
        &app_config,
        std::env::var("HAILO_VDEVICE_GROUP_ID").ok().as_deref(),
    );

    // Mirror Python resolve_server_bind_and_pin: apply config.json["server"] at CLI defaults.
    let server_cfg = app_config
        .get("server")
        .and_then(|v| v.as_object())
        .cloned()
        .unwrap_or_default();
    let _ = restart::RESTART_CONFIG.set(restart::RestartConfig::resolve(
        false,
        false,
        None,
        Some(&server_cfg),
    ));
    let effective_host = resolve_host(&merged_args, &server_cfg, &cli.host);
    let effective_port = resolve_port(&merged_args, &server_cfg, cli.port);
    let effective_lan = cli.lan
        || server_cfg
            .get("lan")
            .and_then(|v| v.as_bool())
            .unwrap_or(false);

    // Resolve project_root early — needed for secret_store::decrypt below.
    let project_root = cli
        .project_root
        .unwrap_or_else(|| std::env::current_dir().expect("failed to resolve project root"));
    let data_dir = secret_store::data_dir(&project_root);

    // CLI --pin / YU_PIN > YU_TAURI_PIN (Tauri-injected) > config.json["server"]["pin"].
    let effective_pin = cli
        .pin
        .clone()
        .or_else(|| {
            std::env::var("YU_TAURI_PIN")
                .ok()
                .filter(|s| !s.trim().is_empty())
                .map(|s| s.trim().to_string())
        })
        .or_else(|| {
            server_cfg
                .get("pin")
                .and_then(|v| v.as_str())
                .filter(|s| !s.is_empty())
                .map(|s| secret_store::decrypt(s, &project_root))
        });

    let host = if effective_lan {
        "0.0.0.0".to_string()
    } else {
        effective_host
    };
    // Not for a path query: `--print-db-path --lan` would otherwise demand a
    // PIN on the command line, which is how secrets end up in `ps`. The query
    // starts no listener, so there is nothing here to protect.
    if !cli.print_db_path && !is_loopback_host(&host) && effective_pin.is_none() {
        eprintln!("error: non-loopback --host requires --pin (or YU_PIN env var) to be set");
        return std::process::ExitCode::FAILURE;
    }

    let pin_auth_enabled = effective_pin.is_some();
    let (pin_hash, valid_token) = if let Some(ref pin) = effective_pin {
        (hash_pin(pin, &cli.secret), make_token(pin, &cli.secret))
    } else {
        (String::new(), String::new())
    };
    let db_path = resolve_db_path(&merged_args, &app_config, &cli.db);
    let static_dir = project_root.join("ui/default/static");
    let cache_dir = std::env::var_os("TAGDB_CACHE_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| project_root.join("cache"));
    std::fs::create_dir_all(&cache_dir).expect("failed to create cache directory");
    let standalone = cli.standalone || env_truthy("YU_STANDALONE");
    let infer_standalone = env_truthy("YU_INFER_STANDALONE");

    // Mirror Python: resolve_profile_config() — merge named profile, optionally override db_path.
    let (app_config, db_path, active_profile, profile_requested_but_missing) = {
        let name = cli.profile.clone().or_else(|| {
            app_config
                .get("active_profile")
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        });
        if let Some(ref n) = name {
            let (merged, prof_db, found) = merge_profile(&app_config, n, &project_root);
            (merged, prof_db.unwrap_or(db_path), Some(n.clone()), !found)
        } else {
            (app_config, db_path, None, false)
        }
    };

    // Everything that decides the path has now been applied: argv, config,
    // the env bridge and the profile override. Print and stop -- before
    // standalone_genesis and db_version_gate, which are the first things below
    // that touch a database. Nothing is created and nothing is opened.
    if cli.print_db_path {
        #[allow(
            clippy::print_stdout,
            reason = "--print-db-path writes to stdout by contract"
        )]
        {
            println!("{db_path}");
        }
        return std::process::ExitCode::SUCCESS;
    }

    // Deliberate asymmetry: server_cfg keeps pre-profile host/port/LAN/PIN settings,
    // while native_daemon uses merged config to match configured_peer_name later.
    let native_daemon_config =
        crate::ext_config::extension_value(&app_config, "builtin-lan-cowork", "enabled")
            .and_then(|value| value.as_bool());
    let native_daemon_env = std::env::var_os("YU_LAN_COWORK_NATIVE_DAEMON")
        .map(|_| env_truthy("YU_LAN_COWORK_NATIVE_DAEMON"));
    let native_daemon_source = if cli.native_daemon || cli.no_native_daemon {
        "cli"
    } else if standalone {
        if native_daemon_config.is_some() {
            "config"
        } else if native_daemon_env.is_some() {
            "env"
        } else {
            "default"
        }
    } else if native_daemon_env.is_some() {
        "env"
    } else {
        "default"
    };
    let native_daemon = match state::resolve_native_daemon(
        standalone,
        cli.native_daemon,
        cli.no_native_daemon,
        native_daemon_config,
        native_daemon_env,
    ) {
        Ok(value) => value,
        Err(message) => {
            eprintln!("error: {message}");
            return std::process::ExitCode::FAILURE;
        }
    };
    // auto_stubs can report LAN Cowork enabled from extension.json while this daemon is off; log this so operators can distinguish them.
    tracing::info!(
        native_daemon,
        source = native_daemon_source,
        "native daemon resolved"
    );

    // Resolved once here (arch-constraints.yaml single-computation rule) and
    // held in `Config` so every producer -- yu-infer spawn, its
    // crash-supervisor respawn, the in-process ONNX fallback, and LAN mesh
    // capability reporting -- reads the same value instead of recomputing it
    // across the up-to-25s window while the sidecar is starting.
    let wd_tagger_root = routes::wd_tagger::wd_tagger_root(&cache_dir);
    let clip_model_dir = routes::clip_model::model_dir(&cache_dir);

    let config = Config {
        db_path: db_path.clone(),
        pin_hash,
        valid_token,
        secret: cli.secret.clone(),
        trusted_proxy_enabled: cli.trusted_proxy_auth
            || server_cfg
                .get("trusted_proxy_auth")
                .and_then(|v| v.as_bool())
                .unwrap_or(false),
        trusted_ips: parse_ip_set(&cli.trusted_ips),
        // Read from `server.trusted_proxy_ips`, matching the exact condition
        // Python uses to install ProxyFix (runtime_app.py:106). Kept apart from
        // `trusted_ips` above, which comes from --trusted-ips and gates
        // `X-Remote-User` delegation: pointing the limiter at that would tie
        // client-IP resolution to an auth decision, and on the ordinary
        // reverse-proxy deployment it resolves every request to the proxy's own
        // address -- one bucket for the whole LAN. See `state::Config`'s field
        // doc and `tmp/trusted-proxy-config-sources.md`.
        rate_limit_trusted_proxies: server_cfg
            .get("trusted_proxy_ips")
            .and_then(|v| v.as_array())
            .map(|entries| {
                entries
                    .iter()
                    .filter_map(|v| v.as_str())
                    .map(|s| s.trim().to_string())
                    .filter(|s| !s.is_empty())
                    .collect()
            })
            .unwrap_or_default(),
        trusted_peer_ips: parse_ip_set(&cli.trusted_peer_ips),
        quick_lock_enabled: !cli.no_quick_lock,
        pin_auth_enabled,
        min_pin_length: 4,
        python_url: if standalone {
            String::new()
        } else {
            cli.python_url.clone()
        },
        config_path,
        project_root,
        app_config,
        cache_dir,
        server_mode: {
            let mode_env = std::env::var("TAGDB_MODE").unwrap_or_default();
            let raw = cli
                .mode
                .as_deref()
                .unwrap_or_else(|| mode_env.trim())
                .trim();
            match raw {
                "full" | "gateway" | "server" => raw.to_string(),
                _ => "full".to_string(),
            }
        },
        headless: cli.headless || env_truthy("TAGDB_HEADLESS"),
        safe_mode: cli.safe_mode,
        standalone,
        infer_standalone,
        mcp_native: env_default_true("YU_MCP_NATIVE"),
        active_profile,
        python_executable: cli.python_executable.clone(),
        pin_boss_login_ui: server_cfg
            .get("pin_boss_login_ui")
            .and_then(|v| v.as_bool())
            .unwrap_or_else(|| env_default_true("TAGDB_PIN_BOSS_LOGIN_UI")),
        wd_tagger_root,
        clip_model_dir,
    };

    // Standalone (Python absent) is the only mode that may create the database:
    // in hybrid, Python owns creation and its whole migration chain. This runs
    // before every other writer -- before the pools, because the read-only pool
    // also opens with create_if_missing(false), and before
    // apply_standalone_schema / ensure_local_identity below, which would
    // otherwise write into a database this binary has not yet accepted.
    warn_if_the_key_is_one_python_would_refuse(&cli.db_key);
    let migrator_declared = migrator_declared(standalone, &cli.python_url, &cli.db_key);
    let migrator_reason = migrator_declaration_reason(standalone, &cli.python_url, &cli.db_key);
    if !standalone
        && !cli.python_url.is_empty()
        && !cli.db_key.is_empty()
        && cli.db_key != tagdb_core::PYTHON_BUILTIN_DB_KEY
    {
        // Worth saying out loud even when the database is current: every
        // route this binary forwards to Python will fail to open it.
        tracing::warn!(
            "a Python backend is declared, but this database uses an \
             operator-supplied key and the Python server opens databases only \
             with its built-in one. Forwarded routes that touch the database \
             will fail, and this binary will not treat Python as a migrator. \
             Migrate with: uv run python scripts/migrate_db_cli.py --db <database>"
        );
    }
    if standalone {
        if let Err(refusal) =
            standalone_genesis(&db_path, &cli.db_key, profile_requested_but_missing).await
        {
            eprintln!("{}", refusal.message);
            return std::process::ExitCode::FAILURE;
        }
    }
    // Every mode, not just standalone: a launch with no declared migrator has
    // nobody to bring a stale database up, whichever flag it was started with.
    if let Err(refusal) =
        db_version_gate(&db_path, &cli.db_key, migrator_declared, migrator_reason).await
    {
        eprintln!("{}", refusal.message);
        // The direction comes from the verdict as a value, never from matching
        // the message: the wording is a contract surface
        // check_genesis_acceptance.py greps, and a predicate that read its own
        // prose would invert on the next reword.
        if refusal.python_can_migrate {
            return std::process::ExitCode::from(EXIT_DB_SCHEMA_BEHIND);
        }
        return std::process::ExitCode::FAILURE;
    }

    // Hand the backup subsystem the key before any route can run: it opens a
    // second connection (the destination of the online backup) and must key it
    // the same way, or it writes a file nothing can restore from.
    db_backup::routes::set_db_key(&cli.db_key);

    let pool = if cli.db_key.is_empty() {
        tagdb_core::connect(&db_path)
            .await
            .expect("failed to connect to tag database")
    } else {
        tagdb_core::connect_encrypted(&db_path, &cli.db_key)
            .await
            .expect("failed to connect to encrypted tag database")
    };
    let read_pool = if cli.db_key.is_empty() {
        tagdb_core::connect_readonly(&db_path)
            .await
            .expect("failed to connect to read-only tag database")
    } else {
        tagdb_core::connect_encrypted_readonly(&db_path, &cli.db_key)
            .await
            .expect("failed to connect to encrypted read-only tag database")
    };
    let (vectors_pool, vectors_read_pool) = crate::state::open_vectors_pools(
        &db_path,
        (!cli.db_key.is_empty()).then_some(cli.db_key.as_str()),
    )
    .await
    .expect("failed to connect to vectors database");
    // standalone (Python absent) is the sole owner of the LAN Cowork peer-family
    // schema; create it here. In hybrid, Python solely owns/migrates these tables
    // and their schema_version, so we deliberately do NOT touch them (avoids
    // double-owning the schema / version desync during the migration period).
    if standalone {
        lan_cowork::schema::apply_standalone_schema(&pool)
            .await
            .expect("failed to create LAN Cowork peer-family schema");
        // The peers-family schema now exists; make sure this node has its own LAN Cowork
        // identity. Standalone only — in hybrid Python owns `lan_cowork_identity`. Without
        // this, every seed reader (pairing, local_peer_id, build_peer_registry and therefore
        // all inbound peer handlers) returns None/503 on a fresh node.
        routes::peer_identity::ensure_local_identity(&pool)
            .await
            .expect("failed to bootstrap LAN Cowork local identity");
    }
    // A refusal here (the database is at a Rust schema this build does not know)
    // is a user-facing condition, not a bug: print the message and stop. A panic
    // would bury it under a backtrace.
    if let Err(err) =
        tagdb_core::apply_pending_rust_migrations_with_data_dir(&pool, Some(&data_dir)).await
    {
        match err {
            tagdb_core::TagdbError::IncompatibleSchema(msg) => {
                eprintln!("{msg}");
                eprintln!("{}", how_to_get_a_newer_build());
                // Close before leaving, as the other two exits do (the pool is
                // otherwise dropped while the runtime is being torn down, and a
                // gate run saw glibc abort with "double free or corruption" right
                // after this message -- exit -6 where the contract is 65).
                pool.close().await;
                // Its own code, not the generic 1: a binary downgrade is the
                // one start-up failure whose repair is "put the newer
                // yu-server back", and an operator reading only an exit status
                // could not tell it from a missing key or a bad config.
                return std::process::ExitCode::from(EXIT_DB_RUST_SCHEMA_AHEAD);
            }
            // Startup, long before the listener binds -- no request can reach
            // this, so it is not the request-path panic the lint guards. An
            // unclassified migration failure is exactly where the backtrace is
            // worth more than a tidy message.
            #[allow(clippy::panic, reason = "startup failure, before any listener exists")]
            other => panic!("failed to apply Rust migrations: {other}"),
        }
    }
    let infer_supervisor_stop = std::sync::Arc::new(std::sync::atomic::AtomicBool::new(false));
    let (infer_client, infer_child) = if !config.infer_standalone {
        let infer_auth_token = infer_auth::generate_infer_auth_token();
        let infer_instance_id = uuid::Uuid::new_v4().to_string();
        let infer_port: u16 = 18771;
        let yu_infer_binary = std::env::current_exe()
            .ok()
            .and_then(|p| p.parent().map(|d| d.join("yu-infer")))
            .unwrap_or_else(|| PathBuf::from("yu-infer"));
        let scan_roots: Vec<PathBuf> = infer_manager::resolve_scan_roots(&config.app_config);

        match infer_manager::spawn_with_restart(
            &yu_infer_binary,
            infer_port,
            &scan_roots,
            &infer_auth_token,
            &infer_instance_id,
            &vdevice_group_id,
            &config.wd_tagger_root,
            &config.clip_model_dir,
            5,
        )
        .await
        {
            Some(child) => {
                let base_url = format!("http://127.0.0.1:{infer_port}");
                let child_handle = std::sync::Arc::new(std::sync::Mutex::new(child));
                tokio::spawn(infer_manager::supervise(
                    std::sync::Arc::clone(&child_handle),
                    yu_infer_binary.clone(),
                    infer_port,
                    config.config_path.clone(),
                    scan_roots.clone(),
                    infer_auth_token.clone(),
                    infer_instance_id.clone(),
                    vdevice_group_id.clone(),
                    config.wd_tagger_root.clone(),
                    config.clip_model_dir.clone(),
                    std::sync::Arc::clone(&infer_supervisor_stop),
                ));
                (
                    Some(crate::infer_client::InferClient::new(
                        base_url,
                        infer_auth_token,
                    )),
                    Some(child_handle),
                )
            }
            None => {
                // Degradation is deliberately spelled out per subsystem: it is
                // uneven, and only WD-Tagger keeps returning results. A generic
                // "falling back to in-process inference" reads as a uniform
                // graceful fallback and hides the parts that simply stop working.
                tracing::error!(
                    wd_tagger = "degraded: in-process ONNX, results still returned",
                    hailort_proxy = "unavailable: requests fail with 503",
                    hailo_genai = "degraded: falls through to the Python backend",
                    clip_search = "unavailable: hailo_available reports false",
                    "failed to start the yu-infer sidecar; Hailo-backed features degrade unevenly"
                );
                (None, None)
            }
        }
    } else {
        (None, None)
    };

    let shared: SharedState = Arc::new(
        AppState::new_with_infer_and_vectors(
            config,
            pool,
            read_pool,
            vectors_pool,
            vectors_read_pool,
            log_ring,
            infer_client,
            infer_child,
        )
        .await
        .with_effective_port(effective_port),
    );
    // LAN-Cowork-owned state, decoupled from `AppState`/`SharedState`. Owns
    // the peer-registry/fleet-manager `Arc`s directly and shares AppState's
    // settings lock because both crates write the same config.json. Hands the
    // SAME instances to `LanCoworkState::new` — see that function's doc comment
    // and the S3 decoupling plan's §6 warnings on identity splitting.
    // Built here (before the peer-registry/fleet-manager/pairing-sweeper
    // wiring below) because those call sites now take `&LanCoworkState`;
    // `peer_registry`'s `OnceLock` is shared by `Arc`, so `lc_state
    // .peer_registry.set(...)` below is visible everywhere `lc_state` (or a
    // clone of it) is held.
    let lc_peer_registry = Arc::new(std::sync::OnceLock::new());
    let lc_fleet_manager = Arc::new(routes::lan_cowork_fleet_manager::FleetManager::new());
    let lc_settings_lock = Arc::clone(&shared.settings_lock);
    let lc_state = routes::lan_cowork_host::LanCoworkState::new(
        &shared,
        Arc::clone(&lc_peer_registry),
        Arc::clone(&lc_fleet_manager),
        Arc::clone(&lc_settings_lock),
    );
    // Populate the peer registry slot for the inbound read handlers. Fail-safe:
    // returns None (slot stays empty -> handlers 503) unless native_daemon is on,
    // the local identity is provisioned, and load_all succeeds. Must run after the
    // standalone peers schema is applied (main.rs ~L761) — it is, native_daemon ⊂
    // standalone. Does not depend on bound_port (set later after the app is built).
    if let Some(registry) =
        routes::lan_cowork_inbound_read::build_peer_registry(&shared, native_daemon).await
    {
        routes::lan_cowork_discovery::start_discovery_daemon(lc_state.clone(), registry.clone())
            .await;
        let _ = lc_state.peer_registry.set(registry);
        routes::lan_cowork_fleet_manager::start_fleet_manager_if_configured(&lc_state).await;
    }
    // Independent pairing-PIN sweeper: bounds expired-plaintext-PIN RAM residency
    // without depending on pairing traffic. Needs no identity/registry, so it is a
    // sibling of the registry block (gating it on identity would skip cleanup on
    // exactly the nodes that still accumulate pending rows). native_daemon-gated
    // (never `standalone`): must stay dead until flag-day.
    if native_daemon {
        routes::lan_cowork_pairing::start_pairing_sweeper(lc_state.clone());
    }
    // Pin the peer-transport nonce grace window to process boot (design MF-3),
    // so nonce replay protection is boot-anchored regardless of which future
    // increment wires the first nonce-required peer route.
    crate::auth::peer_transport::nonce_store();
    routes::lan_cowork_fleet_consent::start_consent_janitor();
    if shared.config.standalone {
        scheduler::start_scheduler(&shared).await;
    }
    // Periodic + scan-complete backups. Gated internally on the `full` profile
    // and `backup.enabled`, so this call is safe on every mode.
    db_backup::scheduler::start(&shared);
    {
        let sm = crate::scan_manager::ScanManager::new(shared.config.project_root.clone());
        shared.scan_manager.set(Arc::new(sm)).ok();
        if let Some(sm) = shared.scan_manager.get() {
            sm.reconnect_if_running(shared.clone()).await;
        }
    }
    routes::watcher::auto_start_if_configured(&shared);

    let session_store = MemoryStore::default();
    let session_layer = SessionManagerLayer::new(session_store);
    let shutdown_state = Arc::clone(&shared);

    // MCP native transport — feature-flagged, registered before the catch-all layer.
    // No .with_state() here — shared state is applied at the app level below.
    let mcp_router: Router<Arc<AppState>> = if shared.config.mcp_native {
        Router::new()
            .route(
                "/mcp",
                get(routes::mcp_native::sse_handler).post(routes::mcp_native::stateless_handler),
            )
            .route("/mcp/message", post(routes::mcp_native::message_handler))
    } else {
        Router::new()
    };

    let app = Router::new()
        .route("/_pin", get(get_pin_page))
        .route("/_pin_check", post(post_pin_check))
        .route("/api/lock/activate", post(post_lock_activate))
        .route("/api/lock/unlock", post(post_lock_unlock))
        .route("/api/lock/status", get(get_lock_status))
        .route("/api/auth/status", get(get_auth_status))
        .route("/api/auth/logout", post(post_auth_logout))
        .route("/api/server/restart", post(routes::server_restart::restart))
        .route("/api/files", get(routes::files::list_files))
        .route(
            "/api/original/{file_id}",
            get(routes::files::serve_original),
        )
        .route("/api/preview/{file_id}", get(routes::files::serve_preview))
        .route(
            "/api/thumbnail/{file_id}",
            get(routes::files::serve_thumbnail),
        )
        .route(
            "/api/thumbnails/batch",
            post(routes::files::thumbnails_batch),
        )
        .route(
            "/api/thumbnails/warmup",
            post(routes::files::thumbnails_warmup),
        )
        .route("/api/search", get(routes::search::search))
        .route("/api/search-count", get(routes::search::search_count))
        .route("/api/stats", get(routes::stats::stats_basic))
        .route("/api/stats/all", get(routes::stats::stats_all))
        .route("/api/stats/timeline", get(routes::stats::stats_timeline))
        .route("/api/stats/hourly", get(routes::stats::stats_hourly))
        .route("/api/stats/models", get(routes::stats::stats_models))
        .route(
            "/api/stats/resolutions",
            get(routes::stats::stats_resolutions),
        )
        .route("/api/stats/story", get(routes::stats::stats_story))
        .route(
            "/api/stats/monthly-report",
            get(routes::monthly_report::monthly_report),
        )
        .route("/api/search-grouped", get(routes::search::search_grouped))
        .route(
            "/api/search-grouped/warm",
            get(routes::search::search_grouped_warm),
        )
        .route(
            "/api/recipe/export/{file_id}",
            get(routes::recipe::recipe_export),
        )
        .route("/api/ratings/get", get(routes::ratings::ratings_get))
        .route("/api/ratings/stats", get(routes::ratings::ratings_stats))
        .route("/api/ratings/set", post(routes::ratings::ratings_set))
        .route("/api/ratings/batch", post(routes::ratings::ratings_batch))
        // Agent Safety Gateway — Kill Switch (Phase 1 native port)
        .route("/api/agent/kill", post(routes::agent::agent_kill))
        .route("/api/agent/resume", post(routes::agent::agent_resume))
        // Agent governance — Tool Classification (Phase D-1 native port)
        .route(
            "/api/agent/tool-levels",
            get(routes::agent_scope::tool_levels),
        )
        // Agent governance — Audit log reads (Phase C1 native port)
        .route("/api/agent/audit", get(routes::agent_audit::audit_status))
        .route("/api/agent/audit/log", get(routes::agent_audit::audit_log))
        .route(
            "/api/agent/audit/verify",
            get(routes::agent_audit::audit_verify),
        )
        // Agent governance — Action Journal reads (Phase B1 native port)
        .route(
            "/api/agent/journal",
            get(routes::agent_journal::agent_journal),
        )
        .route(
            "/api/agent/journal/stats",
            get(routes::agent_journal::agent_journal_stats),
        )
        .route(
            "/api/agent/undoable",
            get(routes::agent_journal::agent_undoable),
        )
        .route(
            "/api/agent/audit/acknowledge/{audit_id}",
            post(routes::agent_audit::audit_acknowledge),
        )
        // Agent governance — Scope Fence reads (Phase B); POST/DELETE stay on the
        // Python proxy (preset->denied expansion lives only in Python).
        .route(
            "/api/agent/scope",
            get(routes::agent_scope_store::scope_status),
        )
        .route(
            "/api/agent/auto-approve",
            get(routes::agent_scope_store::auto_approve_list)
                .post(routes::agent_scope_store::auto_approve_add),
        )
        .route(
            "/api/agent/auto-approve/{index}",
            delete(routes::agent_scope_store::auto_approve_delete),
        )
        .route(
            "/api/agent/scope/{session_id}",
            get(routes::agent_scope_store::scope_get)
                .post(routes::agent_scope_store::scope_set)
                .delete(routes::agent_scope_store::scope_delete),
        )
        // Source browser — read-only filesystem reads (tree/read/search). search
        // shells out to the same rg as Python for byte-identical results.
        .route(
            "/api/source/tree",
            get(routes::source_browser::source_tree_handler),
        )
        .route(
            "/api/source/read",
            get(routes::source_browser::source_read_handler),
        )
        .route(
            "/api/source/search",
            get(routes::source_browser::source_search_handler),
        )
        .route(
            "/api/ratings/batch-set",
            post(routes::ratings::ratings_batch_set),
        )
        .route(
            "/api/wd-tagger/profiles",
            get(routes::wd_tagger::profiles).post(routes::wd_tagger::profile_create),
        )
        .route(
            "/api/wd-tagger/profiles/{id}",
            get(routes::wd_tagger::profile_get)
                .put(routes::wd_tagger::profile_update)
                .delete(routes::wd_tagger::profile_delete),
        )
        .route(
            "/api/wd-tagger/active-model",
            get(routes::wd_tagger::active_model).put(routes::wd_tagger::active_model_update),
        )
        .route(
            "/api/wd-tagger/model/status",
            get(routes::wd_tagger::model_status),
        )
        .route("/api/wd-tagger/stats", get(routes::wd_tagger::stats))
        .route("/api/wd-tagger/untagged", get(routes::wd_tagger::untagged))
        .route(
            "/api/wd-tagger/config",
            get(routes::wd_tagger::config).post(routes::wd_tagger::config_save),
        )
        .route(
            "/api/wd-tagger/auto-tag-on-import",
            post(routes::wd_tagger::auto_tag_on_import_config_save),
        )
        .route("/api/wd-tagger/xmp/{file_id}", get(routes::wd_tagger::xmp))
        .route("/api/wd-tagger/vlm/test", get(routes::wd_tagger::vlm_test))
        .route(
            "/api/wd-tagger/vlm/models",
            get(routes::wd_tagger::vlm_models),
        )
        .route(
            "/api/collections",
            get(routes::collections::list).post(routes::collections::create),
        )
        .route(
            "/api/collections/reorder",
            post(routes::collections::reorder),
        )
        .route(
            "/api/collections/{id}",
            put(routes::collections::update).delete(routes::collections::delete),
        )
        .route(
            "/api/collections/{id}/batch-add",
            post(routes::collections::batch_add),
        )
        .route(
            "/api/collections/{id}/batch-remove",
            post(routes::collections::batch_remove),
        )
        .route(
            "/api/hailo-tagger/config",
            get(routes::hailo_tagger::config).post(routes::hailo_tagger::config_update),
        )
        .route(
            "/api/hailo-tagger/status",
            get(routes::hailo_tagger::status),
        )
        .route(
            "/api/hailo-tagger/tags/{file_id}",
            get(routes::hailo_tagger::tags).delete(routes::hailo_tagger::tags_delete),
        )
        .route(
            "/api/hailort/yolo/metadata",
            get(routes::hailort::yolo_metadata),
        )
        .route(
            "/api/hailort/yolo/smoke-zero",
            post(routes::hailort::yolo_smoke_zero),
        )
        .route(
            "/api/hailort/speech2text/tokenize",
            post(routes::hailort::speech2text_tokenize),
        )
        .route(
            "/api/hailort/llm/tokenize",
            post(routes::hailort::llm_tokenize),
        )
        .route(
            "/api/hailort/llm/generate",
            post(routes::hailort::llm_generate),
        )
        .route("/api/favorites/check", get(routes::favorites::check))
        .route("/api/favorites/toggle", post(routes::favorites::toggle))
        .route(
            "/api/favorites/check_collections",
            get(routes::favorites::check_collections),
        )
        .route("/api/favorites/list", get(routes::favorites::list))
        .route(
            "/api/maintenance/db-stats",
            get(routes::maintenance::db_stats),
        )
        .route(
            "/api/maintenance/scan-error-stats",
            get(routes::maintenance::scan_error_stats),
        )
        .route("/api/maintenance/vacuum", post(routes::maintenance::vacuum))
        .route(
            "/api/maintenance/analyze",
            post(routes::maintenance::analyze),
        )
        .route(
            "/api/diagnostics/safe-mode",
            get(routes::diagnostics::safe_mode),
        )
        .route(
            "/api/diagnostics/open-repair-folder",
            post(routes::diagnostics::open_repair_folder),
        )
        .route(
            "/api/diagnostics/cleanup-update-pending",
            post(routes::diagnostics::cleanup_update_pending),
        )
        .route("/api/checkpoints", get(routes::scan_roots::checkpoints))
        .route(
            "/api/server-info",
            get(routes::server_info::api_server_info),
        )
        .route("/api/server/mode", get(routes::server_info::server_mode))
        .route(
            "/api/server/subsystems",
            get(routes::server_info::server_subsystems),
        )
        .route("/api/headroom/livez", get(routes::headroom::headroom_livez))
        .route(
            "/api/headroom/readyz",
            get(routes::headroom::headroom_readyz),
        )
        .route(
            "/api/headroom/health",
            get(routes::headroom::headroom_health),
        )
        .route("/api/headroom/stats", get(routes::headroom::headroom_stats))
        .route(
            "/api/headroom/stats-history",
            get(routes::headroom::headroom_stats_history),
        )
        .route(
            "/api/headroom/metrics",
            get(routes::headroom::headroom_metrics),
        )
        .route(
            "/api/gateway/headroom/config",
            get(routes::headroom::headroom_config)
                .put(routes::headroom::gateway_headroom_config_put),
        )
        .route("/api/svg/info", get(routes::svg_info::svg_info))
        .route(
            "/api/system/update/status",
            get(routes::update_status::update_status),
        )
        .route(
            "/api/admin/shutdown/info",
            get(routes::admin::shutdown_info),
        )
        .route("/api/admin/shutdown", post(routes::admin::shutdown))
        .route(
            "/api/scan-roots",
            get(routes::scan_roots::scan_roots).post(routes::scan_roots::add_scan_root),
        )
        .route(
            "/api/scan-roots/batch-toggle",
            post(routes::scan_roots::batch_toggle_scan_roots),
        )
        .route(
            "/api/scan-roots/reorder",
            post(routes::scan_roots::reorder_scan_roots),
        )
        .route(
            "/api/scan-roots/recovery-check",
            get(routes::scan_roots::recovery_check),
        )
        .route(
            "/api/scan-roots/recovery-apply",
            post(routes::scan_roots::recovery_apply),
        )
        .route(
            "/api/scan-roots/recovery-dismiss",
            post(routes::scan_roots::recovery_dismiss),
        )
        .route("/api/scanned-roots", get(routes::scan_roots::scanned_roots))
        .route("/api/debug/enabled", get(routes::debug::enabled))
        .route("/api/debug/model-check", get(routes::debug::model_check))
        .route(
            "/api/debug/file-meta/{file_id}",
            get(routes::debug::file_meta),
        )
        .route("/api/scan-errors", get(routes::scan_errors::list))
        .route(
            "/api/scan-errors/clear",
            post(routes::scan_errors::clear_resolved_scan_errors),
        )
        .route(
            "/api/scan-roots/{index}",
            get(routes::scan_roots::get_scan_root)
                .put(routes::scan_roots::edit_scan_root)
                .delete(routes::scan_roots::remove_scan_root),
        )
        .route(
            "/api/scan-roots/{index}/toggle",
            post(routes::scan_roots::toggle_scan_root),
        )
        .route(
            "/api/scan-errors/{error_id}/resolve",
            post(routes::scan_errors::resolve_scan_error),
        )
        .route("/api/groups-index", get(routes::groups::groups_index))
        .route(
            "/api/groups-index/warm",
            get(routes::groups::groups_index_warm),
        )
        .route("/api/group-members", get(routes::groups::group_members))
        .route(
            "/api/container-thumb-ids",
            get(routes::groups::container_thumb_ids),
        )
        .route(
            "/api/files/{file_id}/analysis-trace",
            get(routes::file_trace::analysis_trace),
        )
        .route(
            "/api/file/{file_id}",
            get(routes::file_detail::get_file_detail),
        )
        .route("/api/sweeps/history", get(routes::sweeps::history))
        .route("/api/sweep/info/{file_id}", get(routes::sweeps::info))
        .route("/api/sweep/files/{sweep_id}", get(routes::sweeps::files))
        .route(
            "/api/wd-tagger/tags/batch",
            delete(routes::tag_reads::delete_wd_tags_batch),
        )
        .route(
            "/api/wd-tagger/tags/{file_id}",
            get(routes::tag_reads::wd_tags).delete(routes::tag_reads::delete_wd_tags),
        )
        .route(
            "/api/tagger-servers/tags/{file_id}",
            get(routes::tag_reads::tagger_server_tags)
                .delete(routes::tag_reads::delete_tagger_server_tags),
        )
        .route(
            "/api/file-info/{file_id}",
            get(routes::zip_files::file_info),
        )
        .route(
            "/api/container-members/{file_id}",
            get(routes::zip_files::container_members),
        )
        .route("/api/help/toc", get(routes::help::help_toc))
        .route("/api/help/search", get(routes::help::help_search))
        .route(
            "/api/help/content/{section}",
            get(routes::help::help_content),
        )
        .route(
            "/api/settings/llm-endpoints",
            get(routes::llm_endpoints::list_llm_endpoints)
                .put(routes::llm_endpoints::update_llm_endpoints),
        )
        .route(
            "/api/settings/llm-endpoints/{category}",
            delete(routes::llm_endpoints::delete_endpoint),
        )
        .route(
            "/api/llm/agent/capabilities",
            get(routes::llm_endpoints::agent_capabilities),
        )
        .route(
            "/api/settings/schema",
            get(routes::settings::api_settings_schema),
        )
        .route("/api/settings/all", get(routes::settings::api_settings_all))
        .route(
            "/api/settings/secrets/status",
            get(routes::settings::api_secrets_status),
        )
        .route(
            "/api/webhooks",
            get(routes::webhook::list_webhooks).post(routes::webhook::create_webhook),
        )
        .route(
            "/api/webhooks/deliveries",
            get(routes::webhook::list_deliveries),
        )
        .route(
            "/api/webhooks/inbound",
            get(routes::webhook::list_inbound_webhooks)
                .post(routes::webhook::create_inbound_webhook),
        )
        .route(
            "/api/webhooks/inbound/{wh_id}",
            put(routes::webhook::update_inbound_webhook)
                .delete(routes::webhook::delete_inbound_webhook),
        )
        .route(
            "/api/webhooks/{wh_id}",
            put(routes::webhook::update_webhook).delete(routes::webhook::delete_webhook),
        )
        .route(
            "/api/webhooks/{wh_id}/test",
            post(routes::webhook::test_webhook),
        )
        .route(
            "/api/github/accounts",
            get(routes::github::list_accounts).post(routes::github::add_account),
        )
        .route(
            "/api/github/accounts/{label}",
            put(routes::github::update_account).delete(routes::github::remove_account),
        )
        .route(
            "/api/github/rate-limit/{label}",
            get(routes::github::rate_limit),
        )
        .route(
            "/api/github/issues/{label}",
            get(routes::github::fetch_issues).post(routes::github::create_issue),
        )
        .route(
            "/api/github/issue/{label}/{owner}/{repo}/{number}",
            get(routes::github::get_issue_detail),
        )
        .route(
            "/api/github/triage-prompts",
            get(routes::github::get_triage_prompts).put(routes::github::save_triage_prompts),
        )
        .route(
            "/api/github/pulls/{label}",
            get(routes::github::fetch_pulls),
        )
        .route(
            "/api/github/pull/{label}/{owner}/{repo}/{number}",
            get(routes::github::get_pull_detail),
        )
        .route(
            "/api/github/notifications/{label}",
            get(routes::github::get_notifications),
        )
        .route(
            "/api/github/notifications/{label}/mark-all-read",
            post(routes::github::mark_all_notifications_read),
        )
        .route(
            "/api/github/notifications/{label}/{thread_id}",
            axum::routing::patch(routes::github::mark_notification_read),
        )
        .route(
            "/api/github/discussions/{label}",
            get(routes::github::get_discussions),
        )
        .route(
            "/api/github/releases/{label}",
            get(routes::github::get_releases),
        )
        .route(
            "/api/github/repo-stats/{label}/{owner}/{repo}",
            get(routes::github::get_repo_stats),
        )
        .route(
            "/api/github/repo-stats-all/{label}",
            get(routes::github::get_all_repo_stats),
        )
        .route("/api/github/queue", get(routes::github::get_issue_queue))
        .route(
            "/api/github/queue/pending",
            get(routes::github::get_pending_queue),
        )
        .route(
            "/api/github/queue/config",
            get(routes::github::get_queue_config).put(routes::github::save_queue_config),
        )
        .route(
            "/api/settings/config",
            get(routes::settings::api_settings_config)
                .post(routes::settings::api_settings_config_save),
        )
        .route(
            "/api/settings/config/legacy-migration",
            get(routes::settings::api_settings_config_legacy_migration)
                .post(routes::settings::api_settings_config_legacy_migration_run),
        )
        .route("/api/share/{file_id}", get(routes::share::api_share_data))
        .route(
            "/api/settings/op-status",
            get(routes::settings::api_settings_op_status),
        )
        .route(
            "/api/settings/bw-status",
            get(routes::settings::api_settings_bw_status),
        )
        .route(
            "/api/settings/op-mapping/{*key}",
            delete(routes::settings::api_settings_op_mapping_delete),
        )
        .route(
            "/api/settings/bw-mapping/{*key}",
            delete(routes::settings::api_settings_bw_mapping_delete),
        )
        .route(
            "/api/settings/secrets/export",
            post(routes::settings::api_secrets_export),
        )
        .route(
            "/api/settings/secrets/import",
            post(routes::settings::api_secrets_import),
        )
        .route(
            "/api/settings/secrets/migrate",
            post(routes::settings::api_secrets_migrate),
        )
        .route(
            "/api/settings/secrets/migrate-keychain",
            post(routes::settings::api_secrets_migrate_keychain),
        )
        .route(
            "/api/settings/secrets/rotate",
            post(routes::settings::api_secrets_rotate),
        )
        .route(
            "/api/settings/secrets/keyring",
            get(routes::settings::api_secrets_keyring),
        )
        .route(
            "/api/settings/secrets/bw-folders",
            get(routes::settings::api_secrets_bw_folders),
        )
        .route(
            "/api/settings/secrets/push-to-bw",
            post(routes::settings::api_secrets_push_to_bw),
        )
        .route(
            "/api/settings/secrets/op-vaults",
            get(routes::settings::api_secrets_op_vaults),
        )
        .route(
            "/api/settings/secrets/push-to-op",
            post(routes::settings::api_secrets_push_to_op),
        )
        .route(
            // Must be registered before the `/api/settings/{*key}` catch-all
            // below: without it the UI's request matched the catch-all and got
            // a 200 describing a settings key named "config-toml" -- a wrong
            // answer shaped like a right one.
            "/api/settings/config-toml",
            get(routes::settings::api_settings_config_toml_get)
                .post(routes::settings::api_settings_config_toml_save),
        )
        .route(
            "/api/settings/{*key}",
            get(routes::settings::api_settings_get).put(routes::settings::api_settings_put),
        )
        .route(
            "/api/analysis/available-engines",
            get(routes::analysis::available_engines),
        )
        // Analysis server management — config CRUD batch 1 (native port)
        .route(
            "/api/analysis/servers",
            post(routes::analysis_servers::add_server),
        )
        .route(
            "/api/analysis/servers/reorder",
            put(routes::analysis_servers::reorder_servers),
        )
        .route(
            "/api/analysis/servers/{server_id}/activate",
            post(routes::analysis_servers::activate_server),
        )
        // Server remove/update (batch 2); legacy update preserves stored encrypted keys.
        .route(
            "/api/analysis/servers/{server_id}",
            delete(routes::analysis_servers::remove_server)
                .put(routes::analysis_servers::update_server),
        )
        .route(
            "/api/analysis/ollama/models",
            get(routes::analysis::ollama_models),
        )
        .route(
            "/api/analysis/openai-compat/models",
            get(routes::analysis::openai_compat_models),
        )
        .route(
            "/api/analysis/servers/discovered",
            get(routes::analysis::discovered_servers),
        )
        .route("/api/analysis/servers", get(routes::analysis::servers))
        .route(
            "/api/analysis/trends/history",
            get(routes::analysis::trend_history),
        )
        .route(
            "/api/analysis/result/{file_id}",
            get(routes::analysis_results::result),
        )
        .route("/api/analysis/stats", get(routes::analysis_results::stats))
        .route(
            "/api/video-analysis/config",
            get(routes::video_analysis::config).post(routes::video_analysis::config_save),
        )
        .route(
            "/api/video-analysis/status",
            get(routes::video_analysis::status),
        )
        .route("/api/trophies", get(routes::trophies::list))
        .route("/api/tagger-servers", get(routes::tagger_servers::list))
        .route(
            "/api/tagger-servers/health",
            get(routes::tagger_servers::health),
        )
        .route(
            "/api/tagger-servers/stats",
            get(routes::tagger_servers::stats),
        )
        .route("/api/ui/list", get(routes::ui::ui_list))
        .route(
            "/api/inference/{*path}",
            any(routes::inference_proxy::proxy),
        )
        .route(
            "/api/files/{file_id}/tags",
            get(routes::tags::list_tags).post(routes::tags::add_tag),
        )
        .route(
            "/api/files/{file_id}/tags/{tag_id}",
            delete(routes::tags::delete_tag),
        )
        // scan status is owned by the Python scan worker (separate process +
        // file IPC); proxy it so real progress is returned instead of a Rust
        // idle-stub that lied during active scans. See routes/jobs.rs for the
        // jobs/status merge rationale.
        .route("/api/scan/status", get(routes::scan_admin::scan_status))
        .route(
            "/api/scan/interrupted",
            get(routes::auto_stubs::scan_interrupted),
        )
        .route("/api/agent/status", get(routes::auto_stubs::agent_status))
        .route(
            "/api/agent/approval",
            get(routes::auto_stubs::agent_approval),
        )
        .route(
            "/api/apikeys",
            get(routes::auto_stubs::apikeys_list).post(routes::apikeys::create_apikey),
        )
        .route(
            "/api/apikeys/{key_id}",
            axum::routing::patch(routes::apikeys::update_apikey)
                .delete(routes::apikeys::delete_apikey),
        )
        .route("/api/extensions", get(routes::auto_stubs::list_extensions))
        .route(
            "/api/tools/cache-info",
            get(routes::auto_stubs::tools_cache_info),
        )
        .route(
            "/api/tools/debug-log",
            get(routes::tools_debug_log::debug_log),
        )
        .route(
            "/api/tools/debug-log/download",
            get(routes::tools_debug_log::debug_log_download),
        )
        .route(
            "/api/tools/debug-log/clear",
            post(routes::tools_debug_log::debug_log_clear),
        )
        .route(
            "/api/tools/backup/list",
            get(routes::backup_read::backup_list),
        )
        .route(
            "/api/tools/backup/status",
            get(routes::backup_read::backup_status),
        )
        .route(
            "/api/tools/backup/create",
            post(db_backup::routes::backup_create),
        )
        .route(
            "/api/tools/backup/restore",
            post(db_backup::routes::backup_restore),
        )
        .route(
            "/api/tools/backup/delete",
            post(db_backup::routes::backup_delete),
        )
        .route(
            "/api/tools/backup-download",
            get(db_backup::routes::backup_download),
        )
        .route(
            "/v1/chat/completions",
            post(routes::auto_stubs::stub_unavailable),
        )
        .route("/v1/messages", post(routes::auto_stubs::stub_unavailable))
        .route(
            "/api/gateway/groups",
            get(routes::auto_stubs::gateway_groups),
        )
        .route(
            "/api/gateway/defaults",
            get(routes::auto_stubs::gateway_defaults),
        )
        .route(
            "/api/gateway/scan/stream",
            get(routes::auto_stubs::gateway_scan_stream),
        )
        .route(
            "/api/gateway/scan",
            delete(routes::auto_stubs::gateway_scan_delete),
        )
        .route(
            "/api/gateway/backends",
            get(routes::auto_stubs::gateway_backends_list)
                .post(routes::auto_stubs::stub_unavailable)
                .patch(routes::auto_stubs::gateway_backends_patch),
        )
        .route(
            "/api/gateway/backends/scan",
            post(routes::auto_stubs::stub_unavailable),
        )
        .route(
            "/api/gateway/backends/{id}",
            delete(routes::auto_stubs::stub_unavailable),
        )
        .route(
            "/api/gateway/auth/status",
            get(routes::auto_stubs::gateway_auth_status),
        )
        .route(
            "/api/gateway/local/status",
            get(routes::auto_stubs::gateway_local_status),
        );

    #[cfg(feature = "ocr")]
    let app = app
        .route("/api/ocr/npu", get(routes::ocr_npu::ocr_npu))
        .route("/api/ocr/profiles", get(routes::ocr::ocr_profiles_list))
        .route(
            "/api/ocr/profiles/fetch",
            post(routes::ocr::ocr_profiles_fetch),
        )
        // `/api/ocr/cancel` must be declared before `/api/ocr/{file_id}`:
        // matchit prefers a static segment over a parameter, but keeping them
        // adjacent makes the dependency visible. Without this route the cancel
        // handler is unreachable and the run_id check it performs is dead.
        .route("/api/ocr/cancel", post(routes::ocr_jobs::ocr_cancel))
        .route("/api/ocr/{file_id}", post(routes::ocr_jobs::ocr_single))
        .route(
            "/api/ocr/result/{file_id}",
            get(routes::ocr::ocr_result_get).delete(routes::ocr::ocr_result_delete),
        )
        .route("/api/ocr/engines", get(routes::ocr::ocr_engines))
        .route("/api/ocr/batch", post(routes::ocr_jobs::ocr_batch))
        .route("/api/ocr/export/{file_id}", get(routes::ocr::ocr_export))
        .route("/api/ocr/export/batch", post(routes::ocr::ocr_export_batch))
        .route(
            "/api/ocr/translate/{file_id}",
            post(routes::ocr::ocr_translate),
        )
        .route(
            "/api/ocr/translations/{file_id}",
            get(routes::ocr::ocr_translations),
        )
        .route("/api/ocr/overlay/{file_id}", get(routes::ocr::ocr_overlay))
        .route("/api/ocr/benchmark", post(routes::ocr_jobs::ocr_benchmark))
        .route(
            "/api/ocr/benchmark/report/{report_id}",
            get(routes::ocr::ocr_benchmark_report),
        )
        .route(
            "/api/ocr/benchmark/cases",
            get(routes::ocr::ocr_benchmark_cases),
        )
        .route(
            "/api/ocr/profiles/{model_prefix}",
            put(routes::ocr::ocr_profiles_update),
        )
        .route(
            "/api/ocr/video/{file_id}",
            post(routes::ocr_jobs::ocr_video),
        )
        .route("/api/ocr/pdf/{file_id}", post(routes::ocr_jobs::ocr_pdf));

    #[cfg(not(feature = "ocr"))]
    let app = app;

    let app = app
        // Profiles (Rust native — full implementation, not stubs; see the
        // `profiles_tests` module in auto_stubs.rs)
        .route(
            "/api/profiles",
            get(routes::auto_stubs::profiles_list).post(routes::auto_stubs::profiles_create),
        )
        .route(
            "/api/profiles/import-preview",
            post(routes::auto_stubs::profiles_import_preview),
        )
        .route(
            "/api/profiles/import",
            post(routes::auto_stubs::profiles_import),
        )
        .route(
            "/api/profiles/{name}",
            get(routes::auto_stubs::profiles_get)
                .put(routes::auto_stubs::profiles_update)
                .delete(routes::auto_stubs::profiles_delete),
        )
        .route(
            "/api/profiles/{name}/duplicate",
            post(routes::auto_stubs::profiles_duplicate),
        )
        .route(
            "/api/profiles/{name}/rename",
            post(routes::auto_stubs::profiles_rename),
        )
        .route(
            "/api/profiles/{name}/favorite",
            post(routes::auto_stubs::profiles_favorite),
        )
        .route(
            "/api/profiles/{name}/export",
            get(routes::auto_stubs::profiles_export),
        )
        .route("/api/scan/history", get(routes::scan_history::scan_history))
        .route("/ext/watcher/info", get(routes::watcher::watcher_info))
        .route("/ext/watcher/start", post(routes::watcher::watcher_start))
        .route("/ext/watcher/stop", post(routes::watcher::watcher_stop))
        .route(
            "/ext/convert/sd-to-nai",
            post(routes::sd_nai_convert::sd_to_nai),
        )
        .route(
            "/ext/convert/nai-to-sd",
            post(routes::sd_nai_convert::nai_to_sd),
        )
        .route("/ext/convert/batch", post(routes::sd_nai_convert::batch))
        .route(
            "/ext/syntax/engine.js",
            get(routes::prompt_syntax::engine_js),
        )
        .route(
            "/ext/syntax/widget.js",
            get(routes::prompt_syntax::widget_js),
        )
        .route(
            "/ext/syntax/style.css",
            get(routes::prompt_syntax::style_css),
        )
        .route("/ext/syntax/analyze", post(routes::prompt_syntax::analyze))
        .route("/api/download/batch-zip", post(routes::download::batch_zip))
        .route("/api/annotations/notes", get(routes::annotations::notes))
        .route(
            "/api/annotations/notes-data",
            get(routes::annotations::notes_data),
        )
        .route(
            "/api/annotations/batch-set",
            post(routes::annotations::batch_set),
        )
        .route("/api/annotations/search", get(routes::annotations::search))
        .route(
            "/api/annotations/batch-delete",
            post(routes::annotations::batch_delete),
        )
        .route(
            "/api/annotations/{file_id}",
            get(routes::annotations::get_file_annotations),
        )
        .route(
            "/ext/favorites/api/batch-add",
            post(routes::ext_favorites::batch_add),
        )
        .route(
            "/ext/favorites/api/batch-remove",
            post(routes::ext_favorites::batch_remove),
        )
        .route(
            "/ext/favorites/api/images",
            get(routes::ext_favorites::images),
        )
        .route(
            "/ext/favorites/api/export/zip",
            get(routes::ext_favorites::export_zip),
        )
        .route(
            "/ext/favorites/api/export/folder",
            post(routes::ext_favorites::export_folder),
        )
        .route(
            "/ext/prompt-library/info",
            get(routes::prompt_library::info),
        )
        .route(
            "/ext/prompt-library/api/prompts/bulk-delete",
            post(routes::prompt_library::bulk_delete),
        )
        .route(
            "/ext/prompt-library/api/prompts/bulk-move",
            post(routes::prompt_library::bulk_move),
        )
        .route(
            "/ext/prompt-library/api/prompts/bulk-tag",
            post(routes::prompt_library::bulk_tag),
        )
        .route(
            "/ext/prompt-library/api/prompts/from-file",
            post(routes::prompt_library::from_file),
        )
        .route(
            "/ext/prompt-library/api/prompts/{pid}/folder",
            post(routes::prompt_library::assign_folder)
                .delete(routes::prompt_library::remove_folder),
        )
        .route(
            "/ext/prompt-library/api/prompts/{pid}/tags",
            post(routes::prompt_library::set_tags),
        )
        .route(
            "/ext/prompt-library/api/prompts/{pid}",
            get(routes::prompt_library::get_prompt)
                .put(routes::prompt_library::update_prompt)
                .delete(routes::prompt_library::delete_prompt),
        )
        .route(
            "/ext/prompt-library/api/prompts",
            get(routes::prompt_library::list_prompts).post(routes::prompt_library::create_prompt),
        )
        .route(
            "/ext/prompt-library/api/folders/{fid}",
            put(routes::prompt_library::update_folder)
                .delete(routes::prompt_library::delete_folder),
        )
        .route(
            "/ext/prompt-library/api/folders",
            get(routes::prompt_library::folders).post(routes::prompt_library::create_folder),
        )
        .route(
            "/ext/prompt-library/api/tags/{tid}",
            delete(routes::prompt_library::delete_tag),
        )
        .route(
            "/ext/prompt-library/api/tags",
            get(routes::prompt_library::tags).post(routes::prompt_library::create_tag),
        )
        .route(
            "/ext/prompt-library/api/export",
            get(routes::prompt_library::export_library),
        )
        .route(
            "/ext/prompt-library/api/import",
            post(routes::prompt_library::import_library),
        )
        .route(
            "/ext/md-viewer/api/scan-roots",
            get(routes::md_viewer::scan_roots).post(routes::md_viewer::save_scan_roots),
        )
        .route(
            "/ext/md-viewer/api/scan-roots/{index}",
            delete(routes::md_viewer::delete_scan_root),
        )
        .route("/ext/md-viewer/api/files", get(routes::md_viewer::files))
        .route(
            "/ext/md-viewer/api/files/{file_id}",
            get(routes::md_viewer::file_detail),
        )
        .route("/ext/md-viewer/api/stats", get(routes::md_viewer::stats))
        .route(
            "/ext/md-viewer/api/languages",
            get(routes::md_viewer::languages),
        )
        .route("/ext/md-viewer/api/scan", post(routes::md_viewer::scan))
        .route(
            "/ext/md-viewer/api/scan/status",
            get(routes::md_viewer::scan_status),
        )
        .route(
            "/ext/cross-search/api/search",
            get(routes::cross_search::search),
        )
        .route(
            "/ext/cross-search/api/txt/{file_id}",
            get(routes::cross_search::txt_detail),
        )
        .route(
            "/ext/cross-search/api/open-file",
            post(routes::cross_search::open_file),
        )
        .route(
            "/ext/cross-search/api/scan-roots",
            get(routes::cross_search::scan_roots).post(routes::cross_search::save_scan_roots),
        )
        .route(
            "/ext/cross-search/api/scan-roots/{idx}",
            delete(routes::cross_search::delete_scan_root),
        )
        .route(
            "/ext/cross-search/api/stats",
            get(routes::cross_search::stats),
        )
        .route(
            "/ext/cross-search/api/scan",
            post(routes::cross_search::scan),
        )
        .route(
            "/ext/cross-search/api/scan/stop",
            post(routes::cross_search::scan_stop),
        )
        .route(
            "/ext/cross-search/api/scan/status",
            get(routes::cross_search::scan_status),
        )
        .route(
            "/ext/chatlog/api/conversations",
            get(routes::chatlog::conversations),
        )
        .route(
            "/ext/chatlog/api/conversations/{conv_id}",
            get(routes::chatlog::conversation_detail).delete(routes::chatlog::delete_conversation),
        )
        .route("/ext/chatlog/api/search", get(routes::chatlog::search))
        .route("/ext/chatlog/api/stats", get(routes::chatlog::stats))
        .route(
            "/ext/chatlog/api/text-search",
            get(routes::chatlog::text_search),
        )
        .route(
            "/ext/chatlog/api/entities/search",
            get(routes::chatlog::entity_search),
        )
        .route(
            "/ext/chatlog/api/conversations/{conv_id}/entities",
            get(routes::chatlog::conversation_entities),
        )
        .route(
            "/ext/chatlog/api/conversations/{conv_id}/related",
            get(routes::chatlog::related_conversations),
        )
        .route(
            "/ext/chatlog/api/chat/topics/search",
            get(routes::chatlog::topics_search),
        )
        .route(
            "/ext/chatlog/api/chat/decisions",
            get(routes::chatlog::chat_decisions),
        )
        .route(
            "/ext/chatlog/api/chat/decisions/search",
            get(routes::chatlog::decisions_search),
        )
        .route(
            "/ext/chatlog/api/import-path",
            post(routes::auto_stubs::chatlog_import_path),
        )
        .route(
            "/ext/chatlog/api/import/status",
            get(routes::auto_stubs::chatlog_import_status),
        )
        .route(
            "/ext/chatlog/api/chat/reprocess",
            post(routes::auto_stubs::chatlog_reprocess),
        )
        .route(
            "/ext/chatlog/api/chat/reprocess/status",
            get(routes::auto_stubs::chatlog_reprocess_status),
        )
        .route(
            "/ext/chatlog/api/entities/reindex",
            post(routes::auto_stubs::chatlog_entities_reindex),
        )
        .route("/api/tag-dict/search", get(routes::tag_dictionary::search))
        .route("/api/tag-dict/info", get(routes::tag_dictionary::info))
        .route("/api/tag-dict/stats", get(routes::tag_dictionary::stats))
        .route("/api/tag-dict/import", post(routes::tag_dictionary::import))
        .route("/api/tag-dict/clear", delete(routes::tag_dictionary::clear))
        .route("/api/tag-dict/split", post(routes::tag_dictionary::split))
        .route(
            "/api/rust-migration/proxy-stats",
            get(routes::migration_stats::proxy_stats),
        )
        .merge(routes::nai_bridge::routes())
        .merge(routes::sd_webui_bridge::routes())
        .merge(routes::comfyui_bridge::routes())
        .merge(routes::lan_cowork::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_pairing::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_client::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_local_import::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_fleet_consent::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_fleet_allowlists::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_fleet_ops::routes().with_state(lc_state.clone()))
        .merge(routes::lan_cowork_settings::routes().with_state(lc_state.clone()))
        .merge(
            routes::lan_cowork_inbound_read::inbound_routes(native_daemon)
                .with_state(lc_state.clone()),
        )
        .merge(
            routes::lan_cowork_import_meta::import_routes(native_daemon)
                .with_state(lc_state.clone()),
        )
        .merge(routes::lan_cowork_fleet_ui::routes().with_state(lc_state.clone()))
        .route("/api/events/stream", get(sse::stream::handler))
        .route("/api/events/info", get(sse::info::handler))
        .merge(logs::router())
        .route("/api/jobs/status", get(routes::jobs::status))
        .route("/api/jobs/{job_id}", get(routes::jobs::get_job))
        .route("/api/jobs/{job_id}/cancel", post(routes::jobs::cancel))
        // video / audio analysis stubs
        .route(
            "/api/video-analysis/analyze",
            post(routes::auto_stubs::video_analysis_analyze),
        )
        .route(
            "/api/audio-analysis/transcribe",
            post(routes::auto_stubs::audio_analysis_transcribe),
        )
        .route(
            "/api/audio-analysis/status",
            get(routes::auto_stubs::audio_analysis_status),
        )
        // archive-cleanup stubs
        .route(
            "/api/tools/archive-cleanup/scan",
            post(routes::auto_stubs::archive_cleanup_scan),
        )
        .route(
            "/api/tools/archive-cleanup/execute",
            post(routes::auto_stubs::archive_cleanup_execute),
        )
        .route(
            "/api/tools/archive-cleanup/llm-verify",
            post(routes::auto_stubs::archive_cleanup_llm_verify),
        )
        .route(
            "/api/tools/archive-cleanup/llm-verify-batch",
            post(routes::auto_stubs::archive_cleanup_llm_verify_batch),
        )
        .route(
            "/api/tools/archive-cleanup/llm-config",
            get(routes::auto_stubs::archive_cleanup_llm_config)
                .post(routes::auto_stubs::archive_cleanup_llm_config),
        )
        .route(
            "/api/tools/archive-cleanup/list-models",
            post(routes::tools_ops::archive_cleanup_list_models),
        )
        .route(
            "/api/tools/find-duplicates",
            get(routes::tools_ops::find_duplicates_native),
        )
        .route(
            "/api/tools/normalize-tags",
            get(routes::tools_ops::normalize_tags),
        );

    #[cfg(feature = "ocr")]
    let app = app
        // ocr/bbox stub
        .route(
            "/api/ocr/bbox/{params}",
            get(routes::ocr::ocr_bbox).post(routes::ocr::ocr_bbox),
        );

    #[cfg(not(feature = "ocr"))]
    let app = app;

    let app = app
        // lan-share stubs
        .route(
            "/api/lan-share/create",
            post(routes::auto_stubs::lan_share_create),
        )
        .route(
            "/api/lan-share/revoke",
            post(routes::auto_stubs::lan_share_revoke),
        )
        // fleet peer management
        .merge(routes::lan_cowork_fleet_peers::routes().with_state(lc_state.clone()))
        .nest_service(
            "/ext/lan_cowork/fleet/static",
            ServeDir::new(
                shared
                    .config
                    .project_root
                    .join("extensions/builtin_lan_cowork/ui/fleet"),
            ),
        )
        .merge(routes::lan_cowork_fleet_dispatch::routes().with_state(lc_state.clone()))
        .route(
            "/ext/lora-dataset/tag-presets",
            get(routes::lora_dataset::list_presets).post(routes::lora_dataset::create_preset),
        )
        .route(
            "/ext/lora-dataset/tag-presets/{id}",
            put(routes::lora_dataset::update_preset).delete(routes::lora_dataset::delete_preset),
        )
        .route(
            "/ext/lora-dataset/projects",
            get(routes::lora_dataset::list_projects).post(routes::lora_dataset::create_project),
        )
        .route(
            "/ext/lora-dataset/projects/{id}",
            get(routes::lora_dataset::get_project)
                .put(routes::lora_dataset::update_project)
                .delete(routes::lora_dataset::delete_project),
        )
        .route(
            "/ext/lora-dataset/checkpoints",
            get(routes::auto_stubs::lora_dataset_checkpoints),
        )
        .route(
            "/ext/mcp-client/api/connections",
            get(routes::mcp_client::list_connections).post(routes::mcp_client::add_connection),
        )
        .route(
            "/ext/mcp-client/api/connections/{id}",
            put(routes::mcp_client::update_connection)
                .delete(routes::mcp_client::delete_connection),
        )
        // speech-to-text stubs
        .route(
            "/ext/speech-to-text/api/s2t/status",
            get(routes::auto_stubs::s2t_status),
        )
        .route(
            "/ext/speech-to-text/api/s2t/transcript/{file_id}",
            get(routes::annotations::s2t_transcript),
        )
        .route(
            "/ext/speech-to-text/api/s2t/transcribe-video",
            post(routes::auto_stubs::s2t_transcribe_video),
        )
        .route(
            "/ext/speech-to-text/api/s2t/batch-transcribe",
            post(routes::auto_stubs::s2t_batch_transcribe),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/start",
            post(routes::auto_stubs::s2t_stream_start),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/stop",
            post(routes::auto_stubs::s2t_stream_stop),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/status",
            get(routes::auto_stubs::s2t_stream_status),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/transcript",
            get(routes::auto_stubs::s2t_stream_transcript),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/export/txt",
            get(routes::auto_stubs::s2t_stream_export_txt),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/export/srt",
            get(routes::auto_stubs::s2t_stream_export_srt),
        )
        .route(
            "/ext/speech-to-text/api/s2t/stream/llm-process",
            post(routes::auto_stubs::s2t_stream_llm_process),
        )
        .route("/api/tools/scan", post(routes::auto_stubs::tools_scan))
        .route(
            "/api/tools/find-similar",
            get(routes::tools_ops::find_similar),
        )
        .nest_service("/static", ServeDir::new(&static_dir))
        .route("/sw.js", get(frontend::serve_sw))
        .route("/", get(frontend::index))
        .route("/search", get(frontend::search_redirect))
        .route("/stats", get(frontend::stats))
        .route("/story", get(frontend::story))
        .route("/tools", get(frontend::tools))
        .route("/extensions", get(frontend::extensions))
        .route("/settings", get(frontend::settings))
        .route("/diagnostics", get(frontend::diagnostics))
        .route("/update", get(frontend::update))
        .route("/gateway", get(frontend::gateway))
        .route("/headroom", get(frontend::headroom))
        .route("/inspect", get(frontend::inspect))
        .route("/report", get(frontend::report))
        .route("/scheduler", get(frontend::scheduler))
        .route("/llm-router", get(frontend::llm_router))
        .route("/sweep/{sweep_id}", get(frontend::sweep_view))
        .route("/mesh-inference", get(frontend::mesh_inference))
        .route("/lan-cowork", get(frontend::lan_cowork))
        .route(
            "/lan-cowork/peers",
            get(frontend::lan_cowork_peers_redirect),
        )
        .route("/scan-jobs", get(frontend::scan_jobs))
        .route("/scan_jobs", get(frontend::scan_jobs_redirect))
        .route("/agent-journal", get(frontend::agent_journal))
        .route("/agent_journal", get(frontend::agent_journal_redirect))
        .route("/agent-memory", get(frontend::agent_memory))
        .route("/agent_memory", get(frontend::agent_memory_redirect))
        .route("/llm_router", get(frontend::llm_router_redirect))
        .route("/mesh_inference", get(frontend::mesh_inference_redirect))
        .route("/lan_cowork", get(frontend::lan_cowork_redirect))
        .route("/crypto_tools", get(frontend::crypto_tools_redirect))
        .route("/ext/nai-bridge", get(frontend::nai_bridge))
        .route("/ext/nai-bridge/", get(frontend::nai_bridge))
        .route("/ext/sd-webui", get(frontend::sd_webui))
        .route("/ext/sd-webui/", get(frontend::sd_webui))
        .route("/ext/comfyui-bridge", get(frontend::comfyui_bridge))
        .route("/ext/comfyui-bridge/", get(frontend::comfyui_bridge))
        .route("/ext/hailo-genai", get(frontend::hailo_genai))
        .route("/ext/hailo-genai/", get(frontend::hailo_genai))
        .route("/ext/hailo-genai/chat", get(frontend::hailo_genai_chat))
        .route("/ext/hailo-yolo", get(frontend::hailo_yolo))
        .route("/ext/hailo-yolo/", get(frontend::hailo_yolo))
        .route("/ext/hailo-semantic", get(frontend::hailo_semantic))
        .route("/ext/hailo-semantic/", get(frontend::hailo_semantic))
        .route(
            "/ext/annotations/notes",
            get(frontend::ext_annotations_notes),
        )
        .route("/ext/speech-to-text", get(frontend::ext_speech_to_text))
        .route("/ext/speech-to-text/", get(frontend::ext_speech_to_text))
        .route("/ext/lora-dataset", get(frontend::ext_lora_dataset))
        .route("/ext/lora-dataset/", get(frontend::ext_lora_dataset))
        .route("/ext/prompt-library", get(frontend::ext_prompt_library))
        .route("/ext/prompt-library/", get(frontend::ext_prompt_library))
        .route("/ext/prompt-sim", get(frontend::ext_prompt_sim))
        .route("/ext/prompt-sim/", get(frontend::ext_prompt_sim))
        .route(
            "/ext/prompt-sim/manager",
            get(frontend::ext_prompt_sim_manager),
        )
        .route(
            "/ext/prompt-sim/sweep-axes-manager",
            get(frontend::ext_prompt_sim_sweep),
        )
        .route("/ext/convert", get(frontend::ext_convert))
        .route("/ext/convert/", get(frontend::ext_convert))
        .route("/ext/chatlog", get(frontend::ext_chatlog))
        .route("/ext/chatlog/", get(frontend::ext_chatlog))
        .route("/ext/cross-search", get(frontend::ext_cross_search))
        .route("/ext/cross-search/", get(frontend::ext_cross_search))
        .route("/ext/favorites", get(frontend::ext_favorites))
        .route("/ext/favorites/", get(frontend::ext_favorites))
        .route("/ext/freeze-pullback", get(frontend::ext_freeze_pullback))
        .route("/ext/freeze-pullback/", get(frontend::ext_freeze_pullback))
        .route("/ext/md-viewer", get(frontend::ext_md_viewer))
        .route("/ext/md-viewer/", get(frontend::ext_md_viewer))
        .route("/ext/watcher", get(frontend::ext_watcher))
        .route("/ext/watcher/", get(frontend::ext_watcher))
        .route("/ext/github", get(frontend::ext_github))
        .route("/ext/github/", get(frontend::ext_github))
        .route("/ext/mcp-client", get(frontend::ext_mcp_client))
        .route("/ext/mcp-client/", get(frontend::ext_mcp_client))
        .route("/github", get(frontend::github_redirect))
        .route("/favicon.ico", get(routes::pages::favicon))
        .route("/api/convert", post(routes::pages::convert))
        .route("/api/suggest", get(routes::suggest::suggest))
        .route("/api/suggest/lora", get(routes::suggest::suggest_lora))
        .route(
            "/api/suggest/embedding",
            get(routes::suggest::suggest_embedding),
        )
        .route("/api/tags/suggest", get(routes::suggest::tags_suggest))
        .merge(routes::freeze_pullback::routes())
        .merge(mcp_router)
        // agent governance
        .route("/api/agent/anomaly", get(routes::agent_audit::anomaly))
        .route(
            "/api/agent/anomaly/alerts",
            get(routes::agent_audit::anomaly_alerts),
        )
        .route(
            "/api/agent/anomaly/reset",
            post(routes::agent_audit::anomaly_reset),
        )
        .route(
            "/api/agent/approval/history",
            get(routes::agent_audit::approval_history),
        )
        .route(
            "/api/agent/approval/{request_id}",
            post(routes::agent_audit::approval_respond),
        )
        .route(
            "/api/agent/audit/report",
            post(routes::agent_audit::audit_report),
        )
        .route("/api/agent/budget", get(routes::agent_audit::budget))
        .route(
            "/api/agent/budget/reset",
            post(routes::agent_audit::budget_reset),
        )
        .route(
            "/api/agent/circuit-breaker",
            get(routes::agent_audit::circuit_breaker),
        )
        .route(
            "/api/agent/circuit-breaker/reset",
            post(routes::agent_audit::circuit_breaker_reset),
        )
        .route(
            "/api/agent/undo/{journal_id}",
            post(routes::agent_audit::undo),
        )
        // ai context
        .route(
            "/api/ai-context",
            get(routes::misc_admin::ai_context).layer(axum::extract::Extension(native_daemon)),
        )
        // analysis
        .route(
            "/api/analysis/analyze/{file_id}",
            post(routes::analysis::analyze_file),
        )
        .route(
            "/api/analysis/batch",
            post(routes::analysis::analysis_batch),
        )
        .route(
            "/api/analysis/batch/cancel",
            post(routes::analysis::batch_cancel),
        )
        .route(
            "/api/analysis/config",
            get(routes::analysis::analysis_config_get).post(routes::analysis::analysis_config_post),
        )
        .route(
            "/api/analysis/ollama/test",
            post(routes::analysis::analysis_ollama_test),
        )
        .route(
            "/api/analysis/openai-compat/test",
            post(routes::analysis::analysis_openai_compat_test),
        )
        .route(
            "/api/analysis/servers/discovered/ignore",
            delete(routes::analysis::analysis_servers_discovered_ignore_delete)
                .post(routes::analysis::analysis_servers_discovered_ignore_post),
        )
        .route(
            "/api/analysis/servers/discovered/match",
            delete(routes::analysis::analysis_servers_discovered_match_delete)
                .post(routes::analysis::analysis_servers_discovered_match_post),
        )
        .route(
            "/api/analysis/servers/discovered/register",
            post(routes::analysis::analysis_servers_discovered_register),
        )
        .route(
            "/api/analysis/servers/discovered/test",
            post(routes::analysis::analysis_servers_discovered_test),
        )
        .route(
            "/api/analysis/servers/migrate",
            post(routes::analysis::analysis_servers_migrate),
        )
        .route(
            "/api/analysis/servers/{server_id}/test",
            post(routes::analysis_servers::test_server),
        )
        .route(
            "/api/analysis/trends",
            post(routes::analysis::analysis_trends),
        )
        .route(
            "/api/analysis/trends/history/{history_id}",
            delete(routes::analysis::analysis_trends_history_delete),
        )
        // collections
        .route(
            "/api/collections/{id}/export",
            get(routes::misc_admin::collections_export),
        )
        .route(
            "/api/collections/{id}/export/csv",
            get(routes::misc_admin::collections_export_csv),
        )
        // debug
        .route("/api/debug/query", post(routes::misc_admin::debug_query))
        // diagnostics
        .route(
            "/api/diagnostics/bug-report",
            post(routes::diagnostics::bug_report),
        )
        .route(
            "/api/diagnostics/doctor",
            post(routes::diagnostics::doctor_start),
        )
        .route(
            "/api/diagnostics/doctor/{job_id}",
            get(routes::diagnostics::doctor_status),
        )
        .route(
            "/api/diagnostics/zip-repair",
            post(routes::diagnostics::zip_repair),
        )
        // error report
        .route(
            "/api/error-report/enrich",
            post(routes::server_info::error_report_enrich),
        )
        // extensions
        .route(
            "/api/extensions/author/create",
            post(routes::extensions_admin::author_create),
        )
        .route(
            "/api/extensions/author/{name}/files",
            get(routes::extensions_admin::author_files),
        )
        .route(
            "/api/extensions/author/{name}/read",
            get(routes::extensions_admin::author_read),
        )
        .route(
            "/api/extensions/author/{name}/validate",
            post(routes::extensions_admin::author_validate),
        )
        .route(
            "/api/extensions/author/{name}/write",
            post(routes::extensions_admin::author_write),
        )
        .route(
            "/api/extensions/hooks",
            get(routes::extensions_admin::hooks),
        )
        .route(
            "/api/extensions/install",
            post(routes::extensions_admin::install),
        )
        .route(
            "/api/extensions/isolation",
            get(routes::extensions_admin::isolation),
        )
        .route(
            "/api/extensions/marketplace",
            get(routes::extensions_admin::marketplace),
        )
        .route(
            "/api/extensions/marketplace/refresh",
            post(routes::extensions_admin::marketplace_refresh),
        )
        .route(
            "/api/extensions/os-isolation",
            get(routes::extensions_admin::os_isolation),
        )
        .route(
            "/api/extensions/update-all",
            post(routes::extensions_admin::update_all_git),
        )
        .route(
            "/api/extensions/{name}",
            get(routes::extensions_admin::extension_detail),
        )
        .route(
            "/api/extensions/{name}/config",
            get(routes::extensions_admin::extension_config_get)
                .post(routes::extensions_admin::extension_config_post),
        )
        .route(
            "/api/extensions/{name}/integrity",
            get(routes::extensions_admin::extension_integrity),
        )
        .route(
            "/api/extensions/{name}/permissions",
            get(routes::extensions_admin::extension_permissions_get)
                .post(routes::extensions_admin::extension_permissions_post),
        )
        .route(
            "/api/extensions/{name}/rescan",
            post(routes::extensions_admin::extension_rescan),
        )
        .route(
            "/api/extensions/{name}/scan-results",
            get(routes::extensions_admin::extension_scan_results),
        )
        .route(
            "/api/extensions/{name}/toggle",
            post(routes::extensions_admin::extension_toggle),
        )
        .route(
            "/api/extensions/{name}/tokens",
            get(routes::extensions_admin::extension_tokens),
        )
        .route(
            "/api/extensions/{name}/uninstall",
            delete(routes::extensions_admin::uninstall_ext),
        )
        .route(
            "/api/extensions/{name}/update",
            post(routes::extensions_admin::update_git),
        )
        // zip extraction
        .route(
            "/api/extract-from-zip",
            post(routes::zip_files::extract_from_zip),
        )
        // hailo tagger — native Rust
        .route("/api/hailo-tagger/batch", post(routes::hailo_tagger::batch))
        .route(
            "/api/hailo-tagger/tag/{file_id}",
            post(routes::hailo_tagger::tag_file),
        )
        // hailo-genai extension API — proxy to Python (generation still hardware-bound)
        .route(
            "/ext/hailo-genai/api/runtime",
            get(routes::hailo_genai_chat::runtime),
        )
        .route(
            "/ext/hailo-genai/api/model/status",
            get(routes::auto_stubs::hailo_genai_model_status),
        )
        .route(
            "/ext/hailo-genai/api/model/download",
            post(routes::auto_stubs::hailo_genai_model_download),
        )
        .route(
            "/ext/hailo-genai/api/model/unload",
            post(routes::auto_stubs::hailo_genai_model_unload),
        )
        .route(
            "/ext/hailo-genai/api/llm/generate",
            post(routes::auto_stubs::hailo_genai_llm_generate),
        )
        .route(
            "/ext/hailo-genai/api/llm/clear-context",
            post(routes::auto_stubs::hailo_genai_llm_clear_context),
        )
        .route(
            "/ext/hailo-genai/api/vlm/generate",
            // Without this the handler's `body: Bytes` is truncated by axum's
            // 2 MiB DefaultBodyLimit, so an ordinary phone photo is rejected
            // before either the native path or the Python proxy sees it, and
            // the 16 MiB image cap inside the handler is unreachable.
            // The layer must exceed the image cap, not equal it: the body also
            // carries the multipart framing and the accompanying text fields
            // (prompt, model, system_prompt, generation settings), and Python
            // rejects only when the *image part* exceeds 16 MiB. 1 MiB of room
            // covers those; a request past this outer bound gets axum's
            // generic 413 rather than the handler's message, which is the
            // intended backstop.
            post(routes::auto_stubs::hailo_genai_vlm_generate).layer(
                axum::extract::DefaultBodyLimit::max(
                    routes::auto_stubs::VLM_MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024,
                ),
            ),
        )
        // hailo-genai chat: list/get/delete/rename/new/active/send are all
        // native Rust. new/active/send are migrated together as a single
        // unit (see hailo_genai_chat.rs module doc) to avoid the
        // active-conversation state-split bug fixed in commit 5e7ed834b —
        // send falls back to the Python proxy (verbatim, no native DB
        // writes) for image chat / web_search / subprocess mode.
        .route(
            "/ext/hailo-genai/api/chat/conversations",
            get(routes::hailo_genai_chat::list_conversations),
        )
        .route(
            "/ext/hailo-genai/api/chat/new",
            post(routes::hailo_genai_chat::chat_new),
        )
        .route(
            "/ext/hailo-genai/api/chat/active",
            get(routes::hailo_genai_chat::chat_active),
        )
        .route(
            "/ext/hailo-genai/api/chat/send",
            // The multipart body includes framing and text fields in addition
            // to the image part, so this outer cap needs headroom above the
            // native 16 MiB image limit. Requests beyond it get axum's 413.
            post(routes::hailo_genai_chat::chat_send).layer(axum::extract::DefaultBodyLimit::max(
                routes::auto_stubs::VLM_MAX_IMAGE_UPLOAD_BYTES + 1024 * 1024,
            )),
        )
        .route(
            "/ext/hailo-genai/api/chat/search",
            post(routes::hailo_web_search::chat_search),
        )
        .route(
            "/ext/hailo-genai/api/chat/conversations/{conversation_id}",
            get(routes::hailo_genai_chat::get_conversation)
                .delete(routes::hailo_genai_chat::delete_conversation),
        )
        .route(
            "/ext/hailo-genai/api/chat/conversations/{conversation_id}/title",
            axum::routing::patch(routes::hailo_genai_chat::rename_conversation),
        )
        // hailo-semantic extension API — native CLIP vector search (caption
        // routes remain Python-backed; they are intentionally out of scope).
        .route(
            "/ext/hailo-semantic/api/runtime",
            get(routes::clip_search::runtime_handler),
        )
        .route(
            "/ext/hailo-semantic/api/status",
            get(routes::clip_search::runtime_handler),
        )
        .route(
            "/ext/hailo-semantic/api/backends",
            get(routes::clip_search::backends_handler),
        )
        .route(
            "/ext/hailo-semantic/api/model/status",
            get(routes::clip_model::status_handler),
        )
        .route(
            "/ext/hailo-semantic/api/model/download",
            post(routes::clip_model::download_handler),
        )
        .route(
            "/ext/hailo-semantic/api/search",
            get(routes::clip_search::search_handler),
        )
        .route(
            "/ext/hailo-semantic/api/index/start",
            post(routes::clip_indexer::start_handler),
        )
        .route(
            "/ext/hailo-semantic/api/index/status",
            get(routes::clip_indexer::status_handler),
        )
        .route(
            "/ext/hailo-semantic/api/index/stop",
            post(routes::clip_indexer::stop_handler),
        )
        .route(
            "/ext/hailo-semantic/api/index/clear",
            post(routes::clip_indexer::clear_handler),
        )
        .route(
            "/ext/hailo-semantic/api/caption/start",
            post(routes::caption_runner::start_handler),
        )
        .route(
            "/ext/hailo-semantic/api/caption/status",
            get(routes::caption_runner::status_handler),
        )
        .route(
            "/ext/hailo-semantic/api/caption/stop",
            post(routes::caption_runner::stop_handler),
        )
        // hailo-yolo extension API — native handlers where supported
        .route(
            "/ext/hailo-yolo/api/runtime",
            get(routes::hailo_yolo_detect::runtime_handler),
        )
        .route(
            "/ext/hailo-yolo/api/labels",
            get(routes::hailo_yolo_detect::labels_handler),
        )
        .route(
            "/ext/hailo-yolo/api/model/status",
            get(routes::hailo_yolo_detect::model_status_handler),
        )
        .route(
            "/ext/hailo-yolo/api/model/download",
            post(routes::hailo_yolo_detect::model_download_handler),
        )
        .route(
            "/ext/hailo-yolo/api/detect/start",
            post(routes::hailo_yolo_detect::detect_start_handler),
        )
        .route(
            "/ext/hailo-yolo/api/detect/status",
            get(routes::hailo_yolo_detect::detect_status_handler),
        )
        .route(
            "/ext/hailo-yolo/api/detect/stop",
            post(routes::hailo_yolo_detect::detect_stop_handler),
        )
        .route(
            "/ext/hailo-yolo/api/detect/search",
            get(routes::hailo_yolo_detect::detect_search_handler),
        )
        .route(
            "/ext/hailo-yolo/api/detect/clear",
            post(routes::hailo_yolo_detect::detect_clear_handler),
        )
        // T9 cutover: all fifteen stream contracts are served by the native router.
        .merge(routes::hailo_yolo_stream::handlers::routes())
        .route(
            "/ext/hailo-yolo/api/detect/results/{file_id}",
            get(routes::hailo_yolo_detect::detect_results_handler),
        )
        .route(
            "/ext/hailo-genai/api/s2t/transcribe",
            // Same DefaultBodyLimit reasoning as the VLM image route: multer
            // itself has no cap, so without this layer axum's own 2 MiB
            // default truncates `body: Bytes` before the 32 MiB audio limit
            // inside the handler is ever reachable.
            post(routes::s2t::transcribe).layer(axum::extract::DefaultBodyLimit::max(
                routes::s2t::S2T_MAX_AUDIO_UPLOAD_BYTES + 1024 * 1024,
            )),
        )
        .route(
            "/ext/hailo-genai/api/s2t/transcribe-video",
            post(routes::s2t::transcribe_video),
        )
        .route(
            "/ext/hailo-genai/api/s2t/batch-transcribe",
            post(routes::s2t_runner::start_handler),
        )
        .route(
            "/ext/hailo-genai/api/s2t/transcript/{file_id}",
            get(routes::s2t::transcript),
        )
        .route(
            "/ext/hailo-genai/v1/models",
            get(routes::hailo_genai_chat::openai_models),
        )
        .route(
            "/ext/hailo-genai/v1/chat/completions",
            post(routes::auto_stubs::hailo_genai_v1_chat_completions),
        )
        .route(
            "/ext/hailo-genai/v1/audio/transcriptions",
            post(routes::s2t::openai_transcriptions).layer(axum::extract::DefaultBodyLimit::max(
                routes::s2t::S2T_MAX_AUDIO_UPLOAD_BYTES + 1024 * 1024,
            )),
        )
        .route(
            "/ext/hailo-genai/v1/embeddings",
            post(routes::auto_stubs::hailo_genai_v1_embeddings),
        )
        // hash backfill — native Rust
        .route(
            "/api/hash-backfill/cancel",
            post(routes::hash_backfill::cancel),
        )
        .route(
            "/api/hash-backfill/start",
            post(routes::hash_backfill::start),
        )
        .route(
            "/api/hash-backfill/status",
            get(routes::hash_backfill::status),
        )
        // llm
        .route("/api/llm/agent", post(routes::misc_admin::llm_agent))
        .route("/api/llm/chat", post(routes::misc_admin::llm_chat))
        .route(
            "/api/llm_router/backends/{alias}/disable",
            post(routes::llm_router_admin::llm_router_disable),
        )
        .route(
            "/api/llm_router/backends/{alias}/enable",
            post(routes::llm_router_admin::llm_router_enable),
        )
        .route(
            "/api/llm_router/refresh",
            post(routes::llm_router_admin::llm_router_refresh),
        )
        .route(
            "/api/llm_router/status",
            get(routes::llm_router_admin::llm_router_status),
        )
        // market — native Rust
        .route(
            "/api/market/quotes",
            get(routes::market_quotes::market_quotes),
        )
        // mdns — intentionally unauthenticated forwarder
        .route("/api/mdns/identity", get(routes::mdns::mdns_identity))
        .route("/api/mdns/peers", get(routes::mdns::mdns_peers))
        // mesh inference
        .route(
            "/api/mesh-inference/bulk",
            post(routes::mesh_inference::mesh_bulk),
        )
        .route(
            "/api/mesh-inference/refresh",
            post(routes::mesh_inference::mesh_refresh),
        )
        .route(
            "/api/mesh-inference/state",
            get(routes::mesh_inference::mesh_state),
        )
        .route(
            "/api/mesh-inference/toggle",
            post(routes::mesh_inference::mesh_toggle),
        )
        // open folder
        .route(
            "/api/open-folder/{file_id}",
            post(routes::zip_files::open_folder),
        )
        // recipe
        .route(
            "/api/recipe/export/batch",
            post(routes::recipe::recipe_export_batch),
        )
        .route("/api/recipe/import", post(routes::recipe::recipe_import))
        .route(
            "/api/recipe/import/batch",
            post(routes::recipe::recipe_import_batch),
        )
        // scan
        .route("/api/scan-all", post(routes::scan_admin::scan_all))
        .route("/api/scan/cancel", post(routes::scan_admin::scan_cancel))
        .route("/api/scan/dismiss", post(routes::scan_admin::scan_dismiss))
        .route(
            "/api/scan/history/clear",
            post(routes::scan_history::scan_history_clear),
        )
        .route("/api/scan/queue", get(routes::scan_admin::scan_queue_list))
        .route(
            "/api/scan/queue/clear",
            post(routes::scan_admin::scan_queue_clear),
        )
        .route(
            "/api/scan/queue/{queue_id}",
            delete(routes::scan_admin::scan_queue_remove),
        )
        .route("/api/scan/resume", post(routes::scan_admin::scan_resume))
        .route("/api/scan/start", post(routes::scan_admin::scan_start))
        .route(
            "/api/scanned-roots/purge",
            post(routes::scan_admin::scanned_roots_purge),
        )
        // scheduler
        .route(
            "/api/scheduler/history",
            get(routes::scheduler::scheduler_history),
        )
        .route(
            "/api/scheduler/jobs",
            get(routes::scheduler::scheduler_jobs).post(routes::scheduler::scheduler_add_job),
        )
        .route(
            "/api/scheduler/jobs/{job_id}",
            delete(routes::scheduler::scheduler_remove_job),
        )
        .route(
            "/api/scheduler/jobs/{job_id}/pause",
            post(routes::scheduler::scheduler_pause_job),
        )
        .route(
            "/api/scheduler/jobs/{job_id}/resume",
            post(routes::scheduler::scheduler_resume_job),
        )
        .route(
            "/api/scheduler/jobs/{job_id}/trigger",
            post(routes::scheduler::scheduler_trigger_job),
        )
        .route(
            "/api/scheduler/status",
            get(routes::scheduler::scheduler_status),
        )
        // search
        .route("/api/search-union", post(routes::misc_admin::search_union))
        // settings
        .route(
            "/api/settings/llm-endpoints/test",
            post(routes::llm_endpoints::test_endpoint_connection),
        )
        // sns
        .route(
            "/api/sns/bluesky/post",
            post(routes::misc_admin::sns_bluesky_post),
        )
        .route(
            "/api/sns/bluesky/test",
            post(routes::misc_admin::sns_bluesky_test),
        )
        .route(
            "/api/sns/config",
            get(routes::misc_admin::sns_config_get).post(routes::misc_admin::sns_config_post),
        )
        .route("/api/sns/preview", get(routes::misc_admin::sns_preview))
        .route("/api/sns/x/intent", get(routes::misc_admin::sns_x_intent))
        // svg
        .route("/api/svg/rasterize", post(routes::svg_info::svg_rasterize))
        // system
        .route(
            "/api/system/inference-info",
            get(routes::server_info::inference_info),
        )
        .route("/api/inspect", post(routes::misc_admin::inspect_upload))
        // Prompt Simulator (Phase 2 native port)
        .route(
            "/ext/prompt-sim/wildcards",
            get(routes::prompt_sim::wildcards),
        )
        .route(
            "/ext/prompt-sim/load-wildcards-zip",
            post(routes::prompt_sim::load_wildcards_zip),
        )
        .route(
            "/ext/prompt-sim/wildcard-file",
            post(routes::prompt_sim::wildcard_file_save),
        )
        .route(
            "/ext/prompt-sim/wildcard-rename",
            post(routes::prompt_sim::wildcard_rename),
        )
        .route(
            "/ext/prompt-sim/wildcard-delete",
            post(routes::prompt_sim::wildcard_delete),
        )
        .route(
            "/ext/prompt-sim/wildcard-dirs",
            post(routes::prompt_sim::wildcard_dirs_save),
        )
        .route(
            "/ext/prompt-sim/sweep-axes",
            get(routes::prompt_sim::sweep_axes),
        )
        .route(
            "/ext/prompt-sim/sweep-axis-config",
            post(routes::prompt_sim::sweep_axis_config_save),
        )
        .route("/ext/prompt-sim/convert", post(routes::prompt_sim::convert))
        .route(
            "/ext/prompt-sim/emphasis",
            post(routes::prompt_sim::emphasis),
        )
        .route(
            "/ext/prompt-sim/danbooru-ac",
            get(routes::prompt_sim::danbooru_ac),
        )
        .route(
            "/ext/prompt-sim/dp-analyze",
            post(routes::prompt_sim::dp_analyze),
        )
        .route(
            "/api/system/update/apply",
            post(routes::misc_admin::system_update_apply),
        )
        .route(
            "/api/system/update/check",
            get(routes::misc_admin::update_check),
        )
        .route(
            "/api/system/update/unified-apply",
            post(routes::misc_admin::system_update_unified_apply),
        )
        .route(
            "/api/system/update/unified-check",
            get(routes::misc_admin::update_unified_check),
        )
        // tagger servers
        .route(
            "/api/tagger-servers/batch",
            post(routes::tagger_servers::batch_tag),
        )
        .route(
            "/api/tagger-servers/batch/cancel",
            post(routes::tagger_servers::batch_cancel),
        )
        // tags
        .route("/api/tags/batch-set", post(routes::tags::batch_set))
        .route("/api/tags/dedup", post(routes::tags::dedup))
        // tauri shell
        .route(
            "/api/tauri-shell/tabs",
            get(routes::extensions_admin::tauri_shell_tabs),
        )
        // ui management
        .route("/api/ui/install", post(routes::ui::install))
        .route("/api/ui/switch", post(routes::ui::ui_switch))
        .route("/api/ui/{name}/uninstall", delete(routes::ui::uninstall))
        // update
        .route("/api/update/apply", post(routes::misc_admin::update_apply))
        .route(
            "/api/update/rollback",
            post(routes::misc_admin::update_rollback),
        )
        .route(
            "/api/update/verify",
            post(routes::misc_admin::update_verify),
        )
        // wd-tagger batch is native; retag/tag routes retain their existing handlers.
        .route(
            "/api/wd-tagger/batch",
            post(routes::wd_tagger_batch::batch_handler),
        )
        .route(
            "/api/wd-tagger/batch/cancel",
            post(routes::wd_tagger_batch::batch_cancel_handler),
        )
        .route(
            "/api/wd-tagger/model/download",
            post(routes::wd_tagger::model_download),
        )
        .route(
            "/api/wd-tagger/profiles/{id}/test",
            post(routes::wd_tagger::profile_test),
        )
        .route(
            "/api/wd-tagger/retag/backfill",
            post(routes::wd_tagger::retag_backfill),
        )
        .route(
            "/api/wd-tagger/retag/batch",
            post(routes::wd_tagger::retag_batch),
        )
        .route(
            "/api/wd-tagger/retag/cancel",
            post(routes::wd_tagger::retag_cancel),
        )
        .route(
            "/api/wd-tagger/retag/query",
            post(routes::wd_tagger::retag_query),
        )
        .route(
            "/api/wd-tagger/retag/single",
            post(routes::wd_tagger::retag_single),
        )
        .route(
            "/api/wd-tagger/tag/{file_id}",
            post(routes::wd_tagger::tag_file),
        )
        .route("/api/infer/wd-tagger", post(routes::wd_infer::infer))
        // workflow params
        .route(
            "/api/workflow-gen-params/{file_id}",
            get(routes::misc_admin::workflow_gen_params),
        )
        // sns/bsky routes
        .route(
            "/api/sns/bsky/queue",
            get(routes::misc_admin::sns_bsky_queue),
        )
        .route(
            "/api/sns/bsky/queue/pending",
            get(routes::misc_admin::sns_bsky_queue_pending),
        )
        .route(
            "/api/sns/bsky/monitor/config",
            get(routes::misc_admin::sns_bsky_monitor_config)
                .put(routes::misc_admin::sns_bsky_monitor_config_save),
        )
        .route(
            "/api/sns/bsky/monitor/triage-prompts",
            get(routes::misc_admin::sns_bsky_triage_prompts)
                .put(routes::misc_admin::sns_bsky_triage_prompts_save),
        )
        // non-/api/ gateway/frontend routes bridged to Python
        .route("/share", get(routes::misc_admin::page_share))
        .route("/tauri-shell", get(routes::misc_admin::page_tauri_shell))
        .route("/crypto-tools", get(routes::misc_admin::page_crypto_tools))
        .route("/help", get(routes::help::page_help))
        .route("/help/{section}", get(routes::help::page_help_section))
        .route("/backends", get(routes::misc_admin::page_backends))
        .route("/local/status", get(routes::misc_admin::page_local_status))
        .route("/groups", get(routes::misc_admin::page_groups))
        .route("/defaults", get(routes::misc_admin::page_defaults))
        // gateway API (corrected URL — previously misregistered at short paths)
        .route("/api/gateway/keys", get(routes::misc_admin::gateway_keys))
        .route(
            "/api/gateway/admin-token",
            get(routes::misc_admin::admin_token),
        )
        .route(
            "/agentmemory/livez",
            get(routes::misc_admin::agentmemory_livez),
        )
        .route(
            "/api/agentmemory-dash/livez",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/health",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/profile",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/sessions",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/memories",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/audit",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/graph/stats",
            get(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/graph/query",
            post(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/agentmemory-dash/{*sub}",
            any(routes::gateway_proxy::agentmemory_dash_handler),
        )
        .route(
            "/api/gateway/agentmemory/config",
            get(routes::misc_admin::agentmemory_config)
                .put(routes::misc_admin::gateway_agentmemory_config_put),
        )
        // SD backend proxy
        .route("/sd/config", get(routes::misc_admin::sd_config))
        .route("/sd/info", get(routes::misc_admin::sd_info))
        .route("/sd/internal/ping", get(routes::misc_admin::sd_ping))
        // LLM router meta
        .route("/v1/models", get(routes::misc_admin::llm_models))
        .route("/v1/router/health", get(routes::misc_admin::router_health))
        .route(
            "/v1/router/refresh",
            post(routes::misc_admin::router_refresh),
        )
        .route(
            "/v1/router/estimate",
            post(routes::misc_admin::router_estimate),
        )
        .route(
            "/v1/router/capabilities/{target}",
            get(routes::misc_admin::router_capabilities_target),
        )
        .route(
            "/v1/router/capabilities",
            get(routes::gateway_status::router_capabilities),
        )
        .route(
            "/v1/node/services",
            get(routes::gateway_status::node_services),
        )
        .route(
            "/ollama/{name}/{*sub}",
            any(routes::gateway_proxy::ollama_handler),
        )
        .route(
            "/sd/sdapi/v1/{*sub}",
            get(routes::gateway_proxy::sd_handler).post(routes::gateway_proxy::sd_handler),
        )
        .route("/sd/{*rest}", any(routes::auto_stubs::stub_unavailable))
        // tools_fs — filesystem helper endpoints (Phase 1)
        .route(
            "/api/tools/select-folder",
            get(routes::tools_fs::select_folder),
        )
        .route("/api/tools/list-dirs", get(routes::tools_fs::list_dirs))
        .route("/api/tools/file-search", get(routes::tools_fs::file_search))
        // tools_ops — tools-page operation endpoints (Phase 3)
        .route(
            "/api/tools/clear-cache",
            post(routes::tools_ops::clear_cache),
        )
        .route(
            "/api/tools/rebuild-groups",
            post(routes::tools_ops::rebuild_groups),
        )
        .route(
            "/api/tools/compute-hashes",
            post(routes::tools_ops::compute_hashes),
        )
        .route("/api/dnd-inbox", get(routes::tools_ops::dnd_inbox))
        .route(
            "/api/dnd-upload",
            post(routes::tools_ops::dnd_upload)
                .layer(axum::extract::DefaultBodyLimit::max(500 * 1024 * 1024)),
        )
        .route(
            "/api/files/register-path",
            post(routes::tools_ops::register_path),
        )
        .route(
            "/api/tools/delete-duplicates",
            post(routes::tools_ops::delete_duplicates),
        )
        .fallback(frontend::not_found)
        .layer(middleware::from_fn_with_state(
            Arc::clone(&shared),
            auth_middleware,
        ))
        // Outside auth, inside CSRF. `.layer()` is applied inside-out, so this
        // line sitting *after* auth_middleware means it runs *before* it --
        // which is the point: auth early-returns 401/423, so a limiter placed
        // inside it would cap authenticated users and leave attackers uncapped.
        // Mirrors Python's registration order (csrf -> ratelimit -> auth) at
        // request_hooks.py:71-92 / runtime_runner.py:249 vs :285.
        .layer(middleware::from_fn_with_state(
            Arc::clone(&shared),
            auth::api_rate_limit::layer,
        ))
        .layer(session_layer)
        .layer(middleware::from_fn(csrf::layer))
        .layer(middleware::from_fn(security::layer))
        .with_state(Arc::clone(&shared))
        .route(
            "/_internal/sse-emit",
            post(sse::emit::handler).with_state(Arc::clone(&shared)),
        )
        .route(
            "/_internal/log",
            post(logs::routes::internal_log)
                .layer(axum::extract::DefaultBodyLimit::max(65_536))
                .with_state(Arc::clone(&shared)),
        )
        .route(
            "/api/internal/log",
            post(logs::routes::internal_log)
                .layer(axum::extract::DefaultBodyLimit::max(65_536))
                .with_state(shared),
        );

    let addr = format!("{}:{}", host, effective_port);
    let listener = tokio::net::TcpListener::bind(&addr).await.unwrap();
    routes::lan_cowork_descriptor::set_bound_addr(listener.local_addr().unwrap());
    tracing::info!("yu-server listening on http://{}", addr);
    axum::serve(
        listener,
        app.into_make_service_with_connect_info::<SocketAddr>(),
    )
    .with_graceful_shutdown(async move {
        wait_shutdown_signal().await;
        infer_supervisor_stop.store(true, std::sync::atomic::Ordering::Release);
        if let Some(stream) = &shutdown_state.hailo_yolo_stream {
            stream.shutdown().await;
        }
        if let Some(infer_child) = &shutdown_state.infer_child {
            match infer_child.lock() {
                Ok(mut child) => infer_manager::terminate_child(&mut child),
                Err(poisoned) => {
                    let mut child = poisoned.into_inner();
                    infer_manager::terminate_child(&mut child);
                }
            }
        }
    })
    .await
    .unwrap();

    std::process::ExitCode::SUCCESS
}

#[cfg(unix)]
async fn wait_shutdown_signal() {
    let mut sigterm = tokio::signal::unix::signal(tokio::signal::unix::SignalKind::terminate())
        .expect("failed to install SIGTERM handler");

    wait_for_shutdown_trigger(
        async {
            let _ = tokio::signal::ctrl_c().await;
        },
        async {
            sigterm.recv().await;
        },
    )
    .await;
}

#[cfg(unix)]
async fn wait_for_shutdown_trigger(
    sigint: impl std::future::Future<Output = ()>,
    sigterm: impl std::future::Future<Output = ()>,
) {
    tokio::select! {
        _ = sigint => {}
        _ = sigterm => {}
    }
}

#[cfg(not(unix))]
async fn wait_shutdown_signal() {
    let _ = tokio::signal::ctrl_c().await;
}

#[cfg(test)]
mod tests {

    /// Every case below was measured against a real yu-server launch before
    /// being written down: a launch-args.txt `--port 5199` beside a
    /// config.json `server.port = 5177` bound 5177 (the bug), and binds 5199
    /// once `argv_flag` reads the merged list.
    mod launch_args_beat_the_config_file {
        use super::super::{argv_flag, resolve_db_path, resolve_host, resolve_port};

        /// The token list main() builds: argv0, then launch-args.txt, then
        /// the real command line.
        fn merged(file_args: &[&str], real_argv: &[&str]) -> Vec<String> {
            std::iter::once("yu-server")
                .chain(file_args.iter().copied())
                .chain(real_argv.iter().copied())
                .map(String::from)
                .collect()
        }

        fn server_cfg(json: serde_json::Value) -> serde_json::Map<String, serde_json::Value> {
            json.as_object().cloned().unwrap()
        }

        #[test]
        fn a_file_only_host_outranks_the_config_file() {
            let args = merged(&["--host", "0.0.0.0"], &[]);
            let cfg = server_cfg(serde_json::json!({"host": "127.0.0.1"}));
            // clap parsed the same merged list, so cli.host is already 0.0.0.0.
            assert_eq!(resolve_host(&args, &cfg, "0.0.0.0"), "0.0.0.0");
        }

        #[test]
        fn a_file_only_port_outranks_the_config_file() {
            let args = merged(&["--port", "5199"], &[]);
            let cfg = server_cfg(serde_json::json!({"port": 5177}));
            assert_eq!(resolve_port(&args, &cfg, 5199), 5199);
        }

        #[test]
        fn an_out_of_range_config_port_falls_back_instead_of_wrapping() {
            let args = merged(&[], &[]);
            // 70000 wrapped to 4464 and 65536 wrapped to 0 -- the latter asks
            // the OS for any free port, so the server was reachable nowhere
            // the operator expected. Both must now yield the CLI value.
            for bad in [65536_u64, 70000, u64::from(u32::MAX)] {
                let cfg = server_cfg(serde_json::json!({ "port": bad }));
                assert_eq!(
                    resolve_port(&args, &cfg, 5199),
                    5199,
                    "config port {bad} should have been rejected, not truncated"
                );
            }
            // The boundary itself is still a legal port and must be honoured.
            let cfg = server_cfg(serde_json::json!({"port": 65535}));
            assert_eq!(resolve_port(&args, &cfg, 5199), 65535);
        }

        #[test]
        fn a_build_without_the_python_backend_never_trusts_a_declaration() {
            // `--no-default-features` compiles every forwarding route out; they
            // answer 503. The declaration is then false by construction, and
            // this build must refuse a stale database rather than serve it on
            // the strength of a backend it cannot call.
            let declared = super::super::migrator_declared(false, "http://127.0.0.1:5001", "");
            assert_eq!(
                declared,
                cfg!(feature = "python-backend"),
                "migrator_declared ignored the python-backend feature"
            );
        }

        #[test]
        fn the_bridge_defers_to_an_explicit_yu_db() {
            // Both names set: YU_DB wins, matching the order every other pair
            // follows (YU_* > TAGDB_* > config.json > default). Bridging over
            // it would be a fresh regression for operators who set YU_DB.
            use std::ffi::OsStr;
            assert_eq!(
                super::super::bridged_db_value(
                    Some(OsStr::new("/yu.db")),
                    Some(OsStr::new("/tagdb.db"))
                ),
                None
            );
        }

        #[test]
        fn the_bridge_carries_the_name_over_when_only_tagdb_db_is_set() {
            use std::ffi::{OsStr, OsString};
            assert_eq!(
                super::super::bridged_db_value(None, Some(OsStr::new("/tagdb.db"))),
                Some(OsString::from("/tagdb.db"))
            );
        }

        #[test]
        fn an_empty_tagdb_db_is_not_bridged() {
            // Python compares `args.db == _default_db` with both empty and lets
            // config win. Bridging "" would set YU_DB to an empty string, and
            // clap would then hand resolve_db_path an empty cli_value.
            use std::ffi::OsStr;
            assert_eq!(
                super::super::bridged_db_value(None, Some(OsStr::new(""))),
                None
            );
            assert_eq!(super::super::bridged_db_value(None, None), None);
        }

        #[test]
        fn a_bridged_value_still_loses_to_the_config_file() {
            // The whole point: the bridge must not change the setting's rank.
            // A bridged TAGDB_DB reaches clap as env, so argv carries no --db
            // and config's `db` still wins -- which is what Python does.
            let args = merged(&[], &[]);
            let cfg = serde_json::json!({"db": "/cfg.db"});
            assert_eq!(
                resolve_db_path(&args, &cfg, "/from-bridged-env.db"),
                "/cfg.db"
            );
        }

        #[test]
        fn a_file_only_db_outranks_the_config_file() {
            let args = merged(&["--db", "/real/tags.db"], &[]);
            let cfg = serde_json::json!({"db": "/decoy/tags.db"});
            assert_eq!(
                resolve_db_path(&args, &cfg, "/real/tags.db"),
                "/real/tags.db"
            );
        }

        #[test]
        fn the_config_file_still_wins_when_no_flag_was_written_anywhere() {
            let args = merged(&[], &[]);
            let cfg = server_cfg(serde_json::json!({"host": "10.0.0.5", "port": 5177}));
            // cli_value here is what clap resolved from env/default.
            assert_eq!(resolve_host(&args, &cfg, "127.0.0.1"), "10.0.0.5");
            assert_eq!(resolve_port(&args, &cfg, 5000), 5177);
            assert_eq!(
                resolve_db_path(&args, &serde_json::json!({"db": "/cfg.db"}), "data/tags.db"),
                "/cfg.db"
            );
        }

        #[test]
        fn an_empty_config_db_is_ignored_and_does_not_blank_the_path() {
            let args = merged(&[], &[]);
            assert_eq!(
                resolve_db_path(&args, &serde_json::json!({"db": ""}), "data/tags.db"),
                "data/tags.db"
            );
        }

        #[test]
        fn real_argv_still_outranks_both_the_file_and_the_config() {
            // Both name --port; clap keeps the last occurrence, so cli.port is
            // the real-argv value. resolve_port must not send it back to the
            // config file just because the file also mentioned the flag.
            let args = merged(&["--port", "5199"], &["--port", "6001"]);
            let cfg = server_cfg(serde_json::json!({"port": 5177}));
            assert_eq!(resolve_port(&args, &cfg, 6001), 6001);
        }

        #[test]
        fn the_equals_form_counts_as_specified() {
            // launch-args.txt lines are whitespace-split, so `--host=0.0.0.0`
            // arrives as one token. It must not read as "not specified".
            let args = merged(&["--host=0.0.0.0"], &[]);
            let cfg = server_cfg(serde_json::json!({"host": "127.0.0.1"}));
            assert_eq!(resolve_host(&args, &cfg, "0.0.0.0"), "0.0.0.0");
        }

        #[test]
        fn scanning_only_the_real_argv_is_what_reintroduces_the_bug() {
            // The fault injection for the fix itself: this is the pre-fix
            // behaviour spelled out. argv_flag over a list holding only the
            // real command line finds nothing, so the config file wins --
            // which is exactly the regression the tests above forbid. If this
            // ever stops differing from the merged-list answer, the merge has
            // been dropped and those tests are passing for the wrong reason.
            let real_argv_only = merged(&[], &[]);
            let with_file = merged(&["--port", "5199"], &[]);
            assert!(argv_flag(&real_argv_only, "--port").is_none());
            assert_eq!(argv_flag(&with_file, "--port"), Some("5199".to_string()));

            let cfg = server_cfg(serde_json::json!({"port": 5177}));
            assert_eq!(resolve_port(&real_argv_only, &cfg, 5199), 5177);
            assert_eq!(resolve_port(&with_file, &cfg, 5199), 5199);
        }
    }
    #[test]
    fn loopback_host_detection_rejects_lan_bindings() {
        assert!(super::is_loopback_host("127.0.0.1"));
        assert!(super::is_loopback_host("[::1]"));
        assert!(super::is_loopback_host("localhost"));
        assert!(!super::is_loopback_host("0.0.0.0"));
        assert!(!super::is_loopback_host("192.168.1.2"));
    }

    #[test]
    fn seed_example_files_prefers_json_and_preserves_existing_toml() {
        let root = tempfile::tempdir().unwrap();
        std::fs::write(
            root.path().join("launch-args.txt.example"),
            "--standalone\n",
        )
        .unwrap();
        std::fs::write(
            root.path().join("config.toml.example"),
            "[server]\nport = 5000\n",
        )
        .unwrap();
        std::fs::write(root.path().join("config.json.example"), "{}\n").unwrap();

        super::seed_example_files(root.path());

        assert!(root.path().join("config.json").exists());
        assert!(!root.path().join("config.toml").exists());

        let existing = "[server]\nport = 1234\n";
        std::fs::write(root.path().join("config.toml"), existing).unwrap();
        super::seed_example_files(root.path());
        assert_eq!(
            std::fs::read_to_string(root.path().join("config.toml")).unwrap(),
            existing
        );
    }

    #[tokio::test]
    #[cfg(unix)]
    async fn wait_shutdown_signal_returns_on_sigterm() {
        let (_sigint_tx, sigint_rx) = tokio::sync::oneshot::channel::<()>();
        let (sigterm_tx, sigterm_rx) = tokio::sync::oneshot::channel::<()>();

        let wait = super::wait_for_shutdown_trigger(
            async {
                let _ = sigint_rx.await;
            },
            async {
                let _ = sigterm_rx.await;
            },
        );

        sigterm_tx.send(()).expect("SIGTERM branch should be open");

        tokio::time::timeout(std::time::Duration::from_secs(1), wait)
            .await
            .expect("SIGTERM should trigger shutdown")
    }

    #[test]
    fn matching_schema_version_is_not_a_mismatch_on_either_side() {
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        assert!(super::schema_version_verdict(expected, "db", true).is_none());
        assert!(super::schema_version_verdict(expected, "db", false).is_none());
    }

    #[test]
    fn the_verdict_does_not_depend_on_whether_we_are_refusing() {
        // Only the remedy may differ. If a future edit made the carrying-on
        // side tolerate a range the refusing side rejects, the two callers
        // would be reporting on different databases while claiming the same
        // check.
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        for version in [expected - 14, expected - 1, expected, expected + 1] {
            assert_eq!(
                super::schema_version_verdict(version, "db", true).is_some(),
                super::schema_version_verdict(version, "db", false).is_some(),
                "the two sides disagree about v{version}"
            );
        }
    }

    #[test]
    fn the_gate_selector_is_the_declaration_not_the_standalone_flag() {
        // standalone asserts "there is no Python here". An ambient
        // YU_PYTHON_URL -- which load_dotenv_files injects from
        // ~/.config/yu/server.env with set_var before clap parses -- must not
        // override it, or every launcher path (all of which pass --standalone)
        // silently degrades to serving a stale database.
        assert!(!super::migrator_declared(true, "http://127.0.0.1:5001", ""));
        assert!(!super::migrator_declared(true, "", ""));
        assert!(!super::migrator_declared(false, "", ""));
        assert!(super::migrator_declared(false, "http://127.0.0.1:5001", ""));
    }

    #[test]
    fn the_schema_status_reports_every_drift_and_flags_only_the_ones_being_served() {
        use super::schema_status_value;
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;

        // (actual, declared) -> (drift, serving_with_drift)
        let cases: [(Option<i64>, bool, &str, bool); 8] = [
            (Some(expected), false, "match", false),
            (Some(expected), true, "match", false),
            (Some(expected - 1), true, "behind", true),
            // Behind and undeclared never reaches the status: the gate refuses
            // with 78 first. Shaped anyway, because the function is total and a
            // future caller must not get a surprise.
            (Some(expected - 1), false, "behind", false),
            (Some(expected + 1), true, "ahead", true),
            (Some(expected + 1), false, "ahead", false),
            (None, true, "unreadable", false),
            (None, false, "unreadable", false),
        ];

        for (actual, declared, drift, serving) in cases {
            let value = schema_status_value(expected, actual, declared, "because", None);
            assert_eq!(
                value["drift"], drift,
                "actual={actual:?} declared={declared}"
            );
            assert_eq!(
                value["serving_with_drift"], serving,
                "actual={actual:?} declared={declared}: this is the flag that says \
                 the server is answering queries over a database it disagrees with"
            );
            assert_eq!(value["expected"], expected);
            assert_eq!(value["migrator_declared"], declared);
            assert_eq!(value["migrator_reason"], "because");
        }
    }

    #[test]
    fn the_downgrade_refusal_says_how_to_get_a_newer_build() {
        // The refusal from tagdb-core says "use a newer build" and stops there.
        // An operator on a machine that cannot compile one was left to work out
        // the rest alone, on the one failure whose only repair is that build.
        let dir = tempfile::tempdir().expect("tempdir");
        let restore = std::env::current_dir().expect("cwd");

        // An installed binary with no source beside it.
        std::env::set_current_dir(dir.path()).expect("chdir");
        let packaged = super::how_to_get_a_newer_build();
        assert!(packaged.contains("no source"), "{packaged}");
        assert!(packaged.contains("make install"), "{packaged}");
        // Do not tell that machine to run a compiler it does not have.
        assert!(!packaged.contains("cargo build"), "{packaged}");

        // A source checkout, recognised by what is actually on disk.
        std::fs::create_dir_all(dir.path().join("crates").join("yu-server")).expect("mkdir");
        let checkout = super::how_to_get_a_newer_build();
        std::env::set_current_dir(&restore).expect("chdir back");
        assert!(
            checkout.contains("cargo build --release -p yu-server"),
            "{checkout}"
        );
        assert!(checkout.contains("start.sh"), "{checkout}");

        // Neither branch may claim the repair has happened.
        for text in [&packaged, &checkout] {
            assert!(!text.contains("updated"), "{text}");
            assert!(!text.contains("downloaded"), "{text}");
        }
    }

    #[test]
    fn the_status_reports_the_rust_chain_as_well_as_pythons() {
        use super::schema_status_value;
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        let rust_expected = tagdb_core::latest_rust_migration_version();

        // The chain the 65 exit code comes from. Reporting only Python's
        // described half the schema state while claiming to describe it.
        for (rust_actual, want) in [
            (None, "unreadable"),
            (Some(rust_expected), "match"),
            (Some(rust_expected - 1), "behind"),
            (Some(rust_expected + 1), "ahead"),
        ] {
            let value = schema_status_value(expected, Some(expected), true, "because", rust_actual);
            assert_eq!(value["rust_drift"], want, "rust_actual={rust_actual:?}");
            assert_eq!(value["rust_actual"], serde_json::json!(rust_actual));
            assert_eq!(value["rust_expected"], rust_expected);
            // The two chains are reported independently: a Rust-side finding
            // must not move the Python-side verdict, which is what the gate
            // decided on.
            assert_eq!(value["drift"], "match", "rust_actual={rust_actual:?}");
            assert_eq!(value["serving_with_drift"], false);
        }
    }

    #[test]
    fn the_declaration_reason_matches_the_decision_it_explains() {
        use super::{migrator_declaration_reason, migrator_declared};
        let url = "http://127.0.0.1:5001";
        let key = tagdb_core::PYTHON_BUILTIN_DB_KEY;

        // The reason and the bool are two views of one decision; a reason that
        // said "declared" while the bool said false is the drift this pairing
        // exists to prevent.
        for (standalone, python_url, db_key) in [
            (false, url, ""),
            (false, url, key),
            (false, url, "operator-key"),
            (true, url, ""),
            (false, "", ""),
        ] {
            let declared = migrator_declared(standalone, python_url, db_key);
            let reason = migrator_declaration_reason(standalone, python_url, db_key);
            let reason_says_yes = reason.starts_with("a Python backend is declared");
            assert_eq!(
                declared, reason_says_yes,
                "({standalone}, {python_url:?}, {db_key:?}) -> declared={declared} but \
                 reason={reason:?}"
            );
        }
    }

    #[test]
    fn an_exposed_env_file_is_named_along_with_the_fix() {
        // server.env.example asks for `chmod 600` and nothing checked that it
        // happened. Tested against every mode rather than whichever one this
        // machine produces, because the rule is about the bits, not about here.
        let path = std::path::Path::new("/home/someone/.config/yu/server.env");

        for (mode, who) in [
            (0o640, "the group"),
            (0o604, "everyone else"),
            (0o644, "the group and everyone else"),
            (0o666, "the group and everyone else"),
        ] {
            let warning = super::env_file_exposure_warning(path, mode, true)
                .unwrap_or_else(|| panic!("mode {mode:o} must be reported"));
            assert!(warning.contains(who), "mode {mode:o}: {warning}");
            // The remedy, not just the complaint.
            assert!(warning.contains("chmod 600"), "mode {mode:o}: {warning}");
            assert!(warning.contains("server.env"), "mode {mode:o}: {warning}");
        }

        // Owner-only is the state being asked for.
        assert!(super::env_file_exposure_warning(path, 0o600, true).is_none());
        assert!(super::env_file_exposure_warning(path, 0o400, true).is_none());

        // A file with no secret in it is nobody's business, whatever its mode:
        // warning about every project-local .env teaches operators to ignore
        // the warning that matters.
        assert!(super::env_file_exposure_warning(path, 0o644, false).is_none());
    }

    #[test]
    fn the_exposure_warning_never_carries_the_secret_itself() {
        // It is a warning about a readable file; printing the value would make
        // the log a second copy of the exposure.
        let path = std::path::Path::new("/tmp/server.env");
        let warning = super::env_file_exposure_warning(path, 0o644, true).expect("warned");
        assert!(
            !warning.contains(tagdb_core::PYTHON_BUILTIN_DB_KEY),
            "{warning}"
        );
        for name in super::SECRET_ENV_NAMES {
            assert!(!warning.contains(name), "named {name}: {warning}");
        }
    }

    #[test]
    fn a_python_that_cannot_open_this_database_is_not_a_migrator() {
        // Python's server opens every connection with its built-in key and
        // reads no environment variable, so an operator-generated key leaves
        // it reachable and useless. Trusting the declaration there serves a
        // stale database on the strength of a migration that can never run.
        let url = "http://127.0.0.1:5001";
        assert!(
            !super::migrator_declared(false, url, "an-operator-generated-key"),
            "a key Python cannot use must not count as a declared migrator"
        );
        assert!(
            super::migrator_declared(false, url, tagdb_core::PYTHON_BUILTIN_DB_KEY),
            "Python's own key is exactly the case where it can migrate"
        );
        // Plaintext goes through the same call on the Python side, so an empty
        // key is not a reason to distrust the declaration.
        assert!(super::migrator_declared(false, url, ""));
        // And the key cannot rescue a declaration that was never made.
        assert!(!super::migrator_declared(
            true,
            url,
            tagdb_core::PYTHON_BUILTIN_DB_KEY
        ));
        assert!(!super::migrator_declared(
            false,
            "",
            tagdb_core::PYTHON_BUILTIN_DB_KEY
        ));
    }

    #[test]
    fn a_behind_database_names_the_remedy_for_the_side_that_is_refusing() {
        let behind = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION - 14;
        let (drift, refusing) =
            super::schema_version_verdict(behind, "data/tags.db", true).expect("mismatch");
        assert_eq!(drift, super::SchemaDrift::Behind);
        // The contract phrase check_genesis_acceptance.py greps.
        assert!(refusing.contains("cannot migrate"), "{refusing}");
        // This wording reaches launches that are NOT standalone (a systemd unit
        // passes no flag) and that no launcher is watching. It must not assert
        // either -- and every other test here only greps the contract phrase,
        // so without this the wording drifts back unnoticed.
        assert!(
            !refusing.contains("Standalone"),
            "the refusing wording must not claim this launch is standalone: {refusing}"
        );

        let (drift, carrying_on) =
            super::schema_version_verdict(behind, "data/tags.db", false).expect("mismatch");
        assert_eq!(drift, super::SchemaDrift::Behind);
        assert!(
            carrying_on.contains("Python owns this migration chain"),
            "{carrying_on}"
        );
        // The carrying-on side keeps running, so the message has to explain the
        // symptom the operator actually sees rather than describing a refusal.
        assert!(carrying_on.contains("come back empty"), "{carrying_on}");
        assert!(
            !carrying_on.contains("Nothing has been modified"),
            "{carrying_on}"
        );
    }

    #[test]
    fn an_ahead_database_is_reported_too() {
        let ahead = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION + 1;
        let (drift, carrying_on) =
            super::schema_version_verdict(ahead, "data/tags.db", false).expect("mismatch");
        assert_eq!(drift, super::SchemaDrift::Ahead);
        assert!(
            carrying_on.contains("migrated past this build"),
            "{carrying_on}"
        );
    }

    #[test]
    fn only_a_behind_database_is_one_python_can_migrate() {
        // The launchers fall back to Python on EXIT_DB_SCHEMA_BEHIND. Python
        // cannot undo a migration, so letting the ahead case take that code
        // would turn one refusal into an endless Rust-then-Python round trip.
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        for (version, want) in [
            (expected - 14, super::SchemaDrift::Behind),
            (expected - 1, super::SchemaDrift::Behind),
            (expected + 1, super::SchemaDrift::Ahead),
            (expected + 9, super::SchemaDrift::Ahead),
        ] {
            let (drift, _) = super::schema_version_verdict(version, "db", true).expect("mismatch");
            assert_eq!(drift, want, "wrong drift for v{version}");
        }
    }

    #[test]
    fn a_refusal_python_cannot_fix_does_not_ask_for_a_python_launch() {
        // Every construction site except the behind arm of db_version_gate
        // goes through fatal(). If one of them ever set the flag, a mistyped
        // profile or a wrong key would start Python on every launch, forever.
        let refusal = super::PreflightRefusal::fatal("mistyped profile".to_string());
        assert!(!refusal.python_can_migrate);
    }

    #[test]
    fn the_behind_exit_code_stays_off_the_codes_already_in_use() {
        // 0/1 ordinary, 2 clap usage, 75 web_ui.py's stale-bundle retry,
        // 126/127 exec failures. Colliding with any of these would make the
        // launchers' fallback fire on the wrong event.
        assert!(!matches!(
            super::EXIT_DB_SCHEMA_BEHIND,
            0 | 1 | 2 | 75 | 126 | 127
        ));
    }

    #[test]
    fn the_two_schema_exit_codes_are_distinct_and_mean_opposite_repairs() {
        // 78 says "run the Python version once"; this one says "put the newer
        // yu-server back". Collapsing them into one code -- or into the generic
        // 1, which is where the ahead case used to land -- leaves an operator
        // with an exit status that cannot tell the two apart.
        assert_ne!(
            super::EXIT_DB_RUST_SCHEMA_AHEAD,
            super::EXIT_DB_SCHEMA_BEHIND
        );
        assert!(!matches!(
            super::EXIT_DB_RUST_SCHEMA_AHEAD,
            0 | 1 | 2 | 75 | 126 | 127
        ));
    }

    #[test]
    fn a_rust_schema_downgrade_is_not_in_the_launcher_fallback_set() {
        // Deliberate: falling back to Python would start the app (Python never
        // reads rust_schema_version) but make a binary downgrade permanently
        // and silently serve from the slower path. The launchers carry
        // {78, 126, 127}; check_launcher_fallback_exit_codes pins that list, so
        // this assertion is the other half -- it says the omission is a
        // decision, not an oversight.
        let launcher_fallback = [78_u8, 126, 127];
        assert!(
            !launcher_fallback.contains(&super::EXIT_DB_RUST_SCHEMA_AHEAD),
            "adding this to the launcher fallback set must be a deliberate change"
        );
    }

    #[test]
    fn the_refusal_keeps_the_wording_the_acceptance_gate_matches() {
        // scripts/internal/check_genesis_acceptance.py greps the refusal
        // wording for these phrases. Rewording the ahead case broke that gate
        // once already, and nothing in this crate noticed.
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        let (_, ahead) =
            super::schema_version_verdict(expected + 1, "data/tags.db", true).expect("mismatch");
        assert!(
            ahead.contains("newer than this build"),
            "check_genesis_acceptance.py matches on this phrase: {ahead}"
        );

        let (_, behind) =
            super::schema_version_verdict(expected - 1, "data/tags.db", true).expect("mismatch");
        assert!(
            behind.contains("cannot migrate"),
            "check_genesis_acceptance.py matches on this phrase: {behind}"
        );
    }

    /// A database holding nothing but `schema_version` at `version`.
    async fn db_at_version(dir: &std::path::Path, version: i64) -> String {
        let path = dir.join("tags.db");
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let pool = sqlx::SqlitePool::connect(&url).await.expect("create db");
        sqlx::query(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, \
             applied_at INTEGER NOT NULL, note TEXT NOT NULL)",
        )
        .execute(&pool)
        .await
        .expect("create");
        sqlx::query("INSERT INTO schema_version VALUES (?, 0, 'fixture')")
            .bind(version)
            .execute(&pool)
            .await
            .expect("seed");
        pool.close().await;
        path.to_str().expect("utf-8 path").to_string()
    }

    #[tokio::test]
    async fn the_gate_covers_every_reading_against_both_declarations() {
        // Neither the predicate's truth table nor the wording tests touch
        // db_version_gate itself. (Ahead, undeclared) => exit 1 is the
        // strictest branch this change introduces -- and the only reason the
        // systemd units needed StartLimit* -- so leaving it unmeasured would
        // mean the harshest new behaviour ships untested.
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        // reading: Some(version) seeds that version; None writes a file that is
        // not a database (both read-failure kinds land in the same arm, so one
        // representative fixture covers the row).
        // want: None = proceed, Some(python_can_migrate) = refuse with that class.
        let cases: [(Option<i64>, bool, Option<bool>); 10] = [
            (Some(expected - 1), false, Some(true)), // behind, undeclared -> 78
            (Some(expected - 1), true, None),        // behind, declared   -> warn
            (Some(expected + 1), false, Some(false)), // ahead,  undeclared -> 1
            (Some(expected + 1), true, None),        // ahead,  declared   -> warn
            (None, false, Some(false)),              // unreadable, undeclared -> 1
            (None, true, None),                      // unreadable, declared   -> warn
            (Some(expected), false, None),           // match,  undeclared -> proceed
            (Some(expected), true, None),            // match,  declared   -> proceed
            (Some(1), false, Some(true)),            // far behind -> still 78
            (Some(expected + 9), false, Some(false)), // far ahead  -> still 1
        ];

        for (index, (reading, declared, want)) in cases.into_iter().enumerate() {
            let dir = tempfile::tempdir().expect("tempdir");
            let path = match reading {
                Some(version) => db_at_version(dir.path(), version).await,
                None => {
                    let p = dir.path().join("tags.db");
                    std::fs::write(&p, b"not a sqlite database at all").expect("write");
                    p.to_str().expect("utf-8 path").to_string()
                }
            };
            let got = super::db_version_gate(&path, "", declared, "test").await;
            match (want, got) {
                (None, Ok(())) => {}
                (Some(can_migrate), Err(refusal)) => assert_eq!(
                    refusal.python_can_migrate, can_migrate,
                    "case {index}: wrong exit-code class for {reading:?}/{declared}"
                ),
                (None, Err(refusal)) => panic!(
                    "case {index}: {reading:?}/{declared} must proceed, refused: {}",
                    refusal.message
                ),
                (Some(_), Ok(())) => {
                    panic!("case {index}: {reading:?}/{declared} must refuse, but proceeded")
                }
            }
        }
    }

    #[tokio::test]
    async fn genesis_refuses_a_key_the_migration_cli_would_refuse() {
        // The harm is not the refusal, it is what happens without one: the
        // file gets written, and from then on the only migrator there is
        // cannot open it. So this asserts both halves -- refused, and nothing
        // on disk.
        for key in ["has space", "quote'key", "semi;key", "amp&key", "brace}key"] {
            let dir = tempfile::tempdir().expect("tempdir");
            let db = dir.path().join("tags.db");
            let path = db.to_str().expect("utf-8 path");

            let refusal = super::standalone_genesis(path, key, false)
                .await
                .expect_err("must refuse a key Python would refuse");
            assert!(
                refusal.message.contains("openssl rand -hex 32"),
                "the refusal must say how to get a usable key: {}",
                refusal.message
            );
            assert!(!db.exists(), "a database was created for key {key:?}");
            // The key itself must not travel into the operator-facing text.
            assert!(!refusal.message.contains(key), "{}", refusal.message);
        }
    }

    #[tokio::test]
    async fn genesis_still_accepts_the_key_the_documentation_prescribes() {
        let dir = tempfile::tempdir().expect("tempdir");
        let db = dir.path().join("tags.db");
        let path = db.to_str().expect("utf-8 path");
        if let Err(refusal) =
            super::standalone_genesis(path, &"0123456789abcdef".repeat(4), false).await
        {
            panic!(
                "a hex key must still create a database: {}",
                refusal.message
            );
        }
        assert!(db.exists(), "genesis did not create the database");
    }

    #[tokio::test]
    async fn the_rust_chain_reading_comes_off_the_actual_database() {
        // The shaper can be handed any number; what was untested is that the
        // number comes from disk. A fault injection that discarded the reading
        // passed every test until this existed.
        let dir = tempfile::tempdir().expect("tempdir");
        let db = dir.path().join("tags.db");
        let path = db.to_str().expect("utf-8 path");

        // No database at all: nothing to report, and no error either.
        assert_eq!(super::read_rust_schema_version(path, "").await, None);

        let url = format!("sqlite://{path}?mode=rwc");
        let pool = sqlx::SqlitePool::connect(&url).await.expect("connect");
        // A yu database that predates Rust migrations: the table is absent, and
        // that is "nothing to report", never version 0.
        sqlx::query("CREATE TABLE files (id INTEGER PRIMARY KEY)")
            .execute(&pool)
            .await
            .expect("files");
        assert_eq!(super::read_rust_schema_version(path, "").await, None);

        sqlx::query(
            "CREATE TABLE rust_schema_version (version INTEGER PRIMARY KEY, \
             applied_at INTEGER NOT NULL, description TEXT)",
        )
        .execute(&pool)
        .await
        .expect("table");
        for version in [1_i64, 2, 7] {
            sqlx::query("INSERT INTO rust_schema_version VALUES (?, 0, 'fixture')")
                .bind(version)
                .execute(&pool)
                .await
                .expect("insert");
        }
        pool.close().await;

        // MAX, not an arbitrary row: the table records every applied migration.
        assert_eq!(super::read_rust_schema_version(path, "").await, Some(7));

        // And the reading is what the status reports -- through the same
        // function the gate calls, so the hop from disk to `server-info` is
        // what is under test and not a value handed in by the test itself.
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        let value =
            super::schema_status_for(path, "", expected, Some(expected), true, "because").await;
        assert_eq!(value["rust_actual"], serde_json::json!(7));
    }

    #[tokio::test]
    async fn an_unreadable_database_names_a_missing_key_when_none_was_given() {
        // The systemd unit that passes no --db-key lands here. Reporting only
        // "damaged" sends the operator to look for corruption when the real
        // cause is a missing key -- but asserting "it is encrypted" would be a
        // misdiagnosis too, since a corrupt plaintext file fails identically.
        let dir = tempfile::tempdir().expect("tempdir");
        let db = dir.path().join("tags.db");
        std::fs::write(&db, b"not a sqlite database at all").expect("write");
        let path = db.to_str().expect("utf-8 path");

        let without_key = super::read_schema_version(path, "")
            .await
            .expect_err("must fail");
        assert!(without_key.contains("No key was supplied"), "{without_key}");

        // A DIFFERENT fixture for the keyed case, and the difference is
        // load-bearing. Measured 2026-09-10: with a key,
        // connect_encrypted_readonly issues only key/cipher_memory_security/
        // mmap_size -- none of which read the schema -- so it *establishes*
        // even on a garbage file and fails later at the SELECT, in the other
        // branch with the other message. Without a key, connect_readonly sets
        // synchronous=NORMAL, which needs the schema, so it fails at connect.
        // A path that does not exist fails at connect either way
        // (create_if_missing(false)), which is how this reaches the keyed arm.
        let missing = dir.path().join("no-such.db");
        let with_key =
            super::read_schema_version(missing.to_str().expect("utf-8 path"), "some-key")
                .await
                .expect_err("must fail");
        assert!(
            !with_key.contains("No key was supplied"),
            "a supplied key must not be reported as missing: {with_key}"
        );
        assert!(
            with_key.contains("different key, damaged, or denied"),
            "{with_key}"
        );
    }

    #[test]
    fn every_verdict_carries_both_versions_and_the_path() {
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        for (version, refusing) in [(expected - 3, true), (expected - 3, false)] {
            let (_, message) =
                super::schema_version_verdict(version, "data/tags.db", refusing).expect("mismatch");
            assert!(message.contains(&format!("v{version}")), "{message}");
            assert!(message.contains(&format!("v{expected}")), "{message}");
            assert!(message.contains("data/tags.db"), "{message}");
        }
    }
}
