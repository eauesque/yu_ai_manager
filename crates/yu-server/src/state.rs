use std::collections::{HashMap, HashSet};
use std::path::PathBuf;
use std::str::FromStr;
use std::sync::{Arc, Mutex};

use minijinja::Environment;
use sqlx::sqlite::{SqliteConnectOptions, SqliteJournalMode, SqlitePoolOptions, SqliteSynchronous};

use crate::auth::{PinRateLimiter, QuickLock};
use crate::groups_index::GroupsIndexCache;
use crate::jobs::JobManager;
use crate::logs::LogRingBuffer;
use crate::mcp::session::McpSessionStore;
use crate::sse::SseHub;
use crate::watcher::ScanWatcher;
use sqlx::SqlitePool;

/// Short-lived TTL cache for expensive read-side aggregation queries (stats,
/// checkpoint lists). Holds the lock during recompute, so a TTL expiry under
/// concurrent requests naturally single-flights instead of stampeding the DB.
pub struct TtlCache<T: Clone> {
    ttl: std::time::Duration,
    inner: tokio::sync::Mutex<Option<(std::time::Instant, T)>>,
}

/// TTL for `stats_basic_cache` / `stats_models_cache` / `checkpoints_cache`.
pub const STATS_CACHE_TTL: std::time::Duration = std::time::Duration::from_secs(60);
pub const CLIP_RUNTIME_CACHE_TTL: std::time::Duration = std::time::Duration::from_secs(300);

impl<T: Clone> TtlCache<T> {
    pub fn new(ttl: std::time::Duration) -> Self {
        Self {
            ttl,
            inner: tokio::sync::Mutex::new(None),
        }
    }

    pub async fn get_or_try_insert_with<E, F, Fut>(&self, f: F) -> Result<T, E>
    where
        F: FnOnce() -> Fut,
        Fut: std::future::Future<Output = Result<T, E>>,
    {
        Ok(self.get_or_try_insert_with_status(f).await?.0)
    }

    /// Same as `get_or_try_insert_with`, but also reports whether the value
    /// came from cache (`true`, so may be up to `ttl` old) or was just
    /// recomputed (`false`, fresh as of this call). Callers that bundle
    /// several cached aggregates into one response (see stats.rs's
    /// `build_stats_all`) need this to report an honest `_stale` flag
    /// instead of claiming every response is current.
    pub async fn get_or_try_insert_with_status<E, F, Fut>(&self, f: F) -> Result<(T, bool), E>
    where
        F: FnOnce() -> Fut,
        Fut: std::future::Future<Output = Result<T, E>>,
    {
        let mut guard = self.inner.lock().await;
        if let Some((at, value)) = guard.as_ref() {
            if at.elapsed() < self.ttl {
                return Ok((value.clone(), true));
            }
        }
        let value = f().await?;
        *guard = Some((std::time::Instant::now(), value.clone()));
        Ok((value, false))
    }

    /// Invalidates a cached aggregate after a successful write operation.
    pub async fn invalidate(&self) {
        *self.inner.lock().await = None;
    }
}

