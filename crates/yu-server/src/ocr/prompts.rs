use serde_json::Value;

const PROMPTS: &[(&str, &str)] =
    &[
        (
            "ocr",
            concat!(
                "Read all text in this image. Output the text exactly as written.\n",
                "Reply with JSON only:\n",
                "{\"full_text\": \"all text here\", \"language\": \"detected language code\"}"
            ),
        ),
        (
            "ocr_document",
            concat!(
                "Read all text in this document image in reading order.\n",
                "Separate headings from body text.\n",
                "Reply with JSON only:\n",
                "{\"headings\": [\"...\"], \"body_text\": \"...\", \"full_text\": \"all text\"}"
            ),
        ),
        (
            "ocr_manga",
            concat!("Read ALL text in this manga/comic page. ",
            "Include every speech bubble, sound effect (SFX), narration box, sign, and title.\n",
            "For Japanese manga, read right-to-left, top-to-bottom.\n\n",
            "You MUST reply with a JSON array. Each element has \"text\" and \"type\".\n",
            "Valid types: speech, sfx, narration, sign, title, other\n\n",
            "Example output for a page with 3 text elements:\n",
            "[\n",
            "  {\"text\": \"おはよう\", \"type\": \"speech\"},\n",
            "  {\"text\": \"ドン！！\", \"type\": \"sfx\"},\n",
            "  {\"text\": \"次の日——\", \"type\": \"narration\"}\n",
            "]\n\n",
            "Now read this image and output the JSON array:"),
        ),
    ];

pub const MANGA_RETRY_PROMPT: &str = concat!(
    "List all text in this manga page as a JSON array.\n",
    "Format: [{\"text\": \"...\", \"type\": \"speech\"}]\n",
    "Types: speech, sfx, narration, sign, title, other\n",
    "Output ONLY the JSON array, nothing else."
);

const MANGA_JSON_SCHEMA: &str = r#"{
  "type": "object",
  "properties": {
    "items": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "text": {"type": "string"},
          "type": {
            "type": "string",
            "enum": ["speech", "sfx", "narration", "sign", "title", "other"]
          }
        },
        "required": ["text", "type"]
      }
    }
  },
  "required": ["items"]
}"#;

const OCR_JSON_SCHEMA: &str = r#"{
  "type": "object",
  "properties": {
    "full_text": {"type": "string"},
    "language": {"type": "string"}
  },
  "required": ["full_text"]
}"#;

const LANG_HINT: &[(&str, &str)] = &[
    (
        "ja",
        "The text is primarily in Japanese. Output text in Japanese.",
    ),
    (
        "en",
        "The text is primarily in English. Output text in English.",
    ),
    (
        "zh",
        "The text is primarily in Chinese. Output text in Chinese.",
    ),
    (
        "ko",
        "The text is primarily in Korean. Output text in Korean.",
    ),
];

const LABEL_NORMALIZE: &[(&str, &str)] = &[
    ("speech", "speech_bubble"),
    ("speech_bubble", "speech_bubble"),
    ("speechbubble", "speech_bubble"),
    ("dialogue", "speech_bubble"),
    ("dialog", "speech_bubble"),
    ("bubble", "speech_bubble"),
    ("セリフ", "speech_bubble"),
    ("台詞", "speech_bubble"),
    ("吹き出し", "speech_bubble"),
    ("thought", "thought_bubble"),
    ("thought_bubble", "thought_bubble"),
    ("thinking", "thought_bubble"),
    ("sfx", "sfx"),
    ("sound", "sfx"),
    ("sound_effect", "sfx"),
    ("sound effect", "sfx"),
    ("onomatopoeia", "sfx"),
    ("効果音", "sfx"),
    ("se", "sfx"),
    ("narration", "narration"),
    ("narrator", "narration"),
    ("caption", "caption"),
    ("ナレーション", "narration"),
    ("キャプション", "caption"),
    ("sign", "sign"),
    ("label", "sign"),
    ("看板", "sign"),
    ("表示", "sign"),
    ("title", "title"),
    ("heading", "title"),
    ("chapter", "title"),
    ("タイトル", "title"),
    ("other", "other"),
    ("text", "other"),
    ("その他", "other"),
];

pub fn prompt_for(task: &str) -> &'static str {
    PROMPTS
        .iter()
        .find(|(name, _)| *name == task)
        .map_or(PROMPTS[0].1, |(_, prompt)| *prompt)
}

pub fn schema_for(task: &str) -> Option<Value> {
    let schema = match task {
        "ocr_manga" => MANGA_JSON_SCHEMA,
        "ocr" | "ocr_document" => OCR_JSON_SCHEMA,
        _ => return None,
    };
    Some(serde_json::from_str(schema).expect("embedded JSON schema is valid"))
}

pub fn lang_hint(language: &str) -> Option<&'static str> {
    LANG_HINT
        .iter()
        .find(|(name, _)| *name == language)
        .map(|(_, hint)| *hint)
}

pub fn normalize_label(raw: &str) -> &'static str {
    if raw.is_empty() {
        return "speech_bubble";
    }
    let normalized = raw.trim().to_lowercase();
    LABEL_NORMALIZE
        .iter()
        .find(|(name, _)| *name == normalized)
        .map_or("speech_bubble", |(_, label)| *label)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn prompt_falls_back_to_ocr_for_unknown_task() {
        assert_eq!(prompt_for("no_such_task"), prompt_for("ocr"));
    }

    #[test]
    fn ocr_schema_has_no_regions_key() {
        // Python's OCR_JSON_SCHEMA is {full_text, language} only. With ollama
        // enforcing it, task="ocr" legitimately returns zero regions — callers
        // must not treat that as a broken response.
        let schema = schema_for("ocr").expect("ocr has a schema");
        let props = schema["properties"].as_object().expect("object schema");
        assert!(props.contains_key("full_text"));
        assert!(props.contains_key("language"));
        assert!(!props.contains_key("regions"), "regions must be absent");
    }

    #[test]
    fn lang_hint_is_appended_only_for_the_four_known_languages() {
        // Python: `if language != "auto" and language in LANG_HINT`. A missing
        // guard silently sends "auto" as a language instruction to the VLM.
        assert!(lang_hint("auto").is_none());
        assert!(lang_hint("fr").is_none(), "unknown languages get no hint");
        for l in ["ja", "en", "zh", "ko"] {
            assert!(lang_hint(l).is_some(), "{l} must have a hint");
        }
    }

    #[test]
    fn manga_retry_prompt_differs_from_the_manga_prompt() {
        // The retry exists to ask differently. If the two are equal the retry is a
        // pure cost with no chance of improving anything.
        assert_ne!(MANGA_RETRY_PROMPT, prompt_for("ocr_manga"));
    }

    #[test]
    fn manga_schema_requires_items() {
        // The alias table in parsers.rs (regions -> texts -> items -> …) is not
        // dead code: manga's schema asks the model for `items`.
        let schema = schema_for("ocr_manga").expect("manga has a schema");
        let props = schema["properties"].as_object().expect("object schema");
        assert!(props.contains_key("items"));
    }
}
