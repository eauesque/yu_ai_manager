use serde_json::Value;

use super::parsers::OcrRegion;

// extensions/builtin_ocr/core_impl/overlay_drawing.py:157, 218-262
pub const BOX_PADDING: u32 = 4;
pub const PANEL_PADDING: u32 = 12;
pub const PANEL_LINE_GAP: u32 = 6;
pub const PANEL_RADIUS: u32 = 4;
pub const PANEL_BACKGROUND: [u8; 4] = [24, 24, 32, 240];
pub const PANEL_FONT_MIN: u32 = 14;
pub const PANEL_FONT_MAX: u32 = 24;
pub const PANEL_SMALL_FONT_MIN: u32 = 10;
pub const PANEL_FONT_WIDTH_DIVISOR: u32 = 40;
pub const PANEL_WRAP_WIDTH_OFFSET: u32 = 16;
pub const PANEL_BADGE_WIDTH_PADDING: u32 = 12;
pub const PANEL_BADGE_OFFSET_X: u32 = 6;
pub const PANEL_BADGE_OFFSET_Y: u32 = 1;
pub const PANEL_TEXT_OFFSET_X: u32 = 8;
pub const PANEL_LABEL_TEXT_GAP: u32 = 2;
pub const PANEL_BADGE_ALPHA: u8 = 180;
pub const OUTLINE_OFFSETS: [(i32, i32); 4] = [(-1, -1), (-1, 1), (1, -1), (1, 1)];
pub const OUTLINE_COLOR: [u8; 4] = [0, 0, 0, 180];
pub const TEXT_COLOR: [u8; 4] = [255, 255, 255, 255];
pub const PANEL_TEXT_COLOR: [u8; 4] = [255, 255, 255, 240];
pub const DEFAULT_BG_OPACITY: u8 = 200;
pub const JPEG_QUALITY: u8 = 90;
pub const LABEL_COLORS: [(&str, [u8; 3]); 8] = [
    ("speech_bubble", [59, 130, 246]),
    ("thought_bubble", [99, 155, 255]),
    ("sfx", [245, 158, 11]),
    ("narration", [139, 92, 246]),
    ("caption", [168, 85, 247]),
    ("title", [236, 72, 153]),
    ("sign", [16, 185, 129]),
    ("other", [107, 114, 128]),
];

const JSONL_LABEL_MAP: [(&str, &str); 10] = [
    ("speech", "speech_bubble"),
    ("speech_bubble", "speech_bubble"),
    ("thought", "thought_bubble"),
    ("thought_bubble", "thought_bubble"),
    ("sfx", "sfx"),
    ("sound_effect", "sfx"),
    ("narration", "narration"),
    ("caption", "caption"),
    ("title", "title"),
    ("sign", "sign"),
];

/// Port of `overlay_drawing.py:92-99`.
#[allow(
    clippy::cast_possible_truncation,
    clippy::cast_sign_loss,
    reason = "the preceding clamp confines the truncated f64 to the u32 range 8..=72"
)]
pub fn auto_font_size(w: u32, h: u32, text: &str) -> u32 {
    let char_count = text.replace('\n', "").chars().count().max(1) as f64;
    let size_per_char = ((w as f64 * h as f64) / char_count).sqrt();
    (size_per_char * 0.8).trunc().clamp(8.0, 72.0) as u32
}

/// Port of `overlay.py:34-77` for old single-region JSONL results.
pub fn maybe_reparse_jsonl_regions(regions: Vec<OcrRegion>) -> Vec<OcrRegion> {
    let Some(region) = (regions.len() == 1).then(|| regions.first()).flatten() else {
        return regions;
    };
    if !region.text.trim().starts_with('{') {
        return regions;
    }
    let lines: Vec<_> = region
        .text
        .trim()
        .lines()
        .map(str::trim)
        .filter(|line| !line.is_empty())
        .collect();
    if lines.len() < 2 || !lines.iter().all(|line| line.starts_with('{')) {
        return regions;
    }
    let parsed: Result<Vec<Value>, _> = lines.into_iter().map(serde_json::from_str).collect();
    let Ok(parsed) = parsed else {
        return regions;
    };
    let reparsed: Vec<_> = parsed
        .iter()
        .enumerate()
        .filter_map(|(index, item)| {
            let text = item.get("text")?.as_str()?.trim();
            (!text.is_empty()).then(|| OcrRegion {
                region_id: index + 1,
                bbox: item
                    .get("bbox")
                    .and_then(Value::as_array)
                    .map_or_else(Vec::new, |bbox| {
                        bbox.iter().filter_map(Value::as_i64).collect()
                    }),
                text: text.to_owned(),
                confidence: item
                    .get("confidence")
                    .and_then(Value::as_f64)
                    .unwrap_or(0.0),
                direction: item
                    .get("direction")
                    .and_then(Value::as_str)
                    .unwrap_or("vertical")
                    .to_owned(),
                label: jsonl_label(item),
            })
        })
        .collect();
    if reparsed.is_empty() {
        regions
    } else {
        reparsed
    }
}

fn jsonl_label(item: &Value) -> String {
    let raw_type = item
        .get("type")
        .and_then(Value::as_str)
        .filter(|value| !value.is_empty())
        .or_else(|| item.get("label").and_then(Value::as_str))
        .unwrap_or("");
    JSONL_LABEL_MAP
        .iter()
        .find(|(raw, _)| *raw == raw_type.to_lowercase())
        .map_or("other", |(_, label)| *label)
        .to_owned()
}

