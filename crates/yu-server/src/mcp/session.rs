use std::collections::HashMap;
use std::sync::{Arc, Mutex};

use axum::http::StatusCode;
use tokio::sync::mpsc::{self, Receiver, Sender};

struct McpSessionEntry {
    owner_ip: String,
    tx: Sender<Option<serde_json::Value>>,
    /// Stable Scope Fence identity self-declared via the `agent_scope_bind`
    /// MCP tool (see `mcp::dispatch`). `None` until the connection binds;
    /// enforcement falls back to the raw (volatile) session_id in that case,
    /// which resolves to the default scope preset since no row exists for
    /// it under normal operation.
    bound_scope_id: Option<String>,
}

#[derive(Default)]
struct McpSessionState {
    sessions: HashMap<String, McpSessionEntry>,
    per_ip: HashMap<String, u32>,
}

pub struct McpSessionStore {
    inner: Mutex<McpSessionState>,
    pub max_sessions: usize,
    pub max_per_ip: usize,
    pub queue_depth: usize,
}

impl McpSessionStore {
    pub fn new(max_sessions: usize, max_per_ip: usize, queue_depth: usize) -> Self {
        Self {
            inner: Mutex::new(McpSessionState::default()),
            max_sessions,
            max_per_ip,
            queue_depth,
        }
    }

    /// Register a new session. Returns the mpsc Receiver for the SSE stream.
    /// Returns 429 if global or per-IP limit exceeded.
    pub fn try_register(
        &self,
        session_id: &str,
        owner_ip: &str,
    ) -> Result<Receiver<Option<serde_json::Value>>, StatusCode> {
        let mut st = self.inner.lock().unwrap();
        if st.sessions.len() >= self.max_sessions {
            return Err(StatusCode::TOO_MANY_REQUESTS);
        }
        let per_ip_count = st.per_ip.get(owner_ip).copied().unwrap_or(0) as usize;
        if per_ip_count >= self.max_per_ip {
            return Err(StatusCode::TOO_MANY_REQUESTS);
        }
        let (tx, rx) = mpsc::channel(self.queue_depth);
        st.sessions.insert(
            session_id.to_string(),
            McpSessionEntry {
                owner_ip: owner_ip.to_string(),
                tx,
                bound_scope_id: None,
            },
        );
        *st.per_ip.entry(owner_ip.to_string()).or_insert(0) += 1;
        Ok(rx)
    }

    pub fn get_owner_ip(&self, session_id: &str) -> Option<String> {
        let st = self.inner.lock().unwrap();
        st.sessions.get(session_id).map(|e| e.owner_ip.clone())
    }

    /// Records the Scope Fence identity self-declared by the connection via
    /// `agent_scope_bind`. No-op if the session is no longer registered
    /// (e.g. disconnected between the tool call and this write).
    pub fn set_bound_scope_id(&self, session_id: &str, agent_id: String) {
        let mut st = self.inner.lock().unwrap();
        if let Some(entry) = st.sessions.get_mut(session_id) {
            entry.bound_scope_id = Some(agent_id);
        }
    }

    /// Returns the bound Scope Fence identity for `session_id`, if any.
    pub fn bound_scope_id(&self, session_id: &str) -> Option<String> {
        let st = self.inner.lock().unwrap();
        st.sessions
            .get(session_id)
            .and_then(|e| e.bound_scope_id.clone())
    }

    pub fn send_to(&self, session_id: &str, msg: serde_json::Value) -> Result<(), TrySendKind> {
        let st = self.inner.lock().unwrap();
        let Some(entry) = st.sessions.get(session_id) else {
            return Err(TrySendKind::Disconnected);
        };
        match entry.tx.try_send(Some(msg)) {
            Ok(()) => Ok(()),
            Err(tokio::sync::mpsc::error::TrySendError::Full(_)) => Err(TrySendKind::Full),
            Err(tokio::sync::mpsc::error::TrySendError::Closed(_)) => {
                Err(TrySendKind::Disconnected)
            }
        }
    }

    pub fn remove(&self, session_id: &str, owner_ip: &str) {
        let mut st = self.inner.lock().unwrap();
        if st.sessions.remove(session_id).is_some() {
            let count = st.per_ip.entry(owner_ip.to_string()).or_insert(0);
            if *count <= 1 {
                st.per_ip.remove(owner_ip);
            } else {
                *count -= 1;
            }
        }
    }

    pub fn close_session(&self, session_id: &str) {
        let st = self.inner.lock().unwrap();
        if let Some(entry) = st.sessions.get(session_id) {
            let _ = entry.tx.try_send(None);
        }
    }

    pub fn session_count(&self) -> usize {
        self.inner.lock().unwrap().sessions.len()
    }
}

pub enum TrySendKind {
    Full,
    Disconnected,
}

/// Dropped when the SSE stream ends — cleans up the session automatically.
pub struct McpSessionGuard {
    pub store: Arc<McpSessionStore>,
    pub session_id: String,
    pub owner_ip: String,
}

impl Drop for McpSessionGuard {
    fn drop(&mut self) {
        self.store.remove(&self.session_id, &self.owner_ip);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn store() -> McpSessionStore {
        McpSessionStore::new(1000, 20, 256)
    }

    #[test]
    fn register_and_remove_updates_counters() {
        let s = store();
        let _rx = s.try_register("s1", "1.2.3.4").unwrap();
        assert_eq!(s.session_count(), 1);
        s.remove("s1", "1.2.3.4");
        assert_eq!(s.session_count(), 0);
    }

    #[test]
    fn global_limit_returns_429() {
        let s = McpSessionStore::new(1, 20, 256);
        let _rx = s.try_register("s1", "1.2.3.4").unwrap();
        let err = s.try_register("s2", "1.2.3.5").unwrap_err();
        assert_eq!(err, StatusCode::TOO_MANY_REQUESTS);
    }

    #[test]
    fn per_ip_limit_returns_429() {
        let s = McpSessionStore::new(1000, 1, 256);
        let _rx = s.try_register("s1", "1.2.3.4").unwrap();
        let err = s.try_register("s2", "1.2.3.4").unwrap_err();
        assert_eq!(err, StatusCode::TOO_MANY_REQUESTS);
    }

    #[test]
    fn remove_is_idempotent() {
        let s = store();
        let _rx = s.try_register("s1", "1.2.3.4").unwrap();
        s.remove("s1", "1.2.3.4");
        s.remove("s1", "1.2.3.4");
        assert_eq!(s.session_count(), 0);
    }

    #[test]
    fn get_owner_ip_returns_none_for_unknown() {
        let s = store();
        assert!(s.get_owner_ip("nonexistent").is_none());
    }

    #[test]
    fn bound_scope_id_round_trips_and_defaults_to_none() {
        let s = store();
        let _rx = s.try_register("s1", "1.2.3.4").unwrap();
        assert!(s.bound_scope_id("s1").is_none());
        s.set_bound_scope_id("s1", "agent-42".to_string());
        assert_eq!(s.bound_scope_id("s1"), Some("agent-42".to_string()));
    }

    #[test]
    fn set_bound_scope_id_on_unknown_session_is_noop() {
        let s = store();
        s.set_bound_scope_id("nonexistent", "agent-42".to_string());
        assert!(s.bound_scope_id("nonexistent").is_none());
    }
}
