use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use fancy_regex::Regex;
use meta_extract::{
    db_meta_source, parse_metadata, read_exif_tags, read_png_text_chunks, PngTextChunks,
};
use serde_json::Value;

#[derive(Debug, Clone, Default, PartialEq, Eq)]
pub struct ExtractedMeta {
    pub meta_source: String,
    pub format: String,
    pub raw_prompt: Option<String>,
    pub raw_negative: Option<String>,
    pub raw_meta_json: Option<String>,
    pub tag_source: Option<String>,
}

impl ExtractedMeta {
    fn unknown() -> Self {
        Self {
            meta_source: "unknown".to_string(),
            format: "unknown".to_string(),
            raw_prompt: None,
            raw_negative: None,
            raw_meta_json: None,
            tag_source: None,
        }
    }
}

fn read_sidecar_txt(path: &Path) -> Option<String> {
    for sidecar in sidecar_candidates(path) {
        if !sidecar.exists() {
            continue;
        }
        let text = std::fs::read_to_string(sidecar).ok()?;
        let trimmed = text.trim().to_string();
        if !trimmed.is_empty() {
            return Some(trimmed);
        }
    }
    None
}

fn sidecar_candidates(path: &Path) -> [PathBuf; 2] {
    let mut appended = OsString::from(path.as_os_str());
    appended.push(".txt");
    [PathBuf::from(appended), path.with_extension("txt")]
}

fn extract_chunks_for_file(path: &Path) -> PngTextChunks {
    match path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(str::to_ascii_lowercase)
        .as_deref()
    {
        Some("png") => read_png_text_chunks(path),
        _ => PngTextChunks::default(),
    }
}

fn apply_extension_parsers(path: &Path, chunks: &PngTextChunks) -> Option<ExtractedMeta> {
    if let Some(extracted) = parsed_chunks_to_extracted(path, chunks) {
        return Some(extracted);
    }

    let extension = path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(str::to_ascii_lowercase);
    let supports_exif = matches!(
        extension.as_deref(),
        Some("jpg" | "jpeg" | "jxl" | "avif" | "heif" | "heic" | "webp")
    );
    if !supports_exif {
        return None;
    }

    let exif_tags = read_exif_tags(path);
    if exif_tags.is_empty() {
        return None;
    }

    let mut exif_chunks = PngTextChunks::default();
    for (key, value) in exif_tags {
        exif_chunks.entries.insert(key.clone(), value.clone());
        if key == "UserComment"
            || key == "Exif.Image.UserComment"
            || key == "Exif.Photo.UserComment"
        {
            let stripped = value.strip_prefix("YU_META:").unwrap_or(&value).to_string();
            exif_chunks
                .entries
                .entry("Comment".to_string())
                .or_insert_with(|| stripped.clone());
            exif_chunks
                .entries
                .entry("exif:UserComment".to_string())
                .or_insert_with(|| stripped.clone());
            if let Ok(Value::Object(map)) = serde_json::from_str::<Value>(&stripped) {
                for (json_key, json_value) in map {
                    if let Value::String(json_text) = json_value {
                        exif_chunks.entries.entry(json_key).or_insert(json_text);
                    }
                }
            }
        }
    }

    parsed_chunks_to_extracted(path, &exif_chunks)
}

fn parsed_chunks_to_extracted(path: &Path, chunks: &PngTextChunks) -> Option<ExtractedMeta> {
    if chunks.entries.is_empty() {
        return None;
    }

    let parsed = parse_metadata(chunks);
    if parsed.format == "unknown" && parsed.positive.is_none() && parsed.raw_meta.is_none() {
        return None;
    }

    let tag_source = parsed.positive.clone();
    let meta_source = db_meta_source(
        &parsed.format,
        path.extension().and_then(|ext| ext.to_str()),
    );
    Some(ExtractedMeta {
        meta_source,
        format: parsed.format,
        raw_prompt: parsed.positive,
        raw_negative: parsed.negative,
        raw_meta_json: parsed.raw_meta,
        tag_source,
    })
}

fn apply_chunk_fallback(path: &Path, chunks: &PngTextChunks) -> Option<ExtractedMeta> {
    parsed_chunks_to_extracted(path, chunks)
}

fn apply_bytes_fallback(_path: &Path) -> Option<ExtractedMeta> {
    None
}

fn apply_media_fallback(_path: &Path) -> Option<ExtractedMeta> {
    None
}

fn size_re() -> &'static Regex {
    static SIZE_RE: OnceLock<Regex> = OnceLock::new();
    SIZE_RE.get_or_init(|| Regex::new(r"Size:\s*(\d+)\s*x\s*(\d+)").unwrap())
}

// BUG-40: ComfyUI latent-image node classes that carry width/height.
const COMFYUI_LATENT_CLASSES: &[&str] = &["EmptyLatentImage", "EmptySD3LatentImage"];

