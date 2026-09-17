use fancy_regex::Regex;
use serde_json::Value;
use std::collections::{HashMap, HashSet};
use std::sync::OnceLock;

const W_NUM: &str = r"\d*\.?\d+";
const W_SNUM: &str = r"-?\d*\.?\d+";
const SD_BASE: f64 = 1.1;
const NAI_BASE: f64 = 1.05;
const MAX_TAG_LENGTH: usize = 80;
const MAX_NAMESPACE_LENGTH: usize = 50;

const BLOCKED_NAMESPACES: &[&str] = &[
    "model",
    "model hash",
    "sampler",
    "seed",
    "steps",
    "cfg scale",
    "clip skip",
    "size",
    "version",
    "vae",
    "vae hash",
    "denoising strength",
    "hires upscale",
    "hires steps",
    "hires upscaler",
    "rng",
    "schedule type",
    "token merging ratio",
];

static NAI_WEIGHT_RE: OnceLock<Regex> = OnceLock::new();
static SD_WEIGHT_RE: OnceLock<Regex> = OnceLock::new();
static LBW_FRAGMENT_RE: OnceLock<Regex> = OnceLock::new();
static LORA_FRAGMENT_RE: OnceLock<Regex> = OnceLock::new();
static SD_ALTERNATION_RE: OnceLock<Regex> = OnceLock::new();
static BRACE_EMPHASIS_RE: OnceLock<Regex> = OnceLock::new();
static NAI_CHOICE_RE: OnceLock<Regex> = OnceLock::new();
static BRACE_CHOICE_RE: OnceLock<Regex> = OnceLock::new();
static BREAK_RE: OnceLock<Regex> = OnceLock::new();
static BREAK_TAG_RE: OnceLock<Regex> = OnceLock::new();
static BARE_COLON_RE: OnceLock<Regex> = OnceLock::new();
static WILDCARD_VAR_RE: OnceLock<Regex> = OnceLock::new();
static ANGLE_BLOCK_RE: OnceLock<Regex> = OnceLock::new();
static ADJACENT_WEIGHT_RE: OnceLock<Regex> = OnceLock::new();
static BROKEN_WEIGHT_RE: OnceLock<Regex> = OnceLock::new();
static WORD_CHAR_RE: OnceLock<Regex> = OnceLock::new();
static COLON_PREFIX_RE: OnceLock<Regex> = OnceLock::new();
static NUMERIC_RE: OnceLock<Regex> = OnceLock::new();
static SPLIT_NAMESPACE_NUMERIC_RE: OnceLock<Regex> = OnceLock::new();
static SPLIT_NAMESPACE_CLEAN_RE: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_1: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_2: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_3: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_4: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_5: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_6: OnceLock<Regex> = OnceLock::new();
static CLEAN_RE_7: OnceLock<Regex> = OnceLock::new();

fn nai_weight_re() -> &'static Regex {
    NAI_WEIGHT_RE.get_or_init(|| Regex::new(&format!(r"({W_SNUM})::((?:[^:]|:[^:])+?)::")).unwrap())
}

// Python uses `SD_WEIGHT_RE.match(c)` (anchored to the start of the string,
// unlike NAI_WEIGHT_RE's `.search()`). fancy_regex's `captures()` behaves
// like Python's `re.search` — an unanchored `.captures()` call here would
// match a nested "(word:1.2)" substring inside e.g. "((word:1.2))" instead
// of correctly falling through to paren-counting. The leading `^` restores
// match-from-start semantics equivalent to Python's `.match()`.
fn sd_weight_re() -> &'static Regex {
    SD_WEIGHT_RE.get_or_init(|| Regex::new(&format!(r"^\(([^()]+):({W_NUM})\)")).unwrap())
}

fn lbw_fragment_re() -> &'static Regex {
    LBW_FRAGMENT_RE.get_or_init(|| Regex::new(r"^[\d.]+>?$").unwrap())
}

fn lora_fragment_re() -> &'static Regex {
    LORA_FRAGMENT_RE.get_or_init(|| Regex::new(r".*:[\d.]+>").unwrap())
}

fn sd_alternation_re() -> &'static Regex {
    SD_ALTERNATION_RE
        .get_or_init(|| Regex::new(&format!(r"\[[^\[\]]*:[^\[\]]*:{W_NUM}\]")).unwrap())
}

fn brace_emphasis_re() -> &'static Regex {
    BRACE_EMPHASIS_RE.get_or_init(|| Regex::new(r"\{+([^{}|]+?)\}+").unwrap())
}

