//! Shared filesystem-path helpers used across route modules.
//!
//! Every producer that needs the user's home directory, or that derives a
//! cache directory name from a model identifier, must go through the
//! functions here rather than re-deriving its own logic -- see
//! `docs/development/arch-constraints.yaml`'s single-normalization rule.

use std::path::PathBuf;

/// Cross-platform home directory resolution.
///
/// Windows normally leaves `HOME` unset, so `USERPROFILE` is checked first
/// there; POSIX platforms use `HOME`. Lifted from the pre-existing
/// `comfyui_bridge::home_dir` (the only prior correct implementation in this
/// crate) so every legacy-cache lookup shares it instead of re-deriving a
/// POSIX-only `std::env::var_os("HOME")` that silently disables legacy
/// resolution on Windows.
pub(crate) fn home_dir() -> Option<PathBuf> {
    #[cfg(windows)]
    let value = std::env::var_os("USERPROFILE").or_else(|| std::env::var_os("HOME"));
    #[cfg(not(windows))]
    let value = std::env::var_os("HOME");
    value.map(PathBuf::from)
}

/// Normalize a model identifier (e.g. a HuggingFace repo id) into a
/// filesystem-safe directory-name segment. Matches Python's `safe_name()`
/// (`re.sub(r"[^\w\-.]", "_", repo)`): word characters, `-`, and `.` pass
/// through, everything else (including `/`) becomes `_`.
///
/// Every Rust producer that derives a cache directory from a model id must
/// use this single normalization -- a second definition (e.g. a bare
/// `.replace('/', "_")`) can disagree on ids containing other punctuation
/// and silently split one model across two directories.
pub(crate) fn safe_model_dir_name(id: &str) -> String {
    id.chars()
        .map(|ch| {
            if ch.is_alphanumeric() || ch == '_' || ch == '-' || ch == '.' {
                ch
            } else {
                '_'
            }
        })
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn safe_model_dir_name_replaces_non_word_characters() {
        assert_eq!(
            safe_model_dir_name("SmilingWolf/wd-swinv2-tagger-v3"),
            "SmilingWolf_wd-swinv2-tagger-v3"
        );
        assert_eq!(safe_model_dir_name("org/model:v1.1"), "org_model_v1.1");
    }

    // home_dir()'s OS-specific precedence can only be exercised on its own
    // platform; each test below is cfg-gated to the platform whose branch it
    // asserts, so exactly one of them compiles and runs per target.
    #[cfg(windows)]
    #[test]
    fn home_dir_prefers_userprofile_over_home_on_windows() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let saved_userprofile = std::env::var_os("USERPROFILE");
        let saved_home = std::env::var_os("HOME");
        unsafe {
            std::env::set_var("USERPROFILE", r"C:\Users\example");
            std::env::set_var("HOME", r"C:\wrong");
        }
        assert_eq!(home_dir(), Some(PathBuf::from(r"C:\Users\example")));

        unsafe {
            std::env::remove_var("USERPROFILE");
        }
        assert_eq!(home_dir(), Some(PathBuf::from(r"C:\wrong")));

        unsafe {
            match saved_userprofile {
                Some(value) => std::env::set_var("USERPROFILE", value),
                None => std::env::remove_var("USERPROFILE"),
            }
            match saved_home {
                Some(value) => std::env::set_var("HOME", value),
                None => std::env::remove_var("HOME"),
            }
        }
    }

    #[cfg(not(windows))]
    #[test]
    fn home_dir_uses_home_on_posix() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(std::sync::PoisonError::into_inner);
        let saved_home = std::env::var_os("HOME");
        unsafe {
            std::env::set_var("HOME", "/tmp/example-home");
        }
        assert_eq!(home_dir(), Some(PathBuf::from("/tmp/example-home")));

        unsafe {
            std::env::remove_var("HOME");
        }
        assert_eq!(home_dir(), None);

        unsafe {
            match saved_home {
                Some(value) => std::env::set_var("HOME", value),
                None => std::env::remove_var("HOME"),
            }
        }
    }
}
