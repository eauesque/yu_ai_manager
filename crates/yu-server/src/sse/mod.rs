pub mod emit;
pub mod event;
pub mod info;
pub mod stream;

use std::collections::HashMap;
use std::net::IpAddr;
use std::sync::atomic::{AtomicU64, Ordering};
use std::sync::{Arc, Mutex};
use tokio::sync::broadcast;

pub use event::SseEvent;

pub const BROADCAST_CAPACITY: usize = 4096;
pub const MAX_SSE_PER_IP: usize = 100;
pub const MAX_STREAM_AGE_SECS: u64 = 900;
pub const HEARTBEAT_SECS: u64 = 30;

pub struct SseHub {
    sender: broadcast::Sender<Arc<SseEvent>>,
    connections: Mutex<HashMap<IpAddr, usize>>,
    pub lagged_count: AtomicU64,
}

impl SseHub {
    pub fn new() -> Self {
        let (sender, _) = broadcast::channel(BROADCAST_CAPACITY);
        Self {
            sender,
            connections: Mutex::new(HashMap::new()),
            lagged_count: AtomicU64::new(0),
        }
    }

    pub fn send(&self, event: SseEvent) {
        let _ = self.sender.send(Arc::new(event));
    }

    pub fn subscribe(&self) -> broadcast::Receiver<Arc<SseEvent>> {
        self.sender.subscribe()
    }

    pub fn receiver_count(&self) -> usize {
        self.sender.receiver_count()
    }

    /// Returns true and increments counter if under limit; false if at limit.
    pub fn register_connection(&self, ip: IpAddr) -> bool {
        let mut guard = self.connections.lock().unwrap();
        let count = guard.entry(ip).or_insert(0);
        if *count >= MAX_SSE_PER_IP {
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

    pub fn connection_count(&self, ip: IpAddr) -> usize {
        self.connections
            .lock()
            .unwrap()
            .get(&ip)
            .copied()
            .unwrap_or(0)
    }

    pub fn lagged(&self) -> u64 {
        self.lagged_count.load(Ordering::Relaxed)
    }

    pub fn inc_lagged(&self) {
        self.lagged_count.fetch_add(1, Ordering::Relaxed);
    }
}

impl Default for SseHub {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn ip(s: &str) -> IpAddr {
        s.parse().unwrap()
    }

    #[test]
    fn test_register_up_to_limit() {
        let hub = SseHub::new();
        let client_ip = ip("10.0.0.1");
        for _ in 0..MAX_SSE_PER_IP {
            assert!(hub.register_connection(client_ip));
        }
        // 31st must fail
        assert!(!hub.register_connection(client_ip));
        assert_eq!(hub.connection_count(client_ip), MAX_SSE_PER_IP);
    }

    #[test]
    fn test_unregister_decrements_count() {
        let hub = SseHub::new();
        let client_ip = ip("10.0.0.2");
        hub.register_connection(client_ip);
        hub.register_connection(client_ip);
        assert_eq!(hub.connection_count(client_ip), 2);
        hub.unregister_connection(client_ip);
        assert_eq!(hub.connection_count(client_ip), 1);
        hub.unregister_connection(client_ip);
        assert_eq!(hub.connection_count(client_ip), 0);
    }

    #[test]
    fn test_unregister_cleans_entry() {
        let hub = SseHub::new();
        let client_ip = ip("10.0.0.3");
        hub.register_connection(client_ip);
        hub.unregister_connection(client_ip);
        // Entry is cleaned up — re-registering should succeed
        assert!(hub.register_connection(client_ip));
    }

    #[test]
    fn test_lagged_counter() {
        let hub = SseHub::new();
        assert_eq!(hub.lagged(), 0);
        hub.inc_lagged();
        hub.inc_lagged();
        assert_eq!(hub.lagged(), 2);
    }

    #[test]
    fn test_send_and_subscribe() {
        let hub = SseHub::new();
        let mut rx = hub.subscribe();
        hub.send(SseEvent {
            event_type: "test".into(),
            timestamp: 1.0,
            data: json!({}),
            source: "unit".into(),
        });
        let ev = rx.try_recv().expect("event should be in channel");
        assert_eq!(ev.event_type, "test");
    }

    #[test]
    fn test_different_ips_independent() {
        let hub = SseHub::new();
        let ip1 = ip("192.168.1.1");
        let ip2 = ip("192.168.1.2");
        for _ in 0..MAX_SSE_PER_IP {
            hub.register_connection(ip1);
        }
        // ip1 is full but ip2 should still work
        assert!(!hub.register_connection(ip1));
        assert!(hub.register_connection(ip2));
    }
}
