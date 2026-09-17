use std::{
    path::Path,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use lan_cowork::{
    auth::peer_transport::{sign_peer_headers, PeerHeaderSigningInput},
    routes::{lan_cowork_client::build_peer_client, lan_cowork_discovery::load_identity_seed},
};
use reqwest::header::{HeaderMap, HeaderValue};
use serde_json::Value;
use sqlx::SqlitePool;

const BOUNDARY: &str = "----YuAiMeshInferenceBoundary";
const PATH: &str = "/ext/lan_cowork/api/peer/infer/tag";
const IMAGE_EXTS: &[&str] = &[
    ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp", ".tiff", ".tif", ".heif", ".heic",
    ".jxl",
];

#[derive(Debug, Clone)]
pub struct TaggerPeer {
    pub peer_id: String,
    // Used by the stage-2 coordinator for the `mesh:{name}` tag source.
    pub name: String,
    pub api_host: String,
    pub api_port: u16,
    pub token: String,
}

#[derive(Debug, PartialEq)]
pub enum TaggerClientError {
    UnsupportedImage,
    ReadImage,
    MissingIdentity,
    Signing,
    Transport,
    RejectedResponse,
    InvalidTags,
    InvalidResponse,
}

pub async fn tag_remote_image(
    db: &SqlitePool,
    peer: &TaggerPeer,
    image_path: &Path,
) -> Result<Vec<Value>, TaggerClientError> {
    let ext = image_extension(image_path).ok_or(TaggerClientError::UnsupportedImage)?;
    let image = tokio::fs::read(image_path)
        .await
        .map_err(|_| TaggerClientError::ReadImage)?;
    let filename = image_path
        .file_name()
        .and_then(|value| value.to_str())
        .ok_or(TaggerClientError::ReadImage)?;
    let mime = image_mime(&ext);
    let body = multipart_body(filename, mime, &image);
    let seed = load_identity_seed(db)
        .await
        .ok_or(TaggerClientError::MissingIdentity)?;
    let ts = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map_err(|_| TaggerClientError::Signing)?
        .as_secs() as i64;
    let headers = request_headers(&seed, peer, &body, ts)?;
    let (client, base) = build_peer_client(
        &peer.api_host,
        peer.api_port,
        Some(Duration::from_secs(60)),
        Some(Duration::from_secs(60)),
    )
    .await
    .map_err(|_| TaggerClientError::Transport)?;
    let response = client
        .post(format!("{base}{PATH}"))
        .headers(headers)
        .body(body)
        .send()
        .await
        .map_err(|_| TaggerClientError::Transport)?;
    parse_tags(
        response
            .json()
            .await
            .map_err(|_| TaggerClientError::InvalidResponse)?,
    )
}

fn image_extension(path: &Path) -> Option<String> {
    let ext = format!(".{}", path.extension()?.to_str()?.to_ascii_lowercase());
    IMAGE_EXTS.contains(&ext.as_str()).then_some(ext)
}

fn image_mime(ext: &str) -> &'static str {
    match ext {
        ".png" => "image/png",
        ".webp" => "image/webp",
        ".gif" => "image/gif",
        ".bmp" => "image/bmp",
        ".avif" => "image/avif",
        ".tiff" | ".tif" => "image/tiff",
        ".heif" => "image/heif",
        ".heic" => "image/heic",
        ".jxl" => "image/jxl",
        _ => "image/jpeg",
    }
}

fn request_headers(
    seed: &[u8],
    peer: &TaggerPeer,
    body: &[u8],
    ts: i64,
) -> Result<HeaderMap, TaggerClientError> {
    let mut headers = sign_peer_headers(PeerHeaderSigningInput {
        seed,
        method: "POST",
        path: PATH,
        query: "",
        body,
        ts,
        nonce: "",
        peer_id: &peer.peer_id,
    })
    .ok_or(TaggerClientError::Signing)?;
    headers.insert(
        "Content-Type",
        format!("multipart/form-data; boundary={BOUNDARY}")
            .parse()
            .map_err(|_| TaggerClientError::Signing)?,
    );
    headers.insert("Accept", HeaderValue::from_static("application/json"));
    headers.insert(
        "User-Agent",
        HeaderValue::from_static("YuAiManager/1.0 MeshInferenceClient"),
    );
    headers.insert(
        "X-Requested-With",
        HeaderValue::from_static("MeshInference"),
    );
    if !peer.token.is_empty() {
        headers.insert(
            "Authorization",
            format!("Bearer {}", peer.token)
                .parse()
                .map_err(|_| TaggerClientError::Signing)?,
        );
    }
    Ok(headers)
}

