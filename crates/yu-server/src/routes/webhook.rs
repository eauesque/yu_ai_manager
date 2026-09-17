use std::{
    collections::HashMap,
    net::{IpAddr, ToSocketAddrs},
    time::{SystemTime, UNIX_EPOCH},
};

use axum::{
    body::{to_bytes, Body},
    extract::{Extension, Path as AxumPath, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use hmac::{Hmac, Mac};
use openssl::rand::rand_bytes;
use serde_json::{json, Value};
use sha2::Sha256;
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    ext_config, secret_store,
    state::SharedState,
};

pub(crate) fn api_success(payload: Value, status: StatusCode) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return (
                status,
                Json(json!({"ok": true, "error": null, "data": other})),
            )
                .into_response()
        }
    };
    body.entry("ok".to_string()).or_insert(Value::Bool(true));
    body.entry("error".to_string()).or_insert(Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    (status, Json(Value::Object(body))).into_response()
}

pub(crate) fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{message}");
    api_error("internal_server_error", StatusCode::INTERNAL_SERVER_ERROR)
}

async fn json_object_from_body(body: Body) -> Result<Value, Response> {
    let bytes = to_bytes(body, usize::MAX)
        .await
        .map_err(|_| api_error("JSON object required", StatusCode::BAD_REQUEST))?;
    let value = serde_json::from_slice::<Value>(&bytes)
        .map_err(|_| api_error("JSON object required", StatusCode::BAD_REQUEST))?;
    if value.is_object() {
        Ok(value)
    } else {
        Err(api_error("JSON object required", StatusCode::BAD_REQUEST))
    }
}

fn now_ts() -> i64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0)
}

pub(crate) fn random_hex(bytes: usize) -> String {
    let mut raw = vec![0_u8; bytes];
    rand_bytes(&mut raw).expect("openssl rand_bytes");
    hex::encode(raw)
}

pub(crate) fn config_array_mut<'a>(config: &'a mut Value, key: &str) -> &'a mut Vec<Value> {
    if !config.get(key).is_some_and(Value::is_array) {
        config[key] = json!([]);
    }
    config[key].as_array_mut().expect("array set above")
}

fn list_array(config: &Value, key: &str) -> Vec<Value> {
    config
        .get(key)
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
}

fn truncate_str(value: Option<&Value>, max: usize) -> String {
    value
        .and_then(Value::as_str)
        .unwrap_or("")
        .chars()
        .take(max)
        .collect()
}

fn truncated_string_list(
    value: Option<&Value>,
    max_items: usize,
    max_len: usize,
) -> Option<Vec<Value>> {
    value.and_then(Value::as_array).map(|items| {
        items
            .iter()
            .take(max_items)
            .map(|item| Value::String(item.as_str().unwrap_or("").chars().take(max_len).collect()))
            .collect()
    })
}

fn notify_webhooks_changed(state: &SharedState) {
    if state.config.python_url.is_empty() {
        return;
    }
    let url = format!(
        "{}/_internal/webhooks-changed",
        state.config.python_url.trim_end_matches('/')
    );
    let client = state.python_client.clone();
    tokio::spawn(async move {
        let _ = client.post(url).send().await;
    });
}

fn ensure_webhook_secret(config: &mut Value, project_root: &std::path::Path) {
    let existing = config
        .get("webhook_secret")
        .and_then(Value::as_str)
        .unwrap_or("");
    if existing.is_empty() {
        let secret = random_hex(32);
        config["webhook_secret"] = json!(secret_store::encrypt(&secret, project_root));
    }
}

trait HostResolver {
    fn resolve_host(&self, host: &str) -> std::io::Result<Vec<IpAddr>>;
}

struct SystemResolver;

impl HostResolver for SystemResolver {
    fn resolve_host(&self, host: &str) -> std::io::Result<Vec<IpAddr>> {
        (host, 0).to_socket_addrs().map(|addrs| {
            addrs
                .map(|addr| addr.ip())
                .collect::<std::collections::HashSet<_>>()
                .into_iter()
                .collect()
        })
    }
}

