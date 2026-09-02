//! Restart-API infrastructure, ported from Python but **not yet reachable**.
//!
//! Stage A1 of the port described in `docs/development/development_docs/spec-rust-restart-debug-log.md`: the
//! settings resolution, the local-request and token checks, the cooldown gate
//! and `exec_restart` are here and tested, but no route calls them yet and the
//! CLI flags that would turn them on are deliberately absent from `Cli`.
//!
//! The flags are absent on purpose. yu-server has no `/api/server/restart`,
//! `/api/server/restart-with-config` or `/api/server/switch-profile`, so a
//! `--allow-remote-restart` that clap accepted would enable nothing while
//! *also* stopping `scripts/fast_mode.py` from declining fast mode — and that
//! decline is what currently routes such a launch to the Python server, which
//! does implement them. Adding the flags before the routes would therefore
//! turn a working launch into a silently broken one. They go in together with
//! stage A2/A3, not before.
//!
//! See `docs/development/development_docs/QA-rust-restart-debug-log.md` for
//! what is still unimplemented and unverified.

#![allow(dead_code)] // Reachable from stage A2 onwards; see the note above.

use std::collections::HashSet;
use std::io;
use std::net::ToSocketAddrs;
use std::process::Command;
use std::sync::{LazyLock, Mutex, OnceLock};
use std::time::{Duration, Instant};

use axum::http::HeaderMap;

mod source_guard;

pub const RESTART_COOLDOWN: Duration = Duration::from_secs(20);
/// Restart settings initialized by main and read by future request handlers.
pub static RESTART_CONFIG: OnceLock<RestartConfig> = OnceLock::new();

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct RestartConfig {
    pub allow_restart: bool,
    pub allow_remote_restart: bool,
    pub token: Option<String>,
    pub enable_source: &'static str,
    pub remote_source: &'static str,
    pub token_source: &'static str,
}

impl RestartConfig {
    pub fn resolve(
        cli_allow_restart: bool,
        cli_allow_remote_restart: bool,
        cli_token: Option<&str>,
        server: Option<&serde_json::Map<String, serde_json::Value>>,
    ) -> Self {
        let env_enabled = env_truthy("TAGDB_ALLOW_RESTART");
        let config_enabled = server
            .and_then(|server| server.get("allow_restart"))
            .and_then(config_truthy)
            .unwrap_or(false);
        let env_remote = env_truthy("TAGDB_ALLOW_REMOTE_RESTART");
        let config_remote = server
            .and_then(|server| server.get("allow_remote_restart"))
            .and_then(config_truthy)
            .unwrap_or(false);
        let env_token = std::env::var("TAGDB_RESTART_TOKEN")
            .ok()
            .and_then(trim_nonempty);
        let config_token = server
            .and_then(|server| server.get("restart_token"))
            .and_then(|value| value.as_str())
            .map(str::to_string)
            .and_then(trim_nonempty);

        // Python: `restart_token = str(args.restart_token).strip() or None` with
        // the source still recorded as "cli". A blank --restart-token therefore
        // yields no token *and* stops env/config from supplying one, so the
        // remote path answers remote_token_missing rather than falling through
        // to a token the operator thought they had overridden.
        let (token, token_source) = if let Some(token) = cli_token {
            (trim_nonempty(token.to_string()), "cli")
        } else if let Some(token) = env_token {
            (Some(token), "env")
        } else if let Some(token) = config_token {
            (Some(token), "config")
        } else {
            (None, "none")
        };

        Self {
            allow_restart: cli_allow_restart || env_enabled || config_enabled,
            allow_remote_restart: cli_allow_remote_restart || env_remote || config_remote,
            token,
            enable_source: first_enabled_source(cli_allow_restart, env_enabled, config_enabled),
            remote_source: first_enabled_source(
                cli_allow_remote_restart,
                env_remote,
                config_remote,
            ),
            token_source,
        }
    }
}

fn first_enabled_source(cli: bool, env: bool, config: bool) -> &'static str {
    if cli {
        "cli"
    } else if env {
        "env"
    } else if config {
        "config"
    } else {
        "none"
    }
}

