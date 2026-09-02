use std::io;
use std::path::{Path, PathBuf};

use serde::{Deserialize, Serialize};

#[derive(Clone)]
pub struct WorkerIpcPaths {
    pub root: PathBuf,
    pub pid_file: PathBuf,
    pub progress_file: PathBuf,
}

fn default_true() -> bool {
    true
}

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct ProgressData {
    #[serde(default = "default_true")]
    pub running: bool,
    pub phase: Option<String>,
    pub message: Option<String>,
    #[serde(default)]
    pub current: u64,
    #[serde(default)]
    pub total: u64,
    #[serde(default)]
    pub percent: f32,
    pub detail: Option<String>,
    pub error: Option<String>,
    #[serde(default)]
    pub deleted: u64,
    #[serde(default)]
    pub elapsed_seconds: f64,
    #[serde(default)]
    pub added_ids: Vec<i64>,
    #[serde(default)]
    pub updated_ids: Vec<i64>,
    #[serde(default)]
    pub deleted_ids: Vec<i64>,
}

fn resolve_ipc_dir(name: &str) -> PathBuf {
    if let Ok(ov) = std::env::var("YU_SCAN_IPC_DIR") {
        if !ov.is_empty() {
            return PathBuf::from(ov);
        }
    }

    if let Ok(xdg) = std::env::var("XDG_RUNTIME_DIR") {
        let p = PathBuf::from(&xdg);
        if !xdg.is_empty() && p.is_dir() {
            return p.join(name);
        }
    }

    #[cfg(unix)]
    {
        let uid = get_uid();
        std::env::temp_dir().join(format!("{}-{}", name, uid))
    }

    #[cfg(not(unix))]
    {
        std::env::temp_dir().join(name)
    }
}

#[cfg(unix)]
fn get_uid() -> u32 {
    std::fs::read_to_string("/proc/self/status")
        .ok()
        .and_then(|s| {
            s.lines()
                .find(|l| l.starts_with("Uid:"))
                .and_then(|l| l.split_whitespace().nth(1))
                .and_then(|uid| uid.parse().ok())
        })
        .unwrap_or(0)
}

pub fn make_worker_ipc_paths(name: &str) -> WorkerIpcPaths {
    let root = resolve_ipc_dir(name);
    WorkerIpcPaths {
        pid_file: root.join("worker.pid"),
        progress_file: root.join("progress.json"),
        root,
    }
}

pub fn write_pid(paths: &WorkerIpcPaths, pid: u32) -> io::Result<()> {
    std::fs::create_dir_all(&paths.root)?;
    std::fs::write(&paths.pid_file, pid.to_string())
}

pub fn read_pid(paths: &WorkerIpcPaths) -> Option<u32> {
    std::fs::read_to_string(&paths.pid_file)
        .ok()
        .and_then(|s| s.trim().parse().ok())
}

pub fn clear_pid(paths: &WorkerIpcPaths) {
    let _ = std::fs::remove_file(&paths.pid_file);
}

pub fn write_progress(paths: &WorkerIpcPaths, data: &serde_json::Value) -> io::Result<()> {
    std::fs::create_dir_all(&paths.root)?;
    let tmp = tempfile::NamedTempFile::new_in(&paths.root)?;
    serde_json::to_writer(tmp.as_file(), data).map_err(io::Error::other)?;
    tmp.persist(&paths.progress_file).map_err(|e| e.error)?;
    Ok(())
}

pub fn read_progress(paths: &WorkerIpcPaths) -> Option<ProgressData> {
    let bytes = std::fs::read(&paths.progress_file).ok()?;
    serde_json::from_slice(&bytes).ok()
}

pub fn clear_progress(paths: &WorkerIpcPaths) {
    let _ = std::fs::remove_file(&paths.progress_file);
}

