use std::path::{Path, PathBuf};
use std::time::{Duration, SystemTime, UNIX_EPOCH};

use axum::{
    extract::{Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};
use tokio_util::sync::CancellationToken;

use crate::config_io::{load as load_config_json, write as write_config_json};
use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn hailo_config(config: &Value) -> Value {
    let ht = config.get("hailo_tagger").and_then(Value::as_object);
    json!({
        "enabled": ht
            .and_then(|ht| ht.get("enabled"))
            .and_then(Value::as_bool)
            .unwrap_or(false),
        "endpoint_url": ht
            .and_then(|ht| ht.get("endpoint_url"))
            .and_then(Value::as_str)
            .unwrap_or(""),
        "threshold": ht
            .and_then(|ht| ht.get("threshold"))
            .and_then(Value::as_f64)
            .unwrap_or(0.35),
        "timeout": ht
            .and_then(|ht| ht.get("timeout"))
            .and_then(Value::as_i64)
            .unwrap_or(30),
    })
}

/// The configured request timeout, in seconds.
///
/// A negative `timeout` used to reach `as u64` and wrap to ~584 billion years
/// -- which is to say, no timeout at all.
fn resolve_timeout_secs(cfg: &Value) -> u64 {
    cfg.get("timeout")
        .and_then(Value::as_i64)
        .and_then(|seconds| u64::try_from(seconds).ok())
        .unwrap_or(30)
}

pub async fn config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = load_config_json(&state.config.config_path);
    api_result(json!({"config": hailo_config(&config)}))
}

fn invalid_value(message: String) -> Response {
    (
        StatusCode::BAD_REQUEST,
        Json(json!({"ok": false, "error": message, "code": "invalid_value", "data": null})),
    )
        .into_response()
}

const HAILO_BLOCKED_HOSTNAMES: &[&str] = &["metadata.google.internal", "metadata.goog"];

/// A domain host resolves to a validated address that must be pinned for the
/// actual connection; an IP-literal host needs no pinning since reqwest
/// never re-resolves it. Mirrors `HostCheck` in `tools_ops.rs`.
enum HailoHostCheck {
    IpLiteralOk,
    Pin(String, std::net::SocketAddr),
}

/// Unlike the shared `validate_openai_compat_url` (which gates loopback and
/// private ranges together behind one `allow_local` flag), the Hailo Tagger
/// inherently targets a LAN device (e.g. a Raspberry Pi on 192.168.x.x):
/// private ranges must be allowed, but loopback/link-local/unspecified
/// targets must still be blocked, since those would let this feature be
/// used to probe or hit the server's own local services (SSRF).
fn is_hailo_blocked_ip(ip: std::net::IpAddr) -> bool {
    use std::net::IpAddr;
    // Normalize IPv4-mapped IPv6 (e.g. ::ffff:127.0.0.1) to plain IPv4 first
    // — otherwise the checks below can be bypassed entirely.
    let ip = match ip {
        IpAddr::V6(v6) => v6
            .to_ipv4_mapped()
            .map(IpAddr::V4)
            .unwrap_or(IpAddr::V6(v6)),
        other => other,
    };
    if ip.is_unspecified() || ip.is_loopback() {
        return true;
    }
    if let IpAddr::V4(v4) = ip {
        let [a, b, ..] = v4.octets();
        if a == 169 && b == 254 {
            return true;
        }
    }
    if let IpAddr::V6(v6) = ip {
        // fe80::/10
        if (v6.segments()[0] & 0xffc0) == 0xfe80 {
            return true;
        }
    }
    // Private LAN ranges (e.g. 192.168.x.x, 10.x.x.x) are intentionally
    // allowed — that's the documented, intended use case.
    false
}

