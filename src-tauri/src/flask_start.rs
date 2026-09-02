use std::io::{BufRead, BufReader};
use std::path::Path;
use std::process::{Child, Command, Stdio};

#[cfg(windows)]
use std::os::windows::process::CommandExt;

#[allow(unused_imports)]
use crate::log;

fn build_config_arg(project_root: &Path, log_path: &Path) -> Vec<String> {
    let data_dir = crate::app_dirs::ensure_data_dir();
    let config_in_data = data_dir.as_ref().map(|d| d.join("config.json"));
    let config_in_project = project_root.join("config.json");

    #[cfg(debug_assertions)]
    let use_config_test = project_root.join("config_test.json").exists();
    #[cfg(not(debug_assertions))]
    let use_config_test = false;

    if use_config_test {
        vec![
            "--config".to_string(),
            project_root
                .join("config_test.json")
                .to_string_lossy()
                .to_string(),
        ]
    } else if config_in_data.as_ref().is_some_and(|p| p.exists()) {
        vec![
            "--config".to_string(),
            config_in_data.unwrap().to_string_lossy().to_string(),
        ]
    } else if config_in_project.exists() {
        if let Some(ref dd) = data_dir {
            let dest = dd.join("config.json");
            let _ = std::fs::copy(&config_in_project, &dest);
            log!(log_path, "Migrated config.json to {}", dest.display());
            vec!["--config".to_string(), dest.to_string_lossy().to_string()]
        } else {
            vec![
                "--config".to_string(),
                config_in_project.to_string_lossy().to_string(),
            ]
        }
    } else if let Some(ref dd) = data_dir {
        let dest = dd.join("config.json");
        let _ = std::fs::write(&dest, "{\n}\n");
        log!(
            log_path,
            "Created default config.json at {}",
            dest.display()
        );
        vec!["--config".to_string(), dest.to_string_lossy().to_string()]
    } else {
        vec![]
    }
}

fn resolve_db_path(project_root: &Path) -> std::path::PathBuf {
    let data_dir = crate::app_dirs::ensure_data_dir();
    let db_in_data = data_dir.as_ref().map(|d| d.join("tags.db"));
    if db_in_data.as_ref().is_some_and(|p| p.exists()) {
        db_in_data.unwrap()
    } else if project_root.join("tags.db").exists() {
        project_root.join("tags.db")
    } else if project_root.join("data/tags.db").exists() {
        project_root.join("data/tags.db")
    } else {
        db_in_data.unwrap_or_else(|| project_root.join("data/tags.db"))
    }
}

fn attach_log_drains(child: &mut Child, log_path: &Path) {
    if let Some(stderr) = child.stderr.take() {
        let log_dest = log_path.to_path_buf();
        std::thread::Builder::new()
            .name("flask-stderr-drain".into())
            .spawn(move || {
                let reader = BufReader::new(stderr);
                for line in reader.lines() {
                    match line {
                        Ok(l) => crate::logging::log_to_file(&log_dest, &format!("[flask] {}", l)),
                        Err(_) => break,
                    }
                }
            })
            .ok();
    }

    if let Some(stdout) = child.stdout.take() {
        std::thread::Builder::new()
            .name("flask-stdout-drain".into())
            .spawn(move || {
                let reader = BufReader::new(stdout);
                for line in reader.lines() {
                    if line.is_err() {
                        break;
                    }
                }
            })
            .ok();
    }
}

/// Start the Flask server.
pub fn start_flask(
    project_root: &Path,
    python: &Path,
    port: u16,
    auto_pin: &str,
    log_path: &Path,
) -> std::io::Result<Child> {
    let web_ui = project_root.join("web_ui.py");
    let config_arg = build_config_arg(project_root, log_path);
    let db_path = resolve_db_path(project_root);

    let mut args: Vec<String> = vec![
        web_ui.to_string_lossy().to_string(),
        "--db".to_string(),
        db_path.to_string_lossy().to_string(),
        "--host".to_string(),
        "127.0.0.1".to_string(),
        "--port".to_string(),
        port.to_string(),
        "--allow-restart".to_string(),
    ];
    args.extend(config_arg);

    let data_dir = crate::app_dirs::ensure_data_dir();
    let mut cmd = Command::new(python);
    cmd.current_dir(project_root)
        .args(&args)
        .env("YU_TAURI_PIN", auto_pin)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(ref dd) = data_dir {
        cmd.env("TAGDB_DATA_DIR", dd.join("data"))
            .env("TAGDB_CACHE_DIR", dd.join("cache"))
            .env("TAGDB_LOG_DIR", dd.join("logs"))
            .env("TAGDB_PROFILES_DIR", dd.join("profiles"));
        log!(log_path, "TAGDB_*_DIR env vars set under {}", dd.display());
    }

    #[cfg(windows)]
    {
        const CREATE_NO_WINDOW: u32 = 0x0800_0000;
        cmd.creation_flags(CREATE_NO_WINDOW);
    }

    let mut child = cmd.spawn()?;
    attach_log_drains(&mut child, log_path);
    Ok(child)
}
