use std::collections::HashSet;

use axum::{
    body::Bytes,
    extract::{Extension, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use tower_sessions::Session;

use crate::{
    auth::client_ip::ClientIp,
    restart::{
        is_local_request, launch_restart, restart_args, restart_token_matches, session_pin_ok,
        RestartConfig, RestartCooldown, RESTART_CONFIG, RESTART_STATE,
    },
    state::SharedState,
};

fn reply(
    status: StatusCode,
    error: Option<&str>,
    code: &str,
    hint: Option<&str>,
    data: Value,
) -> Response {
    let mut body = json!({"ok": error.is_none(), "error": error, "code": code, "data": data});
    if let Some(hint) = hint {
        body["hint"] = json!(hint);
    }
    (status, Json(body)).into_response()
}

/// Shared by the restart route and `server_info`'s `api_server_info` --
/// both need the SAME notion of "local" for the same request (design-advisor
/// M1: computing it twice, even from identical inputs, is how a third
/// definition creeps in later). Spawn-blocking wraps `is_local_request`
/// itself; callers must not add a cache on top of this.
pub(crate) async fn local_request(
    state: &SharedState,
    client_ip: Option<Extension<ClientIp>>,
    headers: HeaderMap,
) -> bool {
    let Some(Extension(ClientIp(ip))) = client_ip else {
        return false;
    };
    let trusted: HashSet<String> = if state.config.trusted_proxy_enabled {
        state.config.trusted_ips.clone()
    } else {
        HashSet::new()
    };
    tokio::task::spawn_blocking(move || is_local_request(&ip, &headers, &trusted))
        .await
        .unwrap_or(false)
}

fn confirm_restart(body: &Value) -> bool {
    ["confirm", "action", "cmd"]
        .iter()
        .any(|key| body.get(*key).and_then(Value::as_str) == Some("restart"))
}

fn remote_access(
    config: &RestartConfig,
    is_local: bool,
    headers: &HeaderMap,
    body: &Value,
) -> Result<(), Response> {
    if is_local {
        return Ok(());
    }
    if !config.allow_remote_restart {
        return Err(reply(
            StatusCode::FORBIDDEN,
            Some("remote restart is local only"),
            "local_only",
            None,
            Value::Null,
        ));
    }
    let Some(expected) = config.token.as_deref() else {
        return Err(reply(
            StatusCode::FORBIDDEN,
            Some("restart token is required"),
            "remote_token_missing",
            Some("Set TAGDB_RESTART_TOKEN or server.restart_token."),
            Value::Null,
        ));
    };
    let supplied = headers
        .get("x-restart-token")
        .and_then(|value| value.to_str().ok())
        .or_else(|| {
            ["restart_token", "restartToken", "token"]
                .iter()
                .find_map(|key| body.get(*key).and_then(Value::as_str))
        })
        .unwrap_or("");
    if restart_token_matches(expected, supplied) {
        Ok(())
    } else {
        Err(reply(
            StatusCode::UNAUTHORIZED,
            Some("restart token is invalid"),
            "remote_token_invalid",
            None,
            Value::Null,
        ))
    }
}

fn cooldown_error(cooldown: RestartCooldown) -> Response {
    reply(
        StatusCode::TOO_MANY_REQUESTS,
        Some("restart is cooling down"),
        "restart_cooldown",
        None,
        json!({"remaining_seconds": cooldown.remaining_seconds}),
    )
}

/// POST /api/server/restart.  The body stays as bytes because Axum's Json
/// rejection cannot preserve Python's three distinct malformed-body codes.
pub async fn restart(
    State(state): State<SharedState>,
    headers: HeaderMap,
    client_ip: Option<Extension<ClientIp>>,
    session: Option<Extension<Session>>,
    body: Bytes,
) -> Response {
    let Some(config) = RESTART_CONFIG.get() else {
        return reply(
            StatusCode::FORBIDDEN,
            Some("restart is disabled"),
            "restart_disabled",
            Some("Restart configuration is unavailable."),
            Value::Null,
        );
    };
    let pin_ok = session_pin_ok(session).await;
    let is_local = local_request(&state, client_ip, headers.clone()).await;
    if !config.allow_restart {
        return reply(
            StatusCode::FORBIDDEN,
            Some("restart is disabled"),
            "restart_disabled",
            Some("Enable restart with TAGDB_ALLOW_RESTART or server.allow_restart."),
            Value::Null,
        );
    }
    if state.config.pin_auth_enabled && !pin_ok {
        return reply(
            StatusCode::UNAUTHORIZED,
            Some("再起動にはPIN認証済みセッションが必要です"),
            "pin_auth_required",
            None,
            Value::Null,
        );
    }
    if !state.config.pin_auth_enabled && !is_local {
        return reply(
            StatusCode::FORBIDDEN,
            Some("PIN認証が無効のためリモートからの再起動は許可されていません"),
            "pin_required",
            None,
            Value::Null,
        );
    }
    if !headers.get(header::CONTENT_TYPE).is_some_and(|value| {
        value.to_str().is_ok_and(|value| {
            value
                .split(';')
                .next()
                .is_some_and(|kind| kind.trim().eq_ignore_ascii_case("application/json"))
        })
    }) {
        return reply(
            StatusCode::BAD_REQUEST,
            Some("JSON content type required"),
            "invalid_content_type",
            None,
            Value::Null,
        );
    }
    let body: Value = match serde_json::from_slice(&body) {
        Ok(body) => body,
        Err(_) => {
            return reply(
                StatusCode::BAD_REQUEST,
                Some("invalid JSON"),
                "invalid_json",
                None,
                Value::Null,
            )
        }
    };
    if !body.is_object() {
        return reply(
            StatusCode::BAD_REQUEST,
            Some("JSON object required"),
            "invalid_json_object",
            None,
            Value::Null,
        );
    }
    if !confirm_restart(&body) {
        return reply(
            StatusCode::BAD_REQUEST,
            Some("confirm='restart' が必要です"),
            "confirm_required",
            None,
            Value::Null,
        );
    }
    if let Err(response) = remote_access(config, is_local, &headers, &body) {
        return response;
    }
    let reservation = match RESTART_STATE.enforce_restart_cooldown() {
        Ok(reservation) => reservation,
        Err(cooldown) => return cooldown_error(cooldown),
    };
    let args = match restart_args() {
        Ok(args) => args,
        Err(_) => {
            return reply(
                StatusCode::INTERNAL_SERVER_ERROR,
                Some("restart arguments unavailable"),
                "restart_args_missing",
                None,
                Value::Null,
            )
        }
    };
    launch_restart(reservation, args);
    reply(
        StatusCode::OK,
        None,
        "restart_accepted",
        None,
        json!({"accepted": true, "message": "Restart accepted."}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;

    async fn response_json(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    /// A single permissive `RestartConfig` shared by every test in this module
    /// that must go through the real `restart()` handler. `RESTART_CONFIG` is
    /// a process-wide `OnceLock` (only the first successful `.set()` in the
    /// whole test binary sticks), so every test that needs it calls this with
    /// the SAME values -- whichever test runs first "wins" and the rest see
    /// an identical value, which keeps the race harmless.
    fn ensure_test_restart_config() {
        let _ = RESTART_CONFIG.set(RestartConfig {
            allow_restart: true,
            allow_remote_restart: false,
            token: None,
            enable_source: "test",
            remote_source: "test",
            token_source: "test",
        });
    }

    async fn session_with_pin_ok(pin_ok: bool) -> Session {
        let session = Session::new(
            None,
            std::sync::Arc::new(tower_sessions::MemoryStore::default()),
            None,
        );
        session.insert("pin_ok", pin_ok).await.unwrap();
        session
    }

    // --- reply() envelope (Task 4 row: "drop `ok` from the envelope") ------

    // NOTE: this test only pins the status code `reply()` is given -- it does
    // NOT check the `ok`/`error`/`code`/`data` fields despite its old name
    // having claimed to. `reply_envelope_json_shape` below is what actually
    // asserts those fields (plus `hint`).
    #[test]
    fn reply_sets_the_status_code_it_is_given() {
        let success = reply(
            StatusCode::OK,
            None,
            "restart_accepted",
            None,
            json!({"accepted": true}),
        );
        assert_eq!(success.status(), StatusCode::OK);

        let failure = reply(
            StatusCode::FORBIDDEN,
            Some("restart is disabled"),
            "restart_disabled",
            Some("enable it"),
            Value::Null,
        );
        assert_eq!(failure.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn reply_envelope_json_shape() {
        let ok_body = response_json(reply(
            StatusCode::OK,
            None,
            "restart_accepted",
            None,
            json!({"accepted": true}),
        ))
        .await;
        assert_eq!(ok_body["ok"], true);
        assert_eq!(ok_body["error"], Value::Null);
        assert_eq!(ok_body["code"], "restart_accepted");
        assert_eq!(ok_body["data"]["accepted"], true);
        // hint=None must OMIT the key entirely, not emit `"hint": null` --
        // matches Python's `if hint: payload["hint"] = hint`
        // (core/infra_core/api_errors.py:43-44).
        assert!(
            !ok_body.as_object().unwrap().contains_key("hint"),
            "hint key must be absent when hint is None: {ok_body:?}"
        );

        let err_body = response_json(reply(
            StatusCode::FORBIDDEN,
            Some("restart is disabled"),
            "restart_disabled",
            Some("enable it"),
            Value::Null,
        ))
        .await;
        assert_eq!(err_body["ok"], false);
        assert_eq!(err_body["error"], "restart is disabled");
        assert_eq!(err_body["code"], "restart_disabled");
        // decision 6 / spec 決定6: restart_disabled carries a hint, and it
        // must actually reach the body (row: "hint reaches the body").
        assert_eq!(err_body["hint"], "enable it");
    }

    // --- local_request / decision 2 (trusted set gated by trusted_proxy_enabled) --

    #[tokio::test]
    async fn local_request_ignores_trusted_ips_when_trusted_proxy_disabled() {
        // Misconfiguration guard: trusted_proxy_enabled=false but trusted_ips
        // is non-empty anyway. `local_request` must pass an EMPTY set to
        // `is_local_request` in this case (spec 決定 2), so an untrusted
        // X-Forwarded-For hint still disqualifies the request even though the
        // peer itself is loopback.
        let mut trusted = HashSet::new();
        trusted.insert("127.0.0.1".to_string());
        let state = crate::state::restart_test_state(false, false, trusted).await;

        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "10.0.0.9".parse().unwrap());
        let client_ip = Some(Extension(ClientIp("127.0.0.1".to_string())));

        let is_local = local_request(&state, client_ip, headers).await;
        assert!(
            !is_local,
            "trusted_ips must be ignored when trusted_proxy_enabled is false"
        );
    }

    #[tokio::test]
    async fn local_request_honors_trusted_ips_when_trusted_proxy_enabled() {
        // Sanity counterpart: with trusted_proxy_enabled=true and the peer
        // itself listed as trusted, the same forwarding hint is accepted.
        let mut trusted = HashSet::new();
        trusted.insert("127.0.0.1".to_string());
        let state = crate::state::restart_test_state(false, true, trusted).await;

        let mut headers = HeaderMap::new();
        headers.insert("x-forwarded-for", "10.0.0.9".parse().unwrap());
        let client_ip = Some(Extension(ClientIp("127.0.0.1".to_string())));

        let is_local = local_request(&state, client_ip, headers).await;
        assert!(is_local);
    }

    // --- decision 1: an API-key-authenticated request with no PIN session --
    // --- must be treated as pin_ok == false, never bypassed. ---------------

    #[tokio::test]
    async fn restart_requires_pin_session_even_without_any_session_extension() {
        ensure_test_restart_config();
        let state = crate::state::restart_test_state(true, false, HashSet::new()).await;
        let response = restart(
            State(state),
            HeaderMap::new(),
            Some(Extension(ClientIp("203.0.113.5".to_string()))),
            None, // no Session extension at all -- e.g. an API-key-only caller
            Bytes::new(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = response_json(response).await;
        assert_eq!(
            body,
            json!({
                "ok": false,
                "error": "再起動にはPIN認証済みセッションが必要です",
                "code": "pin_auth_required",
                "data": null,
            })
        );
    }

    #[tokio::test]
    async fn restart_requires_pin_session_with_pin_ok_false_in_session() {
        ensure_test_restart_config();
        let state = crate::state::restart_test_state(true, false, HashSet::new()).await;
        let session = session_with_pin_ok(false).await;
        let response = restart(
            State(state),
            HeaderMap::new(),
            Some(Extension(ClientIp("203.0.113.5".to_string()))),
            Some(Extension(session)),
            Bytes::new(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let body = response_json(response).await;
        assert_eq!(
            body,
            json!({
                "ok": false,
                "error": "再起動にはPIN認証済みセッションが必要です",
                "code": "pin_auth_required",
                "data": null,
            })
        );
    }

    #[tokio::test]
    async fn restart_requires_local_request_when_pin_auth_is_disabled() {
        ensure_test_restart_config();
        let state = crate::state::restart_test_state(false, false, HashSet::new()).await;
        let response = restart(
            State(state),
            HeaderMap::new(),
            Some(Extension(ClientIp("203.0.113.5".to_string()))),
            None,
            Bytes::new(),
        )
        .await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let body = response_json(response).await;
        assert_eq!(
            body,
            json!({
                "ok": false,
                "error": "PIN認証が無効のためリモートからの再起動は許可されていません",
                "code": "pin_required",
                "data": null,
            })
        );
    }

    // --- ordering: confirm check must run before remote-token/local-only ---

    #[tokio::test]
    async fn confirm_is_checked_before_remote_access() {
        ensure_test_restart_config(); // allow_remote_restart: false
        let state = crate::state::restart_test_state(true, false, HashSet::new()).await;
        let session = session_with_pin_ok(true).await;
        let mut headers = HeaderMap::new();
        headers.insert(header::CONTENT_TYPE, "application/json".parse().unwrap());
        // is_local will be false (no ClientIp extension supplied), confirm is
        // missing, and allow_remote_restart is false -- if the handler
        // checked confirm first (correct order), we get confirm_required. If
        // remote-access were checked first, we'd get local_only instead.
        let response = restart(
            State(state),
            headers,
            None,
            Some(Extension(session)),
            Bytes::from_static(b"{}"),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(
            body,
            json!({
                "ok": false,
                "error": "confirm='restart' が必要です",
                "code": "confirm_required",
                "data": null,
            })
        );
    }
}
