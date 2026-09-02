use axum::{
    body::Bytes,
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use std::{collections::BTreeMap, sync::Arc};

use serde_json::{json, Value};
use sqlx::Row;
use tokio::sync::Mutex;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    routes::peer_identity::{derive_peer_id_from_seed, local_peer_id},
    state::SharedState,
};

#[derive(Clone)]
pub(crate) struct ResolvedTaggerPeer {
    pub peer_id: String,
    pub name: String,
    pub is_local: bool,
    pub transport: Option<crate::tagger_peer_client::TaggerPeer>,
}

pub(crate) async fn resolve_tagger_peers(
    state: &SharedState,
) -> Result<Vec<ResolvedTaggerPeer>, sqlx::Error> {
    let mut resolved = Vec::new();
    for peer in crate::routes::mesh_inference::peers(state).await? {
        let Some(types) = peer.get("inference_types").and_then(Value::as_array) else {
            continue;
        };
        let disabled = peer
            .get("disabled_types")
            .and_then(Value::as_array)
            .is_some_and(|types| types.iter().any(|value| value == "tagger"));
        if disabled || !types.iter().any(|value| value == "tagger") {
            continue;
        }
        let Some(peer_id) = peer.get("peer_id").and_then(Value::as_str) else {
            continue;
        };
        let name = peer
            .get("name")
            .and_then(Value::as_str)
            .unwrap_or(peer_id)
            .to_owned();
        if peer
            .get("is_local")
            .and_then(Value::as_bool)
            .unwrap_or(false)
        {
            resolved.push(ResolvedTaggerPeer {
                peer_id: peer_id.to_owned(),
                name,
                is_local: true,
                transport: None,
            });
            continue;
        }
        let Some(row) = sqlx::query("SELECT api_host, api_port, token FROM peers WHERE peer_id = ? AND last_reached_at IS NOT NULL").bind(peer_id).fetch_optional(&state.db_read).await? else { continue; };
        let host = row.get::<Option<String>, _>("api_host").unwrap_or_default();
        let port = row.get::<Option<i64>, _>("api_port").unwrap_or(0);
        let token = row.get::<Option<String>, _>("token").unwrap_or_default();
        if host.is_empty() || !(1..=i64::from(u16::MAX)).contains(&port) {
            continue;
        }
        resolved.push(ResolvedTaggerPeer {
            peer_id: peer_id.to_owned(),
            name: name.clone(),
            is_local: false,
            transport: Some(crate::tagger_peer_client::TaggerPeer {
                peer_id: peer_id.to_owned(),
                name,
                api_host: host,
                // The `(1..=u16::MAX)` check above already rejected anything else.
                api_port: u16::try_from(port).unwrap_or(0),
                token,
            }),
        });
    }
    Ok(resolved)
}

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.entry("ok".to_string()).or_insert(Value::Bool(true));
    body.entry("error".to_string()).or_insert(Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(message: &str) -> Response {
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": message})),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn online_peer_rows(
    state: &SharedState,
) -> Result<Vec<sqlx::sqlite::SqliteRow>, sqlx::Error> {
    // The Python mesh registry owns live mDNS/runtime capability updates. Rust
    // reads the persisted table only, so liveness is as fresh as last_reached_at.
    sqlx::query(
        "SELECT peer_id, name
         FROM peers
         WHERE last_reached_at IS NOT NULL
         ORDER BY peer_id",
    )
    .fetch_all(&state.db_read)
    .await
}

fn hostname() -> String {
    std::env::var("HOSTNAME")
        .ok()
        .filter(|value| !value.is_empty())
        .or_else(|| {
            std::fs::read_to_string("/etc/hostname")
                .ok()
                .map(|value| value.trim().to_string())
                .filter(|value| !value.is_empty())
        })
        .unwrap_or_else(|| "localhost".to_string())
}

pub(crate) fn configured_peer_name(state: &SharedState) -> String {
    let configured = state
        .config
        .app_config
        .get("extensions")
        .and_then(|extensions| extensions.get("builtin-lan-cowork"))
        .and_then(|cowork| cowork.get("peer_name"))
        .and_then(Value::as_str)
        .unwrap_or("auto");
    if configured == "auto" {
        hostname()
    } else {
        configured.to_string()
    }
}

pub(crate) fn has_local_tagger_capability(state: &SharedState) -> bool {
    let mut roots = vec![state.config.project_root.join("cache").join("wd_tagger")];
    if let Some(home) = std::env::var_os("HOME") {
        roots.push(
            std::path::PathBuf::from(home)
                .join(".cache")
                .join("yu_ai_manager")
                .join("wd_tagger"),
        );
    }
    roots.into_iter().any(|root| {
        let Ok(entries) = std::fs::read_dir(root) else {
            return false;
        };
        entries.flatten().any(|entry| {
            let path = entry.path();
            path.is_dir() && (path.join("model.hef").exists() || path.join("model.onnx").exists())
        })
    })
}

async fn local_tagger_peer(state: &SharedState) -> Option<Value> {
    if !has_local_tagger_capability(state) {
        return None;
    }
    let peer_id = local_peer_id(&**state).await?;
    Some(json!({
        "peer_id": peer_id,
        "name": configured_peer_name(state),
        "status": "online",
        "is_local": true,
    }))
}

pub async fn list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match online_peer_rows(&state).await {
        Ok(rows) => {
            let mut servers = Vec::new();
            if let Some(local) = local_tagger_peer(&state).await {
                servers.push(json!({
                    "id": local.get("peer_id").and_then(Value::as_str).unwrap_or(""),
                    "name": local.get("name").and_then(Value::as_str).unwrap_or(""),
                    "type": "mesh",
                    "priority": 0,
                    "enabled": true,
                    "status": "online",
                }));
            }
            servers.extend(
                rows.into_iter()
                    .map(|row| {
                        json!({
                            "id": row.try_get::<String, _>("peer_id").unwrap_or_default(),
                            "name": row.try_get::<String, _>("name").unwrap_or_default(),
                            "type": "mesh",
                            "priority": 0,
                            "enabled": true,
                            "status": "online",
                        })
                    })
                    .collect::<Vec<_>>(),
            );
            api_result(json!({"mode": "mesh", "servers": servers}))
        }
        Err(error) => {
            tracing::error!(?error, "failed to list tagger peers");
            api_error("Failed to list tagger servers")
        }
    }
}

