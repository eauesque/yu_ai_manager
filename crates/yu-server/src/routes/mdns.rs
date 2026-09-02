//! `/api/mdns/*` — mDNS identity and peer list (stub, Python backend absent).

use axum::{
    extract::State,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

use crate::state::SharedState;

/// GET /api/mdns/identity
pub async fn mdns_identity(State(_state): State<SharedState>) -> Response {
    Json(json!({
        "product": "yu_ai_manager",
        "node_id": null,
        "version": null,
        "capabilities": [],
    }))
    .into_response()
}

/// GET /api/mdns/peers
pub async fn mdns_peers(State(_state): State<SharedState>) -> Response {
    Json(json!({"running": false, "reason": "python backend unavailable", "peers": []}))
        .into_response()
}
