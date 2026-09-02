use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use sqlx::{Row, SqlitePool};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

#[derive(Clone, Copy)]
struct TrophyDef {
    trophy_type: &'static str,
    title: &'static str,
    tier: &'static str,
    category: &'static str,
    hidden: bool,
}

// Source of truth: extensions/builtin_trophy/core_impl/trophy_definitions.py.
// Drift is caught by the golden compatibility gate.
const ALL_TROPHY_DEFS: &[TrophyDef] = &[
    TrophyDef {
        trophy_type: "milestone_100",
        title: "100 Files",
        tier: "bronze",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "milestone_500",
        title: "500 Files",
        tier: "bronze",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "milestone_1k",
        title: "1,000 Files",
        tier: "silver",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "milestone_5k",
        title: "5,000 Files",
        tier: "silver",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "milestone_10k",
        title: "10,000 Files",
        tier: "gold",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "milestone_50k",
        title: "50,000 Files",
        tier: "gold",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "milestone_100k",
        title: "100,000 Files",
        tier: "platinum",
        category: "milestone",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "streak_7",
        title: "7 Days Streak",
        tier: "bronze",
        category: "streak",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "streak_30",
        title: "30 Days Streak",
        tier: "silver",
        category: "streak",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "streak_365",
        title: "365 Days Streak",
        tier: "platinum",
        category: "streak",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "tags_100",
        title: "100 Unique Tags",
        tier: "bronze",
        category: "diversity",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "tags_500",
        title: "500 Unique Tags",
        tier: "silver",
        category: "diversity",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "tags_1000",
        title: "1,000 Unique Tags",
        tier: "gold",
        category: "diversity",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "source_all",
        title: "All Sources Used",
        tier: "gold",
        category: "source",
        hidden: false,
    },
    TrophyDef {
        trophy_type: "night_owl",
        title: "Night Owl",
        tier: "silver",
        category: "hidden",
        hidden: true,
    },
    TrophyDef {
        trophy_type: "centurion",
        title: "Centurion",
        tier: "gold",
        category: "hidden",
        hidden: true,
    },
];

fn api_success(data: Value) -> Response {
    Json(json!({
        "ok": true,
        "error": null,
        "data": data,
    }))
    .into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{}", message);
    (
        StatusCode::INTERNAL_SERVER_ERROR,
        Json(json!({"ok": false, "error": "internal_server_error"})),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn build_trophies(pool: &SqlitePool) -> Result<Value, sqlx::Error> {
    let rows = sqlx::query(
        "SELECT trophy_type, title, tier, category, achieved_month, achieved_at, metadata
         FROM trophies",
    )
    .fetch_all(pool)
    .await?;
    let mut achieved = std::collections::HashMap::new();
    for row in rows {
        achieved.insert(row.get::<String, _>("trophy_type"), row);
    }
    let mut result = Vec::with_capacity(ALL_TROPHY_DEFS.len());
    for def in ALL_TROPHY_DEFS {
        if let Some(row) = achieved.get(def.trophy_type) {
            let metadata = row
                .try_get::<Option<String>, _>("metadata")
                .ok()
                .flatten()
                .and_then(|raw| serde_json::from_str::<Value>(&raw).ok())
                .filter(Value::is_object)
                .unwrap_or_else(|| json!({}));
            result.push(json!({
                "type": def.trophy_type,
                "title": row.get::<String, _>("title"),
                "tier": row.get::<String, _>("tier"),
                "category": row.get::<String, _>("category"),
                "achieved": true,
                "achieved_month": row.try_get::<Option<String>, _>("achieved_month").ok().flatten(),
                "achieved_at": row.try_get::<Option<i64>, _>("achieved_at").ok().flatten(),
                "metadata": metadata,
            }));
        } else {
            result.push(json!({
                "type": def.trophy_type,
                "title": if def.hidden { "???" } else { def.title },
                "tier": def.tier,
                "category": def.category,
                "achieved": false,
                "achieved_month": null,
                "achieved_at": null,
                "metadata": {},
            }));
        }
    }
    Ok(Value::Array(result))
}

pub async fn list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_trophies(&state.db_read).await {
        Ok(data) => api_success(data),
        Err(error) => internal_error(error, "failed to list trophies"),
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(schema: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(schema).execute(&pool).await.unwrap();
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

    async fn json_body(response: Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn trophies_include_earned_unearned_hidden_and_invalid_metadata() {
        let state = test_state(
            "CREATE TABLE trophies (
               trophy_type TEXT PRIMARY KEY,
               title TEXT NOT NULL,
               tier TEXT NOT NULL,
               category TEXT NOT NULL,
               achieved_month TEXT,
               achieved_at INTEGER,
               metadata TEXT
             );
             INSERT INTO trophies(trophy_type, title, tier, category, achieved_month, achieved_at, metadata)
             VALUES
               ('milestone_100', '100 Files', 'bronze', 'milestone', '2026-06', 123, '{\"count\":100}'),
               ('night_owl', 'Night Owl', 'silver', 'hidden', '2026-06', 124, 'not-json');",
        )
        .await;

        let value = json_body(list(State(state), None).await).await;

        assert_eq!(value["ok"], true);
        assert_eq!(value["error"], Value::Null);
        assert!(value["data"].as_array().unwrap().len() >= 16);
        assert_eq!(value["data"][0]["type"], "milestone_100");
        assert_eq!(value["data"][0]["achieved"], true);
        assert_eq!(value["data"][0]["metadata"], json!({"count": 100}));
        assert_eq!(value["data"][1]["achieved"], false);
        assert_eq!(value["data"][1]["title"], "500 Files");
        let night_owl = value["data"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["type"] == "night_owl")
            .unwrap();
        assert_eq!(night_owl["achieved"], true);
        assert_eq!(night_owl["metadata"], json!({}));
        let centurion = value["data"]
            .as_array()
            .unwrap()
            .iter()
            .find(|item| item["type"] == "centurion")
            .unwrap();
        assert_eq!(centurion["achieved"], false);
        assert_eq!(centurion["title"], "???");
    }
}
