use std::collections::BTreeMap;

use regex::Regex;
use serde_json::Value;

/// Port of `translation.py:60-78`; an empty result signals that callers should keep the input.
pub fn clean_jsonl_text(text: &str) -> String {
    let lines: Vec<_> = text
        .trim()
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect();
    if lines.len() < 2 || !lines.iter().all(|line| line.starts_with('{')) {
        return String::new();
    }

    let mut texts = Vec::new();
    for line in lines {
        let Ok(value) = serde_json::from_str::<Value>(line) else {
            return String::new();
        };
        let Some(value) = value.get("text").and_then(Value::as_str) else {
            continue;
        };
        let value = value.trim();
        if !value.is_empty() {
            texts.push(value.to_owned());
        }
    }
    texts.join("\n")
}

/// Rebuilds Python's `re.split(r'(?=\\[\\d+\\])', raw.strip())` without lookahead.
pub fn split_numbered_response(raw: &str) -> Vec<String> {
    let raw = raw.trim();
    let Ok(marker) = Regex::new(r"\[\d+\]") else {
        return vec![raw.to_owned()];
    };

    let mut parts = Vec::new();
    let mut start = 0;
    for matched in marker.find_iter(raw) {
        parts.push(raw[start..matched.start()].to_owned());
        start = matched.start();
    }
    parts.push(raw[start..].to_owned());
    parts
}

/// Parses numbered LLM output. IDs above `u64::MAX` are skipped: Python accepts bignums,
/// while this port uses finite Rust map keys and must not panic on untrusted digit runs.
pub fn parse_numbered_response(raw: &str) -> BTreeMap<u64, String> {
    let Ok(part_pattern) = Regex::new(r"(?s)^\[(\d+)\]\s*(.*)\z") else {
        return BTreeMap::new();
    };

    let mut translated = BTreeMap::new();
    for part in split_numbered_response(raw) {
        let Some(captures) = part_pattern.captures(part.trim()) else {
            continue;
        };
        let (Some(id), Some(text)) = (captures.get(1), captures.get(2)) else {
            continue;
        };
        let (Ok(id), text) = (id.as_str().parse::<u64>(), text.as_str().trim()) else {
            continue;
        };
        if !text.is_empty() {
            translated.insert(id, text.to_owned());
        }
    }
    translated
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn clean_jsonl_text_matches_python_golden_vectors() {
        let vectors = [
            (
                "{\"text\":\"a\",\"type\":\"speech\"}\n{\"text\":\"b\",\"type\":\"sfx\"}",
                "a\nb",
            ),
            ("{\"text\":\"a\"}", ""),
            ("{\"text\":\"a\"}\nplain text", ""),
            ("{\"text\":\"a\"}\n{broken", ""),
            ("{\"text\":\"\"}\n{\"text\":\"  \"}", ""),
            ("{\"text\":\"\"}\n{\"text\":\"b\"}", "b"),
            ("  {\"text\":\" a \"}  \n  {\"text\":\"b\"}  ", "a\nb"),
            ("{\"text\":\"a\"}\n\n\n{\"text\":\"b\"}", "a\nb"),
            ("{\"type\":\"speech\"}\n{\"text\":\"b\"}", "b"),
            ("", ""),
            ("hello\nworld", ""),
            (
                "{\"text\":\"a\"}\n{\"text\":\"b\"}\n{\"text\":\"c\"}",
                "a\nb\nc",
            ),
        ];
        for (input, expected) in vectors {
            assert_eq!(clean_jsonl_text(input), expected, "{input:?}");
        }
    }

    #[test]
    fn numbered_response_matches_python_golden_vectors() {
        let vectors = [
            (
                "[1] hello\n[2] world",
                vec!["", "[1] hello\n", "[2] world"],
                vec![(1, "hello"), (2, "world")],
            ),
            (
                "Sure! Here you go:\n[1] hello",
                vec!["Sure! Here you go:\n", "[1] hello"],
                vec![(1, "hello")],
            ),
            (
                "[1] line one\nline two\n[2] second",
                vec!["", "[1] line one\nline two\n", "[2] second"],
                vec![(1, "line one\nline two"), (2, "second")],
            ),
            (
                "[1] first\n[1] second",
                vec!["", "[1] first\n", "[1] second"],
                vec![(1, "second")],
            ),
            (
                "[0] zero\n[1] one",
                vec!["", "[0] zero\n", "[1] one"],
                vec![(0, "zero"), (1, "one")],
            ),
            (
                "[12] twelve\n[345] many",
                vec!["", "[12] twelve\n", "[345] many"],
                vec![(12, "twelve"), (345, "many")],
            ),
            ("just some text", vec!["just some text"], vec![]),
            ("", vec![""], vec![]),
            ("   \n  ", vec![""], vec![]),
            (
                "[1]\n[2] two",
                vec!["", "[1]\n", "[2] two"],
                vec![(2, "two")],
            ),
            (
                "[1]    \n[2] two",
                vec!["", "[1]    \n", "[2] two"],
                vec![(2, "two")],
            ),
            (
                "text [1] hello",
                vec!["text ", "[1] hello"],
                vec![(1, "hello")],
            ),
            (
                "[1] こんにちは\n[2] さようなら",
                vec!["", "[1] こんにちは\n", "[2] さようなら"],
                vec![(1, "こんにちは"), (2, "さようなら")],
            ),
            ("[1][2] two", vec!["", "[1]", "[2] two"], vec![(2, "two")]),
            ("\n\n[1] hello", vec!["", "[1] hello"], vec![(1, "hello")]),
            (
                "[1] hello   \n[2] world",
                vec!["", "[1] hello   \n", "[2] world"],
                vec![(1, "hello"), (2, "world")],
            ),
            (
                "[abc] hello\n[1] one",
                vec!["[abc] hello\n", "[1] one"],
                vec![(1, "one")],
            ),
            (
                "[1] see [2] inside",
                vec!["", "[1] see ", "[2] inside"],
                vec![(1, "see"), (2, "inside")],
            ),
        ];
        for (input, expected_parts, expected_map) in vectors {
            assert_eq!(
                split_numbered_response(input),
                expected_parts,
                "split {input:?}"
            );
            assert_eq!(
                parse_numbered_response(input),
                expected_map
                    .into_iter()
                    .map(|(id, text)| (id, text.to_owned()))
                    .collect(),
                "map {input:?}"
            );
        }
        assert!(parse_numbered_response("[18446744073709551616] too large").is_empty());
    }
}
