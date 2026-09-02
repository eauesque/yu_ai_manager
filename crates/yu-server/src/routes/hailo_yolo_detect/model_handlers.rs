use super::*;
use crate::routes::hailo_model_download;
use axum::body::Bytes;

/// Reports local availability of every supported Hailo YOLO HEF model.
pub(crate) async fn model_status_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }

    let hef_dir = hailo_model_download::default_hef_dir();
    Json(json!({
        "status": "ok",
        "models": hailo_model_download::get_yolo_model_status(&hef_dir),
    }))
    .into_response()
}

/// Downloads a supported Hailo YOLO HEF model unless it is already present.
pub(crate) async fn model_download_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    // Deliberate deviation from Python parity: its download endpoint has no
    // auth check, but this handler writes a network-downloaded file, so admin
    // scope is required just as it is for the native detection handlers.
    if let Some(response) =
        crate::routes::wd_tagger::admin_scope_error(&state, auth_context.as_ref())
    {
        return response;
    }

    // `Option<Json<Value>>` silently swallows body-extraction failures (malformed
    // JSON, wrong content-type) by collapsing them to `None`, which is
    // indistinguishable from "no body was sent" — that made a malformed/mistyped
    // `model` value fall back to the default model instead of erroring. Parse the
    // raw bytes ourselves so malformed JSON and a non-string `model` field are
    // both rejected with 400 instead of triggering an unintended default download.
    let model_name = if body.is_empty() {
        "yolov8n".to_string()
    } else {
        let parsed: Value = match serde_json::from_slice(&body) {
            Ok(value) => value,
            Err(error) => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({
                        "status": "error",
                        "message": format!("Invalid JSON body: {error}"),
                    })),
                )
                    .into_response();
            }
        };
        // `Value::get("model")` on a non-object top-level value (array, number,
        // string, bool) also returns `None`, which is indistinguishable from a
        // missing `model` key on an object — that let a valid-but-non-object body
        // (e.g. `123`, `"x"`, `[1]`) silently fall back to the default model
        // instead of erroring. Reject any top-level value that isn't an object
        // (or `null`, treated the same as an absent body) before looking up `model`.
        if !matches!(parsed, Value::Object(_) | Value::Null) {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({
                    "status": "error",
                    "message": "Request body must be a JSON object",
                })),
            )
                .into_response();
        }
        match parsed.get("model") {
            None | Some(Value::Null) => "yolov8n".to_string(),
            Some(Value::String(name)) => name.clone(),
            Some(_) => {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({
                        "status": "error",
                        "message": "model must be a string",
                    })),
                )
                    .into_response();
            }
        }
    };
    let Some(info) = hailo_model_download::YOLO_MODELS.get(&model_name).cloned() else {
        let mut available = hailo_model_download::YOLO_MODELS
            .keys()
            .cloned()
            .collect::<Vec<_>>();
        available.sort_unstable();
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({
                "status": "error",
                "message": format!("Unknown model: {model_name}"),
                "available": available,
            })),
        )
            .into_response();
    };

    let hef_dir = hailo_model_download::default_hef_dir();
    match hailo_model_download::download_hef(
        &info.hef_filename,
        &info.url,
        &hef_dir,
        "YU-AI-Manager/4.488 (Hailo YOLO Download)",
    )
    .await
    {
        Ok(path) => Json(json!({
            "status": "ok",
            "model": model_name,
            "path": path.to_string_lossy().into_owned(),
        }))
        .into_response(),
        Err(error) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({
                "status": "error",
                "message": format!("Download failed: {error}"),
            })),
        )
            .into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::body::to_bytes;

    async fn test_state() -> SharedState {
        let dirs = Box::leak(Box::new(crate::routes::wd_tagger::tests::test_dirs()));
        crate::routes::wd_tagger::tests::test_state(dirs, json!({})).await
    }

    async fn response_json(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn model_status_handler_returns_yolo_model_status() {
        let response = model_status_handler(State(test_state().await), None).await;

        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["status"], "ok");
        assert_eq!(body["models"]["yolov8n"]["input_size"], 640);
        assert!(body["models"]["yolov8n"].get("type").is_none());
    }

    #[tokio::test(flavor = "current_thread")]
    async fn model_download_handler_returns_existing_default_model_path() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let previous_hef_dir = std::env::var_os("HAILO_HEF_DIR");
        let temp_dir = tempfile::tempdir().unwrap();
        let expected_path = temp_dir.path().join("yolov8n.hef");
        std::fs::write(&expected_path, b"already downloaded").unwrap();
        std::env::set_var("HAILO_HEF_DIR", temp_dir.path());

        let response =
            model_download_handler(State(test_state().await), None, Bytes::from_static(b"{}"))
                .await;

        if let Some(previous_hef_dir) = previous_hef_dir {
            std::env::set_var("HAILO_HEF_DIR", previous_hef_dir);
        } else {
            std::env::remove_var("HAILO_HEF_DIR");
        }

        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["status"], "ok");
        assert_eq!(body["model"], "yolov8n");
        assert_eq!(body["path"], expected_path.to_string_lossy().as_ref());
    }

    #[tokio::test]
    async fn model_download_handler_rejects_unknown_model() {
        let response = model_download_handler(
            State(test_state().await),
            None,
            Bytes::from_static(br#"{"model": "unknown-model"}"#),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(body["status"], "error");
        assert_eq!(body["message"], "Unknown model: unknown-model");
        assert!(body["available"]
            .as_array()
            .unwrap()
            .iter()
            .any(|name| name == "yolov8n"));
    }

    #[tokio::test]
    async fn model_handlers_require_admin_scope_when_pin_auth_is_enabled() {
        let mut status_state = test_state().await;
        std::sync::Arc::get_mut(&mut status_state)
            .unwrap()
            .config
            .pin_auth_enabled = true;
        let status_response = model_status_handler(State(status_state), None).await;
        assert_eq!(status_response.status(), StatusCode::FORBIDDEN);

        let mut download_state = test_state().await;
        std::sync::Arc::get_mut(&mut download_state)
            .unwrap()
            .config
            .pin_auth_enabled = true;
        let download_response = model_download_handler(
            State(download_state),
            None,
            Bytes::from_static(br#"{"model": "yolov8n"}"#),
        )
        .await;
        assert_eq!(download_response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn model_download_handler_rejects_malformed_json_body() {
        let response = model_download_handler(
            State(test_state().await),
            None,
            Bytes::from_static(b"{not valid json"),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(body["status"], "error");
        assert!(body["message"]
            .as_str()
            .unwrap()
            .starts_with("Invalid JSON body"));
    }

    #[tokio::test]
    async fn model_download_handler_rejects_non_string_model_field() {
        let response = model_download_handler(
            State(test_state().await),
            None,
            Bytes::from_static(br#"{"model": 123}"#),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(body["status"], "error");
        assert_eq!(body["message"], "model must be a string");
    }

    #[tokio::test(flavor = "current_thread")]
    async fn model_download_handler_defaults_model_when_body_is_empty() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|error| error.into_inner());
        let previous_hef_dir = std::env::var_os("HAILO_HEF_DIR");
        let temp_dir = tempfile::tempdir().unwrap();
        let expected_path = temp_dir.path().join("yolov8n.hef");
        std::fs::write(&expected_path, b"already downloaded").unwrap();
        std::env::set_var("HAILO_HEF_DIR", temp_dir.path());

        let response = model_download_handler(State(test_state().await), None, Bytes::new()).await;

        if let Some(previous_hef_dir) = previous_hef_dir {
            std::env::set_var("HAILO_HEF_DIR", previous_hef_dir);
        } else {
            std::env::remove_var("HAILO_HEF_DIR");
        }

        assert_eq!(response.status(), StatusCode::OK);
        let body = response_json(response).await;
        assert_eq!(body["model"], "yolov8n");
    }

    #[tokio::test]
    async fn model_download_handler_rejects_top_level_array_body() {
        let response = model_download_handler(
            State(test_state().await),
            None,
            Bytes::from_static(b"[1,2,3]"),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(body["status"], "error");
        assert_eq!(body["message"], "Request body must be a JSON object");
    }

    #[tokio::test]
    async fn model_download_handler_rejects_top_level_number_body() {
        let response =
            model_download_handler(State(test_state().await), None, Bytes::from_static(b"123"))
                .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(body["status"], "error");
        assert_eq!(body["message"], "Request body must be a JSON object");
    }

    #[tokio::test]
    async fn model_download_handler_rejects_top_level_string_body() {
        let response = model_download_handler(
            State(test_state().await),
            None,
            Bytes::from_static(br#""hello""#),
        )
        .await;

        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        let body = response_json(response).await;
        assert_eq!(body["status"], "error");
        assert_eq!(body["message"], "Request body must be a JSON object");
    }
}
