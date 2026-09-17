//! ffprobe-backed metadata for audio and video files.
//!
//! A port of Python's `core/extractors/media_ffprobe_*.py`, which is the last
//! stage of the scan metadata fallback chain: when a file carries no sidecar,
//! no PNG text chunks and no EXIF, a media container can still describe itself
//! through ffprobe.
//!
//! The JSON envelope written to `files.raw_meta_json` is the `media_readonly_v1`
//! shape Python writes, because `upsert_media_extract_state` in tagdb-core
//! reads those exact keys back out to populate `media_extract_state`. Renaming
//! a key here silently empties that table.

use std::path::Path;
use std::process::Command;
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use serde_json::{json, Map, Value};

/// Mirrors Python's `MEDIA_METADATA_SCHEMA_VERSION`.
const MEDIA_METADATA_SCHEMA_VERSION: i64 = 1;
const FFPROBE_TIMEOUT: Duration = Duration::from_secs(5);
/// One retry, as Python's `FFPROBE_RETRY_COUNT`.
const FFPROBE_RETRY_COUNT: u32 = 1;
const FFPROBE_BACKOFF: Duration = Duration::from_millis(200);
/// Python re-probes a failed file only after a day.
const RETRY_AFTER_SECS: i64 = 24 * 60 * 60;

pub const AUDIO_EXTS: &[&str] = &["mp3", "wav", "ogg", "opus", "m4a", "aac", "flac"];
pub const VIDEO_EXTS: &[&str] = &["webm", "mp4", "mov", "m4v", "avi", "mkv", "ogv"];

/// What the fallback produces for one file, in the same field vocabulary as
/// the rest of the chain.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MediaMeta {
    pub meta_source: String,
    pub format: String,
    pub raw_prompt: Option<String>,
    pub raw_meta_json: String,
    pub tag_source: Option<String>,
}

pub fn is_media_file(path: &Path) -> bool {
    path.extension()
        .and_then(|e| e.to_str())
        .map(str::to_ascii_lowercase)
        .is_some_and(|ext| is_media_extension(&ext))
}

/// Whether a lowercase extension (no dot) names an audio or video container
/// ffprobe can describe. Split out so archive scanning can ask the same
/// question about a member name that has no file behind it.
pub fn is_media_extension(ext: &str) -> bool {
    AUDIO_EXTS.contains(&ext) || VIDEO_EXTS.contains(&ext)
}

fn now_ts() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

/// `ffprobe -version`'s first line, minus its `ffprobe version ` prefix.
/// Empty when ffprobe is absent -- Python stores "" rather than NULL there.
fn source_version() -> String {
    let Ok(out) = Command::new("ffprobe").arg("-version").output() else {
        return String::new();
    };
    if !out.status.success() {
        return String::new();
    }
    let text = String::from_utf8_lossy(&out.stdout);
    let line = text.lines().next().unwrap_or("").trim();
    line.strip_prefix("ffprobe version ")
        .unwrap_or(line)
        .trim()
        .to_string()
}

fn state_envelope(
    cache_state: &str,
    source_version: &str,
    error_code: Option<&str>,
    fingerprint_mtime: Option<i64>,
    fingerprint_size: Option<i64>,
    next_retry_after: Option<i64>,
) -> Map<String, Value> {
    let ts = now_ts();
    let mut env = Map::new();
    env.insert("schema".into(), json!("media_readonly_v1"));
    env.insert(
        "metadata_schema_version".into(),
        json!(MEDIA_METADATA_SCHEMA_VERSION),
    );
    env.insert("metadata_extracted_at".into(), json!(ts));
    env.insert("metadata_source".into(), json!("ffprobe"));
    env.insert("metadata_source_version".into(), json!(source_version));
    env.insert("cache_state".into(), json!(cache_state));
    env.insert("error_code".into(), json!(error_code));
    env.insert(
        "error_at".into(),
        if error_code.is_some() {
            json!(ts)
        } else {
            Value::Null
        },
    );
    env.insert("next_retry_after".into(), json!(next_retry_after));
    env.insert(
        "fingerprint".into(),
        json!({
            "mtime": fingerprint_mtime,
            "size": fingerprint_size,
            "hash": Value::Null,
        }),
    );
    env
}

