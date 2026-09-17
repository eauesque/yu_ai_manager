use std::{path::PathBuf, sync::Arc, time::Duration};

use chrono::Local;
use hmac::{Hmac, Mac};
use reqwest::{Method, Url};
use serde_json::{json, Map, Value};
use sha2::Sha256;
use tokio::{
    sync::{mpsc, oneshot, Semaphore},
    time::Instant,
};

use crate::sse::{SseEvent, SseHub};

use super::{
    mjpeg::encode_jpeg,
    recorder::{Recorder, RecordingRequest, TriggerState},
    rules::{execute_actions, ActionBatch},
};

const ACTION_QUEUE_CAPACITY: usize = 8;
const ACTION_CONCURRENCY: usize = 4;
const BATCH_TIMEOUT: Duration = Duration::from_secs(10);
const DEFAULT_WEBHOOK_TIMEOUT: Duration = Duration::from_secs(5);
const SNAPSHOT_QUALITY: u8 = 90;

#[derive(Clone)]
pub(crate) struct ActionExecutor {
    tx: mpsc::Sender<QueuedBatch>,
    recorder: Recorder,
    #[cfg(test)]
    dispatcher: Arc<StreamEventDispatcher>,
    #[cfg(test)]
    permits: Arc<Semaphore>,
}

struct QueuedBatch {
    enqueued_at: Instant,
    batch: ActionBatch,
    reply: oneshot::Sender<Vec<Value>>,
}

struct ActionExecutorTask {
    rx: mpsc::Receiver<QueuedBatch>,
    owners: ActionOwners,
    permits: Arc<Semaphore>,
}

#[derive(Clone)]
struct ActionOwners {
    project_root: PathBuf,
    client: reqwest::Client,
    dispatcher: Arc<StreamEventDispatcher>,
    recorder: Recorder,
}

struct StreamEventDispatcher {
    hub: Arc<SseHub>,
    #[cfg(test)]
    calls: std::sync::atomic::AtomicUsize,
}

impl StreamEventDispatcher {
    fn new(hub: Arc<SseHub>) -> Self {
        Self {
            hub,
            #[cfg(test)]
            calls: std::sync::atomic::AtomicUsize::new(0),
        }
    }

    fn publish(&self, event_type: String, data: Value) {
        #[cfg(test)]
        self.calls.fetch_add(1, std::sync::atomic::Ordering::SeqCst);
        self.hub.send(SseEvent {
            event_type,
            timestamp: std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs_f64(),
            data,
            source: "yolo_stream".to_string(),
        });
    }
}

impl ActionExecutor {
    pub(crate) fn spawn(
        project_root: PathBuf,
        client: reqwest::Client,
        sse_hub: Arc<SseHub>,
    ) -> Self {
        let (handle, task) =
            Self::new_with_recorder(project_root, client, sse_hub, Recorder::spawn());
        tokio::spawn(task.run());
        handle
    }

    fn new_with_recorder(
        project_root: PathBuf,
        client: reqwest::Client,
        sse_hub: Arc<SseHub>,
        recorder: Recorder,
    ) -> (Self, ActionExecutorTask) {
        let (tx, rx) = mpsc::channel(ACTION_QUEUE_CAPACITY);
        let permits = Arc::new(Semaphore::new(ACTION_CONCURRENCY));
        let dispatcher = Arc::new(StreamEventDispatcher::new(sse_hub));
        (
            Self {
                tx,
                recorder: recorder.clone(),
                #[cfg(test)]
                dispatcher: Arc::clone(&dispatcher),
                #[cfg(test)]
                permits: Arc::clone(&permits),
            },
            ActionExecutorTask {
                rx,
                owners: ActionOwners {
                    project_root,
                    client,
                    dispatcher,
                    recorder,
                },
                permits,
            },
        )
    }

    #[cfg(test)]
    fn new(
        project_root: PathBuf,
        client: reqwest::Client,
        sse_hub: Arc<SseHub>,
    ) -> (Self, ActionExecutorTask) {
        Self::new_with_recorder(project_root, client, sse_hub, Recorder::spawn())
    }

    pub(crate) fn recorder(&self) -> Recorder {
        self.recorder.clone()
    }

    pub(crate) async fn submit(&self, batch: ActionBatch) -> Vec<Value> {
        match self.enqueue(batch) {
            Ok(reply) => reply.await.unwrap_or_else(|_| {
                vec![error_result(
                    "batch",
                    "Action executor stopped before completion",
                )]
            }),
            Err(results) => results,
        }
    }