/// Validate the Hailo Remote Tagger endpoint URL and, for domain hosts,
/// return the exact address the real connection must be pinned to.
///
/// Resolving here and then letting reqwest re-resolve the same hostname at
/// connect time would be DNS-rebinding-bypassable: an attacker's DNS server
/// can answer with a public IP for this check, then answer with a
/// loopback/private IP moments later when reqwest itself resolves the host
/// to actually connect. Instead, resolve exactly once here, validate that
/// address, and have the caller pin the connection to it via
/// `ClientBuilder::resolve()` (see `apply_hailo_host_check`) so no second,
/// unvalidated DNS lookup ever happens for this request. Callers must also
/// disable redirects (`redirect::Policy::none()`): otherwise a
/// malicious/compromised Hailo server could redirect a validated request to
/// a blocked local address after the fact.
async fn resolve_hailo_endpoint(url: &str) -> Result<HailoHostCheck, String> {
    let parsed = reqwest::Url::parse(url).map_err(|_| "Invalid URL".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("Only http/https URLs are allowed".to_string());
    }
    // `host()` gives IP literals directly (as `Host::Ipv4`/`Host::Ipv6`),
    // which is required here: `host_str()` renders IPv6 literals bracketed
    // (e.g. "[::ffff:127.0.0.1]"), which does not round-trip through DNS
    // resolution as an IP literal.
    let Some(host) = parsed.host() else {
        return Err("No hostname specified".to_string());
    };
    let hostname = parsed.host_str().unwrap_or_default();
    if hostname.is_empty() {
        return Err("No hostname specified".to_string());
    }
    if HAILO_BLOCKED_HOSTNAMES
        .iter()
        .any(|blocked| hostname.eq_ignore_ascii_case(blocked))
    {
        return Err("Blocked address".to_string());
    }
    match host {
        url::Host::Ipv4(v4) => {
            if is_hailo_blocked_ip(std::net::IpAddr::V4(v4)) {
                return Err("Blocked address".to_string());
            }
            Ok(HailoHostCheck::IpLiteralOk)
        }
        url::Host::Ipv6(v6) => {
            if is_hailo_blocked_ip(std::net::IpAddr::V6(v6)) {
                return Err("Blocked address".to_string());
            }
            Ok(HailoHostCheck::IpLiteralOk)
        }
        url::Host::Domain(domain) => {
            let port = parsed.port_or_known_default().unwrap_or(80);
            let addrs: Vec<std::net::SocketAddr> =
                match tokio::net::lookup_host((domain, port)).await {
                    Ok(iter) => iter.collect(),
                    // Unresolvable hostname: let the later connection attempt fail
                    // instead of blocking here (matches the shared validator's behavior).
                    Err(_) => return Ok(HailoHostCheck::IpLiteralOk),
                };
            let Some(&first) = addrs.first() else {
                return Ok(HailoHostCheck::IpLiteralOk);
            };
            // A hostname can resolve to multiple A/AAAA records; reject if
            // *any* of them is blocked rather than only the one we happen to
            // pin to below — otherwise an attacker could mix one allowed and
            // one blocked answer.
            for addr in &addrs {
                if is_hailo_blocked_ip(addr.ip()) {
                    return Err("Blocked address".to_string());
                }
            }
            Ok(HailoHostCheck::Pin(domain.to_string(), first))
        }
    }
}

/// Applies the result of `resolve_hailo_endpoint` to a `ClientBuilder`,
/// pinning the connection to the exact validated address for domain hosts.
fn apply_hailo_host_check(
    builder: reqwest::ClientBuilder,
    check: HailoHostCheck,
) -> reqwest::ClientBuilder {
    match check {
        HailoHostCheck::IpLiteralOk => builder,
        HailoHostCheck::Pin(host, addr) => builder.resolve(&host, addr),
    }
}

