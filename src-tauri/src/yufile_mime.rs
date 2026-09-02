/// Allowed media file extensions for yufile:// protocol.
/// Only media types are served — arbitrary file read is blocked.
pub fn is_allowed_media_ext(ext: &str) -> bool {
    matches!(
        ext,
        "mp4"
            | "m4v"
            | "webm"
            | "mov"
            | "mkv"
            | "avi"
            | "ogv"
            | "mp3"
            | "wav"
            | "ogg"
            | "opus"
            | "m4a"
            | "aac"
            | "flac"
    )
}

/// Determine MIME type from file extension.
pub fn mime_from_ext(ext: &str) -> &'static str {
    match ext {
        "mp4" | "m4v" => "video/mp4",
        "webm" => "video/webm",
        "mov" => "video/quicktime",
        "mkv" => "video/x-matroska",
        "avi" => "video/x-msvideo",
        "ogv" => "video/ogg",
        "mp3" => "audio/mpeg",
        "wav" => "audio/wav",
        "ogg" | "opus" => "audio/ogg",
        "m4a" | "aac" => "audio/mp4",
        "flac" => "audio/flac",
        _ => "application/octet-stream",
    }
}