pub async fn health(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match online_peer_rows(&state).await {
        Ok(rows) => {
            let mut peers = Vec::new();
            if let Some(local) = local_tagger_peer(&state).await {
                peers.push(local);
            }
            peers.extend(
                rows.into_iter()
                    .map(|row| {
                        json!({
                            "peer_id": row.try_get::<String, _>("peer_id").unwrap_or_default(),
                            "name": row.try_get::<String, _>("name").unwrap_or_default(),
                            "status": "online",
                            "is_local": false,
                        })
                    })
                    .collect::<Vec<_>>(),
            );
            api_result(json!({"peers": peers}))
        }
        Err(error) => {
            tracing::error!(?error, "failed to list tagger peer health");
            api_error("Failed to get tagger server health")
        }
    }
}

pub async fn stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match sqlx::query_scalar::<_, i64>(
        "SELECT COUNT(*)
         FROM files f
         WHERE f.is_deleted = 0
           AND NOT EXISTS (
             SELECT 1 FROM file_hailo_tags h WHERE h.file_id = f.id
           )",
    )
    .fetch_one(&state.db_read)
    .await
    {
        Ok(count) => api_result(json!({"untagged_count": count})),
        Err(error) => {
            tracing::error!(?error, "failed to count untagged files");
            api_error("Failed to get tagger server stats")
        }
    }
}