fn env_truthy(name: &str) -> bool {
    std::env::var(name).ok().as_deref().is_some_and(truthy)
}

/// Python's `truthy()` runs `str(v or "")` first, so it accepts more than
/// booleans and strings: `server.allow_restart = 1` is truthy there. Numbers
/// are rendered and matched the same way here so a config that enables the
/// API under Python does not silently leave it disabled under yu-server.
fn config_truthy(value: &serde_json::Value) -> Option<bool> {
    match value {
        serde_json::Value::Bool(value) => Some(*value),
        serde_json::Value::String(value) => Some(truthy(value)),
        serde_json::Value::Number(value) => Some(truthy(&value.to_string())),
        // Named rather than wildcarded: Python's `str(v or "")` renders these
        // to something `truthy()` never matches, so they read as "not
        // enabled". A new JSON variant should make this fail to compile and be
        // decided deliberately, not silently fall into None.
        serde_json::Value::Null | serde_json::Value::Array(_) | serde_json::Value::Object(_) => {
            None
        }
    }
}

fn truthy(value: &str) -> bool {
    matches!(
        value.trim().to_ascii_lowercase().as_str(),
        "1" | "true" | "yes" | "on" | "enabled"
    )
}

fn trim_nonempty(value: String) -> Option<String> {
    let value = value.trim();
    (!value.is_empty()).then(|| value.to_string())
}

pub fn is_local_request(
    resolved_ip: &str,
    headers: &HeaderMap,
    trusted_proxy_ips: &HashSet<String>,
) -> bool {
    is_local_request_with_local_ips(
        resolved_ip,
        headers,
        trusted_proxy_ips,
        &hostname_local_ips(),
    )
}

fn is_local_request_with_local_ips(
    resolved_ip: &str,
    headers: &HeaderMap,
    trusted_proxy_ips: &HashSet<String>,
    local_ips: &HashSet<String>,
) -> bool {
    let resolved_ip = resolved_ip.trim().to_ascii_lowercase();
    // An untrusted forwarding hint disqualifies the peer address entirely --
    // loopback included. This is a deliberate divergence from
    // auth_restart.is_local_request_from, which checks loopback first;
    // see docs/development/development_docs/QA-rust-restart-debug-log.md §4.5.
    //
    // The reason: a reverse proxy on the same host is the ordinary way to run
    // this, and it presents tcp_ip = 127.0.0.1 for a request that came from
    // anywhere at all. resolve_client_ip returns tcp_ip verbatim while
    // trusted_ips is empty, so such a request reads as loopback. Granting it
    // "local" status skips check_remote_restart_access's token check outright,
    // which is the one thing --restart-token exists to enforce.
    //
    // Nothing legitimate is lost. A browser talking straight to the server
    // sends no forwarding headers and is still local. An operator who really
    // does front the server with a proxy lists it in --trusted-ips, and then
    // this branch is skipped and resolve_client_ip walks the chain properly.
    if trusted_proxy_ips.is_empty()
        && ["x-forwarded-for", "x-real-ip", "forwarded"]
            .iter()
            .any(|name| headers.contains_key(*name))
    {
        return false;
    }
    matches!(resolved_ip.as_str(), "127.0.0.1" | "::1" | "localhost")
        || local_ips.contains(&resolved_ip)
}

fn hostname_local_ips() -> HashSet<String> {
    let Ok(hostname) = hostname::get() else {
        return HashSet::new();
    };
    let Some(hostname) = hostname.to_str() else {
        return HashSet::new();
    };
    (hostname, 0)
        .to_socket_addrs()
        .map(|addresses| {
            addresses
                .map(|address| address.ip().to_string().to_ascii_lowercase())
                .collect()
        })
        .unwrap_or_default()
}

