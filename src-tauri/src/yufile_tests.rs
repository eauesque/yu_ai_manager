use super::*;

#[test]
fn test_parse_range_basic() {
    assert_eq!(parse_range("bytes=0-499", 1000), Some((0, 499)));
}

#[test]
fn test_parse_range_open_ended() {
    assert_eq!(parse_range("bytes=500-", 1000), Some((500, 999)));
}

#[test]
fn test_parse_range_single_byte() {
    assert_eq!(parse_range("bytes=0-0", 1000), Some((0, 0)));
}

#[test]
fn test_parse_range_last_byte() {
    assert_eq!(parse_range("bytes=999-999", 1000), Some((999, 999)));
}

#[test]
fn test_parse_range_clamp_to_file_size() {
    assert_eq!(parse_range("bytes=0-9999", 1000), Some((0, 999)));
}

#[test]
fn test_parse_range_start_at_file_size_returns_none() {
    assert_eq!(parse_range("bytes=1000-1000", 1000), None);
}

#[test]
fn test_parse_range_start_beyond_file_size() {
    assert_eq!(parse_range("bytes=2000-3000", 1000), None);
}

#[test]
fn test_parse_range_start_greater_than_end() {
    assert_eq!(parse_range("bytes=500-100", 1000), None);
}

#[test]
fn test_parse_range_invalid_format_no_prefix() {
    assert_eq!(parse_range("0-499", 1000), None);
}

#[test]
fn test_parse_range_invalid_format_garbage() {
    assert_eq!(parse_range("bytes=abc-def", 1000), None);
}

#[test]
fn test_parse_range_empty_file() {
    assert_eq!(parse_range("bytes=0-0", 0), None);
}

#[test]
fn test_parse_range_large_file() {
    let size: u64 = 10 * 1024 * 1024 * 1024;
    assert_eq!(parse_range("bytes=0-8388607", size), Some((0, 8388607)));
}

#[test]
fn test_mime_video_types() {
    assert_eq!(mime_from_ext("mp4"), "video/mp4");
    assert_eq!(mime_from_ext("m4v"), "video/mp4");
    assert_eq!(mime_from_ext("webm"), "video/webm");
    assert_eq!(mime_from_ext("mov"), "video/quicktime");
    assert_eq!(mime_from_ext("mkv"), "video/x-matroska");
    assert_eq!(mime_from_ext("avi"), "video/x-msvideo");
    assert_eq!(mime_from_ext("ogv"), "video/ogg");
}

#[test]
fn test_mime_audio_types() {
    assert_eq!(mime_from_ext("mp3"), "audio/mpeg");
    assert_eq!(mime_from_ext("wav"), "audio/wav");
    assert_eq!(mime_from_ext("ogg"), "audio/ogg");
    assert_eq!(mime_from_ext("opus"), "audio/ogg");
    assert_eq!(mime_from_ext("m4a"), "audio/mp4");
    assert_eq!(mime_from_ext("aac"), "audio/mp4");
    assert_eq!(mime_from_ext("flac"), "audio/flac");
}

#[test]
fn test_mime_unknown_fallback() {
    assert_eq!(mime_from_ext("txt"), "application/octet-stream");
    assert_eq!(mime_from_ext("png"), "application/octet-stream");
    assert_eq!(mime_from_ext(""), "application/octet-stream");
    assert_eq!(mime_from_ext("xyz"), "application/octet-stream");
}

#[test]
fn test_yufile_request_nonexistent_file() {
    let uri = "yufile://localhost/C%3A%5Cnonexistent%5Cfile.mp4"
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[std::env::temp_dir()]);
    assert_eq!(response.status(), 404);
}

#[test]
fn test_yufile_request_empty_path() {
    let uri = "yufile://localhost/".parse::<tauri::http::Uri>().unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[]);
    let status = response.status();
    assert!(
        status == 400 || status == 404,
        "Empty path should be 400 or 404, got {}",
        status
    );
}

#[test]
fn test_yufile_request_real_file_full_read() {
    let dir = std::env::temp_dir().join("yu_tauri_test_yufile");
    let _ = std::fs::create_dir_all(&dir);
    let file_path = dir.join("test.mp4");
    let content = b"FAKE_MP4_CONTENT_FOR_TESTING_12345";
    std::fs::write(&file_path, content).unwrap();

    let path_str = file_path
        .to_string_lossy()
        .replace('\\', "%5C")
        .replace(':', "%3A");
    let uri = format!("yufile://localhost/{}", path_str)
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[dir.clone()]);

    assert_eq!(response.status(), 200);
    assert_eq!(response.body(), content);
    assert_eq!(
        response
            .headers()
            .get("Content-Type")
            .unwrap()
            .to_str()
            .unwrap(),
        "video/mp4"
    );
    assert_eq!(
        response
            .headers()
            .get("Content-Length")
            .unwrap()
            .to_str()
            .unwrap(),
        content.len().to_string()
    );

    let _ = std::fs::remove_file(&file_path);
    let _ = std::fs::remove_dir(&dir);
}

#[test]
fn test_yufile_request_range_partial() {
    let dir = std::env::temp_dir().join("yu_tauri_test_yufile_range");
    let _ = std::fs::create_dir_all(&dir);
    let file_path = dir.join("test_range.webm");
    let content: Vec<u8> = (0u8..=255).cycle().take(1000).collect();
    std::fs::write(&file_path, &content).unwrap();

    let path_str = file_path
        .to_string_lossy()
        .replace('\\', "%5C")
        .replace(':', "%3A");
    let uri = format!("yufile://localhost/{}", path_str)
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .header("range", "bytes=100-199")
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[dir.clone()]);

    assert_eq!(response.status(), 206);
    assert_eq!(response.body().len(), 100);
    assert_eq!(response.body(), &content[100..200]);
    assert_eq!(
        response
            .headers()
            .get("Content-Range")
            .unwrap()
            .to_str()
            .unwrap(),
        "bytes 100-199/1000"
    );

    let _ = std::fs::remove_file(&file_path);
    let _ = std::fs::remove_dir(&dir);
}

