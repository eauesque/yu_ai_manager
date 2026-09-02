use std::{path::Path, time::Instant};

use async_trait::async_trait;
use axum::response::Response;
use futures_util::stream::{self, BoxStream, StreamExt};
use lan_cowork::routes::lan_cowork_host::{LanCoworkHost, LogEvent, LogLine};
use sqlx::SqlitePool;
use tokio::sync::broadcast::error::RecvError;

use crate::{
    logs::ring::LogEntry, routes::agent_journal::record_action, sse::event::SseEvent,
    state::AppState,
};

/// Per-IP concurrent connection budget for the LAN Cowork fleet log SSE stream.
/// Matches `logs::ring::MAX_LOG_SSE_PER_IP`, core's own log-viewer limit, since
/// no reason emerged to diverge — both guard the same class of resource
/// (a long-lived SSE connection fed by the in-memory log ring).
const MAX_FLEET_LOG_SSE_PER_IP: usize = 3;

impl From<LogEntry> for LogLine {
    fn from(entry: LogEntry) -> Self {
        Self {
            seq: entry.seq,
            timestamp: entry.timestamp,
            level: entry.level,
            target: entry.target,
            message: entry.message,
        }
    }
}

#[cfg(test)]
thread_local! {
    static LOG_OPEN_SEAM_HOOK: std::cell::RefCell<Option<Box<dyn FnOnce(&crate::logs::LogRingBuffer)>>> =
        std::cell::RefCell::new(None);
}

#[cfg(test)]
pub(crate) fn set_log_open_seam_hook(hook: impl FnOnce(&crate::logs::LogRingBuffer) + 'static) {
    LOG_OPEN_SEAM_HOOK.with(|cell| {
        *cell.borrow_mut() = Some(Box::new(hook));
    });
}

#[cfg(test)]
fn run_log_open_seam_hook(ring: &crate::logs::LogRingBuffer) {
    LOG_OPEN_SEAM_HOOK.with(|cell| {
        if let Some(hook) = cell.borrow_mut().take() {
            hook(ring);
        }
    });
}

#[async_trait]
impl LanCoworkHost for AppState {
    fn db(&self) -> &SqlitePool {
        &self.db
    }

    fn db_read(&self) -> &SqlitePool {
        &self.db_read
    }

    fn python_client(&self) -> &reqwest::Client {
        &self.python_client
    }

    fn version(&self) -> &str {
        &self.version
    }

    fn start_time(&self) -> Instant {
        self.start_time
    }

    fn config_json(&self) -> &serde_json::Value {
        &self.config.app_config
    }

    fn config_path(&self) -> &Path {
        &self.config.config_path
    }

    fn project_root(&self) -> &Path {
        &self.config.project_root
    }

    fn python_url(&self) -> &str {
        &self.config.python_url
    }

    fn pin_auth_enabled(&self) -> bool {
        self.config.pin_auth_enabled
    }

    fn safe_mode(&self) -> bool {
        self.config.safe_mode
    }

    fn sse_send(&self, source: &str, kind: &str, timestamp: f64, payload: serde_json::Value) {
        self.sse_hub.send(SseEvent {
            event_type: kind.to_owned(),
            timestamp,
            data: payload,
            source: source.to_owned(),
        });
    }

    fn sse_receiver_count(&self) -> usize {
        self.sse_hub.receiver_count()
    }

    fn render_nav(&self, csp_nonce: &str, active: &str) -> String {
        self.env
            .get_template("_nav.html")
            .and_then(|template| {
                template.render(serde_json::json!({
                    "csp_nonce": csp_nonce,
                    "dist_v": self.dist_v,
                    "active": active,
                }))
            })
            .unwrap_or_default()
    }

    fn log_open(
        &self,
        limit: usize,
        level: Option<&str>,
    ) -> (BoxStream<'static, LogEvent>, Vec<LogLine>) {
        let rx = self.log_ring.subscribe();
        #[cfg(test)]
        run_log_open_seam_hook(&self.log_ring);
        let backlog = self
            .log_ring
            .recent(limit, level, None)
            .into_iter()
            .map(LogLine::from)
            .collect();
        let stream = stream::unfold((rx, false), |(mut rx, closed)| async move {
            if closed {
                return None;
            }
            loop {
                match rx.recv().await {
                    Ok(entry) => return Some((LogEvent::Line(LogLine::from(entry)), (rx, false))),
                    Err(RecvError::Lagged(_)) => continue,
                    Err(RecvError::Closed) => return Some((LogEvent::Closed, (rx, true))),
                }
            }
        })
        .boxed();
        (stream, backlog)
    }

    async fn record_journal_action(
        &self,
        session_id: &str,
        tool_name: &str,
        status: &str,
        duration_ms: i64,
        result_summary: &str,
    ) {
        record_action(
            &self.db,
            session_id,
            tool_name,
            status,
            duration_ms,
            result_summary,
        )
        .await;
    }

    fn register_log_stream_connection(&self, ip: &str) -> bool {
        let mut connections = self.fleet_log_stream_connections.lock().unwrap();
        let count = connections.entry(ip.to_string()).or_insert(0);
        if *count >= MAX_FLEET_LOG_SSE_PER_IP {
            return false;
        }
        *count += 1;
        true
    }

    fn unregister_log_stream_connection(&self, ip: &str) {
        let mut connections = self.fleet_log_stream_connections.lock().unwrap();
        if let Some(count) = connections.get_mut(ip) {
            *count = count.saturating_sub(1);
            if *count == 0 {
                connections.remove(ip);
            }
        }
    }

    async fn require_session(&self, session: Option<&tower_sessions::Session>) -> Option<Response> {
        crate::auth::scope::require_session(self.pin_auth_enabled(), session).await
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::{semantic_test_state_with_root, SharedState};

    fn assert_matches_shared_state(host: &dyn LanCoworkHost, state: &SharedState) {
        assert!(std::ptr::eq(host.db(), &state.db));
        assert!(std::ptr::eq(host.db_read(), &state.db_read));
        assert!(std::ptr::eq(host.python_client(), &state.python_client));
        assert_eq!(host.version(), state.version);
        assert_eq!(host.start_time(), state.start_time);
        assert!(std::ptr::eq(host.config_json(), &state.config.app_config));
        assert_eq!(host.config_path(), state.config.config_path);
        assert_eq!(host.project_root(), state.config.project_root);
        assert_eq!(host.python_url(), state.config.python_url);
        assert_eq!(host.pin_auth_enabled(), state.config.pin_auth_enabled);
        assert_eq!(host.safe_mode(), state.config.safe_mode);
    }

    #[tokio::test]
    async fn shared_state_exposes_the_lan_cowork_host_surface() {
        let root = tempfile::tempdir().unwrap();
        let state = semantic_test_state_with_root(
            true,
            "http://127.0.0.1:8765".to_string(),
            root.path().to_path_buf(),
        )
        .await;

        assert_matches_shared_state(&*state, &state);

        let mut receiver = state.sse_hub.subscribe();
        let payload = serde_json::json!({"peer_id": "test-peer"});
        state.sse_send("lan-cowork", "peer.test", 123.5, payload.clone());
        let event = receiver.recv().await.unwrap();
        assert_eq!(event.source, "lan-cowork");
        assert_eq!(event.event_type, "peer.test");
        assert_eq!(event.timestamp, 123.5);
        assert_eq!(event.data, payload);
    }
}
