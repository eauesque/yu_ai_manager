use std::{
    io::{Read, Seek, SeekFrom},
    path::Path,
    time::{SystemTime, UNIX_EPOCH},
};

use axum::{
    extract::{Extension, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use sha2::{Digest, Sha256};
use tokio_util::sync::CancellationToken;

use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::sse::{SseEvent, SseHub};
use crate::state::SharedState;

const JOB_ID: &str = "hash-backfill";
const STATE_FILE: &str = "hash_backfill_state.json";

#[derive(Serialize, Deserialize, Default, Clone)]
struct BackfillState {
    last_id: i64,
    computed: u64,
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn sse_ts() -> f64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0)
}

fn send_sse(hub: &SseHub, event_type: &str, data: Value) {
    hub.send(SseEvent {
        event_type: event_type.into(),
        timestamp: sse_ts(),
        data,
        source: "hash_backfill".into(),
    });
}

/// SHA-256 etag replicating Python's file_etag(). Seeds with size+ext ASCII,
/// then hashes full content (small) or head+[mid]+tail chunks (large).
fn file_etag(path: &Path) -> Option<String> {
    let size = std::fs::metadata(path).ok()?.len();
    let ext = path
        .extension()
        .and_then(|e| e.to_str())
        .unwrap_or("")
        .to_ascii_lowercase();

    let (full_threshold, chunk_size, use_mid) = match ext.as_str() {
        "png" => (2 * 1024 * 1024u64, 512 * 1024usize, false),
        "webm" => (4 * 1024 * 1024u64, 512 * 1024usize, true),
        _ => (2 * 1024 * 1024u64, 256 * 1024usize, false),
    };

    let mut h = Sha256::new();
    h.update(size.to_string().as_bytes());
    h.update(ext.as_bytes());

    let mut f = std::fs::File::open(path).ok()?;
    if size <= full_threshold {
        let mut buf = Vec::new();
        f.read_to_end(&mut buf).ok()?;
        h.update(&buf);
    } else {
        let mut head = vec![0u8; chunk_size];
        let n = f.read(&mut head).ok()?;
        h.update(&head[..n]);

        if use_mid && size > (chunk_size as u64) * 3 {
            let mid = size / 2 - (chunk_size as u64) / 2;
            f.seek(SeekFrom::Start(mid)).ok()?;
            let mut buf = vec![0u8; chunk_size];
            let n = f.read(&mut buf).ok()?;
            h.update(&buf[..n]);
        }

        let tail = size.saturating_sub(chunk_size as u64);
        f.seek(SeekFrom::Start(tail)).ok()?;
        let mut buf = vec![0u8; chunk_size];
        let n = f.read(&mut buf).ok()?;
        h.update(&buf[..n]);
    }

    Some(format!("{:x}", h.finalize()))
}

fn load_state(project_root: &Path) -> BackfillState {
    let path = project_root.join(STATE_FILE);
    std::fs::read_to_string(path)
        .ok()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_default()
}

fn save_state(project_root: &Path, bs: &BackfillState) {
    if let Ok(content) = serde_json::to_string(bs) {
        let path = project_root.join(STATE_FILE);
        let tmp = path.with_extension("json.tmp");
        let _ = std::fs::write(&tmp, content);
        let _ = std::fs::rename(tmp, path);
    }
}

async fn run_worker(state: SharedState, token: CancellationToken) {
    let project_root = state.config.project_root.clone();
    let db = state.db.clone();
    let hub = state.sse_hub.clone();
    let jm = state.job_manager.clone();

    let total: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NULL")
            .fetch_one(&db)
            .await
            .unwrap_or(0);

    let mut bs = load_state(&project_root);
    let base = bs.computed;

    loop {
        if token.is_cancelled() {
            break;
        }

        let rows: Vec<(i64, String)> = sqlx::query_as(
            "SELECT id, path FROM files WHERE is_deleted=0 AND hash IS NULL AND id > ? ORDER BY id LIMIT 200",
        )
        .bind(bs.last_id)
        .fetch_all(&db)
        .await
        .unwrap_or_default();

        if rows.is_empty() {
            break;
        }

        for (id, path_str) in &rows {
            if token.is_cancelled() {
                break;
            }
            let p = std::path::PathBuf::from(path_str);
            if let Some(etag) = tokio::task::block_in_place(|| file_etag(&p)) {
                let _ = sqlx::query("UPDATE files SET hash=? WHERE id=?")
                    .bind(&etag)
                    .bind(id)
                    .execute(&db)
                    .await;
                bs.computed += 1;
            }
            bs.last_id = *id;
        }

        save_state(&project_root, &bs);

        send_sse(
            &hub,
            "hash_backfill.progress",
            json!({
                "computed": bs.computed,
                "done_this_run": bs.computed - base,
                "total_pending": total,
                "last_id": bs.last_id,
            }),
        );
    }

    let cancelled = token.is_cancelled();
    send_sse(
        &hub,
        "hash_backfill.complete",
        json!({ "computed": bs.computed, "cancelled": cancelled }),
    );
    jm.finish(JOB_ID, Some(json!({ "computed": bs.computed })), None);
}

pub async fn start(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.job_manager.is_running(JOB_ID) {
        return (
            StatusCode::CONFLICT,
            Json(json!({"ok": false, "error": "already running"})),
        )
            .into_response();
    }
    let token = state.job_manager.start(JOB_ID, "Hash Backfill");
    let s = state.clone();
    tokio::spawn(async move { run_worker(s, token).await });
    Json(json!({"ok": true, "error": null, "data": {"status": "started"}})).into_response()
}

pub async fn cancel(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    if state.job_manager.cancel_job(JOB_ID) {
        Json(json!({"ok": true, "error": null, "data": {"status": "cancelling"}})).into_response()
    } else {
        (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "job not running"})),
        )
            .into_response()
    }
}

pub async fn status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let running = state.job_manager.is_running(JOB_ID);
    let bs = load_state(&state.config.project_root);
    let pending: i64 =
        sqlx::query_scalar("SELECT COUNT(*) FROM files WHERE is_deleted=0 AND hash IS NULL")
            .fetch_one(&state.db)
            .await
            .unwrap_or(0);

    Json(json!({
        "ok": true,
        "error": null,
        "data": {
            "running": running,
            "pending": pending,
            "computed": bs.computed,
            "last_id": bs.last_id,
            "paused": false,
        }
    }))
    .into_response()
}