pub async fn config_update(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<Value>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(Json(Value::Object(data))) = body else {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "JSON object required", "code": "invalid_json", "data": null})),
        )
            .into_response();
    };

    if let Some(value) = data.get("enabled") {
        if !value.is_boolean() {
            return invalid_value("enabled must be a boolean".to_string());
        }
    }
    if let Some(value) = data.get("endpoint_url") {
        let Some(url) = value.as_str() else {
            return invalid_value("endpoint_url must be a string".to_string());
        };
        if let Err(error) = resolve_hailo_endpoint(url.trim()).await {
            return invalid_value(format!("endpoint_url: {error}"));
        }
    }
    if let Some(value) = data.get("threshold") {
        let Some(threshold) = value.as_f64() else {
            return invalid_value("threshold must be a number between 0.0 and 1.0".to_string());
        };
        if !(0.0..=1.0).contains(&threshold) {
            return invalid_value("threshold must be a number between 0.0 and 1.0".to_string());
        }
    }
    if let Some(value) = data.get("timeout") {
        let Some(timeout) = value.as_i64() else {
            return invalid_value("timeout must be an integer between 1 and 300".to_string());
        };
        if !(1..=300).contains(&timeout) {
            return invalid_value("timeout must be an integer between 1 and 300".to_string());
        }
    }

    let mut config = load_config_json(&state.config.config_path);
    let root = config
        .as_object_mut()
        .expect("load_config_json returns an object");
    let ht = root
        .entry("hailo_tagger".to_string())
        .or_insert_with(|| json!({}));
    let ht = ht
        .as_object_mut()
        .expect("hailo_tagger section is an object");
    if let Some(value) = data.get("enabled") {
        ht.insert("enabled".to_string(), value.clone());
    }
    if let Some(value) = data.get("endpoint_url") {
        ht.insert(
            "endpoint_url".to_string(),
            json!(value.as_str().unwrap_or("").trim()),
        );
    }
    if let Some(value) = data.get("threshold") {
        let rounded = (value.as_f64().unwrap_or(0.35) * 100.0).round() / 100.0;
        ht.insert("threshold".to_string(), json!(rounded));
    }
    if let Some(value) = data.get("timeout") {
        ht.insert("timeout".to_string(), json!(value.as_i64().unwrap_or(30)));
    }
    let saved = Value::Object(ht.clone());

    if let Err(error) = write_config_json(&state.config.config_path, &config) {
        return internal_error(error, "failed to save Hailo Tagger config");
    }

    api_result(json!({"config": saved}))
}

pub async fn status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let cfg = hailo_config(&load_config_json(&state.config.config_path));
    let enabled = cfg.get("enabled").and_then(Value::as_bool).unwrap_or(false);
    let url = cfg
        .get("endpoint_url")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if !enabled || url.is_empty() {
        return api_result(
            json!({"enabled": enabled, "reachable": false, "reason": "not_configured"}),
        );
    }
    // Re-resolve and re-validate at request time (not just at config-save
    // time): the endpoint_url is persisted config, and a DNS answer that was
    // safe when it was saved can change by the time this check runs.
    let host_check = match resolve_hailo_endpoint(&url).await {
        Ok(check) => check,
        Err(reason) => {
            return api_result(
                json!({"enabled": true, "reachable": false, "reason": reason, "endpoint_url": url}),
            );
        }
    };
    let client = match apply_hailo_host_check(
        reqwest::Client::builder()
            .timeout(Duration::from_secs(5))
            .redirect(reqwest::redirect::Policy::none())
            // A system/env proxy would resolve and connect to the target
            // itself, bypassing the pinned address entirely.
            .no_proxy(),
        host_check,
    )
    .build()
    {
        Ok(client) => client,
        Err(error) => {
            return api_result(
                json!({"enabled": true, "reachable": false, "reason": error.to_string(), "endpoint_url": url}),
            );
        }
    };
    let health_url = format!("{}/health", url.trim_end_matches('/'));
    match client
        .get(health_url)
        .header(reqwest::header::USER_AGENT, "YU-AI-Manager/1.0")
        .send()
        .await
    {
        Ok(response) if response.status().is_success() => {
            api_result(json!({"enabled": true, "reachable": true, "endpoint_url": url}))
        }
        Ok(response) => api_result(json!({
            "enabled": true,
            "reachable": false,
            // reqwest does not expose urllib's exact exception string.
            "reason": format!("HTTP {}", response.status().as_u16()),
            "endpoint_url": url,
        })),
        Err(error) => api_result(json!({
            "enabled": true,
            "reachable": false,
            "reason": error.to_string(),
            "endpoint_url": url,
        })),
    }
}

