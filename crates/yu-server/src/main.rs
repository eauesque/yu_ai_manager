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
mod ext_config;
mod frontend;
mod groups_index;
mod infer_auth;
mod infer_client;
mod infer_manager;
mod jobs;
mod logs;
mod mcp;
mod num;
mod ocr;
mod pages;
mod pages_boss;
mod tagger_batch;
mod tagger_peer_client;
mod work_steal;
pub(crate) use ::lan_cowork::path_guard;
mod prompt_sim_core;
mod restart;
mod routes;
mod scan_manager;
mod scan_native;
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
/// Create the database if standalone needs one, then refuse a database this
/// binary cannot use.
///
/// Ordering matters twice over. It runs before the pools because the read-only
/// pool opens with `create_if_missing(false)`, and it runs before
/// `apply_standalone_schema` / `ensure_local_identity` / the Rust migrations,
/// all of which write. Gating after any of them would mean rejecting a database
/// this process had already modified.
///
/// Only standalone reaches here. In hybrid, Python owns `schema_version` and its
/// migration chain, so a version this binary does not expect is Python's business
/// and not grounds for refusing to start -- gating there would take the server
/// down the moment Python moved a version ahead. Hybrid runs
/// `warn_schema_version_mismatch` instead, which reports the same disagreement
/// without acting on it.
async fn standalone_db_preflight(
    db_path: &str,
    db_key: &str,
    profile_requested_but_missing: bool,
) -> Result<(), String> {
    // A SQLite URI has no parent to check and no file to claim. Leave it to the
    // normal open path.
    if tagdb_core::is_sqlite_uri(db_path) {
        return Ok(());
    }

    if !Path::new(db_path).exists() {
        if profile_requested_but_missing {
            return Err(format!(
                "refusing to create a database: the requested profile was not found, so the \
                 path fell back to the default ({db_path}). Creating one here would look \
                 exactly like losing your library. Check the profile name."
            ));
        }
        if db_key.is_empty() {
            return Err(format!(
                "refusing to create a database at {db_path} without --db-key (or YU_DB_KEY).\n\
                 The Python version opens tags.db through SQLCipher unconditionally, so an \
                 unencrypted database created here could never be opened by it again.\n\
                 The launcher is expected to supply the key."
            ));
        }
        match tagdb_core::create_fresh_database(db_path, db_key).await {
            Ok(tagdb_core::GenesisOutcome::Created) => {
                tracing::info!("created a new database at {db_path}");
                return Ok(());
            }
            // Another process won the race and has, or is building, a database.
            // Fall through to the version check.
            Ok(tagdb_core::GenesisOutcome::Skipped) => {}
            Err(err) => return Err(format!("{err}")),
        }
    }

    check_schema_version(db_path, db_key).await
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
            return Err(format!(
                "cannot read the schema version of {db_path}: {err}\n\
                 The database may be encrypted with a different key, or damaged. \
                 Nothing has been modified."
            ))
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

/// The single comparison behind both the standalone gate and the hybrid warning.
/// `None` means the database is at the version this build was made for.
///
/// `standalone` only picks the remediation sentence. The verdict itself -- which
/// versions are a mismatch -- must not depend on the mode, or the two callers
/// would disagree about what they are looking at.
fn schema_version_verdict(version: i64, db_path: &str, standalone: bool) -> Option<String> {
    let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
    if version == expected {
        return None;
    }
    // The two opening sentences are the wording `check_genesis_acceptance.py`
    // matches on ("newer than this build" for the ahead case). Keep them
    // verbatim: collapsing both directions into one sentence reads tidier and
    // silently breaks that gate.
    let (headline, remedy) = if version < expected {
        let remedy = if standalone {
            format!(
                "Standalone cannot migrate. Start the Python version once to bring it up to \
                 v{expected}, then start again."
            )
        } else {
            format!(
                "Python owns this migration chain; it has not brought the database up to \
                 v{expected} yet. Until it does, tables this build expects may be missing and \
                 queries against them can come back empty."
            )
        };
        (
            format!("this database is at schema v{version}, but this build needs v{expected}."),
            remedy,
        )
    } else {
        let remedy = if standalone {
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
            format!(
                "this database is at schema v{version}, which is newer than this build \
                 (v{expected})."
            ),
            remedy,
        )
    };
    Some(format!("{headline}\nPath: {db_path}\n{remedy}"))
}

/// Refuse a database whose Python schema version is not the one this binary was
/// built against. Standalone cannot migrate: the Python migration chain was
/// deliberately not ported.
async fn check_schema_version(db_path: &str, db_key: &str) -> Result<(), String> {
    let version = read_schema_version(db_path, db_key).await?;
    match schema_version_verdict(version, db_path, true) {
        Some(message) => Err(message),
        None => Ok(()),
    }
}

/// Hybrid's half of the same check. Python owns `schema_version` here, so a
/// mismatch is not grounds for refusing to start -- gating would take the server
/// down the moment Python moved a version ahead. Staying *silent* about it is
/// the other failure: a database several versions behind serves empty results
/// from a server that reported a clean start, which reads as "the database is
/// broken" rather than "this binary and this database disagree". Say it once,
/// loudly, and carry on.
async fn warn_schema_version_mismatch(db_path: &str, db_key: &str) {
    // A SQLite URI (`:memory:` and friends) has no Python-owned schema to be
    // behind. Same exemption the standalone preflight takes.
    if tagdb_core::is_sqlite_uri(db_path) || !Path::new(db_path).exists() {
        return;
    }
    match read_schema_version(db_path, db_key).await {
        Ok(version) => {
            if let Some(message) = schema_version_verdict(version, db_path, false) {
                tracing::warn!("{message}");
            }
        }
        Err(message) => tracing::warn!("{message}"),
    }
}

/// Returns (merged_config, optional_db_override, profile_was_found).
///
/// The third element exists because the first two cannot distinguish "no such
/// profile" from "the profile exists but sets no db". Both yield `None`, and
/// the caller falls back to the default database path either way. That is
/// harmless while the server only opens existing databases, but genesis must
/// refuse the first case: a mistyped `--profile` would otherwise create an
/// empty new library at the default path, which a user cannot tell apart from
/// having lost everything.
fn merge_profile(
    config: &serde_json::Value,
    name: &str,
    config_path: &Path,
) -> (serde_json::Value, Option<String>, bool) {
    let profiles_dir = config_path
        .parent()
        .unwrap_or(Path::new("."))
        .join("profiles");
    let prof = {
        let file = profiles_dir.join(format!("{name}.json"));
        if file.exists() {
            std::fs::read_to_string(&file)
                .ok()
                .and_then(|s| serde_json::from_str(&s).ok())
        } else {
            config.get("profiles").and_then(|p| p.get(name)).cloned()
        }
    };
    let Some(prof) = prof else {
        tracing::warn!("profile '{}' not found, ignoring", name);
        return (config.clone(), None, false);
    };
    const SKIP: &[&str] = &[
        "label",
        "db",
        "name",
        "description",
        "favorite",
        "last_used_at",
        "created_at",
    ];
    let mut merged = config.clone();
    if let (Some(obj), Some(m)) = (prof.as_object(), merged.as_object_mut()) {
        for (k, v) in obj {
            if SKIP.contains(&k.as_str()) {
                continue;
            }
            if k == "server" {
                if let Some(srv) = m.get_mut("server").and_then(|s| s.as_object_mut()) {
                    if let Some(pobj) = v.as_object() {
                        for (sk, sv) in pobj {
                            srv.insert(sk.clone(), sv.clone());
                        }
                    }
                } else {
                    m.insert(k.clone(), v.clone());
                }
            } else {
                m.insert(k.clone(), v.clone());
            }
        }
        m.insert(
            "active_profile".to_string(),
            serde_json::Value::String(name.to_string()),
        );
    }
    let prof_db = prof
        .get("db")
        .and_then(|v| v.as_str())
        .map(|s| s.to_string());
    if let Some(ref db) = prof_db {
        // ponytail: minimal path-traversal guard; more thorough validation belongs at startup
        if db.contains("..")
            || db.starts_with("/etc")
            || db.starts_with("/proc")
            || db.starts_with("/sys")
        {
            tracing::error!("profile '{}' unsafe db path '{}', ignoring", name, db);
            return (merged, None, true);
        }
    }
    (merged, prof_db, true)
}

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
fn load_env_file_override(path: &Path) {
    match dotenvy::from_path_iter(path) {
        Err(e) => eprintln!("[yu-server] env load skipped {}: {e}", path.display()),
        Ok(iter) => {
            let mut count = 0usize;
            for item in iter {
                match item {
                    Ok((k, v)) => {
                        std::env::set_var(&k, &v);
                        count += 1;
                    }
                    Err(e) => eprintln!("[yu-server] env line skipped in {}: {e}", path.display()),
                }
            }
            eprintln!("[yu-server] loaded env: {} ({count} vars)", path.display());
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

#[tokio::main]
async fn main() {
    let cwd = std::env::current_dir().unwrap_or_default();
    seed_example_files(&cwd);
    load_dotenv_files();

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
    // passed the encryption key. Must run before standalone_db_preflight and
    // check_schema_version, the first functions below that touch the DB.
    if cli.compat_info {
        // stdout IS this flag's output contract: the launcher parses it.
        #[allow(
            clippy::print_stdout,
            reason = "--compat-info writes to stdout by contract"
        )]
        {
            println!("{}", compat_info::render_compat_info());
        }
        return;
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
    if !is_loopback_host(&host) && effective_pin.is_none() {
        eprintln!("error: non-loopback --host requires --pin (or YU_PIN env var) to be set");
        std::process::exit(1);
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
            let (merged, prof_db, found) = merge_profile(&app_config, n, &config_path);
            (merged, prof_db.unwrap_or(db_path), Some(n.clone()), !found)
        } else {
            (app_config, db_path, None, false)
        }
    };

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
            std::process::exit(1);
        }
    };
    // auto_stubs can report LAN Cowork enabled from extension.json while this daemon is off; log this so operators can distinguish them.
    tracing::info!(
        native_daemon,
        source = native_daemon_source,
        "native daemon resolved"
    );

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
    };

    // Standalone (Python absent) is the only mode that may create the database:
    // in hybrid, Python owns creation and its whole migration chain. This runs
    // before every other writer -- before the pools, because the read-only pool
    // also opens with create_if_missing(false), and before
    // apply_standalone_schema / ensure_local_identity below, which would
    // otherwise write into a database this binary has not yet accepted.
    if standalone {
        if let Err(err) =
            standalone_db_preflight(&db_path, &cli.db_key, profile_requested_but_missing).await
        {
            eprintln!("{err}");
            std::process::exit(1);
        }
    } else {
        // Hybrid cannot refuse on a version mismatch (Python owns the chain and
        // may legitimately be ahead), but it must not stay quiet about one
        // either. Same position in the sequence as the gate above, so the
        // version reported is the one on disk, before the Rust migrations run.
        warn_schema_version_mismatch(&db_path, &cli.db_key).await;
    }

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
                std::process::exit(1);
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
        let scan_roots: Vec<PathBuf> = config
            .app_config
            .get("scan_roots")
            .and_then(|v| v.as_array())
            .map(|arr| {
                let roots: Vec<PathBuf> = arr
                    .iter()
                    .filter_map(|r| r.get("path").and_then(|p| p.as_str()))
                    // Config written before the input was normalised can hold
                    // `"C:\Users\me\Pictures"` with the quotes Windows
                    // Explorer's "Copy as path" supplies. Those fail
                    // canonicalize with ERROR_INVALID_NAME, so an existing
                    // install would keep losing every root until the user
                    // re-entered it by hand -- strip here too rather than only
                    // at the point of entry.
                    .map(crate::routes::scan_roots::unquote_path)
                    .filter_map(|p| match std::fs::canonicalize(&p) {
                        Ok(path) => Some(path),
                        Err(err) => {
                            tracing::warn!("failed canonicalize scan root '{}': {err}", p);
                            None
                        }
                    })
                    .collect();
                if !arr.is_empty() && roots.is_empty() {
                    tracing::error!(
                        "all configured scan roots failed canonicalization; yu-infer will deny all paths"
                    );
                }
                roots
            })
            .unwrap_or_default();

        match infer_manager::spawn_with_restart(
            &yu_infer_binary,
            infer_port,
            &scan_roots,
            &infer_auth_token,
            &infer_instance_id,
            &vdevice_group_id,
            &config.cache_dir.join("wd_tagger"),
            &routes::clip_model::model_dir(&config.cache_dir),
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
                    scan_roots.clone(),
                    infer_auth_token.clone(),
                    infer_instance_id.clone(),
                    vdevice_group_id.clone(),
                    config.cache_dir.join("wd_tagger"),
                    routes::clip_model::model_dir(&config.cache_dir),
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
    {
        let sm = crate::scan_manager::ScanManager::new(shared.config.project_root.clone());
        shared.scan_manager.set(Arc::new(sm)).ok();
        if let Some(sm) = shared.scan_manager.get() {
            sm.reconnect_if_running(shared.clone()).await;
        }
    }

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
        .route("/api/apikeys", get(routes::auto_stubs::apikeys_list))
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
            get(routes::auto_stubs::backup_list),
        )
        .route(
            "/api/tools/backup/status",
            get(routes::auto_stubs::backup_status),
        )
        .route(
            "/api/tools/backup/create",
            post(routes::auto_stubs::stub_unavailable),
        )
        .route(
            "/api/tools/backup/restore",
            post(routes::auto_stubs::stub_unavailable),
        )
        .route(
            "/api/tools/backup/delete",
            post(routes::auto_stubs::stub_unavailable),
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
        )
        .route("/api/ocr/npu", get(routes::auto_stubs::ocr_npu))
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
        .route(
            "/api/ocr/export/{file_id}",
            get(routes::auto_stubs::ocr_export),
        )
        .route(
            "/api/ocr/export/batch",
            post(routes::auto_stubs::ocr_export_batch),
        )
        .route(
            "/api/ocr/translate/{file_id}",
            post(routes::auto_stubs::ocr_translate),
        )
        .route(
            "/api/ocr/translations/{file_id}",
            get(routes::ocr::ocr_translations),
        )
        .route(
            "/api/ocr/overlay/{file_id}",
            get(routes::auto_stubs::ocr_overlay),
        )
        .route("/api/ocr/benchmark", post(routes::ocr_jobs::ocr_benchmark))
        .route(
            "/api/ocr/benchmark/report/{report_id}",
            get(routes::ocr::ocr_benchmark_report),
        )
        .route(
            "/api/ocr/benchmark/cases",
            get(routes::auto_stubs::ocr_benchmark_cases),
        )
        .route(
            "/api/ocr/profiles/{model_prefix}",
            put(routes::ocr::ocr_profiles_update),
        )
        .route(
            "/api/ocr/video/{file_id}",
            post(routes::ocr_jobs::ocr_video),
        )
        .route("/api/ocr/pdf/{file_id}", post(routes::ocr_jobs::ocr_pdf))
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
        )
        // ocr/bbox stub
        .route(
            "/api/ocr/bbox/{params}",
            get(routes::auto_stubs::ocr_bbox).post(routes::auto_stubs::ocr_bbox),
        )
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
            "/api/agentmemory-dash/health",
            get(routes::misc_admin::agentmemory_dash_health),
        )
        .route(
            "/api/agentmemory-dash/profile",
            get(routes::misc_admin::agentmemory_dash_profile),
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
    fn matching_schema_version_is_not_a_mismatch_in_either_mode() {
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        assert!(super::schema_version_verdict(expected, "db", true).is_none());
        assert!(super::schema_version_verdict(expected, "db", false).is_none());
    }

    #[test]
    fn the_verdict_does_not_depend_on_the_mode() {
        // Only the remedy may differ. If a future edit made hybrid tolerate a
        // range standalone rejects, the two callers would be reporting on
        // different databases while claiming the same check.
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        for version in [expected - 14, expected - 1, expected, expected + 1] {
            assert_eq!(
                super::schema_version_verdict(version, "db", true).is_some(),
                super::schema_version_verdict(version, "db", false).is_some(),
                "modes disagree about v{version}"
            );
        }
    }

    #[test]
    fn a_behind_database_names_the_mode_specific_remedy() {
        let behind = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION - 14;
        let standalone =
            super::schema_version_verdict(behind, "data/tags.db", true).expect("mismatch");
        assert!(
            standalone.contains("Standalone cannot migrate"),
            "{standalone}"
        );

        let hybrid =
            super::schema_version_verdict(behind, "data/tags.db", false).expect("mismatch");
        assert!(
            hybrid.contains("Python owns this migration chain"),
            "{hybrid}"
        );
        // Hybrid keeps running, so the message has to explain the symptom the
        // operator actually sees rather than describing a refusal.
        assert!(hybrid.contains("come back empty"), "{hybrid}");
        assert!(!hybrid.contains("Nothing has been modified"), "{hybrid}");
    }

    #[test]
    fn an_ahead_database_is_reported_too() {
        let ahead = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION + 1;
        let hybrid = super::schema_version_verdict(ahead, "data/tags.db", false).expect("mismatch");
        assert!(hybrid.contains("migrated past this build"), "{hybrid}");
    }

    #[test]
    fn the_standalone_refusal_keeps_the_wording_the_acceptance_gate_matches() {
        // scripts/internal/check_genesis_acceptance.py greps the standalone
        // refusal for this phrase. Rewording the ahead case broke that gate once
        // already, and nothing in this crate noticed.
        let ahead = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION + 1;
        let standalone =
            super::schema_version_verdict(ahead, "data/tags.db", true).expect("mismatch");
        assert!(
            standalone.contains("newer than this build"),
            "check_genesis_acceptance.py matches on this phrase: {standalone}"
        );
    }

    #[test]
    fn every_verdict_carries_both_versions_and_the_path() {
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        for (version, standalone) in [(expected - 3, true), (expected - 3, false)] {
            let message = super::schema_version_verdict(version, "data/tags.db", standalone)
                .expect("mismatch");
            assert!(message.contains(&format!("v{version}")), "{message}");
            assert!(message.contains(&format!("v{expected}")), "{message}");
            assert!(message.contains("data/tags.db"), "{message}");
        }
    }
}