/// Startup configuration derived from CLI args / env.
pub struct Config {
    #[allow(dead_code)]
    pub db_path: String,
    pub pin_hash: String,
    pub valid_token: String,
    pub secret: String,
    pub trusted_proxy_enabled: bool,
    pub trusted_ips: HashSet<String>,
    pub trusted_peer_ips: HashSet<String>,
    pub quick_lock_enabled: bool,
    pub pin_auth_enabled: bool,
    /// Minimum PIN length (default 4).
    pub min_pin_length: usize,
    /// Base URL of the Python backend for unimplemented route fallback.
    pub python_url: String,
    /// Config file path used by Python's --config / YU_CONFIG fallback chain.
    pub config_path: PathBuf,
    /// Repository root used for docs and UI filesystem lookups.
    pub project_root: PathBuf,
    /// Startup application config, matching Python app_runtime_state.get_config().
    pub app_config: serde_json::Value,
    /// Cache directory matching Python TAGDB_CACHE_DIR / ./cache resolution.
    pub cache_dir: PathBuf,
    /// Server mode resolved from CLI > env > config. Values: "full" | "gateway" | "server".
    pub server_mode: String,
    /// Headless mode (no UI server). Populated from --headless CLI flag.
    pub headless: bool,
    /// Safe mode (--safe-mode flag). Disables all subsystems/bg-tasks.
    pub safe_mode: bool,
    /// Standalone mode without the Python backend.
    pub standalone: bool,
    pub infer_standalone: bool,
    /// Python 実行ファイルパス（scan worker 起動用）。
    pub python_executable: String,
    /// Enable Rust-native MCP transport. Set YU_MCP_NATIVE=true to activate.
    pub mcp_native: bool,
    /// Active profile name resolved from --profile / YU_PROFILE / config["active_profile"].
    pub active_profile: Option<String>,
    /// Render the WSJ-skin boss-mode camouflage login/lock gate instead of the
    /// plain PIN/lock page. Default true; see TAGDB_PIN_BOSS_LOGIN_UI.
    pub pin_boss_login_ui: bool,
}

/// Startup coherence check for the LAN Cowork native daemon flag. This remains
/// in use until main.rs switches to [`resolve_native_daemon`]. `native_daemon`
/// requires `standalone`: in hybrid mode the Python backend owns the daemon and a
/// second Rust daemon would split-brain the shared registry/socket (spec §3.2).
/// Pure so it is unit-testable; main.rs turns `Err` into a fatal exit.
pub fn native_daemon_startup_check(
    native_daemon: bool,
    standalone: bool,
) -> Result<(), &'static str> {
    if native_daemon && !standalone {
        return Err("--native-daemon requires --standalone (or YU_STANDALONE)");
    }
    Ok(())
}

/// Resolves native-daemon activation with CLI > config > env precedence, defaulting
/// to disabled when no source opts in. An explicit config `false` beats env so a
/// WebUI opt-out cannot be overridden by a stale dotenv value. In hybrid mode,
/// config is ignored and an enabled CLI flag or environment value is fatal.
pub fn resolve_native_daemon(
    standalone: bool,
    cli_on: bool,
    cli_off: bool,
    config: Option<bool>,
    env: Option<bool>,
) -> Result<bool, &'static str> {
    if cli_off {
        return Ok(false);
    }
    if !standalone {
        return if cli_on || env == Some(true) {
            Err("--native-daemon / YU_LAN_COWORK_NATIVE_DAEMON=1 requires --standalone (or YU_STANDALONE)")
        } else {
            Ok(false)
        };
    }
    if cli_on {
        return Ok(true);
    }
    Ok(config.or(env).unwrap_or(false))
}