fn is_internal_ip(ip: IpAddr) -> bool {
    // Normalize IPv4-mapped/IPv4-compatible IPv6 to IPv4 first to prevent bypass.
    if let IpAddr::V6(v6) = ip {
        if let Some(v4) = v6.to_ipv4_mapped().or_else(|| v6.to_ipv4()) {
            return is_internal_ip(IpAddr::V4(v4));
        }
        // Block 6to4 relay prefix (2002::/16) by checking the embedded IPv4.
        if v6.segments()[0] == 0x2002 {
            let segs = v6.segments();
            let v4 = std::net::Ipv4Addr::new(
                (segs[1] >> 8) as u8,
                (segs[1] & 0xff) as u8,
                (segs[2] >> 8) as u8,
                (segs[2] & 0xff) as u8,
            );
            return is_internal_ip(IpAddr::V4(v4));
        }
        return v6.is_loopback()
            || v6.is_unspecified()
            || v6.is_unique_local()
            || v6.is_unicast_link_local()
            || v6.is_multicast();
    }
    let IpAddr::V4(ip) = ip else {
        // The `if let IpAddr::V6` block above returns on every path, so only V4
        // reaches here. Say it without a panic: this runs inside the SSRF check
        // on a caller-supplied URL, where an unwind is a denial of service.
        return true;
    };
    ip.is_private()
        || ip.is_loopback()
        || ip.is_link_local()
        || ip.is_unspecified()
        || ip.is_broadcast()
        || ip.is_documentation()
        || ip.octets()[0] >= 240
        // CGNAT (100.64.0.0/10) and benchmark (198.18.0.0/15)
        || (ip.octets()[0] == 100 && ip.octets()[1] >= 64 && ip.octets()[1] < 128)
        || (ip.octets()[0] == 198 && (ip.octets()[1] == 18 || ip.octets()[1] == 19))
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn validate_webhook_url_with_resolver(
    url: &str,
    resolver: &dyn HostResolver,
) -> Result<(), &'static str> {
    if let Some((scheme, rest)) = url.split_once("://") {
        if matches!(scheme, "http" | "https") && (rest.is_empty() || rest.starts_with('/')) {
            return Err("URL must have a valid hostname");
        }
    }
    let parsed = reqwest::Url::parse(url).map_err(|_| "URL must use http or https scheme")?;
    if !matches!(parsed.scheme(), "http" | "https") {
        return Err("URL must use http or https scheme");
    }
    let Some(host) = parsed.host_str() else {
        return Err("URL must have a valid hostname");
    };
    if !parsed.username().is_empty() || parsed.password().is_some() {
        return Err("URL must not contain credentials");
    }
    if std::env::var_os("ALLOW_LOOPBACK_WEBHOOK").is_some() {
        return Ok(());
    }
    if let Ok(ip) = host.parse::<IpAddr>() {
        return if is_internal_ip(ip) {
            Err("URL must not point to a private or internal address")
        } else {
            Ok(())
        };
    }
    let ips = resolver
        .resolve_host(host)
        .map_err(|_| "URL must not point to a private or internal address")?;
    if ips.is_empty() || ips.into_iter().any(is_internal_ip) {
        return Err("URL must not point to a private or internal address");
    }
    Ok(())
}

fn validate_webhook_url(url: &str) -> Result<(), &'static str> {
    validate_webhook_url_with_resolver(url, &SystemResolver)
}

/// Build the `webhook.test` body, mirroring Python's `Event.to_dict()`.
///
/// Field ORDER is deliberate and load-bearing for readers who diff the two
/// runtimes: `serde` emits struct fields in declaration order, so this matches
/// `webhook_dispatcher.py:155-161` without hand-writing JSON. An earlier draft
/// built the string with `format!`, which put the escaping of `wh_id` on the
/// author rather than on the serializer.
///
/// Byte-identity with Python is NOT required for the signature to verify: both
/// sides sign the bytes they actually send, and the receiver verifies over the
/// bytes it actually got. It is not achievable here either -- Python's
/// `json.dumps` writes a whole-second float as `1757308800.0` where Rust writes
/// `1757308800`, and Python separates items with `", "` where `serde_json` uses
/// `","`. Both are valid JSON carrying the same values. Do not chase the bytes;
/// if a receiver ever needs a canonical form, give it one explicitly.
#[derive(serde::Serialize)]
struct TestEvent<'a> {
    #[serde(rename = "type")]
    event_type: &'a str,
    timestamp: f64,
    data: TestEventData<'a>,
    source: &'a str,
}

#[derive(serde::Serialize)]
struct TestEventData<'a> {
    message: &'a str,
    webhook_id: &'a str,
}