fn failure(
    error_code: &str,
    source_version: &str,
    fingerprint_mtime: Option<i64>,
    fingerprint_size: Option<i64>,
) -> MediaMeta {
    let env = state_envelope(
        "error",
        source_version,
        Some(error_code),
        fingerprint_mtime,
        fingerprint_size,
        Some(now_ts() + RETRY_AFTER_SECS),
    );
    MediaMeta {
        meta_source: "media_error_ffprobe".to_string(),
        format: "media".to_string(),
        raw_prompt: None,
        raw_meta_json: Value::Object(env).to_string(),
        tag_source: None,
    }
}

fn fingerprint(path: &Path) -> (Option<i64>, Option<i64>) {
    let Ok(meta) = path.metadata() else {
        return (None, None);
    };
    let mtime = meta
        .modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64);
    (mtime, Some(meta.len() as i64))
}

/// Probe one file. Always returns a result: a failed probe is recorded as
/// `media_error_ffprobe` with an error envelope, exactly as Python does, so
/// that `media_extract_state` carries the reason and the retry deadline
/// instead of the file looking simply unscanned.
pub fn extract_with_ffprobe(path: &Path) -> MediaMeta {
    let version = source_version();
    let (fp_mtime, fp_size) = fingerprint(path);
    if which_ffprobe().is_none() {
        return failure("missing_tool", &version, None, None);
    }

    let mut last_error = "unknown".to_string();
    for attempt in 0..=FFPROBE_RETRY_COUNT {
        match run_ffprobe(path) {
            Err(code) => last_error = code,
            Ok(stdout) => match serde_json::from_str::<Value>(&stdout) {
                Err(_) => last_error = "parse_error".to_string(),
                Ok(payload) => {
                    let mut normalized = normalize_ffprobe_payload(&payload);
                    if !has_readable_payload(&normalized) {
                        last_error = "parse_error".to_string();
                    } else {
                        let env = state_envelope("ready", &version, None, fp_mtime, fp_size, None);
                        for (k, v) in env {
                            normalized.insert(k, v);
                        }
                        let kind = if normalized.get("video").is_some_and(|v| !v.is_null()) {
                            "video"
                        } else if normalized.get("audio").is_some_and(|v| !v.is_null()) {
                            "audio"
                        } else {
                            "media"
                        };
                        let (raw_prompt, tag_source) = derive_prompt_tags(&normalized);
                        return MediaMeta {
                            meta_source: format!("media_{kind}_ffprobe"),
                            format: "media".to_string(),
                            raw_prompt,
                            raw_meta_json: Value::Object(normalized).to_string(),
                            tag_source,
                        };
                    }
                }
            },
        }
        if attempt < FFPROBE_RETRY_COUNT {
            std::thread::sleep(FFPROBE_BACKOFF);
        }
    }
    failure(&last_error, &version, fp_mtime, fp_size)
}

fn which_ffprobe() -> Option<()> {
    Command::new("ffprobe")
        .arg("-version")
        .output()
        .ok()
        .map(|_| ())
}

/// Run ffprobe once, returning its stdout or the error code Python would
/// record. `Command` has no timeout of its own, so the child is polled and
/// killed past the deadline -- a hung ffprobe must not wedge a whole scan.
fn run_ffprobe(path: &Path) -> Result<String, String> {
    let mut child = Command::new("ffprobe")
        .args([
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            "-show_chapters",
        ])
        .arg(path)
        .stdout(std::process::Stdio::piped())
        .stderr(std::process::Stdio::null())
        .spawn()
        .map_err(|_| "missing_tool".to_string())?;

    let deadline = std::time::Instant::now() + FFPROBE_TIMEOUT;
    loop {
        match child.try_wait() {
            Err(_) => return Err("unknown".to_string()),
            Ok(Some(status)) => {
                let mut stdout = String::new();
                if let Some(mut out) = child.stdout.take() {
                    use std::io::Read;
                    let _ = out.read_to_string(&mut stdout);
                }
                if !status.success() || stdout.trim().is_empty() {
                    return Err("nonzero_exit".to_string());
                }
                return Ok(stdout);
            }
            Ok(None) => {
                if std::time::Instant::now() >= deadline {
                    let _ = child.kill();
                    let _ = child.wait();
                    return Err("timeout".to_string());
                }
                std::thread::sleep(Duration::from_millis(25));
            }
        }
    }
}

/// `value as i64`, saturating -- the same behaviour `as` already has (NaN
/// yields 0, out-of-range saturates), with the truncation named here instead
/// of left implicit at each call site. Mirrors yu-server's `num::sat_i64`,
/// which is crate-private there.
#[allow(clippy::cast_possible_truncation)]
#[inline]
fn sat_i64(value: f64) -> i64 {
    value as i64
}

