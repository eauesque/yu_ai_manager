use caseless::Caseless;
use unicode_normalization::UnicodeNormalization;

/// Python `tag_postprocess.normalize_tags` と等価。`wd_tag_dict.tag_name` 用。
pub(crate) fn normalize_tag_name(raw: &str) -> String {
    let lowered = raw.trim().to_lowercase().replace(' ', "_");
    let filtered: String = lowered
        .chars()
        .filter(|c| {
            !matches!(
                c,
                '[' | ']' | '(' | ')' | '{' | '}' | '"' | '\'' | '/' | '\\'
            )
        })
        .collect();
    if (1..=100).contains(&filtered.chars().count()) {
        filtered
    } else {
        String::new()
    }
}

/// Python `tag_normalize.normalize_tag` と等価。`wd_tag_dict.tag_name_normalized` 用。
/// 入力は生タグ名ではなく `normalize_tag_name` の出力(連鎖適用)。
pub(crate) fn normalize_tag_name_canonical(tag_name: &str) -> String {
    let nfkc: String = tag_name.nfkc().collect();
    let underscored = nfkc.replace('_', " ");
    let folded: String = underscored.chars().default_case_fold().collect();
    let collapsed = folded.split_whitespace().collect::<Vec<_>>().join(" ");
    collapsed.trim().to_string()
}

/// confidence(f32相当、f64で受け取る)をDB格納用milli値へ変換。
/// 決定論契約のみ(同一入力に対し常に同一出力)。Python版との数値比較はしない。
pub(crate) fn confidence_to_milli(conf: f64) -> u16 {
    let scaled = (conf * 1000.0).round_ties_even();
    crate::num::sat_u16(scaled.clamp(0.0, 1000.0))
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_tag_name_lowercases_and_underscores() {
        assert_eq!(normalize_tag_name("Blue Eyes"), "blue_eyes");
    }

    #[test]
    fn normalize_tag_name_strips_invalid_chars() {
        assert_eq!(normalize_tag_name("foo[bar]"), "foobar");
    }

    #[test]
    fn normalize_tag_name_rejects_out_of_range_length() {
        assert_eq!(normalize_tag_name(""), "");
        let too_long = "a".repeat(101);
        assert_eq!(normalize_tag_name(&too_long), "");
    }

    #[test]
    fn normalize_tag_name_canonical_applies_nfkc_before_casefold() {
        // NFKC正規化のテスト: 全角英数字が半角化される
        assert_eq!(normalize_tag_name_canonical("blue_eyes"), "blue eyes");
    }

    #[test]
    fn normalize_tag_name_canonical_folds_sharp_s() {
        // 完全Unicode casefold: ß -> ss (to_lowercase()では起きない既知差異)
        assert_eq!(normalize_tag_name_canonical("stra\u{df}e"), "strasse");
    }

    #[test]
    fn normalize_tag_name_canonical_collapses_whitespace() {
        assert_eq!(normalize_tag_name_canonical("foo  bar"), "foo bar");
    }

    #[test]
    fn confidence_to_milli_rounds_ties_to_even() {
        // 0.1235 * 1000 = 123.5 -> round_ties_even -> 124 (偶数側)
        assert_eq!(confidence_to_milli(0.1235), 124);
        // 0.1245 * 1000 = 124.5 -> round_ties_even -> 124 (偶数側)
        assert_eq!(confidence_to_milli(0.1245), 124);
    }

    #[test]
    fn confidence_to_milli_clamps_to_valid_range() {
        assert_eq!(confidence_to_milli(-0.5), 0);
        assert_eq!(confidence_to_milli(1.5), 1000);
    }

    #[test]
    fn confidence_to_milli_is_deterministic() {
        let a = confidence_to_milli(0.876543);
        let b = confidence_to_milli(0.876543);
        assert_eq!(a, b);
    }
}
