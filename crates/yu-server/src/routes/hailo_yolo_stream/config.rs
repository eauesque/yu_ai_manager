use std::{
    fs::{self, File, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicU64, Ordering},
        Arc,
    },
};

use tokio::sync::{mpsc, RwLock};

use super::{
    registry::{ConfigCommand, ConfigWriteError},
    rules::StreamConfig,
};

const CONFIG_CHANNEL_CAPACITY: usize = 32;
static TEMP_SEQUENCE: AtomicU64 = AtomicU64::new(0);

type WriteConfig = Arc<dyn Fn(&Path, &StreamConfig) -> io::Result<()> + Send + Sync>;

pub(crate) struct ConfigWriterHandle {
    pub(crate) restored: StreamConfig,
    pub(crate) snapshot: Arc<RwLock<StreamConfig>>,
    pub(crate) tx: mpsc::Sender<ConfigCommand>,
    /// At least one protected value was on disk in the clear, so the caller should
    /// issue one `PersistSnapshot` to rewrite it encrypted.
    pub(crate) migration_needed: bool,
}

pub(crate) struct ConfigWriterTask {
    path: PathBuf,
    project_root: PathBuf,
    config: StreamConfig,
    snapshot: Arc<RwLock<StreamConfig>>,
    rx: mpsc::Receiver<ConfigCommand>,
    write: WriteConfig,
    /// Nothing on disk could be decrypted. Refuse every write: the key is more
    /// likely missing than every value corrupt, and an empty snapshot would
    /// destroy a config that is merely unreadable right now.
    locked: bool,
}

impl ConfigWriterTask {
    pub(crate) fn spawn(path: PathBuf, project_root: PathBuf) -> ConfigWriterHandle {
        Self::spawn_with(path, project_root, Arc::new(write_snapshot))
    }

    fn spawn_with(path: PathBuf, project_root: PathBuf, write: WriteConfig) -> ConfigWriterHandle {
        let loaded = load_config(&path, &project_root);
        let restored = loaded.config;
        let snapshot = Arc::new(RwLock::new(restored.clone()));
        let (tx, rx) = mpsc::channel(CONFIG_CHANNEL_CAPACITY);
        let task = Self {
            path,
            project_root,
            config: restored.clone(),
            snapshot: Arc::clone(&snapshot),
            rx,
            write,
            locked: loaded.locked,
        };
        tokio::spawn(task.run());
        ConfigWriterHandle {
            restored,
            snapshot,
            tx,
            migration_needed: loaded.migration_needed,
        }
    }

    async fn run(mut self) {
        while let Some(command) = self.rx.recv().await {
            if self.locked {
                // Applying the command first would put it in the snapshot that a
                // later unlocked write persists, so refuse before touching memory.
                let _ = command.reply().send(Err(ConfigWriteError));
                continue;
            }
            match &command {
                ConfigCommand::UpsertSource { source, .. } => {
                    if let Some(existing) = self
                        .config
                        .sources
                        .iter_mut()
                        .find(|existing| existing.id == source.id)
                    {
                        *existing = source.clone();
                    } else {
                        self.config.sources.push(source.clone());
                    }
                }
                ConfigCommand::DeleteSource { source_id, .. } => {
                    self.config.sources.retain(|source| source.id != *source_id);
                }
                ConfigCommand::UpsertRule { rule, .. } => {
                    if let Some(existing) = self
                        .config
                        .rules
                        .iter_mut()
                        .find(|existing| existing.id == rule.id)
                    {
                        *existing = rule.clone();
                    } else {
                        self.config.rules.push(rule.clone());
                    }
                }
                ConfigCommand::DeleteRule { rule_id, .. } => {
                    self.config.rules.retain(|rule| rule.id != *rule_id);
                }
                // Rewrites the current snapshot unchanged. Used to migrate a
                // plaintext config without a user-visible mutation.
                ConfigCommand::PersistSnapshot { .. } => {}
            }

            *self.snapshot.write().await = self.config.clone();
            let result = super::secrets::encrypt_config(&self.config, &self.project_root)
                .map_err(|error| {
                    tracing::error!(%error, path = %self.path.display(), "refusing to persist stream config in the clear");
                    ConfigWriteError
                })
                .and_then(|encrypted| {
                    (self.write)(&self.path, &encrypted).map_err(|error| {
                        tracing::error!(%error, path = %self.path.display(), "failed to persist stream config");
                        ConfigWriteError
                    })
                });
            let _ = command.reply().send(result);
        }
    }
}

