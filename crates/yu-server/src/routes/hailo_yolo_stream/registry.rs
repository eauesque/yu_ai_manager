use std::{
    collections::{BTreeMap, HashMap},
    sync::Arc,
};

use axum::response::Response;
use serde::Serialize;
use serde_json::Value;
use thiserror::Error;
use tokio::sync::{mpsc, oneshot, Mutex, RwLock, Semaphore};

use super::{
    actions::ActionExecutor,
    detect::DetectPipeline,
    draw::DrawnFrame,
    input::validate_source,
    mjpeg::MjpegHub,
    recorder::{Recorder, RecorderStatus},
    rules::{DetectionRule, RuleHandle, RuleTask, StreamConfig, StreamSourceConfig},
    source_task::{
        SourceFactory, SourceHandle, SourceState, SourceStatus, SourceTask, SourceTaskError,
        SourceTestResult, ValidatedFfmpegFactory,
    },
};

pub(crate) type SourceId = String;

const DEFAULT_MAX_SOURCES: usize = 4;
const MIN_MAX_SOURCES: usize = 1;
const MAX_MAX_SOURCES: usize = 8;
const CONFIG_CHANNEL_CAPACITY: usize = 32;

#[derive(Debug)]
pub(crate) enum ConfigCommand {
    UpsertSource {
        source: StreamSourceConfig,
        reply: oneshot::Sender<Result<(), ConfigWriteError>>,
    },
    DeleteSource {
        source_id: SourceId,
        reply: oneshot::Sender<Result<(), ConfigWriteError>>,
    },
    UpsertRule {
        rule: DetectionRule,
        reply: oneshot::Sender<Result<(), ConfigWriteError>>,
    },
    DeleteRule {
        rule_id: String,
        reply: oneshot::Sender<Result<(), ConfigWriteError>>,
    },
    /// Rewrite the current snapshot without changing it. The only way to migrate a
    /// plaintext config to the secret store without a user-visible mutation.
    PersistSnapshot {
        reply: oneshot::Sender<Result<(), ConfigWriteError>>,
    },
}

#[derive(Clone, Debug, Error, Eq, PartialEq)]
#[error("failed to persist stream config")]
pub(crate) struct ConfigWriteError;

impl ConfigCommand {
    pub(super) fn reply(self) -> oneshot::Sender<Result<(), ConfigWriteError>> {
        match self {
            Self::UpsertSource { reply, .. }
            | Self::DeleteSource { reply, .. }
            | Self::UpsertRule { reply, .. }
            | Self::DeleteRule { reply, .. }
            | Self::PersistSnapshot { reply } => reply,
        }
    }
}