fn nai_choice_re() -> &'static Regex {
    NAI_CHOICE_RE.get_or_init(|| Regex::new(r"\|\|(?P<body>[^|].*?)\|\|").unwrap())
}

fn brace_choice_re() -> &'static Regex {
    BRACE_CHOICE_RE.get_or_init(|| Regex::new(r"\{(?P<body>[^{}]+)\}").unwrap())
}

fn break_re() -> &'static Regex {
    BREAK_RE.get_or_init(|| Regex::new(r"(?<![a-zA-Z])BREAK(?![a-zA-Z])").unwrap())
}

fn break_tag_re() -> &'static Regex {
    BREAK_TAG_RE.get_or_init(|| Regex::new(r"(?i)<break>").unwrap())
}

fn bare_colon_re() -> &'static Regex {
    BARE_COLON_RE.get_or_init(|| Regex::new(r"(?<!\d)::(?!\d)").unwrap())
}

fn wildcard_var_re() -> &'static Regex {
    WILDCARD_VAR_RE.get_or_init(|| Regex::new(r"\$\{[^}]*\}").unwrap())
}

fn angle_block_re() -> &'static Regex {
    ANGLE_BLOCK_RE.get_or_init(|| Regex::new(r"<[^>]+>").unwrap())
}

fn adjacent_weight_re() -> &'static Regex {
    ADJACENT_WEIGHT_RE.get_or_init(|| Regex::new(r"\)\s*(?:(?:and|AND)\s+)?(?=\()").unwrap())
}

fn broken_weight_re() -> &'static Regex {
    BROKEN_WEIGHT_RE.get_or_init(|| Regex::new(&format!(r"^(.+?):({W_NUM})\)$")).unwrap())
}

fn word_char_re() -> &'static Regex {
    WORD_CHAR_RE.get_or_init(|| Regex::new(r"\w").unwrap())
}

fn colon_prefix_re() -> &'static Regex {
    COLON_PREFIX_RE.get_or_init(|| Regex::new(r"^:[\d.]+$").unwrap())
}

fn numeric_re() -> &'static Regex {
    NUMERIC_RE.get_or_init(|| Regex::new(r"^[\d.]+$").unwrap())
}

fn split_namespace_numeric_re() -> &'static Regex {
    SPLIT_NAMESPACE_NUMERIC_RE.get_or_init(|| Regex::new(r"^[\d.]+\)?$").unwrap())
}

fn split_namespace_clean_re() -> &'static Regex {
    SPLIT_NAMESPACE_CLEAN_RE.get_or_init(|| Regex::new(r":[\d.]+\)?$").unwrap())
}

fn clean_re_1() -> &'static Regex {
    CLEAN_RE_1.get_or_init(|| Regex::new(r":[\d.]+\)").unwrap())
}

fn clean_re_2() -> &'static Regex {
    CLEAN_RE_2.get_or_init(|| Regex::new(r"(?<!\w)(?<!\\)\((?!\w)").unwrap())
}

fn clean_re_3() -> &'static Regex {
    CLEAN_RE_3.get_or_init(|| Regex::new(r"(?<!\w)(?<!\\)\)|(?<!\\)\)(?!\w)").unwrap())
}

fn clean_re_4() -> &'static Regex {
    CLEAN_RE_4.get_or_init(|| Regex::new(r"^\(+|(?<!\\)\)+$").unwrap())
}

fn clean_re_5() -> &'static Regex {
    CLEAN_RE_5.get_or_init(|| Regex::new(r"(?<!\w)\{(?!\w)").unwrap())
}

fn clean_re_6() -> &'static Regex {
    CLEAN_RE_6.get_or_init(|| Regex::new(r"(?<!\w)\}|\}(?!\w)").unwrap())
}

fn clean_re_7() -> &'static Regex {
    CLEAN_RE_7.get_or_init(|| Regex::new(r"^\{+|\}+$").unwrap())
}

fn norm_space(s: &str) -> String {
    s.split_whitespace().collect::<Vec<_>>().join(" ")
}

fn split_namespace(tag: &str) -> (Option<String>, String) {
    let tag = norm_space(tag);
    if let Some((ns, raw_rest)) = tag.split_once(':') {
        let ns = norm_space(ns);
        let rest = norm_space(raw_rest);
        if !ns.is_empty() && !rest.is_empty() {
            if split_namespace_numeric_re()
                .is_match(&rest)
                .unwrap_or(false)
            {
                let cleaned = split_namespace_clean_re().replace_all(&tag, "").to_string();
                return (None, norm_space(&cleaned));
            }
            return (Some(ns), rest);
        }
    }
    (None, tag)
}

