//! The non-parser halves of `GET /api/file/{file_id}`: read-only media
//! metadata, the sections built from it, and animation detection.
//!
//! Ports `core/file_api/detail_media_parse.py`,
//! `core/file_api/detail_media_sections.py` and
//! `core/files_core/animated_detect.py`. These are **core** features, not
//! extension ones: Python puts them in the same payload the UI renders with
//! `renderSections`, and the Rust route was answering without them.

use std::path::Path;

use serde_json::{json, Map, Value};

/// Mirrors Python's `MEDIA_METADATA_SCHEMA_VERSION`.
const MEDIA_METADATA_SCHEMA_VERSION: i64 = 1;

fn to_int(v: Option<&Value>) -> Option<i64> {
    match v? {
        Value::Number(n) => n.as_f64().map(sat_i64),
        Value::String(s) if !s.is_empty() => s.parse::<f64>().ok().map(sat_i64),
        // ffprobe writes numbers as JSON numbers or decimal strings; nothing
        // else in this slot is a value we can read.
        Value::String(_) | Value::Null | Value::Bool(_) | Value::Array(_) | Value::Object(_) => {
            None
        }
    }
}

/// `value as i64`, saturating -- the behaviour `as` already has, named here
/// rather than left implicit. Same helper as `meta_extract::ffprobe`.
#[allow(clippy::cast_possible_truncation)]
#[inline]
fn sat_i64(value: f64) -> i64 {
    value as i64
}

fn non_blank(v: Option<&Value>) -> Option<String> {
    let text = match v? {
        Value::String(s) => s.trim().to_string(),
        Value::Null => return None,
        // A non-string tag still has a printable form; Python's `str(raw)`
        // keeps it too.
        other @ (Value::Bool(_) | Value::Number(_) | Value::Array(_) | Value::Object(_)) => {
            other.to_string()
        }
    };
    (!text.is_empty()).then_some(text)
}

/// Upgrade a pre-`media_readonly_v1` blob (the mutagen-era shape) to v1.
fn normalize_from_legacy(raw: &Map<String, Value>) -> Map<String, Value> {
    let mut tags = Map::new();
    for key in ["title", "artist", "album", "genre", "comment", "date"] {
        if let Some(value) = non_blank(raw.get(key)) {
            // Python renames `date` to `creation_time` on the way in.
            let out_key = if key == "date" { "creation_time" } else { key };
            tags.insert(out_key.to_string(), json!(value));
        }
    }
    let duration_ms = raw
        .get("duration_sec")
        .and_then(|v| match v {
            Value::Number(n) => n.as_f64(),
            Value::String(s) if !s.is_empty() => s.parse::<f64>().ok(),
            Value::String(_)
            | Value::Null
            | Value::Bool(_)
            | Value::Array(_)
            | Value::Object(_) => None,
        })
        .map(|secs| sat_i64(secs * 1000.0));

    let mut out = Map::new();
    out.insert("schema".into(), json!("media_readonly_v1"));
    out.insert("source".into(), json!("mutagen_legacy"));
    out.insert("container".into(), Value::Null);
    out.insert("duration_ms".into(), json!(duration_ms));
    out.insert("filesize".into(), Value::Null);
    out.insert("overall_bitrate".into(), Value::Null);
    out.insert("video".into(), Value::Null);
    out.insert("audio".into(), Value::Null);
    out.insert("tags_readonly".into(), Value::Object(tags));
    out.insert("chapters".into(), json!([]));
    out
}

/// Read-only media metadata for one row, or `None` when the row is not media.
///
/// Python's resolver also schedules deferred re-extraction and writes the
/// normalized JSON back; that write path is deliberately not ported here --
/// this route is a read, and the scan owns the write.
pub fn resolve_readonly_media_metadata(
    meta_source: &str,
    raw_meta_json: Option<&str>,
) -> Option<Map<String, Value>> {
    if !meta_source.starts_with("media_") {
        return None;
    }
    let raw: Value = serde_json::from_str(raw_meta_json?).ok()?;
    let raw = raw.as_object()?;

    if raw.get("schema").and_then(Value::as_str) == Some("media_readonly_v1") {
        let mut meta = raw.clone();
        // Same field-level repairs Python applies before handing the metadata
        // out, so an older row still renders.
        if to_int(meta.get("metadata_schema_version"))
            .is_none_or(|v| v < MEDIA_METADATA_SCHEMA_VERSION)
        {
            meta.insert(
                "metadata_schema_version".into(),
                json!(MEDIA_METADATA_SCHEMA_VERSION),
            );
        }
        if non_blank(meta.get("metadata_source")).is_none() {
            meta.insert("metadata_source".into(), json!("ffprobe"));
        }
        return Some(meta);
    }
    Some(normalize_from_legacy(raw))
}

fn table_section(title: &str, content: Value) -> Value {
    json!({"title": title, "display_type": "table", "content": content})
}