async fn get_hailo_tags(pool: &SqlitePool, file_id: i64) -> Result<Value, sqlx::Error> {
    let rows = match sqlx::query(
        "SELECT tag_name, confidence, source, created_at
         FROM file_hailo_tags WHERE file_id = ?
         ORDER BY confidence DESC, tag_name ASC",
    )
    .bind(file_id)
    .fetch_all(pool)
    .await
    {
        Ok(rows) => rows,
        Err(error) if error.to_string().contains("no such table: file_hailo_tags") => {
            // Some deployments have not run the optional Hailo table migration yet;
            // returning an empty list keeps read routes harmless until first write.
            Vec::new()
        }
        Err(error) => return Err(error),
    };
    Ok(json!(rows
        .into_iter()
        .map(|row| {
            json!({
                "tag_name": row.get::<String, _>("tag_name"),
                "confidence": row.get::<f64, _>("confidence"),
                "source": row.get::<String, _>("source"),
                "created_at": row.get::<i64, _>("created_at"),
            })
        })
        .collect::<Vec<_>>()))
}

pub async fn tags(State(state): State<SharedState>, AxumPath(file_id): AxumPath<i64>) -> Response {
    match get_hailo_tags(&state.db_read, file_id).await {
        Ok(tags) => api_result(json!({"file_id": file_id, "tags": tags})),
        Err(error) => internal_error(error, "failed to get Hailo tags"),
    }
}

pub async fn tags_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    match sqlx::query("DELETE FROM file_hailo_tags WHERE file_id = ?")
        .bind(file_id)
        .execute(&state.db)
        .await
    {
        Ok(r) => api_result(json!({"file_id": file_id, "deleted": r.rows_affected()})),
        Err(error) => internal_error(error, "failed to delete Hailo tags"),
    }
}

fn is_taggable_ext(ext: &str) -> bool {
    matches!(
        ext,
        ".png"
            | ".jpg"
            | ".jpeg"
            | ".webp"
            | ".gif"
            | ".avif"
            | ".bmp"
            | ".tiff"
            | ".tif"
            | ".heif"
            | ".heic"
            | ".jxl"
            | ".svg"
            | ".webm"
            | ".mp4"
            | ".avi"
            | ".mov"
            | ".mkv"
            | ".m4v"
            | ".ogv"
    )
}

fn mime_for_ext(ext: &str) -> &'static str {
    match ext {
        ".png" => "image/png",
        ".webp" => "image/webp",
        ".gif" => "image/gif",
        ".bmp" => "image/bmp",
        ".svg" => "image/svg+xml",
        ".webm" => "video/webm",
        ".mp4" => "video/mp4",
        _ => "image/jpeg",
    }
}