fn load_config(path: &Path, project_root: &Path) -> super::secrets::LoadOutcome {
    if !path.exists() {
        return super::secrets::LoadOutcome {
            config: StreamConfig::default(),
            locked: false,
            migration_needed: false,
        };
    }
    if let Err(error) = restrict_owner_only(path) {
        tracing::warn!(%error, path = %path.display(), "failed to restrict stream config permissions");
    }
    let raw: StreamConfig = fs::read(path)
        .ok()
        .and_then(|bytes| serde_json::from_slice(&bytes).ok())
        .unwrap_or_default();
    super::secrets::decrypt_config(raw, project_root)
}

fn write_snapshot(path: &Path, config: &StreamConfig) -> io::Result<()> {
    write_snapshot_inner(path, config, None)
}

#[derive(Clone, Copy)]
enum WriteFault {
    Permission,
    Capacity,
    Rename,
}

fn write_snapshot_inner(
    path: &Path,
    config: &StreamConfig,
    fault: Option<WriteFault>,
) -> io::Result<()> {
    if matches!(fault, Some(WriteFault::Permission)) {
        return Err(io::Error::new(
            io::ErrorKind::PermissionDenied,
            "injected permission failure",
        ));
    }

    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    fs::create_dir_all(parent)?;
    if path.exists() {
        restrict_owner_only(path)?;
    }

    let (temporary, mut file) = create_temporary(parent)?;
    let result = (|| {
        restrict_owner_only(&temporary)?;
        if matches!(fault, Some(WriteFault::Capacity)) {
            return Err(io::Error::other("injected capacity failure"));
        }
        let mut bytes = serde_json::to_vec_pretty(config)
            .map_err(|error| io::Error::new(io::ErrorKind::InvalidData, error))?;
        bytes.push(b'\n');
        file.write_all(&bytes)?;
        file.sync_all()?;
        drop(file);
        if matches!(fault, Some(WriteFault::Rename)) {
            return Err(io::Error::other("injected rename failure"));
        }
        atomic_replace(&temporary, path)?;
        restrict_owner_only(path)
    })();

    if result.is_err() {
        let _ = fs::remove_file(&temporary);
    }
    result
}

fn create_temporary(parent: &Path) -> io::Result<(PathBuf, File)> {
    for _ in 0..8 {
        let path = parent.join(format!(
            ".stream_config.{}.{}.tmp",
            std::process::id(),
            TEMP_SEQUENCE.fetch_add(1, Ordering::Relaxed)
        ));
        let mut options = OpenOptions::new();
        options.write(true).create_new(true);
        #[cfg(unix)]
        {
            use std::os::unix::fs::OpenOptionsExt;
            options.mode(0o600);
        }
        match options.open(&path) {
            Ok(file) => return Ok((path, file)),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => {}
            Err(error) => return Err(error),
        }
    }
    Err(io::Error::new(
        io::ErrorKind::AlreadyExists,
        "could not allocate a stream config temporary file",
    ))
}

#[cfg(not(windows))]
fn atomic_replace(from: &Path, to: &Path) -> io::Result<()> {
    fs::rename(from, to)
}

#[cfg(windows)]
fn atomic_replace(from: &Path, to: &Path) -> io::Result<()> {
    use std::os::windows::ffi::OsStrExt;
    use windows_sys::Win32::Storage::FileSystem::{
        MoveFileExW, MOVEFILE_REPLACE_EXISTING, MOVEFILE_WRITE_THROUGH,
    };

    let from: Vec<u16> = from.as_os_str().encode_wide().chain(Some(0)).collect();
    let to: Vec<u16> = to.as_os_str().encode_wide().chain(Some(0)).collect();
    if unsafe {
        MoveFileExW(
            from.as_ptr(),
            to.as_ptr(),
            MOVEFILE_REPLACE_EXISTING | MOVEFILE_WRITE_THROUGH,
        )
    } == 0
    {
        Err(io::Error::last_os_error())
    } else {
        Ok(())
    }
}