    fn enqueue(&self, batch: ActionBatch) -> Result<oneshot::Receiver<Vec<Value>>, Vec<Value>> {
        let action_types = action_types(&batch);
        let (reply_tx, reply_rx) = oneshot::channel();
        match self.tx.try_send(QueuedBatch {
            enqueued_at: Instant::now(),
            batch,
            reply: reply_tx,
        }) {
            Ok(()) => Ok(reply_rx),
            Err(mpsc::error::TrySendError::Full(_)) => {
                Err(error_results(&action_types, "Action queue full"))
            }
            Err(mpsc::error::TrySendError::Closed(_)) => Err(error_results(
                &action_types,
                "Action executor is unavailable",
            )),
        }
    }
}

impl ActionExecutorTask {
    async fn run(mut self) {
        while let Some(queued) = self.rx.recv().await {
            let owners = self.owners.clone();
            let permits = Arc::clone(&self.permits);
            tokio::spawn(async move {
                let deadline = queued.enqueued_at + BATCH_TIMEOUT;
                let action_types = action_types(&queued.batch);
                let results = match tokio::time::timeout_at(
                    deadline,
                    execute_batch(queued.batch, owners, permits, deadline),
                )
                .await
                {
                    Ok(results) => results,
                    Err(_) => error_results(&action_types, "Action timeout"),
                };
                let _ = queued.reply.send(results);
            });
        }
    }
}

async fn execute_batch(
    batch: ActionBatch,
    owners: ActionOwners,
    permits: Arc<Semaphore>,
    deadline: Instant,
) -> Vec<Value> {
    let batch = Arc::new(batch);
    execute_actions(
        &batch.rule,
        {
            let batch = Arc::clone(&batch);
            let owners = owners.clone();
            let permits = Arc::clone(&permits);
            move |action| {
                snapshot_action(
                    Arc::clone(&batch),
                    owners.clone(),
                    Arc::clone(&permits),
                    action,
                )
            }
        },
        {
            let batch = Arc::clone(&batch);
            move |action, snapshot| {
                run_action(
                    Arc::clone(&batch),
                    owners.clone(),
                    Arc::clone(&permits),
                    action,
                    snapshot,
                    deadline,
                )
            }
        },
    )
    .await
}

async fn snapshot_action(
    batch: Arc<ActionBatch>,
    owners: ActionOwners,
    permits: Arc<Semaphore>,
    action: Value,
) -> Result<Value, String> {
    let _permit = permits
        .acquire_owned()
        .await
        .map_err(|_| "Action executor is unavailable".to_string())?;
    let quality = action
        .get("quality")
        .and_then(Value::as_u64)
        .and_then(|value| u8::try_from(value).ok())
        .map_or(SNAPSHOT_QUALITY, |value| value.clamp(1, 100));
    let safe_id: String = batch
        .source_id
        .chars()
        .map(|character| {
            if character.is_ascii_alphanumeric() || matches!(character, '-' | '_' | '.') {
                character
            } else {
                '_'
            }
        })
        .collect();
    let filename = format!(
        "{}_{}.jpg",
        Local::now().format("%Y-%m-%d_%H%M%S_%6f"),
        safe_id
    );
    let relative_path = format!("./detections/snapshots/{filename}");
    let directory = owners.project_root.join("detections").join("snapshots");
    tokio::fs::create_dir_all(&directory)
        .await
        .map_err(|error| error.to_string())?;
    let jpeg = encode_jpeg(
        &batch.trigger_frame.bytes,
        batch.trigger_frame.width,
        batch.trigger_frame.height,
        quality,
    )?;
    tokio::fs::write(directory.join(&filename), jpeg)
        .await
        .map_err(|error| error.to_string())?;
    Ok(json!({
        "type": "snapshot",
        "status": "ok",
        "path": relative_path,
        "filename": filename,
    }))
}