pub fn _should_apply_sd_paren_weight(prompt_syntax: &str, candidate: &str) -> bool {
    match prompt_syntax.trim().to_lowercase().as_str() {
        "sd" => true,
        "nai" => false,
        _ => !candidate.contains("::") && !candidate.contains("||"),
    }
}

/// The two `count as i32` exponents below are bracket-nesting depths counted
/// off the candidate string, so reaching `i32::MAX` would need a two-billion
/// character prompt of nothing but brackets; `powi` has already gone to
/// infinity long before that, in both this implementation and Python's.
#[allow(clippy::cast_possible_truncation)]
pub fn parse_candidate(
    c: &str,
    brace_choice: bool,
    prompt_syntax: &str,
) -> Option<(Option<String>, String, f64)> {
    let c = norm_space(c);
    if c.is_empty() {
        return None;
    }

    if c.starts_with("<lora:") || c.starts_with("<lyco:") || c.starts_with("<hypernet:") {
        return None;
    }

    if c.starts_with(':') {
        return None;
    }

    if lbw_fragment_re().is_match(&c).unwrap_or(false) {
        return None;
    }

    if lora_fragment_re().is_match(&c).unwrap_or(false) {
        return None;
    }

    if c.starts_with("||") && c.ends_with("||") {
        return None;
    }

    if brace_choice && c.starts_with('{') && c.ends_with('}') && c.contains('|') {
        return None;
    }

    if let Ok(Some(caps)) = nai_weight_re().captures(&c) {
        let w = caps.get(1).and_then(|m| m.as_str().parse::<f64>().ok())?;
        let content = caps.get(2).map(|m| m.as_str()).unwrap_or_default();
        let (ns, t) = split_namespace(&norm_space(content));
        return Some((ns, t, w));
    }

    if let Ok(Some(caps)) = sd_weight_re().captures(&c) {
        let content = caps.get(1).map(|m| m.as_str()).unwrap_or_default();
        let w = caps.get(2).and_then(|m| m.as_str().parse::<f64>().ok())?;
        let (ns, t) = split_namespace(&norm_space(content));
        return Some((ns, t, w));
    }

    if _should_apply_sd_paren_weight(prompt_syntax, &c) {
        let mut paren_count = 0usize;
        let mut temp = c.as_str();
        while temp.starts_with('(') && temp.ends_with(')') {
            paren_count += 1;
            temp = &temp[1..temp.len() - 1];
        }
        if paren_count > 0 {
            let weight = SD_BASE.powi(paren_count as i32);
            let (ns, t) = split_namespace(&norm_space(temp));
            return Some((ns, t, weight));
        }
    }

    let mut brace_count = 0usize;
    let mut temp = c.as_str();
    while temp.starts_with('{') && temp.ends_with('}') && !temp.contains('|') {
        brace_count += 1;
        temp = &temp[1..temp.len() - 1];
    }
    if brace_count > 0 {
        let content = norm_space(temp);
        if !content.is_empty() {
            let (ns, t) = split_namespace(&content);
            let weight = NAI_BASE.powi(brace_count as i32);
            return Some((ns, t, weight));
        }
    }

    if let Ok(Some(caps)) = broken_weight_re().captures(&c) {
        let content = caps.get(1).map(|m| m.as_str()).unwrap_or_default();
        let w = caps.get(2).and_then(|m| m.as_str().parse::<f64>().ok())?;
        let (ns, t) = split_namespace(&norm_space(content));
        if !numeric_re().is_match(&t).unwrap_or(false) {
            return Some((ns, t, w));
        }
    }

    let mut cleaned = c.to_string();
    cleaned = clean_re_1().replace_all(&cleaned, "").to_string();
    cleaned = clean_re_2().replace_all(&cleaned, "").to_string();
    cleaned = clean_re_3().replace_all(&cleaned, "").to_string();
    cleaned = clean_re_4().replace_all(&cleaned, "").to_string();
    cleaned = clean_re_5().replace_all(&cleaned, "").to_string();
    cleaned = clean_re_6().replace_all(&cleaned, "").to_string();
    cleaned = clean_re_7().replace_all(&cleaned, "").to_string();
    cleaned = norm_space(&cleaned);

    if cleaned.is_empty() {
        return None;
    }

    let (ns, t) = split_namespace(&cleaned);
    if t.is_empty() || !word_char_re().is_match(&t).unwrap_or(false) {
        return None;
    }

    Some((ns, t, 1.0))
}

