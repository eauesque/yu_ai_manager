// YU AI Manager — Tauri Desktop Wrapper
//
// Launches a Flask server as a child process and displays it in a WebView.
// Project root detection: see project_root.rs (4 stages).
// Errors are reported to the user via Windows MessageBox.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

#[macro_use]
mod logging;
mod app_dirs;
mod project_root;
#[macro_use]
mod flask;
#[macro_use]
mod external_editor;
mod main_runtime;
mod tray;
mod yu_server;
mod yufile;
use app_dirs::{config_dir, ensure_data_dir};
use flask::{find_free_port, find_python, generate_random_pin, start_flask, wait_for_server};
use main_runtime::{run_tauri_app, AppLaunchConfig};
use project_root::resolve_project_root;

use std::path::PathBuf;
use std::time::Duration;

fn main() {
    // Log file path in the same directory as the exe (temporary path before project root detection)
    let initial_log_path = std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.join("yu-ai-manager.log")))
        .unwrap_or_else(|| PathBuf::from("yu-ai-manager.log"));

    // Panic hook: with windows_subsystem = "windows", panics silently terminate,
    // so we notify via MessageBox + log
    {
        let panic_log = initial_log_path.clone();
        std::panic::set_hook(Box::new(move |info| {
            let msg = format!("予期しないエラーが発生しました:\n\n{}", info);
            logging::log_to_file(&panic_log, &format!("PANIC: {}", info));
            logging::show_message_box("YU AI Manager - 致命的エラー", &msg, true);
        }));
    }

    log!(&initial_log_path, "=== YU AI Manager 起動 ===");
    log!(
        &initial_log_path,
        "exe: {}",
        std::env::current_exe()
            .map(|p| p.display().to_string())
            .unwrap_or_else(|_| "unknown".into())
    );

    // 1. Project root detection (near exe -> saved config -> dialog)
    let project_root = match resolve_project_root(&initial_log_path) {
        Ok(root) => root,
        Err(msg) => {
            logging::show_error_and_exit("YU AI Manager - 起動エラー", &msg, &initial_log_path)
        }
    };

    // Log to data dir if available, otherwise project root
    let log_path = ensure_data_dir()
        .map(|d| d.join("yu-ai-manager.log"))
        .unwrap_or_else(|| project_root.join("yu-ai-manager.log"));
    log!(&log_path, "プロジェクトルート: {}", project_root.display());
    if let Some(dd) = config_dir() {
        log!(&log_path, "データディレクトリ: {}", dd.display());
    }

    // Change CWD to project root
    if let Err(e) = std::env::set_current_dir(&project_root) {
        logging::show_error_and_exit(
            "YU AI Manager - 起動エラー",
            &format!(
                "作業ディレクトリの変更に失敗しました。\n\n{}\n\nパス: {}",
                e,
                project_root.display()
            ),
            &log_path,
        );
    }

    // 2. yu-server detection (standalone mode — no Python required)
    if let Some(yu_bin) = yu_server::find_yu_server_bin() {
        log!(&log_path, "yu-server バイナリ検出: {}", yu_bin.display());
        let port = match find_free_port() {
            Ok(p) => p,
            Err(msg) => {
                logging::show_error_and_exit("YU AI Manager - ポート確保エラー", &msg, &log_path)
            }
        };
        log!(&log_path, "yu-server 用にポート {} を確保", port);
        // Starting yu-server can fail for reasons the user cannot act on -- a
        // schema the bundled binary does not know, a port already taken.
        // Degrade to Python rather than refusing to open. Bundling a binary
        // makes version skew ordinary, and a user cannot act on
        // "yu-server failed to start". The actual degrade-vs-use decision is
        // made by yu_server::decide_fast_mode_outcome(), a pure function
        // that is unit tested independently of this binary-only crate (see
        // yu_server.rs's `fallback_tests`); this block must route through
        // its answer rather than deciding on its own.
        let server_child = match yu_server::start_yu_server(&yu_bin, &project_root, port, &log_path)
        {
            Ok(child) => Some(child),
            Err(e) => {
                log!(
                    &log_path,
                    "yu-server の起動に失敗したため Python 経路へ降格します: {}",
                    e
                );
                None
            }
        };
        let spawn_succeeded = server_child.is_some();
        if let Some(ref child) = server_child {
            log!(&log_path, "yu-server プロセス起動 (PID: {})", child.id());
        }

        let server_timeout = Duration::from_secs(30);
        let became_ready = spawn_succeeded && wait_for_server(port, server_timeout);

        match yu_server::decide_fast_mode_outcome(spawn_succeeded, became_ready) {
            yu_server::FastModeOutcome::UseYuServer => {
                let server_child =
                    server_child.expect("UseYuServer only when spawn_succeeded is true");
                log!(&log_path, "yu-server 起動確認 (port {})", port);
                let restart_token = generate_random_pin();
                let run_result = run_tauri_app(AppLaunchConfig {
                    project_root: project_root.clone(),
                    python: PathBuf::default(), // not used in standalone mode
                    port,
                    log_path: log_path.clone(),
                    auto_pin: String::new(), // PIN auth not applicable in standalone mode
                    restart_token,
                    flask_child: server_child,
                });
                if let Err(e) = run_result {
                    logging::show_error_and_exit(
                        "YU AI Manager - 起動エラー",
                        &format!("Tauri アプリの起動に失敗しました。\n\n{}", e),
                        &log_path,
                    );
                }
                return;
            }
            yu_server::FastModeOutcome::DegradeToPython => {
                if let Some(mut server_child) = server_child {
                    log!(
                        &log_path,
                        "yu-server が {} 秒以内に起動しなかったため Python 経路へ降格します (port {})",
                        server_timeout.as_secs(),
                        port
                    );
                    let _ = server_child.kill();
                    let _ = server_child.wait();
                }
                // Fall through to Python detection below (fast-mode degradation).
            }
        }
    }

    // 3. Python detection (Flask fallback when yu-server is not available)
    let python = match find_python(&project_root) {
        Ok(p) => p,
        Err(msg) => logging::show_error_and_exit("YU AI Manager - Python 未検出", &msg, &log_path),
    };
    log!(&log_path, "Python: {}", python.display());

    // 3. Port allocation
    let port = match find_free_port() {
        Ok(p) => p,
        Err(msg) => {
            logging::show_error_and_exit("YU AI Manager - ポート確保エラー", &msg, &log_path)
        }
    };
    log!(&log_path, "Flask 用にポート {} を確保", port);

    // 4. Start Flask (auto-generated PIN for security)
    let auto_pin = generate_random_pin();
    log!(&log_path, "Auto-PIN generated for Tauri session");
    let flask_child = match start_flask(&project_root, &python, port, &auto_pin, &log_path) {
        Ok(child) => child,
        Err(e) => logging::show_error_and_exit(
            "YU AI Manager - Flask 起動エラー",
            &format!(
                "Flask サーバーの起動に失敗しました。\n\n{}\n\nPython: {}",
                e,
                python.display()
            ),
            &log_path,
        ),
    };
    log!(&log_path, "Flask プロセス起動 (PID: {})", flask_child.id());

    // 5. Wait for Flask to start
    // First run (after bundle.zip extraction) may take longer due to pyc compilation.
    let server_timeout = Duration::from_secs(120);
    if !wait_for_server(port, server_timeout) {
        logging::show_error_and_exit(
            "YU AI Manager - タイムアウト",
            &format!(
                "Flask サーバーが 120 秒以内に起動しませんでした。\n\n\
                 考えられる原因:\n\
                 - 初回起動時は Python の初期化に時間がかかります (しばらくお待ちください)\n\
                 - venv の依存パッケージ不足 (uv pip install -r requirements.txt)\n\
                 - tags.db が存在しない\n\
                 - ポート {} が他のプロセスに使用中\n\n\
                 詳細はログファイルを確認してください:\n{}",
                port,
                log_path.display()
            ),
            &log_path,
        );
    }
    log!(&log_path, "Flask サーバー起動確認 (port {})", port);

    let restart_token = generate_random_pin(); // Separate cryptographic token for IPC auth
    let run_result = run_tauri_app(AppLaunchConfig {
        project_root: project_root.clone(),
        python: python.clone(),
        port,
        log_path: log_path.clone(),
        auto_pin: auto_pin.clone(),
        restart_token,
        flask_child,
    });

    if let Err(e) = run_result {
        logging::show_error_and_exit(
            "YU AI Manager - 起動エラー",
            &format!(
                "Tauri アプリの起動に失敗しました。\n\n{}\n\n\
                 WebView2 ランタイムがインストールされているか確認してください。\n\
                 https://developer.microsoft.com/en-us/microsoft-edge/webview2/",
                e
            ),
            &log_path,
        );
    }
}

#[cfg(test)]
mod main_tests;