async fn run_action(
    batch: Arc<ActionBatch>,
    owners: ActionOwners,
    permits: Arc<Semaphore>,
    action: Value,
    snapshot: Option<Value>,
    deadline: Instant,
) -> Result<Value, String> {
    let _permit = permits
        .acquire_owned()
        .await
        .map_err(|_| "Action executor is unavailable".to_string())?;
    match action.get("type").and_then(Value::as_str).unwrap_or("") {
        "record" => record_action(&batch, &owners, &action).await,
        "webhook" => webhook_action(&batch, &owners, &action, snapshot.as_ref(), deadline).await,
        "sse" => Ok(stream_event_action(&batch, &owners, &action, false)),
        "mcp_event" => Ok(stream_event_action(&batch, &owners, &action, true)),
        "agent" => Ok(error_result("agent", "Agent action unavailable")),
        action_type => Ok(error_result(
            action_type,
            &format!("Unknown action: {action_type}"),
        )),
    }
}

async fn record_action(
    batch: &ActionBatch,
    owners: &ActionOwners,
    action: &Value,
) -> Result<Value, String> {
    let configured_dir = action
        .get("save_dir")
        .and_then(Value::as_str)
        .unwrap_or("./detections/videos");
    let configured_dir = PathBuf::from(configured_dir);
    let save_dir = if configured_dir.is_absolute() {
        configured_dir
    } else {
        owners.project_root.join(configured_dir)
    };
    let duration = Duration::from_secs(
        action
            .get("duration_sec")
            .and_then(Value::as_u64)
            .unwrap_or(30),
    );
    let max_duration = Duration::from_secs(
        action
            .get("max_duration_sec")
            .and_then(Value::as_u64)
            .unwrap_or(300),
    );
    let result = owners
        .recorder
        .trigger(
            RecordingRequest {
                source_id: batch.source_id.clone(),
                save_dir,
                duration,
                max_duration,
                extend_mode: action
                    .get("extend_mode")
                    .and_then(Value::as_str)
                    .unwrap_or("fixed")
                    .to_string(),
                width: batch.trigger_frame.width,
                height: batch.trigger_frame.height,
                fps: action.get("fps").and_then(Value::as_f64).unwrap_or(15.0),
            },
            batch.trigger_frame.bytes.clone(),
        )
        .await?;
    Ok(json!({
        "type": "record",
        "status": match result.state {
            TriggerState::Started => "started",
            TriggerState::Extended => "extended",
        },
        "path": result.path,
    }))
}

async fn webhook_action(
    batch: &ActionBatch,
    owners: &ActionOwners,
    action: &Value,
    snapshot: Option<&Value>,
    deadline: Instant,
) -> Result<Value, String> {
    let url = action
        .get("url")
        .and_then(Value::as_str)
        .ok_or_else(|| "No URL specified".to_string())?;
    let parsed = Url::parse(url).map_err(|_| "Invalid webhook URL".to_string())?;
    if !matches!(parsed.scheme(), "http" | "https") || parsed.host_str().is_none() {
        return Err("Invalid webhook URL".to_string());
    }
    let method = action
        .get("method")
        .and_then(Value::as_str)
        .unwrap_or("POST")
        .to_ascii_uppercase()
        .parse::<Method>()
        .map_err(|_| "Invalid webhook method".to_string())?;
    let mut payload = Map::from_iter([
        ("event".to_string(), json!("detection")),
        (
            "timestamp".to_string(),
            json!(Local::now().format("%Y-%m-%dT%H:%M:%S%.6f").to_string()),
        ),
        (
            "source".to_string(),
            json!({"id": batch.source_id, "name": ""}),
        ),
        (
            "rule".to_string(),
            json!({"id": batch.rule.id, "name": batch.rule.name}),
        ),
        ("detections".to_string(), json!(batch.detections)),
    ]);
    if let Some(path) = snapshot
        .and_then(|value| value.get("path"))
        .and_then(Value::as_str)
    {
        if let Some(filename) = std::path::Path::new(path)
            .file_name()
            .and_then(|value| value.to_str())
        {
            payload.insert(
                "snapshot_url".to_string(),
                json!(format!("/ext/hailo-yolo/api/stream/snapshot/{filename}")),
            );
            payload.insert("snapshot_path".to_string(), json!(path));
        }
    }
    let body = serde_json::to_vec(&payload).map_err(|error| error.to_string())?;
    let configured_timeout = action
        .get("timeout")
        .and_then(Value::as_f64)
        .filter(|value| value.is_finite() && *value > 0.0)
        .map(Duration::from_secs_f64)
        .unwrap_or(DEFAULT_WEBHOOK_TIMEOUT);
    let remaining = deadline.saturating_duration_since(Instant::now());
    let mut request = owners
        .client
        .request(method, parsed)
        .timeout(configured_timeout.min(remaining))
        .header(reqwest::header::CONTENT_TYPE, "application/json")
        .header(reqwest::header::USER_AGENT, "YU-AI-Manager/YOLO");
    if let Some(secret) = action
        .get("secret")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
    {
        let mut signer = Hmac::<Sha256>::new_from_slice(secret.as_bytes())
            .map_err(|_| "Invalid webhook secret".to_string())?;
        signer.update(&body);
        request = request.header(
            "X-YOLO-Signature",
            format!("sha256={}", hex::encode(signer.finalize().into_bytes())),
        );
    }
    let response = request
        .body(body)
        .send()
        .await
        .map_err(|_| "Webhook request failed".to_string())?;
    Ok(json!({
        "type": "webhook",
        "status": "ok",
        "http_status": response.status().as_u16(),
    }))
}

