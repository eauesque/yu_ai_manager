use std::fs;
use std::path::{Path, PathBuf};
use tauri::Manager;

#[derive(Clone, Debug, Default, serde::Serialize, serde::Deserialize)]
pub struct EditorConfig {
    #[serde(default)]
    pub path: String,
}

pub fn editor_config_path() -> Option<PathBuf> {
    crate::app_dirs::config_dir().map(|d| d.join("editor_config.json"))
}

pub fn load_editor_config() -> EditorConfig {
    let Some(cfg_path) = editor_config_path() else {
        return EditorConfig::default();
    };
    fs::read_to_string(&cfg_path)
        .ok()
        .and_then(|content| serde_json::from_str::<EditorConfig>(&content).ok())
        .unwrap_or_default()
}

pub fn save_editor_config(cfg: &EditorConfig) -> Result<(), String> {
    let Some(cfg_path) = editor_config_path() else {
        return Err("editor config directory unavailable".into());
    };
    if let Some(parent) = cfg_path.parent() {
        fs::create_dir_all(parent).map_err(|e| format!("mkdir failed: {}", e))?;
    }
    let serialized =
        serde_json::to_string_pretty(cfg).map_err(|e| format!("serialize failed: {}", e))?;
    fs::write(&cfg_path, serialized).map_err(|e| format!("write failed: {}", e))?;
    Ok(())
}

#[tauri::command]
pub async fn get_external_editor_config() -> Result<EditorConfig, String> {
    Ok(load_editor_config())
}

#[tauri::command]
pub async fn set_external_editor_config(
    app: tauri::AppHandle,
    token: String,
    path: String,
) -> Result<EditorConfig, String> {
    let expected = app.state::<crate::flask::RestartToken>();
    if token != expected.0 {
        return Err("Invalid IPC token".into());
    }
    let trimmed = path.trim().to_string();
    if !trimmed.is_empty() && !Path::new(&trimmed).exists() {
        return Err(format!("editor path does not exist: {}", trimmed));
    }
    let cfg = EditorConfig { path: trimmed };
    save_editor_config(&cfg)?;
    Ok(cfg)
}
