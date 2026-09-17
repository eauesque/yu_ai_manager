//! tag_normalize.rs — tag string normalization for `/api/tools/normalize-tags`.
//!
//! Port of Python's `core/cleanup_core/cleanup_tag_normalize.py`. The extension
//! hook step (`normalize_via_hooks`) is intentionally omitted: it is a no-op
//! unless an extension registers `on_normalize_tags`, and the Rust extension
//! runtime does not yet support that hook.

use regex::Regex;
use std::sync::OnceLock;

static HAS_WORD_RE: OnceLock<Regex> = OnceLock::new();
static WEIGHT_PREFIX_RE: OnceLock<Regex> = OnceLock::new();
static TRAILING_WEIGHT_RE: OnceLock<Regex> = OnceLock::new();
static TRAILING_WEIGHT_PAREN_RE: OnceLock<Regex> = OnceLock::new();
static WHITESPACE_RE: OnceLock<Regex> = OnceLock::new();

fn has_word_re() -> &'static Regex {
    HAS_WORD_RE.get_or_init(|| Regex::new(r"\w").unwrap())
}

fn weight_prefix_re() -> &'static Regex {
    // Python: r"^[\d.]+::(.+?)(?:::)?$"
    WEIGHT_PREFIX_RE.get_or_init(|| Regex::new(r"^[\d.]+::(.+?)(?:::)?$").unwrap())
}

fn trailing_weight_re() -> &'static Regex {
    // Python: r":[\d.]+$"
    TRAILING_WEIGHT_RE.get_or_init(|| Regex::new(r":[\d.]+$").unwrap())
}

fn trailing_weight_paren_re() -> &'static Regex {
    // Python: r":[\d.]+\)"
    TRAILING_WEIGHT_PAREN_RE.get_or_init(|| Regex::new(r":[\d.]+\)").unwrap())
}

/// Port of Python's `re.sub(r",(?!\s)", ", ", s)`: insert a space after any
/// comma not already followed by whitespace. `regex` (unlike Python's `re`)
/// has no negative look-ahead, so this walks the string manually.
fn space_after_comma(s: &str) -> String {
    let mut out = String::with_capacity(s.len());
    let mut chars = s.chars().peekable();
    while let Some(c) = chars.next() {
        out.push(c);
        if c == ',' && !chars.peek().is_some_and(|next| next.is_whitespace()) {
            out.push(' ');
        }
    }
    out
}

fn whitespace_re() -> &'static Regex {
    // Python: r"\s+"
    WHITESPACE_RE.get_or_init(|| Regex::new(r"\s+").unwrap())
}

fn rstrip_punct(s: &str) -> String {
    s.trim_end_matches(['.', ',', ';', ':', '!', '?'])
        .to_string()
}

/// Port of Python's `normalize_tag_string`.
pub fn normalize_tag_string(tag: &str) -> String {
    let mut normalized = tag.trim().to_string();
    if normalized.is_empty() {
        return normalized;
    }

    if normalized.starts_with('<') && normalized.ends_with('>') {
        return normalized;
    }
    if normalized == "BREAK" || normalized == "AND" {
        return normalized;
    }

    if let Some(caps) = weight_prefix_re().captures(&normalized) {
        normalized = caps.get(1).unwrap().as_str().to_string();
    }

    loop {
        if normalized.len() < 2 {
            break;
        }
        let bytes = normalized.as_bytes();
        let first = bytes[0];
        let last = bytes[bytes.len() - 1];
        let matches = (first == b'(' && last == b')')
            || (first == b'[' && last == b']')
            || (first == b'{' && last == b'}');
        if matches {
            let inner = &normalized[1..normalized.len() - 1];
            normalized = inner.trim().to_string();
        } else {
            break;
        }
    }

    // trailing_weight_re is `$`-anchored so it can match at most once, but
    // Python's `re.sub` replaces ALL matches by default — trailing_weight_paren_re
    // is not anchored and can match multiple times, so use replace_all for both
    // to mirror that.
    normalized = trailing_weight_re()
        .replace_all(&normalized, "")
        .to_string();
    normalized = trailing_weight_paren_re()
        .replace_all(&normalized, "")
        .to_string();

    let open_count = normalized.matches('(').count();
    let close_count = normalized.matches(')').count();
    if open_count != close_count {
        if close_count > open_count {
            let excess = close_count - open_count;
            for _ in 0..excess {
                if let Some(idx) = normalized.rfind(')') {
                    normalized = format!("{}{}", &normalized[..idx], &normalized[idx + 1..]);
                }
            }
        }
        if open_count > close_count {
            let excess = open_count - close_count;
            for _ in 0..excess {
                if let Some(idx) = normalized.find('(') {
                    normalized = format!("{}{}", &normalized[..idx], &normalized[idx + 1..]);
                }
            }
        }
    }

    if normalized.contains('|') {
        let parts: Vec<String> = normalized
            .split('|')
            .map(|p| p.trim().to_string())
            .filter(|p| !p.is_empty())
            .collect();
        if parts.len() > 1 {
            return parts
                .iter()
                .map(|p| normalize_tag_string(p))
                .collect::<Vec<_>>()
                .join(", ");
        }
        if parts.len() == 1 {
            normalized = parts[0].clone();
        }
    }

    normalized = normalized
        .replace("\\(", "(")
        .replace("\\)", ")")
        .replace("\\[", "[")
        .replace("\\]", "]")
        .replace("\\{", "{")
        .replace("\\}", "}");
    normalized = space_after_comma(&normalized);
    normalized = rstrip_punct(&normalized);
    normalized = whitespace_re().replace_all(&normalized, " ").to_string();
    normalized = normalized.trim().to_string();
    // BUG-67: re-strip trailing punctuation exposed after whitespace cleanup
    normalized = rstrip_punct(&normalized);
    normalized.trim().to_string()
}

