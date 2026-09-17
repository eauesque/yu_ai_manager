//! Structured extraction of the special tokens A1111-style prompts carry:
//! `<lora:name:weight>`, `<embedding:name>`, `<hypernet:name>` and their
//! parenthesised and bare variants.
//!
//! A port of `core/parsers/prompt_extract_special.py`, which the four builtin
//! `on_build_sections` implementations use to render the LoRA / Embedding
//! tables in a file's detail view.

use fancy_regex::Regex;
use serde_json::{json, Value};
use std::sync::OnceLock;

fn lora_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)<lora:([^:>]+):([^>]+)>").unwrap())
}

/// The leading numeric weight of a LoRA's parameter list.
fn leading_number_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"^(-?\d*\.?\d+)").unwrap())
}

fn embed_angle_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)<embedding:([^:>]+)(?::([^>]*))?>").unwrap())
}

fn hypernet_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)<hypernet:([^:>]+)(?::([^>]*))?>").unwrap())
}

fn embed_paren_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)\(embedding:([^:)]+)(?::([^)]*))?\)").unwrap())
}

/// Bare `embedding:name`, excluding the angle and paren forms via a lookbehind.
fn embed_bare_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?i)(?<![<(])embedding:([A-Za-z0-9_\-.]+)").unwrap())
}

/// `[{"name", "weight", "extra"?}]` for every `<lora:...>` in the prompt.
///
/// The extended syntax (`<lora:name:1:1:lbw=0,0,1>`) keeps everything past the
/// weight in `extra` rather than being dropped or mis-parsed as the weight.
pub fn extract_loras(prompt: &str) -> Vec<Value> {
    let mut out = Vec::new();
    for caps in lora_re().captures_iter(prompt).flatten() {
        let Some(name) = caps.get(1).map(|m| m.as_str().trim().to_string()) else {
            continue;
        };
        let params = caps.get(2).map(|m| m.as_str().trim()).unwrap_or("");
        let leading = leading_number_re()
            .captures(params)
            .ok()
            .flatten()
            .and_then(|c| c.get(1).map(|m| (m.as_str().to_string(), m.end())));
        let (weight, rest) = match leading {
            Some((text, end)) => (text.parse::<f64>().unwrap_or(1.0), &params[end..]),
            None => (1.0, params),
        };
        let mut entry = json!({"name": name, "weight": weight});
        let extra = rest.trim_start_matches(':').trim();
        if !extra.is_empty() {
            entry["extra"] = json!(extra);
        }
        out.push(entry);
    }
    out
}

/// `[{"name", "weight", "type"}]` for embeddings and hypernetworks.
///
/// The bare form is matched last and only outside spans already claimed by the
/// angle/paren forms; without that, `<embedding:x>` would also yield a bare
/// `embedding:x` and double-count.
pub fn extract_embeddings(prompt: &str) -> Vec<Value> {
    let mut out = Vec::new();
    let mut seen_spans: Vec<(usize, usize)> = Vec::new();

    /// A non-numeric weight falls back to 1.0 rather than dropping the entry,
    /// matching Python's suppressed ValueError.
    fn push(
        out: &mut Vec<Value>,
        seen_spans: &mut Vec<(usize, usize)>,
        name: Option<&str>,
        weight: Option<&str>,
        kind: &str,
        span: (usize, usize),
    ) {
        let Some(name) = name.map(str::trim).filter(|n| !n.is_empty()) else {
            return;
        };
        let w = weight
            .map(str::trim)
            .and_then(|t| t.parse::<f64>().ok())
            .unwrap_or(1.0);
        seen_spans.push(span);
        out.push(json!({"name": name, "weight": w, "type": kind}));
    }

    for (re, kind) in [
        (embed_angle_re(), "embedding"),
        (hypernet_re(), "hypernet"),
        (embed_paren_re(), "embedding"),
    ] {
        for caps in re.captures_iter(prompt).flatten() {
            let Some(whole) = caps.get(0) else { continue };
            push(
                &mut out,
                &mut seen_spans,
                caps.get(1).map(|m| m.as_str()),
                caps.get(2).map(|m| m.as_str()),
                kind,
                (whole.start(), whole.end()),
            );
        }
    }

    for caps in embed_bare_re().captures_iter(prompt).flatten() {
        let Some(whole) = caps.get(0) else { continue };
        let (s, e) = (whole.start(), whole.end());
        if seen_spans.iter().any(|&(ss, se)| ss <= s && e <= se) {
            continue;
        }
        push(
            &mut out,
            &mut seen_spans,
            caps.get(1).map(|m| m.as_str()),
            None,
            "embedding",
            (s, e),
        );
    }

    out
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loras_carry_name_weight_and_extended_params() {
        let found = extract_loras("a <lora:styleA:0.8> b <lora:blk:1:1:lbw=0,0,1> c");
        assert_eq!(found.len(), 2);
        assert_eq!(found[0]["name"], json!("styleA"));
        assert_eq!(found[0]["weight"], json!(0.8));
        assert!(found[0].get("extra").is_none());
        // Everything past the weight is kept, not parsed as the weight.
        assert_eq!(found[1]["weight"], json!(1.0));
        assert_eq!(found[1]["extra"], json!("1:lbw=0,0,1"));
    }

    #[test]
    fn a_lora_without_a_numeric_weight_defaults_to_one() {
        let found = extract_loras("<lora:name:abc>");
        assert_eq!(found[0]["weight"], json!(1.0));
        assert_eq!(found[0]["extra"], json!("abc"));
    }

    #[test]
    fn negative_weights_survive() {
        let found = extract_loras("<lora:n:-0.5>");
        assert_eq!(found[0]["weight"], json!(-0.5));
    }

    #[test]
    fn embeddings_cover_all_four_spellings() {
        let found =
            extract_embeddings("<embedding:e1:0.5> <hypernet:h1> (embedding:e2:2) embedding:e3");
        let names: Vec<&str> = found.iter().map(|e| e["name"].as_str().unwrap()).collect();
        assert_eq!(names, vec!["e1", "h1", "e2", "e3"]);
        assert_eq!(found[0]["weight"], json!(0.5));
        assert_eq!(found[1]["type"], json!("hypernet"));
        assert_eq!(found[2]["weight"], json!(2.0));
        assert_eq!(found[3]["weight"], json!(1.0));
    }

    /// The bare pattern also matches inside `<embedding:x>`; the span check is
    /// what keeps that from producing a duplicate entry.
    #[test]
    fn the_bare_form_does_not_double_count_the_angle_form() {
        let found = extract_embeddings("<embedding:solo>");
        assert_eq!(found.len(), 1, "got {found:?}");
        assert_eq!(found[0]["name"], json!("solo"));
    }

    #[test]
    fn nothing_special_yields_nothing() {
        assert!(extract_loras("1girl, solo").is_empty());
        assert!(extract_embeddings("1girl, solo").is_empty());
    }
}