pub fn is_process_alive(pid: u32) -> bool {
    #[cfg(unix)]
    {
        let ret = unsafe { libc::kill(pid as libc::pid_t, 0) };
        if ret == 0 {
            return true;
        }
        let err = std::io::Error::last_os_error();
        err.raw_os_error() == Some(libc::EPERM)
    }

    #[cfg(windows)]
    {
        use std::process::Command;
        Command::new("tasklist")
            .args(["/FI", &format!("PID eq {}", pid), "/NH"])
            .output()
            .map(|o| {
                let out = String::from_utf8_lossy(&o.stdout);
                out.contains(&pid.to_string())
            })
            .unwrap_or(false)
    }

    #[cfg(not(any(unix, windows)))]
    {
        false
    }
}

pub fn is_worker_running(paths: &WorkerIpcPaths) -> bool {
    match read_pid(paths) {
        None => false,
        Some(pid) if is_process_alive(pid) => true,
        Some(_) => {
            clear_pid(paths);
            clear_progress(paths);
            false
        }
    }
}

pub fn clear_scan_state(project_root: &Path) {
    let _ = std::fs::remove_file(project_root.join("core").join("scan_state.json"));
}

pub fn signal_stop(paths: &WorkerIpcPaths) -> bool {
    let Some(pid) = read_pid(paths) else {
        return false;
    };
    if !is_process_alive(pid) {
        clear_pid(paths);
        clear_progress(paths);
        return false;
    }

    #[cfg(unix)]
    {
        let ret = unsafe { libc::kill(pid as libc::pid_t, libc::SIGTERM) };
        if ret != 0 {
            let e = std::io::Error::last_os_error();
            tracing::warn!("signal_stop: kill({pid}) failed: {e}");
        }
        ret == 0
    }

    #[cfg(windows)]
    {
        let status = std::process::Command::new("taskkill")
            .args(["/F", "/PID", &pid.to_string()])
            .status();
        status.map(|s| s.success()).unwrap_or(false)
    }

    #[cfg(not(any(unix, windows)))]
    {
        false
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use tempfile::TempDir;

    fn tmp_paths(dir: &TempDir) -> WorkerIpcPaths {
        let root = dir.path().to_path_buf();
        WorkerIpcPaths {
            pid_file: root.join("worker.pid"),
            progress_file: root.join("progress.json"),
            root,
        }
    }

    #[test]
    fn test_resolve_ipc_dir_override() {
        let dir = tempfile::tempdir().unwrap();
        std::env::set_var("YU_SCAN_IPC_DIR", dir.path().to_str().unwrap());
        let result = resolve_ipc_dir("yu-scan");
        std::env::remove_var("YU_SCAN_IPC_DIR");
        assert_eq!(result, dir.path());
    }

    #[test]
    fn test_read_write_pid() {
        let dir = tempfile::tempdir().unwrap();
        let paths = tmp_paths(&dir);
        write_pid(&paths, 12345).unwrap();
        assert_eq!(read_pid(&paths), Some(12345));
        clear_pid(&paths);
        assert_eq!(read_pid(&paths), None);
    }

    #[test]
    fn test_read_progress_missing_running_field() {
        let dir = tempfile::tempdir().unwrap();
        let paths = tmp_paths(&dir);
        let data = serde_json::json!({"phase": "scanning", "current": 5, "total": 10});
        write_progress(&paths, &data).unwrap();
        let p = read_progress(&paths).unwrap();
        assert!(p.running, "running should default true when absent");
        assert_eq!(p.current, 5);
    }

    #[test]
    fn test_is_worker_running_stale_pid_cleanup() {
        let dir = tempfile::tempdir().unwrap();
        let paths = tmp_paths(&dir);
        write_pid(&paths, i32::MAX as u32).unwrap();
        let data = serde_json::json!({"running": true});
        write_progress(&paths, &data).unwrap();
        assert!(!is_worker_running(&paths));
        assert!(!paths.pid_file.exists());
        assert!(!paths.progress_file.exists());
    }

    #[test]
    fn test_is_process_alive_current() {
        let pid = std::process::id();
        assert!(is_process_alive(pid));
    }
}
