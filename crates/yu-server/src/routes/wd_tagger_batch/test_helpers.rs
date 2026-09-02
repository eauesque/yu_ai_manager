use super::*;
use crate::routes::wd_tagger::tests::{test_dirs, test_state};
use axum::{body::to_bytes, routing::post, Router};
use serde_json::json;

pub(super) async fn build_test_state() -> SharedState {
    let dirs = Box::leak(Box::new(test_dirs()));
    let state = test_state(dirs, json!({})).await;
    // The shared fixture registers 'model-a'/'model-b' in wd_model_dict,
    // but resolve_configured_model_id resolves the *default* configured
    // model (sanitize_model_id("SmilingWolf/wd-swinv2-tagger-v3")), which
    // has no row yet. Register it so backfill tests can exercise the
    // "already tagged with the configured model" path.
    sqlx::query(
        "INSERT OR IGNORE INTO wd_model_dict(model) VALUES ('SmilingWolf_wd-swinv2-tagger-v3')",
    )
    .execute(&state.db)
    .await
    .unwrap();
    state
}

pub(super) fn build_test_router(state: SharedState) -> Router {
    Router::new()
        .route("/api/wd-tagger/batch", post(batch_handler))
        .route("/api/wd-tagger/batch/cancel", post(batch_cancel_handler))
        .with_state(state)
}

pub(super) async fn response_json(response: axum::response::Response) -> serde_json::Value {
    let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
    serde_json::from_slice(&body).unwrap()
}

pub(super) async fn insert_active_file(state: &SharedState, id: i64) {
    sqlx::query("INSERT INTO files(id, path, is_deleted, meta_source) VALUES (?, ?, 0, 'unknown')")
        .bind(id)
        .bind(format!("/img/batch-{id}.png"))
        .execute(&state.db)
        .await
        .unwrap();
}

pub(super) async fn insert_deleted_file(state: &SharedState, id: i64) {
    sqlx::query("INSERT INTO files(id, path, is_deleted, meta_source) VALUES (?, ?, 1, 'unknown')")
        .bind(id)
        .bind(format!("/img/batch-{id}.png"))
        .execute(&state.db)
        .await
        .unwrap();
}

/// Inserts an active file already tagged with the currently configured
/// model (default `SmilingWolf/wd-swinv2-tagger-v3`, registered into
/// `wd_model_dict` under its sanitized name by `build_test_state`).
pub(super) async fn insert_active_tagged_file(state: &SharedState, id: i64) {
    insert_active_file(state, id).await;
    let model_id = resolve_configured_model_id(state).await.unwrap();
    sqlx::query(
        "INSERT INTO file_wd_tags(file_id, tag_id, category_id, model_id, confidence_milli, created_at)
         VALUES (?, 1, 1, ?, 900, 0)",
    )
    .bind(id)
    .bind(model_id)
    .execute(&state.db)
    .await
    .unwrap();
}
