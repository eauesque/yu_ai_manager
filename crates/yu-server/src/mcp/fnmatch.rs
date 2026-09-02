//! Minimal fnmatch-compatible glob matcher, semantically equivalent to
//! Python's `fnmatch.fnmatch` for the subset used by Scope Fence deny
//! patterns: `*`, `?`, `[seq]`, `[!seq]`. Case-sensitive (tool names are
//! always lowercase ASCII on this server). Whole-string anchored match
//! (never a substring match).
//!
//! No external crate is used here: the grammar is small enough that a
//! self-contained implementation avoids adding a new dependency for what a
//! few dozen lines cover, and keeps us clear of any GPL/LGPL/AGPL licensing
//! concerns for a security-boundary component (COVENANT Liber III.iv).

#[derive(Debug, Clone)]
enum ClassItem {
    Char(char),
    Range(char, char),
}

#[derive(Debug, Clone)]
enum Token {
    Star,
    Any,
    Lit(char),
    Class { negate: bool, items: Vec<ClassItem> },
}

/// Parses a glob pattern into a token list. An unclosed `[` (no matching
/// `]` found) is treated as a literal `[`, matching Python's `fnmatch`
/// behavior.
fn parse_pattern(pattern: &str) -> Vec<Token> {
    let chars: Vec<char> = pattern.chars().collect();
    let mut tokens = Vec::new();
    let mut i = 0;
    while i < chars.len() {
        match chars[i] {
            '*' => {
                tokens.push(Token::Star);
                i += 1;
            }
            '?' => {
                tokens.push(Token::Any);
                i += 1;
            }
            '[' => {
                if let Some((token, next_i)) = parse_class(&chars, i) {
                    tokens.push(token);
                    i = next_i;
                } else {
                    tokens.push(Token::Lit('['));
                    i += 1;
                }
            }
            c => {
                tokens.push(Token::Lit(c));
                i += 1;
            }
        }
    }
    tokens
}

/// Attempts to parse a `[seq]`/`[!seq]` class starting at `chars[start]`
/// (which must be `[`). Returns the parsed token and the index just past
/// the closing `]`, or `None` if there is no closing `]` in the pattern.
fn parse_class(chars: &[char], start: usize) -> Option<(Token, usize)> {
    let mut i = start + 1;
    let mut negate = false;
    if i < chars.len() && chars[i] == '!' {
        negate = true;
        i += 1;
    }
    let items_start = i;
    // A ']' immediately after '[' or '[!' is a literal member, not the
    // closing bracket (standard glob convention).
    if i < chars.len() && chars[i] == ']' {
        i += 1;
    }
    while i < chars.len() && chars[i] != ']' {
        i += 1;
    }
    if i >= chars.len() {
        return None;
    }
    let body = &chars[items_start..i];
    let mut items = Vec::new();
    let mut j = 0;
    while j < body.len() {
        if j + 2 < body.len() && body[j + 1] == '-' {
            items.push(ClassItem::Range(body[j], body[j + 2]));
            j += 3;
        } else {
            items.push(ClassItem::Char(body[j]));
            j += 1;
        }
    }
    Some((Token::Class { negate, items }, i + 1))
}

fn class_matches(negate: bool, items: &[ClassItem], c: char) -> bool {
    let hit = items.iter().any(|item| match item {
        ClassItem::Char(x) => *x == c,
        ClassItem::Range(lo, hi) => *lo <= c && c <= *hi,
    });
    hit != negate
}

fn token_matches(token: &Token, c: char) -> bool {
    match token {
        Token::Any => true,
        Token::Lit(x) => *x == c,
        Token::Class { negate, items } => class_matches(*negate, items, c),
        // The matcher loop guards every call with `!matches!(tokens[j],
        // Token::Star)` in the same expression, so this is dead. Answering
        // `false` rather than panicking keeps the MCP allowlist fail-closed if
        // that guard is ever edited away: a pattern stops matching, it does not
        // take the request down.
        Token::Star => false,
    }
}