pub struct AppState {
    pub config: Config,
    /// Actual listener port after CLI/environment overrides.
    pub effective_port: u16,
    /// Serializes read-modify-write operations on `config.json`.
    ///
    /// yu-server handlers and the lan-cowork crate share this same `Arc`. Because
    /// both write the same `config.json`, they must use a single lock.
    pub settings_lock: Arc<tokio::sync::Mutex<()>>,
    /// Serializes the scan-roots-changed notification sent to yu-infer.
    ///
    /// Each notify reads config.json fresh, so overlapping sends without this
    /// lock can arrive at yu-infer out of order (fire-and-forget over HTTP,
    /// no ordering guarantee) and let an older read overwrite a newer one.
    /// Holding this for the read+send keeps our own sends ordered, and each
    /// holder re-reads disk right before sending, so no send we START is
    /// ever staler than the one before it. It does NOT protect against a
    /// send we gave up on (see `infer_client::InferClient::scan_roots_changed`'s
    /// `generation` parameter) still landing late server-side after a newer
    /// one -- that is the receiver's job, and the pinned `yu-hailo-infer`
    /// does it: it keeps the highest generation it applied and drops anything
    /// not strictly newer.
    pub infer_notify_lock: Arc<tokio::sync::Mutex<()>>,
    /// Monotonic counter for `infer_notify_lock`'s `generation` field, see above.
    pub scan_roots_generation: std::sync::atomic::AtomicU64,
    pub db: SqlitePool,
    pub db_read: SqlitePool,
    /// Write pool for Python-compatible `vectors.db`, stored next to `tags.db`.
    pub vectors_db: SqlitePool,
    /// Read pool for Python-compatible `vectors.db`.
    pub vectors_db_read: SqlitePool,
    /// Native persistent CLIP ANN index, independent from Python FAISS files.
    pub clip_index: Arc<crate::routes::clip_index::ClipIndex>,
    /// Background job state for native CLIP image indexing.
    pub clip_indexer: Arc<crate::routes::clip_indexer::ClipIndexer>,
    /// Background job state for native VLM captioning.
    pub caption_runner: Arc<crate::routes::caption_runner::CaptionRunner>,
    /// Background job state for native speech2text batch transcription.
    pub s2t_runner: Arc<crate::routes::s2t_runner::S2tRunner>,
    pub inference_client: reqwest::Client,
    /// Gateway API keys (`gateway.auth.api_keys`), decrypted once at startup.
    /// Separate from the app's own `api_keys`; see [`crate::auth::gateway`].
    /// Adding or revoking a gateway key requires a restart.
    pub gateway_keys: Vec<crate::auth::gateway::GatewayKey>,
    /// `gateway.auth.allow_loopback_bypass` (default true).
    pub gateway_loopback_bypass: bool,
    pub python_client: reqwest::Client,
    pub quick_lock: QuickLock,
    pub rate_limiter: PinRateLimiter,
    pub groups_index_cache: GroupsIndexCache,
    /// "<METHOD> <path>" -> hit count for requests served via the Python fallback.
    pub proxy_hits: Mutex<HashMap<String, u64>>,
    /// Per-IP open-connection counter for the LAN Cowork fleet log SSE stream
    /// (`/ext/lan_cowork/fleet/logs/stream`). Deliberately independent from
    /// `log_ring`'s own per-IP budget for core's `/api/logs/stream` — the two
    /// routes have separate resource-exhaustion surfaces (see design decision
    /// alongside `LanCoworkHost::register_log_stream_connection`).
    pub fleet_log_stream_connections: Mutex<HashMap<String, usize>>,
    pub sse_hub: Arc<SseHub>,
    pub log_ring: Arc<LogRingBuffer>,
    pub mcp_sessions: Arc<McpSessionStore>,
    pub job_manager: Arc<JobManager>,
    pub watcher: Arc<ScanWatcher>,
    pub approval_gate: Mutex<crate::approval_gate::ApprovalGate>,
    pub env: Environment<'static>,
    pub dist_v: String,
    pub version: String,
    pub start_time: std::time::Instant,
    pub scheduler_state: std::sync::OnceLock<Arc<crate::scheduler::SchedulerState>>,
    /// Loaded WD engines, keyed by cache directory plus a fingerprint of
    /// the resolved profile. Keyed rather than a single slot because the
    /// engine holds the vocabulary and preprocess recipe, so two profiles
    /// over the same directory are two different engines.
    pub wd_infer: Arc<std::sync::Mutex<HashMap<String, Arc<infer_core::WdInferEngine>>>>,
    pub infer_client: Option<crate::infer_client::InferClient>,
    pub infer_child: Option<Arc<std::sync::Mutex<std::process::Child>>>,
    pub scan_manager: std::sync::OnceLock<Arc<crate::scan_manager::ScanManager>>,
    /// Native stream owners are initialized before the Python-forwarded routes are served.
    pub hailo_yolo_stream: Option<Arc<crate::routes::hailo_yolo_stream::registry::StreamState>>,
    /// TTL caches for expensive read-side aggregation endpoints, to avoid
    /// re-running heavy GROUP BY queries while concurrent writes (e.g. the
    /// NAI bridge image-generation pipeline) hold the DB busy.
    pub stats_basic_cache: TtlCache<serde_json::Value>,
    /// file_count / tag_count / schema_version for `/api/server-info`, mirroring
    /// Python's `_stats_cache` (180s TTL) so the endpoint's frequent settings-page
    /// polling doesn't re-run `COUNT(*)` over a multi-million-row `files` table
    /// on every request.
    pub server_info_stats_cache: TtlCache<(i64, i64, i64)>,
    pub stats_models_cache: TtlCache<serde_json::Value>,
    pub stats_timeline_cache: TtlCache<serde_json::Value>,
    pub stats_resolutions_cache: TtlCache<serde_json::Value>,
    pub checkpoints_cache: TtlCache<serde_json::Value>,
    pub clip_runtime_cache: TtlCache<(i64, i64)>,
}