/// Python's `int(w)` accepts either a JSON int or a whole-number float
/// (e.g. `832` or `832.0`). serde_json's `Number::as_i64()` only succeeds
/// for the int representation, so a metadata producer that serializes
/// dimensions as floats would silently lose them without this fallback.
///
/// `f as i64` saturates in Rust rather than wrapping (NaN becomes 0), so a
/// nonsense float yields a nonsense-but-bounded dimension exactly as Python's
/// `int()` would raise and leave the field unset — either way the value is
/// rejected downstream rather than becoming a plausible wrong size.
#[allow(clippy::cast_possible_truncation)]
fn value_as_dimension(value: Option<&Value>) -> Option<i64> {
    let value = value?;
    if let Some(i) = value.as_i64() {
        return Some(i);
    }
    value.as_f64().map(|f| f as i64)
}

fn extract_comfyui_resolution(obj: &serde_json::Map<String, Value>) -> (Option<i64>, Option<i64>) {
    for node in obj.values() {
        let Some(node) = node.as_object() else {
            continue;
        };
        let class_type = node.get("class_type").and_then(Value::as_str).unwrap_or("");
        if !COMFYUI_LATENT_CLASSES.contains(&class_type) {
            continue;
        }
        let Some(inputs) = node.get("inputs").and_then(Value::as_object) else {
            continue;
        };
        let w = value_as_dimension(inputs.get("width"));
        let h = value_as_dimension(inputs.get("height"));
        if let (Some(w), Some(h)) = (w, h) {
            return (Some(w), Some(h));
        }
    }
    (None, None)
}

/// Metadata-derived width/height (matches Python's extract_resolution:
/// A1111 "Size: WxH" text, NAI's Comment-wrapped JSON, ComfyUI node graphs).
/// Never a pixel measurement of the actual image.
pub fn extract_resolution(
    raw_prompt: Option<&str>,
    raw_meta_json: Option<&str>,
) -> (Option<i64>, Option<i64>) {
    if let Some(prompt) = raw_prompt {
        if let Ok(Some(caps)) = size_re().captures(prompt) {
            let w = caps.get(1).and_then(|m| m.as_str().parse::<i64>().ok());
            let h = caps.get(2).and_then(|m| m.as_str().parse::<i64>().ok());
            if let (Some(w), Some(h)) = (w, h) {
                return (Some(w), Some(h));
            }
        }
    }

    let Some(raw) = raw_meta_json else {
        return (None, None);
    };
    let Ok(outer) = serde_json::from_str::<Value>(raw) else {
        return (None, None);
    };
    let Some(outer_obj) = outer.as_object() else {
        return (None, None);
    };

    if let Some(comment_str) = outer_obj.get("Comment").and_then(Value::as_str) {
        if let Ok(data) = serde_json::from_str::<Value>(comment_str) {
            let w = value_as_dimension(data.get("width"));
            let h = value_as_dimension(data.get("height"));
            if let (Some(w), Some(h)) = (w, h) {
                return (Some(w), Some(h));
            }
        }
    }

    let w = value_as_dimension(outer_obj.get("width"));
    let h = value_as_dimension(outer_obj.get("height"));
    if let (Some(w), Some(h)) = (w, h) {
        return (Some(w), Some(h));
    }

    let (cw, ch) = extract_comfyui_resolution(outer_obj);
    if cw.is_some() && ch.is_some() {
        return (cw, ch);
    }

    (None, None)
}

pub fn extract_regular_metadata(path: &Path) -> ExtractedMeta {
    if let Some(sidecar) = read_sidecar_txt(path) {
        return ExtractedMeta {
            meta_source: "txt".to_string(),
            format: "unknown".to_string(),
            raw_prompt: Some(sidecar),
            raw_negative: None,
            raw_meta_json: None,
            tag_source: None,
        };
    }

    let chunks = extract_chunks_for_file(path);
    if let Some(extracted) = apply_extension_parsers(path, &chunks) {
        return extracted;
    }
    if let Some(extracted) = apply_chunk_fallback(path, &chunks) {
        return extracted;
    }
    if let Some(extracted) = apply_bytes_fallback(path) {
        return extracted;
    }
    if let Some(extracted) = apply_media_fallback(path) {
        return extracted;
    }

    ExtractedMeta::unknown()
}

#[cfg(test)]
mod tests {
    use super::*;

    const PNG_SIG: &[u8; 8] = b"\x89PNG\r\n\x1a\n";

    fn png_with_text_chunk(keyword: &str, text: &str) -> Vec<u8> {
        let mut out = PNG_SIG.to_vec();
        out.extend_from_slice(&13u32.to_be_bytes());
        out.extend_from_slice(b"IHDR");
        out.extend_from_slice(&[0u8; 13]);
        out.extend_from_slice(&0u32.to_be_bytes());

        let mut chunk = keyword.as_bytes().to_vec();
        chunk.push(0);
        chunk.extend_from_slice(text.as_bytes());
        out.extend_from_slice(&(chunk.len() as u32).to_be_bytes());
        out.extend_from_slice(b"tEXt");
        out.extend_from_slice(&chunk);
        out.extend_from_slice(&0u32.to_be_bytes());

        out.extend_from_slice(&0u32.to_be_bytes());
        out.extend_from_slice(b"IEND");
        out.extend_from_slice(&0u32.to_be_bytes());
        out
    }

