use std::sync::LazyLock;

use regex::{Captures, Regex};

const SD_BASE: f64 = 1.1;
const NAI_BASE: f64 = 1.05;
const W_NUM: &str = r"\d*\.?\d+";
const W_SNUM: &str = r"-?\d*\.?\d+";
const ESC_TOKENS: [&str; 6] = [r"\(", r"\)", r"\[", r"\]", r"\{", r"\}"];

static LORA_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)<lora:[^>]+>").expect("valid regex"));
static LYCO_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)<lyco:[^>]+>").expect("valid regex"));
static EMBED_TAG_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)<(?:embedding|hypernet):[^>]+>").expect("valid regex"));
static EMBED_PAREN_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\(embedding:[^)]+\)").expect("valid regex"));
static EMBED_BARE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"(?i)\bembedding:\S+").expect("valid regex"));
static SD_CHOICE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\{([^{}]+(?:\|[^{}]+)+)\}").expect("valid regex"));
static NAI_CHOICE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\|\|([^|]+(?:\|[^|]+)*)\|\|").expect("valid regex"));
static SD_WEIGHT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(&format!(r"\(([^()]+?):\s*({W_SNUM})\s*\)")).expect("valid regex"));
static NAI_WEIGHT_RE: LazyLock<Regex> = LazyLock::new(|| {
    Regex::new(&format!(r"({W_SNUM})::((?:[^:]|:[^:])+?)::")).expect("valid regex")
});
static SD_EMPHASIS_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\(([^()]+)\)").expect("valid regex"));
static SD_WEIGHT_INNER_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\(([^():]+):(-?\d*\.?\d+)\)").expect("valid regex"));
static NAI_BRACE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\{([^{}]+)\}").expect("valid regex"));
static SD_BRACKET_WEAK_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[+([^\[\]:]+)\]+").expect("valid regex"));
static NAI_BRACKET_WEAK_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\[+([^\[\]]+)\]+").expect("valid regex"));
static MULTI_COMMA_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\s*,\s*,+").expect("valid regex"));
static EDGE_COMMA_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"^\s*,+\s*|\s*,+\s*$").expect("valid regex"));
static MULTI_SPACE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\s{2,}").expect("valid regex"));
static AND_SPLIT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\s+AND\s+").expect("valid regex"));
static AND_WEIGHT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(&format!(r"^(.+?)\s*:({W_SNUM})\s*$")).expect("valid regex"));
static SD_MIX_WEIGHT_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(&format!(r"^\s*\([^()]+:{W_SNUM}\)\s*$")).expect("valid regex"));
static DP_CHOICE_RE: LazyLock<Regex> =
    LazyLock::new(|| Regex::new(r"\{[^{}]*\|[^{}]*\}").expect("valid regex"));

pub fn convert_sd_to_nai(
    prompt: &str,
    strip_lora: bool,
    strip_embedding: bool,
    convert_emphasis: bool,
) -> String {
    if prompt.is_empty() {
        return String::new();
    }

    let (mut result, saved_esc) = protect_escapes(prompt);

    if strip_lora {
        result = LORA_RE.replace_all(&result, "").into_owned();
        result = LYCO_RE.replace_all(&result, "").into_owned();
    }

    if strip_embedding {
        result = EMBED_TAG_RE.replace_all(&result, "").into_owned();
        result = EMBED_PAREN_RE.replace_all(&result, "").into_owned();
        result = EMBED_BARE_RE.replace_all(&result, "").into_owned();
    }

    result = SD_CHOICE_RE
        .replace_all(&result, |caps: &Captures| format!("||{}||", &caps[1]))
        .into_owned();
    result = SD_WEIGHT_RE
        .replace_all(&result, |caps: &Captures| {
            format!("{}::{}::", &caps[2], safe_close(caps[1].trim_end()))
        })
        .into_owned();

    if convert_emphasis {
        result = convert_sd_emphasis_to_nai(&result);
        result = convert_bracket_weaken_to_nai(&result);
    }

    if result.contains(" AND ") {
        result = convert_and_to_mixing(&result);
    }

    result = MULTI_COMMA_RE.replace_all(&result, ",").into_owned();
    result = EDGE_COMMA_RE.replace_all(&result, "").into_owned();
    result = MULTI_SPACE_RE.replace_all(&result, " ").into_owned();
    restore_escapes(result, &saved_esc).trim().to_string()
}

pub fn convert_nai_to_sd(prompt: &str, convert_emphasis: bool) -> String {
    if prompt.is_empty() {
        return String::new();
    }

    let (mut result, saved_esc) = protect_escapes(prompt);

    result = NAI_WEIGHT_RE
        .replace_all(&result, |caps: &Captures| {
            format!("({}:{})", caps[2].trim_end(), &caps[1])
        })
        .into_owned();

    result = NAI_CHOICE_RE
        .replace_all(&result, |caps: &Captures| format!("{{{}}}", &caps[1]))
        .into_owned();

    if convert_emphasis {
        result = convert_nai_emphasis_to_sd(&result);
        result = convert_bracket_weaken_to_sd(&result);
    }

    if result.contains('|') {
        result = convert_nai_mixing_to_sd(&result);
    }

    restore_escapes(result, &saved_esc).trim().to_string()
}