impl AppState {
    pub async fn new(
        config: Config,
        db: SqlitePool,
        db_read: SqlitePool,
        log_ring: Arc<LogRingBuffer>,
    ) -> Self {
        Self::new_with_infer(config, db, db_read, log_ring, None, None).await
    }

    pub async fn new_with_infer(
        config: Config,
        db: SqlitePool,
        db_read: SqlitePool,
        log_ring: Arc<LogRingBuffer>,
        infer_client: Option<crate::infer_client::InferClient>,
        infer_child: Option<Arc<std::sync::Mutex<std::process::Child>>>,
    ) -> Self {
        let (vectors_db, vectors_db_read) = open_vectors_pools(&config.db_path, None)
            .await
            .expect("failed to connect to vectors database");
        Self::new_with_infer_and_vectors(
            config,
            db,
            db_read,
            vectors_db,
            vectors_db_read,
            log_ring,
            infer_client,
            infer_child,
        )
        .await
    }

    /// Builds application state with explicitly configured vectors.db pools.
    ///
    /// The production constructor supplies the same SQLCipher key as tags.db;
    /// the convenience constructors above deliberately use an unencrypted pool
    /// for existing in-memory test helpers.
    #[allow(clippy::too_many_arguments)]
    pub async fn new_with_infer_and_vectors(
        config: Config,
        db: SqlitePool,
        db_read: SqlitePool,
        vectors_db: SqlitePool,
        vectors_db_read: SqlitePool,
        log_ring: Arc<LogRingBuffer>,
        infer_client: Option<crate::infer_client::InferClient>,
        infer_child: Option<Arc<std::sync::Mutex<std::process::Child>>>,
    ) -> Self {
        let inference_client = reqwest::Client::builder()
            .connect_timeout(std::time::Duration::from_secs(10))
            .build()
            .expect("failed to build inference proxy client");
        let sse_hub = Arc::new(SseHub::new());
        let stream_path = config
            .project_root
            .join("extensions/builtin_hailo_yolo_detect/data/stream_config.json");
        let writer = crate::routes::hailo_yolo_stream::config::ConfigWriterTask::spawn(
            stream_path,
            config.project_root.clone(),
        );
        let mut stream_settings = config
            .app_config
            .pointer("/extensions/builtin-hailo-yolo-detect")
            .cloned()
            .filter(serde_json::Value::is_object)
            .unwrap_or_else(|| serde_json::json!({}));
        if let Some(scan_roots) = config.app_config.get("scan_roots") {
            stream_settings
                .as_object_mut()
                .expect("stream settings were initialized as an object")
                .insert("scan_roots".to_string(), scan_roots.clone());
        }
        let stream_migration_needed = writer.migration_needed;
        let stream_config_tx = writer.tx.clone();
        let stream_state = Arc::new(
            crate::routes::hailo_yolo_stream::registry::StreamState::new_with_snapshot_infer_and_actions(
                writer.restored.sources.clone(),
                stream_settings,
                writer.tx,
                writer.snapshot,
                infer_client.clone(),
                crate::routes::hailo_yolo_stream::actions::ActionExecutor::spawn(
                    config.project_root.clone(),
                    inference_client.clone(),
                    Arc::clone(&sse_hub),
                ),
            ),
        );
        if stream_migration_needed {
            // The stream config still holds secrets in the clear. One no-op write
            // rewrites it through the secret store; a config that is never edited
            // again would otherwise stay plaintext forever.
            tokio::spawn(async move {
                let (reply, done) = tokio::sync::oneshot::channel();
                if stream_config_tx
                    .send(
                        crate::routes::hailo_yolo_stream::registry::ConfigCommand::PersistSnapshot {
                            reply,
                        },
                    )
                    .await
                    .is_err()
                {
                    return;
                }
                match done.await {
                    Ok(Ok(())) => {
                        tracing::info!("migrated stream config secrets to the secret store")
                    }
                    // The plaintext is already on disk, so a failed rewrite exposes
                    // nothing new. Retried on the next start.
                    _ => tracing::warn!(
                        "could not migrate stream config secrets; will retry on next start"
                    ),
                }
            });
        }
        let groups_index_cache = GroupsIndexCache::new(config.cache_dir.clone());
        let template_dir = config.project_root.join("ui/default/templates");
        let mut template_dirs: Vec<std::path::PathBuf> = vec![template_dir];
        if let Ok(entries) = std::fs::read_dir(config.project_root.join("extensions")) {
            let mut ext_dirs: Vec<std::path::PathBuf> = entries
                .flatten()
                .map(|e| e.path().join("templates"))
                .filter(|p| p.is_dir())
                .collect();
            ext_dirs.sort(); // ponytail: 決定的順序。同名テンプレートは先行 dir が優先
            template_dirs.extend(ext_dirs);
        }
        let refs: Vec<&std::path::Path> = template_dirs.iter().map(|p| p.as_path()).collect();
        let env = crate::frontend::init_env(&refs);
        let dist_v = crate::frontend::dist_v(&config.project_root);
        let version = std::fs::read_to_string(config.project_root.join("VERSION"))
            .unwrap_or_else(|_| "0.0.0".to_string())
            .trim()
            .to_string();
        let clip_index = Arc::new(
            crate::routes::clip_index::ClipIndex::new_default(&config.cache_dir)
                .expect("default CLIP index model name is safe"),
        );
        let gateway_auth = crate::auth::gateway::auth_config(&config.app_config);
        let gateway_loopback_bypass = crate::auth::gateway::loopback_bypass_enabled(&gateway_auth);
        let gateway_keys = crate::auth::gateway::load_keys(&gateway_auth, &config.project_root);
        Self {
            config,
            effective_port: 5000,
            settings_lock: Arc::new(tokio::sync::Mutex::new(())),
            infer_notify_lock: Arc::new(tokio::sync::Mutex::new(())),
            scan_roots_generation: std::sync::atomic::AtomicU64::new(0),
            db,
            db_read,
            vectors_db,
            vectors_db_read,
            clip_index,
            clip_indexer: Arc::new(crate::routes::clip_indexer::ClipIndexer::new()),
            caption_runner: Arc::new(crate::routes::caption_runner::CaptionRunner::new()),
            s2t_runner: Arc::new(crate::routes::s2t_runner::S2tRunner::new()),
            inference_client,
            gateway_keys,
            gateway_loopback_bypass,
            python_client: reqwest::Client::builder()
                .redirect(reqwest::redirect::Policy::none())
                .build()
                .expect("failed to build python proxy client"),
            quick_lock: QuickLock::new(),
            rate_limiter: PinRateLimiter::new(),
            groups_index_cache,
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub,
            log_ring,
            mcp_sessions: Arc::new(McpSessionStore::new(
                std::env::var("YU_MCP_MAX_SESSIONS")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(1000_usize)
                    .max(1),
                std::env::var("YU_MCP_MAX_SESSIONS_PER_IP")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(20_usize)
                    .max(1),
                std::env::var("YU_MCP_QUEUE_MAXSIZE")
                    .ok()
                    .and_then(|v| v.parse().ok())
                    .unwrap_or(256_usize)
                    .max(1),
            )),
            job_manager: Arc::new(JobManager::new()),
            watcher: Arc::new(ScanWatcher::new()),
            approval_gate: Mutex::new(crate::approval_gate::ApprovalGate::default()),
            env,
            dist_v,
            version,
            start_time: std::time::Instant::now(),
            scheduler_state: std::sync::OnceLock::new(),
            wd_infer: Arc::new(std::sync::Mutex::new(HashMap::new())),
            infer_client,
            infer_child,
            scan_manager: std::sync::OnceLock::new(),
            hailo_yolo_stream: Some(stream_state),
            stats_basic_cache: TtlCache::new(STATS_CACHE_TTL),
            server_info_stats_cache: TtlCache::new(STATS_CACHE_TTL),
            stats_models_cache: TtlCache::new(STATS_CACHE_TTL),
            stats_timeline_cache: TtlCache::new(STATS_CACHE_TTL),
            stats_resolutions_cache: TtlCache::new(STATS_CACHE_TTL),
            checkpoints_cache: TtlCache::new(STATS_CACHE_TTL),
            clip_runtime_cache: TtlCache::new(CLIP_RUNTIME_CACHE_TTL),
        }
    }