// ── tagger-servers batch forwarders (no admin scope — mirrors Python) ─────────
//
// PORTING ORDER (measured 2026-08-22): `batch_cancel` must NOT be ported before
// `batch_tag`. Python's cancel reaches `job_manager.cancel_job("tagger_cluster")`
// for a job that Python's `run_tagger_batch` started. The Rust `JobManager`
// (jobs/mod.rs) cancels through an in-process `cancel_token` in its own `jobs`
// map, so while the batch is still started on the Python side a native cancel
// would find nothing, return false, and answer 404 — silently failing to stop a
// job that is really running, where Python stops it.
//
// `batch_tag`'s callee is `core/mesh_inference` (10 files, 928L): it starts a
// coordinator thread that dispatches across LAN peers. Sizing the 3-line handler
// rather than that subsystem is how this looks deceptively small.

const TAGGER_CLUSTER_JOB_ID: &str = "tagger_cluster";
const TAGGER_BATCH_SIZE: usize = 8;
const DEFAULT_TAGGER_THRESHOLD: f64 = 0.35;
const MAX_TAGGER_BATCH: usize = 2000;

fn batch_error(status: StatusCode, message: &str, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}

fn mesh_progress_message(stats: &crate::tagger_batch::BatchStats, total: usize) -> String {
    format!(
        "Tagger mesh: {}/{} (tagged={}, empty={}, errors={})",
        stats.done, total, stats.tagged, stats.empty, stats.errors
    )
}

async fn run_tagger_cluster(
    state: SharedState,
    file_ids: Vec<i64>,
    threshold: f64,
    cancel: tokio_util::sync::CancellationToken,
) {
    if file_ids.is_empty() {
        state.job_manager.finish(
            TAGGER_CLUSTER_JOB_ID,
            Some(json!({"message": "No files to tag"})),
            None,
        );
        return;
    }
    let total = file_ids.len();
    let peers = match resolve_tagger_peers(&state).await {
        Ok(peers) if !peers.is_empty() => peers,
        Ok(_) => {
            state.job_manager.finish(
                TAGGER_CLUSTER_JOB_ID,
                None,
                Some("no_enabled_peers: all tagger peers are disabled".into()),
            );
            return;
        }
        Err(error) => {
            state.job_manager.finish(
                TAGGER_CLUSTER_JOB_ID,
                None,
                Some(format!("Failed to resolve tagger peers: {error}")),
            );
            return;
        }
    };
    let items = match crate::tagger_batch::iter_active_paths(&state.db, &file_ids).await {
        Ok(items) => items,
        Err(error) => {
            state.job_manager.finish(
                TAGGER_CLUSTER_JOB_ID,
                None,
                Some(format!("Failed to resolve tagger paths: {error}")),
            );
            return;
        }
    };
    let stats = Arc::new(Mutex::new(crate::tagger_batch::BatchStats::default()));
    let dropped = Arc::new(Mutex::new(BTreeMap::new()));
    crate::work_steal::work_steal(items, peers, TAGGER_BATCH_SIZE, cancel.clone(), {
        let state = state.clone();
        let stats = stats.clone();
        let dropped = dropped.clone();
        let cancel_for_workers = cancel.clone();
        move |peer, batch| {
            let state = state.clone();
            let stats = stats.clone();
            let dropped = dropped.clone();
            let cancel = cancel_for_workers.clone();
            async move {
                let (batch_stats, batch_dropped) = crate::tagger_batch::run_tagger_batch_worker(
                    &state, &peer, batch, threshold, &cancel,
                )
                .await;
                let mut current = stats.lock().await;
                current.tagged += batch_stats.tagged;
                current.empty += batch_stats.empty;
                current.errors += batch_stats.errors;
                current.done += batch_stats.done;
                let message = mesh_progress_message(&current, total);
                state.job_manager.update_progress(
                    TAGGER_CLUSTER_JOB_ID,
                    current.done as u64,
                    total as u64,
                    Some(message),
                );
                drop(current);
                let mut all_dropped = dropped.lock().await;
                for (reason, count) in batch_dropped {
                    *all_dropped.entry(reason).or_insert(0) += count;
                }
            }
        }
    })
    .await;
    let stats = stats.lock().await;
    let dropped = dropped.lock().await;
    crate::tagger_batch::log_tagger_dropped("Tagger mesh", &dropped);
    let result = Some(json!({
        "tagged": stats.tagged,
        "empty": stats.empty,
        "errors": stats.errors,
    }));
    if cancel.is_cancelled() {
        state
            .job_manager
            .finish_cancelled(TAGGER_CLUSTER_JOB_ID, result);
    } else {
        state
            .job_manager
            .finish(TAGGER_CLUSTER_JOB_ID, result, None);
    }
}