/// Compare a supplied restart token against the configured one.
///
/// The comparison itself goes through `auth_core::verify_token`, which is
/// backed by `subtle::ConstantTimeEq`. A plain `==` short-circuits on the
/// first differing byte and leaks the length of the matching prefix through
/// timing, which for a restart token is a remote-code-execution oracle: an
/// attacker who can time responses recovers the token byte by byte.
///
/// The emptiness check is deliberately *before* the comparison and is not a
/// timing concern: whether a token was supplied at all is already visible
/// from the response the caller gets either way.
pub fn restart_token_matches(expected: &str, supplied: &str) -> bool {
    let supplied = supplied.trim();
    !supplied.is_empty() && auth_core::verify_token(supplied, expected.trim())
}

#[derive(Default)]
struct RestartStateInner {
    in_progress: bool,
    last_requested_at: Option<Instant>,
}

#[derive(Default)]
pub struct RestartState {
    inner: Mutex<RestartStateInner>,
}

/// The single restart gate for this server process.
pub static RESTART_STATE: LazyLock<RestartState> = LazyLock::new(RestartState::default);

#[derive(Debug, PartialEq, Eq)]
pub struct RestartCooldown {
    pub remaining_seconds: u64,
}

impl RestartState {
    pub fn enforce_restart_cooldown(&self) -> Result<(), RestartCooldown> {
        // A poisoned lock means another thread panicked while holding it. The
        // guarded data is two plain scalars that cannot be left half-written,
        // so recovering beats propagating the panic into a request handler and
        // taking the process down over a restart check.
        let mut state = self.inner.lock().unwrap_or_else(|err| err.into_inner());
        let now = Instant::now();
        // Python evaluates `in_progress or elapsed < cooldown` as one condition
        // and then derives the remaining seconds from last_requested_at for
        // both, so an in-progress restart reports the time actually left, not a
        // fresh full cooldown.
        let elapsed = state
            .last_requested_at
            .map(|last| now.saturating_duration_since(last));
        let within_cooldown = elapsed.is_some_and(|elapsed| elapsed < RESTART_COOLDOWN);
        if state.in_progress || within_cooldown {
            let remaining = elapsed
                .map(|elapsed| RESTART_COOLDOWN.saturating_sub(elapsed))
                .unwrap_or(RESTART_COOLDOWN);
            return Err(RestartCooldown {
                remaining_seconds: remaining.as_secs().max(1),
            });
        }
        state.in_progress = true;
        state.last_requested_at = Some(now);
        Ok(())
    }

    pub fn reset_in_progress(&self) {
        self.inner
            .lock()
            .unwrap_or_else(|err| err.into_inner())
            .in_progress = false;
    }
}

pub fn drop_flag_arg(args: impl IntoIterator<Item = String>, flag: &str) -> Vec<String> {
    let prefix = format!("{flag}=");
    let mut result = Vec::new();
    let mut args = args.into_iter();
    while let Some(arg) = args.next() {
        if arg == flag {
            let _ = args.next();
        } else if !arg.starts_with(&prefix) {
            result.push(arg);
        }
    }
    result
}

pub fn restart_args() -> io::Result<Vec<String>> {
    Ok(
        std::iter::once(std::env::current_exe()?.to_string_lossy().into_owned())
            .chain(std::env::args().skip(1))
            .collect(),
    )
}

pub fn launch_restart(state: &'static RestartState, args: Vec<String>) {
    std::thread::spawn(move || {
        std::thread::sleep(Duration::from_millis(800));
        if let Err(error) = exec_restart(&args) {
            state.reset_in_progress();
            tracing::error!(%error, "restart failed");
        }
    });
}

#[cfg(target_os = "windows")]
pub fn exec_restart(args: &[String]) -> io::Result<()> {
    use std::os::windows::process::CommandExt;

    const CREATE_NEW_PROCESS_GROUP: u32 = 0x0000_0200;
    let executable = args
        .first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "restart args missing"))?;
    Command::new(executable)
        .args(args.get(1..).unwrap_or_default())
        .creation_flags(CREATE_NEW_PROCESS_GROUP)
        .spawn()?;
    std::process::exit(0);
}

#[cfg(target_os = "macos")]
pub fn exec_restart(args: &[String]) -> io::Result<()> {
    use std::os::unix::process::CommandExt;

    let executable = args
        .first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "restart args missing"))?;
    let mut command = Command::new(executable);
    command.args(args.get(1..).unwrap_or_default());
    unsafe {
        command.pre_exec(|| {
            if libc::setsid() == -1 {
                return Err(io::Error::last_os_error());
            }
            Ok(())
        });
    }
    command.spawn()?;
    std::process::exit(0);
}

