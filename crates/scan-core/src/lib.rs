pub mod hash;
pub mod ipc;
pub mod walk;

pub use hash::compute_hash;
pub use ipc::{
    clear_pid, clear_progress, clear_scan_state, is_process_alive, is_worker_running,
    make_worker_ipc_paths, read_pid, read_progress, signal_stop, write_pid, write_progress,
    ProgressData, WorkerIpcPaths,
};
pub use walk::{iter_files, WalkConfig};