    pub fn with_effective_port(mut self, effective_port: u16) -> Self {
        self.effective_port = effective_port;
        self
    }
}

/// Opens the `vectors.db` pools using the same SQLCipher key handling and
/// WAL/busy-timeout policy as the tags database. Python resolves the vectors
/// database as a sibling of tags.db; keep that rule so both processes share it.
pub async fn open_vectors_pools(
    tags_db_path: &str,
    db_key: Option<&str>,
) -> Result<(SqlitePool, SqlitePool), sqlx::Error> {
    let vectors_path = vectors_db_path(tags_db_path);
    let in_memory = vectors_path == "sqlite::memory:";
    let write_options = vector_connect_options(&vectors_path, db_key, false)?;
    let write_pool = SqlitePoolOptions::new()
        .max_connections(5)
        .after_connect(|connection, _| {
            Box::pin(async move {
                sqlx::query("PRAGMA mmap_size=0")
                    .execute(connection)
                    .await?;
                Ok(())
            })
        })
        .connect_with(write_options)
        .await?;
    ensure_vectors_schema(&write_pool).await?;

    // Existing route tests use `sqlite::memory:` for tags.db. A read-only
    // in-memory SQLite URL cannot be opened as a second connection, so retain
    // the test-isolation convention while production always receives a true
    // read-only vectors.db pool.
    let read_options = vector_connect_options(&vectors_path, db_key, !in_memory)?;
    let read_pool = SqlitePoolOptions::new()
        .max_connections(5)
        .after_connect(|connection, _| {
            Box::pin(async move {
                sqlx::query("PRAGMA mmap_size=0")
                    .execute(connection)
                    .await?;
                Ok(())
            })
        })
        .connect_with(read_options)
        .await?;
    if in_memory {
        ensure_vectors_schema(&read_pool).await?;
    }
    Ok((write_pool, read_pool))
}