/// The `Media Metadata (read-only) / *` sections Python builds from the same
/// metadata. Field order and titles are load-bearing: the UI renders whatever
/// rows it is given, so a renamed title is a renamed section on screen.
pub fn build_readonly_media_sections(meta: Option<&Map<String, Value>>) -> Vec<Value> {
    let Some(meta) = meta else {
        return vec![];
    };
    let mut sections = Vec::new();

    let mut file_rows = Map::new();
    if let Some(container) = meta.get("container").filter(|v| !v.is_null()) {
        file_rows.insert("Container".into(), container.clone());
    }
    for (key, label) in [
        ("duration_ms", "Duration(ms)"),
        ("filesize", "File size(bytes)"),
        ("overall_bitrate", "Bitrate(bps)"),
    ] {
        if let Some(value) = meta.get(key).filter(|v| !v.is_null()) {
            file_rows.insert(label.into(), value.clone());
        }
    }
    if !file_rows.is_empty() {
        sections.push(table_section(
            "Media Metadata (read-only) / File",
            json!([Value::Object(file_rows)]),
        ));
    }

    for (key, title) in [
        ("video", "Media Metadata (read-only) / Video"),
        ("audio", "Media Metadata (read-only) / Audio"),
    ] {
        if let Some(Value::Object(stream)) = meta.get(key) {
            let present: Map<String, Value> = stream
                .iter()
                .filter(|(_, v)| !v.is_null())
                .map(|(k, v)| (k.clone(), v.clone()))
                .collect();
            if !present.is_empty() {
                sections.push(table_section(title, json!([Value::Object(present)])));
            }
        }
    }

    if let Some(Value::Object(tags)) = meta.get("tags_readonly") {
        if !tags.is_empty() {
            sections.push(table_section(
                "Media Metadata (read-only) / Embedded tags",
                json!([Value::Object(tags.clone())]),
            ));
        }
    }

    if let Some(Value::Array(chapters)) = meta.get("chapters") {
        if !chapters.is_empty() {
            sections.push(table_section(
                "Media Metadata (read-only) / Chapters",
                Value::Array(chapters.clone()),
            ));
        }
    }

    sections
}

/// Whether an image carries animation: `Some(true)`/`Some(false)` for the
/// formats that can, `None` when unknown -- and `None` for an archive member,
/// whose virtual path cannot be opened.
pub fn detect_animated(path: &str) -> Option<bool> {
    if path.contains('!') {
        return None;
    }
    let lower = path.to_ascii_lowercase();
    if lower.ends_with(".gif") {
        // Python treats every GIF as animated rather than parsing its blocks.
        return Some(true);
    }
    if lower.ends_with(".png") {
        return Some(is_apng(Path::new(path)));
    }
    if lower.ends_with(".webp") {
        return Some(is_animated_webp(Path::new(path)));
    }
    None
}

/// APNG declares itself with an `acTL` chunk that must precede `IDAT`.
fn is_apng(path: &Path) -> bool {
    let Ok(data) = read_prefix(path, 64 * 1024) else {
        return false;
    };
    if !data.starts_with(b"\x89PNG\r\n\x1a\n") {
        return false;
    }
    let mut offset = 8usize;
    // `get` rather than indexing: a truncated or malformed PNG must answer
    // "not animated", never panic in a read path.
    while let Some(header) = data.get(offset..offset + 8) {
        let (len_bytes, ctype) = header.split_at(4);
        let Ok(len_arr) = <[u8; 4]>::try_from(len_bytes) else {
            return false;
        };
        let length = u32::from_be_bytes(len_arr) as usize;
        if ctype == b"acTL" {
            return true;
        }
        if ctype == b"IDAT" || ctype == b"IEND" {
            return false;
        }
        // 8-byte header + payload + 4-byte CRC.
        let Some(next) = offset.checked_add(12).and_then(|n| n.checked_add(length)) else {
            return false;
        };
        offset = next;
    }
    false
}

/// An animated WebP is a RIFF container carrying an `ANIM` chunk.
fn is_animated_webp(path: &Path) -> bool {
    let Ok(data) = read_prefix(path, 64 * 1024) else {
        return false;
    };
    if data.len() < 12 || !data.starts_with(b"RIFF") || data.get(8..12) != Some(b"WEBP") {
        return false;
    }
    data.windows(4).any(|w| w == b"ANIM")
}

