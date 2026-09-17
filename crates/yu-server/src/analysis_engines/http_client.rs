use std::{
    net::{SocketAddr, ToSocketAddrs},
    path::Path,
    time::Duration,
};

use futures_util::StreamExt;

use crate::{
    analysis_engines::EngineError,
    routes::analysis_net::{is_blocked_hostname_literal, is_blocked_ip},
};

const MAX_IMAGE_FILE_BYTES: u64 = 25 * 1024 * 1024;
const MAX_IMAGE_PIXELS: u64 = 40_000_000;

/// Builds a redirect-free client pinned to the validated DNS result.
///
/// DNS is resolved exactly ONCE here, and the single resulting IP is both
/// validated and pinned. Resolving twice (once to validate, again to pin,
/// as an earlier version of this function did via `is_blocked_address`)
/// leaves a DNS-rebinding TOCTOU gap: an attacker-controlled DNS server can
/// answer the validation query with a public IP and the connect query with
/// `127.0.0.1`/`169.254.169.254`/etc, bypassing the SSRF gate entirely.
pub async fn build_pinned_client(
    base_url: &str,
    allow_local: bool,
    timeout: Duration,
) -> Result<reqwest::Client, EngineError> {
    let parsed = reqwest::Url::parse(base_url)
        .map_err(|error| EngineError::msg(format!("Invalid URL: {error}")))?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err(EngineError::msg("Only http/https URLs are allowed"));
    }
    let host = parsed
        .host_str()
        .ok_or_else(|| EngineError::msg("URL missing host"))?
        .to_string();
    let port = parsed
        .port_or_known_default()
        .ok_or_else(|| EngineError::msg("URL missing port"))?;
    if is_blocked_hostname_literal(&host) {
        return Err(EngineError::msg(format!("Blocked address: {host}")));
    }
    let resolved = tokio::task::spawn_blocking({
        let host = host.clone();
        move || (host.as_str(), port).to_socket_addrs()
    })
    .await
    .map_err(|error| EngineError::msg(format!("DNS resolution task failed: {error}")))?
    .map_err(|error| EngineError::msg(format!("DNS resolution failed for {host}: {error}")))?
    .next()
    .ok_or_else(|| EngineError::msg(format!("No addresses resolved for {host}")))?;
    let ip = resolved.ip();
    if is_blocked_ip(ip, allow_local) {
        return Err(EngineError::msg(format!(
            "Blocked address: {host} resolves to {ip}"
        )));
    }
    reqwest::Client::builder()
        .timeout(timeout)
        .redirect(reqwest::redirect::Policy::none())
        .resolve(&host, SocketAddr::new(ip, port))
        .build()
        .map_err(|error| EngineError::msg(format!("Failed to build HTTP client: {error}")))
}

/// Reads a response incrementally and rejects it instead of truncating at the cap.
pub async fn read_response_capped(
    resp: reqwest::Response,
    max_bytes: usize,
) -> Result<String, EngineError> {
    let mut body = Vec::new();
    let mut stream = resp.bytes_stream();
    while let Some(chunk) = stream.next().await {
        let chunk = chunk
            .map_err(|error| EngineError::msg(format!("Failed to read response body: {error}")))?;
        if body.len().saturating_add(chunk.len()) > max_bytes {
            return Err(EngineError::msg("response_too_large"));
        }
        body.extend_from_slice(&chunk);
    }
    Ok(String::from_utf8_lossy(&body).into_owned())
}

/// Checks encoded and decoded image limits before any pixel buffer is allocated.
pub fn check_image_size_limits(
    image_path: &Path,
) -> Result<image::ImageReader<std::io::BufReader<std::fs::File>>, EngineError> {
    let metadata = std::fs::metadata(image_path)
        .map_err(|error| EngineError::msg(format!("Failed to stat image file: {error}")))?;
    if metadata.len() > MAX_IMAGE_FILE_BYTES {
        return Err(EngineError::msg("image_too_large"));
    }
    let reader = image::ImageReader::open(image_path)
        .map_err(|error| EngineError::msg(format!("Failed to open image: {error}")))?
        .with_guessed_format()
        .map_err(|error| EngineError::msg(format!("Failed to read image header: {error}")))?;
    let (width, height) = reader
        .into_dimensions()
        .map_err(|error| EngineError::msg(format!("Failed to read image dimensions: {error}")))?;
    if u64::from(width) * u64::from(height) > MAX_IMAGE_PIXELS {
        return Err(EngineError::msg("image_too_large"));
    }
    image::ImageReader::open(image_path)
        .map_err(|error| EngineError::msg(format!("Failed to reopen image: {error}")))?
        .with_guessed_format()
        .map_err(|error| EngineError::msg(format!("Failed to read image header: {error}")))
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{routing::get, Router};

    #[tokio::test]
    async fn blocks_loopback_and_metadata_when_local_is_disallowed() {
        assert!(
            build_pinned_client("http://127.0.0.1:11434", false, Duration::from_secs(1))
                .await
                .is_err()
        );
        assert!(
            build_pinned_client("http://169.254.169.254", false, Duration::from_secs(1))
                .await
                .is_err()
        );
    }

    #[tokio::test]
    async fn allows_loopback_when_explicitly_allowed() {
        assert!(
            build_pinned_client("http://127.0.0.1:11434", true, Duration::from_secs(1))
                .await
                .is_ok()
        );
    }

    #[tokio::test]
    async fn rejects_response_larger_than_cap() {
        let Ok(listener) = tokio::net::TcpListener::bind("127.0.0.1:0").await else {
            // Restricted CI sandboxes may prohibit loopback listeners.
            return;
        };
        let address = listener.local_addr().unwrap();
        let server = tokio::spawn(async move {
            axum::serve(
                listener,
                Router::new().route("/", get(|| async { "a".repeat(200) })),
            )
            .await
            .unwrap()
        });
        let response = reqwest::get(format!("http://{address}")).await.unwrap();
        assert!(
            matches!(read_response_capped(response, 100).await, Err(EngineError::Message(message)) if message == "response_too_large")
        );
        server.abort();
    }
}
