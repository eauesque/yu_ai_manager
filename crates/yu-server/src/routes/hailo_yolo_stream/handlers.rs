use axum::{
    body::Bytes,
    extract::{Extension, Path, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    routing::{delete, get, post, put},
    Json, Router,
};
use serde_json::{json, Value};

use super::{
    devices::{self, Device, DeviceError},
    registry::{RegistryError, StreamState},
    rules::{DetectionRule, StreamSourceConfig},
    source_task::SourceTestResult,
};
use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

const PREFIX: &str = "/ext/hailo-yolo/api/stream";

/// Route paths are written as whole string literals rather than
/// `&format!("{PREFIX}/…")`.
///
/// `scripts/rust_standalone_gap.py` (and every other static route scanner in
/// this repo) collects `.route()` calls by parsing the source for literal path
/// arguments. Runtime-built paths are invisible to it: with `format!` here, the
/// scanner saw 875 routes and none of these fifteen, so the T9 "zero Python
/// forwards for the stream subsystem" check was vacuously true rather than
/// verified. Keep these literal so the gates can see them.
///
/// `PREFIX` is still used by this module's tests, which therefore assert that
/// the literals below stay in sync with it.
pub(crate) fn routes() -> Router<SharedState> {
    Router::new()
        .route(
            "/ext/hailo-yolo/api/stream/sources",
            get(list_sources).post(add_source),
        )
        .route(
            "/ext/hailo-yolo/api/stream/sources/{source_id}",
            delete(delete_source),
        )
        .route(
            "/ext/hailo-yolo/api/stream/sources/{source_id}/start",
            post(start_source),
        )
        .route(
            "/ext/hailo-yolo/api/stream/sources/{source_id}/stop",
            post(stop_source),
        )
        .route(
            "/ext/hailo-yolo/api/stream/sources/{source_id}/test",
            post(test_source),
        )
        .route(
            "/ext/hailo-yolo/api/stream/rules",
            get(list_rules).post(add_rule),
        )
        .route(
            "/ext/hailo-yolo/api/stream/rules/{rule_id}",
            put(update_rule).delete(delete_rule),
        )
        .route("/ext/hailo-yolo/api/stream/status", get(status))
        .route("/ext/hailo-yolo/api/stream/devices", get(list_devices))
        .route("/ext/hailo-yolo/api/stream/{source_id}/mjpeg", get(mjpeg))
        .route("/ext/hailo-yolo/api/stream/recordings", get(recordings))
        .route(
            "/ext/hailo-yolo/api/stream/snapshot/{filename}",
            get(snapshot),
        )
}

fn authorize(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(
        state.config.pin_auth_enabled,
        auth.map(|context| &context.0),
    )
}

fn stream_state(state: &SharedState) -> Result<&StreamState, Response> {
    state
        .hailo_yolo_stream
        .as_deref()
        .ok_or_else(service_unavailable)
}

fn service_unavailable() -> Response {
    response(
        StatusCode::INTERNAL_SERVER_ERROR,
        json!({"error": "Stream service unavailable"}),
    )
}

fn response(status: StatusCode, body: Value) -> Response {
    (status, Json(body)).into_response()
}

fn error(status: StatusCode, message: &'static str) -> Response {
    response(status, json!({"error": message}))
}

/// Strip credentials on the way out. Every stream response that can carry a source
/// URL or a webhook secret goes through here; the domain types stay plaintext
/// because the config writer persists those same types.
fn masked(value: &impl serde::Serialize) -> Value {
    super::secrets::masked_response(value)
}

/// Put back any protected value the client echoed in masked form.
///
/// Rule updates replace the whole rule, so a client that GETs a rule and PUTs it
/// back would otherwise persist `****` over the real secret.
async fn keep_masked_secrets(stream: &StreamState, incoming: &mut DetectionRule) {
    let Ok(existing) = stream.list_rules().await else {
        return;
    };
    if let Some(stored) = existing.iter().find(|rule| rule.id == incoming.id) {
        super::secrets::preserve_masked_rule(incoming, stored);
    }
}

fn json_body(body: &Bytes) -> Value {
    serde_json::from_slice(body).unwrap_or_else(|_| json!({}))
}

fn body_string(body: &Value, key: &str) -> String {
    body.get(key)
        .and_then(Value::as_str)
        .unwrap_or_default()
        .trim()
        .to_string()
}

pub(crate) async fn list_sources(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    response(
        StatusCode::OK,
        json!({"status": "ok", "sources": masked(&stream.registry.statuses().await)}),
    )
}

pub(crate) async fn add_source(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let body = json_body(&body);
    let id = body_string(&body, "id");
    let url = body_string(&body, "url");
    if id.is_empty() || url.is_empty() {
        return error(StatusCode::BAD_REQUEST, "id and url are required");
    }
    let name = body_string(&body, "name");
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    match stream
        .add_source(StreamSourceConfig { id, url, name })
        .await
    {
        Ok(source) => response(
            StatusCode::CREATED,
            json!({"status": "ok", "source": masked(&source)}),
        ),
        Err(RegistryError::InvalidSource) => error(StatusCode::BAD_REQUEST, "Invalid source URL"),
        Err(RegistryError::Duplicate | RegistryError::Capacity) => {
            error(StatusCode::CONFLICT, "Source could not be added")
        }
        Err(_) => error(StatusCode::CONFLICT, "Source could not be added"),
    }
}

pub(crate) async fn delete_source(
    State(state): State<SharedState>,
    Path(source_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    match stream.delete_source(&source_id).await {
        Ok(()) => response(StatusCode::OK, json!({"status": "ok"})),
        Err(RegistryError::NotFound) => error(StatusCode::NOT_FOUND, "Source not found"),
        Err(_) => service_unavailable(),
    }
}

pub(crate) async fn list_rules(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    match stream.list_rules().await {
        Ok(rules) => response(
            StatusCode::OK,
            json!({"status": "ok", "rules": masked(&rules)}),
        ),
        Err(_) => service_unavailable(),
    }
}

fn rule_from_body(body: Value, path_id: Option<&str>) -> DetectionRule {
    let body = body.as_object();
    let id = path_id.map(str::to_string).unwrap_or_else(|| {
        body.and_then(|body| body.get("id"))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_string()
    });
    let normalized = json!({
        "id": id,
        "name": body.and_then(|body| body.get("name")).and_then(Value::as_str),
        "enabled": body.and_then(|body| body.get("enabled")).and_then(Value::as_bool).unwrap_or(true),
        "conditions": body.and_then(|body| body.get("conditions")).and_then(Value::as_object),
        "cooldown_sec": body.and_then(|body| body.get("cooldown_sec")).and_then(Value::as_i64).unwrap_or(0),
        "actions": body
            .and_then(|body| body.get("actions"))
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default(),
    });
    serde_json::from_value(normalized).expect("normalized stream rule is valid")
}

pub(crate) async fn add_rule(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let body = json_body(&body);
    if body_string(&body, "id").is_empty() {
        return error(StatusCode::BAD_REQUEST, "id is required");
    }
    // Python's invalid-rule 400 branch is unreachable; do not add a Rust-only rejection.
    let mut rule = rule_from_body(body, None);
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    keep_masked_secrets(stream, &mut rule).await;
    match stream.add_rule(rule).await {
        Ok(rule) => response(
            StatusCode::CREATED,
            json!({"status": "ok", "rule": masked(&rule)}),
        ),
        Err(_) => service_unavailable(),
    }
}

pub(crate) async fn update_rule(
    State(state): State<SharedState>,
    Path(rule_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    // Python's invalid-update 400 branch is unreachable; do not add a Rust-only rejection.
    let mut rule = rule_from_body(json_body(&body), Some(&rule_id));
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    keep_masked_secrets(stream, &mut rule).await;
    // update_rule is intentionally an upsert. Python's documented 404 branch is dead code.
    match stream.update_rule(&rule_id, rule).await {
        Ok(rule) => response(
            StatusCode::OK,
            json!({"status": "ok", "rule": masked(&rule)}),
        ),
        Err(_) => service_unavailable(),
    }
}

pub(crate) async fn delete_rule(
    State(state): State<SharedState>,
    Path(rule_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    match stream.delete_rule(&rule_id).await {
        Ok(()) => response(StatusCode::OK, json!({"status": "ok"})),
        Err(RegistryError::NotFound) => error(StatusCode::NOT_FOUND, "Rule not found"),
        Err(_) => service_unavailable(),
    }
}

pub(crate) async fn status(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    let pipeline = stream.pipeline_status().await;
    let sources = stream.status_sources().await;
    let rules_count = match stream.list_rules().await {
        Ok(rules) => rules.len(),
        Err(_) => return service_unavailable(),
    };
    let recorder = stream.recorder_status().await;
    response(
        StatusCode::OK,
        json!({
            "status": "ok",
            "pipeline": pipeline,
            "sources": masked(&sources),
            "rules_count": rules_count,
            "recorder": recorder,
        }),
    )
}

pub(crate) async fn start_source(
    State(state): State<SharedState>,
    Path(source_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    let Some(handle) = stream.registry.get(&source_id).await else {
        return error(StatusCode::NOT_FOUND, "Source not found");
    };
    match stream.start_source(&source_id).await {
        Ok(source) => response(StatusCode::OK, json!({"status": "ok", "source": source})),
        Err(_) => response(
            StatusCode::INTERNAL_SERVER_ERROR,
            json!({"error": "Failed to start source", "source": handle.status()}),
        ),
    }
}

pub(crate) async fn stop_source(
    State(state): State<SharedState>,
    Path(source_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    match stream.stop_source(&source_id).await {
        Ok(source) => response(StatusCode::OK, json!({"status": "ok", "source": source})),
        Err(RegistryError::NotFound) => error(StatusCode::NOT_FOUND, "Source not found"),
        Err(_) => service_unavailable(),
    }
}

fn source_test_response(result: Result<SourceTestResult, RegistryError>) -> Response {
    match result {
        Ok(result) => response(StatusCode::OK, serde_json::to_value(result).unwrap()),
        Err(RegistryError::InvalidSource) => error(StatusCode::BAD_REQUEST, "Invalid source URL"),
        Err(_) => response(
            StatusCode::OK,
            json!({"ok": false, "error": "Source test failed"}),
        ),
    }
}

pub(crate) async fn test_source(
    State(state): State<SharedState>,
    Path(source_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let body = json_body(&body);
    let requested_url = body_string(&body, "url");
    let url = (!requested_url.is_empty()).then_some(requested_url.as_str());
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    if url.is_none() && stream.registry.get(&source_id).await.is_none() {
        return error(StatusCode::BAD_REQUEST, "No URL provided");
    }
    source_test_response(stream.test_source(&source_id, url).await)
}

fn devices_response(result: Result<Vec<Device>, DeviceError>) -> Response {
    match result {
        Ok(devices) => response(StatusCode::OK, json!({"status": "ok", "devices": devices})),
        Err(_) => response(
            StatusCode::OK,
            json!({
                "status": "error",
                "devices": [],
                "error": "Device detection failed",
            }),
        ),
    }
}

pub(crate) async fn list_devices(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    devices_response(devices::enumerate_devices_async().await)
}

pub(crate) async fn mjpeg(
    State(state): State<SharedState>,
    Path(source_id): Path<String>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = authorize(&state, auth.as_ref()) {
        return response;
    }
    let Ok(stream) = stream_state(&state) else {
        return service_unavailable();
    };
    match stream.mjpeg_response(&source_id).await {
        Ok(response) => response,
        Err(RegistryError::NotFound) => error(StatusCode::NOT_FOUND, "Source not found"),
        Err(_) => service_unavailable(),
    }
}

// #14 and #15 (`/stream/recordings`, `/stream/snapshot/{filename}`) do not need
// `StreamState`: they are filesystem-only routes with no active-session state to
// read (see spec `2026-08-13 改訂`). Their logic already lives on the parent
// module (`super::recordings` / `super::snapshot`, ported before T1 as "stage 0")
// alongside its own admin-scope check; these are thin axum-extractor adapters
// that reuse it rather than re-implement it.
pub(crate) async fn recordings(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    super::recordings(&state, auth.as_ref().map(|context| &context.0)).await
}

pub(crate) async fn snapshot(
    State(state): State<SharedState>,
    Path(filename): Path<String>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    super::snapshot(&state, auth.as_ref().map(|context| &context.0), &filename).await
}

#[cfg(test)]
mod tests {
    use std::{
        future::Future,
        io::{self, Write},
        path::PathBuf,
        pin::Pin,
        sync::{
            atomic::{AtomicUsize, Ordering},
            Arc, Mutex,
        },
        time::Duration,
    };

    use axum::{
        body::{to_bytes, Body},
        http::{header, Method, Request},
        middleware,
    };
    use bytes::Bytes;
    use futures_util::StreamExt;
    use serde_json::{json, Value};
    use tokio::{sync::mpsc, time::timeout};
    use tower::ServiceExt;
    use tower_sessions::{MemoryStore, SessionManagerLayer};
    use tracing_subscriber::fmt::MakeWriter;

    use super::*;
    use crate::{
        routes::hailo_yolo_stream::{
            actions::ActionExecutor,
            frame_source::{Frame, SourceError, SupervisorEvent},
            rules::{ActionBatch, TriggerFrame},
            run_bounded_test,
            source_task::{SourceFactory, SourceRuntime},
        },
        sse::SseHub,
        state::{semantic_test_state, semantic_test_state_with_root, SharedState},
    };

    const TEST_TIMEOUT: Duration = Duration::from_secs(15);

    #[derive(Clone, Copy)]
    enum FixtureOutcome {
        Connected,
        Ended,
        Error,
    }

    struct FixtureFactory {
        outcome: FixtureOutcome,
        calls: Arc<AtomicUsize>,
    }

    impl FixtureFactory {
        fn new(outcome: FixtureOutcome) -> (Arc<Self>, Arc<AtomicUsize>) {
            let calls = Arc::new(AtomicUsize::new(0));
            (
                Arc::new(Self {
                    outcome,
                    calls: Arc::clone(&calls),
                }),
                calls,
            )
        }
    }

    struct FixtureRuntime {
        events: mpsc::UnboundedReceiver<SupervisorEvent>,
    }

    impl SourceRuntime for FixtureRuntime {
        fn events(&mut self) -> &mut mpsc::UnboundedReceiver<SupervisorEvent> {
            &mut self.events
        }

        fn request_stop(&self) {}

        fn wait(
            self: Box<Self>,
        ) -> Pin<Box<dyn Future<Output = Result<(), SourceError>> + Send + 'static>> {
            Box::pin(async { Ok(()) })
        }
    }

    impl SourceFactory for FixtureFactory {
        fn spawn(&self) -> Result<Box<dyn SourceRuntime>, SourceError> {
            self.calls.fetch_add(1, Ordering::SeqCst);
            if matches!(self.outcome, FixtureOutcome::Error) {
                return Err(SourceError::InvalidConfiguration);
            }
            let (tx, events) = mpsc::unbounded_channel();
            let event = match self.outcome {
                FixtureOutcome::Connected => SupervisorEvent::Connected {
                    pid: None,
                    width: 640,
                    height: 480,
                },
                FixtureOutcome::Ended => SupervisorEvent::Ended,
                FixtureOutcome::Error => unreachable!(),
            };
            tx.send(event).unwrap();
            Ok(Box::new(FixtureRuntime { events }))
        }
    }

    fn source(id: &str) -> StreamSourceConfig {
        StreamSourceConfig {
            id: id.to_string(),
            url: "rtsp://camera.test/live".to_string(),
            name: String::new(),
        }
    }

    fn config_channel() -> mpsc::Sender<super::super::registry::ConfigCommand> {
        let (tx, mut rx) = mpsc::channel::<super::super::registry::ConfigCommand>(32);
        tokio::spawn(async move {
            while let Some(command) = rx.recv().await {
                let _ = command.reply().send(Ok(()));
            }
        });
        tx
    }

    async fn fixture_state(
        outcome: FixtureOutcome,
        restored: Vec<StreamSourceConfig>,
        pin_auth_enabled: bool,
    ) -> (SharedState, Arc<AtomicUsize>) {
        let (factory, calls) = FixtureFactory::new(outcome);
        let stream = StreamState::with_factory(restored, json!({}), config_channel(), factory);
        let base = semantic_test_state(pin_auth_enabled).await;
        let mut state = match Arc::try_unwrap(base) {
            Ok(state) => state,
            Err(_) => panic!("semantic test state unexpectedly shared"),
        };
        state.hailo_yolo_stream = Some(Arc::new(stream));
        (Arc::new(state), calls)
    }

    /// Like `fixture_state`, but with a caller-controlled `project_root` so
    /// tests can exercise the filesystem-backed `#14`/`#15` routes
    /// (`recordings`, `snapshot`) against a `tempfile::tempdir()` instead of
    /// the crate's real `.` working directory.
    async fn fixture_state_with_root(project_root: PathBuf, pin_auth_enabled: bool) -> SharedState {
        let (factory, _) = FixtureFactory::new(FixtureOutcome::Connected);
        let stream = StreamState::with_factory(Vec::new(), json!({}), config_channel(), factory);
        let base =
            semantic_test_state_with_root(pin_auth_enabled, String::new(), project_root).await;
        let mut state = match Arc::try_unwrap(base) {
            Ok(state) => state,
            Err(_) => panic!("semantic test state unexpectedly shared"),
        };
        state.hailo_yolo_stream = Some(Arc::new(stream));
        Arc::new(state)
    }

    /// A `SourceFactory` for the T9 plan step 9 MJPEG byte-exactness test.
    /// Unlike `FixtureFactory`, `spawn` emits a `Connected` event followed by
    /// one real `Frame` so the frame flows through the actual detect → draw →
    /// encode pipeline (`consume` in `mjpeg.rs`) and the response body carries
    /// a genuine `image` crate-encoded JPEG rather than a fixture byte string.
    struct FrameFactory {
        width: u32,
        height: u32,
        bytes: Vec<u8>,
    }

    impl SourceFactory for FrameFactory {
        fn spawn(&self) -> Result<Box<dyn SourceRuntime>, SourceError> {
            let (tx, events) = mpsc::unbounded_channel();
            tx.send(SupervisorEvent::Connected {
                pid: None,
                width: self.width,
                height: self.height,
            })
            .unwrap();
            // A single one-shot `Frame` event races the MJPEG viewer's
            // subscription: `SourceStream::body()` subscribes to a
            // `broadcast` channel that never replays sends made before
            // subscription, so a frame published before the HTTP GET
            // attaches would be silently lost forever. Keep emitting frames
            // on a short real-time interval (a live camera feed, not a
            // "sleep and assume it's done") so a fresh frame always arrives
            // after the viewer subscribes, however the two tasks interleave.
            let width = self.width;
            let height = self.height;
            let bytes = self.bytes.clone();
            tokio::spawn(async move {
                let mut ticker = tokio::time::interval(Duration::from_millis(10));
                loop {
                    ticker.tick().await;
                    if tx
                        .send(SupervisorEvent::Frame(Frame {
                            width,
                            height,
                            bytes: bytes.clone(),
                        }))
                        .is_err()
                    {
                        return;
                    }
                }
            });
            Ok(Box::new(FixtureRuntime { events }))
        }
    }

    /// Like `fixture_state`, but wires a single restored source to
    /// `FrameFactory` so `start_source` immediately has a real frame flowing
    /// into the MJPEG pipeline.
    async fn frame_source_state(source_id: &str, width: u32, height: u32) -> SharedState {
        let bytes = vec![128u8; (width * height * 3) as usize];
        let factory = Arc::new(FrameFactory {
            width,
            height,
            bytes,
        });
        let stream = StreamState::with_factory(
            vec![source(source_id)],
            json!({}),
            config_channel(),
            factory,
        );
        let base = semantic_test_state(false).await;
        let mut state = match Arc::try_unwrap(base) {
            Ok(state) => state,
            Err(_) => panic!("semantic test state unexpectedly shared"),
        };
        state.hailo_yolo_stream = Some(Arc::new(stream));
        Arc::new(state)
    }

    fn request(method: Method, path: &str, body: Value) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(path)
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from(body.to_string()))
            .unwrap()
    }

    async fn json_response(response: Response) -> (StatusCode, Value) {
        let status = response.status();
        let body = to_bytes(response.into_body(), 1 << 20).await.unwrap();
        (status, serde_json::from_slice(&body).unwrap())
    }

    async fn call_json(
        app: &Router,
        method: Method,
        path: &str,
        body: Value,
    ) -> (StatusCode, Value) {
        json_response(
            app.clone()
                .oneshot(request(method, path, body))
                .await
                .unwrap(),
        )
        .await
    }

    #[test]
    fn shadow_router_exposes_all_fifteen_contracts_with_real_app_state() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) =
                fixture_state(FixtureOutcome::Connected, vec![source("cam")], false).await;
            let app = routes().with_state(state);

            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/sources"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body["status"], "ok");
            assert_eq!(body["sources"].as_array().unwrap().len(), 1);

            let (code, body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources"),
                json!({"id": "new", "url": "https://camera.test/live", "name": " New "}),
            )
            .await;
            assert_eq!(code, StatusCode::CREATED);
            assert_eq!(body["source"]["name"], "New");

            let (code, body) = call_json(
                &app,
                Method::DELETE,
                &format!("{PREFIX}/sources/new"),
                json!({}),
            )
            .await;
            assert_eq!((code, body), (StatusCode::OK, json!({"status": "ok"})));

            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/rules"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body, json!({"status": "ok", "rules": []}));

            let (code, body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/rules"),
                json!({"id": "rule-one", "name": "One"}),
            )
            .await;
            assert_eq!(code, StatusCode::CREATED);
            assert_eq!(body["rule"]["id"], "rule-one");

            let (code, body) = call_json(
                &app,
                Method::PUT,
                &format!("{PREFIX}/rules/upserted"),
                json!({"id": "ignored", "name": "Upserted"}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body["rule"]["id"], "upserted");

            let (code, body) = call_json(
                &app,
                Method::DELETE,
                &format!("{PREFIX}/rules/rule-one"),
                json!({}),
            )
            .await;
            assert_eq!((code, body), (StatusCode::OK, json!({"status": "ok"})));

            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body["status"], "ok");
            assert_eq!(body["rules_count"], 1);
            assert_eq!(body["recorder"], json!({}));

            let (code, body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/start"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body["status"], "ok");

            let (code, body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/stop"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body["status"], "ok");

            let (code, body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/test"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(
                body,
                json!({"ok": true, "resolution": {"width": 640, "height": 480}})
            );

            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/devices"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            assert!(matches!(body["status"].as_str(), Some("ok" | "error")));
            assert!(body["devices"].is_array());

            let response = app
                .clone()
                .oneshot(request(
                    Method::GET,
                    &format!("{PREFIX}/cam/mjpeg"),
                    json!({}),
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(
                response.headers()[header::CONTENT_TYPE],
                "multipart/x-mixed-replace; boundary=frame"
            );
        });
    }

    #[test]
    fn recordings_and_snapshot_routes_are_wired_through_the_shadow_router() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempfile::tempdir().unwrap();
            let state = fixture_state_with_root(root.path().to_path_buf(), false).await;
            let app = routes().with_state(state);

            // #14 with no videos directory yet: empty list, not an error.
            let (code, body) = call_json(
                &app,
                Method::GET,
                &format!("{PREFIX}/recordings"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(body, json!({"status": "ok", "recordings": []}));

            let videos = root.path().join("detections").join("videos");
            tokio::fs::create_dir_all(&videos).await.unwrap();
            tokio::fs::write(videos.join("clip.mp4"), b"CLIP")
                .await
                .unwrap();
            let (code, body) = call_json(
                &app,
                Method::GET,
                &format!("{PREFIX}/recordings"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);
            let recordings = body["recordings"].as_array().unwrap();
            assert_eq!(recordings.len(), 1);
            assert_eq!(recordings[0]["name"], "clip.mp4");

            // #15 missing file: exact 404 body from the task spec.
            let response = app
                .clone()
                .oneshot(request(
                    Method::GET,
                    &format!("{PREFIX}/snapshot/missing.jpg"),
                    json!({}),
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::NOT_FOUND);
            let (status, body) = json_response(response).await;
            assert_eq!(status, StatusCode::NOT_FOUND);
            assert_eq!(body, json!({"error": "Not found"}));

            // #15 real file: body bytes pass through unchanged.
            let snapshots = root.path().join("detections").join("snapshots");
            tokio::fs::create_dir_all(&snapshots).await.unwrap();
            tokio::fs::write(snapshots.join("real.jpg"), b"SNAPSHOT-BYTES")
                .await
                .unwrap();
            let response = app
                .clone()
                .oneshot(request(
                    Method::GET,
                    &format!("{PREFIX}/snapshot/real.jpg"),
                    json!({}),
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            let bytes = to_bytes(response.into_body(), 1 << 20).await.unwrap();
            assert_eq!(&bytes[..], b"SNAPSHOT-BYTES");
        });
    }

    #[test]
    fn contract_error_statuses_and_bodies_are_exact() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = fixture_state(FixtureOutcome::Error, vec![source("cam")], false).await;
            let app = routes().with_state(state);
            let cases = [
                (
                    Method::POST,
                    format!("{PREFIX}/sources"),
                    json!({}),
                    StatusCode::BAD_REQUEST,
                    json!({"error": "id and url are required"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/sources"),
                    json!({"id": "cam", "url": "https://camera.test/live"}),
                    StatusCode::CONFLICT,
                    json!({"error": "Source could not be added"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/sources"),
                    json!({"id": "bad", "url": "-inject"}),
                    StatusCode::BAD_REQUEST,
                    json!({"error": "Invalid source URL"}),
                ),
                (
                    Method::DELETE,
                    format!("{PREFIX}/sources/missing"),
                    json!({}),
                    StatusCode::NOT_FOUND,
                    json!({"error": "Source not found"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/rules"),
                    json!({}),
                    StatusCode::BAD_REQUEST,
                    json!({"error": "id is required"}),
                ),
                (
                    Method::DELETE,
                    format!("{PREFIX}/rules/missing"),
                    json!({}),
                    StatusCode::NOT_FOUND,
                    json!({"error": "Rule not found"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/sources/missing/start"),
                    json!({}),
                    StatusCode::NOT_FOUND,
                    json!({"error": "Source not found"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/sources/missing/stop"),
                    json!({}),
                    StatusCode::NOT_FOUND,
                    json!({"error": "Source not found"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/sources/missing/test"),
                    json!({}),
                    StatusCode::BAD_REQUEST,
                    json!({"error": "No URL provided"}),
                ),
                (
                    Method::POST,
                    format!("{PREFIX}/sources/missing/test"),
                    json!({"url": "-inject"}),
                    StatusCode::BAD_REQUEST,
                    json!({"error": "Invalid source URL"}),
                ),
                (
                    Method::GET,
                    format!("{PREFIX}/missing/mjpeg"),
                    json!({}),
                    StatusCode::NOT_FOUND,
                    json!({"error": "Source not found"}),
                ),
            ];
            for (method, path, request_body, expected_status, expected_body) in cases {
                assert_eq!(
                    call_json(&app, method, &path, request_body).await,
                    (expected_status, expected_body),
                    "{path}"
                );
            }

            let (code, body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/start"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::INTERNAL_SERVER_ERROR);
            assert_eq!(body["error"], "Failed to start source");
            assert_eq!(body["source"]["id"], "cam");
        });
    }

    #[test]
    fn unreachable_python_rule_errors_are_not_treated_as_parity_gates() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = fixture_state(FixtureOutcome::Connected, Vec::new(), false).await;
            let app = routes().with_state(state);
            let (add_status, _) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/rules"),
                json!({"id": "permissive", "conditions": []}),
            )
            .await;
            let (update_status, body) = call_json(
                &app,
                Method::PUT,
                &format!("{PREFIX}/rules/upsert"),
                json!({"conditions": []}),
            )
            .await;
            assert_eq!(add_status, StatusCode::CREATED);
            assert_eq!(update_status, StatusCode::OK);
            assert_eq!(body["rule"]["id"], "upsert");
        });
    }

    #[test]
    fn source_test_normal_failure_fixture_is_200_with_resolution() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, calls) = fixture_state(FixtureOutcome::Ended, Vec::new(), false).await;
            let app = routes().with_state(state);
            let response = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/ad-hoc/test"),
                json!({"url": "https://camera.test/live"}),
            )
            .await;
            assert_eq!(
                response,
                (
                    StatusCode::OK,
                    json!({"ok": false, "resolution": {"width": 0, "height": 0}})
                )
            );
            assert_eq!(calls.load(Ordering::SeqCst), 1);
        });
    }

    #[test]
    fn source_test_exception_fixture_is_200_with_sanitized_error() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, calls) = fixture_state(FixtureOutcome::Error, Vec::new(), false).await;
            let app = routes().with_state(state);
            let response = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/ad-hoc/test"),
                json!({"url": "https://camera.test/live"}),
            )
            .await;
            assert_eq!(
                response,
                (
                    StatusCode::OK,
                    json!({"ok": false, "error": "Source test failed"})
                )
            );
            assert_eq!(calls.load(Ordering::SeqCst), 1);
        });
    }

    #[test]
    fn source_test_registered_url_fallback_fixture_calls_domain_api() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, calls) =
                fixture_state(FixtureOutcome::Connected, vec![source("saved")], false).await;
            let app = routes().with_state(state);
            let response = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/saved/test"),
                json!({}),
            )
            .await;
            assert_eq!(
                response,
                (
                    StatusCode::OK,
                    json!({"ok": true, "resolution": {"width": 640, "height": 480}})
                )
            );
            assert_eq!(calls.load(Ordering::SeqCst), 1);
        });
    }

    #[test]
    fn device_domain_error_fixture_remains_http_200() {
        let result = devices_response(Err(DeviceError::Detection(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "injected",
        ))));
        run_bounded_test(TEST_TIMEOUT, async {
            assert_eq!(
                json_response(result).await,
                (
                    StatusCode::OK,
                    json!({
                        "status": "error",
                        "devices": [],
                        "error": "Device detection failed"
                    })
                )
            );
        });
    }

    #[test]
    fn status_fixture_has_exactly_nine_pipeline_keys() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = fixture_state(FixtureOutcome::Connected, Vec::new(), false).await;
            let app = routes().with_state(state);
            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            let keys = body["pipeline"].as_object().unwrap();
            assert_eq!(keys.len(), 9);
            for key in [
                "running",
                "queue_size",
                "skip_rate",
                "fps",
                "backend_pref",
                "model_name",
                "conf_threshold",
                "result_sources",
                "batch_paused",
            ] {
                assert!(keys.contains_key(key), "missing pipeline key: {key}");
            }
        });
    }

    /// T9 plan step 7 / spec `2026-08-12` L574: `backend_pref` is a deliberate
    /// divergence from Python (whose default is `"auto"`). The parity harness
    /// carries `skip_body_compare` for `/stream/status`, so nothing else in
    /// the suite pins this exact string — this contract test is the only
    /// place that does, and it must fail loudly on any value other than the
    /// literal `"yu-infer"`.
    #[test]
    fn status_backend_pref_is_fixed_to_yu_infer() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = fixture_state(FixtureOutcome::Connected, Vec::new(), false).await;
            let app = routes().with_state(state);
            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(
                body["pipeline"]["backend_pref"].as_str(),
                Some("yu-infer"),
                "backend_pref must be the literal string \"yu-infer\", got {:?}",
                body["pipeline"]["backend_pref"]
            );
        });
    }

    /// Plan T9 step 8: pin the intentional `running` difference against Python.
    ///
    /// Rust derives `running` from whether any source is `Active` or
    /// `Reconnecting` (`registry.rs::pipeline_running`), so stopping the last
    /// active source flips it to `false`. Python derives it from the liveness of
    /// a single shared pipeline worker thread (`stream_pipeline.py:110`:
    /// `self._worker is not None and self._worker.is_alive()`), and the stop
    /// route never stops that worker — `stream_routes_sources.py:64` calls
    /// `pipe.start()` on start, while the stop route at `:78-79` only calls
    /// `mgr.stop_source()` and `pipe.update_source_count()`. The only caller of
    /// `StreamPipeline.stop()` in the whole tree is `core/web/shutdown.py:161`,
    /// i.e. server shutdown. So Python answers `true` here and Rust answers
    /// `false`.
    ///
    /// This is a declared intentional difference (spec diff table, `running`
    /// row), NOT a defect to be "fixed" by making Rust match Python. The parity
    /// harness cannot see it: `/status` carries `skip_body_compare`, and a
    /// harness run only observes the idle state, where both sides agree.
    ///
    /// The plan words this step as a two-server integration test. That form is
    /// no longer constructible: step 4 removed `register_stream_routes(bp)`, so
    /// no live Python stream surface remains to compare against. The Python
    /// value above is therefore established by reading the executed path end to
    /// end (the four lines cited), not by a live measurement.
    ///
    /// `registry.rs::pipeline_running_follows_active_or_reconnecting_sources_only`
    /// already covers the same transition at the registry layer; this test adds
    /// the HTTP `/status` surface, which is what the difference is observed on.
    #[test]
    fn status_running_is_false_after_stopping_the_last_active_source() {
        run_bounded_test(TEST_TIMEOUT, async {
            let state = frame_source_state("cam", 32, 24).await;
            let app = routes().with_state(state);

            let (code, _) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/start"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);

            // `FrameFactory` keeps emitting frames, so the source stays `Active`
            // instead of ending right after `Connected` the way `FixtureFactory`
            // does. Poll observable state with a bounded deadline rather than a
            // fixed sleep — see the module doc's test rules.
            timeout(Duration::from_secs(5), async {
                loop {
                    let (_, body) =
                        call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;
                    if body["pipeline"]["running"] == json!(true) {
                        return;
                    }
                    tokio::task::yield_now().await;
                }
            })
            .await
            .expect("running became true within the bounded deadline");

            let (code, _) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/stop"),
                json!({}),
            )
            .await;
            assert_eq!(code, StatusCode::OK);

            let (code, body) =
                call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;
            assert_eq!(code, StatusCode::OK);
            assert_eq!(
                body["pipeline"]["running"],
                json!(false),
                "after stopping the last active source Rust must report running=false \
                 (Python reports true here — declared intentional difference), got {:?}",
                body["pipeline"]["running"]
            );
        });
    }

    #[test]
    fn devices_handler_calls_t7d_domain_api() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = fixture_state(FixtureOutcome::Connected, Vec::new(), false).await;
            let app = routes().with_state(state);
            let calls = Arc::new(AtomicUsize::new(0));
            devices::observe_enumerate_calls(Arc::clone(&calls), async {
                let response =
                    call_json(&app, Method::GET, &format!("{PREFIX}/devices"), json!({})).await;
                assert_eq!(response.0, StatusCode::OK);
            })
            .await;
            assert_eq!(calls.load(Ordering::SeqCst), 1);
        });
    }

    #[test]
    fn all_fifteen_handlers_apply_admin_scope() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) =
                fixture_state(FixtureOutcome::Connected, vec![source("cam")], true).await;
            let app = routes().with_state(state);
            let cases = [
                (Method::GET, format!("{PREFIX}/sources")),
                (Method::POST, format!("{PREFIX}/sources")),
                (Method::DELETE, format!("{PREFIX}/sources/cam")),
                (Method::GET, format!("{PREFIX}/rules")),
                (Method::POST, format!("{PREFIX}/rules")),
                (Method::PUT, format!("{PREFIX}/rules/rule")),
                (Method::DELETE, format!("{PREFIX}/rules/rule")),
                (Method::GET, format!("{PREFIX}/status")),
                (Method::POST, format!("{PREFIX}/sources/cam/start")),
                (Method::POST, format!("{PREFIX}/sources/cam/stop")),
                (Method::POST, format!("{PREFIX}/sources/cam/test")),
                (Method::GET, format!("{PREFIX}/devices")),
                (Method::GET, format!("{PREFIX}/cam/mjpeg")),
                (Method::GET, format!("{PREFIX}/recordings")),
                (Method::GET, format!("{PREFIX}/snapshot/file.jpg")),
            ];
            assert_eq!(cases.len(), 15);
            for (method, path) in cases {
                let (status, body) = call_json(&app, method, &path, json!({})).await;
                assert_eq!(status, StatusCode::FORBIDDEN, "{path}");
                assert_eq!(body["error"], "Insufficient scope: requires 'admin'");
            }
        });
    }

    #[derive(Clone, Default)]
    struct CapturedLogs(Arc<Mutex<Vec<u8>>>);

    impl Write for CapturedLogs {
        fn write(&mut self, bytes: &[u8]) -> io::Result<usize> {
            self.0.lock().unwrap().extend_from_slice(bytes);
            Ok(bytes.len())
        }

        fn flush(&mut self) -> io::Result<()> {
            Ok(())
        }
    }

    impl<'a> MakeWriter<'a> for CapturedLogs {
        type Writer = Self;

        fn make_writer(&'a self) -> Self::Writer {
            self.clone()
        }
    }

    #[test]
    fn secret_fixture_does_not_leak_outside_source_or_rule_responses() {
        run_bounded_test(TEST_TIMEOUT, async {
            let source_url =
                "rtsp://camera-user:camera-password@example.test/live?token=response-secret";
            let webhook_url = "http://webhook-user:webhook-password@127.0.0.1:1/webhook-secret";
            let webhook_secret = "hmac-secret";
            let logs = CapturedLogs::default();
            let subscriber = tracing_subscriber::fmt().with_writer(logs.clone()).finish();
            let _guard = tracing::subscriber::set_default(subscriber);

            let (state, _) = fixture_state(FixtureOutcome::Error, Vec::new(), false).await;
            let app = routes().with_state(state);
            let (_, response_body) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/secret/test"),
                json!({"url": source_url}),
            )
            .await;

            let hub = Arc::new(SseHub::new());
            let mut events = hub.subscribe();
            let executor = ActionExecutor::spawn(
                std::path::PathBuf::from("."),
                reqwest::Client::new(),
                Arc::clone(&hub),
            );
            let actions = vec![
                json!({"type": "sse", "channel": "safe.event"}),
                json!({"type": "webhook", "url": webhook_url, "secret": webhook_secret}),
            ];
            let results = executor
                .submit(ActionBatch {
                    source_id: "safe-source".to_string(),
                    rule: serde_json::from_value(json!({
                        "id": "safe-rule",
                        "actions": actions
                    }))
                    .unwrap(),
                    detections: vec![json!({"class": "person", "confidence": 0.9})],
                    trigger_frame: TriggerFrame {
                        bytes: Bytes::from_static(&[0; 12]),
                        width: 2,
                        height: 2,
                    },
                    actions,
                })
                .await;
            let event = tokio::time::timeout(Duration::from_secs(2), events.recv())
                .await
                .expect("SSE fixture timed out")
                .unwrap();
            executor.recorder().shutdown().await;

            let exposed = format!(
                "{}\n{}\n{}\n{}",
                response_body,
                serde_json::to_string(&results).unwrap(),
                serde_json::to_string(&event.data).unwrap(),
                String::from_utf8(logs.0.lock().unwrap().clone()).unwrap(),
            );
            for secret in [
                source_url,
                "camera-user",
                "camera-password",
                "response-secret",
                webhook_url,
                "webhook-user",
                "webhook-password",
                "webhook-secret",
                webhook_secret,
            ] {
                assert!(
                    !exposed.contains(secret),
                    "plaintext secret leaked: {secret}"
                );
            }
        });
    }

    /// The port carried the plaintext exposure of `/sources`, `/rules` and
    /// `/status` forward as a known defect; closing it is what this change is for.
    /// The URL stays recognisable — only its credential-bearing parts go.
    #[test]
    fn source_rule_and_status_responses_carry_no_plaintext_credential() {
        run_bounded_test(TEST_TIMEOUT, async {
            let source_url =
                "rtsp://camera-user:camera-password@example.test/live?token=response-secret";
            let webhook_url = "http://webhook-user:webhook-password@127.0.0.1:1/webhook-path";
            let webhook_secret = "hmac-secret-value";

            let (state, _) = fixture_state(
                FixtureOutcome::Connected,
                vec![StreamSourceConfig {
                    id: "cam".to_string(),
                    url: source_url.to_string(),
                    name: "cam".to_string(),
                }],
                false,
            )
            .await;
            let app = routes().with_state(state);

            let (_, created) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/rules"),
                json!({
                    "id": "leaky",
                    "actions": [
                        {"type": "webhook", "url": webhook_url, "secret": webhook_secret}
                    ]
                }),
            )
            .await;
            let (_, sources) =
                call_json(&app, Method::GET, &format!("{PREFIX}/sources"), json!({})).await;
            let (_, rules) =
                call_json(&app, Method::GET, &format!("{PREFIX}/rules"), json!({})).await;
            let (_, status) =
                call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;

            let exposed = format!("{created}\n{sources}\n{rules}\n{status}");
            for secret in [
                source_url,
                "camera-password",
                "response-secret",
                webhook_url,
                "webhook-password",
                webhook_secret,
            ] {
                assert!(!exposed.contains(secret), "plaintext leaked: {secret}");
            }

            // Masked, not erased: the operator must still be able to tell the
            // cameras apart in the list.
            assert!(exposed.contains("example.test"), "{exposed}");
            assert!(exposed.contains("127.0.0.1"), "{exposed}");
        });
    }

    // --- T9 plan step 10: process-middleware auth/CSRF wiring for all 15 routes ---
    //
    // Every test above drives `routes()` through `Router::oneshot` directly, which
    // never runs process middleware (`middleware::from_fn`/`from_fn_with_state`
    // layers). So `require_admin_scope` being called from every handler above does
    // not prove the *production* stack (main.rs) actually enforces auth/CSRF — a
    // route could be wired into main.rs without ever passing through `auth_middleware`
    // and these oneshot tests would not notice. The tests below build the router with
    // the identical layer stack and order `main.rs` applies:
    //   .layer(auth_middleware) -> .layer(session_layer) -> .layer(csrf::layer) -> .layer(security::layer)
    // (each `.layer()` call wraps the router, so the *last* layer added runs *first*
    // on an incoming request: security -> csrf -> session -> auth -> handler).
    // This mirrors the precedent in
    // `routes/lan_cowork_split_integration_tests.rs::authenticated_initiator`.

    /// Builds the router with the exact process-middleware stack `main.rs` applies
    /// (see the block comment above), so a request actually exercises auth + CSRF.
    fn full_middleware_app(state: SharedState) -> Router {
        Router::new()
            .merge(routes())
            .layer(middleware::from_fn_with_state(
                state.clone(),
                crate::auth::middleware::auth_middleware,
            ))
            .layer(SessionManagerLayer::new(MemoryStore::default()))
            .layer(middleware::from_fn(crate::csrf::layer))
            .layer(middleware::from_fn(crate::security::layer))
            .with_state(state)
    }

    /// The 15 route contracts wired in `routes()`, addressed against a fixture
    /// that has a source `"cam"` and a rule `"rule-one"` present (so path params
    /// resolve to a real resource; the auth/CSRF tests never reach business logic
    /// so the exact target only needs to exist as a valid path).
    fn all_fifteen_routes() -> [(Method, String); 15] {
        [
            (Method::GET, format!("{PREFIX}/sources")),
            (Method::POST, format!("{PREFIX}/sources")),
            (Method::DELETE, format!("{PREFIX}/sources/cam")),
            (Method::POST, format!("{PREFIX}/sources/cam/start")),
            (Method::POST, format!("{PREFIX}/sources/cam/stop")),
            (Method::POST, format!("{PREFIX}/sources/cam/test")),
            (Method::GET, format!("{PREFIX}/rules")),
            (Method::POST, format!("{PREFIX}/rules")),
            (Method::PUT, format!("{PREFIX}/rules/rule-one")),
            (Method::DELETE, format!("{PREFIX}/rules/rule-one")),
            (Method::GET, format!("{PREFIX}/status")),
            (Method::GET, format!("{PREFIX}/devices")),
            (Method::GET, format!("{PREFIX}/cam/mjpeg")),
            (Method::GET, format!("{PREFIX}/recordings")),
            (Method::GET, format!("{PREFIX}/snapshot/missing.jpg")),
        ]
    }

    /// Writes a minimal `config.json` with a single API key so
    /// `crate::auth::apikey::verify_key` can resolve it (mirrors the shape used by
    /// `auth::apikey`'s own tests: sha256 hex digest as `key_hash`).
    fn write_api_key_config(config_path: &std::path::Path, raw_key: &str, scopes: &[&str]) {
        use sha2::{Digest, Sha256};
        let hash = hex::encode(Sha256::digest(raw_key.as_bytes()));
        let config = json!({
            "api_keys": [{
                "id": "ak_test",
                "key_hash": hash,
                "key_prefix": raw_key.get(..8).unwrap_or(raw_key),
                "label": "test key",
                "scopes": scopes,
            }]
        });
        std::fs::write(config_path, config.to_string()).unwrap();
    }

    fn bare_request(method: Method, path: &str) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(path)
            .header(header::CONTENT_TYPE, "application/json")
            .body(Body::from("{}"))
            .unwrap()
    }

    /// Sets `X-Requested-With`, one of CSRF's pass conditions, so a request clears
    /// the CSRF layer (which runs before auth) without needing an `Authorization`
    /// header — isolating the response to whatever the auth layer decides.
    fn xrw_request(method: Method, path: &str) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(path)
            .header(header::CONTENT_TYPE, "application/json")
            .header("x-requested-with", "XMLHttpRequest")
            .body(Body::from("{}"))
            .unwrap()
    }

    /// A `Bearer` `Authorization` header is *also* one of CSRF's pass conditions
    /// (API keys are CSRF-exempt; see `csrf::layer`'s doc), so admin/non-admin
    /// requests below clear CSRF unconditionally and land on the auth decision.
    fn bearer_request(method: Method, path: &str, raw_key: &str) -> Request<Body> {
        Request::builder()
            .method(method)
            .uri(path)
            .header(header::CONTENT_TYPE, "application/json")
            .header(header::AUTHORIZATION, format!("Bearer {raw_key}"))
            .body(Body::from("{}"))
            .unwrap()
    }

    #[test]
    fn unauthenticated_requests_are_rejected_by_full_middleware_across_all_fifteen_routes() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) =
                fixture_state(FixtureOutcome::Connected, vec![source("cam")], true).await;
            state
                .hailo_yolo_stream
                .as_ref()
                .unwrap()
                .add_rule(rule_from_body(json!({"id": "rule-one"}), None))
                .await
                .unwrap();
            let app = full_middleware_app(state);

            for (method, path) in all_fifteen_routes() {
                // Non-GET requests carry X-Requested-With to clear the CSRF layer
                // (which runs before auth_middleware) so the response reflects the
                // auth decision alone, not a CSRF short-circuit.
                let request = if method == Method::GET {
                    bare_request(method.clone(), &path)
                } else {
                    xrw_request(method.clone(), &path)
                };
                let response = app.clone().oneshot(request).await.unwrap();
                assert_eq!(
                    response.status(),
                    StatusCode::UNAUTHORIZED,
                    "{method} {path}"
                );
                let (_, body) = json_response(response).await;
                assert_eq!(
                    body,
                    json!({"error": "認証が必要です", "code": "pin_auth_required"}),
                    "{method} {path}"
                );
            }
        });
    }

    #[test]
    fn non_admin_scope_requests_are_rejected_across_all_fifteen_routes() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempfile::tempdir().unwrap();
            let state = fixture_state_with_root(root.path().to_path_buf(), true).await;
            state
                .hailo_yolo_stream
                .as_ref()
                .unwrap()
                .add_source(source("cam"))
                .await
                .unwrap();
            state
                .hailo_yolo_stream
                .as_ref()
                .unwrap()
                .add_rule(rule_from_body(json!({"id": "rule-one"}), None))
                .await
                .unwrap();
            let raw_key = "sk_scan_only_0123456789abcdef";
            write_api_key_config(&state.config.config_path, raw_key, &["scan"]);
            let app = full_middleware_app(state);

            for (method, path) in all_fifteen_routes() {
                let response = app
                    .clone()
                    .oneshot(bearer_request(method.clone(), &path, raw_key))
                    .await
                    .unwrap();
                assert_eq!(response.status(), StatusCode::FORBIDDEN, "{method} {path}");
                let (_, body) = json_response(response).await;
                assert_eq!(
                    body,
                    json!({"ok": false, "error": "Insufficient scope: requires 'admin'"}),
                    "{method} {path}"
                );
            }
        });
    }

    /// Any response shape produced by the auth or CSRF layers (as opposed to a
    /// handler). Used to prove an admin/XRW request actually reached the handler,
    /// not just "some 2xx/4xx came back".
    fn is_auth_or_csrf_block(status: StatusCode, body: &Value) -> bool {
        (status == StatusCode::UNAUTHORIZED
            && body.get("code").and_then(Value::as_str) == Some("pin_auth_required"))
            || (status == StatusCode::FORBIDDEN
                && body.get("error").and_then(Value::as_str) == Some("csrf_required"))
            || (status == StatusCode::FORBIDDEN
                && body
                    .get("error")
                    .and_then(Value::as_str)
                    .is_some_and(|e| e.starts_with("Insufficient scope")))
    }

    #[test]
    fn admin_scope_requests_reach_handlers_across_thirteen_registry_backed_routes() {
        // Covers all routes except `recordings`/`snapshot`, which need a real
        // filesystem root and are covered separately below.
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, calls) =
                fixture_state(FixtureOutcome::Connected, vec![source("cam")], true).await;
            let raw_key = "sk_admin_0123456789abcdef012345";
            write_api_key_config(&state.config.config_path, raw_key, &["admin"]);
            let app = full_middleware_app(state);

            async fn call(
                app: &Router,
                method: Method,
                path: &str,
                raw_key: &str,
            ) -> (StatusCode, Value) {
                let response = app
                    .clone()
                    .oneshot(bearer_request(method, path, raw_key))
                    .await
                    .unwrap();
                json_response(response).await
            }

            let (status, body) =
                call(&app, Method::GET, &format!("{PREFIX}/sources"), raw_key).await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "GET sources: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);
            assert_eq!(body["sources"].as_array().unwrap().len(), 1);

            let response = app
                .clone()
                .oneshot(Request::builder()
                    .method(Method::POST)
                    .uri(format!("{PREFIX}/sources"))
                    .header(header::CONTENT_TYPE, "application/json")
                    .header(header::AUTHORIZATION, format!("Bearer {raw_key}"))
                    .body(Body::from(
                        json!({"id": "new2", "url": "https://camera.test/live", "name": "New2"})
                            .to_string(),
                    ))
                    .unwrap())
                .await
                .unwrap();
            let (status, body) = json_response(response).await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "POST sources: {body:?}"
            );
            assert_eq!(status, StatusCode::CREATED);

            let (status, body) = call(
                &app,
                Method::DELETE,
                &format!("{PREFIX}/sources/new2"),
                raw_key,
            )
            .await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "DELETE sources/new2: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) = call(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/start"),
                raw_key,
            )
            .await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "POST sources/cam/start: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) = call(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/stop"),
                raw_key,
            )
            .await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "POST sources/cam/stop: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) = call(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/test"),
                raw_key,
            )
            .await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "POST sources/cam/test: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) = call(&app, Method::GET, &format!("{PREFIX}/rules"), raw_key).await;
            assert!(!is_auth_or_csrf_block(status, &body), "GET rules: {body:?}");
            assert_eq!(status, StatusCode::OK);

            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::POST)
                        .uri(format!("{PREFIX}/rules"))
                        .header(header::CONTENT_TYPE, "application/json")
                        .header(header::AUTHORIZATION, format!("Bearer {raw_key}"))
                        .body(Body::from(json!({"id": "rule-two"}).to_string()))
                        .unwrap(),
                )
                .await
                .unwrap();
            let (status, body) = json_response(response).await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "POST rules: {body:?}"
            );
            assert_eq!(status, StatusCode::CREATED);

            let (status, body) = call(
                &app,
                Method::PUT,
                &format!("{PREFIX}/rules/rule-two"),
                raw_key,
            )
            .await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "PUT rules/rule-two: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) = call(
                &app,
                Method::DELETE,
                &format!("{PREFIX}/rules/rule-two"),
                raw_key,
            )
            .await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "DELETE rules/rule-two: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) =
                call(&app, Method::GET, &format!("{PREFIX}/status"), raw_key).await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "GET status: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let (status, body) =
                call(&app, Method::GET, &format!("{PREFIX}/devices"), raw_key).await;
            assert!(
                !is_auth_or_csrf_block(status, &body),
                "GET devices: {body:?}"
            );
            assert_eq!(status, StatusCode::OK);

            let response = app
                .clone()
                .oneshot(bearer_request(
                    Method::GET,
                    &format!("{PREFIX}/cam/mjpeg"),
                    raw_key,
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK, "GET cam/mjpeg");
            assert_eq!(
                response.headers()[header::CONTENT_TYPE],
                "multipart/x-mixed-replace; boundary=frame"
            );

            // `start` and `test` each spawn a connection via the factory (see
            // `source_test_registered_url_fallback_fixture_calls_domain_api`
            // above, which independently proves `test` alone spawns once).
            assert_eq!(calls.load(Ordering::SeqCst), 2);
        });
    }

    #[test]
    fn admin_scope_requests_reach_handlers_for_recordings_and_snapshot() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempfile::tempdir().unwrap();
            let state = fixture_state_with_root(root.path().to_path_buf(), true).await;
            let raw_key = "sk_admin_0123456789abcdef012345";
            write_api_key_config(&state.config.config_path, raw_key, &["admin"]);
            let snapshots = root.path().join("detections").join("snapshots");
            tokio::fs::create_dir_all(&snapshots).await.unwrap();
            tokio::fs::write(snapshots.join("real.jpg"), b"SNAPSHOT-BYTES")
                .await
                .unwrap();
            let app = full_middleware_app(state);

            let response = app
                .clone()
                .oneshot(bearer_request(
                    Method::GET,
                    &format!("{PREFIX}/recordings"),
                    raw_key,
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK, "GET recordings");

            let response = app
                .clone()
                .oneshot(bearer_request(
                    Method::GET,
                    &format!("{PREFIX}/snapshot/real.jpg"),
                    raw_key,
                ))
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK, "GET snapshot/real.jpg");
            let bytes = to_bytes(response.into_body(), 1 << 20).await.unwrap();
            assert_eq!(&bytes[..], b"SNAPSHOT-BYTES");
        });
    }

    #[test]
    fn get_routes_do_not_require_csrf_token() {
        // pin_auth disabled so a bare GET (no Authorization, no X-Requested-With)
        // isolates the response to whatever the CSRF layer decides — the auth
        // layer is a pass-through with pin_auth_enabled=false.
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempfile::tempdir().unwrap();
            let state = fixture_state_with_root(root.path().to_path_buf(), false).await;
            state
                .hailo_yolo_stream
                .as_ref()
                .unwrap()
                .add_source(source("cam"))
                .await
                .unwrap();
            let app = full_middleware_app(state);

            for path in [
                format!("{PREFIX}/sources"),
                format!("{PREFIX}/rules"),
                format!("{PREFIX}/status"),
                format!("{PREFIX}/devices"),
                format!("{PREFIX}/cam/mjpeg"),
                format!("{PREFIX}/recordings"),
                format!("{PREFIX}/snapshot/missing.jpg"),
            ] {
                let response = app
                    .clone()
                    .oneshot(bare_request(Method::GET, &path))
                    .await
                    .unwrap();
                let status = response.status();
                let bytes = to_bytes(response.into_body(), 1 << 20).await.unwrap();
                let is_csrf_block = status == StatusCode::FORBIDDEN
                    && serde_json::from_slice::<Value>(&bytes)
                        .ok()
                        .and_then(|v| v.get("error").and_then(Value::as_str).map(str::to_string))
                        == Some("csrf_required".to_string());
                assert!(
                    !is_csrf_block,
                    "{path} was blocked by CSRF: {status} {bytes:?}"
                );
            }
        });
    }

    #[test]
    fn non_get_routes_require_csrf_token() {
        // pin_auth disabled: same isolation rationale as the GET test above.
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) =
                fixture_state(FixtureOutcome::Connected, vec![source("cam")], false).await;
            let app = full_middleware_app(state);

            for (method, path) in [
                (Method::POST, format!("{PREFIX}/sources")),
                (Method::DELETE, format!("{PREFIX}/sources/cam")),
                (Method::POST, format!("{PREFIX}/sources/cam/start")),
                (Method::POST, format!("{PREFIX}/sources/cam/stop")),
                (Method::POST, format!("{PREFIX}/sources/cam/test")),
                (Method::POST, format!("{PREFIX}/rules")),
                (Method::PUT, format!("{PREFIX}/rules/rule-one")),
                (Method::DELETE, format!("{PREFIX}/rules/rule-one")),
            ] {
                // Without X-Requested-With / Authorization: blocked at the CSRF layer.
                let response = app
                    .clone()
                    .oneshot(bare_request(method.clone(), &path))
                    .await
                    .unwrap();
                assert_eq!(response.status(), StatusCode::FORBIDDEN, "{method} {path}");
                let (_, body) = json_response(response).await;
                assert_eq!(
                    body,
                    json!({"ok": false, "error": "csrf_required"}),
                    "{method} {path}"
                );

                // With X-Requested-With: clears CSRF and (pin_auth disabled) reaches
                // the handler — proving the block above was CSRF, not something else.
                let response = app
                    .clone()
                    .oneshot(xrw_request(method.clone(), &path))
                    .await
                    .unwrap();
                let status = response.status();
                assert_ne!(
                    status,
                    StatusCode::FORBIDDEN,
                    "{method} {path} still blocked with XRW"
                );
            }
        });
    }

    /// T9 plan step 9 / spec `2026-08-12` "検証方針": the parity harness treats
    /// MJPEG as `sse:true` and only compares status/content-type, never body.
    /// This bounded integration test reads exactly the first multipart part
    /// over the real HTTP route and validates it byte-for-byte: the `--frame`
    /// boundary line, the `Content-Type`/`Content-Length` headers, and that
    /// the payload is a real JPEG (`0xFF 0xD8` SOI … `0xFF 0xD9` EOI). It never
    /// waits for stream EOF — MJPEG never ends — mirroring the bounded
    /// single-`.next()` pattern in `mjpeg.rs`'s own
    /// `lagged_viewer_resumes_and_first_part_is_byte_exact`.
    #[test]
    fn mjpeg_first_part_is_byte_exact_over_http() {
        run_bounded_test(TEST_TIMEOUT, async {
            const WIDTH: u32 = 32;
            const HEIGHT: u32 = 24;
            let state = frame_source_state("cam", WIDTH, HEIGHT).await;
            let app = routes().with_state(state);

            let (start_status, _) = call_json(
                &app,
                Method::POST,
                &format!("{PREFIX}/sources/cam/start"),
                json!({}),
            )
            .await;
            assert_eq!(start_status, StatusCode::OK);

            // `FrameFactory::spawn` pushes `Connected`+`Frame` synchronously into
            // an unbounded channel, but `SourceTask::run` still consumes them
            // asynchronously, and `SourceStream::body()` returns an empty body
            // until `MjpegHub`'s producer has observed `Connected` and called
            // `SourceStream::start()`. Poll the real `/status` route (explicit
            // synchronization on observable state, bounded by a real-time
            // timeout) instead of assuming a fixed delay is long enough — the
            // module doc forbids the latter as a source of intermittent
            // failures.
            timeout(Duration::from_secs(5), async {
                loop {
                    let (_, body) =
                        call_json(&app, Method::GET, &format!("{PREFIX}/status"), json!({})).await;
                    let active = body["sources"].as_array().is_some_and(|sources| {
                        sources
                            .iter()
                            .any(|source| source["id"] == "cam" && source["state"] == "active")
                    });
                    if active {
                        return;
                    }
                    tokio::task::yield_now().await;
                }
            })
            .await
            .expect("source became active within the bounded deadline");

            let response = app
                .clone()
                .oneshot(
                    Request::builder()
                        .method(Method::GET)
                        .uri(format!("{PREFIX}/cam/mjpeg"))
                        .body(Body::empty())
                        .unwrap(),
                )
                .await
                .unwrap();
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(
                response.headers()[header::CONTENT_TYPE],
                "multipart/x-mixed-replace; boundary=frame"
            );

            let mut body = response.into_body().into_data_stream();
            // Bounded real-time wait for exactly one part. This deliberately
            // stops after the first item instead of reading to stream EOF,
            // which an MJPEG stream never reaches.
            let part = timeout(Duration::from_secs(10), body.next())
                .await
                .expect("first MJPEG part within the bounded deadline")
                .expect("stream yielded a part before closing")
                .expect("part read did not error");

            let expected_prefix = b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: ";
            assert!(
                part.starts_with(expected_prefix),
                "unexpected multipart header prefix: {:?}",
                String::from_utf8_lossy(&part[..part.len().min(80)])
            );
            let after_prefix = &part[expected_prefix.len()..];
            let length_field_end = after_prefix
                .windows(4)
                .position(|window| window == b"\r\n\r\n")
                .expect("Content-Length line is terminated by the header/body separator");
            let content_length: usize = std::str::from_utf8(&after_prefix[..length_field_end])
                .unwrap()
                .parse()
                .expect("Content-Length value is a valid integer");

            let jpeg_start = expected_prefix.len() + length_field_end + 4;
            let jpeg_end = jpeg_start + content_length;
            assert_eq!(
                part.len(),
                jpeg_end + 2,
                "part length must equal header + Content-Length payload + trailing CRLF"
            );
            assert_eq!(
                &part[jpeg_end..],
                b"\r\n",
                "part must end with a trailing CRLF after the JPEG payload"
            );

            let jpeg = &part[jpeg_start..jpeg_end];
            assert_eq!(
                &jpeg[..2],
                &[0xFF, 0xD8],
                "JPEG payload must start with the SOI marker"
            );
            assert_eq!(
                &jpeg[jpeg.len() - 2..],
                &[0xFF, 0xD9],
                "JPEG payload must end with the EOI marker"
            );
        });
    }
}