fn parse_tags(value: Value) -> Result<Vec<Value>, TaggerClientError> {
    let object = value
        .as_object()
        .ok_or(TaggerClientError::InvalidResponse)?;
    if object.get("ok") != Some(&Value::Bool(true)) {
        return Err(TaggerClientError::RejectedResponse);
    }
    object
        .get("tags")
        .and_then(Value::as_array)
        .cloned()
        .ok_or(TaggerClientError::InvalidTags)
}

fn multipart_body(filename: &str, mime: &str, image: &[u8]) -> Vec<u8> {
    let mut body = format!("--{BOUNDARY}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{filename}\"\r\nContent-Type: {mime}\r\n\r\n").into_bytes();
    body.extend_from_slice(image);
    body.extend_from_slice(format!("\r\n--{BOUNDARY}--\r\n").as_bytes());
    body
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn peer(token: &str) -> TaggerPeer {
        TaggerPeer {
            peer_id: "peer-id".into(),
            name: "peer".into(),
            api_host: "127.0.0.1".into(),
            api_port: 8000,
            token: token.into(),
        }
    }

    #[test]
    fn multipart_body_matches_literal_wire_framing() {
        let image = b"\x00image\xff";
        let expected = [
            b"------YuAiMeshInferenceBoundary\r\nContent-Disposition: form-data; name=\"image\"; filename=\"a.png\"\r\nContent-Type: image/png\r\n\r\n".as_slice(),
            image,
            b"\r\n------YuAiMeshInferenceBoundary--\r\n",
        ].concat();
        assert_eq!(multipart_body("a.png", "image/png", image), expected);
    }

    #[test]
    fn image_extension_accepts_all_configured_extensions_case_insensitively() {
        let expected = [
            ".png", ".jpg", ".jpeg", ".webp", ".gif", ".avif", ".bmp", ".tiff", ".tif", ".heif",
            ".heic", ".jxl",
        ];
        assert_eq!(IMAGE_EXTS.len(), expected.len());
        for ext in expected {
            assert_eq!(
                image_extension(Path::new(&format!("a{ext}"))).as_deref(),
                Some(ext)
            );
            assert_eq!(
                image_extension(Path::new(&format!("a{}", ext.to_ascii_uppercase()))).as_deref(),
                Some(ext)
            );
        }
        assert_eq!(image_extension(Path::new("a.txt")), None);
        assert_eq!(image_extension(Path::new("a")), None);
    }

    #[test]
    fn image_mime_matches_worker_transport_map() {
        for (ext, mime) in [
            (".png", "image/png"),
            (".webp", "image/webp"),
            (".gif", "image/gif"),
            (".bmp", "image/bmp"),
            (".avif", "image/avif"),
            (".tiff", "image/tiff"),
            (".tif", "image/tiff"),
            (".heif", "image/heif"),
            (".heic", "image/heic"),
            (".jxl", "image/jxl"),
            (".jpg", "image/jpeg"),
            (".jpeg", "image/jpeg"),
        ] {
            assert_eq!(image_mime(ext), mime);
        }
    }

    #[test]
    fn request_headers_use_prefixed_path_and_required_headers() {
        assert_eq!(PATH, "/ext/lan_cowork/api/peer/infer/tag");
        let headers = request_headers(&[7; 32], &peer("token"), b"body", 1).unwrap();
        assert!(!headers.contains_key("X-Peer-Nonce"));
        assert_eq!(headers["Authorization"], "Bearer token");
        assert_eq!(headers["Accept"], "application/json");
        assert_eq!(headers["User-Agent"], "YuAiManager/1.0 MeshInferenceClient");
        assert_eq!(headers["X-Requested-With"], "MeshInference");
        assert_eq!(
            headers["Content-Type"],
            "multipart/form-data; boundary=----YuAiMeshInferenceBoundary"
        );
    }

    #[test]
    fn request_headers_omit_empty_authorization() {
        assert!(!request_headers(&[7; 32], &peer(""), b"body", 1)
            .unwrap()
            .contains_key("Authorization"));
    }

    #[test]
    fn parse_tags_maps_valid_and_invalid_responses() {
        assert_eq!(parse_tags(json!({"ok": true, "tags": []})), Ok(vec![]));
        assert_eq!(
            parse_tags(json!({"ok": false})),
            Err(TaggerClientError::RejectedResponse)
        );
        assert_eq!(
            parse_tags(json!({"ok": true, "tags": "x"})),
            Err(TaggerClientError::InvalidTags)
        );
        assert_eq!(
            parse_tags(json!([])),
            Err(TaggerClientError::InvalidResponse)
        );
        assert_eq!(
            parse_tags(json!("x")),
            Err(TaggerClientError::InvalidResponse)
        );
    }
}