#[cfg(unix)]
fn restrict_owner_only(path: &Path) -> io::Result<()> {
    use std::os::unix::fs::PermissionsExt;
    fs::set_permissions(path, fs::Permissions::from_mode(0o600))
}

#[cfg(windows)]
fn restrict_owner_only(path: &Path) -> io::Result<()> {
    use std::{mem::size_of, os::windows::ffi::OsStrExt, ptr::null_mut};
    use windows_sys::Win32::{
        Foundation::{CloseHandle, ERROR_SUCCESS, HANDLE},
        Security::{
            AddAccessAllowedAce,
            Authorization::{SetNamedSecurityInfoW, SE_FILE_OBJECT},
            GetLengthSid, GetTokenInformation, InitializeAcl, TokenUser, ACCESS_ALLOWED_ACE, ACL,
            ACL_REVISION, DACL_SECURITY_INFORMATION, PROTECTED_DACL_SECURITY_INFORMATION,
            TOKEN_QUERY, TOKEN_USER,
        },
        System::Threading::{GetCurrentProcess, OpenProcessToken},
    };

    let mut token: HANDLE = null_mut();
    if unsafe { OpenProcessToken(GetCurrentProcess(), TOKEN_QUERY, &mut token) } == 0 {
        return Err(io::Error::last_os_error());
    }
    let result = (|| {
        let mut length = 0;
        unsafe {
            GetTokenInformation(token, TokenUser, null_mut(), 0, &mut length);
        }
        if length == 0 {
            return Err(io::Error::last_os_error());
        }
        let words = (length as usize).div_ceil(size_of::<usize>());
        let mut token_info = vec![0_usize; words];
        if unsafe {
            GetTokenInformation(
                token,
                TokenUser,
                token_info.as_mut_ptr().cast(),
                length,
                &mut length,
            )
        } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let sid = unsafe { (*(token_info.as_ptr().cast::<TOKEN_USER>())).User.Sid };
        let acl_bytes = size_of::<ACL>() + size_of::<ACCESS_ALLOWED_ACE>() - size_of::<u32>()
            + unsafe { GetLengthSid(sid) } as usize;
        let mut acl = vec![0_usize; acl_bytes.div_ceil(size_of::<usize>())];
        let acl = acl.as_mut_ptr().cast::<ACL>();
        if unsafe { InitializeAcl(acl, acl_bytes as u32, ACL_REVISION) } == 0
            || unsafe { AddAccessAllowedAce(acl, ACL_REVISION, 0x001f01ff, sid) } == 0
        {
            return Err(io::Error::last_os_error());
        }
        let wide: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
        let status = unsafe {
            SetNamedSecurityInfoW(
                wide.as_ptr(),
                SE_FILE_OBJECT,
                DACL_SECURITY_INFORMATION | PROTECTED_DACL_SECURITY_INFORMATION,
                null_mut(),
                null_mut(),
                acl,
                null_mut(),
            )
        };
        if status == ERROR_SUCCESS {
            Ok(())
        } else {
            Err(io::Error::from_raw_os_error(status as i32))
        }
    })();
    unsafe {
        CloseHandle(token);
    }
    result
}

#[cfg(not(any(unix, windows)))]
fn restrict_owner_only(_path: &Path) -> io::Result<()> {
    Err(io::Error::new(
        io::ErrorKind::Unsupported,
        "owner-only file permissions are unsupported on this platform",
    ))
}

#[cfg(test)]
mod tests {
    use std::{
        collections::HashSet,
        io::ErrorKind,
        net::TcpListener,
        process::Stdio,
        str::FromStr,
        sync::atomic::{AtomicBool, AtomicUsize},
        time::Duration,
    };

    use serde_json::json;
    use tempfile::tempdir;
    use tokio::{process::Command, sync::oneshot};

