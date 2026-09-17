use super::config::{load_editor_config, save_editor_config};
use super::monitor::{file_mtime, spawn_editor_monitor, MonitoredEditorFiles};
use std::path::{Path, PathBuf};
use tauri::Manager;

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[tauri::command]
pub async fn open_in_external_editor(
    app: tauri::AppHandle,
    token: String,
    file_path: String,
) -> Result<String, String> {
    let expected = app.state::<crate::flask::RestartToken>();
    if token != expected.0 {
        return Err("Invalid IPC token".into());
    }

    let target = PathBuf::from(&file_path);
    if !target.exists() || !target.is_file() {
        return Err(format!("file not found: {}", file_path));
    }

    let mut cfg = load_editor_config();
    if cfg.path.is_empty() || !Path::new(&cfg.path).exists() {
        let picked = rfd::FileDialog::new()
            .set_title("Pick external image editor")
            .pick_file()
            .ok_or_else(|| "No editor selected".to_string())?;
        cfg.path = picked.to_string_lossy().into_owned();
        save_editor_config(&cfg)?;
    }

    let monitor = app.state::<MonitoredEditorFiles>();
    if !monitor.try_acquire(&target) {
        return Err("file is already being monitored by another editor session".into());
    }

    let initial_mtime = file_mtime(&target);

    let mut command = std::process::Command::new(&cfg.path);
    command.arg(&target);
    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        command.creation_flags(CREATE_NO_WINDOW);
    }
    if let Err(e) = command.spawn() {
        monitor.release(&target);
        return Err(format!("failed to spawn editor: {}", e));
    }

    spawn_editor_monitor(app.clone(), target, initial_mtime);
    Ok(format!("launched {} with {}", cfg.path, file_path))
}