pub fn normalize_tags(
    tags: Vec<(Option<String>, String, f64)>,
    lowercase_tags: bool,
) -> Vec<(Option<String>, String, f64)> {
    let mut normed = Vec::new();
    let mut seen: HashSet<(Option<String>, String)> = HashSet::new();

    for (ns, tag, weight) in tags {
        let mut ns2 = ns.map(|v| norm_space(&v));
        let mut t2 = norm_space(&tag);

        t2 = t2.trim_matches(',').trim().to_string();
        if let Some(ns) = ns2.as_ref() {
            ns2 = Some(ns.trim_matches(',').trim().to_string());
        }

        if lowercase_tags {
            if let Some(ns) = ns2.as_mut() {
                *ns = ns.to_lowercase();
            }
            t2 = t2.to_lowercase();
        }

        if t2.is_empty() || t2 == ":" {
            continue;
        }

        if !word_char_re().is_match(&t2).unwrap_or(false) {
            continue;
        }

        if colon_prefix_re().is_match(&t2).unwrap_or(false) {
            continue;
        }

        if let Some(ns) = ns2.as_ref() {
            let ns_colon = format!("{ns}:");
            if t2.starts_with(&ns_colon) {
                t2 = t2[ns.len() + 1..].trim().to_string();
            }
        }

        if t2.is_empty() {
            continue;
        }

        if t2.len() > MAX_TAG_LENGTH {
            continue;
        }

        if let Some(ns) = ns2.as_ref() {
            if ns.len() > MAX_NAMESPACE_LENGTH {
                ns2 = None;
            }
            if ns2.as_ref().is_some_and(|v| v.starts_with("adetailer")) {
                continue;
            }
            if ns2.as_ref().is_some_and(|v| v.contains("<lora")) {
                continue;
            }
            if ns2
                .as_ref()
                .is_some_and(|v| BLOCKED_NAMESPACES.contains(&v.as_str()))
            {
                ns2 = None;
            }
        }

        let w = (weight * 10_000.0).round() / 10_000.0;
        let key = (ns2.clone(), t2.clone());
        if seen.contains(&key) {
            continue;
        }
        seen.insert(key);
        normed.push((ns2, t2, w));
    }

    normed
}

#[derive(Debug, Clone, PartialEq)]
pub struct TemplateToken {
    pub token_type: String,
    pub payload: HashMap<String, Value>,
    pub position: usize,
}

#[derive(Debug, Clone, PartialEq)]
pub struct ParsedPrompt {
    pub raw_prompt: String,
    pub tags: Vec<(Option<String>, String, f64)>,
    pub template_tokens: Vec<TemplateToken>,
}

#[derive(Debug, Clone)]
pub struct PromptParseConfig {
    pub prompt_syntax: String,
    pub brace_choice: bool,
    pub preserve_templates: bool,
    pub lowercase_tags: bool,
}

impl Default for PromptParseConfig {
    fn default() -> Self {
        Self {
            prompt_syntax: "auto".to_string(),
            brace_choice: false,
            preserve_templates: true,
            lowercase_tags: true,
        }
    }
}

pub fn strip_sd_alternation(text: &str) -> String {
    sd_alternation_re().replace_all(text, "").to_string()
}

pub fn strip_break_keyword(text: &str) -> String {
    let text = break_tag_re().replace_all(text, ",").to_string();
    break_re().replace_all(&text, ",").to_string()
}

pub fn strip_nai_bare_colons(text: &str) -> String {
    bare_colon_re().replace_all(text, ",").to_string()
}

pub fn strip_nai_brace_emphasis(text: &str) -> String {
    brace_emphasis_re().replace_all(text, "$1").to_string()
}

pub fn strip_wildcard_vars(text: &str) -> String {
    wildcard_var_re().replace_all(text, "").to_string()
}

pub fn strip_angle_blocks(text: &str) -> String {
    angle_block_re().replace_all(text, "").to_string()
}

pub fn normalize_adjacent_weights(text: &str) -> String {
    adjacent_weight_re().replace_all(text, "),").to_string()
}

