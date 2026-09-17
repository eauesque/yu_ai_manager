use std::collections::{HashMap, VecDeque};
use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};

const DEFAULT_TIMEOUT: f64 = 300.0;
const MAX_HISTORY: usize = 100;

pub struct ApprovalRequest {
    pub request_id: String,
    pub session_id: String,
    pub tool_name: String,
    pub params: Value,
    pub created_at: f64,
    pub timeout: f64,
}

struct HistoryEntry {
    request_id: String,
    session_id: String,
    tool_name: String,
    decision: String,
    created_at: f64,
    decided_at: f64,
    wait_seconds: f64,
}

#[derive(Default)]
pub struct ApprovalGate {
    pub pending: HashMap<String, ApprovalRequest>,
    history: VecDeque<HistoryEntry>,
}

impl ApprovalGate {
    pub fn status(&mut self) -> Value {
        let pending = self.get_pending();
        let count = pending.len();
        let history = self.get_history(10);
        json!({ "pending_count": count, "pending": pending, "recent_history": history })
    }

    pub fn get_pending(&mut self) -> Vec<Value> {
        let now = unix_now();
        let expired: Vec<String> = self
            .pending
            .iter()
            .filter(|(_, r)| now - r.created_at > r.timeout)
            .map(|(id, _)| id.clone())
            .collect();
        for id in &expired {
            if let Some(req) = self.pending.remove(id) {
                self.push_history(&req, "timeout");
            }
        }
        self.pending
            .values()
            .map(|r| {
                let elapsed = now - r.created_at;
                json!({
                    "request_id": r.request_id,
                    "session_id": r.session_id,
                    "tool_name": r.tool_name,
                    "params": r.params,
                    "created_at": r.created_at,
                    "remaining_seconds": (r.timeout - elapsed).max(0.0),
                })
            })
            .collect()
    }

    pub fn get_history(&self, limit: usize) -> Vec<Value> {
        self.history
            .iter()
            .rev()
            .take(limit)
            .map(|e| {
                json!({
                    "request_id": e.request_id,
                    "session_id": e.session_id,
                    "tool_name": e.tool_name,
                    "decision": e.decision,
                    "created_at": e.created_at,
                    "decided_at": e.decided_at,
                    "wait_seconds": e.wait_seconds,
                })
            })
            .collect()
    }

    pub fn respond(&mut self, request_id: &str, decision: &str) -> bool {
        if !matches!(decision, "allow" | "deny" | "always_allow") {
            return false;
        }
        match self.pending.remove(request_id) {
            Some(req) => {
                self.push_history(&req, decision);
                true
            }
            None => false,
        }
    }

    pub fn create_request(
        &mut self,
        session_id: String,
        tool_name: String,
        params: Value,
        timeout: Option<f64>,
    ) -> String {
        let request_id = uuid::Uuid::new_v4().simple().to_string()[..12].to_string();
        self.pending.insert(
            request_id.clone(),
            ApprovalRequest {
                request_id: request_id.clone(),
                session_id,
                tool_name,
                params,
                created_at: unix_now(),
                timeout: timeout.unwrap_or(DEFAULT_TIMEOUT),
            },
        );
        request_id
    }

    fn push_history(&mut self, req: &ApprovalRequest, decision: &str) {
        let decided_at = unix_now();
        self.history.push_back(HistoryEntry {
            request_id: req.request_id.clone(),
            session_id: req.session_id.clone(),
            tool_name: req.tool_name.clone(),
            decision: decision.to_string(),
            created_at: req.created_at,
            decided_at,
            wait_seconds: ((decided_at - req.created_at) * 10.0).round() / 10.0,
        });
        if self.history.len() > MAX_HISTORY {
            self.history.pop_front();
        }
    }
}

fn unix_now() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}