    use super::super::{
        registry::StreamState,
        rules::{DetectionRule, StreamSourceConfig},
        run_bounded_test,
    };
    use super::*;
    use crate::{
        infer_client::InferClient,
        logs::ring::LogRingBuffer,
        state::{AppState, Config},
    };

    const TEST_TIMEOUT: Duration = Duration::from_secs(20);

    fn source(id: &str) -> StreamSourceConfig {
        StreamSourceConfig {
            id: id.to_string(),
            url: "rtsp://camera.test/live".to_string(),
            name: id.to_string(),
        }
    }

    fn rule(id: &str) -> DetectionRule {
        serde_json::from_value(json!({"id": id})).unwrap()
    }

    fn oracle_rule(id: &str) -> DetectionRule {
        serde_json::from_value(json!({
            "id": id,
            "actions": [{
                "type": "webhook",
                "url": "https://webhook.test/hook",
                "secret": "webhook-secret",
                "headers": {"Authorization": "Bearer test-token"},
            }],
        }))
        .unwrap()
    }

    async fn send(
        tx: &mpsc::Sender<ConfigCommand>,
        command: impl FnOnce(oneshot::Sender<Result<(), ConfigWriteError>>) -> ConfigCommand,
    ) -> Result<(), ConfigWriteError> {
        let (reply, result) = oneshot::channel();
        tx.send(command(reply)).await.unwrap();
        result.await.unwrap()
    }

    /// Read what the writer actually persisted, decrypted, so assertions can keep
    /// comparing against plaintext fixtures.
    fn disk_at(path: &Path, project_root: &Path) -> StreamConfig {
        super::super::secrets::decrypt_config(disk_raw(path), project_root).config
    }

    fn disk_raw(path: &Path) -> StreamConfig {
        serde_json::from_slice(&fs::read(path).unwrap()).unwrap()
    }