fn test_webhook_payload(wh_id: &str) -> Vec<u8> {
    let timestamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    let event = TestEvent {
        event_type: "webhook.test",
        timestamp,
        data: TestEventData {
            message: "This is a test event",
            webhook_id: wh_id,
        },
        source: "manual",
    };
    // `to_vec` on a struct of `&str` and `f64` cannot fail, but saying so with
    // `expect` puts a panic in a request path to assert a property the types
    // already give. An empty body would be a visible delivery failure at the
    // receiver, which is the safer way to be wrong.
    serde_json::to_vec(&event).unwrap_or_default()
}

pub async fn test_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(wh_id): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read webhook config"),
    };
    let Some(webhook) = list_array(&config, "webhooks")
        .into_iter()
        .find(|hook| hook.get("id").and_then(Value::as_str) == Some(&wh_id))
    else {
        return api_error("Webhook not found", StatusCode::NOT_FOUND);
    };
    let url = webhook.get("url").and_then(Value::as_str).unwrap_or("");
    if validate_webhook_url(url).is_err() {
        return api_success(
            json!({"success": false, "error": "Invalid webhook target"}),
            StatusCode::OK,
        );
    }

    let payload = test_webhook_payload(&wh_id);
    let secret = config
        .get("webhook_secret")
        .and_then(Value::as_str)
        .map(|stored| secret_store::decrypt(stored, &state.config.project_root))
        .unwrap_or_default();
    let mut signer = match Hmac::<Sha256>::new_from_slice(secret.as_bytes()) {
        Ok(signer) => signer,
        // `Hmac` takes a key of any length, so this arm is unreachable today.
        // Returning the delivery-failure shape rather than `expect`-ing keeps a
        // future upstream change from turning a signing problem into a panic in
        // a request handler.
        Err(error) => {
            tracing::error!(%error, "webhook test signing key rejected");
            return api_success(
                json!({"success": false, "error": "Invalid webhook target"}),
                StatusCode::OK,
            );
        }
    };
    signer.update(&payload);
    let signature = hex::encode(signer.finalize().into_bytes());
    let response = state
        .python_client
        .post(url)
        .header("Content-Type", "application/json; charset=utf-8")
        .header("User-Agent", "YU-AI-Manager-Webhook/1.0")
        .header("X-Webhook-Signature", format!("sha256={signature}"))
        .header("X-Webhook-Id", &wh_id)
        .header("X-Webhook-Event", "webhook.test")
        .body(payload)
        .send()
        .await;
    match response {
        Ok(response) => {
            let status_code = response.status().as_u16();
            let success = response.status().is_success();
            let body = response
                .text()
                .await
                .unwrap_or_default()
                .chars()
                .take(1024)
                .collect::<String>();
            api_success(
                json!({"success": success, "status_code": status_code, "body": body}),
                StatusCode::OK,
            )
        }
        Err(error) => {
            tracing::warn!(?error, "Webhook test failed");
            api_success(
                json!({"success": false, "error": "Connection failed"}),
                StatusCode::OK,
            )
        }
    }
}

pub async fn create_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    request: axum::extract::Request,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    let url = data.get("url").and_then(Value::as_str).unwrap_or("").trim();
    if url.is_empty() {
        return api_error("url is required", StatusCode::BAD_REQUEST);
    }
    if !data.get("events").is_none_or(Value::is_array) {
        return api_error("events must be a list", StatusCode::BAD_REQUEST);
    }
    if validate_webhook_url(url).is_err() {
        return api_error("Invalid webhook configuration", StatusCode::BAD_REQUEST);
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read webhook config"),
    };
    ensure_webhook_secret(&mut config, &state.config.project_root);
    let now = now_ts();
    let label = {
        let label = truncate_str(data.get("label"), 128);
        if label.is_empty() {
            format!("Webhook {now}")
        } else {
            label
        }
    };
    let entry = json!({
        "id": format!("wh_{}", random_hex(8)),
        "url": url,
        "events": truncated_string_list(data.get("events"), 50, 64).unwrap_or_default(),
        "label": label,
        "active": true,
        "created_at": now,
    });
    config_array_mut(&mut config, "webhooks").push(entry.clone());
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write webhook config");
    }
    notify_webhooks_changed(&state);
    api_success(entry, StatusCode::CREATED)
}

pub async fn list_webhooks(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    match ext_config::read_config(&state.config.config_path) {
        Ok(config) => api_success(
            json!({"webhooks": list_array(&config, "webhooks")}),
            StatusCode::OK,
        ),
        Err(error) => internal_error(error, "failed to read webhook config"),
    }
}

