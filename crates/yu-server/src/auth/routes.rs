use axum::{
    extract::{Extension, Form, State},
    http::{header, StatusCode},
    response::{Html, IntoResponse, Redirect, Response},
    Json,
};
use serde::Deserialize;
use tower_sessions::Session;

use crate::auth::client_ip::ClientIp;
use crate::auth::pin::hash_pin;
use crate::pages;
use crate::security::CspNonce;
use crate::state::SharedState;

// ── helpers ───────────────────────────────────────────────────────────────────

/// Python api_success 互換: {"ok": true, "error": null, "data": null, <payload fields>}
fn api_ok(payload: serde_json::Value) -> Json<serde_json::Value> {
    let mut body = serde_json::json!({"ok": true, "error": null, "data": null});
    if let serde_json::Value::Object(map) = payload {
        body.as_object_mut().unwrap().extend(map);
    }
    Json(body)
}

fn api_err(msg: &str, status: StatusCode) -> Response {
    (status, Json(serde_json::json!({"ok": false, "error": msg}))).into_response()
}

fn safe_redirect(url: &str) -> &str {
    if url.starts_with('/') && !url.starts_with("//") {
        url
    } else {
        "/"
    }
}

fn pin_matches(submitted: &str, secret: &str, stored_hash: &str) -> bool {
    let computed = hash_pin(submitted, secret);
    auth_core::verify_token(&computed, stored_hash)
}

/// Renders the PIN error page for `post_pin_check`'s error branches, gated
/// on `pin_boss_login_ui` like every other boss-gate wire-in site.
async fn pin_check_error(state: &SharedState, msg: &str, next: &str, nonce: &str) -> Response {
    if state.config.pin_boss_login_ui {
        Html(
            crate::pages_boss::boss_gate_html(crate::pages_boss::BossMode::Pin, msg, next, nonce)
                .await,
        )
        .into_response()
    } else {
        Html(pages::pin_page(msg, next)).into_response()
    }
}

// ── GET /_pin ─────────────────────────────────────────────────────────────────

pub async fn get_pin_page(
    State(state): State<SharedState>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
) -> Html<String> {
    if state.config.pin_boss_login_ui {
        Html(
            crate::pages_boss::boss_gate_html(crate::pages_boss::BossMode::Pin, "", "/", &nonce)
                .await,
        )
    } else {
        Html(pages::pin_page("", "/"))
    }
}

// ── POST /_pin_check ──────────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct PinForm {
    pin: String,
    #[serde(default)]
    next: String,
}

pub async fn post_pin_check(
    State(state): State<SharedState>,
    Extension(ClientIp(ip)): Extension<ClientIp>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
    session: Session,
    Form(form): Form<PinForm>,
) -> Response {
    // Already-authenticated sessions skip PIN check and redirect (Python-compatible).
    let already_ok: bool = session.get("pin_ok").await.unwrap_or(None).unwrap_or(false);
    if already_ok {
        let redirect_to = safe_redirect(&form.next).to_string();
        return Redirect::to(&redirect_to).into_response();
    }

    // PIN 未設定時は早期リターン（未設定でも hash_pin を呼ぶと 600k PBKDF2 でハング）。
    if state.config.pin_hash.is_empty() {
        return pin_check_error(&state, "PIN認証が設定されていません", &form.next, &nonce).await;
    }

    if state.rate_limiter.is_locked_out(&ip) {
        return pin_check_error(
            &state,
            "試行回数超過。しばらくお待ちください。",
            &form.next,
            &nonce,
        )
        .await;
    }

    let submitted = form.pin.trim().to_string();
    if submitted.len() < state.config.min_pin_length {
        let msg = format!("PINは{}文字以上必要です", state.config.min_pin_length);
        return pin_check_error(&state, &msg, &form.next, &nonce).await;
    }

    // PBKDF2 (600k 反復) は CPU バウンドなので spawn_blocking で async スレッドを解放する。
    let secret = state.config.secret.clone();
    let pin_hash = state.config.pin_hash.clone();
    let matched = tokio::task::spawn_blocking(move || pin_matches(&submitted, &secret, &pin_hash))
        .await
        .unwrap_or(false);

    if matched {
        state.rate_limiter.reset(&ip);
        state.quick_lock.deactivate();
        let _ = session.insert("pin_ok", true).await;
        let redirect_to = safe_redirect(&form.next).to_string();
        let cookie = format!(
            "pin_token={}; HttpOnly; SameSite=Lax; Max-Age=86400; Path=/",
            state.config.valid_token
        );
        ([(header::SET_COOKIE, cookie)], Redirect::to(&redirect_to)).into_response()
    } else {
        state.rate_limiter.record_failure(&ip);
        pin_check_error(&state, "PINが違います", &form.next, &nonce).await
    }
}