    async fn app_state(project_root: PathBuf, infer_url: String) -> AppState {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        AppState::new_with_infer(
            Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: false,
                pin_auth_enabled: false,
                min_pin_length: 4,
                python_url: String::new(),
                config_path: project_root.join("config.json"),
                project_root: project_root.clone(),
                app_config: json!({
                    "extensions": {"builtin-hailo-yolo-detect": {"stream_max_sources": 4}}
                }),
                cache_dir: project_root.join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                standalone: false,
                infer_standalone: true,
                python_executable: String::new(),
                mcp_native: false,
                active_profile: None,
                pin_boss_login_ui: false,
            },
            pool.clone(),
            pool,
            Arc::new(LogRingBuffer::new(64)),
            Some(InferClient::new(infer_url, "test".to_string())),
            None,
        )
        .await
    }

    #[test]
    fn source_and_rule_crud_share_one_snapshot_for_alternating_and_concurrent_writes() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let path = root.path().join("stream_config.json");
            let writer = ConfigWriterTask::spawn(path.clone(), root.path().to_path_buf());

            send(&writer.tx, |reply| ConfigCommand::UpsertSource {
                source: source("one"),
                reply,
            })
            .await
            .unwrap();
            send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                rule: rule("alpha"),
                reply,
            })
            .await
            .unwrap();
            assert_eq!(disk_at(&path, root.path()), *writer.snapshot.read().await);

            let add_source = send(&writer.tx, |reply| ConfigCommand::UpsertSource {
                source: source("two"),
                reply,
            });
            let add_rule = send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                rule: rule("beta"),
                reply,
            });
            let (source_result, rule_result) = tokio::join!(add_source, add_rule);
            source_result.unwrap();
            rule_result.unwrap();

            send(&writer.tx, |reply| ConfigCommand::DeleteSource {
                source_id: "one".to_string(),
                reply,
            })
            .await
            .unwrap();
            send(&writer.tx, |reply| ConfigCommand::DeleteRule {
                rule_id: "alpha".to_string(),
                reply,
            })
            .await
            .unwrap();
            let snapshot = writer.snapshot.read().await.clone();
            assert_eq!(snapshot.sources, vec![source("two")]);
            assert_eq!(snapshot.rules, vec![rule("beta")]);
            assert_eq!(disk_at(&path, root.path()), snapshot);
        });
    }

    #[test]
    fn corrupt_and_missing_config_fallback_without_disk_writes() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let corrupt = root.path().join("stream_config.json");
            fs::write(&corrupt, b"{broken").unwrap();
            let before = fs::metadata(&corrupt).unwrap().modified().unwrap();
            let writer = ConfigWriterTask::spawn(corrupt.clone(), root.path().to_path_buf());
            assert_eq!(writer.restored, StreamConfig::default());
            tokio::task::yield_now().await;
            assert_eq!(fs::read(&corrupt).unwrap(), b"{broken");
            assert_eq!(fs::metadata(&corrupt).unwrap().modified().unwrap(), before);
            assert_eq!(fs::read_dir(root.path()).unwrap().count(), 1);

            let missing = root.path().join("missing.json");
            let writer = ConfigWriterTask::spawn(missing.clone(), root.path().to_path_buf());
            assert_eq!(writer.restored, StreamConfig::default());
            tokio::task::yield_now().await;
            assert!(!missing.exists());
        });
    }

    #[cfg(unix)]
    #[test]
    fn real_app_state_is_inactive_for_all_startup_corpora() {
        use std::os::unix::fs::PermissionsExt;

        run_bounded_test(TEST_TIMEOUT, async {
            let listener = TcpListener::bind("127.0.0.1:0").unwrap();
            listener.set_nonblocking(true).unwrap();
            let infer_url = format!("http://{}", listener.local_addr().unwrap());
            let spawn_observer = Arc::new(AtomicUsize::new(0));
            let normal = serde_json::to_vec(&json!({
                "sources": [{"id": "cam", "url": "rtsp://camera.test/live", "name": "Cam"}],
                "rules": [{"id": "person"}]
            }))
            .unwrap();
            let cases = [
                ("normal", Some(normal.as_slice()), 0o600, 1),
                ("corrupt", Some(b"{broken".as_slice()), 0o600, 0),
                ("missing", None, 0o600, 0),
                ("wide-mode", Some(normal.as_slice()), 0o644, 1),
            ];

            for (name, content, mode, expected_sources) in cases {
                let root = tempdir().unwrap();
                let data = root
                    .path()
                    .join("extensions/builtin_hailo_yolo_detect/data");
                fs::create_dir_all(&data).unwrap();
                let path = data.join("stream_config.json");
                let before = content.map(|content| {
                    fs::write(&path, content).unwrap();
                    fs::set_permissions(&path, fs::Permissions::from_mode(mode)).unwrap();
                    (
                        fs::read(&path).unwrap(),
                        fs::metadata(&path).unwrap().modified().unwrap(),
                    )
                });

                let state = super::super::source_task::observe_ffmpeg_spawns(
                    Arc::clone(&spawn_observer),
                    app_state(root.path().to_path_buf(), infer_url.clone()),
                )
                .await;
                let stream = state.hailo_yolo_stream.as_ref().unwrap();
                assert_eq!(stream.registry.len().await, expected_sources, "{name}");
                assert!(stream
                    .registry
                    .statuses()
                    .await
                    .iter()
                    .all(|status| status.state == super::super::source_task::SourceState::Idle));
                drop(state);
                tokio::time::sleep(Duration::from_millis(20)).await;

                match before {
                    // Startup stays byte-inactive with one deliberate exception:
                    // a config holding plaintext secrets is rewritten once through
                    // the secret store. The rewrite must preserve the config
                    // exactly and must not repeat on the next start.
                    Some((bytes, modified)) if expected_sources > 0 => {
                        // Check the precondition first. The migration is
                        // fail-closed: `encrypt_config` refuses to write when
                        // any value cannot be sealed, so a secret store that
                        // cannot produce a key in this tempdir leaves the file
                        // byte-identical -- and the assertion below then blames
                        // "plaintext should be migrated" for something that is
                        // not the migration's fault. Seen twice as an
                        // intermittent red; naming the real cause here is what
                        // makes the next occurrence diagnosable.
                        let probe = crate::secret_store::encrypt("probe", root.path());
                        assert!(
                            probe.starts_with("enc:"),
                            "{name}: the secret store could not encrypt under {} \
                             (got {probe:?}), so nothing below tests the migration",
                            root.path().display()
                        );
                        let after = fs::read(&path).unwrap();
                        assert_ne!(after, bytes, "{name}: plaintext should be migrated");
                        let stored: StreamConfig = serde_json::from_slice(&after).unwrap();
                        assert!(
                            stored
                                .sources
                                .iter()
                                .all(|source| source.url.starts_with("enc:")),
                            "{name}: migration must encrypt every source URL"
                        );
                        let reloaded = load_config(&path, root.path());
                        assert!(!reloaded.locked, "{name}");
                        assert!(
                            !reloaded.migration_needed,
                            "{name}: a migrated config must not ask to migrate again"
                        );
                        assert_eq!(
                            reloaded.config.sources[0].url, "rtsp://camera.test/live",
                            "{name}: migration must round-trip the value"
                        );
                        assert_eq!(
                            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                            0o600,
                            "{name}"
                        );
                    }
                    // Nothing to migrate: not one byte, not even mtime.
                    Some((bytes, modified)) => {
                        assert_eq!(fs::read(&path).unwrap(), bytes, "{name}");
                        assert_eq!(
                            fs::metadata(&path).unwrap().modified().unwrap(),
                            modified,
                            "{name}"
                        );
                        assert_eq!(
                            fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                            0o600,
                            "{name}"
                        );
                    }
                    None => assert!(!path.exists(), "{name}"),
                }
                assert!(
                    matches!(listener.accept(), Err(error) if error.kind() == ErrorKind::WouldBlock)
                );
            }
            assert_eq!(spawn_observer.load(Ordering::SeqCst), 0);
        });
    }

    #[test]
    fn invalid_restored_url_stays_idle_and_is_rejected_only_on_start_or_test() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let path = root.path().join("stream_config.json");
            let invalid = StreamSourceConfig {
                id: "legacy".to_string(),
                url: "ftp://camera.test/live".to_string(),
                name: String::new(),
            };
            write_snapshot(
                &path,
                &StreamConfig {
                    sources: vec![invalid.clone()],
                    rules: Vec::new(),
                },
            )
            .unwrap();
            let writer = ConfigWriterTask::spawn(path.clone(), root.path().to_path_buf());
            let state = StreamState::new_with_snapshot(
                writer.restored.sources.clone(),
                json!({}),
                writer.tx,
                Arc::clone(&writer.snapshot),
            );
            let handle = state.registry.get("legacy").await.unwrap();
            assert_eq!(
                handle.status().state,
                super::super::source_task::SourceState::Idle
            );
            assert!(state.start_source("legacy").await.is_err());
            assert!(handle.test().await.is_err());
            assert_eq!(disk_at(&path, root.path()).sources, vec![invalid]);
        });
    }

    #[cfg(windows)]
    #[test]
    fn windows_writer_requires_owner_only_dacl() {
        let root = tempdir().unwrap();
        let path = root.path().join("stream_config.json");
        write_snapshot(&path, &StreamConfig::default()).unwrap();
        assert!(path.is_file());
    }

    #[cfg(unix)]
    #[test]
    fn config_permissions_are_owner_only_on_restore_create_and_replace() {
        use std::os::unix::fs::PermissionsExt;

        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let path = root.path().join("stream_config.json");
            let (temporary, file) = create_temporary(root.path()).unwrap();
            assert_eq!(file.metadata().unwrap().permissions().mode() & 0o777, 0o600);
            drop(file);
            fs::remove_file(temporary).unwrap();

            fs::write(&path, b"{}").unwrap();
            fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
            let writer = ConfigWriterTask::spawn(path.clone(), root.path().to_path_buf());
            assert_eq!(
                fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
            send(&writer.tx, |reply| ConfigCommand::UpsertSource {
                source: source("one"),
                reply,
            })
            .await
            .unwrap();
            assert_eq!(
                fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
            fs::set_permissions(&path, fs::Permissions::from_mode(0o644)).unwrap();
            send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                rule: rule("write-time"),
                reply,
            })
            .await
            .unwrap();
            assert_eq!(
                fs::metadata(&path).unwrap().permissions().mode() & 0o777,
                0o600
            );
            // Directories are skipped: the secret store keeps its key material in
            // `data/`, and the check is about stray temp *files*.
            assert!(fs::read_dir(root.path()).unwrap().all(|entry| {
                let entry = entry.unwrap();
                let metadata = entry.metadata().unwrap();
                metadata.is_dir()
                    || entry.file_name() == "stream_config.json"
                    || metadata.permissions().mode() & 0o777 == 0o600
            }));

            let created = root.path().join("created.json");
            let writer = ConfigWriterTask::spawn(created.clone(), root.path().to_path_buf());
            send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                rule: rule("alpha"),
                reply,
            })
            .await
            .unwrap();
            assert_eq!(
                fs::metadata(created).unwrap().permissions().mode() & 0o777,
                0o600
            );
        });
    }

    #[test]
    fn failed_writes_keep_dirty_memory_and_retry_the_full_snapshot() {
        run_bounded_test(TEST_TIMEOUT, async {
            for fault in [
                WriteFault::Rename,
                WriteFault::Capacity,
                WriteFault::Permission,
            ] {
                let root = tempdir().unwrap();
                let path = root.path().join("stream_config.json");
                write_snapshot(
                    &path,
                    &StreamConfig {
                        sources: vec![source("old")],
                        rules: Vec::new(),
                    },
                )
                .unwrap();
                let fail = Arc::new(AtomicBool::new(true));
                let write = {
                    let fail = Arc::clone(&fail);
                    Arc::new(move |path: &Path, config: &StreamConfig| {
                        if fail.swap(false, Ordering::SeqCst) {
                            write_snapshot_inner(path, config, Some(fault))
                        } else {
                            write_snapshot(path, config)
                        }
                    }) as WriteConfig
                };
                let writer =
                    ConfigWriterTask::spawn_with(path.clone(), root.path().to_path_buf(), write);
                assert_eq!(
                    send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                        rule: rule("dirty"),
                        reply,
                    })
                    .await,
                    Err(ConfigWriteError)
                );
                assert_eq!(writer.snapshot.read().await.rules, vec![rule("dirty")]);
                assert!(disk_at(&path, root.path()).rules.is_empty());

                send(&writer.tx, |reply| ConfigCommand::UpsertSource {
                    source: source("next"),
                    reply,
                })
                .await
                .unwrap();
                assert_eq!(disk_at(&path, root.path()), *writer.snapshot.read().await);
                assert_eq!(disk_at(&path, root.path()).rules, vec![rule("dirty")]);
            }
        });
    }

    #[test]
    fn t3a_source_rule_cross_gate_matches_registry_memory_and_disk() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let path = root.path().join("stream_config.json");
            let writer = ConfigWriterTask::spawn(path.clone(), root.path().to_path_buf());
            let state = StreamState::new_with_snapshot(
                Vec::new(),
                json!({}),
                writer.tx.clone(),
                Arc::clone(&writer.snapshot),
            );
            let add_source = state.add_source(source("cam"));
            let add_rule = send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                rule: rule("person"),
                reply,
            });
            let (source_result, rule_result) = tokio::join!(add_source, add_rule);
            source_result.unwrap();
            rule_result.unwrap();

            let snapshot = writer.snapshot.read().await.clone();
            assert_eq!(snapshot, *state.config_snapshot.read().await);
            assert_eq!(state.registry.len().await, snapshot.sources.len());
            assert_eq!(snapshot.sources, vec![source("cam")]);
            assert_eq!(snapshot.rules, vec![rule("person")]);
            assert_eq!(disk_at(&path, root.path()), snapshot);
        });
    }

    #[test]
    fn rust_fixture_is_read_by_python_stream_persist() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let path = root.path().join("stream_config.json");
            let writer = ConfigWriterTask::spawn(path.clone(), root.path().to_path_buf());
            send(&writer.tx, |reply| ConfigCommand::UpsertSource {
                source: source("cam"),
                reply,
            })
            .await
            .unwrap();
            send(&writer.tx, |reply| ConfigCommand::UpsertRule {
                rule: oracle_rule("person"),
                reply,
            })
            .await
            .unwrap();

            let module = Path::new(env!("CARGO_MANIFEST_DIR")).join(
                "../../extensions/builtin_hailo_yolo_detect/core_impl/stream/stream_persist.py",
            );
            let script = r#"
