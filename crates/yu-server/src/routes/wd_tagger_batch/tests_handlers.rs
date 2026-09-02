use super::test_helpers::{build_test_router, build_test_state, insert_active_file, response_json};
use super::*;
use axum::{
    body::Body,
    http::{Request, StatusCode},
};
use serde_json::json;
use tower::ServiceExt;

#[tokio::test]
async fn batch_handler_returns_started_true_with_job_id() {
    let state = build_test_state().await;
    insert_active_file(&state, 1001).await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .header("content-type", "application/json")
                .body(Body::from(json!({"file_ids": [1001]}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    let body = response_json(response).await;
    assert_eq!(
        body,
        json!({
            "started": true,
            "job_id": WD_TAGGER_JOB_ID,
            "ok": true,
            "error": null,
            "data": null,
        })
    );
}

#[tokio::test]
async fn batch_handler_returns_no_targets() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"file_ids": []}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({"started": false, "reason": "no_targets", "ok": true, "error": null, "data": null})
    );
}

#[tokio::test]
async fn batch_handler_treats_missing_target_fields_as_backfill() {
    let state = build_test_state().await;
    sqlx::query("UPDATE files SET is_deleted = 1")
        .execute(&state.db)
        .await
        .unwrap();
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from("{}"))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({"started": false, "reason": "no_targets", "ok": true, "error": null, "data": null})
    );
}

#[tokio::test]
async fn batch_handler_returns_conflict_when_job_is_already_running() {
    let state = build_test_state().await;
    insert_active_file(&state, 1002).await;
    state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"file_ids": [1002]}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::CONFLICT);
    assert_eq!(
        response_json(response).await,
        json!({
            "ok": false,
            "error": "WD-Tagger retag job already running",
            "code": "job_running",
        })
    );
}

#[tokio::test]
async fn batch_handler_rejects_limit_outside_allowed_range() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"limit": 501}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({
            "ok": false,
            "error": "limit must be between 0 and 500",
            "code": "invalid_value",
        })
    );
}

#[tokio::test]
async fn batch_handler_rejects_non_integer_limit() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"limit": "100"}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({"ok": false, "error": "limit must be an integer", "code": "invalid_value"})
    );
}

#[tokio::test]
async fn batch_handler_rejects_boolean_limit() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"limit": true}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({"ok": false, "error": "limit must be an integer", "code": "invalid_value"})
    );
}

#[tokio::test]
async fn batch_handler_rejects_non_boolean_force() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"force": "true"}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({"ok": false, "error": "force must be a boolean", "code": "invalid_value"})
    );
}

#[tokio::test]
async fn batch_handler_rejects_non_list_file_ids() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"file_ids": {"id": 1}}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({"ok": false, "error": "file_ids must be a list", "code": "invalid_input"})
    );
}

#[tokio::test]
async fn batch_handler_rejects_more_than_500_file_ids() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let file_ids: Vec<i64> = (0..=500).collect();
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from(json!({"file_ids": file_ids}).to_string()))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({"ok": false, "error": "file_ids max 500", "code": "batch_too_large"})
    );
}

#[tokio::test]
async fn batch_handler_rejects_json_non_object_body() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch")
                .body(Body::from("[1]"))
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    assert_eq!(
        response_json(response).await,
        json!({
            "ok": false,
            "error": "request body must be a JSON object",
            "code": "invalid_input",
        })
    );
}

#[tokio::test]
async fn batch_cancel_handler_returns_404_when_not_running() {
    let state = build_test_state().await;
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch/cancel")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::NOT_FOUND);
    assert_eq!(
        response_json(response).await,
        json!({
            "ok": false,
            "error": "No running batch tagging job",
            "code": "job_not_running",
        })
    );
}

#[tokio::test]
async fn batch_cancel_handler_returns_cancelling_when_job_is_running() {
    let state = build_test_state().await;
    state.job_manager.start(WD_TAGGER_JOB_ID, "WD-Tagger batch");
    let app = build_test_router(state);
    let response = app
        .oneshot(
            Request::post("/api/wd-tagger/batch/cancel")
                .body(Body::empty())
                .unwrap(),
        )
        .await
        .unwrap();

    assert_eq!(response.status(), StatusCode::OK);
    assert_eq!(
        response_json(response).await,
        json!({
            "status": "cancelling",
            "message": "Batch tagging cancel requested",
            "ok": true,
            "error": null,
            "data": null,
        })
    );
}