/// Port of the policy in `overlay_drawing.py:114-139`; measurement arrives in step 4.
pub fn wrap_text(text: &str, max_width: f64, measure: &dyn Fn(&str) -> f64) -> Vec<String> {
    let mut result_lines = Vec::new();
    for paragraph in text.split('\n') {
        if paragraph.is_empty() {
            result_lines.push(String::new());
            continue;
        }
        let mut line = String::new();
        for ch in paragraph.chars() {
            let test = format!("{line}{ch}");
            if measure(&test) > max_width && !line.is_empty() {
                result_lines.push(line);
                line = ch.to_string();
            } else {
                line = test;
            }
        }
        if !line.is_empty() {
            result_lines.push(line);
        }
    }
    if result_lines.is_empty() {
        vec![String::new()]
    } else {
        result_lines
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn region(text: &str) -> OcrRegion {
        OcrRegion {
            region_id: 9,
            bbox: vec![1, 2, 3, 4],
            text: text.to_owned(),
            confidence: 0.9,
            direction: "horizontal".to_owned(),
            label: "other".to_owned(),
        }
    }

    #[test]
    fn auto_font_size_matches_python_golden_vectors() {
        let vectors = [
            (100, 50, "hello", 25),
            (10, 10, "a", 8),
            (4000, 4000, "x", 72),
            (200, 100, "", 72),
            (200, 100, "\n\n\n", 72),
            (200, 100, "line1\nline2", 35),
            (300, 200, "こんにちは世界", 72),
            (1, 1, "text", 8),
            (640, 480, "The quick brown fox", 72),
        ];
        for (w, h, text, expected) in vectors {
            assert_eq!(auto_font_size(w, h, text), expected, "{text:?}");
        }
        assert_eq!(auto_font_size(300, 200, &"a".repeat(500)), 8);
    }

    #[test]
    fn jsonl_reparse_preserves_guards_and_normalizes_labels() {
        let original = vec![region("plain text")];
        assert_eq!(maybe_reparse_jsonl_regions(original.clone()), original);
        let two_regions = vec![
            region("{\"text\":\"one\"}\n{\"text\":\"two\"}"),
            region("second"),
        ];
        assert_eq!(
            maybe_reparse_jsonl_regions(two_regions.clone()),
            two_regions
        );
        let one_line = vec![region("{\"text\":\"only\"}")];
        assert_eq!(maybe_reparse_jsonl_regions(one_line.clone()), one_line);
        let malformed = vec![region("{\"text\":\"a\"}\n{not json}")];
        assert_eq!(maybe_reparse_jsonl_regions(malformed.clone()), malformed);

        let reparsed = maybe_reparse_jsonl_regions(vec![region(
            "{\"text\":\"one\",\"type\":\"SPEECH\"}\n{\"text\":\"two\",\"type\":\"Sfx\",\"direction\":\"horizontal\"}",
        )]);
        assert_eq!(reparsed.len(), 2);
        let first = reparsed.first();
        let second = reparsed.last();
        assert_eq!(first.map(|item| item.region_id), Some(1));
        assert_eq!(second.map(|item| item.region_id), Some(2));
        assert_eq!(first.map(|item| item.text.as_str()), Some("one"));
        assert_eq!(second.map(|item| item.text.as_str()), Some("two"));
        assert_eq!(first.map(|item| item.label.as_str()), Some("speech_bubble"));
        assert_eq!(second.map(|item| item.label.as_str()), Some("sfx"));
        assert_eq!(first.map(|item| item.direction.as_str()), Some("vertical"));
        assert_eq!(
            second.map(|item| item.direction.as_str()),
            Some("horizontal")
        );
        assert!(reparsed.iter().all(|item| item.confidence == 0.0));

        let legacy_label = maybe_reparse_jsonl_regions(vec![region(
            "{\"text\":\"legacy\",\"label\":\"speech\"}\n{\"text\":\"other\",\"label\":\"sfx\"}",
        )]);
        assert_eq!(
            legacy_label.first().map(|item| item.label.as_str()),
            Some("speech_bubble")
        );
        assert_eq!(
            legacy_label.last().map(|item| item.label.as_str()),
            Some("sfx")
        );

        let skipped = maybe_reparse_jsonl_regions(vec![region(
            "{\"text\":\"first\"}\n{\"text\":\"\"}\n{\"text\":\"third\"}",
        )]);
        assert_eq!(
            skipped
                .iter()
                .map(|item| item.region_id)
                .collect::<Vec<_>>(),
            [1, 3]
        );
        let whitespace_skipped =
            maybe_reparse_jsonl_regions(vec![region("{\"text\":\"  \"}\n{\"text\":\"second\"}")]);
        assert_eq!(
            whitespace_skipped.first().map(|item| item.region_id),
            Some(2)
        );

        let other_labels = maybe_reparse_jsonl_regions(vec![region(
            "{\"text\":\"unknown\",\"type\":\"unknown\"}\n{\"text\":\"absent\"}\n{\"text\":\"empty\",\"type\":\"\"}",
        )]);
        assert!(other_labels.iter().all(|item| item.label == "other"));

        let all_empty = vec![region("{\"text\":\"\"}\n{\"text\":\"  \"}")];
        assert_eq!(maybe_reparse_jsonl_regions(all_empty.clone()), all_empty);
    }

    #[test]
    fn wrap_text_matches_character_policy() {
        let measure = |text: &str| text.chars().count() as f64;
        assert_eq!(wrap_text("abcde", 2.0, &measure), ["ab", "cd", "e"]);
        assert_eq!(wrap_text("a\n\nb", 2.0, &measure), ["a", "", "b"]);
        assert_eq!(wrap_text("ab", 0.5, &measure), ["a", "b"]);
        assert_eq!(wrap_text("e\u{301}", 1.0, &measure), ["e", "\u{301}"]);
        assert_eq!(wrap_text("", 2.0, &measure), [""]);
    }
}