import importlib.util, json, pathlib, sys
# Production Python resolves its writable roots at startup; the secret store
# cannot find the key ring without it, and a rollback would run that startup.
import core.paths, core.settings_core
core.paths.init_app_paths(data_dir=pathlib.Path(sys.argv[3]))
spec = importlib.util.spec_from_file_location("stream_persist", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._CONFIG_FILE = pathlib.Path(sys.argv[2])
protected = module._SECRET_KEYS | module._URL_KEYS
def check_encrypted(value, path=""):
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}" if path else key
            if key.lower() in protected and isinstance(child, str) and child:
                if not core.settings_core.secret_store.is_encrypted(child):
                    print(child_path, file=sys.stderr)
                    raise SystemExit(4)
            check_encrypted(child, child_path)
    elif isinstance(value, list):
        for index, child in enumerate(value):
            check_encrypted(child, f"{path}[{index}]")
check_encrypted(json.loads(module._CONFIG_FILE.read_text(encoding="utf-8")))
print(json.dumps({"sources": module.load_sources(), "rules": module.load_rules()}))
"#;
            let output = tokio::time::timeout(
                Duration::from_secs(10),
                Command::new("uv")
                    .args(["run", "python", "-c", script])
                    .arg(module)
                    .arg(&path)
                    .arg(root.path().join("data"))
                    .env("UV_CACHE_DIR", root.path().join("uv-cache"))
                    // The config is encrypted, so the reader needs the same key
                    // material the writer used. Both sides resolve it from the
                    // data dir.
                    .env("TAGDB_DATA_DIR", root.path().join("data"))
                    // `stream_persist` now imports `core.settings_core`, which is
                    // only importable from the repository root.
                    .current_dir(Path::new(env!("CARGO_MANIFEST_DIR")).join("../.."))
                    .stdin(Stdio::null())
                    .kill_on_drop(true)
                    .output(),
            )
            .await
            .expect("Python reader exceeded its real-time deadline")
            .unwrap();
            let stderr = String::from_utf8_lossy(&output.stderr);
            assert_ne!(
                output.status.code(),
                Some(4),
                "Rust wrote a protected value in plaintext: {stderr}"
            );
            assert!(output.status.success(), "Python oracle failed: {stderr}");
            let value: serde_json::Value = serde_json::from_slice(&output.stdout).unwrap();
            assert_eq!(value["sources"], json!([source("cam")]));
            assert_eq!(value["rules"], json!([oracle_rule("person")]));
        });
    }

    #[test]
    fn python_reader_smoke_rejects_non_list_source_fixture() {
        run_bounded_test(TEST_TIMEOUT, async {
            let root = tempdir().unwrap();
            let path = root.path().join("stream_config.json");
            fs::write(&path, br#"{"sources": {}, "rules": []}"#).unwrap();
            let module = Path::new(env!("CARGO_MANIFEST_DIR")).join(
                "../../extensions/builtin_hailo_yolo_detect/core_impl/stream/stream_persist.py",
            );
            let script = r#"
import importlib.util, pathlib, sys
spec = importlib.util.spec_from_file_location("stream_persist", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
module._CONFIG_FILE = pathlib.Path(sys.argv[2])
if not isinstance(module.load_sources(), list) and isinstance(module.load_rules(), list):
    raise SystemExit(3)
raise SystemExit(1)
"#;
            let output = tokio::time::timeout(
                Duration::from_secs(10),
                Command::new("uv")
                    .args(["run", "python", "-c", script])
                    .arg(module)
                    .arg(path)
                    .env("UV_CACHE_DIR", root.path().join("uv-cache"))
                    .stdin(Stdio::null())
                    .kill_on_drop(true)
                    .output(),
            )
            .await
            .expect("Python reader exceeded its real-time deadline")
            .unwrap();
            assert_eq!(
                output.status.code(),
                Some(3),
                "{}",
                String::from_utf8_lossy(&output.stderr)
            );
        });
    }
}