async fn call_hailo_endpoint(
    filepath: &str,
    endpoint_url: &str,
    timeout_secs: u64,
) -> Result<Vec<Value>, String> {
    let image_bytes = tokio::fs::read(filepath)
        .await
        .map_err(|e| format!("Failed to read file: {e}"))?;

    let ext = Path::new(filepath)
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| format!(".{}", s.to_lowercase()))
        .unwrap_or_default();

    let boundary = "----HailoTaggerBoundary";
    let header = format!(
        "--{boundary}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"image{ext}\"\r\nContent-Type: {mime}\r\n\r\n",
        mime = mime_for_ext(&ext),
    );
    let mut body: Vec<u8> = header.into_bytes();
    body.extend_from_slice(&image_bytes);
    body.extend_from_slice(format!("\r\n--{boundary}--\r\n").as_bytes());

    // Re-resolve and re-validate at request time (not just at config-save
    // time): the endpoint_url is persisted config, and a DNS answer that was
    // safe when it was saved can change by the time this request fires.
    let host_check = resolve_hailo_endpoint(endpoint_url)
        .await
        .map_err(|e| format!("endpoint_url: {e}"))?;
    let url = format!("{}/tag", endpoint_url.trim_end_matches('/'));
    let client = apply_hailo_host_check(
        reqwest::Client::builder()
            .timeout(Duration::from_secs(timeout_secs))
            .redirect(reqwest::redirect::Policy::none())
            // A system/env proxy would resolve and connect to the target
            // itself, bypassing the pinned address entirely.
            .no_proxy(),
        host_check,
    )
    .build()
    .map_err(|e| e.to_string())?;

    let resp = client
        .post(&url)
        .header(
            "Content-Type",
            format!("multipart/form-data; boundary={boundary}"),
        )
        .header("Accept", "application/json")
        .header("User-Agent", "YU-AI-Manager/1.0")
        .body(body)
        .send()
        .await
        .map_err(|e| format!("Hailo tagger request failed: {e}"))?;

    let data: Value = resp
        .json()
        .await
        .map_err(|e| format!("Failed to parse Hailo response: {e}"))?;

    Ok(data
        .get("tags")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default())
}

/// Shared single-file tagging logic used by both `tag_file` and the batch worker.
async fn tag_one(
    db_read: &SqlitePool,
    db: &SqlitePool,
    cfg: &Value,
    file_id: i64,
    force: bool,
) -> Value {
    let enabled = cfg.get("enabled").and_then(Value::as_bool).unwrap_or(false);
    if !enabled {
        return json!({"error": "Hailo Remote Tagger is disabled", "code": "disabled"});
    }
    let endpoint_url = cfg
        .get("endpoint_url")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if endpoint_url.is_empty() {
        return json!({"error": "Hailo endpoint URL not configured", "code": "not_configured"});
    }
    let threshold = cfg.get("threshold").and_then(Value::as_f64).unwrap_or(0.35);
    let timeout = resolve_timeout_secs(cfg);

    let row = match sqlx::query("SELECT id, path FROM files WHERE id = ? AND is_deleted = 0")
        .bind(file_id)
        .fetch_optional(db_read)
        .await
    {
        Ok(Some(r)) => r,
        Ok(None) => return json!({"error": "File not found or deleted", "code": "file_not_found"}),
        Err(e) => return json!({"error": e.to_string(), "code": "db_error"}),
    };
    let filepath: String = row.get("path");

    let ext = Path::new(&filepath)
        .extension()
        .and_then(|s| s.to_str())
        .map(|s| format!(".{}", s.to_lowercase()))
        .unwrap_or_default();
    if !is_taggable_ext(&ext) {
        return json!({"error": "File type not supported for tagging", "code": "unsupported_type"});
    }

    if !Path::new(&filepath).exists() {
        return json!({"error": "File not found on disk", "code": "file_missing"});
    }

    if !force {
        if let Ok(existing) = get_hailo_tags(db_read, file_id).await {
            if let Some(arr) = existing.as_array() {
                if !arr.is_empty() {
                    return json!({
                        "skipped": true,
                        "reason": "already_tagged",
                        "tag_count": arr.len(),
                    });
                }
            }
        }
    }

    let raw_tags = match call_hailo_endpoint(&filepath, &endpoint_url, timeout).await {
        Ok(t) => t,
        Err(e) => return json!({"error": e, "code": "request_failed", "status_code": 502}),
    };

    let filtered: Vec<Value> = raw_tags
        .into_iter()
        .filter(|t| t.get("confidence").and_then(Value::as_f64).unwrap_or(0.0) >= threshold)
        .collect();

    let now = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;

    for tag in &filtered {
        let tag_name = tag.get("tag").and_then(Value::as_str).unwrap_or("");
        let confidence = tag.get("confidence").and_then(Value::as_f64).unwrap_or(0.0);
        if let Err(e) = sqlx::query(
            "INSERT INTO file_hailo_tags (file_id, tag_name, confidence, source, created_at)
             VALUES (?, ?, ?, 'hailo_remote', ?)
             ON CONFLICT(file_id, tag_name) DO UPDATE SET
               confidence = excluded.confidence,
               source = excluded.source,
               created_at = excluded.created_at",
        )
        .bind(file_id)
        .bind(tag_name)
        .bind(confidence)
        .bind(now)
        .execute(db)
        .await
        {
            tracing::error!(?e, file_id, "Hailo UPSERT failed");
        }
    }

    json!({
        "file_id": file_id,
        "filepath": filepath,
        "tag_count": filtered.len(),
        "tags": filtered,
    })
}

