use crate::external_editor::{
    get_external_editor_config as get_external_editor_config_impl,
    open_in_external_editor as open_in_external_editor_impl,
    set_external_editor_config as set_external_editor_config_impl, MonitoredEditorFiles,
};
use crate::flask::{
    restart_flask_server as restart_flask_server_impl, FlaskProcess, FlaskStartupParams,
    RestartToken,
};
use crate::logging;
use crate::tray::{build_system_tray, NOTIFICATION_JS};
use crate::yufile::handle_yufile_request;
use std::path::{Path, PathBuf};
use std::process::Child;
use std::sync::Mutex;
use tauri::Manager;

pub struct AppLaunchConfig {
    pub project_root: PathBuf,
    pub python: PathBuf,
    pub port: u16,
    pub log_path: PathBuf,
    pub auto_pin: String,
    pub restart_token: String,
    pub flask_child: Child,
}

fn yufile_roots(project_root: &Path) -> Vec<PathBuf> {
    let config = crate::app_dirs::config_dir()
        .map(|dir| dir.join("config.json"))
        .filter(|path| path.exists())
        .unwrap_or_else(|| project_root.join("config.json"));
    std::fs::read_to_string(config)
        .ok()
        .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
        .map(|value| yufile_roots_from_config(&value))
        .unwrap_or_default()
}

fn yufile_roots_from_config(value: &serde_json::Value) -> Vec<PathBuf> {
    value
        .get("scan_roots")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|value| match value {
            serde_json::Value::String(path) => Some(path.as_str()),
            serde_json::Value::Object(root)
                if root.get("enabled").and_then(serde_json::Value::as_bool) != Some(false) =>
            {
                root.get("path").and_then(serde_json::Value::as_str)
            }
            _ => None,
        })
        .filter_map(|path| std::fs::canonicalize(path).ok())
        .collect()
}

#[cfg(test)]
mod yufile_root_tests {
    use super::yufile_roots_from_config;

    #[test]
    fn accepts_string_and_enabled_object_roots() {
        let dir = std::env::temp_dir();
        let config = serde_json::json!({"scan_roots": [
            dir.to_string_lossy(),
            {"path": dir.to_string_lossy(), "enabled": true},
            {"path": dir.to_string_lossy(), "enabled": false}
        ]});

        assert_eq!(yufile_roots_from_config(&config).len(), 2);
    }
}

#[tauri::command]
async fn restart_flask_server(
    app: tauri::AppHandle,
    window: tauri::WebviewWindow,
    token: String,
) -> Result<String, String> {
    restart_flask_server_impl(app, window, token).await
}

#[tauri::command]
async fn open_in_external_editor(
    app: tauri::AppHandle,
    token: String,
    file_path: String,
) -> Result<String, String> {
    open_in_external_editor_impl(app, token, file_path).await
}

#[tauri::command]
async fn get_external_editor_config() -> Result<crate::external_editor::EditorConfig, String> {
    get_external_editor_config_impl().await
}

#[tauri::command]
async fn set_external_editor_config(
    app: tauri::AppHandle,
    token: String,
    path: String,
) -> Result<crate::external_editor::EditorConfig, String> {
    set_external_editor_config_impl(app, token, path).await
}

pub fn build_auto_pin_js(pin: &str) -> String {
    format!(
        r#"(function(){{
            var pin="{}";
            var misses=0;
            var iv=setInterval(function(){{
                var lockEl=document.getElementById('lockPin');
                if(lockEl){{
                    misses=0;
                    clearInterval(iv);
                    function doUnlock(){{
                        document.removeEventListener('click',doUnlock);
                        document.removeEventListener('keydown',doUnlock);
                        fetch('/api/lock/unlock',{{
                            method:'POST',
                            headers:{{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'}},
                            body:JSON.stringify({{pin:pin}})
                        }}).then(function(r){{if(r.ok)window.location.reload();}});
                    }}
                    document.addEventListener('click',doUnlock);
                    document.addEventListener('keydown',doUnlock);
                    return;
                }}
                var csrfEl=document.querySelector('input[name="_csrf_token"],input[name="csrf_token"]');
                if(!csrfEl){{
                    misses++;
                    if(misses>3)clearInterval(iv);
                    return;
                }}
                misses=0;
                clearInterval(iv);
                var form=document.createElement("form");
                form.method="POST";
                form.action="/_pin_check";
                form.style.display="none";
                var f1=document.createElement("input");f1.name="pin";f1.value=pin;form.appendChild(f1);
                var f2=document.createElement("input");f2.name="_csrf_token";f2.value=csrfEl.value;form.appendChild(f2);
                document.body.appendChild(form);
                form.submit();
            }},500);
        }})();"#,
        pin
    )
}

