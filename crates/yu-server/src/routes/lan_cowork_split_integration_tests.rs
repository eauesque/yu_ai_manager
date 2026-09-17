use std::{path::Path, sync::Arc, time::Duration};

use axum::{
    body::{to_bytes, Body},
    http::{header, Method, Request as HttpRequest, StatusCode},
    middleware, Router,
};
use futures_util::{FutureExt, StreamExt};
use lan_cowork::routes::{
    lan_cowork::{load_config_json, write_config_json},
    lan_cowork_bypass::{BypassMatch, BYPASS_ROUTES},
    lan_cowork_client,
    lan_cowork_descriptor::{
        reset_client_state, test_guard, LocalDescriptor, TEST_ALLOW_LOOPBACK, TEST_DESCRIPTOR,
    },
    lan_cowork_fleet_dispatch, lan_cowork_fleet_ops, lan_cowork_fleet_peers,
    lan_cowork_host::{LanCoworkHost, LanCoworkState, LogEvent, PeerSourceIp},
    lan_cowork_registry::{PeerInfo, PeerRegistry},
    peer_identity,
};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use std::collections::HashSet;
use std::sync::atomic::Ordering;
use tower::ServiceExt;
use tower_sessions::{MemoryStore, SessionManagerLayer};

use crate::{
    auth::{
        chain::{check_static_bypass, run_chain, ChainParams},
        middleware::auth_middleware,
        scope::AuthContext,
    },
    logs::ring::PartialEntry,
    logs::LogRingBuffer,
    routes::lan_cowork_host_impl::set_log_open_seam_hook,
    state::{
        semantic_test_state, semantic_test_state_with, semantic_test_state_with_root, SharedState,
    },
};

fn authenticated_initiator(state: SharedState) -> Router {
    Router::new()
        .merge(lan_cowork_client::routes())
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .layer(SessionManagerLayer::new(MemoryStore::default()))
        .layer(middleware::from_fn(crate::csrf::layer))
        .layer(middleware::from_fn(crate::security::layer))
        .with_state(LanCoworkState::from_shared(&state))
}