fn stream_event_action(
    batch: &ActionBatch,
    owners: &ActionOwners,
    action: &Value,
    mcp_event: bool,
) -> Value {
    let (result_field, event_type, action_type) = if mcp_event {
        (
            "event",
            action
                .get("event")
                .and_then(Value::as_str)
                .unwrap_or("yolo_stream.detection"),
            "mcp_event",
        )
    } else {
        (
            "channel",
            action
                .get("channel")
                .and_then(Value::as_str)
                .unwrap_or("yolo_stream"),
            "sse",
        )
    };
    owners.dispatcher.publish(
        event_type.to_string(),
        json!({
            "source_id": batch.source_id,
            "rule": batch.rule.id,
            "rule_name": batch.rule.name,
            "detections": batch.detections,
        }),
    );
    json!({"type": action_type, "status": "ok", result_field: event_type})
}

fn action_types(batch: &ActionBatch) -> Vec<String> {
    batch
        .actions
        .iter()
        .map(|action| {
            action
                .get("type")
                .and_then(Value::as_str)
                .unwrap_or("unknown")
                .to_string()
        })
        .collect()
}

fn error_results(action_types: &[String], error: &str) -> Vec<Value> {
    action_types
        .iter()
        .map(|action_type| error_result(action_type, error))
        .collect()
}

fn error_result(action_type: &str, error: &str) -> Value {
    json!({"type": action_type, "status": "error", "error": error})
}

#[cfg(test)]
mod tests {
    use std::sync::{
        atomic::{AtomicBool, AtomicUsize, Ordering},
        Mutex,
    };

    use axum::{
        body::Bytes,
        extract::State,
        http::{HeaderMap, Method as AxumMethod, StatusCode},
        routing::any,
        Router,
    };
    use tempfile::TempDir;
    use tokio::{net::TcpListener, sync::Notify, task::JoinHandle};

    use super::super::{
        rules::{DetectionRule, TriggerFrame},
        run_bounded_paused_test, run_bounded_test,
    };
    use super::*;

    const TEST_TIMEOUT: Duration = Duration::from_secs(8);

    #[derive(Clone)]
    struct FixtureState {
        requests: Arc<Mutex<Vec<CapturedRequest>>>,
        active: Arc<AtomicUsize>,
        maximum_active: Arc<AtomicUsize>,
        released: Arc<AtomicBool>,
        notify: Arc<Notify>,
        block: bool,
    }

    struct CapturedRequest {
        method: AxumMethod,
        headers: HeaderMap,
        body: Bytes,
    }

    impl FixtureState {
        fn new(block: bool) -> Self {
            Self {
                requests: Arc::new(Mutex::new(Vec::new())),
                active: Arc::new(AtomicUsize::new(0)),
                maximum_active: Arc::new(AtomicUsize::new(0)),
                released: Arc::new(AtomicBool::new(!block)),
                notify: Arc::new(Notify::new()),
                block,
            }
        }

        fn count(&self) -> usize {
            self.requests.lock().unwrap().len()
        }

        fn release(&self) {
            self.released.store(true, Ordering::SeqCst);
            self.notify.notify_waiters();
        }

        async fn wait_for_count(&self, count: usize) {
            while self.count() < count {
                tokio::task::yield_now().await;
            }
        }
    }