pub async fn batch_tag(State(s): State<SharedState>, body: Bytes) -> Response {
    let payload = serde_json::from_slice::<Value>(&body).unwrap_or(json!({}));
    if !payload.is_object() {
        return batch_error(
            StatusCode::BAD_REQUEST,
            "request body must be an object",
            "invalid_input",
        );
    }
    let limit = match payload.get("limit") {
        Some(value) if value.is_i64() && !value.is_boolean() => value.as_i64().unwrap(),
        Some(_) => {
            return batch_error(
                StatusCode::BAD_REQUEST,
                "limit must be an integer",
                "invalid_value",
            )
        }
        None => 500,
    };
    if !(1..=2000).contains(&limit) {
        return batch_error(
            StatusCode::BAD_REQUEST,
            "limit must be between 1 and 2000",
            "invalid_value",
        );
    }
    let threshold = match payload.get("threshold") {
        None | Some(Value::Null) => DEFAULT_TAGGER_THRESHOLD,
        Some(value) => match value.as_f64() {
            Some(value) if (0.0..=1.0).contains(&value) => value,
            _ => {
                return batch_error(
                    StatusCode::BAD_REQUEST,
                    "threshold must be between 0 and 1",
                    "invalid_value",
                )
            }
        },
    };
    let force = match payload.get("force") {
        None => false,
        Some(value) => match value.as_bool() {
            Some(value) => value,
            None => {
                return batch_error(
                    StatusCode::BAD_REQUEST,
                    "force must be a boolean",
                    "invalid_value",
                )
            }
        },
    };
    let file_ids = match payload.get("file_ids") {
        Some(Value::Array(ids)) => {
            if ids.len() > MAX_TAGGER_BATCH {
                return batch_error(
                    StatusCode::BAD_REQUEST,
                    "file_ids max 2000",
                    "batch_too_large",
                );
            }
            let mut parsed = Vec::with_capacity(ids.len());
            for id in ids {
                let Some(id) = id.as_i64() else {
                    return batch_error(
                        StatusCode::BAD_REQUEST,
                        "file_ids must contain integers",
                        "invalid_input",
                    );
                };
                parsed.push(id);
            }
            if force {
                parsed
            } else {
                match crate::tagger_batch::filter_untagged(&s.db, &parsed).await {
                    Ok(ids) => ids,
                    Err(error) => {
                        return batch_error(
                            StatusCode::INTERNAL_SERVER_ERROR,
                            &format!("Failed to select files: {error}"),
                            "database_error",
                        )
                    }
                }
            }
        }
        Some(_) => {
            return batch_error(
                StatusCode::BAD_REQUEST,
                "file_ids must be a list",
                "invalid_input",
            )
        }
        None => match crate::tagger_batch::get_untagged_file_ids(&s.db, limit).await {
            Ok(ids) => ids,
            Err(error) => {
                return batch_error(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    &format!("Failed to select files: {error}"),
                    "database_error",
                )
            }
        },
    };
    if file_ids.is_empty() {
        return api_result(json!({"started": false, "reason": "no_targets"}));
    }
    let Some(cancel) = s
        .job_manager
        .start_if_idle(TAGGER_CLUSTER_JOB_ID, "Tagger mesh")
    else {
        return batch_error(
            StatusCode::CONFLICT,
            "Tagger batch is already running",
            "job_running",
        );
    };
    tokio::spawn(run_tagger_cluster(s, file_ids, threshold, cancel));
    api_result(json!({"started": true, "job_id": TAGGER_CLUSTER_JOB_ID}))
}

