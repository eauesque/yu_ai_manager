pub mod a1111;
pub mod comfyui;
pub mod detail;
pub mod exif_reader;
pub mod models;
pub mod novelai_v3;
pub mod novelai_v4;
pub mod parse;
pub mod png;
pub mod tensor_art;

pub use detail::resolve_detail_fields;
pub use exif_reader::{read_exif_tags, read_exif_tags_from_bytes};
pub use models::{MetaResult, PngTextChunks};
pub use parse::parse_metadata;
pub use png::{parse_png_text_chunks, read_png_text_chunks};

/// Returns whether a DB source belongs to the NovelAI family.
///
/// Source vocabularies are families because open generators such as `a1111_<ext>`
/// prevent a closed global enumeration. Internal parser identifiers are accepted
/// only to absorb rows polluted before E1, not to permit new writes of those values.
pub fn is_nai_source(meta_source: &str) -> bool {
    matches!(
        meta_source,
        "novelai_v4_png"
            | "novelai_v4_webp"
            | "novelai_v4"
            | "novelai_png"
            | "novelai_webp"
            | "nai_webp"
            | "nai_v4"
            | "nai_v3"
    )
}

/// Returns whether a DB source belongs to the ComfyUI family.
///
/// Source vocabularies are families because open generators such as `a1111_<ext>`
/// prevent a closed global enumeration. Internal parser identifiers are accepted
/// only to absorb rows polluted before E1, not to permit new writes of those values.
pub fn is_comfy_source(meta_source: &str) -> bool {
    matches!(
        meta_source,
        "comfy_png" | "comfy_webp" | "comfy_webm" | "comfy_flac" | "comfyui" | "comfy"
    )
}

/// Returns whether a DB source belongs to the A1111 family.
///
/// This family uses a prefix because open generators produce `a1111_<ext>` values.
/// The internal parser identifier is accepted only to absorb rows polluted before
/// E1, not to permit new writes of that value.
pub fn is_a1111_source(meta_source: &str) -> bool {
    meta_source == "a1111" || meta_source.starts_with("a1111_")
}

/// Converts an internal parser `format` into the canonical `files.meta_source` vocabulary.
///
/// `meta-extract` formats (`nai_v3`, `nai_v4`, `a1111`, `tensor_art`, `comfy`,
/// `unknown`) are parser identifiers. Most must not reach the database unchanged;
/// canonical DB sources are
/// suffix-bearing families such as `novelai_v4_png`, `comfy_webp`, and
/// `a1111_jpg`. These families are open sets (notably `a1111_<ext>`), so consumers
/// must use family/prefix predicates rather than exhaustive lists.
///
/// `ext` is normally a lowercase extension without a leading dot, but this function
/// accepts leading dots and ASCII case variants. `unknown` and unrecognized formats
/// are returned unchanged. Missing or unsupported extensions follow the Python
/// extractors' format-specific defaults.
pub fn db_meta_source(format: &str, ext: Option<&str>) -> String {
    let ext = ext.map(|value| value.trim_start_matches('.').to_ascii_lowercase());
    match format {
        "nai_v4" => match ext.as_deref() {
            Some("png") => "novelai_v4_png".into(),
            Some("webp") => "novelai_v4_webp".into(),
            _ => "novelai_v4".into(),
        },
        "nai_v3" => match ext.as_deref() {
            Some("webp") => "novelai_webp".into(),
            _ => "novelai_png".into(),
        },
        "comfy" => match ext.as_deref() {
            Some("webm") => "comfy_webm".into(),
            Some("webp") => "comfy_webp".into(),
            Some("flac") => "comfy_flac".into(),
            _ => "comfy_png".into(),
        },
        "a1111" => match ext.as_deref() {
            Some("jpg" | "jpeg") => "a1111_jpg".into(),
            Some("webp") => "a1111_webp".into(),
            Some(extension) if !extension.is_empty() => format!("a1111_{extension}"),
            _ => "a1111_png".into(),
        },
        other => other.into(),
    }
}

#[cfg(test)]
mod db_meta_source_tests {
    use super::db_meta_source;

    #[test]
    fn maps_parser_formats_to_db_sources() {
        let cases = [
            ("nai_v4", Some("png"), "novelai_v4_png"),
            ("nai_v4", Some(".WEBP"), "novelai_v4_webp"),
            ("nai_v4", Some("avif"), "novelai_v4"),
            ("nai_v4", None, "novelai_v4"),
            ("nai_v3", Some("png"), "novelai_png"),
            ("nai_v3", Some("WEBP"), "novelai_webp"),
            ("nai_v3", None, "novelai_png"),
            ("comfy", Some("png"), "comfy_png"),
            ("comfy", Some("webp"), "comfy_webp"),
            ("comfy", Some("webm"), "comfy_webm"),
            ("comfy", Some(".FLAC"), "comfy_flac"),
            ("comfy", None, "comfy_png"),
            ("a1111", Some("png"), "a1111_png"),
            ("a1111", Some("jpg"), "a1111_jpg"),
            ("a1111", Some("jpeg"), "a1111_jpg"),
            ("a1111", Some("webp"), "a1111_webp"),
            ("a1111", Some("jxl"), "a1111_jxl"),
            ("a1111", None, "a1111_png"),
            ("tensor_art", Some("png"), "tensor_art"),
            ("unknown", Some("png"), "unknown"),
            ("future_parser", Some("png"), "future_parser"),
        ];

        for (format, ext, expected) in cases {
            assert_eq!(db_meta_source(format, ext), expected);
        }
    }
}

#[cfg(test)]
mod meta_source_family_tests {
    use super::{is_a1111_source, is_comfy_source, is_nai_source};

    #[test]
    fn recognizes_only_nai_sources() {
        for source in [
            "novelai_v4_png",
            "novelai_v4_webp",
            "novelai_v4",
            "novelai_png",
            "novelai_webp",
            "nai_webp",
            "nai_v4",
            "nai_v3",
        ] {
            assert!(is_nai_source(source), "{source}");
        }
        for source in ["comfy_png", "a1111_png", "nai", "unknown"] {
            assert!(!is_nai_source(source), "{source}");
        }
    }

    #[test]
    fn recognizes_only_comfy_sources() {
        for source in [
            "comfy_png",
            "comfy_webp",
            "comfy_webm",
            "comfy_flac",
            "comfyui",
            "comfy",
        ] {
            assert!(is_comfy_source(source), "{source}");
        }
        for source in ["novelai_v4_png", "a1111_png", "comfy_ui", "unknown"] {
            assert!(!is_comfy_source(source), "{source}");
        }
    }

    #[test]
    fn recognizes_open_a1111_family_only() {
        for source in ["a1111", "a1111_png", "a1111_jxl"] {
            assert!(is_a1111_source(source), "{source}");
        }
        for source in ["novelai_v4_png", "comfy_png", "a111", "unknown"] {
            assert!(!is_a1111_source(source), "{source}");
        }
    }
}
