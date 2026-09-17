use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;

const MAX_ATTEMPTS: u32 = 5;
const LOCKOUT_SECS: u64 = 60;

struct Entry {
    count: u32,
    first: Instant,
}

pub struct PinRateLimiter {
    map: Mutex<HashMap<String, Entry>>,
}

impl PinRateLimiter {
    pub fn new() -> Self {
        Self {
            map: Mutex::new(HashMap::new()),
        }
    }

    /// Records a failed attempt. Returns true if the IP is now locked out.
    pub fn record_failure(&self, ip: &str) -> bool {
        let mut map = self.map.lock().unwrap();
        let now = Instant::now();
        let entry = map.entry(ip.to_string()).or_insert(Entry {
            count: 0,
            first: now,
        });
        if entry.first.elapsed().as_secs() >= LOCKOUT_SECS {
            entry.count = 0;
            entry.first = now;
        }
        entry.count += 1;
        entry.count > MAX_ATTEMPTS
    }

    /// Checks lockout status without recording a failure.
    pub fn is_locked_out(&self, ip: &str) -> bool {
        let map = self.map.lock().unwrap();
        let Some(entry) = map.get(ip) else {
            return false;
        };
        if entry.first.elapsed().as_secs() >= LOCKOUT_SECS {
            return false;
        }
        entry.count >= MAX_ATTEMPTS
    }

    /// Clears the record for an IP (call on successful auth).
    pub fn reset(&self, ip: &str) {
        self.map.lock().unwrap().remove(ip);
    }
}

impl Default for PinRateLimiter {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn not_locked_initially() {
        let rl = PinRateLimiter::new();
        assert!(!rl.is_locked_out("1.2.3.4"));
    }

    #[test]
    fn locked_after_max_failures() {
        let rl = PinRateLimiter::new();
        for _ in 0..MAX_ATTEMPTS {
            rl.record_failure("1.2.3.4");
        }
        assert!(rl.is_locked_out("1.2.3.4"));
    }

    #[test]
    fn reset_clears_lockout() {
        let rl = PinRateLimiter::new();
        for _ in 0..MAX_ATTEMPTS {
            rl.record_failure("1.2.3.4");
        }
        rl.reset("1.2.3.4");
        assert!(!rl.is_locked_out("1.2.3.4"));
    }

    #[test]
    fn different_ips_are_independent() {
        let rl = PinRateLimiter::new();
        for _ in 0..MAX_ATTEMPTS {
            rl.record_failure("1.2.3.4");
        }
        assert!(!rl.is_locked_out("5.6.7.8"));
    }
}
