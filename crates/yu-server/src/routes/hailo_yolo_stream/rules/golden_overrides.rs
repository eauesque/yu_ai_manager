//! Applying deliberate changes to the frozen golden vectors.
//!
//! `tests/fixtures/yolo_rule_vectors.json` was frozen when the Python
//! implementation was retired (v4.616.0): it is the only remaining record of
//! what Python did. If a golden test can be made to pass by editing it, the
//! freeze is decorative.
//!
//! So the fixture is never edited. A deliberate change goes into
//! `yolo_rule_vectors_overrides.json` as `{vector_id, expected, reason,
//! design_doc}`, and the golden tests ask this module for the expected value.
//! A disagreement with no override is an unintended regression.
//!
//! Procedure: docs/superpowers/specs/
//! 2026-08-14-hailo-yolo-stream-python-retirement-design.md (決定 3).

use std::{collections::HashMap, path::Path};

use serde_json::Value;

const OVERRIDES: &str = include_str!("../../../../tests/fixtures/yolo_rule_vectors_overrides.json");

/// Repo root, derived from the crate directory rather than the cwd, because
/// `cargo test` runs with the crate as cwd and CI runs from the workspace.
fn repo_root() -> &'static Path {
    Path::new(env!("CARGO_MANIFEST_DIR"))
        .ancestors()
        .nth(2)
        .expect("the crate lives two levels below the repo root")
}

/// Every override, keyed by `vector_id`, validated on the way in.
///
/// Validation is not a formality: an override whose `reason` or `design_doc`
/// is missing is exactly the silent rewrite the freeze exists to prevent, and
/// it is refused here rather than quietly honoured.
pub(crate) struct Overrides {
    by_id: HashMap<String, Value>,
}

impl Overrides {
    pub(crate) fn load() -> Self {
        let parsed: Value = serde_json::from_str(OVERRIDES)
            .expect("yolo_rule_vectors_overrides.json must be valid JSON");
        let entries = parsed["overrides"]
            .as_array()
            .expect("yolo_rule_vectors_overrides.json needs an `overrides` array");

        let mut by_id = HashMap::new();
        for entry in entries {
            let vector_id = non_empty(entry, "vector_id");
            for field in ["reason", "design_doc"] {
                let value = non_empty(entry, field);
                assert!(
                    !value.trim().is_empty(),
                    "override {vector_id}: `{field}` must not be blank -- an override \
                     nobody can trace is the silent fixture rewrite this mechanism prevents",
                );
            }
            let design_doc = non_empty(entry, "design_doc");
            assert!(
                repo_root().join(design_doc).exists(),
                "override {vector_id}: design_doc `{design_doc}` does not exist",
            );
            assert!(
                entry.get("expected").is_some(),
                "override {vector_id}: `expected` is required (use null to expect null)",
            );
            assert!(
                by_id
                    .insert(vector_id.to_string(), entry["expected"].clone())
                    .is_none(),
                "override {vector_id}: listed twice",
            );
        }
        Self { by_id }
    }

    /// The expected value for `vector_id`: the override when one exists, the
    /// fixture's own value otherwise.
    pub(crate) fn expected(&self, vector_id: &str, fixture: &Value) -> Value {
        self.by_id
            .get(vector_id)
            .cloned()
            .unwrap_or_else(|| fixture.clone())
    }

    /// Fail on an override that names a vector the fixture does not have.
    ///
    /// Without this, an entry left behind after its vector was renamed or
    /// removed sits in the file looking authoritative while overriding nothing
    /// -- the checker would be blind to exactly the region it guards.
    pub(crate) fn assert_every_override_was_used(&self, seen: &[String]) {
        let unmatched: Vec<&String> = self
            .by_id
            .keys()
            .filter(|id| !seen.iter().any(|s| s == *id))
            .collect();
        assert!(
            unmatched.is_empty(),
            "override(s) name a vector_id the fixture does not have: {unmatched:?}\n  \
             known ids: {seen:?}",
        );
    }
}

fn non_empty<'a>(entry: &'a Value, field: &str) -> &'a str {
    entry
        .get(field)
        .and_then(Value::as_str)
        .unwrap_or_else(|| panic!("every override needs a non-empty string `{field}`: {entry}"))
}