pub async fn tag_file(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
    body: Option<Json<Value>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let data = body.map(|b| b.0).unwrap_or(json!({}));
    let force = data.get("force").and_then(Value::as_bool).unwrap_or(false);

    let cfg = hailo_config(&load_config_json(&state.config.config_path));
    let result = tag_one(&state.db_read, &state.db, &cfg, file_id, force).await;

    if let Some(err) = result.get("error") {
        // `as u16` did not merely produce a nonsense code that `from_u16`
        // would reject -- it could produce a *valid* one: 65736 wraps to 200,
        // so this error branch would answer 200 OK. Reject out-of-range before
        // `from_u16` ever sees it.
        let code = result
            .get("status_code")
            .and_then(Value::as_u64)
            .and_then(|status| u16::try_from(status).ok())
            .and_then(|status| StatusCode::from_u16(status).ok())
            .unwrap_or(StatusCode::BAD_REQUEST);
        return (code, Json(json!({"ok": false, "error": err, "data": null}))).into_response();
    }
    api_result(result)
}

pub async fn batch(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<Value>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let data = body.map(|b| b.0).unwrap_or(json!({}));

    let file_ids: Option<Vec<i64>> = match data.get("file_ids") {
        None | Some(Value::Null) => None,
        Some(Value::Array(arr)) => {
            let ids: Option<Vec<i64>> = arr.iter().map(|v| v.as_i64()).collect();
            match ids {
                Some(ids) => Some(ids),
                None => {
                    return (
                        StatusCode::BAD_REQUEST,
                        Json(json!({"ok":false,"error":"file_ids must be a list of integers","data":null})),
                    )
                        .into_response()
                }
            }
        }
        _ => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"ok":false,"error":"file_ids must be a list","data":null})),
            )
                .into_response()
        }
    };

    if let Some(ref ids) = file_ids {
        if ids.len() > 500 {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"ok":false,"error":"file_ids max 500","code":"batch_too_large","data":null})),
            )
                .into_response();
        }
    }

    let limit = data
        .get("limit")
        .and_then(Value::as_i64)
        .unwrap_or(100)
        .clamp(1, 500);
    let force = data.get("force").and_then(Value::as_bool).unwrap_or(false);

    if state.job_manager.is_running("hailo_tagger") {
        return (
            StatusCode::CONFLICT,
            Json(json!({"ok":false,"error":"Hailo Tagger batch is already running","code":"job_running","data":null})),
        )
            .into_response();
    }

    let cancel_token: CancellationToken = state
        .job_manager
        .start("hailo_tagger", "Hailo Remote Tagger batch");
    let state2 = state.clone();

    tokio::spawn(async move {
        let cfg = hailo_config(&load_config_json(&state2.config.config_path));

        let targets: Vec<i64> = match file_ids {
            Some(ids) => ids,
            None => match sqlx::query(
                "SELECT f.id FROM files f \
                 WHERE f.is_deleted = 0 \
                   AND NOT EXISTS (SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id) \
                 ORDER BY f.id LIMIT ?",
            )
            .bind(limit)
            .fetch_all(&state2.db_read)
            .await
            {
                Ok(rows) => rows.iter().map(|r| r.get::<i64, _>("id")).collect(),
                Err(e) => {
                    state2
                        .job_manager
                        .finish("hailo_tagger", None, Some(e.to_string()));
                    return;
                }
            },
        };

        let total = targets.len() as u64;
        if total == 0 {
            state2.job_manager.finish(
                "hailo_tagger",
                Some(json!({"message": "No untagged files found"})),
                None,
            );
            return;
        }

        let (mut tagged, mut skipped, mut errors) = (0u64, 0u64, 0u64);

        for (i, file_id) in targets.iter().enumerate() {
            if cancel_token.is_cancelled() {
                break;
            }
            let result = tag_one(&state2.db_read, &state2.db, &cfg, *file_id, force).await;
            if result.get("error").is_some() {
                errors += 1;
            } else if result
                .get("skipped")
                .and_then(Value::as_bool)
                .unwrap_or(false)
            {
                skipped += 1;
            } else {
                tagged += 1;
            }
            let processed = (i + 1) as u64;
            state2.job_manager.update_progress(
                "hailo_tagger",
                processed,
                total,
                Some(format!(
                    "Hailo Tagger: {processed}/{total} (tagged={tagged})"
                )),
            );
        }

        state2.job_manager.finish(
            "hailo_tagger",
            Some(json!({"tagged": tagged, "skipped": skipped, "errors": errors})),
            None,
        );
    });

    api_result(json!({"started": true, "job_id": "hailo_tagger"}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::{SystemTime, UNIX_EPOCH};
    use std::{collections::HashSet, fs, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    struct TestRoot {
        path: PathBuf,
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = fs::remove_dir_all(&self.path);
        }
    }

    fn test_root() -> TestRoot {
        let suffix = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        let path = std::env::temp_dir().join(format!("yu-server-hailo-test-{suffix}"));
        fs::create_dir_all(&path).unwrap();
        TestRoot { path }
    }

    async fn test_state(root: &TestRoot, schema: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        if !schema.is_empty() {
            sqlx::raw_sql(schema).execute(&pool).await.unwrap();
        }
        Arc::new(
            AppState::new(
                Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,

                    pin_boss_login_ui: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: root.path.join("config.json"),
                    project_root: root.path.clone(),
                    app_config: json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn hailo_config_returns_defaults() {
        let root = test_root();
        let value = json_body(config(State(test_state(&root, "").await), None).await).await;

        assert_eq!(value["config"]["enabled"], false);
        assert_eq!(value["config"]["endpoint_url"], "");
        assert_eq!(value["config"]["threshold"], 0.35);
        assert_eq!(value["config"]["timeout"], 30);
    }

    #[tokio::test]
    async fn hailo_tags_return_seeded_rows_with_deterministic_tie_break() {
        let root = test_root();
        let state = test_state(
            &root,
            "CREATE TABLE file_hailo_tags (
               id INTEGER PRIMARY KEY,
               file_id INTEGER NOT NULL,
               tag_name TEXT NOT NULL,
               confidence REAL NOT NULL,
               source TEXT NOT NULL DEFAULT 'hailo_remote',
               created_at INTEGER NOT NULL
             );
             INSERT INTO file_hailo_tags(file_id, tag_name, confidence, source, created_at) VALUES
               (7, 'zeta', 0.9, 'hailo_remote', 101),
               (7, 'alpha', 0.9, 'hailo_remote', 102),
               (7, 'beta', 0.7, 'hailo_remote', 103);",
        )
        .await;

        let value = json_body(tags(State(state), AxumPath(7)).await).await;

        assert_eq!(value["file_id"], 7);
        assert_eq!(value["tags"][0]["tag_name"], "alpha");
        assert_eq!(value["tags"][1]["tag_name"], "zeta");
        assert_eq!(value["tags"][2]["tag_name"], "beta");
    }

    #[tokio::test]
    async fn hailo_tags_return_empty_when_optional_table_is_missing() {
        let root = test_root();
        let value = json_body(tags(State(test_state(&root, "").await), AxumPath(7)).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["tags"], json!([]));
    }

    #[tokio::test]
    async fn config_update_saves_partial_fields_and_reports_them_back() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let value = json_body(
            config_update(
                State(state.clone()),
                None,
                Some(Json(
                    json!({"enabled": true, "threshold": 0.5001, "timeout": 45}),
                )),
            )
            .await,
        )
        .await;

        assert_eq!(value["config"]["enabled"], true);
        assert_eq!(value["config"]["threshold"], 0.5);
        assert_eq!(value["config"]["timeout"], 45);
        assert!(value["config"].get("endpoint_url").is_none());

        // Persisted to disk, and a later GET reflects it.
        let saved = json_body(config(State(state), None).await).await;
        assert_eq!(saved["config"]["enabled"], true);
        assert_eq!(saved["config"]["timeout"], 45);
    }

    #[tokio::test]
    async fn config_update_accepts_private_lan_endpoint_url() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let value = json_body(
            config_update(
                State(state),
                None,
                Some(Json(json!({"endpoint_url": "http://192.168.1.50:8080"}))),
            )
            .await,
        )
        .await;

        assert_eq!(value["config"]["endpoint_url"], "http://192.168.1.50:8080");
    }

    #[tokio::test]
    async fn config_update_rejects_loopback_endpoint_url() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response = config_update(
            State(state),
            None,
            Some(Json(json!({"endpoint_url": "http://127.0.0.1:8080"}))),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn config_update_rejects_localhost_hostname_endpoint_url() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response = config_update(
            State(state),
            None,
            Some(Json(json!({"endpoint_url": "http://localhost:8080"}))),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn config_update_rejects_ipv4_mapped_ipv6_loopback_endpoint_url() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response = config_update(
            State(state),
            None,
            Some(Json(
                json!({"endpoint_url": "http://[::ffff:127.0.0.1]:8080"}),
            )),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn config_update_rejects_ipv4_mapped_ipv6_link_local_endpoint_url() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response = config_update(
            State(state),
            None,
            Some(Json(
                json!({"endpoint_url": "http://[::ffff:169.254.1.1]:8080"}),
            )),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn config_update_rejects_non_http_scheme() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response = config_update(
            State(state),
            None,
            Some(Json(json!({"endpoint_url": "file:///etc/passwd"}))),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn config_update_rejects_out_of_range_threshold() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response =
            config_update(State(state), None, Some(Json(json!({"threshold": 1.5})))).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn config_update_rejects_missing_body() {
        let root = test_root();
        let state = test_state(&root, "").await;

        let response = config_update(State(state), None, None).await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }
}

#[cfg(test)]
mod timeout_tests {
    use super::resolve_timeout_secs;
    use serde_json::json;

    #[test]
    fn a_negative_timeout_falls_back_instead_of_wrapping() {
        let got = resolve_timeout_secs(&json!({"timeout": -1}));
        assert_eq!(got, 30, "a negative timeout must not become no timeout");
        assert!(got < 86_400, "the timeout must stay within a day");
    }

    #[test]
    fn a_configured_timeout_is_honoured() {
        assert_eq!(resolve_timeout_secs(&json!({"timeout": 5})), 5);
    }

    #[test]
    fn an_absent_timeout_uses_the_default() {
        assert_eq!(resolve_timeout_secs(&json!({})), 30);
    }
}