pub async fn update_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(wh_id): AxumPath<String>,
    request: axum::extract::Request,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    if let Some(url) = data.get("url").and_then(Value::as_str) {
        if validate_webhook_url(url).is_err() {
            return api_error("Invalid webhook update", StatusCode::BAD_REQUEST);
        }
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read webhook config"),
    };
    let hooks = config_array_mut(&mut config, "webhooks");
    let Some(idx) = hooks
        .iter()
        .position(|hook| hook.get("id").and_then(Value::as_str) == Some(&wh_id))
    else {
        return api_error("Webhook not found", StatusCode::NOT_FOUND);
    };
    for key in ["url", "events", "label", "active"] {
        if let Some(value) = data.get(key) {
            hooks[idx][key] = value.clone();
        }
    }
    let updated = hooks[idx].clone();
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write webhook config");
    }
    notify_webhooks_changed(&state);
    api_success(updated, StatusCode::OK)
}

pub async fn delete_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(wh_id): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read webhook config"),
    };
    let hooks = config_array_mut(&mut config, "webhooks");
    let before = hooks.len();
    hooks.retain(|hook| hook.get("id").and_then(Value::as_str) != Some(&wh_id));
    if hooks.len() == before {
        return api_error("Webhook not found", StatusCode::NOT_FOUND);
    }
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write webhook config");
    }
    notify_webhooks_changed(&state);
    api_success(json!({"deleted": wh_id}), StatusCode::OK)
}

pub async fn list_deliveries(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let limit = params
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .map(|v| v.min(500))
        .unwrap_or(50);
    let webhook_id = params.get("webhook_id").filter(|v| !v.is_empty());
    let rows = if let Some(webhook_id) = webhook_id {
        sqlx::query(
            "SELECT id, webhook_id, event_type, status_code, attempt, success, error, created_at, delivered_at
             FROM webhook_deliveries WHERE webhook_id = ? ORDER BY created_at DESC LIMIT ?",
        )
        .bind(webhook_id)
        .bind(limit)
        .fetch_all(&state.db_read)
        .await
    } else {
        sqlx::query(
            "SELECT id, webhook_id, event_type, status_code, attempt, success, error, created_at, delivered_at
             FROM webhook_deliveries ORDER BY created_at DESC LIMIT ?",
        )
        .bind(limit)
        .fetch_all(&state.db_read)
        .await
    };
    let rows = match rows {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to list webhook deliveries"),
    };
    let deliveries = rows
        .iter()
        .map(|row| {
            json!({
                "id": row.get::<i64, _>("id"),
                "webhook_id": row.get::<String, _>("webhook_id"),
                "event_type": row.get::<String, _>("event_type"),
                "status_code": row.try_get::<Option<i64>, _>("status_code").unwrap_or(None),
                "attempt": row.get::<i64, _>("attempt"),
                "success": row.get::<i64, _>("success") != 0,
                "error": row.try_get::<Option<String>, _>("error").unwrap_or(None),
                "created_at": row.get::<i64, _>("created_at"),
                "delivered_at": row.try_get::<Option<i64>, _>("delivered_at").unwrap_or(None),
            })
        })
        .collect::<Vec<_>>();
    api_success(json!({"deliveries": deliveries}), StatusCode::OK)
}

pub async fn create_inbound_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(data): Json<Value>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    if !data.get("allowed_events").is_none_or(Value::is_array) {
        return api_error("allowed_events must be a list", StatusCode::BAD_REQUEST);
    }
    let now = now_ts();
    let label = {
        let label = truncate_str(data.get("label"), 128);
        if label.is_empty() {
            format!("Inbound {now}")
        } else {
            label
        }
    };
    let entry = json!({
        "id": format!("iwh_{}", random_hex(8)),
        "token": random_hex(32),
        "label": label,
        "allowed_events": truncated_string_list(data.get("allowed_events"), 50, 64).unwrap_or_default(),
        "active": true,
        "created_at": now,
    });
    let _guard = state.settings_lock.lock().await;
    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read inbound webhook config"),
    };
    config_array_mut(&mut config, "inbound_webhooks").push(entry.clone());
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write inbound webhook config");
    }
    notify_webhooks_changed(&state);
    api_success(entry, StatusCode::CREATED)
}

pub async fn list_inbound_webhooks(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read inbound webhook config"),
    };
    let mut hooks = list_array(&config, "inbound_webhooks");
    for hook in &mut hooks {
        if let Some(obj) = hook.as_object_mut() {
            obj.remove("token");
        }
    }
    api_success(json!({"inbound_webhooks": hooks}), StatusCode::OK)
}

