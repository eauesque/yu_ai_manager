use std::{fs, path::Path, sync::LazyLock};

use axum::{
    extract::{rejection::JsonRejection, State},
    http::{header, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use regex::Regex;
use serde_json::{json, Value};

use crate::state::SharedState;

const ENGINE_PARTS: &[&str] = &[
    "prompt-syntax-engine-core-lex-main.js",
    "prompt-syntax-engine-core-lex-matchers-general.js",
    "prompt-syntax-engine-core-lex-matchers-square.js",
    "prompt-syntax-engine-core-lex-matchers-brace.js",
    "prompt-syntax-engine-core-lex-matchers-paren.js",
    "prompt-syntax-engine-core-lex-helpers.js",
    "prompt-syntax-engine-core-analyze.js",
    "prompt-syntax-engine-render-utils.js",
    "prompt-syntax-engine-render-token-renderers.js",
    "prompt-syntax-engine-render.js",
    "prompt-syntax-engine-entry.js",
];
const WIDGET_PARTS: &[&str] = &[
    "prompt-syntax-widget-core.js",
    "prompt-syntax-widget-editor-ui.js",
    "prompt-syntax-widget-editor.js",
    "prompt-syntax-widget-display.js",
    "prompt-syntax-widget-token-tip.js",
    "prompt-syntax-widget-entry.js",
];
const STYLE_PARTS: &[&str] = &[
    "prompt-syntax-style-base.css",
    "prompt-syntax-style-tokens.css",
    "prompt-syntax-style-nai.css",
    "prompt-syntax-style-sd.css",
    "prompt-syntax-style-dp.css",
    "prompt-syntax-style-ui.css",
];

static NAI_WEIGHT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\d*\.?\d+::(?:[^:]|:[^:])+?::").expect("valid regex"));
static NAI_RANDOM_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\|\|[^|]+(?:\|[^|]+)*\|\|").expect("valid regex"));
static SD_WEIGHT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\([^()]+:\d*\.?\d+\)").expect("valid regex"));
static LORA_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)<lora:[^>]+>").expect("valid regex"));
static EMBED_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)<(?:embedding|hypernet):[^>]+>").expect("valid regex"));
static DP_CHOICE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\{[^{}]+\|[^{}]+\}").expect("valid regex"));
static DP_WILDCARD_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"__[a-zA-Z0-9_\-/]+__").expect("valid regex"));

pub async fn engine_js(State(state): State<SharedState>) -> Response {
    asset_response(&state, ENGINE_PARTS, "application/javascript")
}

pub async fn widget_js(State(state): State<SharedState>) -> Response {
    asset_response(&state, WIDGET_PARTS, "application/javascript")
}

pub async fn style_css(State(state): State<SharedState>) -> Response {
    asset_response(&state, STYLE_PARTS, "text/css")
}

pub async fn analyze(body: Result<Json<Value>, JsonRejection>) -> Response {
    let text = match body {
        Ok(Json(value)) => value
            .get("text")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        Err(_) => String::new(),
    };
    let (payload, status) = analyze_prompt_text(&text);
    (status, Json(payload)).into_response()
}

fn asset_response(state: &SharedState, parts: &[&str], content_type: &'static str) -> Response {
    let ext_dir = state
        .config
        .project_root
        .join("extensions/builtin_prompt_syntax");
    match bundle(&ext_dir, parts) {
        Ok(body) => {
            let mut response = body.into_response();
            response
                .headers_mut()
                .insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
            response
        }
        Err(error) => {
            tracing::error!(?error, ?parts, "failed to build prompt syntax asset");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"error": "Failed to build asset"})),
            )
                .into_response()
        }
    }
}

fn bundle(ext_dir: &Path, parts: &[&str]) -> Result<String, std::io::Error> {
    let mut chunks = Vec::with_capacity(parts.len());
    for part in parts {
        chunks.push(fs::read_to_string(ext_dir.join(part))?);
    }
    Ok(chunks.join("\n"))
}

fn analyze_prompt_text(text: &str) -> (Value, StatusCode) {
    if text.is_empty() {
        return (
            json!({"error": "No text provided"}),
            StatusCode::BAD_REQUEST,
        );
    }

    let nai = NAI_WEIGHT_RE.find_iter(text).count() + NAI_RANDOM_RE.find_iter(text).count();
    let sd = SD_WEIGHT_RE.find_iter(text).count()
        + LORA_RE.find_iter(text).count()
        + EMBED_RE.find_iter(text).count();
    let dp = DP_CHOICE_RE.find_iter(text).count() + DP_WILDCARD_RE.find_iter(text).count();

    let syntax = if nai > 0 && sd > 0 {
        "mixed"
    } else if nai > 0 {
        "nai"
    } else if sd > 0 {
        "sd"
    } else if dp > 0 {
        "dynamic_prompts"
    } else {
        "unknown"
    };

    let mut warnings = Vec::new();
    if nai > 0 && sd > 0 {
        warnings.push(json!({"level": "warning", "message": "NAI構文とSD構文が混在しています"}));
    }
    warnings.extend(balance_warnings(text));

    (
        json!({
            "syntax": syntax,
            "indicators": {"nai": nai, "sd": sd, "dp": dp},
            "warnings": warnings,
            "tag_count": text.split(',').filter(|part| !part.trim().is_empty()).count(),
        }),
        StatusCode::OK,
    )
}

fn balance_warnings(text: &str) -> Vec<Value> {
    let mut warnings = Vec::new();
    for (open_ch, close_ch, name) in [
        ('(', ')', "丸括弧"),
        ('{', '}', "波括弧"),
        ('[', ']', "角括弧"),
    ] {
        let mut depth = 0_i64;
        for ch in text.chars() {
            if ch == open_ch {
                depth += 1;
            } else if ch == close_ch {
                depth -= 1;
            }
        }
        if depth != 0 {
            warnings.push(json!({
                "level": "error",
                "message": format!("{name}の数が一致しません（差: {depth:+}）"),
            }));
        }
    }
    warnings
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn analyze_detects_mixed_syntax_and_counts_tags() {
        let (payload, status) = analyze_prompt_text("1.2::cat::, (dog:1.1), __wild__");
        assert_eq!(status, StatusCode::OK);
        assert_eq!(payload["syntax"], "mixed");
        assert_eq!(payload["indicators"]["nai"], 1);
        assert_eq!(payload["indicators"]["sd"], 1);
        assert_eq!(payload["indicators"]["dp"], 1);
        assert_eq!(payload["tag_count"], 3);
    }

    #[test]
    fn analyze_reports_balance_warning() {
        let (payload, status) = analyze_prompt_text("(cat");
        assert_eq!(status, StatusCode::OK);
        assert_eq!(
            payload["warnings"][0]["message"],
            "丸括弧の数が一致しません（差: +1）"
        );
    }

    #[test]
    fn matches_python_golden_analyze_fixtures() {
        let fixture: Value =
            serde_json::from_str(include_str!("../../tests/fixtures/e1_golden.json"))
                .expect("valid fixture");
        for case in fixture["analyze"].as_array().expect("analyze cases") {
            let input = case["input"].as_str().expect("input");
            let expected_status = case["status"].as_u64().expect("status");
            let expected_payload = &case["payload"];
            let (payload, status) = analyze_prompt_text(input);
            assert_eq!(status.as_u16() as u64, expected_status);
            assert_eq!(&payload, expected_payload);
        }
    }
}