fn vectors_db_path(tags_db_path: &str) -> String {
    if tags_db_path == "sqlite::memory:" {
        return tags_db_path.to_string();
    }
    std::path::Path::new(tags_db_path)
        .parent()
        .unwrap_or_else(|| std::path::Path::new("."))
        .join("vectors.db")
        .to_string_lossy()
        .into_owned()
}

fn vector_connect_options(
    vectors_path: &str,
    db_key: Option<&str>,
    read_only: bool,
) -> Result<SqliteConnectOptions, sqlx::Error> {
    let mut options = SqliteConnectOptions::from_str(vectors_path)?
        .journal_mode(SqliteJournalMode::Wal)
        .busy_timeout(std::time::Duration::from_millis(5_000))
        .synchronous(SqliteSynchronous::Normal)
        .foreign_keys(true)
        .pragma("mmap_size", "0")
        .create_if_missing(!read_only);
    if read_only {
        options = options.read_only(true);
    }
    if let Some(key) = db_key.filter(|key| !key.is_empty()) {
        let escaped_key = key.replace('\'', "''");
        options = options
            .pragma("cipher_memory_security", "OFF")
            .pragma("key", format!("'{escaped_key}'"));
    }
    Ok(options)
}

async fn ensure_vectors_schema(pool: &SqlitePool) -> Result<(), sqlx::Error> {
    sqlx::query(
        "CREATE TABLE IF NOT EXISTS file_vectors (\
             file_id INTEGER PRIMARY KEY,\
             model TEXT NOT NULL DEFAULT 'clip_vit_b_16',\
             vector BLOB NOT NULL,\
             created_at INTEGER NOT NULL DEFAULT (strftime('%s','now'))\
         )",
    )
    .execute(pool)
    .await?;
    sqlx::query("CREATE INDEX IF NOT EXISTS idx_file_vectors_model ON file_vectors(model)")
        .execute(pool)
        .await?;
    Ok(())
}

