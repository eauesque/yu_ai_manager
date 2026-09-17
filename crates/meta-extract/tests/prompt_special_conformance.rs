//! `extract_loras` / `extract_embeddings` must agree with Python's
//! `core/parsers/prompt_extract_special.py` case for case.
//!
//! The fixture is generated from the Python implementation itself
//! (`scripts`-free, see the golden's provenance in the repo history), so a
//! divergence in either direction fails here rather than showing up as a
//! missing row in a file's detail view.

use serde_json::Value;

const GOLDEN: &str = include_str!("goldens/prompt_special.json");

#[test]
fn prompt_special_extraction_matches_python() {
    let cases: Vec<Value> = serde_json::from_str(GOLDEN).expect("golden parses");
    assert!(cases.len() >= 10, "golden lost cases: {}", cases.len());

    for case in &cases {
        let prompt = case["prompt"].as_str().expect("prompt");
        let loras = Value::Array(meta_extract::extract_loras(prompt));
        let embeddings = Value::Array(meta_extract::extract_embeddings(prompt));
        assert_eq!(loras, case["loras"], "loras differ for {prompt:?}");
        assert_eq!(
            embeddings, case["embeddings"],
            "embeddings differ for {prompt:?}"
        );
    }
}
