//! Source-level guard for the restart token comparison.
//!
//! Why this exists, and why it lives in its own file:
//!
//! Constant-time-ness is a property of *how long* a comparison takes, not of
//! what it returns. `auth_core::verify_token` and a plain `==` agree on every
//! input, so a test that compares results is green under both — measured:
//! replacing the delegation with `==` left the behavioural test in `mod.rs`
//! passing. A result-comparing test cannot pin this property at all.
//!
//! So this guard reads the source instead. It has to live in a *separate*
//! file: the needle would otherwise appear in the scanned text as part of this
//! assertion, and the check would find itself and pass no matter what the
//! implementation does. That is not hypothetical — the delegated version of
//! this stage shipped exactly that tautology, and it stayed green across two
//! opposite implementations.
//!
//! This is a structural guard, not a proof. It says the call is still there;
//! it does not measure timing.

#![cfg(test)]

/// The body of `restart_token_matches`, from its signature to the closing brace.
fn restart_token_matches_body() -> String {
    let source = include_str!("mod.rs");
    let Some(start) = source.find("pub fn restart_token_matches(") else {
        panic!("restart_token_matches must exist in restart/mod.rs");
    };
    let rest = source.get(start..).unwrap_or_default();
    let Some(end) = rest.find("\n}\n") else {
        panic!("restart_token_matches must have a closing brace");
    };
    rest.get(..end).unwrap_or_default().to_string()
}

#[test]
fn the_token_comparison_delegates_to_the_constant_time_verifier() {
    let body = restart_token_matches_body();
    assert!(
        body.contains("auth_core::verify_token"),
        "restart_token_matches must compare through auth_core::verify_token \
         (subtle::ConstantTimeEq). A short-circuiting comparison leaks the \
         length of the matching prefix through response timing, which for a \
         restart token is a remote-code-execution oracle.\nbody was:\n{body}",
    );
}

#[test]
fn the_token_comparison_does_not_compare_the_secret_itself() {
    let body = restart_token_matches_body();
    // `!supplied.is_empty()` is fine; comparing the two secrets with == or !=
    // is not. Look for an equality operator applied to `expected`.
    for forbidden in ["== expected", "!= expected", "expected ==", "expected !="] {
        assert!(
            !body.contains(forbidden),
            "restart_token_matches must not compare the token with `{forbidden}` \
             — that is the short-circuiting path this guard exists to keep out.\
             \nbody was:\n{body}",
        );
    }
}

#[test]
fn the_guard_can_actually_fail() {
    // Self-check: the extractor must return the real body, not an empty string
    // or the whole file. A guard that silently scans nothing reports "clean"
    // for every possible defect.
    let body = restart_token_matches_body();
    assert!(body.starts_with("pub fn restart_token_matches("), "{body}");
    assert!(body.len() > 40, "extracted body implausibly short: {body}");
    assert!(
        !body.contains("pub fn drop_flag_arg"),
        "extractor overran into the next function: {body}",
    );
}

/// The body of the Linux `exec_restart`, from its signature to the closing brace.
#[cfg(all(unix, not(target_os = "macos")))]
fn linux_exec_restart_body() -> String {
    let source = include_str!("mod.rs");
    let marker = "#[cfg(all(unix, not(target_os = \"macos\")))]\npub fn exec_restart(";
    let Some(start) = source.find(marker) else {
        panic!("the Linux exec_restart branch must exist in restart/mod.rs");
    };
    let rest = source.get(start..).unwrap_or_default();
    let Some(end) = rest.find("\n}\n") else {
        panic!("exec_restart must have a closing brace");
    };
    rest.get(..end).unwrap_or_default().to_string()
}

#[cfg(all(unix, not(target_os = "macos")))]
#[test]
fn linux_exec_restart_closes_inherited_descriptors_before_exec() {
    // Structural, because the effect is not observable from inside the test
    // process: measured, emptying the close loop leaves every restart unit
    // test green. `exec()` replaces the process with no fork, so a listening
    // socket that survives here makes the restarted server's bind fail with
    // EADDRINUSE -- the failure this guard exists to keep out. Python's
    // process_restart.py closes the range unconditionally for the same reason.
    //
    // This says the close is still written and still ordered before the exec.
    // It does not prove the listener is gone; that needs a live restart, see
    // QA-rust-restart-debug-log.md §4.1.
    let body = linux_exec_restart_body();
    let Some(close_at) = body.find("libc::close(") else {
        panic!("exec_restart must close inherited descriptors before exec\nbody was:\n{body}");
    };
    let Some(exec_at) = body.find(".exec()") else {
        panic!("exec_restart must still call exec\nbody was:\n{body}");
    };
    assert!(
        close_at < exec_at,
        "descriptors must be closed BEFORE exec replaces the process; \
         closing after it would never run\nbody was:\n{body}",
    );
    assert!(
        body.contains("inherited_fd_range()"),
        "the range must come from inherited_fd_range(), not be inlined past \
         its tested fallback\nbody was:\n{body}",
    );
    // Measured: narrowing the loop to `first..first` keeps every other check
    // here green -- the close call is still written, it just never runs. Pin
    // the bounds too, or the guard passes an implementation that closes
    // nothing.
    assert!(
        body.contains("for fd in first..last"),
        "the close loop must span the whole inherited range (first..last); an \
         empty range closes no descriptor while still looking correct\n\
         body was:\n{body}",
    );
}

#[cfg(all(unix, not(target_os = "macos")))]
#[test]
fn the_exec_restart_guard_can_actually_fail() {
    // Self-check for the extractor above: an empty or runaway slice would
    // report "clean" for every possible defect.
    let body = linux_exec_restart_body();
    assert!(body.contains("pub fn exec_restart("), "{body}");
    assert!(body.len() > 80, "extracted body implausibly short: {body}");
    assert!(
        !body.contains("mod tests"),
        "extractor overran into the test module: {body}",
    );
}