pub async fn batch_cancel(State(s): State<SharedState>, body: Bytes) -> Response {
    let _ = body;
    if !s.job_manager.cancel_job(TAGGER_CLUSTER_JOB_ID) {
        return batch_error(
            StatusCode::NOT_FOUND,
            "No running tagger cluster job",
            "job_not_running",
        );
    }
    api_result(json!({
        "status": "cancelling",
        "message": "Tagger cluster cancel requested"
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{body::to_bytes, extract::State};
    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            r#"CREATE TABLE peers (
               peer_id TEXT PRIMARY KEY,
               name TEXT,
               inference_types TEXT,
               api_host TEXT,
               api_port INTEGER,
               token TEXT,
               token_expires_at INTEGER,
               token_issued_at INTEGER,
               allow_legacy_auth INTEGER NOT NULL DEFAULT 0,
               created_at INTEGER NOT NULL,
               updated_at INTEGER NOT NULL,
               last_reached_at INTEGER,
               last_attempted_at INTEGER
             );
             CREATE TABLE peer_inference_disabled (peer_id TEXT NOT NULL, inference_type TEXT NOT NULL);
             CREATE TABLE files (id INTEGER PRIMARY KEY, is_deleted INTEGER NOT NULL DEFAULT 0);
             CREATE TABLE file_hailo_tags (
               id INTEGER PRIMARY KEY,
               file_id INTEGER NOT NULL,
               tag_name TEXT NOT NULL,
               confidence REAL NOT NULL,
               source TEXT NOT NULL DEFAULT 'hailo_remote',
               created_at INTEGER NOT NULL DEFAULT 0,
               UNIQUE(file_id, tag_name)
             );
             INSERT INTO peers(peer_id, name, inference_types, api_host, api_port, created_at, updated_at, last_reached_at)
             VALUES ('peer-a', 'Peer A', '["tagger"]', '127.0.0.1', 5000, 100, 200, 200),
                    ('peer-b', 'Peer B', '["tagger"]', '127.0.0.2', 5001, 100, 200, NULL);
             INSERT INTO files(id, is_deleted) VALUES (1, 0), (2, 0), (3, 1);
             INSERT INTO file_hailo_tags(file_id, tag_name, confidence, source, created_at)
             VALUES (1, 'cat', 0.9, 'mesh', 200);"#,
        )
        .execute(&pool)
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
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("config.json"),
                    project_root: PathBuf::from("."),
                    app_config: json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn test_state_with_local_tagger() -> (SharedState, String) {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        let seed = vec![7_u8; 32];
        let expected_peer_id = derive_peer_id_from_seed(&seed).unwrap();
        sqlx::raw_sql(
            r#"CREATE TABLE peers (
               peer_id TEXT PRIMARY KEY,
               name TEXT,
               inference_types TEXT,
               api_host TEXT,
               api_port INTEGER,
               token TEXT,
               token_expires_at INTEGER,
               token_issued_at INTEGER,
               allow_legacy_auth INTEGER NOT NULL DEFAULT 0,
               created_at INTEGER NOT NULL,
               updated_at INTEGER NOT NULL,
               last_reached_at INTEGER,
               last_attempted_at INTEGER
             );
             CREATE TABLE peer_inference_disabled (peer_id TEXT NOT NULL, inference_type TEXT NOT NULL);
             CREATE TABLE lan_cowork_identity (
               key TEXT PRIMARY KEY,
               value BLOB NOT NULL
             );
             INSERT INTO lan_cowork_identity(key, value) VALUES ('ed25519_seed', X'0707070707070707070707070707070707070707070707070707070707070707');
             INSERT INTO peers(peer_id, name, inference_types, api_host, api_port, created_at, updated_at, last_reached_at)
             VALUES ('peer-a', 'Peer A', '["tagger"]', '127.0.0.1', 5000, 100, 200, 200);"#,
        )
        .execute(&pool)
        .await
        .unwrap();
        let project_root =
            std::env::temp_dir().join(format!("yu-server-local-peer-test-{}", std::process::id()));
        let model_dir = project_root
            .join("cache")
            .join("wd_tagger")
            .join("SmilingWolf_wd-swinv2-tagger-v3");
        std::fs::create_dir_all(&model_dir).unwrap();
        std::fs::write(model_dir.join("model.onnx"), b"").unwrap();
        let cache_dir = project_root.join("cache");

        let state = Arc::new(
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
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: project_root.join("config.json"),
                    project_root,
                    cache_dir,
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                    app_config: json!({
                        "extensions": {
                            "builtin-lan-cowork": {
                                "peer_name": "local-node"
                            }
                        }
                    }),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        );
        (state, expected_peer_id)
    }

    async fn json_body(response: axum::response::Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn resolve_tagger_peers_excludes_disabled_tagger_capability() {
        let state = test_state().await;
        sqlx::query("INSERT INTO peer_inference_disabled(peer_id, inference_type) VALUES ('peer-a', 'tagger')")
            .execute(&state.db)
            .await
            .unwrap();
        assert!(resolve_tagger_peers(&state).await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn resolve_tagger_peers_excludes_unadvertised_tagger_capability() {
        let state = test_state().await;
        sqlx::query("UPDATE peers SET inference_types = '[\"clip\"]' WHERE peer_id = 'peer-a'")
            .execute(&state.db)
            .await
            .unwrap();
        assert!(resolve_tagger_peers(&state).await.unwrap().is_empty());
    }

    #[tokio::test]
    async fn resolve_tagger_peers_drops_missing_and_invalid_remote_credentials() {
        for update in [
            "DELETE FROM peers WHERE peer_id = 'peer-a'",
            "UPDATE peers SET api_host = '' WHERE peer_id = 'peer-a'",
            "UPDATE peers SET api_host = NULL WHERE peer_id = 'peer-a'",
            "UPDATE peers SET api_port = 0 WHERE peer_id = 'peer-a'",
            "UPDATE peers SET api_port = NULL WHERE peer_id = 'peer-a'",
            "UPDATE peers SET api_port = 65537 WHERE peer_id = 'peer-a'",
        ] {
            let state = test_state().await;
            sqlx::query(update).execute(&state.db).await.unwrap();
            assert!(
                resolve_tagger_peers(&state).await.unwrap().is_empty(),
                "invalid remote credentials must be excluded: {update}"
            );
        }
    }

    #[tokio::test]
    async fn resolve_tagger_peers_keeps_local_peer_first() {
        let (state, local_id) = test_state_with_local_tagger().await;
        let peers = resolve_tagger_peers(&state).await.unwrap();
        assert_eq!(peers[0].peer_id, local_id);
        assert!(peers[0].is_local);
    }

    #[tokio::test]
    async fn resolve_tagger_peers_omits_local_without_tagger_capability() {
        let peers = resolve_tagger_peers(&test_state().await).await.unwrap();
        assert!(peers.iter().all(|peer| !peer.is_local));
    }

    #[tokio::test]
    async fn resolve_tagger_peers_preserves_empty_and_null_tokens() {
        for token in [Some("verbatim"), Some(""), None] {
            let state = test_state().await;
            sqlx::query("UPDATE peers SET token = ? WHERE peer_id = 'peer-a'")
                .bind(token)
                .execute(&state.db)
                .await
                .unwrap();
            let peers = resolve_tagger_peers(&state).await.unwrap();
            assert_eq!(peers.len(), 1);
            assert_eq!(
                peers[0].transport.as_ref().unwrap().token,
                token.unwrap_or_default()
            );
        }
    }

    #[tokio::test]
    async fn list_reads_tagger_peers_from_persisted_registry() {
        let value = json_body(list(State(test_state().await), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["mode"], "mesh");
        assert_eq!(value["servers"][0]["id"], "peer-a");
        assert_eq!(value["servers"][0]["type"], "mesh");
        assert_eq!(value["servers"][0]["status"], "online");
    }

    #[tokio::test]
    async fn health_returns_online_tagger_peers_from_persisted_registry() {
        let value = json_body(health(State(test_state().await), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["peers"][0]["peer_id"], "peer-a");
        assert_eq!(value["peers"][0]["status"], "online");
        assert_eq!(value["peers"][0]["is_local"], false);
    }

    #[tokio::test]
    async fn list_and_health_prepend_local_tagger_peer_from_identity_and_cache() {
        let (state, expected_peer_id) = test_state_with_local_tagger().await;

        let list_value = json_body(list(State(Arc::clone(&state)), None).await).await;
        let health_value = json_body(health(State(state), None).await).await;

        assert_eq!(list_value["servers"][0]["id"], expected_peer_id);
        assert_eq!(list_value["servers"][0]["name"], "local-node");
        assert_eq!(list_value["servers"][0]["status"], "online");
        assert_eq!(health_value["peers"][0]["peer_id"], expected_peer_id);
        assert_eq!(health_value["peers"][0]["name"], "local-node");
        assert_eq!(health_value["peers"][0]["status"], "online");
        assert_eq!(health_value["peers"][0]["is_local"], true);
        assert_eq!(health_value["peers"][1]["peer_id"], "peer-a");
    }

    #[tokio::test]
    async fn stats_counts_files_without_tagger_rows() {
        let value = json_body(stats(State(test_state().await), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["untagged_count"], 1);
    }

    #[tokio::test]
    async fn batch_tag_malformed_or_missing_body_behaves_as_empty_object() {
        for body in [Bytes::new(), Bytes::from_static(b"not json")] {
            let response = batch_tag(State(test_state().await), body).await;
            assert_eq!(response.status(), StatusCode::OK);
            assert_eq!(
                json_body(response).await,
                json!({"started": true, "job_id": "tagger_cluster", "ok": true, "error": null, "data": null})
            );
        }
    }

    #[tokio::test]
    async fn batch_tag_rejects_boolean_limit_with_a_code() {
        let response = batch_tag(
            State(test_state().await),
            Bytes::from_static(br#"{"limit":true}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            json_body(response).await,
            json!({"ok": false, "error": "limit must be an integer", "code": "invalid_value"})
        );
    }

    #[tokio::test]
    async fn batch_cancel_cancels_native_tagger_cluster_job() {
        let state = test_state().await;
        let cancel = state
            .job_manager
            .start_if_idle(TAGGER_CLUSTER_JOB_ID, "Tagger mesh")
            .unwrap();
        let response = batch_cancel(State(state), Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert!(cancel.is_cancelled());
        assert_eq!(
            json_body(response).await,
            json!({
                "status": "cancelling",
                "message": "Tagger cluster cancel requested",
                "ok": true,
                "error": null,
                "data": null
            })
        );
    }

    #[test]
    fn tagger_mesh_progress_uses_equals_delimiters() {
        let stats = crate::tagger_batch::BatchStats {
            tagged: 2,
            empty: 3,
            errors: 4,
            done: 9,
        };
        assert_eq!(
            mesh_progress_message(&stats, 10),
            "Tagger mesh: 9/10 (tagged=2, empty=3, errors=4)"
        );
    }
}