fn to_int(v: Option<&Value>) -> Option<i64> {
    let v = v?;
    match v {
        Value::Number(n) => n.as_f64().map(sat_i64),
        Value::String(s) if !s.is_empty() => s.parse::<f64>().ok().map(sat_i64),
        // ffprobe writes every numeric field as a JSON number or a decimal
        // string; anything else in this slot is not a value we can read.
        Value::String(_) | Value::Null | Value::Bool(_) | Value::Array(_) | Value::Object(_) => {
            None
        }
    }
}

fn to_ms(v: Option<&Value>) -> Option<i64> {
    let v = v?;
    let seconds = match v {
        Value::Number(n) => n.as_f64(),
        Value::String(s) if !s.is_empty() => s.parse::<f64>().ok(),
        Value::String(_) | Value::Null | Value::Bool(_) | Value::Array(_) | Value::Object(_) => {
            None
        }
    }?;
    Some(sat_i64(seconds * 1000.0))
}

/// ffprobe reports frame rates as "30000/1001". "0/0" and "N/A" mean unknown.
fn fps_from_ratio(v: Option<&Value>) -> Option<f64> {
    let s = v?.as_str().unwrap_or("").trim().to_string();
    if s.is_empty() || s == "0/0" || s == "N/A" {
        return None;
    }
    let value = if let Some((a, b)) = s.split_once('/') {
        let (a, b) = (a.parse::<f64>().ok()?, b.parse::<f64>().ok()?);
        if b == 0.0 {
            return None;
        }
        a / b
    } else {
        s.parse::<f64>().ok()?
    };
    Some((value * 1000.0).round() / 1000.0)
}

fn pick_stream<'a>(payload: &'a Value, codec_type: &str) -> Option<&'a Value> {
    payload.get("streams")?.as_array()?.iter().find(|st| {
        st.get("codec_type")
            .and_then(Value::as_str)
            .map(|t| t.to_ascii_lowercase())
            .as_deref()
            == Some(codec_type)
    })
}

fn non_empty_string(v: Option<&Value>) -> Option<String> {
    let s = v?.as_str()?.to_string();
    if s.is_empty() {
        None
    } else {
        Some(s)
    }
}

/// Container tags under the names Python normalizes them to; the first alias
/// that carries a non-blank value wins.
fn extract_tags(format_tags: &Value) -> Map<String, Value> {
    const ALIASES: &[(&str, &[&str])] = &[
        ("title", &["title", "TITLE"]),
        (
            "comment",
            &["comment", "COMMENT", "description", "DESCRIPTION"],
        ),
        ("creation_time", &["creation_time", "DATE", "date"]),
        ("artist", &["artist", "ARTIST"]),
        ("album", &["album", "ALBUM"]),
        ("encoder", &["encoder", "ENCODER"]),
        ("genre", &["genre", "GENRE"]),
    ];
    let mut out = Map::new();
    for (key, aliases) in ALIASES {
        for alias in *aliases {
            let Some(raw) = format_tags.get(*alias) else {
                continue;
            };
            let value = match raw {
                Value::String(s) => s.trim().to_string(),
                // A tag that is not a string still has a printable form;
                // Python's `str(raw).strip()` keeps it too.
                other @ (Value::Null
                | Value::Bool(_)
                | Value::Number(_)
                | Value::Array(_)
                | Value::Object(_)) => other.to_string(),
            };
            if !value.is_empty() {
                out.insert((*key).to_string(), json!(value));
                break;
            }
        }
    }
    out
}

fn any_non_null(obj: &Map<String, Value>) -> bool {
    obj.values().any(|v| !v.is_null())
}

