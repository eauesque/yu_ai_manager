use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};
use std::sync::Mutex;
use std::time::{Duration, Instant, SystemTime};
use tauri::{Emitter, Manager};

pub struct MonitoredEditorFiles(pub Mutex<HashSet<PathBuf>>);

impl MonitoredEditorFiles {
    pub fn new() -> Self {
        Self(Mutex::new(HashSet::new()))
    }

    pub fn try_acquire(&self, path: &Path) -> bool {
        match self.0.lock() {
            Ok(mut set) => set.insert(path.to_path_buf()),
            Err(_) => false,
        }
    }

    pub fn release(&self, path: &Path) {
        if let Ok(mut set) = self.0.lock() {
            set.remove(path);
        }
    }
}

#[derive(Clone, serde::Serialize)]
pub struct EditorClosedPayload {
    pub path: String,
    pub changed: bool,
}

pub fn file_mtime(path: &Path) -> SystemTime {
    fs::metadata(path)
        .and_then(|m| m.modified())
        .unwrap_or(SystemTime::UNIX_EPOCH)
}

pub fn spawn_editor_monitor(app: tauri::AppHandle, target: PathBuf, initial_mtime: SystemTime) {
    std::thread::spawn(move || {
        let deadline = Instant::now() + Duration::from_secs(300);
        let mut changed = false;
        while Instant::now() < deadline {
            std::thread::sleep(Duration::from_secs(2));
            let now_mtime = file_mtime(&target);
            if now_mtime != initial_mtime && now_mtime != SystemTime::UNIX_EPOCH {
                changed = true;
                let _ = app.emit(
                    "editor-closed",
                    EditorClosedPayload {
                        path: target.to_string_lossy().into_owned(),
                        changed: true,
                    },
                );
                break;
            }
        }
        if !changed {
            let _ = app.emit(
                "editor-closed",
                EditorClosedPayload {
                    path: target.to_string_lossy().into_owned(),
                    changed: false,
                },
            );
        }
        if let Some(state) = app.try_state::<MonitoredEditorFiles>() {
            state.release(&target);
        }
    });
}
