#![cfg(test)]
//! Structural guard: where the rate limiter sits in `main.rs`'s layer stack.
//!
//! The behavioural tests in `auth::api_rate_limit::layer_tests` build their own
//! router. That proves the middleware works when correctly placed; it says
//! nothing about where `main.rs` actually places it. `arch-constraints.yaml:59`
//! records the gap ("Router を直接 oneshot するテストは middleware を通らない"),
//! and `hailo_yolo_stream/handlers.rs:1511-1516` names the consequence: a route
//! can be wired into main.rs without passing through a layer and no oneshot
//! test notices.
//!
//! Test ⑬ alone is also not enough for a second reason: "unauthenticated
//! requests are limited" holds both for the chosen position (between
//! auth_middleware and session_layer) and for an outermost placement. The two
//! differ in what they wrap, not in whether they run, so only a structural
//! check separates them.
//!
//! Separate file on purpose: a guard that scans the file it lives in matches
//! its own needle and passes vacuously. Same reason `server_restart_guard.rs`
//! and `main_env_order_guard.rs` sit apart from their subjects.

const MAIN: &str = include_str!("main.rs");

/// Lines of `main.rs` that are code, not commentary.
///
/// `main_env_order_guard.rs` learned this the hard way: its first version
/// flagged the doc comment that explains why `#[tokio::main]` is gone. A
/// comment describing a hazard is not the hazard.
fn code_lines() -> impl Iterator<Item = (usize, &'static str)> {
    MAIN.lines().enumerate().filter(|(_, line)| {
        let t = line.trim_start();
        !t.starts_with("//") && !t.starts_with("/*") && !t.starts_with('*')
    })
}

fn line_of(needle: &str) -> usize {
    code_lines()
        .find(|(_, line)| line.contains(needle))
        .map(|(n, _)| n)
        .unwrap_or_else(|| panic!("main.rs no longer contains {needle:?}"))
}

/// The limiter must be applied after `auth_middleware` and before
/// `session_layer`.
///
/// axum applies layers inside-out, so "applied after auth" means "runs before
/// auth". That is the requirement: `auth_middleware` early-returns 401/423
/// (`auth/middleware.rs:157-201`), so a limiter inside it would only ever see
/// authenticated traffic -- capping legitimate users while leaving an attacker
/// uncapped. Python registers its limiter before auth for the same reason
/// (`runtime_runner.py:249` vs `:285`).
#[test]
fn the_limiter_is_applied_between_auth_and_session() {
    let auth = line_of("auth_middleware,");
    let limiter = line_of("auth::api_rate_limit::layer,");
    let session = line_of(".layer(session_layer)");

    assert!(
        auth < limiter,
        "the limiter must be applied after auth_middleware (line {}) so it runs \
         before it; found at line {}",
        auth + 1,
        limiter + 1
    );
    assert!(
        limiter < session,
        "the limiter must be applied before session_layer (line {}) so CSRF \
         still runs first; found at line {}",
        session + 1,
        limiter + 1
    );
}

/// CSRF must still run before the limiter.
///
/// Applied-order `csrf` after `limiter` means run-order csrf first. If the
/// limiter were moved outside CSRF -- the only way to also cover the routes
/// added after `.with_state()` -- a request that fails the CSRF check would
/// still spend a token, letting an attacker drain buckets without ever passing
/// a header check.
#[test]
fn csrf_still_runs_before_the_limiter() {
    let limiter = line_of("auth::api_rate_limit::layer,");
    let csrf = line_of("middleware::from_fn(csrf::layer)");
    assert!(
        limiter < csrf,
        "csrf::layer (line {}) must be applied after the limiter (line {}) so \
         it runs first",
        csrf + 1,
        limiter + 1
    );
}

/// The limiter is applied exactly once.
///
/// Two applications would make the first route group traverse it twice --
/// two tokens per request, every tier's effective limit halved -- and none of
/// the behavioural tests would notice, because each builds its own single-layer
/// stack.
#[test]
fn the_limiter_is_applied_exactly_once() {
    let applications: Vec<_> = code_lines()
        .filter(|(_, line)| line.contains("api_rate_limit::layer"))
        .map(|(n, line)| format!("{}: {}", n + 1, line.trim()))
        .collect();
    assert_eq!(
        applications.len(),
        1,
        "the limiter must be applied once; found {applications:?}"
    );
}

/// Proves the scans above read real content, and that the comment filter did
/// not discard the code along with the comments.
#[test]
fn the_guard_can_actually_fail() {
    assert!(MAIN.len() > 10_000, "main.rs read as {} bytes", MAIN.len());
    let code: Vec<_> = code_lines().collect();
    assert!(
        code.len() > 500,
        "only {} code line(s) survived",
        code.len()
    );
    for needle in [
        "auth_middleware,",
        "auth::api_rate_limit::layer,",
        ".layer(session_layer)",
        "middleware::from_fn(csrf::layer)",
    ] {
        assert!(
            code.iter().any(|(_, l)| l.contains(needle)),
            "{needle:?} vanished from main.rs's code lines"
        );
    }
}