pub async fn update_inbound_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(wh_id): AxumPath<String>,
    Json(data): Json<Value>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read inbound webhook config"),
    };
    let hooks = config_array_mut(&mut config, "inbound_webhooks");
    let Some(idx) = hooks
        .iter()
        .position(|hook| hook.get("id").and_then(Value::as_str) == Some(&wh_id))
    else {
        return api_error("Inbound webhook not found", StatusCode::NOT_FOUND);
    };
    for key in ["label", "allowed_events", "active"] {
        if let Some(value) = data.get(key) {
            hooks[idx][key] = value.clone();
        }
    }
    let updated = hooks[idx].clone();
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write inbound webhook config");
    }
    notify_webhooks_changed(&state);
    api_success(updated, StatusCode::OK)
}

pub async fn delete_inbound_webhook(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(wh_id): AxumPath<String>,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match ext_config::read_config(&state.config.config_path) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read inbound webhook config"),
    };
    let hooks = config_array_mut(&mut config, "inbound_webhooks");
    let before = hooks.len();
    hooks.retain(|hook| hook.get("id").and_then(Value::as_str) != Some(&wh_id));
    if hooks.len() == before {
        return api_error("Inbound webhook not found", StatusCode::NOT_FOUND);
    }
    if let Err(error) = crate::config_io::write(&state.config.config_path, &config) {
        return internal_error(error, "failed to write inbound webhook config");
    }
    notify_webhooks_changed(&state);
    api_success(json!({"deleted": wh_id}), StatusCode::OK)
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::{HashMap, HashSet},
        sync::{Arc, Mutex},
    };

    use axum::{
        body::{to_bytes, Body},
        extract::{Path as AxumPath, Query, State},
        http::{Request, StatusCode},
        Json,
    };
    use serde_json::{json, Value};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tempfile::TempDir;
    use tokio::{
        io::{AsyncReadExt, AsyncWriteExt},
        net::TcpListener,
        sync::oneshot,
    };

    use crate::{
        auth::{PinRateLimiter, QuickLock},
        groups_index::GroupsIndexCache,
        state::{AppState, Config, SharedState},
    };

    struct MockResolver {
        result: std::io::Result<Vec<IpAddr>>,
    }

    impl HostResolver for MockResolver {
        fn resolve_host(&self, _host: &str) -> std::io::Result<Vec<IpAddr>> {
            match &self.result {
                Ok(ips) => Ok(ips.clone()),
                Err(err) => Err(std::io::Error::new(err.kind(), err.to_string())),
            }
        }
    }

    static ENV_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

    async fn test_state() -> (SharedState, TempDir) {
        let temp = TempDir::new().unwrap();
        let config_path = temp.path().join("config.json");
        std::fs::write(&config_path, "{}").unwrap();
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(SqliteConnectOptions::new().filename(":memory:"))
            .await
            .unwrap();
        let state = Arc::new(AppState {
            effective_port: 5000,
            gateway_keys: Vec::new(),
            gateway_loopback_bypass: true,
            settings_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            infer_notify_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            scan_roots_generation: std::sync::atomic::AtomicU64::new(0),
            config: Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,

                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                rate_limit_trusted_proxies: HashSet::new(),
                quick_lock_enabled: true,
                pin_auth_enabled: false,
                min_pin_length: 4,
                python_url: String::new(),
                config_path,
                project_root: temp.path().to_path_buf(),
                app_config: json!({}),
                cache_dir: temp.path().join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                mcp_native: false,
                standalone: false,
                infer_standalone: true,
                active_profile: None,
                python_executable: String::new(),
                wd_tagger_root: std::path::PathBuf::from("."),
                clip_model_dir: std::path::PathBuf::from("."),
            },
            db: pool.clone(),
            db_read: pool.clone(),
            vectors_db: pool.clone(),
            vectors_db_read: pool,
            clip_index: std::sync::Arc::new(
                crate::routes::clip_index::ClipIndex::new_default(std::env::temp_dir())
                    .expect("clip index test default"),
            ),
            clip_indexer: std::sync::Arc::new(crate::routes::clip_indexer::ClipIndexer::new()),
            caption_runner: std::sync::Arc::new(crate::routes::caption_runner::CaptionRunner::new()),
            s2t_runner: std::sync::Arc::new(crate::routes::s2t_runner::S2tRunner::new()),
            clip_runtime_cache: crate::state::TtlCache::new(crate::state::CLIP_RUNTIME_CACHE_TTL),
            stats_db_sig: tokio::sync::Mutex::new(None),
            inference_client: reqwest::Client::new(),
            python_client: reqwest::Client::new(),
            quick_lock: QuickLock::new(),
            rate_limiter: PinRateLimiter::new(),
            api_rate_limiters: crate::auth::api_rate_limit::RateLimiters::new(),
            groups_index_cache: GroupsIndexCache::new(temp.path().join("cache")),
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub: Arc::new(crate::sse::SseHub::new()),
            job_manager: Arc::new(crate::jobs::JobManager::new()),
            watcher: Arc::new(crate::watcher::ScanWatcher::new()),
            log_ring: Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            mcp_sessions: Arc::new(crate::mcp::session::McpSessionStore::new(1000, 20, 256)),
            approval_gate: Mutex::new(crate::approval_gate::ApprovalGate::default()),
            env: minijinja::Environment::new(),
            dist_v: "dev".to_string(),
            version: "0.0.0".to_string(),
            start_time: std::time::Instant::now(),
            scheduler_state: std::sync::OnceLock::new(),
            wd_infer: std::sync::Arc::new(std::sync::Mutex::new(std::collections::HashMap::new())),
            infer_client: None,
            infer_child: None,
            scan_manager: std::sync::OnceLock::new(),
            scan_queue: std::sync::Arc::new(crate::scan_queue::ScanQueue::load(
                std::path::Path::new(""),
            )),
            hailo_yolo_stream: None,
            stats_basic_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_models_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_timeline_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_resolutions_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            checkpoints_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            server_info_stats_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
        });
        (state, temp)
    }

    async fn json_body(response: axum::response::Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn test_webhook_matches_python_delivery_contract() {
        // Held for the WHOLE test, not just the delivery half. The rejection
        // assertion below checks a default-OFF behaviour, so it races with any
        // test that turns ALLOW_LOOPBACK_WEBHOOK on -- asserting the negative is
        // exactly where an env race hides, and this one lost that race in CI.
        let _guard = ENV_LOCK.lock().unwrap();
        // Do not rely on other tests unsetting it: a panicking test skips its
        // own remove_var and would leave this assertion silently inverted.
        std::env::remove_var("ALLOW_LOOPBACK_WEBHOOK");
        let (state, _temp) = test_state().await;
        let unknown =
            super::test_webhook(State(state.clone()), None, AxumPath("missing".into())).await;
        assert_eq!(unknown.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            json_body(unknown).await,
            json!({"ok": false, "error": "Webhook not found"})
        );

        std::fs::write(
            &state.config.config_path,
            json!({"webhooks": [{"id": "wh_test", "url": "http://127.0.0.1/hook"}]}).to_string(),
        )
        .unwrap();
        let rejected =
            super::test_webhook(State(state.clone()), None, AxumPath("wh_test".into())).await;
        assert_eq!(rejected.status(), StatusCode::OK);
        let rejected = json_body(rejected).await;
        assert_eq!(rejected["success"], false);
        assert_eq!(rejected["error"], "Invalid webhook target");

        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        let url = format!("http://{}/hook", listener.local_addr().unwrap());
        let (received_tx, received_rx) = oneshot::channel();
        tokio::spawn(async move {
            let (mut socket, _) = listener.accept().await.unwrap();
            let mut bytes = Vec::new();
            let mut chunk = [0; 4096];
            loop {
                let count = socket.read(&mut chunk).await.unwrap();
                bytes.extend_from_slice(&chunk[..count]);
                let Some(header_end) = bytes.windows(4).position(|w| w == b"\r\n\r\n") else {
                    continue;
                };
                let headers = std::str::from_utf8(&bytes[..header_end]).unwrap();
                let length = headers
                    .lines()
                    .find_map(|line| {
                        line.strip_prefix("content-length: ")
                            .or_else(|| line.strip_prefix("Content-Length: "))
                    })
                    .unwrap()
                    .parse::<usize>()
                    .unwrap();
                if bytes.len() >= header_end + 4 + length {
                    break;
                }
            }
            socket
                .write_all(b"HTTP/1.1 201 Created\r\nContent-Length: 2\r\n\r\nok")
                .await
                .unwrap();
            let _ = received_tx.send(bytes);
        });
        std::fs::write(
            &state.config.config_path,
            json!({"webhook_secret": "test-secret", "webhooks": [{"id": "wh_test", "url": url}]})
                .to_string(),
        )
        .unwrap();
        std::env::set_var("ALLOW_LOOPBACK_WEBHOOK", "1");
        let delivered =
            super::test_webhook(State(state.clone()), None, AxumPath("wh_test".into())).await;
        std::env::remove_var("ALLOW_LOOPBACK_WEBHOOK");
        assert_eq!(
            json_body(delivered).await,
            json!({"ok": true, "error": null, "data": null, "success": true, "status_code": 201, "body": "ok"})
        );
        let received = received_rx.await.unwrap();
        let header_end = received.windows(4).position(|w| w == b"\r\n\r\n").unwrap();
        let headers = std::str::from_utf8(&received[..header_end]).unwrap();
        let headers = headers.to_ascii_lowercase();
        let body = &received[header_end + 4..];
        assert!(headers.contains("x-webhook-id: wh_test"));
        assert!(headers.contains("x-webhook-event: webhook.test"));
        let mut signer = Hmac::<Sha256>::new_from_slice(b"test-secret").unwrap();
        signer.update(body);
        assert!(headers.contains(&format!(
            "x-webhook-signature: sha256={}",
            hex::encode(signer.finalize().into_bytes())
        )));
        // Key ORDER, not whitespace. The point of this assertion is that the
        // body mirrors Python's `Event.to_dict()` field order, which is what a
        // reader diffing the two runtimes compares. Pinning the exact spacing
        // instead made the assertion fail the moment the payload moved from a
        // hand-written `format!` to `serde` -- `{"type": ` vs `{"type":` --
        // even though every value, and the signature over them, was unchanged.
        // Python and Rust cannot agree on the bytes anyway: `json.dumps` writes
        // a whole-second float as `1757308800.0` and separates items with
        // `", "`, where serde writes `1757308800` and `","`.
        let text = std::str::from_utf8(body).unwrap();
        let key_order: Vec<&str> = ["\"type\"", "\"timestamp\"", "\"data\"", "\"source\""]
            .into_iter()
            .filter(|key| text.contains(key))
            .collect();
        assert_eq!(
            key_order,
            vec!["\"type\"", "\"timestamp\"", "\"data\"", "\"source\""],
            "every top-level key must be present: {text}"
        );
        let positions: Vec<usize> = key_order
            .iter()
            .map(|key| text.find(key).unwrap())
            .collect();
        assert!(
            positions.windows(2).all(|pair| pair[0] < pair[1]),
            "top-level keys must follow Python's Event.to_dict order: {text}"
        );
        assert_eq!(
            serde_json::from_slice::<Value>(body).unwrap()["type"],
            "webhook.test"
        );
        assert_eq!(
            serde_json::from_slice::<Value>(body).unwrap()["data"]["message"],
            "This is a test event"
        );
    }

    #[tokio::test]
    async fn create_webhook_persists_encrypted_secret_and_redacts_response() {
        let (state, _temp) = test_state().await;
        let response = super::create_webhook(
            State(state.clone()),
            None,
            Request::builder()
                .header("content-type", "application/json")
                .body(Body::from(
                    json!({"url": "https://93.184.216.34/hook", "events": ["file.added"], "label": "Deploy"}).to_string(),
                ))
                .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::CREATED);
        let body = json_body(response).await;
        assert_eq!(body["ok"], true);
        assert_eq!(body["error"], Value::Null);
        assert!(body["id"].as_str().unwrap().starts_with("wh_"));
        assert!(body.get("webhook_secret").is_none());

        let saved: Value =
            serde_json::from_str(&std::fs::read_to_string(&state.config.config_path).unwrap())
                .unwrap();
        assert!(saved["webhook_secret"]
            .as_str()
            .unwrap()
            .starts_with("enc:v2:"));
        assert_eq!(saved["webhooks"][0]["url"], "https://93.184.216.34/hook");
    }

    #[tokio::test]
    async fn create_webhook_rejects_non_object_json_with_api_error_shape() {
        let (state, _temp) = test_state().await;
        let response = super::create_webhook(
            State(state),
            None,
            Request::builder()
                .header("content-type", "application/json")
                .body(Body::from("[]"))
                .unwrap(),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "JSON object required"})
        );
    }

    #[test]
    fn validate_webhook_url_rejects_python_error_strings() {
        let _guard = ENV_LOCK.lock().unwrap();
        std::env::remove_var("ALLOW_LOOPBACK_WEBHOOK");
        let resolver = MockResolver {
            result: Ok(vec!["93.184.216.34".parse().unwrap()]),
        };

        assert_eq!(
            validate_webhook_url_with_resolver("ftp://example.com/hook", &resolver),
            Err("URL must use http or https scheme")
        );
        assert_eq!(
            validate_webhook_url_with_resolver("https:///hook", &resolver),
            Err("URL must have a valid hostname")
        );
        assert_eq!(
            validate_webhook_url_with_resolver("https://user:pass@example.com/hook", &resolver),
            Err("URL must not contain credentials")
        );
        assert_eq!(
            validate_webhook_url_with_resolver("http://127.0.0.1/hook", &resolver),
            Err("URL must not point to a private or internal address")
        );
    }

    #[test]
    fn validate_webhook_url_blocks_private_dns_and_resolution_failure() {
        let _guard = ENV_LOCK.lock().unwrap();
        std::env::remove_var("ALLOW_LOOPBACK_WEBHOOK");

        assert_eq!(
            validate_webhook_url_with_resolver(
                "https://internal.example/hook",
                &MockResolver {
                    result: Ok(vec!["10.0.0.5".parse().unwrap()]),
                },
            ),
            Err("URL must not point to a private or internal address")
        );
        assert_eq!(
            validate_webhook_url_with_resolver(
                "https://missing.example/hook",
                &MockResolver {
                    result: Err(std::io::Error::new(
                        std::io::ErrorKind::NotFound,
                        "not found",
                    )),
                },
            ),
            Err("URL must not point to a private or internal address")
        );
    }

    #[test]
    fn validate_webhook_url_allows_loopback_when_env_set() {
        let _guard = ENV_LOCK.lock().unwrap();
        std::env::set_var("ALLOW_LOOPBACK_WEBHOOK", "1");
        let result = validate_webhook_url_with_resolver(
            "http://127.0.0.1/hook",
            &MockResolver {
                result: Err(std::io::Error::other("should not resolve")),
            },
        );
        std::env::remove_var("ALLOW_LOOPBACK_WEBHOOK");
        assert_eq!(result, Ok(()));
    }

    #[tokio::test]
    async fn inbound_crud_redacts_token_on_list_and_preserves_token_on_create() {
        let (state, _temp) = test_state().await;
        let response = super::create_inbound_webhook(
            State(state.clone()),
            None,
            Json(json!({"label": "CI", "allowed_events": ["build.done"]})),
        )
        .await;

        assert_eq!(response.status(), StatusCode::CREATED);
        let created = json_body(response).await;
        assert_eq!(created["ok"], true);
        assert!(created["token"].as_str().unwrap().len() == 64);

        let response = super::list_inbound_webhooks(State(state), None).await;
        let listed = json_body(response).await;
        assert_eq!(listed["inbound_webhooks"][0]["label"], "CI");
        assert!(listed["inbound_webhooks"][0].get("token").is_none());
    }

    #[tokio::test]
    async fn deliveries_clamps_invalid_limit_to_python_default() {
        let (state, _temp) = test_state().await;
        sqlx::query(
            "CREATE TABLE webhook_deliveries (
                id INTEGER PRIMARY KEY,
                webhook_id TEXT NOT NULL,
                event_type TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                status_code INTEGER,
                response_body TEXT,
                attempt INTEGER NOT NULL DEFAULT 1,
                success INTEGER NOT NULL DEFAULT 0,
                error TEXT,
                created_at INTEGER NOT NULL,
                delivered_at INTEGER
            )",
        )
        .execute(&state.db)
        .await
        .unwrap();
        sqlx::query(
            "INSERT INTO webhook_deliveries(id, webhook_id, event_type, payload_json, status_code, attempt, success, error, created_at, delivered_at)
             VALUES (1, 'wh_a', 'file.added', '{}', 200, 1, 1, NULL, 20, 21)",
        )
        .execute(&state.db)
        .await
        .unwrap();

        let response = super::list_deliveries(
            State(state),
            None,
            Query(HashMap::from([("limit".to_string(), "bad".to_string())])),
        )
        .await;

        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(json_body(response).await["deliveries"][0]["success"], true);
    }

    #[tokio::test]
    async fn delete_missing_webhook_uses_python_error_shape() {
        let (state, _temp) = test_state().await;
        let response =
            super::delete_webhook(State(state), None, AxumPath("wh_missing".to_string())).await;

        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "Webhook not found"})
        );
    }
}
