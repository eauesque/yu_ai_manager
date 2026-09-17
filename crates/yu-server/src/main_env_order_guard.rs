#![cfg(test)]
//! Structural guard: the environment must be loaded before the runtime exists.
//!
//! Two functions call `std::env::set_var` outside `#[cfg(test)]`:
//! `load_env_file_override` (the .env loader) and `apply_db_name_bridge`
//! (`TAGDB_DB` -> `YU_DB`). glibc's `setenv` can reallocate the environ
//! block, so it is sound only while nothing else can be reading it -- which is
//! exactly why edition 2024 makes it `unsafe`. Both therefore have to run in
//! `fn main` ahead of the runtime builder, and each is checked for that
//! below: the allowlist is by name, not a hole.
//!
//! Until v4.703.0 `main` carried `#[tokio::main]` and did the loading in its
//! body. That macro builds the runtime *before* the body runs: measured with a
//! standalone binary on this machine,
//!
//!     before runtime:            1 thread
//!     after Builder::build():   13 threads
//!     inside block_on:          13 threads   <- the set_var calls ran here
//!
//! so every `set_var` executed with twelve worker threads already live.
//!
//! This file is separate on purpose. A guard that scans the file it is written
//! in matches its own needle and passes vacuously -- the same reason
//! `server_restart_guard.rs` lives apart from `server_restart.rs`.

const MAIN: &str = include_str!("main.rs");

/// The lines of `main.rs` that are actual code.
///
/// The first version of this guard scanned the raw text and flagged its own
/// subject: `main.rs` documents *why* `#[tokio::main]` is gone and *why*
/// `set_var` is confined, and those doc comments contain the very needles the
/// guard hunts for. A comment describing a hazard is not the hazard.
fn code_lines() -> impl Iterator<Item = (usize, &'static str)> {
    MAIN.lines().enumerate().filter(|(_, line)| {
        let t = line.trim_start();
        !t.starts_with("//") && !t.starts_with("/*") && !t.starts_with('*')
    })
}

/// `#[tokio::main]` must not come back: it would silently restore the ordering
/// this guard exists to prevent.
#[test]
fn main_does_not_use_the_tokio_main_attribute() {
    let found: Vec<_> = code_lines()
        .filter(|(_, line)| line.contains("#[tokio::main]"))
        .map(|(n, line)| format!("{}: {}", n + 1, line.trim()))
        .collect();
    assert!(
        found.is_empty(),
        "#[tokio::main] builds the runtime before the body runs, so any env \
         loading in that body executes multi-threaded: {found:?}"
    );
}

/// The env work must sit in the synchronous `fn main`, ahead of the builder.
#[test]
fn env_is_loaded_before_the_runtime_is_built() {
    let line_of = |needle: &str| {
        code_lines()
            .find(|(_, line)| line.contains(needle))
            .map(|(n, _)| n)
            .unwrap_or_else(|| panic!("main.rs no longer contains {needle:?}"))
    };
    let load = line_of("load_dotenv_files();");
    let build = line_of("Builder::new_multi_thread()");
    assert!(
        load < build,
        "load_dotenv_files() (line {}) must precede the runtime builder \
         (line {}); set_var is only sound single-threaded",
        load + 1,
        build + 1
    );
}

/// The two functions allowed to hold a `set_var`, with the window each one
/// owns. Named deliberately: "anywhere before the runtime" would let a call
/// land in a helper that some later caller invokes from an async context.
const SET_VAR_SITES: &[(&str, usize)] = &[
    ("fn load_env_file_override", 20),
    ("fn apply_db_name_bridge", 12),
];

/// `set_var` outside tests must stay confined to those sites, where the
/// ordering below is what makes it sound. A call elsewhere would inherit none
/// of that reasoning.
#[test]
fn set_var_outside_tests_stays_in_the_allowed_sites() {
    let tests = code_lines()
        .find(|(_, line)| line.trim_start().starts_with("mod tests"))
        .map(|(n, _)| n)
        .unwrap_or(usize::MAX);

    let windows: Vec<(usize, usize)> = SET_VAR_SITES
        .iter()
        .map(|(needle, span)| {
            let start = code_lines()
                .find(|(_, line)| line.contains(needle))
                .map(|(n, _)| n)
                .unwrap_or_else(|| panic!("main.rs no longer contains {needle:?}"));
            (start, span + start)
        })
        .collect();

    let strays: Vec<_> = code_lines()
        .filter(|(n, line)| {
            line.contains("env::set_var")
                && *n < tests
                && !windows.iter().any(|(start, end)| n > start && n < end)
        })
        .map(|(n, line)| format!("{}: {}", n + 1, line.trim()))
        .collect();

    assert!(
        strays.is_empty(),
        "production env::set_var outside {:?}; it would run after the runtime \
         starts: {strays:?}",
        SET_VAR_SITES.iter().map(|(n, _)| *n).collect::<Vec<_>>()
    );
}

/// Every allowed site must actually be reached before the runtime exists.
/// Without this the allowlist above would be the hole it is meant not to be:
/// a named function whose call sits after `Builder::build()` is exactly the
/// hazard, wearing an approved name.
#[test]
fn every_set_var_site_is_called_before_the_runtime_is_built() {
    let build = code_lines()
        .find(|(_, line)| line.contains("Builder::new_multi_thread()"))
        .map(|(n, _)| n)
        .expect("the runtime builder is gone");

    for (needle, _) in SET_VAR_SITES {
        let call = needle.trim_start_matches("fn ");
        let call_sites: Vec<usize> = code_lines()
            .filter(|(_, line)| {
                line.contains(&format!("{call}(")) && !line.contains(&format!("fn {call}("))
            })
            .map(|(n, _)| n)
            .collect();
        assert!(
            !call_sites.is_empty(),
            "{call} is allowed to set_var but is never called"
        );
        for site in call_sites {
            assert!(
                site < build,
                "{call} is called at line {} , after the runtime builder at line {}",
                site + 1,
                build + 1
            );
        }
    }
}

/// Proves the three guards above read real content rather than an empty file,
/// which would make every scan above vacuous -- and that the comment filter
/// did not throw the code away along with the comments.
#[test]
fn the_guard_can_actually_fail() {
    assert!(MAIN.len() > 10_000, "main.rs read as {} bytes", MAIN.len());
    let code: Vec<_> = code_lines().collect();
    assert!(
        code.len() > 500,
        "only {} code line(s) survived",
        code.len()
    );
    assert!(code
        .iter()
        .any(|(_, l)| l.contains("fn load_env_file_override")));
    assert!(code
        .iter()
        .any(|(_, l)| l.contains("runtime.block_on(run(cwd))")));
    // The needles really are present in comments, so the filter is load-bearing
    // rather than decorative.
    assert!(
        MAIN.contains("#[tokio::main]"),
        "expected main.rs to still mention #[tokio::main] in prose"
    );
}
