use std::ffi::OsString;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use fancy_regex::Regex;
use meta_extract::{
    db_meta_source, parse_metadata_with, read_exif_tags, read_png_text_chunks, ParserToggles,
    PngTextChunks,
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

fn apply_extension_parsers(
    path: &Path,
    chunks: &PngTextChunks,
    toggles: ParserToggles,
) -> Option<ExtractedMeta> {
    if let Some(extracted) = parsed_chunks_to_extracted(path, chunks, toggles) {
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

    let exif_chunks = exif_chunks_from_tags(exif_tags);

    parsed_chunks_to_extracted(path, &exif_chunks, toggles)
}

/// Flatten EXIF tags into the chunk map the parsers expect. A `UserComment`
/// carrying our `YU_META:` JSON is unwrapped and its string fields are lifted
/// to top-level keys, which is how A1111/NAI metadata survives a JPEG
/// round-trip.
///
/// Public because `/inspect_image` and `/inspect_zip` need the same mapping.
/// They used to build their own chunk map with an `exif:` prefix on every key,
/// so the parsers -- which look for `Comment` -- never saw the metadata and
/// every NAI WebP came back as `format=unknown`. One predicate, one place.
pub fn exif_chunks_from_tags(
    exif_tags: std::collections::HashMap<String, String>,
) -> PngTextChunks {
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
    exif_chunks
}

fn parsed_chunks_to_extracted(
    path: &Path,
    chunks: &PngTextChunks,
    toggles: ParserToggles,
) -> Option<ExtractedMeta> {
    if chunks.entries.is_empty() {
        return None;
    }

    let parsed = parse_metadata_with(chunks, toggles);
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

fn apply_chunk_fallback(
    path: &Path,
    chunks: &PngTextChunks,
    toggles: ParserToggles,
) -> Option<ExtractedMeta> {
    parsed_chunks_to_extracted(path, chunks, toggles)
}

/// Extract metadata for a file whose bytes are already in memory, named by
/// `virtual_path` (an `archive.zip!inner/name.png` path for archive members).
///
/// Archive members cannot go through `extract_regular_metadata`: there is no
/// real file to open, no sidecar to look for beside them, and ffprobe cannot
/// probe them in place. What remains -- PNG text chunks and EXIF -- is what
/// Python's zip worker reads too (`apply_extractor_by_extension`).
pub fn extract_metadata_from_bytes(virtual_path: &Path, data: &[u8]) -> ExtractedMeta {
    extract_metadata_from_bytes_with(virtual_path, data, ParserToggles::default())
}

/// `extract_metadata_from_bytes`, honouring the per-format scan toggles.
pub fn extract_metadata_from_bytes_with(
    virtual_path: &Path,
    data: &[u8],
    toggles: ParserToggles,
) -> ExtractedMeta {
    let extension = virtual_path
        .extension()
        .and_then(|ext| ext.to_str())
        .map(str::to_ascii_lowercase);

    let chunks = match extension.as_deref() {
        Some("png") => meta_extract::parse_png_text_chunks(data),
        _ => PngTextChunks::default(),
    };
    if let Some(extracted) = parsed_chunks_to_extracted(virtual_path, &chunks, toggles) {
        return extracted;
    }

    let supports_exif = matches!(
        extension.as_deref(),
        Some("jpg" | "jpeg" | "jxl" | "avif" | "heif" | "heic" | "webp")
    );
    if supports_exif {
        let exif_tags = meta_extract::read_exif_tags_from_bytes(data);
        if !exif_tags.is_empty() {
            let exif_chunks = exif_chunks_from_tags(exif_tags);
            if let Some(extracted) = parsed_chunks_to_extracted(virtual_path, &exif_chunks, toggles)
            {
                return extracted;
            }
        }
    }

    ExtractedMeta::unknown()
}

fn apply_bytes_fallback(_path: &Path) -> Option<ExtractedMeta> {
    None
}

fn apply_media_fallback(path: &Path) -> Option<ExtractedMeta> {
    if !meta_extract::is_media_file(path) {
        return None;
    }
    // Python records the failed probe too (`media_error_ffprobe`), so that
    // media_extract_state carries the reason and the retry deadline rather
    // than leaving the file looking unscanned.
    let media = meta_extract::extract_with_ffprobe(path);
    Some(ExtractedMeta {
        meta_source: media.meta_source,
        format: media.format,
        raw_prompt: media.raw_prompt,
        raw_negative: None,
        raw_meta_json: Some(media.raw_meta_json),
        tag_source: media.tag_source,
    })
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
    extract_regular_metadata_with(path, ParserToggles::default())
}

/// `extract_regular_metadata`, honouring the per-format scan toggles
/// (`extract_a1111` / `extract_comfyui`).
pub fn extract_regular_metadata_with(path: &Path, toggles: ParserToggles) -> ExtractedMeta {
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
    if let Some(extracted) = apply_extension_parsers(path, &chunks, toggles) {
        return extracted;
    }
    if let Some(extracted) = apply_chunk_fallback(path, &chunks, toggles) {
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

    /// A real WAV must come back through the media stage of the chain, not as
    /// `unknown`. Writing a valid 44-byte PCM header is enough for ffprobe to
    /// describe the container, which is exactly the case Python covers.
    ///
    /// Skipped where ffprobe is absent rather than asserting a failure
    /// envelope, so the suite stays honest on machines without it.
    #[test]
    fn media_files_reach_the_ffprobe_stage() {
        if std::process::Command::new("ffprobe")
            .arg("-version")
            .output()
            .is_err()
        {
            eprintln!("ffprobe not installed; skipping");
            return;
        }
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("tone.wav");
        std::fs::write(&path, minimal_wav()).unwrap();

        let extracted = extract_regular_metadata(&path);
        assert_eq!(
            extracted.meta_source, "media_audio_ffprobe",
            "media fallback must run for audio files, got {extracted:?}"
        );
        assert_eq!(extracted.format, "media");
        let env: Value = serde_json::from_str(extracted.raw_meta_json.as_deref().unwrap()).unwrap();
        assert_eq!(env["cache_state"], serde_json::json!("ready"));
        assert_eq!(env["metadata_source"], serde_json::json!("ffprobe"));
        assert_eq!(env["container"], serde_json::json!("wav"));
        assert!(env["audio"]["sample_rate"].as_i64().is_some());
    }

    /// 8 kHz mono 16-bit PCM, one sample -- the smallest thing ffprobe will
    /// still parse as a WAV.
    fn minimal_wav() -> Vec<u8> {
        let sample_rate: u32 = 8000;
        let data: [u8; 2] = [0, 0];
        let mut out = Vec::new();
        out.extend_from_slice(b"RIFF");
        out.extend_from_slice(&(36u32 + data.len() as u32).to_le_bytes());
        out.extend_from_slice(b"WAVEfmt ");
        out.extend_from_slice(&16u32.to_le_bytes()); // PCM header size
        out.extend_from_slice(&1u16.to_le_bytes()); // format = PCM
        out.extend_from_slice(&1u16.to_le_bytes()); // channels
        out.extend_from_slice(&sample_rate.to_le_bytes());
        out.extend_from_slice(&(sample_rate * 2).to_le_bytes()); // byte rate
        out.extend_from_slice(&2u16.to_le_bytes()); // block align
        out.extend_from_slice(&16u16.to_le_bytes()); // bits per sample
        out.extend_from_slice(b"data");
        out.extend_from_slice(&(data.len() as u32).to_le_bytes());
        out.extend_from_slice(&data);
        out
    }

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
