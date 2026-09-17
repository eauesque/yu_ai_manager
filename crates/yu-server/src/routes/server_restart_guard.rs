#![cfg(test)]

#[test]
fn production_route_passes_the_real_launch_restart_function() {
    let source = include_str!("server_restart.rs");
    assert!(source.contains("launch_restart(reservation, args)"));
}

#[test]
fn token_comparison_stays_delegated() {
    let source = include_str!("server_restart.rs");
    assert!(source.contains("restart_token_matches(expected, supplied)"));
}

/// Self-check that the two guards above can actually fail: proves
/// `include_str!` read real, non-trivial content from `server_restart.rs`
/// rather than (say) an empty file, which would make the `contains` asserts
/// above vacuously trivial to satisfy by coincidence.
#[test]
fn the_guard_can_actually_fail() {
    let source = include_str!("server_restart.rs");
    assert!(
        source.len() > 500,
        "server_restart.rs source implausibly short ({} bytes) -- include_str! \
         may not be reading the intended file",
        source.len()
    );
    assert!(
        source.contains("pub async fn restart("),
        "server_restart.rs must define the restart handler"
    );
    // A source file that lacked the delegated call entirely would make
    // `token_comparison_stays_delegated` fail -- demonstrated here by
    // asserting the needle is not present in an unrelated string, i.e. the
    // `contains` check is a real substring search, not always-true.
    assert!(!"unrelated text".contains("restart_token_matches(expected, supplied)"));
}

/// Row 9 (Task 4): a bare `==` comparison of the restart token must never
/// creep back in -- it would reintroduce a timing side channel that
/// `restart_token_matches` (backed by `subtle::ConstantTimeEq`) exists to
/// prevent. `token_comparison_stays_delegated` only proves the delegated
/// call is present; it does NOT prove a redundant bare comparison is absent.
#[test]
fn no_bare_equality_compares_the_restart_token() {
    let source = include_str!("server_restart.rs");
    for forbidden in ["expected ==", "== expected", "supplied ==", "== supplied"] {
        assert!(
            !source.contains(forbidden),
            "server_restart.rs must not compare the restart token with a bare \
             `==` (found `{forbidden}`); route through restart_token_matches instead"
        );
    }
}