    #[test]
    fn sidecar_takes_priority_over_embedded_chunks() {
        let dir = tempfile::tempdir().unwrap();
        let image = dir.path().join("image.png");
        std::fs::write(
            &image,
            png_with_text_chunk("parameters", "embedded\nSteps: 10"),
        )
        .unwrap();
        std::fs::write(dir.path().join("image.txt"), "sidecar prompt\n").unwrap();

        let extracted = extract_regular_metadata(&image);

        assert_eq!(extracted.meta_source, "txt");
        assert_eq!(extracted.raw_prompt.as_deref(), Some("sidecar prompt"));
        assert_eq!(extracted.tag_source, None);
    }

    #[test]
    fn png_chunks_are_parsed_when_no_sidecar_exists() {
        let dir = tempfile::tempdir().unwrap();
        let image = dir.path().join("image.png");
        std::fs::write(
            &image,
            png_with_text_chunk("parameters", "embedded\nSteps: 10"),
        )
        .unwrap();

        let extracted = extract_regular_metadata(&image);

        assert_eq!(extracted.meta_source, "a1111_png");
        assert_eq!(extracted.format, "a1111");
        assert_eq!(extracted.raw_prompt.as_deref(), Some("embedded"));
        assert_eq!(extracted.tag_source.as_deref(), Some("embedded"));
    }

    #[test]
    fn extract_resolution_from_a1111_size_text() {
        let prompt = "1girl, outdoors\nNegative prompt: bad\nSteps: 20, Size: 832x1216, Seed: 1";
        assert_eq!(
            extract_resolution(Some(prompt), None),
            (Some(832), Some(1216))
        );
    }

    #[test]
    fn extract_resolution_from_nai_comment_json() {
        let raw_meta = r#"{"Comment": "{\"width\": 832, \"height\": 1216}"}"#;
        assert_eq!(
            extract_resolution(None, Some(raw_meta)),
            (Some(832), Some(1216))
        );
    }

    #[test]
    fn extract_resolution_from_top_level_width_height() {
        let raw_meta = r#"{"width": 512, "height": 768}"#;
        assert_eq!(
            extract_resolution(None, Some(raw_meta)),
            (Some(512), Some(768))
        );
    }

    #[test]
    fn extract_resolution_accepts_whole_number_floats() {
        // Some metadata producers serialize dimensions as JSON floats
        // (832.0 instead of 832); Python's int(w) accepts both.
        let raw_meta = r#"{"width": 832.0, "height": 1216.0}"#;
        assert_eq!(
            extract_resolution(None, Some(raw_meta)),
            (Some(832), Some(1216))
        );

        let comfyui_meta = r#"{
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1024.0, "height": 1536.0}
            }
        }"#;
        assert_eq!(
            extract_resolution(None, Some(comfyui_meta)),
            (Some(1024), Some(1536))
        );

        let nai_meta = r#"{"Comment": "{\"width\": 832.0, \"height\": 1216.0}"}"#;
        assert_eq!(
            extract_resolution(None, Some(nai_meta)),
            (Some(832), Some(1216))
        );
    }

    #[test]
    fn extract_resolution_from_comfyui_empty_latent_image_node() {
        let raw_meta = r#"{
            "5": {
                "class_type": "EmptyLatentImage",
                "inputs": {"width": 1024, "height": 1536, "batch_size": 1}
            }
        }"#;
        assert_eq!(
            extract_resolution(None, Some(raw_meta)),
            (Some(1024), Some(1536))
        );
    }

    #[test]
    fn extract_resolution_from_comfyui_empty_sd3_latent_image_node() {
        let raw_meta = r#"{
            "5": {
                "class_type": "EmptySD3LatentImage",
                "inputs": {"width": 1280, "height": 1280}
            }
        }"#;
        assert_eq!(
            extract_resolution(None, Some(raw_meta)),
            (Some(1280), Some(1280))
        );
    }

    #[test]
    fn extract_resolution_prefers_a1111_text_over_json() {
        let prompt = "cat, Size: 100x200";
        let raw_meta = r#"{"width": 999, "height": 999}"#;
        assert_eq!(
            extract_resolution(Some(prompt), Some(raw_meta)),
            (Some(100), Some(200))
        );
    }

    #[test]
    fn extract_resolution_none_when_nothing_matches() {
        assert_eq!(extract_resolution(None, None), (None, None));
        assert_eq!(extract_resolution(Some("no size here"), None), (None, None));
        assert_eq!(
            extract_resolution(None, Some(r#"{"unrelated": true}"#)),
            (None, None)
        );
        assert_eq!(extract_resolution(None, Some("not json")), (None, None));
    }
}