pub fn strip_a1111_positive_only(text: &str) -> String {
    if text.contains("\nNegative prompt:") && text.contains("\nSteps:") {
        let mut positive = Vec::new();
        for line in text.split('\n') {
            if line.starts_with("Negative prompt:") || line.starts_with("Steps:") {
                break;
            }
            positive.push(line);
        }
        return positive.join("\n").trim().to_string();
    }
    text.to_string()
}

pub fn preprocess_prompt_text(text: &str) -> String {
    let mut out = text.to_string();
    out = strip_sd_alternation(&out);
    out = strip_break_keyword(&out);
    out = strip_nai_bare_colons(&out);
    out = strip_nai_brace_emphasis(&out);
    out = strip_wildcard_vars(&out);
    out = strip_angle_blocks(&out);
    normalize_adjacent_weights(&out)
}

pub fn smart_split_by_comma(text: &str) -> Vec<String> {
    let mut result = Vec::new();
    let mut current = Vec::new();
    let mut paren_depth: usize = 0;
    let mut brace_depth: usize = 0;
    let mut angle_depth: usize = 0;

    for ch in text.chars() {
        match ch {
            '(' => {
                paren_depth += 1;
                current.push(ch);
            }
            ')' => {
                paren_depth = paren_depth.saturating_sub(1);
                current.push(ch);
            }
            '{' => {
                brace_depth += 1;
                current.push(ch);
            }
            '}' => {
                brace_depth = brace_depth.saturating_sub(1);
                current.push(ch);
            }
            '<' => {
                angle_depth += 1;
                current.push(ch);
            }
            '>' => {
                angle_depth = angle_depth.saturating_sub(1);
                current.push(ch);
            }
            ',' if paren_depth == 0 && brace_depth == 0 && angle_depth == 0 => {
                let segment = current.iter().collect::<String>();
                if !norm_space(&segment).is_empty() {
                    result.push(norm_space(&segment));
                }
                current.clear();
            }
            _ => current.push(ch),
        }
    }

    let tail = current.iter().collect::<String>();
    if !norm_space(&tail).is_empty() {
        result.push(norm_space(&tail));
    }

    result
}

pub fn extract_nai_choices(
    text: &str,
    config: &PromptParseConfig,
    template_tokens: &mut Vec<TemplateToken>,
) -> String {
    let mut out = Vec::new();
    let mut pos = 0usize;

    for match_res in nai_choice_re().find_iter(text) {
        let Ok(mat) = match_res else {
            continue;
        };
        if mat.start() > pos {
            out.push(text[pos..mat.start()].to_string());
        }

        let body = nai_choice_re()
            .captures(mat.as_str())
            .ok()
            .and_then(|caps| caps.and_then(|caps| caps.name("body")))
            .map(|m| m.as_str())
            .unwrap_or("");

        let choices: Vec<String> = body
            .split('|')
            .map(norm_space)
            .filter(|v| !v.is_empty())
            .collect();

        let mut payload = HashMap::new();
        payload.insert("syntax".to_string(), Value::String("|| ||".to_string()));
        payload.insert(
            "choices".to_string(),
            Value::Array(choices.iter().cloned().map(Value::String).collect()),
        );
        template_tokens.push(TemplateToken {
            token_type: "choice".to_string(),
            payload,
            position: template_tokens.len(),
        });

        if config.preserve_templates {
            out.push(mat.as_str().to_string());
        } else {
            out.push(choices.first().cloned().unwrap_or_default());
        }

        pos = mat.end();
    }

    out.push(text[pos..].to_string());
    out.join("")
}

pub fn extract_brace_choices(
    text: &str,
    config: &PromptParseConfig,
    template_tokens: &mut Vec<TemplateToken>,
) -> String {
    let mut out = Vec::new();
    let mut pos = 0usize;

    for match_res in brace_choice_re().find_iter(text) {
        let Ok(mat) = match_res else {
            continue;
        };
        if mat.start() > pos {
            out.push(text[pos..mat.start()].to_string());
        }

        let body = brace_choice_re()
            .captures(mat.as_str())
            .ok()
            .and_then(|caps| caps.and_then(|caps| caps.name("body")))
            .map(|m| m.as_str())
            .unwrap_or("");

        if !body.contains('|') {
            out.push(mat.as_str().to_string());
            pos = mat.end();
            continue;
        }

        let choices: Vec<String> = body
            .split('|')
            .map(norm_space)
            .filter(|v| !v.is_empty())
            .collect();

        let mut payload = HashMap::new();
        payload.insert("syntax".to_string(), Value::String("{ }".to_string()));
        payload.insert(
            "choices".to_string(),
            Value::Array(choices.iter().cloned().map(Value::String).collect()),
        );

        template_tokens.push(TemplateToken {
            token_type: "choice".to_string(),
            payload,
            position: template_tokens.len(),
        });

        if config.preserve_templates {
            out.push(mat.as_str().to_string());
        } else {
            out.push(choices.first().cloned().unwrap_or_default());
        }

        pos = mat.end();
    }

    out.push(text[pos..].to_string());
    out.join("")
}