#[derive(Debug, Error, Eq, PartialEq)]
pub(crate) enum RegistryError {
    #[error("source already exists")]
    Duplicate,
    #[error("source capacity reached")]
    Capacity,
    #[error("source not found")]
    NotFound,
    #[error("source is invalid")]
    InvalidSource,
    #[error("stream domain task is unavailable")]
    Unavailable,
    #[error(transparent)]
    Config(#[from] ConfigWriteError),
    #[error(transparent)]
    Task(#[from] SourceTaskError),
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub(crate) struct PipelineStatus {
    pub(crate) running: bool,
    pub(crate) queue_size: usize,
    pub(crate) skip_rate: usize,
    pub(crate) fps: f64,
    pub(crate) backend_pref: String,
    pub(crate) model_name: String,
    pub(crate) conf_threshold: f64,
    pub(crate) result_sources: Vec<SourceId>,
    pub(crate) batch_paused: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize)]
pub(crate) struct StatusSource {
    #[serde(flatten)]
    pub(crate) source: SourceStatus,
    pub(crate) viewers: usize,
}

pub(crate) struct StreamRegistry {
    sources: RwLock<HashMap<SourceId, SourceHandle>>,
}

impl StreamRegistry {
    fn new(sources: HashMap<SourceId, SourceHandle>) -> Self {
        Self {
            sources: RwLock::new(sources),
        }
    }

    pub(crate) async fn get(&self, source_id: &str) -> Option<SourceHandle> {
        self.sources.read().await.get(source_id).cloned()
    }

    async fn handles(&self) -> Vec<SourceHandle> {
        self.sources.read().await.values().cloned().collect()
    }

    pub(crate) async fn statuses(&self) -> Vec<SourceStatus> {
        let handles = self.handles().await;
        let mut statuses: Vec<_> = handles.iter().map(SourceHandle::status).collect();
        statuses.sort_by(|left, right| left.id.cmp(&right.id));
        statuses
    }

    pub(crate) async fn len(&self) -> usize {
        self.sources.read().await.len()
    }

    pub(crate) async fn is_empty(&self) -> bool {
        self.sources.read().await.is_empty()
    }
}

pub(crate) struct StreamState {
    pub(crate) registry: StreamRegistry,
    pub(crate) rule_tx: RuleHandle,
    pub(crate) config_tx: mpsc::Sender<ConfigCommand>,
    pub(crate) config_snapshot: Arc<RwLock<StreamConfig>>,
    settings: Arc<Value>,
    max_sources: usize,
    active_slots: Arc<Semaphore>,
    mutations: Mutex<()>,
    factory: Option<Arc<dyn SourceFactory>>,
    detector: DetectPipeline,
    mjpeg: MjpegHub,
    recorder: Option<Recorder>,
}

impl StreamState {
    pub(crate) fn new(
        restored: Vec<StreamSourceConfig>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
    ) -> Self {
        let snapshot = Arc::new(RwLock::new(StreamConfig {
            sources: restored.clone(),
            rules: Vec::new(),
        }));
        Self::build(
            restored,
            Vec::new(),
            settings,
            config_tx,
            snapshot,
            None,
            None,
            None,
        )
    }

    pub(crate) fn new_with_snapshot(
        restored: Vec<StreamSourceConfig>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
        config_snapshot: Arc<RwLock<StreamConfig>>,
    ) -> Self {
        let restored_rules = config_snapshot
            .try_read()
            .expect("stream config snapshot is unlocked during construction")
            .rules
            .clone();
        Self::build(
            restored,
            restored_rules,
            settings,
            config_tx,
            config_snapshot,
            None,
            None,
            None,
        )
    }

    pub(crate) fn new_with_snapshot_and_infer(
        restored: Vec<StreamSourceConfig>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
        config_snapshot: Arc<RwLock<StreamConfig>>,
        infer_client: Option<crate::infer_client::InferClient>,
    ) -> Self {
        let restored_rules = config_snapshot
            .try_read()
            .expect("stream config snapshot is unlocked during construction")
            .rules
            .clone();
        Self::build(
            restored,
            restored_rules,
            settings,
            config_tx,
            config_snapshot,
            None,
            infer_client,
            None,
        )
    }

    pub(crate) fn new_with_snapshot_infer_and_actions(
        restored: Vec<StreamSourceConfig>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
        config_snapshot: Arc<RwLock<StreamConfig>>,
        infer_client: Option<crate::infer_client::InferClient>,
        actions: ActionExecutor,
    ) -> Self {
        let restored_rules = config_snapshot
            .try_read()
            .expect("stream config snapshot is unlocked during construction")
            .rules
            .clone();
        Self::build(
            restored,
            restored_rules,
            settings,
            config_tx,
            config_snapshot,
            None,
            infer_client,
            Some(actions),
        )
    }

    pub(crate) fn with_config_stub(restored: Vec<StreamSourceConfig>, settings: Value) -> Self {
        let (config_tx, mut config_rx) = mpsc::channel::<ConfigCommand>(CONFIG_CHANNEL_CAPACITY);
        tokio::spawn(async move {
            while let Some(command) = config_rx.recv().await {
                let _ = command.reply().send(Ok(()));
            }
        });
        Self::new(restored, settings, config_tx)
    }

    #[cfg(test)]
    pub(super) fn with_factory(
        restored: Vec<StreamSourceConfig>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
        factory: Arc<dyn SourceFactory>,
    ) -> Self {
        let snapshot = Arc::new(RwLock::new(StreamConfig {
            sources: restored.clone(),
            rules: Vec::new(),
        }));
        Self::build(
            restored,
            Vec::new(),
            settings,
            config_tx,
            snapshot,
            Some(factory),
            None,
            None,
        )
    }

    #[cfg(test)]
    fn with_factory_and_actions(
        restored: Vec<StreamSourceConfig>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
        factory: Arc<dyn SourceFactory>,
        actions: ActionExecutor,
    ) -> Self {
        let snapshot = Arc::new(RwLock::new(StreamConfig {
            sources: restored.clone(),
            rules: Vec::new(),
        }));
        Self::build(
            restored,
            Vec::new(),
            settings,
            config_tx,
            snapshot,
            Some(factory),
            None,
            Some(actions),
        )
    }

    fn build(
        restored: Vec<StreamSourceConfig>,
        restored_rules: Vec<DetectionRule>,
        settings: Value,
        config_tx: mpsc::Sender<ConfigCommand>,
        config_snapshot: Arc<RwLock<StreamConfig>>,
        factory: Option<Arc<dyn SourceFactory>>,
        infer_client: Option<crate::infer_client::InferClient>,
        actions: Option<ActionExecutor>,
    ) -> Self {
        let max_sources = configured_max_sources(&settings);
        let active_slots = Arc::new(Semaphore::new(max_sources));
        let settings = Arc::new(settings);
        let recorder = actions.as_ref().map(ActionExecutor::recorder);
        let rule_tx = match actions {
            Some(executor) => RuleTask::spawn_with(restored_rules, move |batch| {
                let executor = executor.clone();
                async move {
                    let source_id = batch.source_id.clone();
                    let rule_id = batch.rule.id.clone();
                    let results = executor.submit(batch).await;
                    if results
                        .iter()
                        .any(|result| result.get("status").and_then(Value::as_str) == Some("error"))
                    {
                        tracing::warn!(%source_id, %rule_id, ?results, "Hailo YOLO action batch failed");
                    }
                }
            }),
            None => RuleTask::spawn(restored_rules),
        };
        let detector = DetectPipeline::new(infer_client, Arc::clone(&settings), rule_tx.clone());
        let mjpeg = MjpegHub::new();
        let sources = restored
            .into_iter()
            .map(|config| {
                let source_id = config.id.clone();
                let handle = match &factory {
                    Some(factory) => SourceTask::spawn(
                        config,
                        Arc::clone(factory),
                        Arc::clone(&active_slots),
                        Arc::new(super::frame_source::SystemClock::default()),
                    ),
                    None => SourceTask::spawn_ffmpeg(
                        config,
                        Arc::clone(&settings),
                        Arc::clone(&active_slots),
                    ),
                };
                detector.attach(source_id.clone(), &handle);
                mjpeg.attach(source_id.clone(), &handle, detector.clone());
                (source_id, handle)
            })
            .collect();
        Self {
            registry: StreamRegistry::new(sources),
            rule_tx,
            config_tx,
            config_snapshot,
            settings,
            max_sources,
            active_slots,
            mutations: Mutex::new(()),
            factory,
            detector,
            mjpeg,
            recorder,
        }
    }

    pub(crate) fn max_sources(&self) -> usize {
        self.max_sources
    }

    pub(crate) async fn add_source(
        &self,
        config: StreamSourceConfig,
    ) -> Result<SourceStatus, RegistryError> {
        validate_source(&config.url, &self.settings).map_err(|_| RegistryError::InvalidSource)?;
        let _mutation = self.mutations.lock().await;
        let status = {
            let mut sources = self.registry.sources.write().await;
            if sources.contains_key(&config.id) {
                return Err(RegistryError::Duplicate);
            }
            if sources.len() >= self.max_sources {
                return Err(RegistryError::Capacity);
            }
            let handle = match &self.factory {
                Some(factory) => SourceTask::spawn(
                    config.clone(),
                    Arc::clone(factory),
                    Arc::clone(&self.active_slots),
                    Arc::new(super::frame_source::SystemClock::default()),
                ),
                None => SourceTask::spawn_ffmpeg(
                    config.clone(),
                    Arc::clone(&self.settings),
                    Arc::clone(&self.active_slots),
                ),
            };
            let status = handle.status();
            self.detector.attach(config.id.clone(), &handle);
            self.mjpeg
                .attach(config.id.clone(), &handle, self.detector.clone());
            sources.insert(config.id.clone(), handle);
            status
        };
        self.persist(|reply| ConfigCommand::UpsertSource {
            source: config,
            reply,
        })
        .await?;
        Ok(status)
    }

    pub(crate) async fn start_source(
        &self,
        source_id: &str,
    ) -> Result<SourceStatus, RegistryError> {
        let status = self
            .registry
            .get(source_id)
            .await
            .ok_or(RegistryError::NotFound)?
            .start()
            .await
            .map_err(RegistryError::from)?;
        self.mjpeg.start_source(source_id);
        Ok(status)
    }

    pub(crate) async fn stop_source(&self, source_id: &str) -> Result<SourceStatus, RegistryError> {
        let handle = self
            .registry
            .get(source_id)
            .await
            .ok_or(RegistryError::NotFound)?;
        self.mjpeg.stop_source(source_id).await;
        if let Some(recorder) = &self.recorder {
            recorder.stop_source(source_id).await;
        }
        handle.stop().await.map_err(RegistryError::from)
    }

    pub(crate) async fn test_source(
        &self,
        source_id: &str,
        url: Option<&str>,
    ) -> Result<SourceTestResult, RegistryError> {
        let handle = match url {
            Some(url) => {
                validate_source(url, &self.settings).map_err(|_| RegistryError::InvalidSource)?;
                let config = StreamSourceConfig {
                    id: source_id.to_string(),
                    url: url.to_string(),
                    name: String::new(),
                };
                let factory = self.factory.clone().unwrap_or_else(|| {
                    Arc::new(ValidatedFfmpegFactory::new(
                        url.to_string(),
                        Arc::clone(&self.settings),
                    ))
                });
                SourceTask::spawn(
                    config,
                    factory,
                    Arc::clone(&self.active_slots),
                    Arc::new(super::frame_source::SystemClock::default()),
                )
            }
            None => {
                let handle = self
                    .registry
                    .get(source_id)
                    .await
                    .ok_or(RegistryError::NotFound)?;
                validate_source(&handle.status().url, &self.settings)
                    .map_err(|_| RegistryError::InvalidSource)?;
                handle
            }
        };
        handle.test().await.map_err(RegistryError::from)
    }

    pub(crate) async fn list_rules(&self) -> Result<Vec<DetectionRule>, RegistryError> {
        self.rule_tx
            .list_rules()
            .await
            .map_err(|_| RegistryError::Unavailable)
    }

    pub(crate) async fn add_rule(
        &self,
        rule: DetectionRule,
    ) -> Result<DetectionRule, RegistryError> {
        let _mutation = self.mutations.lock().await;
        let rule = self
            .rule_tx
            .add_rule(rule)
            .await
            .map_err(|_| RegistryError::Unavailable)?;
        self.persist(|reply| ConfigCommand::UpsertRule {
            rule: rule.clone(),
            reply,
        })
        .await?;
        Ok(rule)
    }

    pub(crate) async fn update_rule(
        &self,
        rule_id: &str,
        rule: DetectionRule,
    ) -> Result<DetectionRule, RegistryError> {
        let _mutation = self.mutations.lock().await;
        let rule = self
            .rule_tx
            .update_rule(rule_id.to_string(), rule)
            .await
            .map_err(|_| RegistryError::Unavailable)?;
        self.persist(|reply| ConfigCommand::UpsertRule {
            rule: rule.clone(),
            reply,
        })
        .await?;
        Ok(rule)
    }

    pub(crate) async fn delete_rule(&self, rule_id: &str) -> Result<(), RegistryError> {
        let _mutation = self.mutations.lock().await;
        let removed = self
            .rule_tx
            .remove_rule(rule_id.to_string())
            .await
            .map_err(|_| RegistryError::Unavailable)?;
        if !removed {
            return Err(RegistryError::NotFound);
        }
        self.persist(|reply| ConfigCommand::DeleteRule {
            rule_id: rule_id.to_string(),
            reply,
        })
        .await
    }

    pub(crate) async fn delete_source(&self, source_id: &str) -> Result<(), RegistryError> {
        let _mutation = self.mutations.lock().await;
        let handle = self
            .registry
            .get(source_id)
            .await
            .ok_or(RegistryError::NotFound)?;
        self.mjpeg.stop_source(source_id).await;
        if let Some(recorder) = &self.recorder {
            recorder.stop_source(source_id).await;
        }
        handle.delete().await?;
        {
            let mut sources = self.registry.sources.write().await;
            if sources
                .get(source_id)
                .is_some_and(|current| current.cmd_tx.same_channel(&handle.cmd_tx))
            {
                sources.remove(source_id);
            }
        }
        self.mjpeg.remove_source(source_id).await;
        self.persist(|reply| ConfigCommand::DeleteSource {
            source_id: source_id.to_string(),
            reply,
        })
        .await
    }

    pub(crate) async fn pipeline_status(&self) -> PipelineStatus {
        let statuses = self.registry.statuses().await;
        let detection = self.detector.snapshot().await;
        PipelineStatus {
            running: pipeline_running(&statuses),
            queue_size: detection.queue_size,
            skip_rate: detection.skip_rate,
            fps: detection.fps,
            backend_pref: "yu-infer".to_string(),
            model_name: detection.model_name,
            conf_threshold: detection.conf_threshold,
            result_sources: detection.result_sources,
            batch_paused: false,
        }
    }

    pub(crate) async fn status_sources(&self) -> Vec<StatusSource> {
        self.registry
            .statuses()
            .await
            .into_iter()
            .map(|source| StatusSource {
                viewers: self.mjpeg.viewer_count(&source.id),
                source,
            })
            .collect()
    }

    pub(crate) async fn recorder_status(&self) -> BTreeMap<String, RecorderStatus> {
        match &self.recorder {
            Some(recorder) => recorder.status().await,
            None => BTreeMap::new(),
        }
    }

    pub(crate) async fn mjpeg_response(&self, source_id: &str) -> Result<Response, RegistryError> {
        if self.registry.get(source_id).await.is_none() {
            return Err(RegistryError::NotFound);
        }
        Ok(self
            .mjpeg
            .response(source_id)
            .expect("registered source has an MJPEG stream"))
    }

    pub(crate) async fn latest_drawn(&self, source_id: &str) -> Option<Arc<DrawnFrame>> {
        self.detector.drawn_frame(source_id).await
    }

    pub(crate) async fn shutdown(&self) {
        self.mjpeg.shutdown().await;
        if let Some(recorder) = &self.recorder {
            recorder.shutdown().await;
        }
        let handles = self.registry.handles().await;
        futures_util::future::join_all(handles.iter().map(SourceHandle::stop)).await;
    }

    async fn persist(
        &self,
        command: impl FnOnce(oneshot::Sender<Result<(), ConfigWriteError>>) -> ConfigCommand,
    ) -> Result<(), RegistryError> {
        let (reply_tx, reply_rx) = oneshot::channel();
        self.config_tx
            .send(command(reply_tx))
            .await
            .map_err(|_| ConfigWriteError)?;
        reply_rx.await.map_err(|_| ConfigWriteError)??;
        Ok(())
    }
}

fn pipeline_running(statuses: &[SourceStatus]) -> bool {
    statuses.iter().any(|status| {
        matches!(
            status.state,
            SourceState::Active | SourceState::Reconnecting
        )
    })
}

fn configured_max_sources(settings: &Value) -> usize {
    settings
        .get("stream_max_sources")
        .and_then(Value::as_u64)
        .and_then(|value| usize::try_from(value).ok())
        .unwrap_or(DEFAULT_MAX_SOURCES)
        .clamp(MIN_MAX_SOURCES, MAX_MAX_SOURCES)
}

#[cfg(test)]
mod tests {
    use bytes::Bytes;
    use futures_util::StreamExt;
    use serde_json::json;
    use tempfile::TempDir;
    use tokio::time::{timeout, Duration};

    use super::super::run_bounded_test;
    use super::super::source_task::tests::{ManualClock, SyntheticFactory};
    use super::super::{recorder::RecordingRequest, rules::TriggerFrame};
    use super::*;
    use crate::sse::SseHub;

    const TEST_TIMEOUT: Duration = Duration::from_secs(3);

    fn source(id: &str) -> StreamSourceConfig {
        StreamSourceConfig {
            id: id.to_string(),
            url: "rtsp://camera.test/live".to_string(),
            name: String::new(),
        }
    }

    fn config_channel() -> mpsc::Sender<ConfigCommand> {
        let (tx, mut rx) = mpsc::channel::<ConfigCommand>(CONFIG_CHANNEL_CAPACITY);
        tokio::spawn(async move {
            while let Some(command) = rx.recv().await {
                let _ = command.reply().send(Ok(()));
            }
        });
        tx
    }

    fn synthetic_state(ids: &[&str], max: usize) -> (StreamState, Arc<SyntheticFactory>) {
        let clock = Arc::new(ManualClock::default());
        let factory = SyntheticFactory::new(clock, ids.len() + 2, false);
        let state = StreamState::with_factory(
            ids.iter().map(|id| source(id)).collect(),
            json!({"stream_max_sources": max}),
            config_channel(),
            factory.clone(),
        );
        (state, factory)
    }

    #[test]
    fn restored_sources_have_exact_idle_info_shape() {
        run_bounded_test(TEST_TIMEOUT, async {
            let state = StreamState::with_config_stub(vec![source("cam")], json!({}));
            let statuses = state.registry.statuses().await;
            assert_eq!(statuses.len(), 1);
            assert_eq!(
                serde_json::to_value(&statuses[0]).unwrap(),
                json!({
                    "id": "cam", "name": "cam", "url": "rtsp://camera.test/live",
                    "type": "rtsp", "state": "idle",
                    "resolution": {"width": 0, "height": 0},
                    "fps": 0.0, "frame_count": 0, "error": ""
                })
            );
        });
    }

    #[test]
    fn source_limit_defaults_and_clamps_to_extension_range() {
        assert_eq!(configured_max_sources(&json!({})), 4);
        assert_eq!(configured_max_sources(&json!({"stream_max_sources": 0})), 1);
        assert_eq!(configured_max_sources(&json!({"stream_max_sources": 9})), 8);
    }

    #[test]
    fn running_includes_only_active_and_reconnecting() {
        let mut status = SourceStatus::restored(&source("cam"));
        for state in [
            SourceState::Idle,
            SourceState::Connecting,
            SourceState::Stopped,
            SourceState::Error,
        ] {
            status.state = state;
            assert!(!pipeline_running(std::slice::from_ref(&status)));
        }
        for state in [SourceState::Active, SourceState::Reconnecting] {
            status.state = state;
            assert!(pipeline_running(std::slice::from_ref(&status)));
        }
    }

    #[test]
    fn registration_capacity_rejects_n_plus_one() {
        run_bounded_test(TEST_TIMEOUT, async {
            let state = StreamState::with_config_stub(Vec::new(), json!({"stream_max_sources": 2}));
            state.add_source(source("one")).await.unwrap();
            state.add_source(source("two")).await.unwrap();
            assert_eq!(
                state.add_source(source("three")).await.unwrap_err(),
                RegistryError::Capacity
            );
        });
    }

    #[test]
    fn persistence_failure_keeps_runtime_membership_and_returns_error() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (config_tx, mut config_rx) =
                mpsc::channel::<ConfigCommand>(CONFIG_CHANNEL_CAPACITY);
            tokio::spawn(async move {
                let command = config_rx.recv().await.unwrap();
                let _ = command.reply().send(Err(ConfigWriteError));
            });
            let state = StreamState::new(Vec::new(), json!({}), config_tx);
            assert_eq!(
                state.add_source(source("cam")).await.unwrap_err(),
                RegistryError::Config(ConfigWriteError)
            );
            assert_eq!(state.registry.len().await, 1);
        });
    }

    #[test]
    fn active_capacity_is_independent_of_restored_registration_count() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, factory) = synthetic_state(&["one", "two", "three"], 2);
            state.start_source("one").await.unwrap();
            state.start_source("two").await.unwrap();
            assert_eq!(
                state.start_source("three").await.unwrap_err(),
                RegistryError::Task(SourceTaskError::Capacity)
            );
            assert_eq!(factory.starts(), 2);
            state.stop_source("one").await.unwrap();
            state.stop_source("two").await.unwrap();
        });
    }

    #[test]
    fn over_capacity_restore_keeps_all_and_only_blocks_new_adds() {
        run_bounded_test(TEST_TIMEOUT, async {
            let state = StreamState::with_config_stub(
                vec![source("one"), source("two"), source("three")],
                json!({"stream_max_sources": 2}),
            );
            assert_eq!(state.registry.len().await, 3);
            assert!(state
                .registry
                .statuses()
                .await
                .iter()
                .all(|status| status.state == SourceState::Idle));
            assert_eq!(
                state.stop_source("three").await.unwrap().state,
                SourceState::Stopped
            );
            state.delete_source("three").await.unwrap();
            assert_eq!(state.registry.len().await, 2);
            assert_eq!(
                state.add_source(source("four")).await.unwrap_err(),
                RegistryError::Capacity
            );
            state.delete_source("two").await.unwrap();
            state.add_source(source("four")).await.unwrap();
            assert_eq!(state.registry.len().await, 2);
        });
    }

    #[test]
    fn pipeline_running_follows_active_or_reconnecting_sources_only() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = synthetic_state(&["cam"], 1);
            assert!(!state.pipeline_status().await.running);
            state.start_source("cam").await.unwrap();
            let handle = state.registry.get("cam").await.unwrap();
            let mut status_rx = handle.status_rx.clone();
            while status_rx.borrow().state != SourceState::Active {
                status_rx.changed().await.unwrap();
            }
            let pipeline = state.pipeline_status().await;
            assert!(pipeline.running);
            assert_eq!(pipeline.model_name, "yolov8n");
            assert_eq!(pipeline.conf_threshold, 0.25);
            assert!(!pipeline.batch_paused);
            state.stop_source("cam").await.unwrap();
            assert!(!state.pipeline_status().await.running);

            let clock = Arc::new(ManualClock::default());
            let factory = SyntheticFactory::reconnecting(clock);
            let reconnecting = StreamState::with_factory(
                vec![source("retry")],
                json!({"stream_max_sources": 1}),
                config_channel(),
                factory,
            );
            reconnecting.start_source("retry").await.unwrap();
            let handle = reconnecting.registry.get("retry").await.unwrap();
            let mut status_rx = handle.status_rx.clone();
            while status_rx.borrow().state != SourceState::Reconnecting {
                status_rx.changed().await.unwrap();
            }
            assert!(reconnecting.pipeline_status().await.running);
            reconnecting.stop_source("retry").await.unwrap();
            assert!(!reconnecting.pipeline_status().await.running);
        });
    }

    #[test]
    fn status_viewers_match_connect_disconnect_and_cancel_within_zero_to_four() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = synthetic_state(&["cam"], 1);
            state.start_source("cam").await.unwrap();
            let mut bodies = Vec::new();
            for expected in 1..=4 {
                bodies.push(state.mjpeg_response("cam").await.unwrap().into_body());
                let sources = state.status_sources().await;
                assert_eq!(sources[0].viewers, expected);
                assert!((0..=4).contains(&sources[0].viewers));
            }

            let mut rejected = state
                .mjpeg_response("cam")
                .await
                .unwrap()
                .into_body()
                .into_data_stream();
            assert!(timeout(Duration::from_secs(1), rejected.next())
                .await
                .unwrap()
                .is_none());
            assert_eq!(state.status_sources().await[0].viewers, 4);

            drop(bodies.pop());
            assert_eq!(state.status_sources().await[0].viewers, 3);
            let body = state.mjpeg_response("cam").await.unwrap().into_body();
            assert_eq!(state.status_sources().await[0].viewers, 4);
            let request = tokio::spawn(async move {
                let _body = body;
                std::future::pending::<()>().await;
            });
            request.abort();
            let _ = request.await;
            assert_eq!(state.status_sources().await[0].viewers, 3);
            drop(bodies);
            assert_eq!(state.status_sources().await[0].viewers, 0);
            state.shutdown().await;
        });
    }

    #[test]
    fn registry_shutdown_stops_all_sources_and_viewers() {
        run_bounded_test(TEST_TIMEOUT, async {
            let (state, _) = synthetic_state(&["one", "two"], 2);
            state.start_source("one").await.unwrap();
            state.start_source("two").await.unwrap();
            let mut one = state
                .mjpeg_response("one")
                .await
                .unwrap()
                .into_body()
                .into_data_stream();
            let mut two = state
                .mjpeg_response("two")
                .await
                .unwrap()
                .into_body()
                .into_data_stream();

            state.shutdown().await;
            assert!(timeout(Duration::from_secs(1), one.next())
                .await
                .unwrap()
                .is_none());
            assert!(timeout(Duration::from_secs(1), two.next())
                .await
                .unwrap()
                .is_none());
            assert!(state
                .registry
                .statuses()
                .await
                .iter()
                .all(|status| status.state == SourceState::Stopped));
            assert!(state
                .status_sources()
                .await
                .iter()
                .all(|source| source.viewers == 0));
        });
    }

    #[test]
    fn source_stop_delete_and_server_shutdown_finalize_recordings() {
        run_bounded_test(Duration::from_secs(12), async {
            let directory = TempDir::new().unwrap();
            let actions = ActionExecutor::spawn(
                directory.path().to_path_buf(),
                reqwest::Client::new(),
                Arc::new(SseHub::new()),
            );
            let recorder = actions.recorder();
            let clock = Arc::new(ManualClock::default());
            let factory = SyntheticFactory::new(clock, 6, false);
            let state = StreamState::with_factory_and_actions(
                ["stop", "delete", "shutdown-a", "shutdown-b"]
                    .into_iter()
                    .map(source)
                    .collect(),
                json!({"stream_max_sources": 4}),
                config_channel(),
                factory,
                actions,
            );
            let request = |source_id: &str| RecordingRequest {
                source_id: source_id.to_string(),
                save_dir: directory.path().to_path_buf(),
                duration: Duration::from_secs(30),
                max_duration: Duration::from_secs(300),
                extend_mode: "fixed".to_string(),
                width: 2,
                height: 2,
                fps: 1.0,
            };
            let frame = TriggerFrame {
                bytes: Bytes::from_static(&[0; 12]),
                width: 2,
                height: 2,
            };

            recorder
                .trigger(request("stop"), frame.bytes.clone())
                .await
                .unwrap();
            state.stop_source("stop").await.unwrap();
            assert!(!state.recorder_status().await.contains_key("stop"));

            recorder
                .trigger(request("delete"), frame.bytes.clone())
                .await
                .unwrap();
            state.delete_source("delete").await.unwrap();
            assert!(!state.recorder_status().await.contains_key("delete"));

            for source_id in ["shutdown-a", "shutdown-b"] {
                recorder
                    .trigger(request(source_id), frame.bytes.clone())
                    .await
                    .unwrap();
            }
            assert_eq!(state.recorder_status().await.len(), 2);
            state.shutdown().await;
            assert!(state.recorder_status().await.is_empty());
        });
    }
}
