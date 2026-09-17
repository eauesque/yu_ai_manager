//! Scan queue -- holds requests that arrive while a scan is already running.
//!
//! A port of Python's `core/scan_core/scan_queue.py`: a FIFO persisted to
//! `data/scan_queue.json` so queued work survives a restart, guarded by a
//! mutex because both HTTP handlers and the scan-completion consumer touch it.
//!
//! The JSON shape is shared with Python on purpose -- the two implementations
//! read the same file, so a library scanned under one and restarted under the
//! other must not lose its queue.

use std::path::{Path, PathBuf};
use std::sync::{Mutex, MutexGuard, PoisonError};
use std::time::{SystemTime, UNIX_EPOCH};

use serde::{Deserialize, Serialize};
use tracing::{info, warn};

/// Sentinel `root` marking a queued "scan every enabled root" request.
pub const SCAN_ALL_ROOT: &str = "__all__";

const MAX_QUEUE_SIZE: usize = 50;

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ScanQueueItem {
    pub queue_id: String,
    pub root: String,
    pub recursive: bool,
    pub force: bool,
    pub scan_zips: bool,
    /// Unix seconds, fractional -- Python writes `time.time()` here.
    pub queued_at: f64,
    pub label: String,
    /// "manual" | "scan-all" | "api"
    pub source: String,
}

#[derive(Debug, PartialEq, Eq)]
pub enum QueueError {
    /// The same root is already queued. Python raises ValueError for this.
    Duplicate,
    Full,
}

impl std::fmt::Display for QueueError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            QueueError::Duplicate => write!(f, "root is already in queue"),
            QueueError::Full => write!(f, "Queue is full"),
        }
    }
}

pub struct ScanQueue {
    path: PathBuf,
    items: Mutex<Vec<ScanQueueItem>>,
}

/// A panic while the queue lock was held must not turn every later queue
/// operation into a panic; the guarded value is a plain Vec with no invariant
/// a half-finished write could break. Same reasoning as `ScanManager`.
fn lock_recover<T>(mutex: &Mutex<T>) -> MutexGuard<'_, T> {
    mutex.lock().unwrap_or_else(PoisonError::into_inner)
}

fn now_ts() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

impl ScanQueue {
    /// Load the queue from `<project_root>/data/scan_queue.json`, the same
    /// path Python uses. A missing or unreadable file yields an empty queue --
    /// Python logs and continues too, since a corrupt queue must not stop the
    /// server from serving.
    pub fn load(project_root: &Path) -> Self {
        let path = project_root.join("data").join("scan_queue.json");
        let items = match std::fs::read_to_string(&path) {
            Ok(text) => match serde_json::from_str::<Vec<ScanQueueItem>>(&text) {
                Ok(items) => {
                    info!("scan_queue: {} items restored", items.len());
                    items
                }
                Err(e) => {
                    warn!("scan_queue load failed: {e}");
                    vec![]
                }
            },
            Err(_) => vec![],
        };
        Self {
            path,
            items: Mutex::new(items),
        }
    }

    fn save(&self, items: &[ScanQueueItem]) {
        let Some(parent) = self.path.parent() else {
            return;
        };
        if let Err(e) = std::fs::create_dir_all(parent) {
            warn!("scan_queue save failed (mkdir): {e}");
            return;
        }
        let Ok(text) = serde_json::to_string_pretty(items) else {
            return;
        };
        // Write-then-rename, as Python does: a crash mid-write must not leave
        // a truncated queue file that the next load discards wholesale.
        let tmp = parent.join(format!(".scan_queue_{}.tmp", std::process::id()));
        if let Err(e) = std::fs::write(&tmp, text) {
            warn!("scan_queue save failed (write): {e}");
            return;
        }
        if let Err(e) = std::fs::rename(&tmp, &self.path) {
            warn!("scan_queue save failed (rename): {e}");
            let _ = std::fs::remove_file(&tmp);
        }
    }