/// Whole-string match, semantically equivalent to Python's
/// `fnmatch.fnmatch(name, pattern)` for the `*`/`?`/`[seq]`/`[!seq]`
/// grammar. Case-sensitive.
pub fn fnmatch(name: &str, pattern: &str) -> bool {
    let text: Vec<char> = name.chars().collect();
    let tokens = parse_pattern(pattern);

    let (mut i, mut j) = (0usize, 0usize);
    let mut star_idx: Option<usize> = None;
    let mut match_idx = 0usize;

    while i < text.len() {
        if j < tokens.len()
            && !matches!(tokens[j], Token::Star)
            && token_matches(&tokens[j], text[i])
        {
            i += 1;
            j += 1;
        } else if j < tokens.len() && matches!(tokens[j], Token::Star) {
            star_idx = Some(j);
            match_idx = i;
            j += 1;
        } else if let Some(si) = star_idx {
            j = si + 1;
            match_idx += 1;
            i = match_idx;
        } else {
            return false;
        }
    }

    while j < tokens.len() && matches!(tokens[j], Token::Star) {
        j += 1;
    }
    j == tokens.len()
}

#[cfg(test)]
mod tests {
    use super::fnmatch;

    /// Golden corpus generated from Python's `fnmatch.fnmatch` (see
    /// `tmp/scratchpad` generation script referenced in the implementation
    /// PR). Each entry is `(pattern, string, expected)`. This is the
    /// differential test required by the approved spec (AC-14) to keep the
    /// self-implemented matcher semantically equivalent to the reference.
    const GOLDEN: &[(&str, &str, bool)] = &[
        ("get_server_info", "get_server_info", true),
        ("get_server_info", "get_server_info2", false),
        ("get_server_info", "", false),
        ("", "", true),
        ("", "x", false),
        ("set_*", "set_tags", true),
        ("set_*", "set_", true),
        ("set_*", "sett_tags", false),
        ("delete_*", "delete_file", true),
        ("delete_*", "Delete_file", false),
        ("wd_tagger_tag*", "wd_tagger_tag", true),
        ("wd_tagger_tag*", "wd_tagger_tags_batch", true),
        ("wd_tagger_delete*", "wd_tagger_delete_all", true),
        ("agent_kill", "agent_kill", true),
        ("agent_kill", "agent_killed", false),
        ("a*b*c", "aXbYc", true),
        ("a*b*c", "abc", true),
        ("a*b*c", "ac", false),
        ("*", "", true),
        ("*", "anything", true),
        ("**", "anything", true),
        ("a?c", "abc", true),
        ("a?c", "ac", false),
        ("a?c", "abbc", false),
        ("???", "abc", true),
        ("???", "ab", false),
        ("tool_[abc]", "tool_a", true),
        ("tool_[abc]", "tool_b", true),
        ("tool_[abc]", "tool_d", false),
        ("tool_[a-c]", "tool_b", true),
        ("tool_[a-c]", "tool_d", false),
        ("tool_[0-9]*", "tool_5_reset", true),
        ("tool_[0-9]*", "tool_x_reset", false),
        ("tool_[!abc]", "tool_d", true),
        ("tool_[!abc]", "tool_a", false),
        ("tool_[!a-c]", "tool_z", true),
        ("tool_[!a-c]", "tool_b", false),
        ("*_[0-9]", "reset_9", true),
        ("*_[0-9]", "reset_x", false),
        ("tool_[abc", "tool_[abc", true),
        ("tool_[abc", "tool_a", false),
        ("[unterminated*", "[unterminated_extra", true),
        ("Set_*", "set_tags", false),
        ("Set_*", "Set_tags", true),
    ];

    #[test]
    fn matches_python_fnmatch_golden_corpus() {
        for (pattern, name, expected) in GOLDEN {
            assert_eq!(
                fnmatch(name, pattern),
                *expected,
                "fnmatch({name:?}, {pattern:?}) should be {expected}"
            );
        }
    }

    #[test]
    fn all_preset_deny_patterns_are_supported_grammar() {
        // Sanity check that the grammar subset covers every pattern shape
        // actually used by the built-in presets (all are '*'-suffixed or
        // exact matches; no '[seq]' appears in the shipped presets, but the
        // matcher must still support it for custom scope patterns).
        let read_only_deny = [
            "set_*",
            "wd_tagger_tag*",
            "agent_kill",
            "agent_budget_reset",
        ];
        for pat in read_only_deny {
            // exercised only for parse-ability; actual pass/fail is covered above
            let _ = fnmatch("some_tool_name", pat);
        }
    }
}
