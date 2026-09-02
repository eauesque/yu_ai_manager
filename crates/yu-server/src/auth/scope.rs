use axum::{
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::json;

use crate::auth::apikey::{key_has_scope, KeyInfo};

#[derive(Debug, Clone)]
pub struct AuthContext {
    pub reason: String,
    pub scopes: Option<Vec<String>>,
}

/// Allow if the API key holds `required` scope **or** `admin` (which always implies all scopes).
pub fn require_scope(
    pin_auth_enabled: bool,
    auth_context: Option<&AuthContext>,
    required: &str,
) -> Option<Response> {
    if !pin_auth_enabled {
        return None;
    }
    if let Some(context) = auth_context {
        match context.reason.as_str() {
            "api_key" => {
                let key_info = KeyInfo {
                    id: String::new(),
                    label: String::new(),
                    key_prefix: String::new(),
                    scopes: context.scopes.clone(),
                };
                if key_has_scope(&key_info, "admin") || key_has_scope(&key_info, required) {
                    return None;
                }
            }
            // Gateway/internal candidates should only reach proxied routes.
            // If they ever hit a native admin handler, fail closed below.
            "gateway_candidate" | "internal_candidate" => {}
            _ => return None,
        }
    }
    Some(
        (
            StatusCode::FORBIDDEN,
            Json(json!({
                "ok": false,
                "error": format!("Insufficient scope: requires '{required}'"),
            })),
        )
            .into_response(),
    )
}

pub fn require_admin_scope(
    pin_auth_enabled: bool,
    auth_context: Option<&AuthContext>,
) -> Option<Response> {
    require_scope(pin_auth_enabled, auth_context, "admin")
}

/// Session-only authorization, matching the Python `session_guard()` semantics
/// (PIN session required; API keys are never accepted). Deliberately reads
/// `tower_sessions::Session` directly rather than `AuthContext.reason` —
/// the auth chain evaluates API-key credentials before session credentials,
/// so `AuthContext.reason == "session"` would incorrectly reject a request
/// that presents both a valid session and an unrelated API key header.
pub async fn require_session(
    pin_auth_enabled: bool,
    session: Option<&tower_sessions::Session>,
) -> Option<Response> {
    if !pin_auth_enabled {
        return None;
    }
    let pin_ok = match session {
        Some(s) => s
            .get::<bool>("pin_ok")
            .await
            .unwrap_or(None)
            .unwrap_or(false),
        None => false,
    };
    if pin_ok {
        return None;
    }
    Some(
        (
            StatusCode::UNAUTHORIZED,
            Json(json!({
                "ok": false,
                "error": "session required",
            })),
        )
            .into_response(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    use axum::{body::to_bytes, http::StatusCode};

    async fn response_json(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[test]
    fn require_admin_scope_allows_when_pin_auth_disabled() {
        let context = AuthContext {
            reason: "api_key".to_string(),
            scopes: None,
        };
        assert!(require_admin_scope(false, Some(&context)).is_none());
    }

    #[test]
    fn require_admin_scope_allows_pin_session_context() {
        let context = AuthContext {
            reason: "session".to_string(),
            scopes: None,
        };
        assert!(require_admin_scope(true, Some(&context)).is_none());
    }

    #[tokio::test]
    async fn require_admin_scope_denies_no_scope_api_key_with_python_shape() {
        let context = AuthContext {
            reason: "api_key".to_string(),
            scopes: None,
        };
        let response = require_admin_scope(true, Some(&context)).unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
        let value = response_json(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["error"], "Insufficient scope: requires 'admin'");
    }

    #[test]
    fn require_admin_scope_allows_admin_api_key() {
        let context = AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["admin".to_string()]),
        };
        assert!(require_admin_scope(true, Some(&context)).is_none());
    }

    #[test]
    fn require_admin_scope_allows_trusted_proxy_context() {
        let context = AuthContext {
            reason: "trusted_proxy".to_string(),
            scopes: None,
        };
        assert!(require_admin_scope(true, Some(&context)).is_none());
    }

    #[test]
    fn require_scope_allows_scan_key_for_scan_scope() {
        let context = AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["scan".to_string()]),
        };
        assert!(require_scope(true, Some(&context), "scan").is_none());
    }

    #[test]
    fn require_scope_allows_admin_key_for_any_scope() {
        let context = AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["admin".to_string()]),
        };
        assert!(require_scope(true, Some(&context), "scan").is_none());
    }

    #[tokio::test]
    async fn require_admin_scope_denies_scan_only_key() {
        let context = AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["scan".to_string()]),
        };
        let response = require_admin_scope(true, Some(&context)).unwrap();
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn require_session_allows_when_pin_auth_disabled() {
        assert!(require_session(false, None).await.is_none());
    }

    #[tokio::test]
    async fn require_session_denies_when_no_session() {
        let response = require_session(true, None).await.unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
        let value = response_json(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["error"], "session required");
    }

    #[tokio::test]
    async fn require_session_denies_session_without_pin_ok() {
        let session = tower_sessions::Session::new(
            None,
            std::sync::Arc::new(tower_sessions::MemoryStore::default()),
            None,
        );
        let response = require_session(true, Some(&session)).await.unwrap();
        assert_eq!(response.status(), StatusCode::UNAUTHORIZED);
    }

    #[tokio::test]
    async fn require_session_allows_session_with_pin_ok() {
        let session = tower_sessions::Session::new(
            None,
            std::sync::Arc::new(tower_sessions::MemoryStore::default()),
            None,
        );
        session.insert("pin_ok", true).await.unwrap();
        assert!(require_session(true, Some(&session)).await.is_none());
    }
}