pub fn parse_prompt_to_tags(raw: &str, config: &PromptParseConfig) -> ParsedPrompt {
    let mut text = strip_a1111_positive_only(raw);
    let mut template_tokens = Vec::new();

    text = extract_nai_choices(&text, config, &mut template_tokens);
    if config.brace_choice {
        text = extract_brace_choices(&text, config, &mut template_tokens);
    }

    text = preprocess_prompt_text(&text);

    let mut tags = Vec::new();
    for c in smart_split_by_comma(&text) {
        if let Some(parsed) = parse_candidate(&c, config.brace_choice, &config.prompt_syntax) {
            tags.push(parsed);
        }
    }

    for tok in &template_tokens {
        if tok.token_type != "choice" {
            continue;
        }

        let Some(Value::Array(choices)) = tok.payload.get("choices") else {
            continue;
        };

        for choice in choices {
            let Some(raw_choice) = choice.as_str() else {
                continue;
            };
            let (ns, t) = split_namespace(raw_choice);
            if !t.is_empty() {
                tags.push((ns, t, 1.0));
            }
        }
    }

    let tags = normalize_tags(tags, config.lowercase_tags);

    ParsedPrompt {
        raw_prompt: raw.to_string(),
        tags,
        template_tokens,
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_tags_lowercases_and_dedupes() {
        let input = vec![
            (None, "1Girl".to_string(), 1.0),
            (None, "1girl".to_string(), 1.0),
        ];
        let out = normalize_tags(input, true);
        assert_eq!(out, vec![(None, "1girl".to_string(), 1.0)]);
    }

    #[test]
    fn normalize_tags_strips_blocked_namespaces() {
        let input = vec![(Some("adetailer".to_string()), "face".to_string(), 1.0)];
        let out = normalize_tags(input, true);
        assert!(out.is_empty());
    }

    #[test]
    fn normalize_tags_rounds_weight_to_4_decimals() {
        let input = vec![(None, "cat".to_string(), 1.23456789)];
        let out = normalize_tags(input, true);
        assert_eq!(out[0].2, 1.2346);
    }

    #[test]
    fn normalize_tags_drops_tags_without_word_chars() {
        let input = vec![(None, "***".to_string(), 1.0)];
        let out = normalize_tags(input, true);
        assert!(out.is_empty());
    }

    #[test]
    fn smart_split_by_comma_respects_nested_delimiters() {
        let input = "(a:1),(b:2),(c,(d:3))";
        let out = smart_split_by_comma(input);
        assert_eq!(
            out,
            vec![
                "(a:1)".to_string(),
                "(b:2)".to_string(),
                "(c,(d:3))".to_string()
            ]
        );
    }

    #[test]
    fn parse_candidate_applies_sd_paren_weight() {
        let parsed = parse_candidate("(cat)", false, "sd");
        assert_eq!(parsed, Some((None, "cat".to_string(), 1.1)));
    }

    #[test]
    fn parse_candidate_ignores_closed_lora_chunks() {
        assert_eq!(parse_candidate("<lora:test>", false, "sd"), None);
    }

    #[test]
    fn parse_prompt_to_tags_includes_choice_tokens() {
        let config = PromptParseConfig {
            prompt_syntax: "sd".to_string(),
            brace_choice: false,
            preserve_templates: false,
            lowercase_tags: true,
        };

        let parsed = parse_prompt_to_tags("cat, ||a|b||", &config);
        assert!(parsed
            .tags
            .iter()
            .any(|(_, tag, _)| tag == "cat" || tag == "a" || tag == "b"));
    }

    #[test]
    fn preprocess_prompt_text_removes_a1111_blocks_and_breaks() {
        let raw = "1girl, <lora:test>, BREAK, test {cat}".to_string();
        let out = preprocess_prompt_text(&raw);
        assert!(out.contains("cat"));
        assert!(!out.contains("<lora:test>"));
        assert!(!out.contains("BREAK"));
    }
}
