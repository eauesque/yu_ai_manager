use std::error::Error;
use std::fs;
use std::path::PathBuf;

use serde_json::Value;
use tagdb_core::import::prompt_parse::{parse_prompt_to_tags, PromptParseConfig};

fn repo_root() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("..")
        .join("..")
}

fn bool_config(fixture: &Value, key: &str, default: bool) -> bool {
    fixture
        .get("config")
        .and_then(|config| config.get(key))
        .and_then(Value::as_bool)
        .unwrap_or(default)
}

#[test]
fn prompt_parse_matches_python_goldens() -> Result<(), Box<dyn Error>> {
    let fixtures_dir = repo_root()
        .join("tests")
        .join("compat_goldens")
        .join("prompt_parse");
    if !fixtures_dir.exists() {
        return Ok(());
    }

    let mut fixture_paths = fs::read_dir(&fixtures_dir)?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect::<Vec<_>>();
    fixture_paths.sort();

    for fixture_path in fixture_paths {
        let fixture_text = fs::read_to_string(&fixture_path)?;
        let fixture: Value = serde_json::from_str(&fixture_text)?;
        let prompt = fixture
            .get("prompt")
            .and_then(Value::as_str)
            .ok_or_else(|| format!("fixture missing prompt: {}", fixture_path.display()))?;
        let config = PromptParseConfig {
            prompt_syntax: fixture
                .get("config")
                .and_then(|config| config.get("prompt_syntax"))
                .and_then(Value::as_str)
                .unwrap_or("auto")
                .to_string(),
            brace_choice: bool_config(&fixture, "brace_choice", false),
            preserve_templates: bool_config(&fixture, "preserve_templates", true),
            lowercase_tags: bool_config(&fixture, "lowercase_tags", true),
        };
        let parsed = parse_prompt_to_tags(prompt, &config);

        let rust_tags = Value::Array(
            parsed
                .tags
                .iter()
                .map(|(namespace, tag, weight)| {
                    serde_json::json!({
                        "namespace": namespace,
                        "tag": tag,
                        "weight": weight,
                    })
                })
                .collect(),
        );
        let rust_tokens = Value::Array(
            parsed
                .template_tokens
                .iter()
                .map(|token| {
                    serde_json::json!({
                        "type": token.token_type,
                        "payload": token.payload,
                        "position": token.position,
                    })
                })
                .collect(),
        );

        assert_eq!(
            rust_tags,
            fixture["expected_tags"],
            "{}",
            fixture_path.display()
        );
        assert_eq!(
            rust_tokens,
            fixture["expected_template_tokens"],
            "{}",
            fixture_path.display()
        );
    }

    Ok(())
}