pub fn normalize_ffprobe_payload(payload: &Value) -> Map<String, Value> {
    let fmt = payload.get("format").cloned().unwrap_or(json!({}));
    let format_tags = fmt.get("tags").cloned().unwrap_or(json!({}));
    let tags = extract_tags(&format_tags);

    let video = pick_stream(payload, "video").cloned().unwrap_or(json!({}));
    let audio = pick_stream(payload, "audio").cloned().unwrap_or(json!({}));

    let mut video_obj = Map::new();
    video_obj.insert(
        "codec".into(),
        json!(non_empty_string(video.get("codec_name"))),
    );
    video_obj.insert("width".into(), json!(to_int(video.get("width"))));
    video_obj.insert("height".into(), json!(to_int(video.get("height"))));
    video_obj.insert(
        "fps_avg".into(),
        json!(fps_from_ratio(video.get("avg_frame_rate"))),
    );
    video_obj.insert(
        "fps_nominal".into(),
        json!(fps_from_ratio(video.get("r_frame_rate"))),
    );
    video_obj.insert("bitrate".into(), json!(to_int(video.get("bit_rate"))));
    video_obj.insert(
        "pix_fmt".into(),
        json!(non_empty_string(video.get("pix_fmt"))),
    );

    let mut audio_obj = Map::new();
    audio_obj.insert(
        "codec".into(),
        json!(non_empty_string(audio.get("codec_name"))),
    );
    audio_obj.insert("channels".into(), json!(to_int(audio.get("channels"))));
    audio_obj.insert(
        "sample_rate".into(),
        json!(to_int(audio.get("sample_rate"))),
    );
    audio_obj.insert("bitrate".into(), json!(to_int(audio.get("bit_rate"))));

    let chapters: Vec<Value> = payload
        .get("chapters")
        .and_then(Value::as_array)
        .map(|list| {
            list.iter()
                .map(|ch| {
                    json!({
                        "start_ms": to_ms(ch.get("start_time")),
                        "end_ms": to_ms(ch.get("end_time")),
                        "title": non_empty_string(
                            ch.get("tags").and_then(|t| t.get("title"))
                        ),
                    })
                })
                .collect()
        })
        .unwrap_or_default();

    let format_name = fmt
        .get("format_name")
        .and_then(Value::as_str)
        .unwrap_or("")
        .to_string();
    let container = if format_name.is_empty() {
        Value::Null
    } else {
        json!(format_name.split(',').next().unwrap_or(""))
    };

    let mut out = Map::new();
    out.insert("schema".into(), json!("media_readonly_v1"));
    out.insert("container".into(), container);
    out.insert("duration_ms".into(), json!(to_ms(fmt.get("duration"))));
    out.insert("filesize".into(), json!(to_int(fmt.get("size"))));
    out.insert("overall_bitrate".into(), json!(to_int(fmt.get("bit_rate"))));
    out.insert(
        "video".into(),
        if any_non_null(&video_obj) {
            Value::Object(video_obj)
        } else {
            Value::Null
        },
    );
    out.insert(
        "audio".into(),
        if any_non_null(&audio_obj) {
            Value::Object(audio_obj)
        } else {
            Value::Null
        },
    );
    out.insert("tags_readonly".into(), Value::Object(tags));
    out.insert("chapters".into(), Value::Array(chapters));
    out
}

pub fn has_readable_payload(meta: &Map<String, Value>) -> bool {
    if meta.get("duration_ms").is_some_and(|v| !v.is_null())
        || meta.get("container").is_some_and(|v| !v.is_null())
    {
        return true;
    }
    for key in ["video", "audio"] {
        if let Some(Value::Object(obj)) = meta.get(key) {
            if any_non_null(obj) {
                return true;
            }
        }
    }
    let has_tags = matches!(meta.get("tags_readonly"), Some(Value::Object(o)) if !o.is_empty());
    let has_chapters = matches!(meta.get("chapters"), Some(Value::Array(a)) if !a.is_empty());
    has_tags || has_chapters
}

