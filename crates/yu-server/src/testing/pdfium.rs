use std::path::{Path, PathBuf};

/// The vendored pdfium directory the PDF tests bind against.
///
/// `vendor/` is gitignored, so a fresh checkout -- CI included -- does not have
/// it, and every PDF test failed there with `failed to bind pdfium`. That red
/// said nothing about the code, only about the machine, and it kept the whole
/// suite off `pre_push_check.py`: a gate that is always red gates nothing.
pub(crate) fn vendored_library_dir() -> PathBuf {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("the crate lives two levels below the repo root")
        .join("vendor/pdfium/linux-x64")
}

#[derive(Debug, PartialEq, Eq)]
pub(crate) enum Decision {
    /// pdfium loaded: run every assertion.
    Run,
    /// pdfium is absent on a developer machine: run nothing, and say so.
    Skip,
    /// pdfium is absent where it must not be. Provisioning defect.
    Fail,
}

/// Split out from [`library_dir_or_skip`] so it can be tested on a machine that
/// has no pdfium -- which is every machine that made this necessary. Injecting a
/// fault into the binding call itself is invisible here (absent either way), so
/// the decision it feeds is what carries a local guard.
pub(crate) fn decide(pdfium_loadable: bool, is_ci: bool) -> Decision {
    match (pdfium_loadable, is_ci) {
        (true, _) => Decision::Run,
        (false, true) => Decision::Fail,
        (false, false) => Decision::Skip,
    }
}

/// `Some(dir)` when the vendored pdfium is really loadable, `None` to skip.
///
/// This is not "turn a failing test green": a skip runs no assertions and says
/// so. What it must never do is hide a *missing* library on a machine that is
/// supposed to have one, so under `CI` it panics instead of skipping -- there,
/// an absent pdfium is a provisioning defect, not a local convenience.
pub(crate) fn library_dir_or_skip(test_name: &str) -> Option<PathBuf> {
    let dir = vendored_library_dir();
    let loadable = crate::routes::files::bind_pdfium(&dir, false).is_some();
    match decide(loadable, std::env::var_os("CI").is_some()) {
        Decision::Run => Some(dir),
        Decision::Fail => panic!(
            "{test_name}: pdfium is not loadable from {} and CI is set. \
             CI must provision the vendored pdfium; skipping here would drop \
             the only coverage this test provides.",
            dir.display()
        ),
        Decision::Skip => {
            eprintln!(
                "SKIP {test_name}: pdfium is not loadable from {} \
                 (vendor/ is gitignored). No assertion ran.",
                dir.display()
            );
            None
        }
    }
}

#[cfg(test)]
mod tests {
    use super::{decide, Decision};

    #[test]
    fn a_loadable_pdfium_always_runs_the_assertions() {
        assert_eq!(decide(true, false), Decision::Run);
        assert_eq!(decide(true, true), Decision::Run);
    }

    #[test]
    fn an_absent_pdfium_skips_locally_but_fails_in_ci() {
        // Skipping in CI would silently delete the only coverage these tests
        // provide, which is exactly the failure the skip was meant to avoid
        // introducing.
        assert_eq!(decide(false, false), Decision::Skip);
        assert_eq!(decide(false, true), Decision::Fail);
    }
}