fn read_prefix(path: &Path, limit: usize) -> std::io::Result<Vec<u8>> {
    use std::io::Read;
    let mut file = std::fs::File::open(path)?;
    let mut buf = Vec::new();
    file.by_ref().take(limit as u64).read_to_end(&mut buf)?;
    Ok(buf)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn meta_from(json_text: &str) -> Option<Map<String, Value>> {
        resolve_readonly_media_metadata("media_audio_ffprobe", Some(json_text))
    }

    #[test]
    fn non_media_rows_have_no_metadata() {
        assert!(resolve_readonly_media_metadata("a1111_png", Some("{}")).is_none());
        assert!(resolve_readonly_media_metadata("media_audio_ffprobe", None).is_none());
    }

    #[test]
    fn v1_metadata_is_repaired_not_replaced() {
        let meta = meta_from(r#"{"schema":"media_readonly_v1","container":"wav"}"#).unwrap();
        assert_eq!(meta["container"], json!("wav"));
        // The two fields Python fills in when they are missing.
        assert_eq!(meta["metadata_schema_version"], json!(1));
        assert_eq!(meta["metadata_source"], json!("ffprobe"));
    }

    #[test]
    fn legacy_metadata_is_upgraded_to_v1() {
        let meta = meta_from(r#"{"title":" Song ","date":"2024","duration_sec":"1.5"}"#).unwrap();
        assert_eq!(meta["schema"], json!("media_readonly_v1"));
        assert_eq!(meta["source"], json!("mutagen_legacy"));
        assert_eq!(meta["duration_ms"], json!(1500));
        // `date` is renamed and values are trimmed, as Python does.
        assert_eq!(meta["tags_readonly"]["creation_time"], json!("2024"));
        assert_eq!(meta["tags_readonly"]["title"], json!("Song"));
    }

    #[test]
    fn sections_cover_file_streams_tags_and_chapters() {
        let meta = meta_from(
            r#"{"schema":"media_readonly_v1","container":"mp4","duration_ms":1200,
                "filesize":99,"overall_bitrate":700,
                "video":{"codec":"h264","width":16,"height":9,"bitrate":null},
                "audio":{"codec":"aac"},
                "tags_readonly":{"title":"Clip"},
                "chapters":[{"start_ms":0,"title":"Intro"}]}"#,
        )
        .unwrap();
        let sections = build_readonly_media_sections(Some(&meta));
        let titles: Vec<&str> = sections
            .iter()
            .map(|s| s["title"].as_str().unwrap())
            .collect();
        assert_eq!(
            titles,
            vec![
                "Media Metadata (read-only) / File",
                "Media Metadata (read-only) / Video",
                "Media Metadata (read-only) / Audio",
                "Media Metadata (read-only) / Embedded tags",
                "Media Metadata (read-only) / Chapters",
            ]
        );
        assert_eq!(sections[0]["content"][0]["Duration(ms)"], json!(1200));
        // Null stream fields are dropped, not rendered as empty cells.
        assert!(sections[1]["content"][0].get("bitrate").is_none());
        assert_eq!(sections[1]["content"][0]["width"], json!(16));
    }

    #[test]
    fn empty_and_absent_metadata_yield_no_sections() {
        assert!(build_readonly_media_sections(None).is_empty());
        let meta = meta_from(r#"{"schema":"media_readonly_v1"}"#).unwrap();
        assert!(build_readonly_media_sections(Some(&meta)).is_empty());
    }

    #[test]
    fn archive_members_and_unknown_formats_report_nothing() {
        assert_eq!(detect_animated("/lib/pack.zip!a.png"), None);
        assert_eq!(detect_animated("/lib/a.jpg"), None);
    }

    #[test]
    fn apng_is_detected_and_plain_png_is_not() {
        let dir = tempfile::tempdir().unwrap();

        let plain = dir.path().join("plain.png");
        std::fs::write(&plain, png_bytes(false)).unwrap();
        assert_eq!(detect_animated(plain.to_str().unwrap()), Some(false));

        let apng = dir.path().join("anim.png");
        std::fs::write(&apng, png_bytes(true)).unwrap();
        assert_eq!(detect_animated(apng.to_str().unwrap()), Some(true));
    }

    #[test]
    fn animated_webp_is_detected_by_its_anim_chunk() {
        let dir = tempfile::tempdir().unwrap();
        let still = dir.path().join("still.webp");
        let mut bytes = b"RIFF\0\0\0\0WEBPVP8 ".to_vec();
        bytes.extend_from_slice(&[0u8; 16]);
        std::fs::write(&still, &bytes).unwrap();
        assert_eq!(detect_animated(still.to_str().unwrap()), Some(false));

        let anim = dir.path().join("anim.webp");
        let mut bytes = b"RIFF\0\0\0\0WEBPVP8X".to_vec();
        bytes.extend_from_slice(&[0u8; 12]);
        bytes.extend_from_slice(b"ANIM");
        std::fs::write(&anim, &bytes).unwrap();
        assert_eq!(detect_animated(anim.to_str().unwrap()), Some(true));
    }

    /// A minimal PNG, optionally carrying the `acTL` chunk before `IDAT`.
    fn png_bytes(animated: bool) -> Vec<u8> {
        fn chunk(kind: &[u8; 4], body: &[u8]) -> Vec<u8> {
            let mut out = (body.len() as u32).to_be_bytes().to_vec();
            out.extend_from_slice(kind);
            out.extend_from_slice(body);
            out.extend_from_slice(&0u32.to_be_bytes());
            out
        }
        let mut out = b"\x89PNG\r\n\x1a\n".to_vec();
        out.extend_from_slice(&chunk(b"IHDR", &[0u8; 13]));
        if animated {
            out.extend_from_slice(&chunk(b"acTL", &[0u8; 8]));
        }
        out.extend_from_slice(&chunk(b"IDAT", &[0u8; 4]));
        out.extend_from_slice(&chunk(b"IEND", b""));
        out
    }
}