/// Thread-safe shared state passed through axum extensions.
pub type SharedState = Arc<AppState>;

/// Minimal authenticated state shared by native semantic-search route tests.
/// The handlers under test reject before touching the incomplete test schema,
/// which keeps these checks focused on the mandatory admin gate.
#[cfg(test)]
pub(crate) async fn semantic_test_state(pin_auth_enabled: bool) -> SharedState {
    semantic_test_state_with(pin_auth_enabled, String::new()).await
}

/// Same as [`semantic_test_state`] but lets a test set `python_url`, which is the
/// only signal distinguishing standalone from hybrid mode.
#[cfg(test)]
pub(crate) async fn semantic_test_state_with(
    pin_auth_enabled: bool,
    python_url: String,
) -> SharedState {
    semantic_test_state_with_root(pin_auth_enabled, python_url, PathBuf::from(".")).await
}

/// Builds semantic test state with its immutable project root injected before
/// the state is shared through `Arc`.
#[cfg(test)]
pub(crate) async fn semantic_test_state_with_root(
    pin_auth_enabled: bool,
    python_url: String,
    project_root: PathBuf,
) -> SharedState {
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    let pool = SqlitePoolOptions::new()
        .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
        .await
        .unwrap();
    Arc::new(
        AppState::new(
            Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,

                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: true,
                pin_auth_enabled,
                min_pin_length: 4,
                python_url,
                config_path: project_root.join("config.json"),
                project_root,
                app_config: serde_json::json!({}),
                cache_dir: PathBuf::from("."),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                standalone: false,
                infer_standalone: true,
                python_executable: String::new(),
                mcp_native: false,
                active_profile: None,
            },
            pool.clone(),
            pool,
            Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
        )
        .await,
    )
}

#[cfg(test)]
mod ttl_cache_tests {
    use super::{open_vectors_pools, TtlCache};
    use std::sync::atomic::{AtomicUsize, Ordering};
    use std::sync::Arc;

    #[tokio::test]
    async fn hit_within_ttl_does_not_recompute() {
        let cache = TtlCache::new(std::time::Duration::from_millis(200));
        let calls = Arc::new(AtomicUsize::new(0));

        let c = calls.clone();
        let first: Result<i32, ()> = cache
            .get_or_try_insert_with(|| async move {
                c.fetch_add(1, Ordering::SeqCst);
                Ok(1)
            })
            .await;
        assert_eq!(first, Ok(1));

        let c = calls.clone();
        let second: Result<i32, ()> = cache
            .get_or_try_insert_with(|| async move {
                c.fetch_add(1, Ordering::SeqCst);
                Ok(2)
            })
            .await;
        assert_eq!(second, Ok(1)); // stale cached value returned, closure not re-run
        assert_eq!(calls.load(Ordering::SeqCst), 1);
    }

