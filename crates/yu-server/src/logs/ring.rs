use std::collections::{HashMap, VecDeque};
use std::net::IpAddr;
use std::sync::{
    atomic::{AtomicU64, Ordering},
    Mutex, RwLock,
};

use serde::{Deserialize, Serialize};
use tokio::sync::broadcast;

use super::scrub::{scrub_secrets, scrub_value};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct LogEntry {
    pub seq: u64,
    pub timestamp: f64,
    pub level: String,
    pub target: String,
    pub message: String,
    #[serde(skip_serializing_if = "Option::is_none")]
    pub fields: Option<serde_json::Map<String, serde_json::Value>>,
}

pub struct PartialEntry {
    pub level: String,
    pub target: String,
    pub message: String,
    pub fields: Option<serde_json::Map<String, serde_json::Value>>,
}

pub const MAX_LOG_SSE_PER_IP: usize = 3;
const BROADCAST_CAPACITY: usize = 512;

pub struct LogRingBuffer {
    entries: RwLock<VecDeque<LogEntry>>,
    next_seq: AtomicU64,
    capacity: usize,
    pub(super) notify: broadcast::Sender<LogEntry>,
    connections: Mutex<HashMap<IpAddr, usize>>,
}

fn unix_now() -> f64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs_f64()
}

pub(crate) fn level_rank(l: &str) -> u8 {
    // `"TRACE" => 0` and `_ => 0` coincide today. Merging them means deleting
    // the known level from the table, which is the one place a reader looks to
    // see which levels exist.
    #[allow(
        clippy::match_same_arms,
        reason = "the explicit arm lists a known level"
    )]
    match l {
        "TRACE" => 0,
        "DEBUG" => 1,
        "INFO" => 2,
        "WARN" => 3,
        "ERROR" => 4,
        _ => 0,
    }
}

impl LogRingBuffer {
    pub fn new(capacity: usize) -> Self {
        let (notify, _) = broadcast::channel(BROADCAST_CAPACITY);
        Self {
            entries: RwLock::new(VecDeque::with_capacity(capacity)),
            next_seq: AtomicU64::new(0),
            capacity,
            notify,
            connections: Mutex::new(HashMap::new()),
        }
    }

    pub fn push(&self, partial: PartialEntry) {
        let seq = self.next_seq.fetch_add(1, Ordering::Relaxed);
        // Scrub on the way in, not on the way out. Authorization decides who may
        // read this buffer; it does not decide whether a PIN belonged in it. And
        // /fleet/logs/stream hands these lines to a *remote* peer, so a reader
        // that forgets to scrub is a reader on someone else's machine.
        let mut fields = partial.fields;
        if let Some(map) = fields.as_mut() {
            for (key, value) in map.iter_mut() {
                scrub_value(key, value);
            }
        }
        let entry = LogEntry {
            seq,
            timestamp: unix_now(),
            level: partial.level,
            target: partial.target,
            message: scrub_secrets(&partial.message),
            fields,
        };
        {
            let mut ring = self.entries.write().unwrap();
            if ring.len() >= self.capacity {
                ring.pop_front();
            }
            ring.push_back(entry.clone());
        }
        let _ = self.notify.send(entry);
    }

    /// Return entries in ascending seq order (oldest first).
    pub fn recent(
        &self,
        limit: usize,
        min_level: Option<&str>,
        after_seq: Option<u64>,
    ) -> Vec<LogEntry> {
        let ring = self.entries.read().unwrap();
        let min_rank = min_level
            .map(|l| level_rank(&l.to_ascii_uppercase()))
            .unwrap_or(0);
        let mut out: Vec<LogEntry> = ring
            .iter()
            .filter(|e| after_seq.is_none_or(|s| e.seq > s) && level_rank(&e.level) >= min_rank)
            .rev()
            .take(limit)
            .cloned()
            .collect();
        out.reverse();
        out
    }

    pub fn subscribe(&self) -> broadcast::Receiver<LogEntry> {
        self.notify.subscribe()
    }

    pub fn register_connection(&self, ip: IpAddr) -> bool {
        let mut guard = self.connections.lock().unwrap();
        let count = guard.entry(ip).or_insert(0);
        if *count >= MAX_LOG_SSE_PER_IP {
            return false;
        }
        *count += 1;
        true
    }

    pub fn unregister_connection(&self, ip: IpAddr) {
        let mut guard = self.connections.lock().unwrap();
        if let Some(count) = guard.get_mut(&ip) {
            *count = count.saturating_sub(1);
            if *count == 0 {
                guard.remove(&ip);
            }
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn partial(
        message: &str,
        fields: Option<serde_json::Map<String, serde_json::Value>>,
    ) -> PartialEntry {
        PartialEntry {
            level: "INFO".into(),
            target: "t".into(),
            message: message.into(),
            fields,
        }
    }

    /// A correct scrubber nobody calls protects nothing: pin the seam, not the
    /// predicate. This fails if `push` stops scrubbing, even while
    /// `scrub::tests` stay green.
    #[test]
    fn push_scrubs_the_message_before_it_can_be_read() {
        let ring = LogRingBuffer::new(4);
        ring.push(partial(
            "peer pull failed: http://p/api/pull?token=abc123DEF",
            None,
        ));
        let stored = &ring.recent(4, None, None)[0].message;
        assert!(!stored.contains("abc123DEF"), "{stored}");
        assert!(stored.contains("***"), "{stored}");
    }

    /// A tracing call site that records `token = %tok` puts the secret in the
    /// fields and never in the message, so scrubbing the message alone misses
    /// every one of them.
    #[test]
    fn push_scrubs_structured_fields_too() {
        let mut fields = serde_json::Map::new();
        fields.insert(
            "token".into(),
            serde_json::Value::String("abc123DEF".into()),
        );
        fields.insert("peer".into(), serde_json::Value::String("nas-01".into()));
        let ring = LogRingBuffer::new(4);
        ring.push(partial("peer pull failed", Some(fields)));

        let stored = ring.recent(4, None, None).remove(0);
        let got = stored.fields.expect("fields survive the push");
        assert_eq!(got["token"], serde_json::Value::String("***".into()));
        assert_eq!(got["peer"], serde_json::Value::String("nas-01".into()));
    }
}
