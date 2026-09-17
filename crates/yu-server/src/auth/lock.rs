use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::Mutex;
use std::time::{Instant, SystemTime, UNIX_EPOCH};

pub struct QuickLock {
    locked: AtomicBool,
    locked_at: Mutex<Option<(Instant, SystemTime)>>,
}

impl QuickLock {
    pub fn new() -> Self {
        Self {
            locked: AtomicBool::new(false),
            locked_at: Mutex::new(None),
        }
    }

    pub fn is_locked(&self) -> bool {
        self.locked.load(Ordering::Acquire)
    }

    pub fn activate(&self) {
        *self.locked_at.lock().unwrap() = Some((Instant::now(), SystemTime::now()));
        self.locked.store(true, Ordering::Release);
    }

    pub fn deactivate(&self) {
        self.locked.store(false, Ordering::Release);
        *self.locked_at.lock().unwrap() = None;
    }

    /// Returns (locked, locked_at_unix_secs, locked_duration_secs) — Python互換形式。
    pub fn info(&self) -> (bool, Option<f64>, i64) {
        let locked = self.is_locked();
        let guard = self.locked_at.lock().unwrap();
        match *guard {
            None => (locked, None, 0),
            Some((inst, sys)) => {
                let locked_at = sys
                    .duration_since(UNIX_EPOCH)
                    .unwrap_or_default()
                    .as_secs_f64();
                let locked_duration = inst.elapsed().as_secs() as i64;
                (locked, Some(locked_at), locked_duration)
            }
        }
    }
}

impl Default for QuickLock {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn initial_state_unlocked() {
        let lock = QuickLock::new();
        assert!(!lock.is_locked());
    }

    #[test]
    fn activate_sets_locked() {
        let lock = QuickLock::new();
        lock.activate();
        assert!(lock.is_locked());
    }

    #[test]
    fn deactivate_clears_locked() {
        let lock = QuickLock::new();
        lock.activate();
        lock.deactivate();
        assert!(!lock.is_locked());
    }

    #[test]
    fn info_has_locked_at_when_locked() {
        let lock = QuickLock::new();
        lock.activate();
        let (locked, locked_at, locked_duration) = lock.info();
        assert!(locked);
        assert!(locked_at.is_some());
        assert!(locked_at.unwrap() > 0.0);
        assert!(locked_duration >= 0);
    }

    #[test]
    fn info_no_locked_at_when_unlocked() {
        let lock = QuickLock::new();
        let (locked, locked_at, locked_duration) = lock.info();
        assert!(!locked);
        assert!(locked_at.is_none());
        assert_eq!(locked_duration, 0);
    }
}
