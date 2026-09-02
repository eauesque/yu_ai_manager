use std::fs::{self, File};
use std::io::{Read, Seek, SeekFrom};
use std::path::{Path, PathBuf};

use percent_encoding::percent_decode_str;

use super::{is_allowed_media_ext, mime_from_ext, parse_range};

const MAX_RESPONSE_BYTES: u64 = 8 * 1024 * 1024;

/// Handle a yufile:// request.
///
/// URL format: yufile://localhost/C%3A%5Cusers%5C...%5Cvideo.mp4
/// The path portion is percent-decoded and the file is read.
/// If a Range header is present, returns 206 Partial Content.
pub fn handle_yufile_request(
    request: tauri::http::Request<Vec<u8>>,
    allowed_roots: &[PathBuf],
) -> tauri::http::Response<Vec<u8>> {
    let url = request.uri().to_string();
    let path_encoded = url
        .strip_prefix("yufile://localhost/")
        .or_else(|| url.strip_prefix("yufile://localhost"))
        .unwrap_or("");

    let decoded = percent_decode_str(path_encoded)
        .decode_utf8_lossy()
        .to_string();

    if decoded.is_empty() {
        return tauri::http::Response::builder()
            .status(400)
            .body(b"Bad Request: empty path".to_vec())
            .unwrap();
    }

    let file_path = PathBuf::from(&decoded);
    let file_path = match fs::canonicalize(&file_path) {
        Ok(path) => path,
        Err(_) => {
            return tauri::http::Response::builder()
                .status(404)
                .body(b"Not Found".to_vec())
                .unwrap();
        }
    };
    if !allowed_roots.iter().any(|root| file_path.starts_with(root)) {
        return tauri::http::Response::builder()
            .status(403)
            .body(b"Forbidden: path is outside configured scan roots".to_vec())
            .unwrap();
    }

    let ext = file_path
        .extension()
        .and_then(|value| value.to_str())
        .unwrap_or("")
        .to_lowercase();
    if !is_allowed_media_ext(&ext) {
        return tauri::http::Response::builder()
            .status(403)
            .body(b"Forbidden: only media files are allowed".to_vec())
            .unwrap();
    }

    let metadata = match fs::metadata(&file_path) {
        Ok(meta) if meta.is_file() => meta,
        _ => {
            return tauri::http::Response::builder()
                .status(404)
                .body(b"Not Found".to_vec())
                .unwrap();
        }
    };

    let file_size = metadata.len();
    let mime = mime_from_ext(&ext);
    let range_header = request
        .headers()
        .get("range")
        .and_then(|value| value.to_str().ok())
        .map(|value| value.to_string());

    if let Some(ref range_str) = range_header {
        if let Some((start, end)) = parse_range(range_str, file_size) {
            let length = end - start + 1;
            let read_len = length.min(MAX_RESPONSE_BYTES) as usize;

            let mut file = match File::open(&file_path) {
                Ok(file) => file,
                Err(_) => {
                    return tauri::http::Response::builder()
                        .status(500)
                        .body(b"Failed to open file".to_vec())
                        .unwrap();
                }
            };

            if file.seek(SeekFrom::Start(start)).is_err() {
                return tauri::http::Response::builder()
                    .status(500)
                    .body(b"Seek failed".to_vec())
                    .unwrap();
            }

            let mut buf = vec![0u8; read_len];
            let bytes_read = match file.read(&mut buf) {
                Ok(size) => size,
                Err(_) => {
                    return tauri::http::Response::builder()
                        .status(500)
                        .body(b"Read failed".to_vec())
                        .unwrap();
                }
            };
            buf.truncate(bytes_read);

            let range_end = start + bytes_read as u64 - 1;
            return tauri::http::Response::builder()
                .status(206)
                .header("Content-Type", mime)
                .header("Content-Length", bytes_read.to_string())
                .header(
                    "Content-Range",
                    format!("bytes {}-{}/{}", start, range_end, file_size),
                )
                .header("Accept-Ranges", "bytes")
                .body(buf)
                .unwrap();
        }
        return tauri::http::Response::builder()
            .status(416)
            .header("Content-Range", format!("bytes */{file_size}"))
            .body(b"Range Not Satisfiable".to_vec())
            .unwrap();
    }

    if file_size > MAX_RESPONSE_BYTES {
        return tauri::http::Response::builder()
            .status(413)
            .body(b"Payload Too Large: use Range requests".to_vec())
            .unwrap();
    }

    let data = match fs::read(&file_path) {
        Ok(data) => data,
        Err(_) => {
            return tauri::http::Response::builder()
                .status(500)
                .body(b"Failed to read file".to_vec())
                .unwrap();
        }
    };

    tauri::http::Response::builder()
        .status(200)
        .header("Content-Type", mime)
        .header("Content-Length", data.len().to_string())
        .header("Accept-Ranges", "bytes")
        .body(data)
        .unwrap()
}
