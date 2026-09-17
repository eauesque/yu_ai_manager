use std::net::SocketAddr;
use std::time::Duration;

use axum::http::StatusCode;
use axum::{
    extract::{ConnectInfo, State},
    response::IntoResponse,
    Extension, Json,
};
use serde_json::json;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::state::SharedState;

/// GET /api/admin/shutdown/info
pub async fn shutdown_info(
    ConnectInfo(addr): ConnectInfo<SocketAddr>,
    State(state): State<SharedState>,
) -> impl IntoResponse {
    let loopback = addr.ip().is_loopback();
    (
        StatusCode::OK,
        Json(json!({
            "ok": true,
            "loopback": loopback,
            "pin_required": state.config.pin_auth_enabled,
        })),
    )
}

/// POST /api/admin/shutdown
pub async fn shutdown(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> impl IntoResponse {
    // loopback を auth bypass に使わない: 同ホストプロセスや逆プロキシが
    // 無認証シャットダウンできる。pin_auth_enabled=false なら誰でも通る。
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return resp;
    }
    tokio::spawn(async {
        tokio::time::sleep(Duration::from_millis(500)).await;
        // The whole purpose of this endpoint. The 500 ms delay exists so the
        // 200 below reaches the client first; there is no graceful-shutdown
        // path to signal instead, and admin scope is already required above.
        #[allow(clippy::exit, reason = "this route's contract is to end the process")]
        std::process::exit(0);
    });
    (
        StatusCode::OK,
        Json(json!({
            "ok": true,
            "status": "shutting_down",
            "delay_s": 0.5,
        })),
    )
        .into_response()
}