pub fn build_restart_token_js(restart_token: &str) -> String {
    format!(r#"window.__TAURI_RESTART_TOKEN__="{}";"#, restart_token)
}

fn setup_main_window(
    app: &tauri::AppHandle,
    server_url: &str,
    log_path: &Path,
    auto_pin: &str,
    restart_token: &str,
) -> Result<(), tauri::Error> {
    let window = app.get_webview_window("main").ok_or_else(|| {
        let msg =
            "メインウィンドウの取得に失敗しました (WebView2 が未インストールの可能性があります)";
        logging::log_to_file(log_path, &format!("FATAL: {}", msg));
        tauri::Error::WindowNotFound
    })?;
    let url: tauri::Url = server_url.parse().map_err(|e| {
        logging::log_to_file(log_path, &format!("FATAL: URL parse error: {}", e));
        tauri::Error::InvalidUrl(e)
    })?;
    window.navigate(url).map_err(|e| {
        logging::log_to_file(log_path, &format!("FATAL: navigate error: {}", e));
        e
    })?;
    log!(log_path, "WebView を Flask に接続完了");

    let _ = window.eval(build_auto_pin_js(auto_pin));
    let _ = window.eval(build_restart_token_js(restart_token));
    let _ = window.eval(NOTIFICATION_JS);

    if let Err(e) = build_system_tray(app) {
        logging::log_to_file(log_path, &format!("WARN: system tray build failed: {}", e));
    } else {
        log!(log_path, "System tray icon registered");
    }

    Ok(())
}

fn handle_main_window_event(window: &tauri::Window, event: &tauri::WindowEvent) {
    match event {
        tauri::WindowEvent::CloseRequested { api, .. } => {
            api.prevent_close();
            let _ = window.hide();
        }
        tauri::WindowEvent::Destroyed => {
            let app = window.app_handle();
            if let Some(state) = app.try_state::<FlaskProcess>() {
                if let Ok(mut guard) = state.0.lock() {
                    if let Some(mut child) = guard.take() {
                        eprintln!("[tauri] Flask プロセスを終了中...");
                        let _ = child.kill();
                        let _ = child.wait();
                        eprintln!("[tauri] Flask プロセス終了");
                    }
                }
            }
        }
        _ => {}
    }
}

pub fn run_tauri_app(config: AppLaunchConfig) -> tauri::Result<()> {
    let server_url = format!("http://127.0.0.1:{}/tauri-shell", config.port);
    let setup_log_path = config.log_path.clone();
    let setup_pin = config.auto_pin.clone();
    let setup_restart_token = config.restart_token.clone();
    let yufile_project_root = config.project_root.clone();

    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .invoke_handler(tauri::generate_handler![
            restart_flask_server,
            open_in_external_editor,
            get_external_editor_config,
            set_external_editor_config,
        ])
        .register_uri_scheme_protocol("yufile", move |_ctx, request| {
            let roots = yufile_roots(&yufile_project_root);
            handle_yufile_request(request, &roots)
        })
        .manage(FlaskProcess(Mutex::new(Some(config.flask_child))))
        .manage(FlaskStartupParams {
            project_root: config.project_root,
            python: config.python,
            port: config.port,
            log_path: config.log_path,
        })
        .manage(RestartToken(config.restart_token))
        .manage(MonitoredEditorFiles::new())
        .setup(move |app| {
            Ok(setup_main_window(
                app.handle(),
                &server_url,
                &setup_log_path,
                &setup_pin,
                &setup_restart_token,
            )?)
        })
        .on_window_event(handle_main_window_event)
        .run(tauri::generate_context!())
}