/// Prompt text and tag source, joined from container tags the same way Python
/// does -- the prompt drops `comment`, the tag source keeps it.
pub fn derive_prompt_tags(meta: &Map<String, Value>) -> (Option<String>, Option<String>) {
    let tags = match meta.get("tags_readonly") {
        Some(Value::Object(o)) => o.clone(),
        _ => Map::new(),
    };
    let get = |key: &str| tags.get(key).and_then(Value::as_str).map(str::to_string);
    let join = |parts: Vec<Option<String>>| {
        let joined = parts.into_iter().flatten().collect::<Vec<_>>().join(", ");
        if joined.is_empty() {
            None
        } else {
            Some(joined)
        }
    };
    let prompt = join(vec![
        get("title"),
        get("artist"),
        get("album"),
        get("genre"),
    ]);
    let tag_source = join(vec![
        get("title"),
        get("artist"),
        get("album"),
        get("genre"),
        get("comment"),
    ])
    .or_else(|| prompt.clone());
    (prompt, tag_source)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn video_payload() -> Value {
        json!({
            "format": {
                "format_name": "mov,mp4,m4a",
                "duration": "12.5",
                "size": "1048576",
                "bit_rate": "700000",
                "tags": {"title": "Clip", "ARTIST": "Ann", "comment": "  note  "}
            },
            "streams": [
                {"codec_type": "audio", "codec_name": "aac", "channels": 2, "sample_rate": "48000"},
                {"codec_type": "video", "codec_name": "h264", "width": 1920, "height": 1080,
                 "avg_frame_rate": "30000/1001", "r_frame_rate": "0/0", "pix_fmt": "yuv420p"}
            ],
            "chapters": [{"start_time": "0.0", "end_time": "1.5", "tags": {"title": "Intro"}}]
        })
    }

    #[test]
    fn normalizes_container_streams_and_chapters() {
        let n = normalize_ffprobe_payload(&video_payload());
        assert_eq!(n["container"], json!("mov"));
        assert_eq!(n["duration_ms"], json!(12500));
        assert_eq!(n["overall_bitrate"], json!(700000));
        assert_eq!(n["video"]["width"], json!(1920));
        // 30000/1001 rounds to 3 decimals, and "0/0" is unknown, not 0.
        assert_eq!(n["video"]["fps_avg"], json!(29.97));
        assert_eq!(n["video"]["fps_nominal"], Value::Null);
        assert_eq!(n["audio"]["sample_rate"], json!(48000));
        assert_eq!(n["chapters"][0]["start_ms"], json!(0));
        assert_eq!(n["chapters"][0]["title"], json!("Intro"));
        // Alias resolution and trimming, as Python's _extract_tags does.
        assert_eq!(n["tags_readonly"]["artist"], json!("Ann"));
        assert_eq!(n["tags_readonly"]["comment"], json!("note"));
        assert!(has_readable_payload(&n));
    }

    /// A stream section whose every field is missing must serialize as null,
    /// not as an object of nulls: `extract_with_ffprobe` picks the
    /// `media_<kind>_ffprobe` source by asking whether these are null.
    #[test]
    fn absent_streams_normalize_to_null() {
        let n = normalize_ffprobe_payload(&json!({"format": {"format_name": "wav"}}));
        assert_eq!(n["video"], Value::Null);
        assert_eq!(n["audio"], Value::Null);
    }

    #[test]
    fn empty_payload_is_not_readable() {
        let n = normalize_ffprobe_payload(&json!({}));
        assert!(!has_readable_payload(&n));
    }

    #[test]
    fn prompt_omits_comment_but_tag_source_keeps_it() {
        let n = normalize_ffprobe_payload(&video_payload());
        let (prompt, tag_source) = derive_prompt_tags(&n);
        assert_eq!(prompt.as_deref(), Some("Clip, Ann"));
        assert_eq!(tag_source.as_deref(), Some("Clip, Ann, note"));
    }

    /// With no tags at all Python yields (None, None) -- `tag_source` falls
    /// back to the prompt, which is itself None.
    #[test]
    fn no_tags_yields_no_prompt() {
        let n = normalize_ffprobe_payload(&json!({"format": {"format_name": "wav"}}));
        assert_eq!(derive_prompt_tags(&n), (None, None));
    }

    #[test]
    fn media_extensions_are_recognized_case_insensitively() {
        assert!(is_media_file(Path::new("/x/a.MP4")));
        assert!(is_media_file(Path::new("/x/a.flac")));
        assert!(!is_media_file(Path::new("/x/a.png")));
        assert!(!is_media_file(Path::new("/x/noext")));
    }

    /// A failed probe must still carry the envelope keys
    /// `upsert_media_extract_state` reads, or the row silently stays empty.
    #[test]
    fn failure_envelope_carries_error_state() {
        let meta = failure("timeout", "7.1", Some(11), Some(22));
        assert_eq!(meta.meta_source, "media_error_ffprobe");
        let env: Value = serde_json::from_str(&meta.raw_meta_json).unwrap();
        assert_eq!(env["cache_state"], json!("error"));
        assert_eq!(env["error_code"], json!("timeout"));
        assert_eq!(env["metadata_source"], json!("ffprobe"));
        assert_eq!(env["metadata_source_version"], json!("7.1"));
        assert_eq!(env["fingerprint"]["mtime"], json!(11));
        assert_eq!(env["fingerprint"]["size"], json!(22));
        assert!(env["error_at"].is_i64());
        assert!(env["next_retry_after"].as_i64().unwrap() > env["error_at"].as_i64().unwrap());
    }
}
