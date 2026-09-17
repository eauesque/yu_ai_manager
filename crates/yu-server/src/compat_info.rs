//! Machine-readable compatibility self-report.
//!
//! The launcher must decide whether a given binary may be used *before*
//! opening the database. Everything needed for that decision is printed
//! here as a single line of JSON.

use serde_json::{json, Value};

/// The UI contract this build expects, read from the generated bundle info.
/// Returns `None` when `dist_info.json` is absent (packaged builds without `src/ts/`).
fn ui_contract(project_root: &std::path::Path) -> Option<String> {
    let path = project_root.join("ui/default/static/dist/dist_info.json");
    let text = std::fs::read_to_string(path).ok()?;
    let value: Value = serde_json::from_str(&text).ok()?;
    value.get("v")?.as_str().map(str::to_owned)
}

pub fn compat_info() -> Value {
    let project_root = std::env::current_dir().unwrap_or_else(|_| ".".into());
    json!({
        "python_schema_version": tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION,
        // The other chain. Without it the launcher's `decide()` compares only
        // the Python side, so "the checkout knows a Rust migration this binary
        // does not" is invisible to it -- and this module's own promise, that
        // everything the decision needs is printed here, was not kept.
        "rust_schema_version": tagdb_core::latest_rust_migration_version(),
        "ui_contract": ui_contract(&project_root),
        "build_commit": option_env!("YU_BUILD_COMMIT").unwrap_or("unknown"),
    })
}

pub fn render_compat_info() -> String {
    compat_info().to_string()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn compat_info_reports_the_schema_version_the_binary_expects() {
        let info = compat_info();
        assert_eq!(
            info["python_schema_version"],
            serde_json::json!(tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION)
        );
    }

    #[test]
    fn compat_info_reports_both_chains_not_just_pythons() {
        // The launcher decides whether this binary is usable from this line
        // alone. Reporting one chain of two made "the checkout knows a Rust
        // migration this binary does not" undetectable, which is the same
        // class of blind spot the Python field exists to close.
        let info = compat_info();
        assert_eq!(
            info["rust_schema_version"],
            serde_json::json!(tagdb_core::latest_rust_migration_version()),
            "{info}"
        );
    }

    #[test]
    fn compat_info_is_a_single_line() {
        let rendered = render_compat_info();
        assert!(
            !rendered.trim_end().contains('\n'),
            "must stay one line: {rendered}"
        );
    }

    #[test]
    fn compat_info_does_not_leak_the_database_key() {
        let rendered = render_compat_info();
        assert!(
            !rendered.contains("cipher"),
            "key material must never appear: {rendered}"
        );
    }
}