/// The descriptor range `exec_restart` closes before replacing the process.
///
/// Mirrors `process_restart.py`'s `os.closerange(3, SC_OPEN_MAX)`: 0/1/2 are
/// left alone so the restarted server keeps the launcher's stdio, and the
/// upper bound falls back to Python's own 4096 when `sysconf` cannot answer.
#[cfg(all(unix, not(target_os = "macos")))]
fn inherited_fd_range() -> (i32, i32) {
    // SAFETY: sysconf with a compile-time-valid name and no pointer arguments.
    let reported = unsafe { libc::sysconf(libc::_SC_OPEN_MAX) };
    fd_range_from_sysconf(reported)
}

/// The mapping split out from the `sysconf` call so the failure branch is
/// reachable from a test. Measured: on this machine `sysconf` always answers
/// with a positive value, so a test that goes through `inherited_fd_range()`
/// exercises only the success path and stays green even when the fallback is
/// broken to close nothing at all.
#[cfg(all(unix, not(target_os = "macos")))]
fn fd_range_from_sysconf(reported: libc::c_long) -> (i32, i32) {
    let max_fd = i32::try_from(reported).unwrap_or(i32::MAX);
    (3, if reported > 0 { max_fd } else { 4096 })
}

#[cfg(all(unix, not(target_os = "macos")))]
pub fn exec_restart(args: &[String]) -> io::Result<()> {
    use std::os::unix::process::CommandExt;

    let executable = args
        .first()
        .ok_or_else(|| io::Error::new(io::ErrorKind::InvalidInput, "restart args missing"))?;

    // `exec()` replaces this process in place -- there is no fork, so anything
    // still open here is inherited by the new server. The listening socket is
    // the one that matters: if it survives, the restarted server's bind fails
    // with EADDRINUSE and the restart dies without a visible cause. Rust's std
    // sets CLOEXEC on the descriptors it opens, but that has not been measured
    // for every descriptor this process holds (tokio's internals, SQLCipher's
    // file handles, any C library loaded at runtime), and Python closes the
    // range unconditionally rather than relying on it. Assume nothing and do
    // the same.
    //
    // The cost of being wrong in the other direction is accepted, exactly as
    // it is in process_restart.py: if `exec` then fails, this process has just
    // closed descriptors it still needs. It is already unrecoverable at that
    // point -- the caller logs the error and leaves the restart marked failed.
    let (first, last) = inherited_fd_range();
    for fd in first..last {
        // SAFETY: close() on an integer descriptor; an already-closed or never
        // opened fd returns EBADF, which is ignored on purpose.
        unsafe {
            libc::close(fd);
        }
    }

    Err(Command::new(executable)
        .args(args.get(1..).unwrap_or_default())
        .exec())
}