fn protect_escapes(input: &str) -> (String, Vec<String>) {
    let mut text = input.to_string();
    let mut saved = Vec::new();
    for esc in ESC_TOKENS {
        while let Some(pos) = text.find(esc) {
            saved.push(esc.to_string());
            let token = format!("\0E{}\0", saved.len() - 1);
            text.replace_range(pos..pos + esc.len(), &token);
        }
    }
    (text, saved)
}

fn restore_escapes(mut text: String, saved: &[String]) -> String {
    for (idx, saved_text) in saved.iter().enumerate() {
        text = text.replace(&format!("\0E{idx}\0"), saved_text);
    }
    text
}

fn w(value: f64) -> String {
    let rounded = (value * 1_000_000.0).round() / 1_000_000.0;
    let mut text = format!("{rounded:.6}");
    while text.contains('.') && text.ends_with('0') {
        text.pop();
    }
    if text.ends_with('.') {
        text.push('0');
    }
    text
}

fn safe_close(text: &str) -> String {
    if text
        .chars()
        .last()
        .is_some_and(|ch| ch.is_ascii_digit() || ch == '.')
    {
        format!("{text} ")
    } else {
        text.to_string()
    }
}

fn convert_sd_emphasis_to_nai(input: &str) -> String {
    let (mut text, saved) = protect_escapes(input);
    while SD_EMPHASIS_RE.is_match(&text) {
        text = SD_EMPHASIS_RE
            .replace_all(&text, |caps: &Captures| {
                let inner = &caps[1];
                if inner.contains("::") {
                    merge_nai_weights(inner, SD_BASE)
                } else {
                    format!("{}::{}::", w(SD_BASE), safe_close(inner))
                }
            })
            .into_owned();
    }
    restore_escapes(text, &saved)
}

fn merge_nai_weights(inner: &str, multiplier: f64) -> String {
    let mut parts = Vec::new();
    let mut last_end = 0;
    for caps in NAI_WEIGHT_RE.captures_iter(inner) {
        let whole = caps.get(0).expect("whole match");
        let before = inner[last_end..whole.start()]
            .trim()
            .trim_matches(',')
            .trim();
        if !before.is_empty() {
            parts.push(format!("{}::{}::", w(multiplier), safe_close(before)));
        }
        let inner_w = caps[1].parse::<f64>().unwrap_or(0.0);
        parts.push(format!(
            "{}::{}::",
            w(inner_w * multiplier),
            safe_close(&caps[2])
        ));
        last_end = whole.end();
    }
    let after = inner[last_end..].trim().trim_matches(',').trim();
    if !after.is_empty() {
        parts.push(format!("{}::{}::", w(multiplier), safe_close(after)));
    }
    parts.join(", ")
}

fn convert_nai_emphasis_to_sd(input: &str) -> String {
    let (mut text, saved) = protect_escapes(input);
    let mut previous: Option<String> = None;
    while previous.as_deref() != Some(&text) {
        previous = Some(text.clone());
        text = NAI_BRACE_RE
            .replace_all(&text, |caps: &Captures| {
                let inner = &caps[1];
                if inner.contains('|') {
                    caps[0].to_string()
                } else if SD_WEIGHT_INNER_RE.is_match(inner) {
                    merge_sd_weights(inner, NAI_BASE)
                } else {
                    format!("({}:{})", inner, w(NAI_BASE))
                }
            })
            .into_owned();
    }
    restore_escapes(text, &saved)
}

fn merge_sd_weights(inner: &str, multiplier: f64) -> String {
    let mut parts = Vec::new();
    let mut last_end = 0;
    for caps in SD_WEIGHT_INNER_RE.captures_iter(inner) {
        let whole = caps.get(0).expect("whole match");
        let before = inner[last_end..whole.start()]
            .trim()
            .trim_matches(',')
            .trim();
        if !before.is_empty() {
            parts.push(format!("({}:{})", before, w(multiplier)));
        }
        let inner_w = caps[2].parse::<f64>().unwrap_or(0.0);
        parts.push(format!("({}:{})", &caps[1], w(inner_w * multiplier)));
        last_end = whole.end();
    }
    let after = inner[last_end..].trim().trim_matches(',').trim();
    if !after.is_empty() {
        parts.push(format!("({}:{})", after, w(multiplier)));
    }
    parts.join(", ")
}

fn convert_bracket_weaken_to_nai(text: &str) -> String {
    SD_BRACKET_WEAK_RE
        .replace_all(text, |caps: &Captures| {
            let full = &caps[0];
            let depth = full.chars().take_while(|ch| *ch == '[').count();
            let inner = &full[depth..full.len() - depth];
            format!(
                "{}::{}::",
                w((1.0 / SD_BASE).powi(i32::try_from(depth).unwrap_or(i32::MAX))),
                safe_close(inner)
            )
        })
        .into_owned()
}

