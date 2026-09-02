use std::io::Write;
use std::path::{Path, PathBuf};
use std::process::{Child, Command, Stdio};
use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::time::Duration;

pub fn resolve_vdevice_group_id(config: &serde_json::Value, env_group_id: Option<&str>) -> String {
    env_group_id
        .filter(|value| !value.is_empty())
        .or_else(|| {
            config
                .get("hailo")
                .and_then(|value| value.get("vdevice_group_id"))
                .and_then(|value| value.as_str())
                .filter(|value| !value.is_empty())
        })
        .unwrap_or("YU_SHARED")
        .to_string()
}

pub fn build_startup_payload(
    scan_roots: &[PathBuf],
    auth_token: &str,
    instance_id: &str,
    vdevice_group_id: &str,
) -> serde_json::Value {
    serde_json::json!({
        "instance_id": instance_id,
        "scan_roots": scan_roots
            .iter()
            .map(|path| path.to_string_lossy().to_string())
            .collect::<Vec<_>>(),
        "auth_token": auth_token,
        "vdevice_group_id": vdevice_group_id,
    })
}

pub fn spawn_yu_infer(
    binary_path: &Path,
    port: u16,
    scan_roots: &[PathBuf],
    auth_token: &str,
    instance_id: &str,
    vdevice_group_id: &str,
    wd_cache_dir: &Path,
    clip_text_model_dir: &Path,
) -> std::io::Result<Child> {
    let mut command = Command::new(binary_path);
    command
        .arg("--port")
        .arg(port.to_string())
        .arg("--wd-cache-dir")
        .arg(wd_cache_dir)
        .env("HAILO_CLIP_TEXT_MODEL_DIR", clip_text_model_dir)
        .stdin(Stdio::piped())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());

    #[cfg(unix)]
    unsafe {
        use std::os::unix::process::CommandExt;

        command.pre_exec(|| {
            if libc::setsid() == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }

    let mut child = command.spawn()?;
    let payload = build_startup_payload(scan_roots, auth_token, instance_id, vdevice_group_id);
    let stdin = child.stdin.as_mut().expect("child stdin was piped");
    if let Err(error) = stdin.write_all(payload.to_string().as_bytes()) {
        let _ = child.kill();
        let _ = child.wait();
        return Err(error);
    }
    child.stdin = None;
    Ok(child)
}

#[cfg(unix)]
pub fn terminate_child(child: &mut Child) {
    unsafe {
        libc::kill(child.id() as libc::pid_t, libc::SIGTERM);
    }
}

// Windows has no SIGTERM equivalent; std::process::Child::kill() maps to
// TerminateProcess, the closest available graceful-enough stop.
#[cfg(windows)]
pub fn terminate_child(child: &mut Child) {
    let _ = child.kill();
}

#[allow(clippy::too_many_arguments)]
pub async fn spawn_with_restart(
    binary_path: &Path,
    port: u16,
    scan_roots: &[PathBuf],
    auth_token: &str,
    instance_id: &str,
    vdevice_group_id: &str,
    wd_cache_dir: &Path,
    clip_text_model_dir: &Path,
    max_attempts: u32,
) -> Option<Child> {
    let base_url = format!("http://127.0.0.1:{port}");

    for attempt in 1..=max_attempts {
        match spawn_yu_infer(
            binary_path,
            port,
            scan_roots,
            auth_token,
            instance_id,
            vdevice_group_id,
            wd_cache_dir,
            clip_text_model_dir,
        ) {
            Ok(mut child) => {
                if wait_for_healthy(&base_url, instance_id, Duration::from_secs(5)).await {
                    return Some(child);
                }

                tracing::warn!(
                    attempt,
                    max_attempts,
                    "yu-infer spawned but did not become healthy"
                );
                let _ = child.kill();
                let _ = child.wait();
            }
            Err(error) => {
                tracing::warn!(
                    attempt,
                    max_attempts,
                    %error,
                    "failed to spawn yu-infer"
                );
            }
        }

        if attempt < max_attempts {
            tokio::time::sleep(Duration::from_millis(200)).await;
        }
    }

    None
}

/// Polls the yu-infer sidecar's liveness and respawns it if it exits while
/// the server is running. `spawn_with_restart` only retries at startup; once
/// healthy, nothing previously watched the child, so a crash (OOM-kill,
/// panic, segfault — anything unrelated to the known CMA non-reclaim issue)
/// left every subsequent request failing until `yu-server` itself restarted.
#[allow(clippy::too_many_arguments)]
pub async fn supervise(
    child: Arc<Mutex<Child>>,
    binary_path: PathBuf,
    port: u16,
    scan_roots: Vec<PathBuf>,
    auth_token: String,
    instance_id: String,
    vdevice_group_id: String,
    wd_cache_dir: PathBuf,
    clip_text_model_dir: PathBuf,
    stop: Arc<AtomicBool>,
) {
    let poll_interval = Duration::from_secs(3);
    loop {
        tokio::time::sleep(poll_interval).await;
        if stop.load(Ordering::Acquire) {
            return;
        }

        let exit_status = {
            let mut guard = child
                .lock()
                .unwrap_or_else(|poisoned| poisoned.into_inner());
            match guard.try_wait() {
                Ok(status) => status,
                Err(error) => {
                    tracing::warn!(%error, "failed to poll yu-infer sidecar status");
                    None
                }
            }
        };
        let Some(status) = exit_status else {
            continue;
        };
        if stop.load(Ordering::Acquire) {
            return;
        }

        tracing::error!(%status, "yu-infer sidecar exited unexpectedly; respawning");
        match spawn_with_restart(
            &binary_path,
            port,
            &scan_roots,
            &auth_token,
            &instance_id,
            &vdevice_group_id,
            &wd_cache_dir,
            &clip_text_model_dir,
            5,
        )
        .await
        {
            Some(mut new_child) => {
                // The `stop` recheck and the install must happen under the
                // same lock acquisition as shutdown's own lock-and-terminate
                // step (see the graceful-shutdown closure in main.rs). A
                // check-then-lock sequence leaves a window where shutdown can
                // set `stop`, terminate whatever child is currently installed,
                // and return — all before this task gets to install
                // `new_child`, orphaning it. Locking first and checking
                // `stop` while still holding the lock makes the two mutually
                // exclusive: either shutdown's terminate call happens first
                // (and sees the old child, or an already-installed
                // `new_child` if this task ran first), or this task's
                // recheck happens first and sees `stop` already set, in
                // which case it discards `new_child` instead of installing
                // it.
                let mut guard = child
                    .lock()
                    .unwrap_or_else(|poisoned| poisoned.into_inner());
                if stop.load(Ordering::Acquire) {
                    drop(guard);
                    terminate_child(&mut new_child);
                    let _ = new_child.wait();
                    tracing::info!(
                        "yu-infer sidecar respawn completed after shutdown was requested; terminated the new child instead of installing it"
                    );
                    return;
                }
                *guard = new_child;
                tracing::info!("yu-infer sidecar respawned after crash");
            }
            None => {
                tracing::error!(
                    "failed to respawn yu-infer sidecar after crash; will retry on next poll"
                );
            }
        }
    }
}

pub async fn wait_for_healthy(
    base_url: &str,
    expected_instance_id: &str,
    timeout: Duration,
) -> bool {
    let url = format!("{}/healthz", base_url.trim_end_matches('/'));
    let client = reqwest::Client::new();

    tokio::time::timeout(timeout, async {
        loop {
            if let Ok(response) = client.get(&url).send().await {
                if response.status().is_success() {
                    if let Ok(body) = response.json::<serde_json::Value>().await {
                        if body.get("instance_id").and_then(|value| value.as_str())
                            == Some(expected_instance_id)
                        {
                            return true;
                        }
                    }
                }
            }

            tokio::time::sleep(Duration::from_millis(100)).await;
        }
    })
    .await
    .unwrap_or(false)
}

#[cfg(test)]
mod tests {
    use super::*;
    use axum::{extract::State, http::StatusCode, routing::get, Router};
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use std::time::Duration;

    #[test]
    fn vdevice_group_id_resolution_matches_python_priority() {
        let config = serde_json::json!({"hailo": {"vdevice_group_id": "CONFIG_GROUP"}});

        assert_eq!(
            resolve_vdevice_group_id(&config, Some("ENV_GROUP")),
            "ENV_GROUP"
        );
        assert_eq!(resolve_vdevice_group_id(&config, Some("")), "CONFIG_GROUP");
        assert_eq!(resolve_vdevice_group_id(&config, None), "CONFIG_GROUP");
        assert_eq!(
            resolve_vdevice_group_id(&serde_json::json!({}), None),
            "YU_SHARED"
        );
    }

    #[test]
    fn build_startup_payload_serializes_roots_and_token() {
        let roots = vec![PathBuf::from("/data/a"), PathBuf::from("/data/b")];
        let payload = build_startup_payload(&roots, "tok123", "inst-1", "YU_SHARED");
        assert_eq!(payload["scan_roots"][0], "/data/a");
        assert_eq!(payload["scan_roots"][1], "/data/b");
        assert_eq!(payload["auth_token"], "tok123");
        assert_eq!(payload["instance_id"], "inst-1");
        assert_eq!(payload["vdevice_group_id"], "YU_SHARED");
    }

    #[test]
    fn build_startup_payload_handles_empty_roots() {
        let payload = build_startup_payload(&[], "tok123", "inst-1", "YU_SHARED");
        assert_eq!(payload["scan_roots"].as_array().unwrap().len(), 0);
    }

    #[cfg(unix)]
    #[test]
    fn terminate_child_sends_sigterm_and_process_exits() {
        let mut child = Command::new("sleep")
            .arg("30")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn sleep");

        terminate_child(&mut child);

        let deadline = std::time::Instant::now() + Duration::from_secs(2);
        while std::time::Instant::now() < deadline {
            if child.try_wait().expect("wait sleep").is_some() {
                return;
            }
            std::thread::sleep(Duration::from_millis(20));
        }

        let _ = child.kill();
        let _ = child.wait();
        panic!("child did not exit after SIGTERM");
    }

    #[tokio::test]
    async fn spawn_with_restart_gives_up_after_max_attempts_for_nonexistent_binary() {
        let missing_binary =
            std::env::temp_dir().join(format!("yu-infer-missing-{}", std::process::id()));
        let child = spawn_with_restart(
            &missing_binary,
            18771,
            &[],
            "tok123",
            "inst-1",
            "YU_SHARED",
            &std::env::temp_dir(),
            &std::env::temp_dir(),
            2,
        )
        .await;

        assert!(child.is_none());
    }

    #[tokio::test]
    async fn supervise_detects_crash_and_attempts_respawn_without_panicking() {
        // A child that exits almost immediately stands in for a crashed sidecar.
        let dead_child = Command::new("true")
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .expect("spawn `true`");
        let child = Arc::new(Mutex::new(dead_child));
        let stop = Arc::new(AtomicBool::new(false));
        let missing_binary =
            std::env::temp_dir().join(format!("yu-infer-missing-{}", std::process::id()));

        let stop_clone = Arc::clone(&stop);
        let supervisor = tokio::spawn(supervise(
            Arc::clone(&child),
            missing_binary,
            18771,
            vec![],
            "tok123".to_string(),
            "inst-1".to_string(),
            "YU_SHARED".to_string(),
            std::env::temp_dir(),
            std::env::temp_dir(),
            stop_clone,
        ));

        // Give the first poll tick time to observe the exit and attempt (and
        // fail, since the respawn binary does not exist) a respawn.
        tokio::time::sleep(Duration::from_secs(4)).await;
        stop.store(true, Ordering::Release);

        tokio::time::timeout(Duration::from_secs(5), supervisor)
            .await
            .expect("supervisor task did not stop after the stop flag was set")
            .expect("supervisor task panicked");
    }

    #[tokio::test]
    async fn wait_for_healthy_returns_false_on_timeout_when_nothing_listening() {
        assert!(!wait_for_healthy("http://127.0.0.1:9", "inst-1", Duration::from_millis(50)).await);
    }

    async fn flaky_healthz(
        State(count): State<Arc<AtomicUsize>>,
    ) -> (StatusCode, axum::Json<serde_json::Value>) {
        if count.fetch_add(1, Ordering::SeqCst) == 0 {
            (
                StatusCode::SERVICE_UNAVAILABLE,
                axum::Json(serde_json::json!({"ok": false, "instance_id": "inst-1"})),
            )
        } else {
            (
                StatusCode::OK,
                axum::Json(serde_json::json!({"ok": true, "instance_id": "inst-1"})),
            )
        }
    }

    #[tokio::test]
    async fn wait_for_healthy_returns_true_once_server_responds() {
        let count = Arc::new(AtomicUsize::new(0));
        let app = Router::new()
            .route("/healthz", get(flaky_healthz))
            .with_state(count);
        let listener = match tokio::net::TcpListener::bind("127.0.0.1:0").await {
            Ok(listener) => listener,
            Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied => return,
            Err(e) => panic!("failed to bind mock health server: {e}"),
        };
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });

        assert!(
            wait_for_healthy(&format!("http://{addr}"), "inst-1", Duration::from_secs(1)).await
        );
    }

    #[tokio::test]
    async fn wait_for_healthy_rejects_mismatched_instance_id() {
        let app = Router::new().route(
            "/healthz",
            get(|| async {
                (
                    StatusCode::OK,
                    axum::Json(serde_json::json!({"ok": true, "instance_id": "other"})),
                )
            }),
        );
        let listener = match tokio::net::TcpListener::bind("127.0.0.1:0").await {
            Ok(listener) => listener,
            Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied => return,
            Err(e) => panic!("failed to bind mock health server: {e}"),
        };
        let addr = listener.local_addr().unwrap();
        tokio::spawn(async move {
            axum::serve(listener, app).await.unwrap();
        });

        assert!(
            !wait_for_healthy(
                &format!("http://{addr}"),
                "inst-1",
                Duration::from_millis(150)
            )
            .await
        );
    }
}