    pub fn enqueue(
        &self,
        root: &str,
        recursive: bool,
        force: bool,
        scan_zips: bool,
        label: &str,
        source: &str,
    ) -> Result<ScanQueueItem, QueueError> {
        let mut items = lock_recover(&self.items);
        if items.iter().any(|i| i.root == root) {
            return Err(QueueError::Duplicate);
        }
        if items.len() >= MAX_QUEUE_SIZE {
            return Err(QueueError::Full);
        }
        let item = ScanQueueItem {
            queue_id: uuid::Uuid::new_v4().simple().to_string()[..12].to_string(),
            root: root.to_string(),
            recursive,
            force,
            scan_zips,
            queued_at: now_ts(),
            label: if label.is_empty() {
                root.to_string()
            } else {
                label.to_string()
            },
            source: source.to_string(),
        };
        items.push(item.clone());
        self.save(&items);
        Ok(item)
    }

    pub fn pop_next(&self) -> Option<ScanQueueItem> {
        let mut items = lock_recover(&self.items);
        if items.is_empty() {
            return None;
        }
        let item = items.remove(0);
        self.save(&items);
        Some(item)
    }

    pub fn remove(&self, queue_id: &str) -> bool {
        let mut items = lock_recover(&self.items);
        let before = items.len();
        items.retain(|i| i.queue_id != queue_id);
        if items.len() < before {
            self.save(&items);
            true
        } else {
            false
        }
    }

    pub fn clear(&self) -> usize {
        let mut items = lock_recover(&self.items);
        let count = items.len();
        if count > 0 {
            items.clear();
            self.save(&items);
        }
        count
    }

    pub fn list(&self) -> Vec<ScanQueueItem> {
        lock_recover(&self.items).clone()
    }

    pub fn size(&self) -> usize {
        lock_recover(&self.items).len()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn fifo_order_duplicate_rejection_and_persistence() {
        let dir = tempfile::TempDir::new().unwrap();
        let q = ScanQueue::load(dir.path());

        let first = q.enqueue("/a", true, false, true, "A", "api").unwrap();
        q.enqueue("/b", true, false, true, "B", "api").unwrap();
        assert_eq!(
            q.enqueue("/a", true, false, true, "A again", "api")
                .unwrap_err(),
            QueueError::Duplicate
        );
        assert_eq!(q.size(), 2);

        // A fresh queue over the same directory must see what was saved.
        let reloaded = ScanQueue::load(dir.path());
        assert_eq!(reloaded.size(), 2);
        let popped = reloaded.pop_next().expect("front item");
        assert_eq!(popped.queue_id, first.queue_id);
        assert_eq!(popped.root, "/a");

        // ...and the pop must have been written through, not just held in RAM.
        assert_eq!(ScanQueue::load(dir.path()).size(), 1);

        assert!(!reloaded.remove("no-such-id"));
        assert_eq!(reloaded.clear(), 1);
        assert_eq!(ScanQueue::load(dir.path()).size(), 0);
    }

    #[test]
    fn queue_is_capped_at_fifty() {
        let dir = tempfile::TempDir::new().unwrap();
        let q = ScanQueue::load(dir.path());
        for i in 0..MAX_QUEUE_SIZE {
            q.enqueue(&format!("/root{i}"), true, false, true, "", "api")
                .unwrap();
        }
        assert_eq!(
            q.enqueue("/one-too-many", true, false, true, "", "api")
                .unwrap_err(),
            QueueError::Full
        );
    }

    /// The label defaults to the root, matching Python's `label or root`.
    #[test]
    fn empty_label_falls_back_to_root() {
        let dir = tempfile::TempDir::new().unwrap();
        let q = ScanQueue::load(dir.path());
        let item = q
            .enqueue("/pictures", true, false, true, "", "api")
            .unwrap();
        assert_eq!(item.label, "/pictures");
    }
}
