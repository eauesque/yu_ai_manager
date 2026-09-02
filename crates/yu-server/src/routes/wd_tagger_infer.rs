/// Python `model_download_legacy.safe_name` と等価。
/// [^\w\-.] にマッチする文字を全て "_" に置換する。
pub(crate) fn sanitize_model_id(repo: &str) -> String {
    repo.chars()
        .map(|c| {
            if c.is_alphanumeric() || c == '_' || c == '-' || c == '.' {
                c
            } else {
                '_'
            }
        })
        .collect()
}

/// Python `tag_postprocess.NSFW_TAG_SET` と等価の固定ブロックリスト。
pub(crate) const NSFW_TAG_SET: &[&str] = &[
    "sex",
    "nude",
    "naked",
    "nipples",
    "nipple",
    "pussy",
    "penis",
    "vaginal",
    "anal",
    "cum",
    "cum_on_body",
    "cum_in_pussy",
    "cum_on_face",
    "cum_in_mouth",
    "fellatio",
    "oral",
    "paizuri",
    "handjob",
    "masturbation",
    "spread_legs",
    "spread_pussy",
    "ass_visible_through_thighs",
    "anus",
    "pubic_hair",
    "completely_nude",
    "topless",
    "bottomless",
    "censored",
    "uncensored",
    "mosaic_censoring",
    "bar_censor",
];

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn sanitize_model_id_replaces_slash_with_underscore() {
        assert_eq!(
            sanitize_model_id("SmilingWolf/wd-swinv2-tagger-v3"),
            "SmilingWolf_wd-swinv2-tagger-v3"
        );
    }

    #[test]
    fn sanitize_model_id_preserves_dots_and_dashes() {
        assert_eq!(sanitize_model_id("foo.bar-baz_1"), "foo.bar-baz_1");
    }

    #[test]
    fn nsfw_tag_set_contains_known_entries() {
        assert!(NSFW_TAG_SET.contains(&"nude"));
        assert!(NSFW_TAG_SET.contains(&"anal"));
        assert_eq!(NSFW_TAG_SET.len(), 31);
    }
}
