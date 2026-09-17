pub mod ring;
pub mod routes;
mod scrub;
pub mod tracing_layer;

pub use ring::LogRingBuffer;

use axum::{routing::get, Router};

use crate::state::SharedState;

/// Routes served under the auth middleware (`/api/logs/*`).
pub fn router() -> Router<SharedState> {
    Router::new()
        .route("/api/logs/recent", get(routes::recent))
        .route("/api/logs/stream", get(routes::stream_handler))
        // legacy native-prefixed aliases kept for compatibility
        .route("/api/logs/native/recent", get(routes::recent))
        .route("/api/logs/native/stream", get(routes::stream_handler))
}
