use axum::{extract::State, response::Json};

use crate::state::SharedState;

/// Reports only transfers through the shared forwarders in `auto_stubs`.
/// Route-specific `python_url` forwarding is not measured.
pub async fn proxy_stats(State(state): State<SharedState>) -> Json<serde_json::Value> {
    let hits = state.proxy_hits.lock().expect("proxy_hits lock");
    let total: u64 = hits.values().sum();
    Json(serde_json::json!({
        "ok": true,
        "scope": "auto_stubs",
        "total": total,
        "proxied": &*hits,
    }))
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::extract::State;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state() -> SharedState {
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
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: PathBuf::from("config.json"),
                    project_root: PathBuf::from("."),
                    app_config: serde_json::json!({}),
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

    #[tokio::test]
    async fn proxy_stats_returns_total_and_proxied_hit_counts() {
        let state = test_state().await;
        {
            let mut hits = state.proxy_hits.lock().expect("proxy_hits lock");
            hits.insert("GET /api/files".to_string(), 1);
            hits.insert("POST /api/tags".to_string(), 1);
        }

        let axum::Json(value) = proxy_stats(State(state)).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["scope"], "auto_stubs");
        assert_eq!(value["total"], 2);
        assert_eq!(value["proxied"]["GET /api/files"], 1);
        assert_eq!(value["proxied"]["POST /api/tags"], 1);
    }
}