    #[tokio::test]
    async fn recomputes_after_ttl_expiry() {
        let cache = TtlCache::new(std::time::Duration::from_millis(10));
        let calls = Arc::new(AtomicUsize::new(0));

        let c = calls.clone();
        let first: Result<i32, ()> = cache
            .get_or_try_insert_with(|| async move {
                c.fetch_add(1, Ordering::SeqCst);
                Ok(1)
            })
            .await;
        assert_eq!(first, Ok(1));

        tokio::time::sleep(std::time::Duration::from_millis(30)).await;

        let c = calls.clone();
        let second: Result<i32, ()> = cache
            .get_or_try_insert_with(|| async move {
                c.fetch_add(1, Ordering::SeqCst);
                Ok(2)
            })
            .await;
        assert_eq!(second, Ok(2));
        assert_eq!(calls.load(Ordering::SeqCst), 2);
    }

    #[tokio::test]
    async fn error_is_not_cached() {
        let cache = TtlCache::new(std::time::Duration::from_secs(60));
        let calls = Arc::new(AtomicUsize::new(0));

        let c = calls.clone();
        let first: Result<i32, &'static str> = cache
            .get_or_try_insert_with(|| async move {
                c.fetch_add(1, Ordering::SeqCst);
                Err("boom")
            })
            .await;
        assert_eq!(first, Err("boom"));

        let c = calls.clone();
        let second: Result<i32, &'static str> = cache
            .get_or_try_insert_with(|| async move {
                c.fetch_add(1, Ordering::SeqCst);
                Ok(42)
            })
            .await;
        assert_eq!(second, Ok(42));
        assert_eq!(calls.load(Ordering::SeqCst), 2); // retried, not poisoned by prior error
    }

    #[tokio::test]
    async fn vectors_pools_use_tags_db_sibling_path() {
        let root = tempfile::tempdir().unwrap();
        let tags_db = root.path().join("tags.db");
        let (write, read) = open_vectors_pools(tags_db.to_str().unwrap(), None)
            .await
            .unwrap();
        sqlx::query("INSERT INTO file_vectors(file_id, model, vector) VALUES (1, 'test', X'0000')")
            .execute(&write)
            .await
            .unwrap();
        let count: i64 = sqlx::query_scalar("SELECT COUNT(*) FROM file_vectors")
            .fetch_one(&read)
            .await
            .unwrap();
        assert_eq!(count, 1);
        assert!(root.path().join("vectors.db").exists());
    }
}

#[cfg(test)]
mod native_daemon_tests {
    use super::{native_daemon_startup_check, resolve_native_daemon};

    #[test]
    fn native_daemon_requires_standalone() {
        assert!(native_daemon_startup_check(false, false).is_ok());
        assert!(native_daemon_startup_check(false, true).is_ok());
        assert!(native_daemon_startup_check(true, true).is_ok());
        assert!(native_daemon_startup_check(true, false).is_err());
    }

    #[test]
    fn resolve_native_daemon_truth_table() {
        let cases = [
            (true, false, true, Some(true), Some(true), Ok(false)),
            (true, true, false, Some(false), Some(false), Ok(true)),
            (true, false, false, Some(true), Some(false), Ok(true)),
            (true, false, false, Some(false), Some(true), Ok(false)),
            (true, false, false, None, Some(true), Ok(true)),
            (true, false, false, None, Some(false), Ok(false)),
            (true, false, false, None, None, Ok(false)),
            (false, false, true, Some(true), Some(true), Ok(false)),
            (
                false,
                true,
                false,
                Some(false),
                Some(false),
                Err("--native-daemon / YU_LAN_COWORK_NATIVE_DAEMON=1 requires --standalone (or YU_STANDALONE)"),
            ),
            (
                false,
                false,
                false,
                Some(true),
                Some(true),
                Err("--native-daemon / YU_LAN_COWORK_NATIVE_DAEMON=1 requires --standalone (or YU_STANDALONE)"),
            ),
            (false, false, false, Some(true), Some(false), Ok(false)),
            (false, false, false, Some(true), None, Ok(false)),
            (true, true, true, Some(false), Some(true), Ok(false)),
        ];

        for (standalone, cli_on, cli_off, config, env, expected) in cases {
            assert_eq!(
                resolve_native_daemon(standalone, cli_on, cli_off, config, env),
                expected
            );
        }
    }
}
