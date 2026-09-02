//! Cross-language conformance: Rust parse_metadata output must match Python
//! builtin parser golden files in tests/goldens/.
//!
//! Run: cargo test -p meta-extract
//!
//! Golden regeneration:
//! UV_CACHE_DIR=tmp/.uv-cache ./bin/uv run python scripts/gen_meta_extract_goldens.py

use meta_extract::{parse_metadata, read_png_text_chunks};
use serde_json::Value;
use std::path::PathBuf;

fn crate_tests_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("tests")
}

fn load_golden(parser_id: &str) -> Value {
    let path = crate_tests_root()
        .join("goldens")
        .join(format!("{}.json", parser_id));
    let raw = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("Cannot read golden {}: {}", path.display(), e));
    serde_json::from_str(&raw)
        .unwrap_or_else(|e| panic!("Invalid JSON in {}: {}", path.display(), e))
}

fn load_capability_matrix() -> Vec<(String, String)> {
    let path = crate_tests_root().join("goldens/capability_matrix.yaml");
    let raw = std::fs::read_to_string(&path)
        .unwrap_or_else(|e| panic!("Cannot read capability_matrix.yaml: {}", e));
    let mut skips: Vec<(String, String)> = Vec::new();
    let mut current_parser: Option<String> = None;
    let mut current_field: Option<String> = None;
    for line in raw.lines() {
        let t = line.trim();
        // Reset per list entry so a field:/parser: from one gap can never pair
        // with a stale slot left by an incomplete neighbouring entry.
        if t.starts_with("- id:") {
            current_parser = None;
            current_field = None;
        }
        if let Some(rest) = t.strip_prefix("field:") {
            current_field = Some(rest.trim().trim_matches('"').to_string());
        } else if let Some(rest) = t.strip_prefix("parser:") {
            current_parser = Some(rest.trim().trim_matches('"').to_string());
        }
        if current_parser.is_some() && current_field.is_some() {
            skips.push((
                current_parser.take().unwrap(),
                current_field.take().unwrap(),
            ));
        }
    }
    skips
}

fn is_skip_allowed(matrix: &[(String, String)], parser: &str, field: &str) -> bool {
    matrix
        .iter()
        .any(|(p, f)| (p == "all" || p == parser) && (f == "all" || f == field))
}

fn normalize_raw_meta(s: &str) -> String {
    match serde_json::from_str::<Value>(s) {
        Ok(v) => serde_json::to_string(&v).unwrap(),
        Err(_) => s.to_string(),
    }
}

fn normalize_text(s: &str) -> String {
    s.replace("\r\n", "\n")
        .replace('\r', "\n")
        .trim()
        .to_string()
}

fn run_conformance(parser_id: &str) {
    let golden = load_golden(parser_id);
    let matrix = load_capability_matrix();

    let fixture_rel = golden["fixture"]
        .as_str()
        .unwrap_or_else(|| panic!("Golden {}: missing 'fixture' key", parser_id));
    let fixture_path = crate_tests_root().join(fixture_rel);
    assert!(
        fixture_path.exists(),
        "Fixture not found: {}",
        fixture_path.display()
    );

    let chunks = read_png_text_chunks(&fixture_path);
    let result = parse_metadata(&chunks);

    let expected_format = golden["format_rust"].as_str().unwrap_or("unknown");
    assert_eq!(
        result.format, expected_format,
        "[{}] format mismatch: Rust='{}' expected='{}'",
        parser_id, result.format, expected_format
    );

    let expected_positive = golden["positive"].as_str();
    let rust_positive = result.positive.as_deref();
    let pos_match = match (rust_positive, expected_positive) {
        (Some(r), Some(p)) => normalize_text(r) == normalize_text(p),
        (None, None) => true,
        _ => false,
    };
    if !pos_match {
        if is_skip_allowed(&matrix, parser_id, "positive") {
            eprintln!(
                "[{}] positive mismatch SKIPPED (capability_matrix)",
                parser_id
            );
        } else {
            panic!(
                "[{}] positive mismatch - Rust={:?} golden={:?}\n\
                 If this is a known gap, add it to tests/goldens/capability_matrix.yaml",
                parser_id, rust_positive, expected_positive
            );
        }
    }

    let expected_negative = golden["negative"].as_str();
    let rust_negative = result.negative.as_deref();
    let neg_match = match (rust_negative, expected_negative) {
        (Some(r), Some(p)) => normalize_text(r) == normalize_text(p),
        (None, None) => true,
        _ => false,
    };
    if !neg_match {
        if is_skip_allowed(&matrix, parser_id, "negative") {
            eprintln!(
                "[{}] negative mismatch SKIPPED (capability_matrix)",
                parser_id
            );
        } else {
            panic!(
                "[{}] negative mismatch - Rust={:?} golden={:?}\n\
                 If this is a known gap, add it to tests/goldens/capability_matrix.yaml",
                parser_id, rust_negative, expected_negative
            );
        }
    }

    let expected_raw_meta = golden["raw_meta"].as_str();
    let rust_raw_meta = result.raw_meta.as_deref();
    let meta_match = match (rust_raw_meta, expected_raw_meta) {
        (Some(r), Some(p)) => normalize_raw_meta(r) == normalize_raw_meta(p),
        (None, None) => true,
        _ => false,
    };
    if !meta_match {
        if is_skip_allowed(&matrix, parser_id, "raw_meta") {
            eprintln!(
                "[{}] raw_meta mismatch SKIPPED (capability_matrix)",
                parser_id
            );
        } else {
            panic!(
                "[{}] raw_meta mismatch - Rust={:?} golden={:?}\n\
                 If this is a known gap, add it to tests/goldens/capability_matrix.yaml",
                parser_id,
                rust_raw_meta.map(|s| &s[..s.len().min(80)]),
                expected_raw_meta.map(|s| &s[..s.len().min(80)])
            );
        }
    }

    println!(
        "[{}] conformance OK (format={}, positive={}, negative={}, raw_meta={})",
        parser_id,
        result.format,
        if pos_match { "match" } else { "skip" },
        if neg_match { "match" } else { "skip" },
        if meta_match { "match" } else { "skip" },
    );
}

/// Regression guard: a `field: "all" / parser: "all"` entry would make every
/// mismatch skip-allowed and the whole suite pass vacuously. Real comparison
/// fields (format/positive) must never be universally skip-allowed.
#[test]
fn matrix_does_not_mask_everything() {
    let m = load_capability_matrix();
    assert!(
        !is_skip_allowed(&m, "a1111", "format"),
        "capability_matrix skips 'format' — a wildcard (all/all) entry is masking all conformance checks"
    );
    assert!(
        !is_skip_allowed(&m, "comfy", "positive"),
        "capability_matrix skips 'positive' for comfy — conformance would be vacuous"
    );
}

#[test]
fn conformance_a1111() {
    run_conformance("a1111");
}

#[test]
fn conformance_comfy() {
    run_conformance("comfy");
}

#[test]
fn conformance_nai_v3() {
    run_conformance("nai_v3");
}

#[test]
fn conformance_nai_v4() {
    run_conformance("nai_v4");
}