// ── POST /api/lock/activate ───────────────────────────────────────────────────

pub async fn post_lock_activate(State(state): State<SharedState>, session: Session) -> Response {
    if !state.config.pin_auth_enabled {
        return api_err(
            "PIN認証が設定されていません。ロックにはPINが必要です。",
            StatusCode::BAD_REQUEST,
        );
    }
    if !state.config.quick_lock_enabled {
        return api_err(
            "QuickLock は設定で無効化されています。",
            StatusCode::BAD_REQUEST,
        );
    }
    state.quick_lock.activate();
    let _ = session.remove::<bool>("pin_ok").await;
    api_ok(serde_json::json!({"success": true, "locked": true})).into_response()
}

// ── POST /api/lock/unlock ─────────────────────────────────────────────────────

#[derive(Deserialize)]
pub struct UnlockBody {
    pin: String,
}

pub async fn post_lock_unlock(
    State(state): State<SharedState>,
    Extension(ClientIp(ip)): Extension<ClientIp>,
    session: Session,
    Json(body): Json<UnlockBody>,
) -> Response {
    if state.config.pin_hash.is_empty() {
        return api_err("PIN not configured", StatusCode::BAD_REQUEST);
    }
    if state.rate_limiter.is_locked_out(&ip) {
        return api_err("ロックアウト中", StatusCode::TOO_MANY_REQUESTS);
    }
    if pin_matches(&body.pin, &state.config.secret, &state.config.pin_hash) {
        state.quick_lock.deactivate();
        let _ = session.insert("pin_ok", true).await;
        state.rate_limiter.reset(&ip);
        api_ok(serde_json::json!({"success": true, "locked": false})).into_response()
    } else {
        state.rate_limiter.record_failure(&ip);
        api_err("PINが違います", StatusCode::UNAUTHORIZED)
    }
}

// ── GET /api/lock/status ──────────────────────────────────────────────────────

pub async fn get_lock_status(State(state): State<SharedState>) -> impl IntoResponse {
    let (locked, locked_at, locked_duration) = state.quick_lock.info();
    api_ok(serde_json::json!({
        "locked": locked,
        "locked_at": locked_at,
        "locked_duration": locked_duration,
    }))
}

// ── GET /api/auth/status ──────────────────────────────────────────────────────

pub async fn get_auth_status(
    State(state): State<SharedState>,
    session: Session,
) -> impl IntoResponse {
    let session_ok: bool = session.get("pin_ok").await.unwrap_or(None).unwrap_or(false);
    api_ok(serde_json::json!({
        "pin_auth": state.config.pin_auth_enabled,
        "quick_lock_enabled": state.config.quick_lock_enabled,
        "quick_lock_locked": state.quick_lock.is_locked(),
        "trusted_proxy_auth": state.config.trusted_proxy_enabled,
        "session_authenticated": session_ok,
    }))
}

// ── POST /api/auth/logout ─────────────────────────────────────────────────────

pub async fn post_auth_logout(session: Session) -> Response {
    let _ = session.flush().await;
    let clear_cookie = "pin_token=; HttpOnly; SameSite=Lax; Max-Age=0; Path=/";
    (
        [(header::SET_COOKIE, clear_cookie)],
        api_ok(serde_json::json!({"success": true})),
    )
        .into_response()
}