/// Port of Python's `split_normalized_tag`.
pub fn split_normalized_tag(tag: &str) -> Vec<String> {
    let normalized = normalize_tag_string(tag);
    if normalized.is_empty() {
        return vec![];
    }
    // BUG-67: skip tags with no word characters (symbol-only garbage)
    if !has_word_re().is_match(&normalized) {
        return vec![];
    }
    if normalized.contains(", ") {
        return normalized
            .split(", ")
            .map(str::trim)
            .filter(|t| !t.is_empty() && has_word_re().is_match(t))
            .map(str::to_string)
            .collect();
    }
    vec![normalized]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn passthrough_for_lora_and_control_tokens() {
        assert_eq!(normalize_tag_string("<lora:foo:0.8>"), "<lora:foo:0.8>");
        assert_eq!(normalize_tag_string("BREAK"), "BREAK");
        assert_eq!(normalize_tag_string("AND"), "AND");
    }

    #[test]
    fn strips_weight_prefix() {
        assert_eq!(normalize_tag_string("1.2::masterpiece"), "masterpiece");
        assert_eq!(normalize_tag_string("1.2::masterpiece::"), "masterpiece");
    }

    #[test]
    fn strips_surrounding_brackets() {
        assert_eq!(normalize_tag_string("(masterpiece)"), "masterpiece");
        assert_eq!(normalize_tag_string("[[masterpiece]]"), "masterpiece");
        assert_eq!(normalize_tag_string("{masterpiece}"), "masterpiece");
    }

    #[test]
    fn strips_trailing_weight() {
        assert_eq!(normalize_tag_string("masterpiece:1.2"), "masterpiece");
        assert_eq!(normalize_tag_string("(masterpiece:1.2)"), "masterpiece");
    }

    #[test]
    fn repairs_unbalanced_parens() {
        assert_eq!(normalize_tag_string("masterpiece)"), "masterpiece");
        assert_eq!(normalize_tag_string("(masterpiece"), "masterpiece");
    }

    #[test]
    fn splits_on_pipe_recursively() {
        assert_eq!(normalize_tag_string("(a|b|c)"), "a, b, c");
    }

    #[test]
    fn unescapes_backslash_brackets() {
        assert_eq!(
            normalize_tag_string(r"masterpiece\(1girl\)"),
            "masterpiece(1girl)"
        );
    }

    #[test]
    fn normalizes_comma_spacing_and_whitespace() {
        assert_eq!(normalize_tag_string("a,b   c"), "a, b c");
    }

    #[test]
    fn strips_trailing_punctuation() {
        assert_eq!(normalize_tag_string("masterpiece."), "masterpiece");
    }

    #[test]
    fn split_normalized_tag_splits_comma_joined_result() {
        assert_eq!(
            split_normalized_tag("(a|b|c)"),
            vec!["a".to_string(), "b".to_string(), "c".to_string()]
        );
    }

    #[test]
    fn split_normalized_tag_rejects_symbol_only_garbage() {
        assert!(split_normalized_tag(":::").is_empty());
        assert!(split_normalized_tag("").is_empty());
    }

    #[test]
    fn trailing_weight_paren_removes_all_occurrences_not_just_first() {
        // Non-surrounding parens: the balanced-bracket-strip loop doesn't touch
        // this (first char isn't a bracket), so trailing_weight_paren_re must
        // remove `:1.2)` -> paren-balance repair then removes the leftover "(".
        assert_eq!(normalize_tag_string("foo(bar:1.2)"), "foobar");
    }

    #[test]
    fn split_normalized_tag_single_tag() {
        assert_eq!(
            split_normalized_tag("masterpiece"),
            vec!["masterpiece".to_string()]
        );
    }
}