    async fn fixture_handler(
        State(state): State<FixtureState>,
        method: AxumMethod,
        headers: HeaderMap,
        body: Bytes,
    ) -> StatusCode {
        let active = state.active.fetch_add(1, Ordering::SeqCst) + 1;
        state.maximum_active.fetch_max(active, Ordering::SeqCst);
        state.requests.lock().unwrap().push(CapturedRequest {
            method,
            headers,
            body,
        });
        if state.block {
            while !state.released.load(Ordering::SeqCst) {
                state.notify.notified().await;
            }
        }
        state.active.fetch_sub(1, Ordering::SeqCst);
        StatusCode::NO_CONTENT
    }

    async fn fixture(block: bool) -> (String, FixtureState, JoinHandle<()>) {
        let listener = TcpListener::bind("127.0.0.1:0").await.unwrap();
        assert!(listener.local_addr().unwrap().ip().is_loopback());
        let address = listener.local_addr().unwrap();
        let state = FixtureState::new(block);
        let app = Router::new()
            .route("/hook", any(fixture_handler))
            .with_state(state.clone());
        let server = tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });
        (format!("http://{address}/hook"), state, server)
    }

    fn batch(actions: Vec<Value>) -> ActionBatch {
        let rule: DetectionRule = serde_json::from_value(json!({
            "id": "rule-1",
            "name": "Front door",
            "actions": actions,
        }))
        .unwrap();
        ActionBatch {
            source_id: "cam/one".to_string(),
            actions: rule.actions.clone(),
            rule,
            detections: vec![json!({
                "class": "person",
                "confidence": 0.9,
                "bbox": [0.0, 0.0, 1.0, 1.0],
            })],
            trigger_frame: TriggerFrame {
                bytes: bytes::Bytes::from_static(&[10; 12]),
                width: 2,
                height: 2,
            },
        }
    }

    fn executor(root: &TempDir, hub: Arc<SseHub>) -> (ActionExecutor, ActionExecutorTask) {
        ActionExecutor::new(root.path().to_path_buf(), reqwest::Client::new(), hub)
    }

    fn result<'a>(results: &'a [Value], action_type: &str) -> &'a Value {
        results
            .iter()
            .find(|result| result["type"] == action_type)
            .unwrap()
    }

    #[test]
    fn six_actions_reach_intended_owners_once() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let hub = Arc::new(SseHub::new());
            let mut events = hub.subscribe();
            let (url, fixture, server) = fixture(false).await;
            let (executor, task) = executor(&root, hub);
            tokio::spawn(task.run());
            let secret = "fixture-secret";
            let record_dir = root.path().join("recordings");
            let results = executor
                .submit(batch(vec![
                    json!({"type": "webhook", "url": url, "method": "PUT", "timeout": 2.0, "secret": secret}),
                    json!({"type": "sse", "channel": "custom.sse"}),
                    json!({"type": "snapshot", "quality": 88}),
                    json!({"type": "mcp_event", "event": "custom.mcp"}),
                    json!({"type": "agent", "url": url}),
                    json!({"type": "record", "save_dir": record_dir.display().to_string(), "duration_sec": 5, "max_duration_sec": 8, "extend_mode": "extend_max", "fps": 1.0}),
                ]))
                .await;

            assert_eq!(results.len(), 6);
            assert_eq!(fixture.count(), 1, "agent must not make an HTTP request");
            assert_eq!(
                result(&results, "agent"),
                &json!({"type": "agent", "status": "error", "error": "Agent action unavailable"})
            );
            assert_eq!(result(&results, "record")["status"], "started");
            let recordings = executor.recorder.status().await;
            assert_eq!(recordings.len(), 1);
            assert_eq!(recordings["cam/one"].frame_count, 1);
            assert_eq!(recordings["cam/one"].extend_mode, "extend_max");
            assert_eq!(
                PathBuf::from(&recordings["cam/one"].path).parent(),
                Some(record_dir.as_path())
            );
            assert_eq!(result(&results, "sse")["channel"], "custom.sse");
            assert_eq!(result(&results, "mcp_event")["event"], "custom.mcp");
            assert_eq!(executor.dispatcher.calls.load(Ordering::SeqCst), 2);

            let first_event = events.recv().await.unwrap();
            let second_event = events.recv().await.unwrap();
            let mut event_types = [
                first_event.event_type.clone(),
                second_event.event_type.clone(),
            ];
            event_types.sort();
            assert_eq!(event_types, ["custom.mcp", "custom.sse"]);
            for event in [first_event, second_event] {
                assert_eq!(event.data["source_id"], "cam/one");
                assert_eq!(event.data["rule"], "rule-1");
                assert_eq!(event.data["rule_name"], "Front door");
                assert!(event.data["detections"].is_array());
            }

            executor.recorder.shutdown().await;
            let requests = fixture.requests.lock().unwrap();
            let request = &requests[0];
            assert_eq!(request.method, AxumMethod::PUT);
            assert_eq!(
                request.headers[reqwest::header::USER_AGENT],
                "YU-AI-Manager/YOLO"
            );
            assert_eq!(
                request.headers[reqwest::header::CONTENT_TYPE],
                "application/json"
            );
            let payload: Value = serde_json::from_slice(&request.body).unwrap();
            assert_eq!(payload["event"], "detection");
            assert!(payload["timestamp"].as_str().unwrap().contains('T'));
            assert_eq!(payload["source"], json!({"id": "cam/one", "name": ""}));
            assert_eq!(
                payload["rule"],
                json!({"id": "rule-1", "name": "Front door"})
            );
            assert_eq!(payload["detections"].as_array().unwrap().len(), 1);
            let snapshot_path = payload["snapshot_path"].as_str().unwrap();
            assert!(snapshot_path.starts_with("./detections/snapshots/"));
            assert_eq!(
                payload["snapshot_url"],
                format!(
                    "/ext/hailo-yolo/api/stream/snapshot/{}",
                    std::path::Path::new(snapshot_path)
                        .file_name()
                        .unwrap()
                        .to_string_lossy()
                )
            );
            assert!(root
                .path()
                .join(snapshot_path.trim_start_matches("./"))
                .is_file());
            let mut signer = Hmac::<Sha256>::new_from_slice(secret.as_bytes()).unwrap();
            signer.update(&request.body);
            assert_eq!(
                request.headers["X-YOLO-Signature"],
                format!("sha256={}", hex::encode(signer.finalize().into_bytes()))
            );
            drop(requests);
            server.abort();
        });
    }

    #[test]
    fn snapshot_finishes_before_concurrent_remaining_actions() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let (url, fixture, server) = fixture(true).await;
            let (executor, task) = executor(&root, Arc::new(SseHub::new()));
            tokio::spawn(task.run());
            let submitted = tokio::spawn({
                let executor = executor.clone();
                async move {
                    executor
                        .submit(batch(vec![
                            json!({"type": "webhook", "url": url, "timeout": 2.0}),
                            json!({"type": "snapshot"}),
                            json!({"type": "webhook", "url": url, "timeout": 2.0}),
                        ]))
                        .await
                }
            });
            fixture.wait_for_count(2).await;
            assert_eq!(fixture.maximum_active.load(Ordering::SeqCst), 2);
            let snapshot_path = {
                let requests = fixture.requests.lock().unwrap();
                let payloads: Vec<Value> = requests
                    .iter()
                    .map(|request| serde_json::from_slice(&request.body).unwrap())
                    .collect();
                assert_eq!(payloads[0]["snapshot_path"], payloads[1]["snapshot_path"]);
                payloads[0]["snapshot_path"].as_str().unwrap().to_string()
            };
            assert!(root
                .path()
                .join(snapshot_path.trim_start_matches("./"))
                .is_file());
            fixture.release();
            assert_eq!(submitted.await.unwrap().len(), 3);
            server.abort();
        });
    }

    #[test]
    fn failed_snapshot_is_not_added_to_webhook_context() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            std::fs::write(root.path().join("detections"), b"not a directory").unwrap();
            let (url, fixture, server) = fixture(false).await;
            let (executor, task) = executor(&root, Arc::new(SseHub::new()));
            tokio::spawn(task.run());
            let results = executor
                .submit(batch(vec![
                    json!({"type": "snapshot"}),
                    json!({"type": "webhook", "url": url}),
                ]))
                .await;
            assert_eq!(result(&results, "snapshot")["status"], "error");
            let requests = fixture.requests.lock().unwrap();
            let payload: Value = serde_json::from_slice(&requests[0].body).unwrap();
            assert!(payload.get("snapshot_url").is_none());
            assert!(payload.get("snapshot_path").is_none());
            drop(requests);
            server.abort();
        });
    }

    #[test]
    fn four_permits_limit_actions_across_batches() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let (url, fixture, server) = fixture(true).await;
            let (executor, task) = executor(&root, Arc::new(SseHub::new()));
            tokio::spawn(task.run());
            let actions = || {
                (0..4)
                    .map(|_| json!({"type": "webhook", "url": url, "timeout": 4.0}))
                    .collect()
            };
            let first = tokio::spawn({
                let executor = executor.clone();
                let batch = batch(actions());
                async move { executor.submit(batch).await }
            });
            let second = tokio::spawn({
                let executor = executor.clone();
                let batch = batch(actions());
                async move { executor.submit(batch).await }
            });
            fixture.wait_for_count(4).await;
            for _ in 0..100 {
                tokio::task::yield_now().await;
            }
            assert_eq!(fixture.count(), 4);
            assert_eq!(fixture.maximum_active.load(Ordering::SeqCst), 4);
            fixture.release();
            assert_eq!(first.await.unwrap().len(), 4);
            assert_eq!(second.await.unwrap().len(), 4);
            assert_eq!(fixture.count(), 8);
            assert_eq!(fixture.maximum_active.load(Ordering::SeqCst), 4);
            server.abort();
        });
    }

    #[test]
    fn ninth_pending_batch_is_rejected_without_external_execution() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let (url, fixture, server) = fixture(false).await;
            let (executor, _task) = executor(&root, Arc::new(SseHub::new()));
            let mut replies = Vec::new();
            for _ in 0..ACTION_QUEUE_CAPACITY {
                replies.push(
                    executor
                        .enqueue(batch(vec![json!({"type": "webhook", "url": url})]))
                        .unwrap(),
                );
            }
            let rejected = executor
                .enqueue(batch(vec![json!({"type": "webhook", "url": url})]))
                .unwrap_err();
            assert_eq!(rejected, vec![error_result("webhook", "Action queue full")]);
            assert_eq!(fixture.count(), 0);
            assert_eq!(replies.len(), ACTION_QUEUE_CAPACITY);
            server.abort();
        });
    }

    #[test]
    fn queued_batch_times_out_while_waiting_for_action_permit() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let (executor, task) = executor(&root, Arc::new(SseHub::new()));
            let held = Arc::clone(&executor.permits)
                .acquire_many_owned(ACTION_CONCURRENCY as u32)
                .await
                .unwrap();
            tokio::spawn(task.run());
            let reply = executor
                .enqueue(batch(vec![json!({"type": "agent"})]))
                .unwrap();
            tokio::time::advance(BATCH_TIMEOUT).await;
            let results = reply.await.unwrap();
            assert_eq!(results, vec![error_result("agent", "Action timeout")]);
            drop(held);
        });
    }

    #[test]
    fn timed_out_action_is_cancelled_without_retry_and_releases_permit() {
        run_bounded_paused_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let (url, fixture, server) = fixture(true).await;
            let (executor, task) = executor(&root, Arc::new(SseHub::new()));
            tokio::spawn(task.run());
            let submitted = tokio::spawn({
                let executor = executor.clone();
                async move {
                    executor
                        .submit(batch(vec![
                            json!({"type": "webhook", "url": url, "timeout": 30.0}),
                        ]))
                        .await
                }
            });
            fixture.wait_for_count(1).await;
            tokio::time::advance(BATCH_TIMEOUT).await;
            let results = submitted.await.unwrap();
            assert_eq!(result(&results, "webhook")["status"], "error");
            assert_eq!(fixture.count(), 1, "timed out action must not retry");
            let recovered = executor.submit(batch(vec![json!({"type": "agent"})])).await;
            assert_eq!(result(&recovered, "agent")["status"], "error");
            fixture.release();
            server.abort();
        });
    }

    #[test]
    fn webhook_uses_action_timeout() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = TempDir::new().unwrap();
            let (url, fixture, server) = fixture(true).await;
            let (executor, task) = executor(&root, Arc::new(SseHub::new()));
            tokio::spawn(task.run());
            let started = std::time::Instant::now();
            let results = executor
                .submit(batch(vec![
                    json!({"type": "webhook", "url": url, "timeout": 0.05}),
                ]))
                .await;
            assert_eq!(result(&results, "webhook")["status"], "error");
            assert!(started.elapsed() < Duration::from_secs(1));
            assert_eq!(fixture.count(), 1);
            fixture.release();
            server.abort();
        });
    }
}