#[cfg(not(any(unix, target_os = "windows")))]
pub fn exec_restart(_args: &[String]) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "restart is unsupported on this platform",
    ))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::http::{HeaderMap, HeaderValue};
    use serde_json::json;

    #[test]
    fn restart_config_ors_all_boolean_sources_and_tracks_sources() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        std::env::set_var("TAGDB_ALLOW_RESTART", "enabled");
        std::env::set_var("TAGDB_ALLOW_REMOTE_RESTART", "on");
        let server = serde_json::from_value(json!({"allow_restart": false})).unwrap();
        let config = RestartConfig::resolve(false, false, None, Some(&server));
        std::env::remove_var("TAGDB_ALLOW_RESTART");
        std::env::remove_var("TAGDB_ALLOW_REMOTE_RESTART");
        assert!(config.allow_restart);
        assert!(config.allow_remote_restart);
        assert_eq!(config.enable_source, "env");
        assert_eq!(config.remote_source, "env");
    }

    #[test]
    fn restart_config_uses_token_precedence_and_trims_non_cli_sources() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        std::env::set_var("TAGDB_RESTART_TOKEN", " env-token ");
        let server = serde_json::from_value(json!({"restart_token": " config-token "})).unwrap();
        let env = RestartConfig::resolve(false, false, None, Some(&server));
        let cli = RestartConfig::resolve(false, false, Some("cli-token"), Some(&server));
        std::env::remove_var("TAGDB_RESTART_TOKEN");
        assert_eq!(
            (env.token, env.token_source),
            (Some("env-token".into()), "env")
        );
        assert_eq!(
            (cli.token, cli.token_source),
            (Some("cli-token".into()), "cli")
        );
    }

    #[test]
    fn local_request_accepts_host_lan_ip_but_rejects_untrusted_forwarding_hints() {
        let mut local_ips = HashSet::new();
        local_ips.insert("192.168.1.20".to_string());
        let trusted = HashSet::new();
        let headers = HeaderMap::new();
        assert!(is_local_request_with_local_ips(
            "192.168.1.20",
            &headers,
            &trusted,
            &local_ips
        ));
        let mut forwarded = HeaderMap::new();
        forwarded.insert("x-forwarded-for", HeaderValue::from_static("127.0.0.1"));
        assert!(!is_local_request_with_local_ips(
            "192.168.1.20",
            &forwarded,
            &trusted,
            &local_ips
        ));
    }

    #[test]
    fn restart_token_match_accepts_only_the_exact_token() {
        assert!(restart_token_matches(" expected ", " expected "));
        assert!(!restart_token_matches("expected", ""));
        assert!(!restart_token_matches("expected", "   "));
        assert!(!restart_token_matches("expected", "expecteD"));
        // A shared prefix must not pass, and neither must a longer string that
        // starts with the token -- the two shapes a length-or-prefix-sensitive
        // comparison gets wrong.
        assert!(!restart_token_matches("expected", "expect"));
        assert!(!restart_token_matches("expected", "expectedX"));
    }

    #[test]
    fn restart_token_match_agrees_with_the_verifier_on_every_shape() {
        // This pins the accept/reject semantics, NOT constant-time-ness.
        // Measured 2026-09-01: swapping the delegation for a plain `==` leaves
        // this test green, because verify_token and `==` return the same
        // boolean for every input -- the property that differs is timing, and
        // no result comparison can see it. The structural guard in
        // source_guard.rs is what keeps the delegation in place; this test is
        // what keeps the semantics right.
        for (expected, supplied) in [
            ("tok", "tok"),
            ("tok", "to"),
            ("tok", "tokk"),
            ("tok", "TOK"),
            ("", "tok"),
        ] {
            let delegated = auth_core::verify_token(supplied.trim(), expected.trim());
            let ours = restart_token_matches(expected, supplied);
            assert_eq!(
                ours,
                delegated && !supplied.trim().is_empty(),
                "restart_token_matches({expected:?}, {supplied:?}) disagreed with auth_core::verify_token's verdict",
            );
        }
    }

    #[test]
    fn a_loopback_peer_carrying_untrusted_forwarding_hints_is_not_local() {
        // Revised 2026-09-01, reversing
        // a_loopback_peer_stays_local_even_with_forwarding_headers.
        //
        // That test pinned Python's order (loopback before the hint check) on
        // the grounds that reversing it would lock out an operator behind a
        // local dev proxy. The lock-out reasoning was wrong -- such an operator
        // lists the proxy in --trusted-ips, which skips this branch -- and the
        // order it pinned is exploitable: a reverse proxy on the same host
        // shows tcp_ip = 127.0.0.1 for requests from anywhere, and "local"
        // skips the restart-token check completely.
        let local_ips = HashSet::new();
        let trusted = HashSet::new();
        let mut forwarded = HeaderMap::new();
        forwarded.insert("x-forwarded-for", HeaderValue::from_static("10.0.0.9"));
        assert!(!is_local_request_with_local_ips(
            "127.0.0.1",
            &forwarded,
            &trusted,
            &local_ips
        ));
    }

    #[test]
    fn a_loopback_peer_without_forwarding_hints_is_still_local() {
        // The other half of the pair: tightening must not cost the ordinary
        // case. A browser talking straight to the server sends no such header.
        let local_ips = HashSet::new();
        let trusted = HashSet::new();
        let headers = HeaderMap::new();
        for peer in ["127.0.0.1", "::1", "localhost"] {
            assert!(
                is_local_request_with_local_ips(peer, &headers, &trusted, &local_ips),
                "{peer} must still count as local",
            );
        }
    }

    #[test]
    fn a_configured_proxy_makes_the_hints_stop_disqualifying_the_peer() {
        // The documented escape hatch has to actually work, or the advice in
        // the comment above is a dead end: once the operator lists the proxy,
        // forwarding headers are expected and must not reject the request.
        let local_ips = HashSet::new();
        let trusted: HashSet<String> = ["127.0.0.1".to_string()].into_iter().collect();
        let mut forwarded = HeaderMap::new();
        forwarded.insert("x-forwarded-for", HeaderValue::from_static("10.0.0.9"));
        assert!(is_local_request_with_local_ips(
            "127.0.0.1",
            &forwarded,
            &trusted,
            &local_ips
        ));
    }

    #[test]
    fn a_blank_cli_token_yields_no_token_and_shadows_env_and_config() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        std::env::set_var("TAGDB_RESTART_TOKEN", "env-token");
        let server = serde_json::from_value(json!({"restart_token": "config-token"})).unwrap();
        let config = RestartConfig::resolve(false, false, Some("   "), Some(&server));
        std::env::remove_var("TAGDB_RESTART_TOKEN");
        assert_eq!(config.token, None);
        assert_eq!(config.token_source, "cli");
    }

    #[test]
    fn a_numeric_config_value_enables_the_api_as_it_does_under_python() {
        let server = serde_json::from_value(json!({"allow_restart": 1})).unwrap();
        let config = RestartConfig::resolve(false, false, None, Some(&server));
        assert!(config.allow_restart);
        assert_eq!(config.enable_source, "config");
    }

    #[test]
    fn cooldown_reports_the_time_actually_left_while_a_restart_is_in_progress() {
        let state = RestartState::default();
        state.enforce_restart_cooldown().expect("first call passes");
        let err = state
            .enforce_restart_cooldown()
            .expect_err("second call is refused");
        // in_progress is set by the first call; the remaining seconds must come
        // from last_requested_at, so they are below the full cooldown.
        assert!(err.remaining_seconds >= 1);
        assert!(err.remaining_seconds <= RESTART_COOLDOWN.as_secs());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    #[test]
    fn the_closed_fd_range_starts_above_stdio() {
        // Starting at 0 would shut the launcher's stdout/stderr on the way out.
        let (first, last) = inherited_fd_range();
        assert_eq!(first, 3, "stdio must not be closed");
        assert!(last > first, "range must be non-empty, got {first}..{last}");
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    #[test]
    fn a_failed_sysconf_falls_back_instead_of_closing_nothing() {
        // Driven through the pure mapping on purpose. sysconf answers
        // positively on this machine, so a test that called
        // inherited_fd_range() could never reach this branch -- and it did
        // stay green, measured, when the fallback was broken to return 3
        // (an empty range that closes no descriptor at all).
        //
        // Whether the listener is actually gone after the close loop needs a
        // live restart; see QA-rust-restart-debug-log.md §4.1.
        for failed in [-1, 0] {
            let (first, last) = fd_range_from_sysconf(failed);
            assert_eq!(first, 3);
            assert_eq!(
                last, 4096,
                "sysconf={failed} must fall back to Python's 4096"
            );
        }
        let (_, last) = fd_range_from_sysconf(512);
        assert_eq!(last, 512, "a positive sysconf answer must be used as-is");
    }

    #[test]
    fn drop_flag_arg_removes_split_and_equals_forms() {
        assert_eq!(
            drop_flag_arg(
                vec![
                    "--db".into(),
                    "old.db".into(),
                    "--db=older.db".into(),
                    "--port".into(),
                    "5000".into()
                ],
                "--db",
            ),
            vec!["--port", "5000"],
        );
    }
}