#[tokio::test]
async fn client_pair_request_requires_a_session_in_the_full_middleware_stack() {
    let state = semantic_test_state(true).await;
    let response = authenticated_initiator(state)
        .oneshot(
            axum::http::Request::post("/ext/lan_cowork/api/client/pair/request")
                .header("content-type", "application/json")
                .header("x-requested-with", "XMLHttpRequest")
                .body(Body::from(r#"{"peer_id":"peer"}"#))
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
}

async fn client_state() -> SharedState {
    let state = crate::state::semantic_test_state_with(false, String::new()).await;
    sqlx::raw_sql(
        "CREATE TABLE peers (peer_id TEXT PRIMARY KEY, name TEXT, api_host TEXT,
           api_port INTEGER, token TEXT, token_expires_at INTEGER, token_issued_at INTEGER,
           pubkey BLOB, x25519_pk BLOB, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);
         CREATE TABLE lan_cowork_identity (key TEXT PRIMARY KEY, value BLOB);
         CREATE TABLE peer_pairing_requests (
           request_id TEXT PRIMARY KEY, peer_id TEXT NOT NULL, host TEXT NOT NULL,
           port INTEGER NOT NULL, pin_hash TEXT, pin_expires_at INTEGER,
           verify_attempts INTEGER NOT NULL DEFAULT 0, status TEXT NOT NULL,
           created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL,
           pubkey BLOB, x25519_pk BLOB, commit_hash BLOB, sas TEXT, source_ip TEXT);
         CREATE TABLE peer_tokens (
           peer_id TEXT PRIMARY KEY, token_hash TEXT NOT NULL, issued_at INTEGER NOT NULL,
           expires_at INTEGER NOT NULL, revoked_at INTEGER,
           source TEXT NOT NULL DEFAULT 'pairing', note TEXT);",
    )
    .execute(&state.db)
    .await
    .unwrap();
    sqlx::query("INSERT INTO lan_cowork_identity (key, value) VALUES ('ed25519_seed', ?1)")
        .bind((1u8..=32).collect::<Vec<_>>())
        .execute(&state.db)
        .await
        .unwrap();
    state
}

async fn local_peer_id_of(state: &SharedState) -> String {
    let (ed, _) = peer_identity::local_identity_material(&**state)
        .await
        .unwrap();
    peer_identity::derive_peer_id(&ed)
}

async fn start_responder(
    state: &SharedState,
    source_ip: &str,
) -> (u16, tokio::task::JoinHandle<()>) {
    let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.unwrap();
    let port = listener.local_addr().unwrap().port();
    let app = crate::routes::lan_cowork_pairing::routes()
        .with_state(LanCoworkState::from_shared(state))
        .layer(axum::Extension(PeerSourceIp(source_ip.to_string())));
    let handle = tokio::spawn(async move {
        let _ = axum::serve(listener, app).await;
    });
    (port, handle)
}

async fn insert_peer(state: &SharedState, peer_id: &str, host: &str, port: i64) {
    sqlx::query(
        "INSERT INTO peers (peer_id,name,api_host,api_port,created_at,updated_at)
         VALUES (?1,?1,?2,?3,0,0)",
    )
    .bind(peer_id)
    .bind(host)
    .bind(port)
    .execute(&state.db)
    .await
    .unwrap();
}

fn set_descriptor(peer_id: &str) {
    *TEST_DESCRIPTOR.lock().unwrap_or_else(|e| e.into_inner()) = Some(Ok(LocalDescriptor {
        peer_id: peer_id.to_string(),
        name: "test".into(),
        api_host: "10.0.0.2".into(),
        api_port: 5000,
        version: "test".into(),
        bridges: vec![],
    }));
}

fn open_roundtrip() -> std::sync::MutexGuard<'static, ()> {
    let guard = test_guard();
    reset_client_state();
    TEST_ALLOW_LOOPBACK.store(true, Ordering::Relaxed);
    guard
}

async fn request_via(state: &SharedState, peer_id: &str) -> (StatusCode, Value) {
    let response = lan_cowork_client::routes()
        .with_state(LanCoworkState::from_shared(state))
        .oneshot(
            axum::http::Request::post("/ext/lan_cowork/api/client/pair/request")
                .header("content-type", "application/json")
                .body(Body::from(json!({"peer_id": peer_id}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();
    let status = response.status();
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    (status, serde_json::from_slice(&body).unwrap())
}

#[tokio::test]
async fn task5_success_returns_202_and_confirms_the_nonce() {
    let _guard = open_roundtrip();
    let state = client_state().await;
    let peer_id = local_peer_id_of(&state).await;
    let (port, server) = start_responder(&state, "10.90.0.1").await;
    insert_peer(&state, &peer_id, "127.0.0.1", port.into()).await;
    set_descriptor(&peer_id);

    let (status, body) = request_via(&state, &peer_id).await;
    assert_eq!(status, StatusCode::ACCEPTED, "unexpected body: {body}");
    let request_id = body["request_id"].as_str().unwrap();
    assert!(body["sas"].is_string());
    assert!(lan_cowork_client::peek_entry(&peer_id, request_id).is_some());

    server.abort();
}

#[tokio::test]
async fn task6_two_concurrent_pairings_keep_both_nonces() {
    let _guard = open_roundtrip();
    let state = client_state().await;
    let peer_id = local_peer_id_of(&state).await;
    let (port, server) = start_responder(&state, "10.91.0.3").await;
    insert_peer(&state, &peer_id, "127.0.0.1", port.into()).await;
    set_descriptor(&peer_id);

    let (sa, ba) = request_via(&state, &peer_id).await;
    assert_eq!(sa, StatusCode::ACCEPTED, "{ba}");
    let rid_a = ba["request_id"].as_str().unwrap().to_string();

    let (sb, bb) = request_via(&state, &peer_id).await;
    assert_eq!(sb, StatusCode::ACCEPTED, "{bb}");
    let rid_b = bb["request_id"].as_str().unwrap().to_string();

    assert_ne!(rid_a, rid_b, "each request gets a fresh id");
    assert!(
        lan_cowork_client::peek_entry(&peer_id, &rid_a).is_some(),
        "the second request must not clobber the first nonce"
    );
    assert!(lan_cowork_client::peek_entry(&peer_id, &rid_b).is_some());

    server.abort();
}

#[test]
fn dispatch_routes_never_static_bypass_auth() {
    for path in [
        "/ext/lan_cowork/fleet/update/dispatch",
        "/ext/lan_cowork/fleet/update/dispatch/status",
        "/ext/lan_cowork/fleet/restart/dispatch",
    ] {
        assert!(check_static_bypass(path).is_none(), "{path}");
    }
    assert!(check_static_bypass("/ext/lan_cowork/fleet/update").is_some());
}

async fn route_state(root: &Path) -> LanCoworkState {
    let state = semantic_test_state_with_root(false, String::new(), root.to_path_buf()).await;
    write_config_json(
        &state.config.config_path,
        &json!({"extensions":{"builtin-lan-cowork":{"fleet":{"chief":true}}}}),
    )
    .unwrap();
    let lc = LanCoworkState::from_shared(&state);
    lc.peer_registry
        .set(Arc::new(PeerRegistry::new(
            state.db.clone(),
            Duration::from_secs(30),
            "local".to_owned(),
        )))
        .ok();
    lc
}

fn route_request(path: &str, xrw: bool) -> HttpRequest<Body> {
    let mut builder = HttpRequest::builder()
        .method(Method::POST)
        .uri(path)
        .header(header::CONTENT_TYPE, "application/json");
    if xrw {
        builder = builder.header("X-Requested-With", "test");
    }
    builder.body(Body::from("{}")).unwrap()
}

async fn send_route(app: Router, request: HttpRequest<Body>) -> (StatusCode, Value) {
    let response = app.oneshot(request).await.unwrap();
    let status = response.status();
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    (status, serde_json::from_slice(&body).unwrap())
}

#[tokio::test]
async fn csrf_blocks_both_posts_and_xrw_reaches_handlers() {
    let tmp = tempfile::tempdir().unwrap();
    let lc = route_state(tmp.path()).await;
    for path in [
        "/ext/lan_cowork/fleet/update/dispatch",
        "/ext/lan_cowork/fleet/restart/dispatch",
    ] {
        let app = lan_cowork_fleet_dispatch::routes()
            .layer(middleware::from_fn(crate::csrf::layer))
            .with_state(lc.clone());
        let (status, body) = send_route(app.clone(), route_request(path, false)).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(body, json!({"ok":false,"error":"csrf_required"}));

        let (status, body) = send_route(app, route_request(path, true)).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["error"], "no_peers");
    }
}

// The following tests were relocated from lan-cowork's own lan_cowork_bypass
// module (S4d step 3): they exercise crate::auth::chain::{check_static_bypass,
// run_chain}, a yu-server-internal module not present inside the lan-cowork
// crate, so they cannot compile there. EXPECTED_ROUTES/matching_path are
// duplicated fixtures (mirrors the level_rank duplication precedent).
const EXPECTED_ROUTES: &[(&str, BypassMatch, &str)] = &[
    (
        "/ext/lan_cowork/api/peer/pair/request",
        BypassMatch::Exact,
        "lan_cowork_pairing",
    ),
    (
        "/ext/lan_cowork/api/peer/pair/verify",
        BypassMatch::Exact,
        "lan_cowork_pairing",
    ),
    (
        "/ext/lan_cowork/api/peer/discover",
        BypassMatch::Exact,
        "lan_cowork_discover_status",
    ),
    (
        "/ext/lan_cowork/api/peer/status",
        BypassMatch::Exact,
        "lan_cowork_discover_status",
    ),
    (
        "/ext/lan_cowork/api/peer/register",
        BypassMatch::Exact,
        "lan_cowork_register",
    ),
    (
        "/ext/lan_cowork/api/peer/token/renew",
        BypassMatch::Exact,
        "lan_cowork_token_renew",
    ),
    (
        "/ext/lan_cowork/api/peer/event",
        BypassMatch::Exact,
        "lan_cowork_event",
    ),
    (
        "/ext/lan_cowork/api/peer/heartbeat",
        BypassMatch::Exact,
        "lan_cowork_heartbeat",
    ),
    (
        "/ext/lan_cowork/fleet/consent/request",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/consent/respond",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/consent/pending",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/consent/relay/request",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/consent/relay/status",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/allowlists/grant",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/allowlists/revoke",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/allowlists/check",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/info",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/logs/stream",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/restart",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/update",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/update/status",
        BypassMatch::Exact,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/fleet/consent/status/",
        BypassMatch::SingleSegment,
        "lan_cowork_fleet_peer",
    ),
    (
        "/ext/lan_cowork/api/peer/import/meta",
        BypassMatch::Exact,
        "lan_cowork_remote_import",
    ),
    (
        "/ext/lan_cowork/api/peer/import/diff",
        BypassMatch::Exact,
        "lan_cowork_remote_import",
    ),
    (
        "/ext/lan_cowork/api/peer/import/zip",
        BypassMatch::Exact,
        "lan_cowork_remote_import",
    ),
    (
        "/ext/lan_cowork/api/peer/import/file/",
        BypassMatch::Prefix,
        "lan_cowork_remote_import",
    ),
    (
        "/ext/lan_cowork/api/peer/import/stream/",
        BypassMatch::Prefix,
        "lan_cowork_remote_import",
    ),
];

fn matching_path(pattern: &str, kind: BypassMatch) -> String {
    match kind {
        BypassMatch::Exact => pattern.to_owned(),
        BypassMatch::SingleSegment | BypassMatch::Prefix => format!("{pattern}id"),
    }
}

#[test]
fn routes_match_and_reasons_are_pinned() {
    assert_eq!(BYPASS_ROUTES, EXPECTED_ROUTES);
    for &(pattern, kind, reason) in EXPECTED_ROUTES {
        let path = matching_path(pattern, kind);
        let result = check_static_bypass(&path)
            .unwrap_or_else(|| panic!("{path} must bypass authentication"));
        assert!(result.passed, "{path}");
        assert_eq!(result.reason, reason, "{path}");
    }
}

#[test]
fn prefix_routes_preserve_empty_and_multisegment_tails() {
    for &(pattern, kind, reason) in BYPASS_ROUTES {
        if kind != BypassMatch::Prefix {
            continue;
        }
        for path in [pattern.to_owned(), format!("{pattern}a/b")] {
            assert_eq!(check_static_bypass(&path).unwrap().reason, reason, "{path}");
        }
    }
}

#[test]
fn chain_production_contains_no_lan_cowork_hardcoding() {
    let production = include_str!("../auth/chain.rs")
        .split("\n#[cfg(test)]")
        .next()
        .unwrap();
    assert_eq!(production.matches("lan_cowork").count(), 0);
}

#[test]
fn static_bypass_precedes_api_key_and_quick_lock() {
    let empty = HashSet::new();
    for &(pattern, kind, reason) in EXPECTED_ROUTES {
        let path = matching_path(pattern, kind);
        for auth_header in ["Bearer scoped-key", ""] {
            let result = run_chain(&ChainParams {
                path: &path,
                method: "GET",
                auth_header,
                is_locked: true,
                trusted_proxy_enabled: false,
                remote_addr: "1.2.3.4",
                tcp_peer: "1.2.3.4",
                trusted_ips: &empty,
                trusted_peer_ips: &empty,
                remote_user_header: "",
                session_pin_ok: false,
                cookie_token: "",
                valid_token: "",
            })
            .unwrap();
            assert_eq!(result.reason, reason, "{path}");
        }
    }
}

// The following 3 tests were relocated from lan-cowork's own
// lan_cowork_fleet_peers module (S4d step 3): they exercise
// crate::auth::{middleware::auth_middleware, scope::AuthContext, chain::check_static_bypass}
// and crate::csrf::layer, none of which exist inside the lan-cowork crate.

#[test]
fn fleet_peer_management_never_static_bypasses_auth() {
    for path in [
        "/ext/lan_cowork/fleet/peers",
        "/ext/lan_cowork/fleet/peer-grant",
        "/ext/lan_cowork/fleet/peer-revoke",
        "/ext/lan_cowork/fleet/peer-allowlist-status",
    ] {
        assert!(check_static_bypass(path).is_none(), "{path}");
    }
    assert!(check_static_bypass("/ext/lan_cowork/api/peer/discover").is_some());
}

#[tokio::test]
async fn fleet_peers_csrf_blocks_both_posts_and_xrw_reaches_handlers() {
    let tmp = tempfile::tempdir().unwrap();
    let lc = route_state(tmp.path()).await;
    for path in [
        "/ext/lan_cowork/fleet/peer-grant",
        "/ext/lan_cowork/fleet/peer-revoke",
    ] {
        let app = lan_cowork_fleet_peers::routes()
            .layer(middleware::from_fn(crate::csrf::layer))
            .with_state(lc.clone());
        let (status, body) = send_route(app.clone(), route_request(path, false)).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(body, json!({"ok":false,"error":"csrf_required"}));

        let (status, body) = send_route(app, route_request(path, true)).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(body["error"], "peer_id required");
    }
}

#[tokio::test]
async fn admin_api_key_never_returns_peer_data_and_auth_context_is_not_a_session() {
    let tmp = tempfile::tempdir().unwrap();
    let state = semantic_test_state_with_root(true, String::new(), tmp.path().to_path_buf()).await;
    lan_cowork::schema::apply_standalone_schema(&state.db)
        .await
        .unwrap();
    write_config_json(
        &state.config.config_path,
        &json!({"extensions":{"builtin-lan-cowork":{"fleet":{
            "chief": true,
            "timings":{"peers_poll_interval_sec":3600}
        }}}}),
    )
    .unwrap();
    let lc = LanCoworkState::from_shared(&state);
    lc.peer_registry
        .set(Arc::new(PeerRegistry::new(
            state.db.clone(),
            Duration::from_secs(30),
            "local".to_owned(),
        )))
        .ok();

    let key = "sk_fleet_peer_routes_session_test";
    let hash = hex::encode(Sha256::digest(key.as_bytes()));
    let mut config = load_config_json(&state.config.config_path);
    config["api_keys"] = json!([{
        "id":"fleet-peer-test","key_hash":hash,"key_prefix":"sk_fleet",
        "label":"test","scopes":["admin"]
    }]);
    write_config_json(&state.config.config_path, &config).unwrap();
    let middleware_app = lan_cowork_fleet_peers::routes()
        .layer(middleware::from_fn_with_state(
            state.clone(),
            auth_middleware,
        ))
        .with_state(lc.clone());
    let response = middleware_app
        .oneshot(
            HttpRequest::builder()
                .uri("/ext/lan_cowork/fleet/peers")
                .header(header::AUTHORIZATION, format!("Bearer {key}"))
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert!(response
        .headers()
        .get(header::CONTENT_TYPE)
        .and_then(|value| value.to_str().ok())
        .is_some_and(|value| value.starts_with("text/html")));
    let body = String::from_utf8(
        to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap()
            .to_vec(),
    )
    .unwrap();
    assert!(!body.contains("responder_peer_id"));
    assert!(!body.contains("roles_index"));

    let mut auth_context_request = HttpRequest::builder()
        .method(Method::GET)
        .uri("/ext/lan_cowork/fleet/peers")
        .body(Body::empty())
        .unwrap();
    auth_context_request.extensions_mut().insert(AuthContext {
        reason: "api_key".to_owned(),
        scopes: Some(vec!["admin".to_owned()]),
    });
    let (status, body) = send_route(
        lan_cowork_fleet_peers::routes().with_state(lc.clone()),
        auth_context_request,
    )
    .await;
    assert_eq!(status, StatusCode::UNAUTHORIZED);
    assert_eq!(body, json!({"error":"session required"}));

    let session = tower_sessions::Session::new(None, Arc::new(MemoryStore::default()), None);
    session.insert("pin_ok", true).await.unwrap();
    let mut session_request = HttpRequest::builder()
        .method(Method::GET)
        .uri("/ext/lan_cowork/fleet/peers")
        .body(Body::empty())
        .unwrap();
    session_request.extensions_mut().insert(session);
    let (status, body) = send_route(
        lan_cowork_fleet_peers::routes().with_state(lc),
        session_request,
    )
    .await;
    assert_eq!(status, StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(body["error"], "fleet_manager_not_running");
}

// Relocated from lan-cowork's `lan_cowork_fleet_ops.rs` test module (S4d step 4):
// these exercise `SharedState.log_ring` and `LanCoworkHost::log_open` /
// `set_log_open_seam_hook`, which depend on yu-server's real production
// SharedState/LogRingBuffer types that the lan-cowork crate's TestHost double
// does not carry. The helpers below are minimal duplicates of the originals
// (still present and load-bearing for ~18 other tests in `lan_cowork_fleet_ops.rs`
// — see design decision §3.10(2)); production logic under test is exercised via
// the now-`pub` `lan_cowork_fleet_ops::{routes, local_log_response, parse_lines,
// parse_level}`, never duplicated.

const LOG_TEST_SEED: [u8; 32] = [21; 32];

fn log_test_now() -> i64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap()
        .as_secs() as i64
}

fn log_test_peer(pubkey: [u8; 32]) -> PeerInfo {
    PeerInfo {
        peer_id: "peer".into(),
        name: "peer".into(),
        api_host: "10.0.0.2".into(),
        api_port: 5000,
        token: None,
        token_expires_at: None,
        token_issued_at: None,
        pubkey: Some(pubkey),
        x25519_pk: None,
        version: String::new(),
        bridges: vec![],
        inference_types: vec![],
        gpu: String::new(),
        generating: false,
        queue_depth: 0,
        status: "online".into(),
        last_seen: 0.0,
        session_id: String::new(),
        roles: vec![],
        last_reached_at: None,
        last_attempted_at: None,
    }
}

async fn log_test_peer_state(
    present_in_registry: bool,
    root: &Path,
) -> (SharedState, LanCoworkState, String) {
    use lan_cowork::schema::apply_standalone_schema;
    let state = semantic_test_state_with_root(true, String::new(), root.to_path_buf()).await;
    apply_standalone_schema(&state.db).await.unwrap();
    let key =
        openssl::pkey::PKey::private_key_from_raw_bytes(&LOG_TEST_SEED, openssl::pkey::Id::ED25519)
            .unwrap();
    let public: [u8; 32] = key.raw_public_key().unwrap().try_into().unwrap();
    let token = "fleet-f3a-test-token".to_owned();
    let timestamp = log_test_now();
    sqlx::query("INSERT INTO peers (peer_id,name,api_host,api_port,pubkey,created_at,updated_at) VALUES ('peer','peer','10.0.0.2',5000,?1,0,0)")
        .bind(public.as_slice())
        .execute(&state.db)
        .await
        .unwrap();
    sqlx::query("INSERT INTO peer_tokens (peer_id,token_hash,issued_at,expires_at,revoked_at,source) VALUES ('peer',?1,?2,?3,NULL,'pairing')")
        .bind(lan_cowork::auth::peer_transport::hash_token(&token))
        .bind(timestamp)
        .bind(timestamp + 86_400)
        .execute(&state.db)
        .await
        .unwrap();
    let registry = Arc::new(PeerRegistry::new(
        state.db.clone(),
        Duration::from_secs(30),
        "self".into(),
    ));
    if present_in_registry {
        registry.upsert(log_test_peer(public)).await.unwrap();
    }
    let lc = LanCoworkState::from_shared(&state);
    lc.peer_registry.set(registry).ok();
    (state, lc, token)
}

fn log_test_signed_request_with(
    method: &str,
    uri: &str,
    body: &[u8],
    token: Option<&str>,
    nonce: &str,
) -> HttpRequest<Body> {
    let (path, query) = uri.split_once('?').unwrap_or((uri, ""));
    let mut headers = lan_cowork::auth::peer_transport::sign_headers(
        &LOG_TEST_SEED,
        method,
        path,
        query,
        body,
        log_test_now(),
        nonce,
        "peer",
    );
    if let Some(token) = token {
        headers.insert("authorization", format!("Bearer {token}").parse().unwrap());
    }
    let mut request = HttpRequest::builder()
        .method(method)
        .uri(uri)
        .body(Body::from(body.to_vec()))
        .unwrap();
    *request.headers_mut() = headers;
    request
}

fn log_test_signed_request(uri: &str, token: Option<&str>, nonce: &str) -> HttpRequest<Body> {
    log_test_signed_request_with("GET", uri, &[], token, nonce)
}

async fn log_test_json_body(response: axum::response::Response) -> Value {
    serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap()
}

async fn log_test_session() -> tower_sessions::Session {
    let session = tower_sessions::Session::new(None, Arc::new(MemoryStore::default()), None);
    session.insert("pin_ok", true).await.unwrap();
    session
}

fn log_test_request(uri: &str, session: Option<tower_sessions::Session>) -> HttpRequest<Body> {
    let mut request = HttpRequest::builder().uri(uri).body(Body::empty()).unwrap();
    if let Some(session) = session {
        request.extensions_mut().insert(session);
    }
    request
}

/// `allow_remote_update` is the master switch every remote fleet operation is
/// gated on, log streaming included. It is a separate parameter rather than a
/// constant because a caller that hard-codes it to true can no longer tell the
/// switch apart from the per-route allowlist.
fn log_test_configure_fleet(
    state: &SharedState,
    chief: bool,
    allow: &[&str],
    allow_remote_update: bool,
) {
    write_config_json(
        &state.config.config_path,
        &json!({"extensions":{"builtin-lan-cowork":{"fleet":{
            "chief": chief,
            "allow_log_stream_from": allow,
            "allow_remote_update": allow_remote_update,
        }}}}),
    )
    .unwrap();
}

async fn log_test_empty_stream_state(
    root: &Path,
    local_peer_id: &str,
) -> (SharedState, LanCoworkState) {
    use lan_cowork::schema::apply_standalone_schema;
    let state = semantic_test_state_with_root(true, String::new(), root.to_path_buf()).await;
    apply_standalone_schema(&state.db).await.unwrap();
    let lc = LanCoworkState::from_shared(&state);
    lc.peer_registry
        .set(Arc::new(PeerRegistry::new(
            state.db.clone(),
            Duration::from_secs(30),
            local_peer_id.to_owned(),
        )))
        .ok();
    (state, lc)
}

async fn log_test_insert_identity_seed(state: &SharedState) {
    sqlx::query("INSERT INTO lan_cowork_identity (key, value) VALUES ('ed25519_seed', ?1)")
        .bind(LOG_TEST_SEED.as_slice())
        .execute(&state.db)
        .await
        .unwrap();
}

async fn log_test_first_sse_chunk(response: axum::response::Response) -> String {
    let mut stream = response.into_body().into_data_stream();
    let chunk = tokio::time::timeout(Duration::from_secs(1), stream.next())
        .await
        .unwrap()
        .unwrap()
        .unwrap();
    String::from_utf8(chunk.to_vec()).unwrap()
}

#[tokio::test]
async fn log_peer_positive_and_unauthenticated_self_have_discriminating_controls() {
    // `fleet_logs_stream`'s nonce-required auth path (peer_transport::peer_only)
    // has a `#[cfg(test)]` branch that swaps in a zero-grace nonce store, but
    // that branch only compiles when `lan-cowork` is built as the crate under
    // test -- never when it's linked as an ordinary dependency, which is how
    // yu-server sees it here. So this integration test unavoidably exercises
    // the real, process-wide `nonce_store()` singleton and its genuine
    // NONCE_GRACE_SECS (60s) boot window. Force it to initialize now and wait
    // the window out so the signed request below isn't rejected with 503
    // "nonce grace period" purely because the test ran fast.
    lan_cowork::auth::peer_transport::nonce_store();
    tokio::time::sleep(Duration::from_secs(61)).await;

    let root = tempfile::tempdir().unwrap();
    let (state, lc) = log_test_empty_stream_state(root.path(), "self").await;
    let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM peers WHERE peer_id = 'self'")
        .fetch_one(&state.db_read)
        .await
        .unwrap();
    assert_eq!(count, 0, "self must have no peers row");
    let app = lan_cowork_fleet_ops::routes().with_state(lc.clone());
    let mut self_request = HttpRequest::builder()
        .uri("/ext/lan_cowork/fleet/logs/stream")
        .body(Body::empty())
        .unwrap();
    self_request
        .headers_mut()
        .insert("X-Peer-Id", "self".parse().unwrap());
    let response = app.clone().oneshot(self_request).await.unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        log_test_json_body(response).await,
        json!({"ok":false,"error":"unknown peer"})
    );

    let key =
        openssl::pkey::PKey::private_key_from_raw_bytes(&LOG_TEST_SEED, openssl::pkey::Id::ED25519)
            .unwrap();
    let public = key.raw_public_key().unwrap();
    sqlx::query("INSERT INTO peers (peer_id,name,api_host,api_port,pubkey,created_at,updated_at) VALUES ('peer','peer','10.0.0.2',5000,?1,0,0)")
        .bind(public)
        .execute(&state.db)
        .await
        .unwrap();
    let mut control = HttpRequest::builder()
        .uri("/ext/lan_cowork/fleet/logs/stream")
        .body(Body::empty())
        .unwrap();
    control
        .headers_mut()
        .insert("X-Peer-Id", "peer".parse().unwrap());
    assert_eq!(
        app.oneshot(control).await.unwrap().status(),
        StatusCode::UNAUTHORIZED
    );

    let root = tempfile::tempdir().unwrap();
    let (state, lc, token) = log_test_peer_state(true, root.path()).await;
    log_test_configure_fleet(&state, false, &["peer"], true);
    state.log_ring.push(PartialEntry {
        level: "INFO".into(),
        target: "fleet".into(),
        message: "peer-positive".into(),
        fields: None,
    });
    let response = lan_cowork_fleet_ops::routes()
        .with_state(lc.clone())
        .oneshot(log_test_signed_request(
            "/ext/lan_cowork/fleet/logs/stream?lines=1",
            Some(&token),
            "peer-positive",
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert!(log_test_first_sse_chunk(response)
        .await
        .contains("peer-positive"));

    // Same peer, same allowlist, master switch off. Log streaming ships this
    // node's ring buffer to a remote peer, so an operator who unchecked the
    // switch must not still be serving it. Only this leg fails if the gate is
    // removed -- the leg above passes either way.
    //
    // The nonce must differ from the one above: nonces are single-use, and a
    // replay is rejected with 401 before this route reads any config at all,
    // which would make the leg green without ever reaching the gate.
    log_test_configure_fleet(&state, false, &["peer"], false);
    let response = lan_cowork_fleet_ops::routes()
        .with_state(lc.clone())
        .oneshot(log_test_signed_request(
            "/ext/lan_cowork/fleet/logs/stream?lines=1",
            Some(&token),
            "peer-switch-off",
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::FORBIDDEN);
    assert_eq!(
        log_test_json_body(response).await["error"],
        "remote_update_disabled"
    );
}

#[tokio::test]
async fn log_browser_branch_requires_only_session_and_parses_after_auth() {
    let root = tempfile::tempdir().unwrap();
    let (state, lc) = log_test_empty_stream_state(root.path(), "self").await;
    state.log_ring.push(PartialEntry {
        level: "INFO".into(),
        target: "browser".into(),
        message: "local".into(),
        fields: None,
    });
    let app = lan_cowork_fleet_ops::routes().with_state(lc.clone());
    let response = app
        .clone()
        .oneshot(log_test_request(
            "/ext/lan_cowork/fleet/logs/stream?lines=abc",
            None,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    assert_eq!(
        log_test_json_body(response).await,
        json!({"error":"session required"})
    );

    let response = app
        .clone()
        .oneshot(log_test_request(
            "/ext/lan_cowork/fleet/logs/stream?lines=1",
            Some(log_test_session().await),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert!(log_test_first_sse_chunk(response).await.contains("local"));

    let response = app
        .clone()
        .oneshot(log_test_request(
            "/ext/lan_cowork/fleet/logs/stream?peer_id=self&lines=1",
            Some(log_test_session().await),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::OK);
    assert!(log_test_first_sse_chunk(response).await.contains("local"));

    let response = app
        .oneshot(log_test_request(
            "/ext/lan_cowork/fleet/logs/stream?lines=abc",
            Some(log_test_session().await),
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);

    let disabled = semantic_test_state_with(true, String::new()).await;
    let response = lan_cowork_fleet_ops::routes()
        .with_state(LanCoworkState::from_shared(&disabled))
        .oneshot(log_test_request(
            "/ext/lan_cowork/fleet/logs/stream?lines=abc",
            None,
        ))
        .await
        .unwrap();
    assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
    assert_eq!(
        log_test_json_body(response).await,
        json!({"error":"service_unavailable"})
    );
}

#[tokio::test]
async fn log_sse_backlog_payload_headers_levels_and_line_clamps_match_python() {
    let state = semantic_test_state_with(true, String::new()).await;
    for (level, target, message) in [
        ("DEBUG", "old", "old"),
        ("WARN", "worker", "warning"),
        ("TRACE", "trace-source", "trace"),
    ] {
        state.log_ring.push(PartialEntry {
            level: level.into(),
            target: target.into(),
            message: message.into(),
            fields: Some(serde_json::Map::new()),
        });
    }
    let response =
        lan_cowork_fleet_ops::local_log_response(state.clone(), 2, None, "198.51.100.10");
    assert_eq!(
        response.headers()[axum::http::header::CONTENT_TYPE],
        "text/event-stream"
    );
    assert_eq!(
        response.headers()[axum::http::header::CACHE_CONTROL],
        "no-cache"
    );
    assert_eq!(response.headers()["x-accel-buffering"], "no");
    assert_eq!(response.headers().len(), 3);
    assert!(!response
        .headers()
        .contains_key(axum::http::header::CONNECTION));
    let mut stream = response.into_body().into_data_stream();
    let first = stream.next().await.unwrap().unwrap();
    let second = stream.next().await.unwrap().unwrap();
    let first = String::from_utf8(first.to_vec()).unwrap();
    let second = String::from_utf8(second.to_vec()).unwrap();
    assert!(first.contains("event: log"));
    assert!(first.contains("\"source\":\"worker\""));
    assert!(first.contains("\"level\":\"WARNING\""));
    assert!(!first.contains("\"target\""));
    assert!(!first.contains("\"fields\""));
    assert!(second.contains("\"source\":\"trace-source\""));
    assert!(second.contains("\"level\":\"DEBUG\""));

    assert_eq!(lan_cowork_fleet_ops::parse_lines(None), Ok(200));
    assert_eq!(lan_cowork_fleet_ops::parse_lines(Some("0")), Ok(1));
    assert_eq!(lan_cowork_fleet_ops::parse_lines(Some("1001")), Ok(1000));
    assert_eq!(lan_cowork_fleet_ops::parse_lines(Some("-5")), Ok(1));
    assert_eq!(
        lan_cowork_fleet_ops::parse_lines(Some("999999999999999999999999999999")),
        Ok(1000)
    );
    assert_eq!(
        lan_cowork_fleet_ops::parse_lines(Some("-999999999999999999999999999999")),
        Ok(1)
    );
    assert_eq!(lan_cowork_fleet_ops::parse_lines(Some("abc")), Err(()));
    assert_eq!(lan_cowork_fleet_ops::parse_level(Some("error")), None);

    let count_ring = LogRingBuffer::new(1100);
    for index in 0..1001 {
        count_ring.push(PartialEntry {
            level: "INFO".into(),
            target: "count".into(),
            message: index.to_string(),
            fields: None,
        });
    }
    for (raw, expected) in [("0", 1), ("1001", 1000), ("-5", 1)] {
        assert_eq!(
            count_ring
                .recent(
                    lan_cowork_fleet_ops::parse_lines(Some(raw)).unwrap(),
                    None,
                    None
                )
                .len(),
            expected
        );
    }

    let state = semantic_test_state_with(true, String::new()).await;
    state.log_ring.push(PartialEntry {
        level: "DEBUG".into(),
        target: "case".into(),
        message: "lowercase-is-unfiltered".into(),
        fields: None,
    });
    assert!(
        log_test_first_sse_chunk(lan_cowork_fleet_ops::local_log_response(
            state.clone(),
            1,
            lan_cowork_fleet_ops::parse_level(Some("error")),
            "198.51.100.11"
        ))
        .await
        .contains("lowercase-is-unfiltered")
    );
}

#[tokio::test]
async fn log_sse_live_filter_seam_close_and_connection_budget_are_pinned() {
    let state = semantic_test_state_with(true, String::new()).await;
    let response = lan_cowork_fleet_ops::local_log_response(
        state.clone(),
        8,
        Some("WARNING"),
        "198.51.100.12",
    );
    state.log_ring.push(PartialEntry {
        level: "INFO".into(),
        target: "live".into(),
        message: "filtered".into(),
        fields: None,
    });
    state.log_ring.push(PartialEntry {
        level: "WARN".into(),
        target: "live".into(),
        message: "visible".into(),
        fields: None,
    });
    let chunk = log_test_first_sse_chunk(response).await;
    assert!(chunk.contains("visible"));
    assert!(!chunk.contains("filtered"));

    set_log_open_seam_hook(|ring| {
        ring.push(PartialEntry {
            level: "INFO".into(),
            target: "seam".into(),
            message: "between-subscribe-and-recent".into(),
            fields: None,
        });
    });
    let (mut live, backlog) = state.log_open(8, None);
    let live_has_it = live.next().now_or_never().flatten().is_some_and(|event| {
        matches!(event, LogEvent::Line(line) if line.message == "between-subscribe-and-recent")
    });
    assert!(
        backlog
            .iter()
            .any(|entry| entry.message == "between-subscribe-and-recent")
            || live_has_it
    );

    let state = semantic_test_state_with(true, String::new()).await;
    let response =
        lan_cowork_fleet_ops::local_log_response(state.clone(), 1, None, "198.51.100.13");
    drop(state);
    assert_eq!(
        log_test_first_sse_chunk(response).await,
        "event: close\ndata: {}\n\n"
    );

    let state = semantic_test_state_with(true, String::new()).await;
    let budget_ip = "198.51.100.14";
    let mut fleet_streams = Vec::new();
    for _ in 0..3 {
        let response = lan_cowork_fleet_ops::local_log_response(state.clone(), 1, None, budget_ip);
        assert_eq!(response.status(), StatusCode::OK);
        fleet_streams.push(response);
    }
    let over_limit = lan_cowork_fleet_ops::local_log_response(state.clone(), 1, None, budget_ip);
    assert_eq!(over_limit.status(), StatusCode::TOO_MANY_REQUESTS);

    // Dropping one open stream releases its slot (Drop-guard release, mirroring
    // core's LogConnectionGuard), so a new connection is allowed again.
    fleet_streams.pop();
    let after_drop = lan_cowork_fleet_ops::local_log_response(state.clone(), 1, None, budget_ip);
    assert_eq!(after_drop.status(), StatusCode::OK);
    drop(fleet_streams);
    drop(after_drop);

    // Core's own log-viewer SSE budget (`logs::ring::LogRingBuffer`) is a
    // separate, independently-enforced counter from the fleet-log budget above.
    let ip: std::net::IpAddr = "127.0.0.1".parse().unwrap();
    assert!(state.log_ring.register_connection(ip));
    assert!(state.log_ring.register_connection(ip));
    assert!(state.log_ring.register_connection(ip));
    assert!(!state.log_ring.register_connection(ip));
}

// Suppress "unused" lint for the identity-seed helper: kept for parity with the
// original `insert_identity_seed`, available to future relocated tests in this
// group even though none of the 4 above currently call it.
#[allow(dead_code)]
async fn _log_test_insert_identity_seed_is_reachable(state: &SharedState) {
    log_test_insert_identity_seed(state).await;
}

// --- Relocated from `lan_cowork_local_import.rs`, `lan_cowork_settings.rs`,
// and `lan_cowork_fleet_ui.rs` (S4d step 4): each of the following exercises
// `auth_middleware` (or, for the query-logging test, yu-server's own
// `logs::tracing_layer::TracingLayer`/`LogRingBuffer`), none of which lan-cowork
// can reach across the crate boundary. See those files' `mod tests` for the
// "relocated to yu-server's `lan_cowork_split_integration_tests.rs`" markers.

mod relocated_local_import {
    use super::*;
    use lan_cowork::routes::lan_cowork_local_import;

    const SESSIONS_PATH: &str = "/ext/lan_cowork/api/peer/import/sessions";
    const EXECUTE_PATH: &str = "/ext/lan_cowork/api/peer/import/execute";
    const INDEX_PATH: &str = "/ext/lan_cowork/api/peer/import/index";

    async fn test_state(root: &Path) -> SharedState {
        let state = semantic_test_state_with_root(false, String::new(), root.join("project")).await;
        sqlx::raw_sql(
            "CREATE TABLE import_session (
                id TEXT PRIMARY KEY, peer_id TEXT NOT NULL, peer_name TEXT NOT NULL,
                mode TEXT NOT NULL, status TEXT NOT NULL, last_seen_rowid INTEGER,
                snapshot_max_rowid INTEGER, total_files INTEGER, done_files INTEGER NOT NULL,
                import_folder TEXT NOT NULL, options TEXT NOT NULL,
                created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL
            );",
        )
        .execute(&state.db)
        .await
        .unwrap();
        state
    }

    fn app_with_auth(state: &SharedState) -> Router {
        lan_cowork_local_import::routes()
            .layer(middleware::from_fn_with_state(
                state.clone(),
                auth_middleware,
            ))
            .with_state(LanCoworkState::from_shared(state))
    }

    #[tokio::test]
    async fn execute_route_rejects_api_key_without_session() {
        let tmp = tempfile::tempdir().unwrap();
        let key = "sk_execute_session_test";
        std::fs::create_dir_all(tmp.path().join("project")).unwrap();
        std::fs::write(
            tmp.path().join("project").join("config.json"),
            json!({"api_keys":[{"id":"execute","key_hash":hex::encode(Sha256::digest(key.as_bytes())),"key_prefix":"sk_execute","label":"test","scopes":["admin"]}]}).to_string(),
        )
        .unwrap();
        let mut state = test_state(tmp.path()).await;
        Arc::get_mut(&mut state).unwrap().config.pin_auth_enabled = true;
        let response = app_with_auth(&state)
            .oneshot(
                HttpRequest::builder()
                    .method("POST")
                    .uri(EXECUTE_PATH)
                    .header(header::AUTHORIZATION, format!("Bearer {key}"))
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from(r#"{"session_id":"run"}"#))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            log_test_json_body(response).await,
            json!({"ok":false,"error":"session required"})
        );
    }

    #[tokio::test]
    async fn valid_api_key_without_session_reaches_route_and_is_rejected() {
        let tmp = tempfile::tempdir().unwrap();
        let key = "sk_local_import_session_test";
        let hash = hex::encode(Sha256::digest(key.as_bytes()));
        std::fs::create_dir_all(tmp.path().join("project")).unwrap();
        std::fs::write(
            tmp.path().join("project").join("config.json"),
            json!({"api_keys":[{
                "id":"local-import-test", "key_hash":hash, "key_prefix":"sk_local_i",
                "label":"test", "scopes":["admin"]
            }]})
            .to_string(),
        )
        .unwrap();
        let mut state = test_state(tmp.path()).await;
        Arc::get_mut(&mut state).unwrap().config.pin_auth_enabled = true;
        let response = app_with_auth(&state)
            .oneshot(
                HttpRequest::builder()
                    .uri(SESSIONS_PATH)
                    .header(header::AUTHORIZATION, format!("Bearer {key}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            log_test_json_body(response).await,
            json!({"ok": false, "error": "session required"})
        );
    }

    #[tokio::test]
    async fn index_route_requires_session_and_rejects_api_key_without_session() {
        let tmp = tempfile::tempdir().unwrap();
        let mut state = test_state(tmp.path()).await;
        Arc::get_mut(&mut state).unwrap().config.pin_auth_enabled = true;
        // No `auth_middleware` layer here (matches the original test): the
        // route handler's own `require_session()` guard must fire directly.
        let response = lan_cowork_local_import::routes()
            .with_state(LanCoworkState::from_shared(&state))
            .oneshot(
                HttpRequest::builder()
                    .method("POST")
                    .uri(INDEX_PATH)
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            log_test_json_body(response).await,
            json!({"ok":false,"error":"session required"})
        );

        let tmp = tempfile::tempdir().unwrap();
        let key = "sk_index_session_test";
        std::fs::create_dir_all(tmp.path().join("project")).unwrap();
        std::fs::write(
            tmp.path().join("project").join("config.json"),
            json!({"api_keys":[{"id":"index","key_hash":hex::encode(Sha256::digest(key.as_bytes())),"key_prefix":"sk_index","label":"test","scopes":["admin"]}]}).to_string(),
        )
        .unwrap();
        let mut state = test_state(tmp.path()).await;
        Arc::get_mut(&mut state).unwrap().config.pin_auth_enabled = true;
        let response = app_with_auth(&state)
            .oneshot(
                HttpRequest::builder()
                    .method("POST")
                    .uri(INDEX_PATH)
                    .header(header::AUTHORIZATION, format!("Bearer {key}"))
                    .header(header::CONTENT_TYPE, "application/json")
                    .body(Body::from("{}"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            log_test_json_body(response).await,
            json!({"ok":false,"error":"session required"})
        );
    }
}

mod relocated_settings {
    use super::*;
    use lan_cowork::routes::lan_cowork_settings;
    use tracing_subscriber::layer::SubscriberExt;

    const PATH: &str = "/ext/lan_cowork/api/settings/fleet/my-permissions";

    async fn test_state(root: &Path, pin_auth_enabled: bool) -> (SharedState, LanCoworkState) {
        let state =
            semantic_test_state_with_root(pin_auth_enabled, String::new(), root.to_path_buf())
                .await;
        lan_cowork::schema::apply_standalone_schema(&state.db)
            .await
            .unwrap();
        let lc = LanCoworkState::from_shared(&state);
        lc.peer_registry
            .set(Arc::new(PeerRegistry::new(
                state.db.clone(),
                Duration::from_secs(30),
                "local".to_owned(),
            )))
            .ok();
        (state, lc)
    }

    fn peer(peer_id: &str, port: u16) -> PeerInfo {
        PeerInfo {
            peer_id: peer_id.to_owned(),
            name: peer_id.to_owned(),
            api_host: "127.0.0.1".to_owned(),
            api_port: port,
            token: Some(format!("token-{peer_id}")),
            token_expires_at: None,
            token_issued_at: None,
            pubkey: None,
            x25519_pk: None,
            version: String::new(),
            bridges: Vec::new(),
            inference_types: Vec::new(),
            gpu: String::new(),
            generating: false,
            queue_depth: 0,
            status: "online".to_owned(),
            last_seen: 0.0,
            session_id: String::new(),
            roles: Vec::new(),
            last_reached_at: None,
            last_attempted_at: None,
        }
    }

    #[tokio::test]
    async fn admin_api_key_without_session_is_rejected_by_handler() {
        let _guard = test_guard();
        reset_client_state();
        let tmp = tempfile::tempdir().unwrap();
        let key = "sk_my_permissions_session_test";
        let hash = hex::encode(Sha256::digest(key.as_bytes()));
        std::fs::write(
            tmp.path().join("config.json"),
            json!({"api_keys":[{
                "id":"my-permissions-test", "key_hash":hash,
                "key_prefix":"sk_my_per", "label":"test", "scopes":["admin"]
            }]})
            .to_string(),
        )
        .unwrap();
        let (state, lc) = test_state(tmp.path(), true).await;
        let app = lan_cowork_settings::routes()
            .layer(middleware::from_fn_with_state(
                state.clone(),
                auth_middleware,
            ))
            .with_state(lc.clone());
        let response = app
            .oneshot(
                HttpRequest::builder()
                    .uri(PATH)
                    .header(header::AUTHORIZATION, format!("Bearer {key}"))
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        assert_eq!(
            log_test_json_body(response).await,
            json!({"ok":false,"error":"session required"})
        );
    }

    // Drives the real `my_permissions` handler (via HTTP, its only public
    // surface) so `log_query_complete` -- private to `lan_cowork_settings` and
    // unreachable across the crate boundary -- fires for real, and checks the
    // resulting event through yu-server's own tracing sink: production
    // `tracing::debug!` calls are captured by whatever subscriber is installed
    // at the call site, regardless of which crate emits them.
    #[tokio::test]
    async fn query_logging_has_positive_control_without_secrets() {
        let _guard = test_guard();
        reset_client_state();
        let tmp = tempfile::tempdir().unwrap();
        let (state, lc) = test_state(tmp.path(), false).await;
        let registry = lc.peer_registry.get().unwrap().clone();
        for (id, expiry) in [("unlimited", None), ("future", Some(log_test_now() + 60))] {
            let mut included = peer(id, 1);
            included.status = "offline".to_owned();
            included.token_expires_at = expiry;
            registry.insert_for_test(included);
        }

        let ring = Arc::new(LogRingBuffer::new(8));
        let subscriber = tracing_subscriber::registry().with(
            crate::logs::tracing_layer::TracingLayer::new(ring.clone(), tracing::Level::DEBUG),
        );
        let _tracing_guard = tracing::subscriber::set_default(subscriber);
        let response = lan_cowork_settings::routes()
            .with_state(lc)
            .oneshot(
                HttpRequest::builder()
                    .uri(PATH)
                    .extension(log_test_session().await)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        drop(_tracing_guard);
        drop(state);

        let entries = ring.recent(8, Some("DEBUG"), None);
        let entry = entries
            .iter()
            .find(|entry| entry.message == "LAN Cowork permissions queried")
            .unwrap();
        assert_eq!(
            entry
                .fields
                .as_ref()
                .and_then(|fields| fields.get("peer_count")),
            Some(&json!(2))
        );
        let logged = serde_json::to_string(entry).unwrap();
        for secret in ["token", "authorization", "x-peer", "body", "signature"] {
            assert!(!logged.to_ascii_lowercase().contains(secret));
        }
    }
}

mod relocated_fleet_ui {
    use super::*;
    use lan_cowork::routes::lan_cowork_fleet_ui;
    use tower_http::services::ServeDir;

    const FLEET_HTML: &str =
        r#"<main nonce="{{ csp_nonce }}"><!-- NAV_PLACEHOLDER -->Fleet</main>"#;
    const FLEET_JS: &str = "window.fleetAdminLoaded = true;";

    async fn state(
        root: &Path,
        registry: bool,
        chief: bool,
        nav: Option<&str>,
    ) -> (SharedState, LanCoworkState) {
        std::fs::create_dir_all(root.join("extensions/builtin_lan_cowork/ui/fleet")).unwrap();
        std::fs::create_dir_all(root.join("ui/default/templates")).unwrap();
        std::fs::write(
            root.join("config.json"),
            json!({"extensions":{"builtin-lan-cowork":{"fleet":{"chief":chief}}}}).to_string(),
        )
        .unwrap();
        if let Some(nav) = nav {
            std::fs::write(root.join("ui/default/templates/_nav.html"), nav).unwrap();
        }
        let shared = semantic_test_state_with_root(true, String::new(), root.to_path_buf()).await;
        let lc = LanCoworkState::from_shared(&shared);
        if registry {
            lc.peer_registry
                .set(Arc::new(PeerRegistry::new(
                    shared.db.clone(),
                    Duration::from_secs(30),
                    "local".to_owned(),
                )))
                .ok();
        }
        (shared, lc)
    }

    async fn call(lc: LanCoworkState, nonce: &str) -> (StatusCode, String, String) {
        let response = lan_cowork_fleet_ui::fleet_ui(
            axum::extract::State(lc),
            axum::extract::Extension(lan_cowork::routes::lan_cowork_host::FleetUiNonce(
                nonce.to_owned(),
            )),
        )
        .await;
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        (
            status,
            String::new(),
            String::from_utf8(body.to_vec()).unwrap(),
        )
    }

    fn static_app(shared: SharedState, lc: LanCoworkState) -> Router {
        let root = shared
            .config
            .project_root
            .join("extensions/builtin_lan_cowork/ui/fleet");
        let fleet_ui_router: Router<SharedState> = lan_cowork_fleet_ui::routes().with_state(lc);
        Router::new()
            .merge(fleet_ui_router)
            .nest_service("/ext/lan_cowork/fleet/static", ServeDir::new(root))
            .layer(middleware::from_fn_with_state(
                shared.clone(),
                auth_middleware,
            ))
            .with_state(shared)
    }

    async fn request(app: Router, uri: &str, authenticated: bool) -> (StatusCode, String) {
        let mut request = HttpRequest::get(uri).body(Body::empty()).unwrap();
        if authenticated {
            request.extensions_mut().insert(log_test_session().await);
        }
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        (status, String::from_utf8(body.to_vec()).unwrap())
    }

    #[tokio::test]
    async fn ui_renders_nav_with_all_context_keys() {
        let root = tempfile::tempdir().unwrap();
        let nav = r#"<nav nonce="{{ csp_nonce }}" data-v="{{ dist_v }}">{{ active }}</nav>"#;
        let (_, lc) = state(root.path(), true, true, Some(nav)).await;
        std::fs::write(
            root.path()
                .join("extensions/builtin_lan_cowork/ui/fleet/fleet.html"),
            FLEET_HTML,
        )
        .unwrap();

        let (_, _, body) = call(lc, "test-nonce").await;
        assert!(body.contains(r#"<nav nonce="test-nonce" data-v="dev">fleet</nav>"#));
        assert!(!body.contains("<!-- NAV_PLACEHOLDER -->"));
    }

    #[tokio::test]
    async fn static_file_requires_and_accepts_session() {
        let root = tempfile::tempdir().unwrap();
        let (shared, lc) = state(root.path(), false, false, None).await;
        std::fs::write(
            root.path()
                .join("extensions/builtin_lan_cowork/ui/fleet/fleet.js"),
            FLEET_JS,
        )
        .unwrap();

        let (status, body) = request(
            static_app(shared.clone(), lc.clone()),
            "/ext/lan_cowork/fleet/static/fleet.js",
            true,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(body, FLEET_JS);

        let (status, body) = request(
            static_app(shared, lc),
            "/ext/lan_cowork/fleet/static/fleet.js",
            false,
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert!(body.contains("PIN 認証"));
        assert!(!body.contains(FLEET_JS));
    }

    #[tokio::test]
    async fn static_path_traversal_is_404() {
        let root = tempfile::tempdir().unwrap();
        let (shared, lc) = state(root.path(), false, false, None).await;
        std::fs::create_dir_all(root.path().join("extensions/etc")).unwrap();
        std::fs::write(root.path().join("extensions/etc/passwd"), "escaped").unwrap();
        let (status, _) = request(
            static_app(shared, lc),
            "/ext/lan_cowork/fleet/static/%2e%2e/%2e%2e/%2e%2e/etc/passwd",
            true,
        )
        .await;
        assert_eq!(status, StatusCode::NOT_FOUND);
    }
}

// --- Cross-crate consistency check for `level_rank` (S4d step 4, design decision
// §3.10(1)): lan-cowork duplicates yu-server's `logs::ring::level_rank` because the
// original is `pub(crate)` to yu-server and unreachable across the crate boundary.
// This test asserts both copies stay in lockstep; a future edit to one without the
// other fails here rather than silently diverging log-level filtering behavior.
mod relocated_level_rank_consistency {
    use crate::logs::ring::level_rank as yu_server_level_rank;
    use lan_cowork::routes::lan_cowork_fleet_ops::level_rank as lan_cowork_level_rank;

    #[test]
    fn lan_cowork_and_yu_server_level_rank_agree() {
        for level in [
            "TRACE", "DEBUG", "INFO", "WARN", "ERROR", "UNKNOWN", "", "warn",
        ] {
            assert_eq!(
                lan_cowork_level_rank(level),
                yu_server_level_rank(level),
                "level_rank mismatch for {level:?}"
            );
        }
    }
}