#[test]
fn test_yufile_request_range_open_ended() {
    let dir = std::env::temp_dir().join("yu_tauri_test_yufile_range2");
    let _ = std::fs::create_dir_all(&dir);
    let file_path = dir.join("test_range2.mp4");
    let content = vec![0xABu8; 500];
    std::fs::write(&file_path, &content).unwrap();

    let path_str = file_path
        .to_string_lossy()
        .replace('\\', "%5C")
        .replace(':', "%3A");
    let uri = format!("yufile://localhost/{}", path_str)
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .header("range", "bytes=400-")
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[dir.clone()]);

    assert_eq!(response.status(), 206);
    assert_eq!(response.body().len(), 100);

    let _ = std::fs::remove_file(&file_path);
    let _ = std::fs::remove_dir(&dir);
}

#[test]
fn test_yufile_rejects_large_full_and_invalid_range_requests() {
    let dir = std::env::temp_dir().join("yu_tauri_test_yufile_limits");
    let _ = std::fs::create_dir_all(&dir);
    let file_path = dir.join("large.mp4");
    std::fs::write(&file_path, vec![0u8; 8 * 1024 * 1024 + 1]).unwrap();
    let uri = format!("yufile://localhost/{}", file_path.to_string_lossy())
        .parse::<tauri::http::Uri>()
        .unwrap();
    let full = tauri::http::Request::builder()
        .uri(uri.clone())
        .body(Vec::new())
        .unwrap();
    assert_eq!(handle_yufile_request(full, &[dir.clone()]).status(), 413);
    let invalid = tauri::http::Request::builder()
        .uri(uri)
        .header("range", "bytes=bad")
        .body(Vec::new())
        .unwrap();
    assert_eq!(handle_yufile_request(invalid, &[dir.clone()]).status(), 416);
    let _ = std::fs::remove_dir_all(dir);
}

#[test]
fn test_is_allowed_media_ext() {
    assert!(is_allowed_media_ext("mp4"));
    assert!(is_allowed_media_ext("webm"));
    assert!(is_allowed_media_ext("flac"));
    assert!(is_allowed_media_ext("ogg"));
    assert!(!is_allowed_media_ext("txt"));
    assert!(!is_allowed_media_ext("py"));
    assert!(!is_allowed_media_ext("json"));
    assert!(!is_allowed_media_ext("db"));
    assert!(!is_allowed_media_ext("png"));
    assert!(!is_allowed_media_ext("html"));
    assert!(!is_allowed_media_ext("js"));
    assert!(!is_allowed_media_ext(""));
}

#[test]
fn test_yufile_rejects_non_media_file() {
    let dir = std::env::temp_dir().join("yu_tauri_test_yufile_sec");
    let _ = std::fs::create_dir_all(&dir);
    let file_path = dir.join("secret.txt");
    std::fs::write(&file_path, b"sensitive data").unwrap();

    let path_str = file_path
        .to_string_lossy()
        .replace('\\', "%5C")
        .replace(':', "%3A");
    let uri = format!("yufile://localhost/{}", path_str)
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[dir.clone()]);

    assert_eq!(response.status(), 403);
    let _ = std::fs::remove_file(&file_path);
    let _ = std::fs::remove_dir(&dir);
}

#[test]
fn test_yufile_rejects_directory() {
    let dir = std::env::temp_dir().join("yu_tauri_test_yufile_dir.mp4");
    let _ = std::fs::create_dir_all(&dir);

    let path_str = dir
        .to_string_lossy()
        .replace('\\', "%5C")
        .replace(':', "%3A");
    let uri = format!("yufile://localhost/{}", path_str)
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();
    let response = handle_yufile_request(request, &[]);

    assert_eq!(response.status(), 404);
    let _ = std::fs::remove_dir(&dir);
}

#[test]
fn test_yufile_rejects_canonical_path_outside_root() {
    let base = std::env::temp_dir().join("yu_tauri_test_yufile_outside");
    let allowed = base.join("allowed");
    let outside = base.join("outside.mp4");
    std::fs::create_dir_all(&allowed).unwrap();
    std::fs::write(&outside, b"video").unwrap();
    let uri = format!("yufile://localhost/{}", outside.to_string_lossy())
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();

    assert_eq!(handle_yufile_request(request, &[allowed]).status(), 403);
    let _ = std::fs::remove_dir_all(base);
}

#[cfg(unix)]
#[test]
fn test_yufile_rejects_symlink_from_root_to_outside() {
    use std::os::unix::fs::symlink;

    let base = std::env::temp_dir().join("yu_tauri_test_yufile_symlink");
    let allowed = base.join("allowed");
    let outside = base.join("outside.mp4");
    let link = allowed.join("link.mp4");
    std::fs::create_dir_all(&allowed).unwrap();
    std::fs::write(&outside, b"video").unwrap();
    symlink(&outside, &link).unwrap();
    let uri = format!("yufile://localhost/{}", link.to_string_lossy())
        .parse::<tauri::http::Uri>()
        .unwrap();
    let request = tauri::http::Request::builder()
        .uri(uri)
        .body(Vec::new())
        .unwrap();

    assert_eq!(handle_yufile_request(request, &[allowed]).status(), 403);
    let _ = std::fs::remove_dir_all(base);
}
