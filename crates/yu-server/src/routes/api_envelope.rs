//! The one success-envelope shape, mirroring Python's `api_result`.
//!
//! `core/infra_core/api_success.py` builds `{"ok": true, "error": null, "data": null}`
//! and then does `body.update(payload)` -- so the payload lands at the **top level**
//! and `data` stays null. A client reads `json.peers`, never `json.data.peers`.
//!
//! This lives here rather than in each route file because the envelope already existed
//! five times in the tree, in three shapes:
//!
//! - `nai_bridge`, `sd_webui_bridge`, `comfyui_bridge` -- correct.
//! - `mcp_client::api_ok` -- `{"ok": true, ...payload}`, omitting `error` and `data`.
//! - `mesh_inference::result` -- `{"ok", "error", "data": payload}`, nesting the payload
//!   so `GET /api/mesh-inference/state` answered `data.peers` while Python answered
//!   `peers`. Measured against Python at 200/200 in v4.734.24; the differing keys were
//!   exactly `data` and `peers`.
//!
//! The same nesting mistake was repaired once before, in v4.732.22, in other handlers.
//! It came back in a file the repair did not reach -- which is why the shape now has
//! one owner instead of five.

use axum::Json;
use serde_json::{json, Map, Value};

/// Python's `api_result(payload)`: envelope keys, then the payload spread over them.
///
/// A non-object payload is dropped rather than nested, because Python's `dict.update`
/// would raise on one -- there is no shape for it to take.
pub fn api_ok(payload: Value) -> Json<Value> {
    let mut body = Map::new();
    body.insert("ok".to_string(), json!(true));
    body.insert("error".to_string(), json!(null));
    body.insert("data".to_string(), json!(null));
    if let Value::Object(map) = payload {
        for (k, v) in map {
            body.insert(k, v);
        }
    }
    Json(Value::Object(body))
}

#[cfg(test)]
mod tests {
    use super::*;

    /// The payload sits at the top level -- this is the regression that shipped.
    ///
    /// `mesh_inference::result` nested it under `data`, so every client reading
    /// `json.peers` got nothing from Rust while Python answered normally.
    #[test]
    fn payload_is_spread_not_nested() {
        let Json(body) = api_ok(json!({"peers": [1, 2]}));
        assert_eq!(body["peers"], json!([1, 2]), "payload must be top level");
        assert_eq!(body["data"], json!(null), "data stays null, as in Python");
        assert!(
            body.get("data").and_then(|d| d.get("peers")).is_none(),
            "payload must not also appear under data"
        );
    }

    /// `error` and `data` are always present -- `mcp_client::api_ok` omitted both, so a
    /// client testing `\"error\" in body` saw a different contract per route.
    #[test]
    fn envelope_keys_are_always_present() {
        let Json(body) = api_ok(json!({}));
        for key in ["ok", "error", "data"] {
            assert!(body.get(key).is_some(), "missing envelope key: {key}");
        }
        assert_eq!(body["ok"], json!(true));
    }

    /// A payload key of its own may overwrite an envelope default, exactly as
    /// Python's `body.update(payload)` does -- handlers rely on this to report
    /// `{"ok": false}` through the success path.
    #[test]
    fn payload_overrides_the_defaults_like_python_update() {
        let Json(body) = api_ok(json!({"ok": false, "error": "nope"}));
        assert_eq!(body["ok"], json!(false));
        assert_eq!(body["error"], json!("nope"));
    }
}