fn convert_bracket_weaken_to_sd(text: &str) -> String {
    NAI_BRACKET_WEAK_RE
        .replace_all(text, |caps: &Captures| {
            let full = &caps[0];
            let depth = full.chars().take_while(|ch| *ch == '[').count();
            let inner = &full[depth..full.len() - depth];
            format!(
                "({}:{})",
                inner,
                w((1.0 / NAI_BASE).powi(i32::try_from(depth).unwrap_or(i32::MAX)))
            )
        })
        .into_owned()
}

fn convert_and_to_mixing(text: &str) -> String {
    AND_SPLIT_RE
        .split(text)
        .map(|part| {
            let part = part.trim();
            AND_WEIGHT_RE.captures(part).map_or_else(
                || part.to_string(),
                |caps| format!("{}:{}", caps[1].trim(), &caps[2]),
            )
        })
        .collect::<Vec<_>>()
        .join("|")
}

fn convert_nai_mixing_to_sd(text: &str) -> String {
    let mut saved = Vec::new();
    let mut protected = NAI_CHOICE_RE
        .replace_all(text, |caps: &Captures| {
            saved.push(caps[0].to_string());
            format!("\0S{}\0", saved.len() - 1)
        })
        .into_owned();
    protected = DP_CHOICE_RE
        .replace_all(&protected, |caps: &Captures| {
            saved.push(caps[0].to_string());
            format!("\0S{}\0", saved.len() - 1)
        })
        .into_owned();

    if protected.contains('|') {
        let parts = protected.split('|').collect::<Vec<_>>();
        let all_weighted = parts.iter().all(|part| SD_MIX_WEIGHT_RE.is_match(part));
        protected = if all_weighted {
            parts.join("|")
        } else {
            parts
                .iter()
                .map(|part| part.trim())
                .collect::<Vec<_>>()
                .join(" AND ")
        };
    }

    for (idx, saved_text) in saved.iter().enumerate() {
        protected = protected.replace(&format!("\0S{idx}\0"), saved_text);
    }
    protected
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn converts_sd_weight_and_nested_emphasis() {
        assert_eq!(
            convert_sd_to_nai("(cat:1.2)", true, true, true),
            "1.2::cat::"
        );
        assert_eq!(
            convert_sd_to_nai("((cat))", true, true, true),
            "1.21::cat::"
        );
    }

    #[test]
    fn pads_digit_suffix_for_nai_close() {
        assert_eq!(
            convert_sd_to_nai("(artist:coupe50:1.2)", true, true, true),
            "1.2::artist:coupe50 ::"
        );
        assert_eq!(
            convert_nai_to_sd("1.2::artist:coupe50 ::", true),
            "(artist:coupe50:1.2)"
        );
    }

    #[test]
    fn protects_escaped_brackets() {
        let input = r"\(literal\), \[weak\], \{brace\}";
        assert_eq!(convert_sd_to_nai(input, true, true, true), input);
        assert_eq!(convert_nai_to_sd(input, true), input);
    }

    #[test]
    fn converts_dynamic_choices_and_mixing() {
        assert_eq!(convert_sd_to_nai("{a|b|c}", true, true, true), "||a|b|c||");
        assert_eq!(convert_nai_to_sd("||a|b|c||", true), "{a|b|c}");
        assert_eq!(
            convert_sd_to_nai("cat AND dog:0.5", true, true, true),
            "cat|dog:0.5"
        );
        assert_eq!(convert_nai_to_sd("cat|dog", true), "cat AND dog");
    }

    #[test]
    fn strips_lora_and_embedding_by_default() {
        assert_eq!(
            convert_sd_to_nai("cat, <lora:test:1>, embedding:bad", true, true, true),
            "cat"
        );
        assert_eq!(
            convert_sd_to_nai("cat, <lora:test:1>", false, true, true),
            "cat, <lora:test:1>"
        );
    }

    #[test]
    fn converts_bracket_weaken() {
        assert_eq!(
            convert_sd_to_nai("[cat]", true, true, true),
            "0.909091::cat::"
        );
        assert_eq!(convert_nai_to_sd("[cat]", true), "(cat:0.952381)");
    }

    #[test]
    fn matches_python_golden_conversion_fixtures() {
        let fixture: serde_json::Value =
            serde_json::from_str(include_str!("../../tests/fixtures/e1_golden.json"))
                .expect("valid fixture");
        for case in fixture["sd_to_nai"].as_array().expect("sd cases") {
            let input = case["input"].as_str().expect("input");
            let expected = case["output"].as_str().expect("output");
            assert_eq!(convert_sd_to_nai(input, true, true, true), expected);
        }
        for case in fixture["nai_to_sd"].as_array().expect("nai cases") {
            let input = case["input"].as_str().expect("input");
            let expected = case["output"].as_str().expect("output");
            assert_eq!(convert_nai_to_sd(input, true), expected);
        }
    }
}
