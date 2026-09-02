//! Native `/api/mesh-inference/*` handlers.

use std::{
    collections::{HashMap, HashSet},
    sync::{Mutex, OnceLock},
    time::{Duration, Instant},
};

use axum::{
    extract::{rejection::JsonRejection, Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    routes::{
        peer_identity::local_peer_id,
        tagger_servers::{configured_peer_name, has_local_tagger_capability},
    },
    state::SharedState,
};

const KNOWN_TYPES: [&str; 4] = ["tagger", "clip", "yolo", "whisper"];
const BULK_DEBOUNCE: Duration = Duration::from_secs(1);
static BULK_LAST_CALL: OnceLock<Mutex<HashMap<String, Instant>>> = OnceLock::new();

fn result(data: Value) -> Response {
    Json(json!({"ok": true, "error": null, "data": data})).into_response()
}
fn error(status: StatusCode, message: &str, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
        .into_response()
}
fn gate(state: &SharedState, auth: Option<&Extension<AuthContext>>) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth.map(|a| &a.0))
}
fn valid_peer_id(peer_id: &str) -> bool {
    !peer_id.is_empty()
        && peer_id.len() <= 64
        && peer_id
            .bytes()
            .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'_' | b'-' | b'.' | b':'))
}
fn advertised(raw: &str) -> Vec<String> {
    serde_json::from_str::<Vec<Value>>(raw)
        .ok()
        .map(|v| {
            v.into_iter()
                .filter_map(|x| x.as_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default()
}

// Rust can detect only a local tagger model. Reporting clip/yolo/whisper would invent
// capabilities; under-reporting is the honest fallback until their discovery exists here.
pub(crate) async fn local_peer(state: &SharedState) -> Option<(String, Value)> {
    let peer_id = local_peer_id(&**state).await?;
    let types = if has_local_tagger_capability(state) {
        vec!["tagger"]
    } else {
        vec![]
    };
    // Python's mDNS GPU field is not persisted in `peers`; native returns an empty string.
    Some((
        peer_id.clone(),
        json!({"peer_id": peer_id, "name": configured_peer_name(state), "status": "online", "is_local": true, "inference_types": types, "device_info": ""}),
    ))
}

pub(crate) async fn disabled(
    state: &SharedState,
) -> Result<HashSet<(String, String)>, sqlx::Error> {
    Ok(
        sqlx::query("SELECT peer_id, inference_type FROM peer_inference_disabled")
            .fetch_all(&state.db_read)
            .await?
            .into_iter()
            .filter_map(|r| {
                Some((
                    r.try_get("peer_id").ok()?,
                    r.try_get("inference_type").ok()?,
                ))
            })
            .collect(),
    )
}

pub(crate) async fn peers(state: &SharedState) -> Result<Vec<Value>, sqlx::Error> {
    let disabled = disabled(state).await?;
    let mut out = Vec::new();
    if let Some((id, mut local)) = local_peer(state).await {
        let types = local["inference_types"].as_array().unwrap();
        let mut d: Vec<_> = types
            .iter()
            .filter_map(Value::as_str)
            .filter(|t| disabled.contains(&(id.clone(), (*t).to_owned())))
            .collect();
        d.sort_unstable();
        local["disabled_types"] = json!(d);
        out.push(local);
    }
    for row in sqlx::query("SELECT peer_id, name, inference_types FROM peers WHERE last_reached_at IS NOT NULL ORDER BY peer_id").fetch_all(&state.db_read).await? {
        let id: String = row.try_get("peer_id")?; let types = advertised(&row.try_get::<String, _>("inference_types")?);
        let mut d: Vec<_> = types.iter().filter(|t| disabled.contains(&(id.clone(), (*t).clone()))).collect();
        d.sort_unstable();
        out.push(json!({"peer_id": id, "name": row.try_get::<String, _>("name").unwrap_or_default(), "status": "online", "is_local": false, "inference_types": types, "device_info": "", "disabled_types": d}));
    }
    Ok(out)
}

async fn known_peer(
    state: &SharedState,
    peer_id: &str,
) -> Result<Option<Vec<String>>, sqlx::Error> {
    if let Some((id, local)) = local_peer(state).await {
        if id == peer_id {
            return Ok(Some(
                local["inference_types"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_owned)
                    .collect(),
            ));
        }
    }
    Ok(
        sqlx::query("SELECT inference_types FROM peers WHERE peer_id = ?")
            .bind(peer_id)
            .fetch_optional(&state.db_read)
            .await?
            .map(|r| {
                advertised(
                    &r.try_get::<String, _>("inference_types")
                        .unwrap_or_default(),
                )
            }),
    )
}

pub async fn mesh_state(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(r) = gate(&state, auth.as_ref()) {
        return r;
    }
    match peers(&state).await {
        Ok(peers) => result(json!({"peers": peers})),
        Err(err) => {
            tracing::error!(?err, "failed to read mesh inference peers");
            error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "failed to read peers",
                "database_error",
            )
        }
    }
}
pub async fn mesh_refresh(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
) -> Response {
    mesh_state(State(state), auth).await
}

pub async fn mesh_toggle(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(r) = gate(&state, auth.as_ref()) {
        return r;
    }
    let body = body.map(|Json(body)| body).unwrap_or_else(|_| json!({}));
    let Some(peer_id) = body
        .get("peer_id")
        .and_then(Value::as_str)
        .filter(|p| valid_peer_id(p))
    else {
        return error(
            StatusCode::BAD_REQUEST,
            "invalid peer_id",
            "invalid_peer_id",
        );
    };
    let Some(kind) = body
        .get("inference_type")
        .and_then(Value::as_str)
        .filter(|t| KNOWN_TYPES.contains(t))
    else {
        return error(
            StatusCode::BAD_REQUEST,
            "unknown inference_type",
            "unknown_inference_type",
        );
    };
    let Some(flag) = body.get("disabled").and_then(Value::as_bool) else {
        return error(
            StatusCode::BAD_REQUEST,
            "disabled must be a boolean",
            "invalid_disabled",
        );
    };
    let advertised = match known_peer(&state, peer_id).await {
        Ok(Some(types)) => types,
        Ok(None) => return error(StatusCode::NOT_FOUND, "unknown peer", "unknown_peer"),
        Err(err) => {
            tracing::error!(?err, "failed to read mesh inference peer");
            return error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "failed to read peers",
                "database_error",
            );
        }
    };
    if !advertised.iter().any(|t| t == kind) {
        return error(
            StatusCode::BAD_REQUEST,
            "type not advertised",
            "type_not_advertised",
        );
    }
    let query = if flag {
        "INSERT OR IGNORE INTO peer_inference_disabled (peer_id, inference_type) VALUES (?, ?)"
    } else {
        "DELETE FROM peer_inference_disabled WHERE peer_id = ? AND inference_type = ?"
    };
    if let Err(err) = sqlx::query(query)
        .bind(peer_id)
        .bind(kind)
        .execute(&state.db)
        .await
    {
        tracing::error!(?err, "failed to update mesh inference disabled state");
        return error(
            StatusCode::INTERNAL_SERVER_ERROR,
            "failed to update disabled state",
            "database_error",
        );
    }
    result(json!({"peer_id": peer_id, "inference_type": kind, "disabled": flag}))
}

fn debounced(key: String) -> bool {
    let now = Instant::now();
    let mut calls = BULK_LAST_CALL
        .get_or_init(|| Mutex::new(HashMap::new()))
        .lock()
        .expect("bulk debounce lock poisoned");
    if calls
        .get(&key)
        .is_some_and(|last| now.duration_since(*last) < BULK_DEBOUNCE)
    {
        true
    } else {
        calls.insert(key, now);
        false
    }
}
async fn set_disabled(
    state: &SharedState,
    peer_id: &str,
    kind: &str,
    flag: bool,
) -> Result<u64, sqlx::Error> {
    let query = if flag {
        "INSERT OR IGNORE INTO peer_inference_disabled (peer_id, inference_type) VALUES (?, ?)"
    } else {
        "DELETE FROM peer_inference_disabled WHERE peer_id = ? AND inference_type = ?"
    };
    Ok(sqlx::query(query)
        .bind(peer_id)
        .bind(kind)
        .execute(&state.db)
        .await?
        .rows_affected())
}

pub async fn mesh_bulk(
    State(state): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    body: Result<Json<Value>, JsonRejection>,
) -> Response {
    if let Some(r) = gate(&state, auth.as_ref()) {
        return r;
    }
    let body = body.map(|Json(body)| body).unwrap_or_else(|_| json!({}));
    let action = body.get("action").and_then(Value::as_str).unwrap_or("");
    let kind = body.get("inference_type").and_then(Value::as_str);
    let current = match peers(&state).await {
        Ok(p) => p,
        Err(err) => {
            tracing::error!(?err, "failed to read mesh inference peers for bulk action");
            return error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "failed to read peers",
                "database_error",
            );
        }
    };
    if action == "local_only" {
        let Some(local) = current.iter().find(|peer| peer["is_local"] == true) else {
            return error(
                StatusCode::CONFLICT,
                "local peer has no effective inference types",
                "local_peer_has_no_effective_types",
            );
        };
        if local["inference_types"]
            .as_array()
            .unwrap()
            .iter()
            .filter_map(Value::as_str)
            .all(|t| {
                local["disabled_types"]
                    .as_array()
                    .unwrap()
                    .iter()
                    .filter_map(Value::as_str)
                    .any(|d| d == t)
            })
        {
            return error(
                StatusCode::CONFLICT,
                "local peer has no effective inference types",
                "local_peer_has_no_effective_types",
            );
        }
    }
    if !matches!(action, "disable_all_remote" | "enable_all" | "local_only") {
        return error(StatusCode::BAD_REQUEST, "unknown action", "unknown_action");
    }
    if debounced(format!("{action}:{}", kind.unwrap_or(""))) {
        return error(
            StatusCode::TOO_MANY_REQUESTS,
            "too many requests, please wait",
            "bulk_debounce",
        );
    }
    if matches!(action, "disable_all_remote" | "enable_all")
        && !kind.is_some_and(|t| KNOWN_TYPES.contains(&t))
    {
        return error(
            StatusCode::BAD_REQUEST,
            "inference_type required",
            "unknown_inference_type",
        );
    }
    let mut changed = 0;
    match action {
        "disable_all_remote" => {
            for p in &current {
                if !p["is_local"].as_bool().unwrap_or(false)
                    && p["inference_types"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter_map(Value::as_str)
                        .any(|t| Some(t) == kind)
                {
                    match set_disabled(&state, p["peer_id"].as_str().unwrap(), kind.unwrap(), true)
                        .await
                    {
                        Ok(count) => changed += count,
                        Err(err) => {
                            tracing::error!(
                                ?err,
                                "failed to update mesh inference disabled state in bulk action"
                            );
                            return error(
                                StatusCode::INTERNAL_SERVER_ERROR,
                                "failed to update disabled state",
                                "database_error",
                            );
                        }
                    }
                }
            }
        }
        "enable_all" => {
            let current_ids: HashSet<_> = current
                .iter()
                .filter_map(|peer| peer["peer_id"].as_str())
                .collect();
            let disabled = match disabled(&state).await {
                Ok(disabled) => disabled,
                Err(err) => {
                    tracing::error!(
                        ?err,
                        "failed to read mesh inference disabled state in bulk action"
                    );
                    return error(
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "failed to read disabled state",
                        "database_error",
                    );
                }
            };
            for (peer, typ) in disabled {
                if current_ids.contains(peer.as_str()) && Some(typ.as_str()) == kind {
                    match set_disabled(&state, &peer, &typ, false).await {
                        Ok(count) => changed += count,
                        Err(err) => {
                            tracing::error!(
                                ?err,
                                "failed to update mesh inference disabled state in bulk action"
                            );
                            return error(
                                StatusCode::INTERNAL_SERVER_ERROR,
                                "failed to update disabled state",
                                "database_error",
                            );
                        }
                    }
                }
            }
        }
        "local_only" => {
            for p in &current {
                if !p["is_local"].as_bool().unwrap_or(false) {
                    for typ in p["inference_types"]
                        .as_array()
                        .unwrap()
                        .iter()
                        .filter_map(Value::as_str)
                    {
                        match set_disabled(&state, p["peer_id"].as_str().unwrap(), typ, true).await
                        {
                            Ok(count) => changed += count,
                            Err(err) => {
                                tracing::error!(
                                    ?err,
                                    "failed to update mesh inference disabled state in bulk action"
                                );
                                return error(
                                    StatusCode::INTERNAL_SERVER_ERROR,
                                    "failed to update disabled state",
                                    "database_error",
                                );
                            }
                        }
                    }
                }
            }
        }
        _ => return error(StatusCode::BAD_REQUEST, "unknown action", "unknown_action"),
    };
    result(json!({"changed": changed}))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{
        body::{to_bytes, Body},
        http::{header, Request},
        routing::post,
        Router,
    };
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use tower::ServiceExt;

    use crate::state::{AppState, Config};

    async fn test_state() -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE peers (peer_id TEXT PRIMARY KEY, name TEXT, inference_types TEXT, last_reached_at INTEGER);
             CREATE TABLE peer_inference_disabled (peer_id TEXT, inference_type TEXT, PRIMARY KEY(peer_id, inference_type));
             INSERT INTO peers VALUES
                ('online', 'Online', '[\"whisper\", \"tagger\"]', 1),
                ('offline', 'Offline', '[\"tagger\"]', NULL),
                ('broken', 'Broken', 'not-json', 1);",
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

    async fn response_json(response: Response) -> Value {
        serde_json::from_slice(&to_bytes(response.into_body(), usize::MAX).await.unwrap()).unwrap()
    }

    #[tokio::test]
    async fn state_succeeds_after_rust_migrations_without_python_migration() {
        let dir = tempfile::tempdir().unwrap();
        let db_path = dir.path().join("tags.db");
        let options = SqliteConnectOptions::from_str(&format!("sqlite:{}", db_path.display()))
            .unwrap()
            .create_if_missing(true);
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect_with(options)
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, applied_at INTEGER, description TEXT);
             CREATE TABLE files (path TEXT PRIMARY KEY, meta_source TEXT, parser_version INTEGER NOT NULL DEFAULT 1);
             CREATE TABLE peers (peer_id TEXT PRIMARY KEY, name TEXT, last_reached_at INTEGER);",
        )
        .execute(&pool)
        .await
        .unwrap();
        tagdb_core::apply_pending_rust_migrations(&pool)
            .await
            .unwrap();
        let state = Arc::new(
            AppState::new(
                Config {
                    db_path: format!("sqlite:{}", db_path.display()),
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
                    cache_dir: dir.path().to_path_buf(),
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
        );

        assert_eq!(
            mesh_state(State(state), None).await.status(),
            StatusCode::OK
        );
    }

    async fn request(
        app: Router,
        path: &str,
        body: Body,
        content_type: Option<&str>,
    ) -> (StatusCode, Value) {
        let mut request = Request::post(path).body(body).unwrap();
        if let Some(content_type) = content_type {
            request
                .headers_mut()
                .insert(header::CONTENT_TYPE, content_type.parse().unwrap());
        }
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        (status, response_json(response).await)
    }

    #[test]
    fn peer_id_matches_python_validator() {
        assert!(valid_peer_id(&"a".repeat(64)));
        assert!(valid_peer_id("host.local:8080"));
        assert!(!valid_peer_id(""));
        assert!(!valid_peer_id("../peer"));
        assert!(!valid_peer_id(&"a".repeat(65)));
    }

    #[test]
    fn malformed_inference_types_advertises_nothing() {
        assert_eq!(advertised("not-json"), Vec::<String>::new());
        assert_eq!(advertised(r#"["tagger", 1, "clip"]"#), ["tagger", "clip"]);
    }

    #[tokio::test]
    async fn state_sorts_disabled_types_and_degrades_malformed_advertisement() {
        let state = test_state().await;
        sqlx::query("INSERT INTO peer_inference_disabled VALUES ('online', 'whisper'), ('online', 'tagger')")
            .execute(&state.db).await.unwrap();
        let body = response_json(mesh_state(State(state), None).await).await;
        let peers = body["data"]["peers"].as_array().unwrap();
        assert_eq!(
            peers
                .iter()
                .find(|peer| peer["peer_id"] == "online")
                .unwrap()["disabled_types"],
            json!(["tagger", "whisper"])
        );
        assert_eq!(
            peers
                .iter()
                .find(|peer| peer["peer_id"] == "broken")
                .unwrap()["inference_types"],
            json!([])
        );
    }

    #[tokio::test]
    async fn peers_keep_the_local_peer_first_even_when_a_remote_sorts_before_it() {
        let state = test_state().await;
        sqlx::raw_sql(
            "CREATE TABLE lan_cowork_identity (key TEXT PRIMARY KEY, value BLOB NOT NULL);",
        )
        .execute(&state.db)
        .await
        .unwrap();
        sqlx::query("INSERT INTO lan_cowork_identity (key, value) VALUES ('ed25519_seed', ?)")
            .bind((1u8..=32).collect::<Vec<_>>())
            .execute(&state.db)
            .await
            .unwrap();
        let local = local_peer(&state).await.expect("local peer").0;
        sqlx::query("INSERT INTO peers VALUES (?, 'Earlier', '[\"tagger\"]', 1)")
            .bind(format!("!before-{local}"))
            .execute(&state.db)
            .await
            .unwrap();
        let peers = peers(&state).await.unwrap();
        assert_eq!(
            peers[0]["peer_id"], local,
            "local peer must precede SQL-sorted remotes"
        );
    }

    #[tokio::test]
    async fn toggle_accepts_offline_peer_and_reports_validation_codes() {
        let state = test_state().await;
        let ok = mesh_toggle(
            State(Arc::clone(&state)),
            None,
            Ok(Json(
                json!({"peer_id":"offline", "inference_type":"tagger", "disabled":true}),
            )),
        )
        .await;
        assert_eq!(ok.status(), StatusCode::OK);
        for (body, code) in [
            (json!({}), "invalid_peer_id"),
            (json!({"peer_id":"online"}), "unknown_inference_type"),
            (
                json!({"peer_id":"online", "inference_type":"tagger"}),
                "invalid_disabled",
            ),
            (
                json!({"peer_id":"missing", "inference_type":"tagger", "disabled":true}),
                "unknown_peer",
            ),
            (
                json!({"peer_id":"online", "inference_type":"clip", "disabled":true}),
                "type_not_advertised",
            ),
        ] {
            assert_eq!(
                response_json(mesh_toggle(State(Arc::clone(&state)), None, Ok(Json(body))).await)
                    .await["code"],
                code
            );
        }
    }

    #[tokio::test]
    async fn malformed_bodies_keep_python_error_shape() {
        for (path, expected) in [("/toggle", "invalid_peer_id"), ("/bulk", "unknown_action")] {
            for (body, content_type) in [
                (Body::empty(), None),
                (Body::from("{"), Some("application/json")),
                (Body::from("{}"), Some("text/plain")),
            ] {
                let state = test_state().await;
                let app = Router::new()
                    .route("/toggle", post(mesh_toggle))
                    .route("/bulk", post(mesh_bulk))
                    .with_state(state);
                let (status, value) = request(app, path, body, content_type).await;
                assert_eq!(status, StatusCode::BAD_REQUEST);
                assert_eq!(value["code"], expected);
            }
        }
    }

    #[tokio::test]
    async fn bulk_actions_preserve_offline_disablement() {
        let state = test_state().await;
        sqlx::query("INSERT INTO peer_inference_disabled VALUES ('online', 'tagger'), ('offline', 'tagger')").execute(&state.db).await.unwrap();
        let enabled = response_json(
            mesh_bulk(
                State(Arc::clone(&state)),
                None,
                Ok(Json(
                    json!({"action":"enable_all", "inference_type":"tagger"}),
                )),
            )
            .await,
        )
        .await;
        assert_eq!(enabled["data"]["changed"], 1);
        assert_eq!(
            sqlx::query_scalar::<_, i64>(
                "SELECT count(*) FROM peer_inference_disabled WHERE peer_id = 'offline'"
            )
            .fetch_one(&state.db)
            .await
            .unwrap(),
            1
        );
        let disabled = response_json(
            mesh_bulk(
                State(Arc::clone(&state)),
                None,
                Ok(Json(
                    json!({"action":"disable_all_remote", "inference_type":"whisper"}),
                )),
            )
            .await,
        )
        .await;
        assert_eq!(disabled["data"]["changed"], 1);
        let local_only = response_json(
            mesh_bulk(
                State(Arc::clone(&state)),
                None,
                Ok(Json(json!({"action":"local_only"}))),
            )
            .await,
        )
        .await;
        assert_eq!(local_only["code"], "local_peer_has_no_effective_types");
    }

    #[test]
    fn bulk_debounce_rejects_same_key() {
        let key = format!("test:{}", Instant::now().elapsed().as_nanos());
        assert!(!debounced(key.clone()));
        assert!(debounced(key));
    }
}
