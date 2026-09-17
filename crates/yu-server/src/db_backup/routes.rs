//! Write-path routes for the database backup subsystem.
//!
//! Port of the `create` / `restore` / `delete` / `backup-download` handlers in
//! `core/tools_api/routes_backup.py`. The read endpoints (`list`, `status`)
//! are ported separately and deliberately do not live here.
//!
//! Authorization mirrors Python exactly: these four are `require_local`, i.e.
//! loopback only, on top of the admin-scope check. That gate is invisible to
//! the parity harness — it drives both servers from loopback — so the unit
//! tests below are the only thing that holds it.

use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::sync::OnceLock;

use axum::{
    extract::{ConnectInfo, State},
    http::{header, StatusCode},
    response::{IntoResponse, Response},
    Extension, Json,
};
use serde_json::{json, Value};
use sqlx::ConnectOptions;
use tokio::sync::Mutex;

use super::ffi;
use crate::auth::{scope::require_admin_scope, AuthContext};
use crate::config_io::load as load_config_json;
use crate::routes::tools_fs::is_local;
use crate::state::SharedState;

/// SQLCipher key for the tags database.
///
/// Held here rather than on `Config` because adding a field to that struct
/// would touch all 67 of its construction sites, and the key is genuinely
/// process-wide and immutable: it comes from `--db-key` / `YU_DB_KEY` once at
/// start-up. Functions below take the key as a parameter so tests never touch
/// this global.
static DB_KEY: OnceLock<String> = OnceLock::new();

/// Serialises backups against each other, standing in for Python's
/// `_backup_lock`. Python uses a 5 second acquisition timeout and reports
/// "Another backup is already in progress" on failure; the same wait and the
/// same message are reproduced below.
static BACKUP_LOCK: Mutex<()> = Mutex::const_new(());

/// Record the database key at start-up. Calling twice keeps the first value.
pub fn set_db_key(key: &str) {
    let _ = DB_KEY.set(key.to_string());
}

fn db_key() -> &'static str {
    DB_KEY.get().map(String::as_str).unwrap_or("")
}

fn api_result(payload: Value) -> Response {
    // `if let` rather than a match with a wildcard arm: the non-object case is
    // one branch, not "every other variant", and spelling it this way keeps
    // the wildcard_enum_match_arm gate meaningful elsewhere.
    let Value::Object(mut body) = payload else {
        return Json(json!({"ok": true, "error": null, "data": payload})).into_response();
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

/// Apply Python's two gates in Python's order: admin scope, then loopback.
///
/// The message is the one `require_local("<label>")` builds, verbatim.
fn guard(
    state: &SharedState,
    auth: Option<&Extension<AuthContext>>,
    addr: Option<&Extension<ConnectInfo<SocketAddr>>>,
    label: &str,
) -> Option<Response> {
    if let Some(response) = require_admin_scope(state.config.pin_auth_enabled, auth.map(|e| &e.0)) {
        return Some(response);
    }
    if !is_local(addr.map(|e| &e.0)) {
        return Some(api_error(
            &format!("{label} is only available from localhost"),
            StatusCode::FORBIDDEN,
        ));
    }
    None
}

/// Read the backup section of the config *from disk*, not from the start-up
/// snapshot: `app_config` is frozen at launch, so a PUT to settings would not
/// be visible here until a restart.
fn backup_config(state: &SharedState) -> Value {
    load_config_json(&state.config.config_path)
}

fn max_generations(config: &Value) -> i64 {
    config
        .get("backup")
        .and_then(|b| b.get("max_generations"))
        .and_then(Value::as_i64)
        .unwrap_or(5)
}

/// Delete the backups retention says are surplus, oldest first.
///
/// Returns how many were removed. A file that cannot be deleted is logged and
/// skipped rather than failing the whole operation — Python retries three
/// times for Windows file locks and then warns, and a backup run must not fail
/// because an old generation is held open.
async fn enforce_retention(dir: &Path, config: &Value) -> usize {
    let names = match tokio::fs::read_dir(dir).await {
        Ok(mut entries) => {
            let mut collected = Vec::new();
            while let Ok(Some(entry)) = entries.next_entry().await {
                collected.push(entry.file_name().to_string_lossy().into_owned());
            }
            collected
        }
        Err(_) => return 0,
    };
    let victims = super::retention_victims(&names, max_generations(config));
    let mut removed = 0;
    for name in victims {
        let target = dir.join(&name);
        if remove_with_retry(&target).await {
            let meta = super::meta_path(&target);
            if meta.exists() {
                let _ = tokio::fs::remove_file(&meta).await;
            }
            removed += 1;
        } else {
            tracing::warn!("retention: could not delete old backup {name} (file locked?)");
        }
    }
    removed
}

/// Delete a file, retrying briefly for Windows file locks.
///
/// Python retries three times at 0.5s only for `PermissionError`, and treats a
/// missing file as success. Both behaviours are kept: a vanished file is the
/// outcome the caller wanted.
async fn remove_with_retry(path: &Path) -> bool {
    for attempt in 0..3 {
        match tokio::fs::remove_file(path).await {
            Ok(()) => return true,
            Err(e) if e.kind() == std::io::ErrorKind::NotFound => return true,
            Err(e) if e.kind() == std::io::ErrorKind::PermissionDenied && attempt < 2 => {
                tokio::time::sleep(std::time::Duration::from_millis(500)).await;
            }
            Err(_) => return false,
        }
    }
    false
}

/// Resolve the backup directory and make sure it exists.
async fn ensure_backup_dir(state: &SharedState, config: &Value) -> std::io::Result<PathBuf> {
    let dir = super::resolve_backup_dir(None, config, Path::new(&state.config.db_path));
    tokio::fs::create_dir_all(&dir).await?;
    Ok(dir)
}

/// Pick a destination filename that does not already exist.
///
/// Backup names carry a second-resolution timestamp, so two backups taken in
/// the same second collide. That is not hypothetical: `restore` takes a
/// `pre_restore` snapshot first, and restoring a backup made in the same
/// second made that snapshot **overwrite the very file being restored from** —
/// while this code already held it open for reading. Observed on a live
/// server: `restored_from` and `pre_restore_backup` came back as one name.
///
/// Python shares the format and the hole; this side declines to reuse a name
/// rather than reproducing it.
fn unique_destination(dir: &Path, now: chrono::DateTime<chrono::Local>) -> (String, PathBuf) {
    let base = super::make_filename(now);
    let candidate = dir.join(&base);
    if !candidate.exists() {
        return (base, candidate);
    }
    let stem = base.trim_end_matches(super::SUFFIX).to_string();
    for suffix in 1..1000 {
        let name = format!("{stem}_{suffix}{}", super::SUFFIX);
        let path = dir.join(&name);
        if !path.exists() {
            return (name, path);
        }
    }
    // A thousand backups inside one second is not a real scenario; falling
    // back to the plain name keeps this total rather than panicking.
    (base, candidate)
}

/// Shared body of every backup creation, whatever triggered it.
///
/// `reason` reaches the sidecar and the `list` output unchanged, so the
/// scheduler and the scan-complete hook can record why a backup exists.
pub async fn create_backup(state: &SharedState, reason: &str) -> Result<Value, String> {
    let Ok(_guard) =
        tokio::time::timeout(std::time::Duration::from_secs(5), BACKUP_LOCK.lock()).await
    else {
        return Err("Another backup is already in progress".to_string());
    };

    let db_path = PathBuf::from(&state.config.db_path);
    if !db_path.exists() {
        return Err("Database not found".to_string());
    }
    let config = backup_config(state);
    let dir = ensure_backup_dir(state, &config)
        .await
        .map_err(|e| format!("Backup failed: {e}"))?;

    // Pre-cleanup, matching Python: retry deleting leftovers a previous
    // retention pass could not remove before adding another generation.
    enforce_retention(&dir, &config).await;

    let now = chrono::Local::now();
    let (filename, dest) = unique_destination(&dir, now);

    let mut source = state
        .db
        .acquire()
        .await
        .map_err(|e| format!("Backup failed: {e}"))?;
    ffi::backup_to_path(&mut source, &dest, db_key())
        .await
        .map_err(|e| format!("Backup failed: {e}"))?;
    drop(source);

    write_meta(&dest, reason, &db_path, now).await;
    enforce_retention(&dir, &config).await;

    let size_bytes = tokio::fs::metadata(&dest)
        .await
        .map(|m| m.len())
        .unwrap_or(0);
    super::set_last_backup_time(now.timestamp() as f64);

    Ok(json!({
        "success": true,
        "filename": filename,
        "size_bytes": size_bytes,
        "reason": reason,
        "backup_dir": dir.to_string_lossy(),
    }))
}

/// Write the sidecar beside a freshly created backup.
///
/// Failures are logged, not propagated: Python treats an unreadable schema
/// version as a warning, and a backup that exists without its sidecar is far
/// better than one that was rolled back because a metadata write failed.
async fn write_meta(
    dest: &Path,
    reason: &str,
    source_db: &Path,
    now: chrono::DateTime<chrono::Local>,
) {
    let schema_version = read_schema_version(dest).await;
    let source_stat = tokio::fs::metadata(source_db).await.ok();
    let meta = super::BackupMeta {
        reason: reason.to_string(),
        created_at: super::naive_created_at(now),
        created_epoch: now.timestamp_micros() as f64 / 1_000_000.0,
        schema_version,
        source_db_path: source_db
            .canonicalize()
            .ok()
            .map(|p| p.to_string_lossy().into_owned()),
        source_db_size: source_stat.as_ref().map(|m| m.len()),
        source_db_mtime_ns: source_stat.as_ref().and_then(mtime_nanos),
    };
    match serde_json::to_string_pretty(&meta) {
        Ok(text) => {
            if let Err(e) = tokio::fs::write(super::meta_path(dest), text).await {
                tracing::warn!("backup sidecar could not be written: {e}");
            }
        }
        Err(e) => tracing::warn!("backup sidecar could not be serialised: {e}"),
    }
}

fn mtime_nanos(meta: &std::fs::Metadata) -> Option<i128> {
    let modified = meta.modified().ok()?;
    let since_epoch = modified.duration_since(std::time::UNIX_EPOCH).ok()?;
    Some(since_epoch.as_nanos() as i128)
}

/// Read `schema_version` out of a backup, with the key applied.
///
/// Applying the key is the whole point: the Python original opened the backup
/// unkeyed, which always raised on an encrypted build, so the field was
/// silently absent from every sidecar ever written.
async fn read_schema_version(backup: &Path) -> Option<i64> {
    let options = ffi::keyed_options(backup, db_key(), false).ok()?;
    let mut conn = options.connect().await.ok()?;
    sqlx::query_scalar::<_, i64>("SELECT version FROM schema_version ORDER BY version DESC LIMIT 1")
        .fetch_one(&mut conn)
        .await
        .ok()
}

// ── POST /api/tools/backup/create ─────────────────────────────────────

pub async fn backup_create(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = guard(&s, auth.as_ref(), addr.as_ref(), "Backup create") {
        return r;
    }
    match create_backup(&s, "manual").await {
        Ok(payload) => api_result(payload),
        Err(message) => api_error(&message, StatusCode::INTERNAL_SERVER_ERROR),
    }
}

// ── POST /api/tools/backup/restore ────────────────────────────────────

pub async fn backup_restore(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
    body: Option<Json<Value>>,
) -> Response {
    if let Some(r) = guard(&s, auth.as_ref(), addr.as_ref(), "Backup restore") {
        return r;
    }
    let filename = body
        .as_ref()
        .and_then(|Json(v)| v.get("filename"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if let Err(e) = super::validate_backup_filename(filename) {
        return api_error(e.message(), StatusCode::BAD_REQUEST);
    }

    let config = backup_config(&s);
    let dir = super::resolve_backup_dir(None, &config, Path::new(&s.config.db_path));
    let src = dir.join(filename);
    if !src.exists() {
        return api_error("Backup file not found", StatusCode::BAD_REQUEST);
    }

    // Validate by opening it with the key and looking for `files` — the same
    // decision Python now makes. A plaintext magic-byte check cannot be used:
    // on an encrypted build every backup this server writes is ciphertext.
    let Ok(options) = ffi::keyed_options(&src, db_key(), false) else {
        return api_error("Failed to read backup file", StatusCode::BAD_REQUEST);
    };
    let mut backup_conn = match options.connect().await {
        Ok(conn) => conn,
        Err(e) => {
            return api_error(
                &format!("Invalid SQLite file: {e}"),
                StatusCode::BAD_REQUEST,
            )
        }
    };
    // `trusted_schema = OFF` blocks a hostile backup from running code through
    // a view or trigger while we inspect it.
    if sqlx::query("PRAGMA trusted_schema = OFF")
        .execute(&mut backup_conn)
        .await
        .is_err()
    {
        return api_error("Failed to read backup file", StatusCode::BAD_REQUEST);
    }
    let has_files = sqlx::query_scalar::<_, String>(
        "SELECT name FROM sqlite_master WHERE type='table' AND name='files'",
    )
    .fetch_optional(&mut backup_conn)
    .await;
    match has_files {
        Ok(Some(_)) => {}
        Ok(None) => {
            return api_error(
                "Invalid database: 'files' table not found",
                StatusCode::BAD_REQUEST,
            )
        }
        Err(e) => {
            return api_error(
                &format!("Invalid SQLite file: {e}"),
                StatusCode::BAD_REQUEST,
            )
        }
    }

    // The schema version, which nothing used to look at. A restore writes the
    // backup over the live database, so an old backup silently produces a
    // database the next start refuses -- and the process doing the restoring
    // keeps running, so the operator sees success. This is the one path that
    // *creates* the stale-database condition rather than meeting it.
    //
    // Only the ahead case is refused. Restoring an older backup is a legitimate
    // recovery, and since v4.726.1 the launchers migrate it on the next start;
    // refusing it would take away the recovery itself. A backup from a newer
    // build is different: nobody can repair that, because no migration chain
    // goes backwards. Refusing is also the reversible answer -- upgrade the
    // binary and retry.
    let backup_version = read_schema_version(&src).await;
    let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
    if let Some(version) = backup_version {
        if version > expected {
            return api_error(
                &format!(
                    "This backup is at schema v{version}, which is newer than this build \
                     (v{expected}). Restoring it would leave a database this build cannot \
                     open, and no migration goes backwards. Use a newer build, then restore. \
                     Nothing has been modified."
                ),
                StatusCode::BAD_REQUEST,
            );
        }
    }

    let pre_restore = match create_backup(&s, "pre_restore").await {
        Ok(payload) => payload
            .get("filename")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string(),
        Err(message) => {
            tracing::warn!("pre-restore backup failed: {message}");
            String::new()
        }
    };

    let mut live = match s.db.acquire().await {
        Ok(conn) => conn,
        Err(e) => {
            return api_error(
                &format!("Restore failed: {e}"),
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    };
    if let Err(e) = ffi::copy_between(&mut backup_conn, &mut live).await {
        // Python returns 400 here; that is wrong — a failed copy is a server
        // fault, not bad input — and both sides now return 500.
        return api_error(
            &format!("Restore failed: {e}"),
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    }

    // Say it in the response, not only the log: the caller is a UI that reports
    // "restored successfully", and the database it just wrote needs a migration
    // before anything can open it. Silence here is what made this path able to
    // hand back a broken library as a success.
    let migration_notice = backup_version.filter(|v| *v < expected).map(|version| {
        let notice = format!(
            "The restored database is at schema v{version}; this build needs v{expected}. \
             Start it through the launcher and the Python version migrates it \
             automatically. A headless deployment (systemd, a bare yu-server) must run \
             the Python version once before it will start."
        );
        tracing::warn!("{notice}");
        (version, notice)
    });
    match migration_notice {
        Some((version, notice)) => api_result(json!({
            "success": true,
            "message": "Database restored successfully",
            "restored_from": filename,
            "pre_restore_backup": pre_restore,
            "schema_version": version,
            "needs_migration": true,
            "migration_notice": notice,
        })),
        None => api_result(json!({
            "success": true,
            "message": "Database restored successfully",
            "restored_from": filename,
            "pre_restore_backup": pre_restore,
        })),
    }
}

// ── POST /api/tools/backup/delete ─────────────────────────────────────

pub async fn backup_delete(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
    body: Option<Json<Value>>,
) -> Response {
    if let Some(r) = guard(&s, auth.as_ref(), addr.as_ref(), "Backup delete") {
        return r;
    }
    let filename = body
        .as_ref()
        .and_then(|Json(v)| v.get("filename"))
        .and_then(Value::as_str)
        .unwrap_or("");
    if let Err(e) = super::validate_backup_filename(filename) {
        return api_error(e.message(), StatusCode::BAD_REQUEST);
    }

    let config = backup_config(&s);
    let dir = super::resolve_backup_dir(None, &config, Path::new(&s.config.db_path));
    let target = dir.join(filename);
    if !target.exists() {
        return api_error("Backup file not found", StatusCode::BAD_REQUEST);
    }
    if let Err(e) = tokio::fs::remove_file(&target).await {
        return api_error(
            &format!("Failed to delete backup: {e}"),
            StatusCode::BAD_REQUEST,
        );
    }
    let meta = super::meta_path(&target);
    if meta.exists() {
        let _ = tokio::fs::remove_file(&meta).await;
    }
    api_result(json!({"success": true, "deleted": filename}))
}

// ── GET /api/tools/backup-download ────────────────────────────────────

/// Stream a one-off copy of the live database to the caller.
///
/// Distinct from the managed backups: it writes nowhere permanent and takes no
/// retention slot. Rust had no route for this at all, so the UI's download
/// button (`src/ts/tools-page/backup.ts`) was hitting a 404.
pub async fn backup_download(
    State(s): State<SharedState>,
    auth: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(r) = guard(&s, auth.as_ref(), addr.as_ref(), "Database backup") {
        return r;
    }
    let db_path = PathBuf::from(&s.config.db_path);
    if !db_path.exists() {
        return api_error("Database not found", StatusCode::NOT_FOUND);
    }

    let temp = match tempfile::Builder::new().suffix(".db").tempfile() {
        Ok(file) => file,
        Err(e) => {
            return api_error(
                &format!("Backup failed: {e}"),
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    };
    let temp_path = temp.path().to_path_buf();
    // The online backup API needs to create the destination itself, so hand it
    // a path rather than the already-open handle.
    drop(temp);

    let mut source = match s.db.acquire().await {
        Ok(conn) => conn,
        Err(e) => {
            return api_error(
                &format!("Backup failed: {e}"),
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    };
    if let Err(e) = ffi::backup_to_path(&mut source, &temp_path, db_key()).await {
        let _ = tokio::fs::remove_file(&temp_path).await;
        return api_error(
            &format!("Backup failed: {e}"),
            StatusCode::INTERNAL_SERVER_ERROR,
        );
    }
    drop(source);

    let bytes = match tokio::fs::read(&temp_path).await {
        Ok(bytes) => bytes,
        Err(e) => {
            let _ = tokio::fs::remove_file(&temp_path).await;
            return api_error(
                &format!("Backup failed: {e}"),
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };
    let _ = tokio::fs::remove_file(&temp_path).await;

    let stamp = chrono::Local::now().format("%Y%m%d_%H%M%S");
    let filename = format!("tags_backup_{stamp}.db");
    (
        [
            // Python serves the backup as application/x-sqlite3
            // (core/tools_api/routes_backup.py).
            (header::CONTENT_TYPE, "application/x-sqlite3".to_string()),
            (
                header::CONTENT_DISPOSITION,
                format!("attachment; filename=\"{filename}\""),
            ),
        ],
        bytes,
    )
        .into_response()
}

#[cfg(test)]
mod tests {
    use std::collections::HashSet;
    use std::sync::Arc;

    use axum::body::to_bytes;
    use axum::extract::ConnectInfo;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::str::FromStr;

    use super::*;
    use crate::state::{AppState, Config};

    async fn test_state() -> SharedState {
        let project_root = std::env::temp_dir().join("yu-backup-route-tests");
        let _ = std::fs::create_dir_all(&project_root);
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
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
                    rate_limit_trusted_proxies: HashSet::new(),
                    quick_lock_enabled: false,
                    pin_auth_enabled: false,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path: project_root.join("config.json"),
                    project_root,
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
                    wd_tagger_root: std::path::PathBuf::from("."),
                    clip_model_dir: std::path::PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    fn remote() -> Option<Extension<ConnectInfo<SocketAddr>>> {
        Some(Extension(ConnectInfo("203.0.113.9:5000".parse().unwrap())))
    }

    fn loopback() -> Option<Extension<ConnectInfo<SocketAddr>>> {
        Some(Extension(ConnectInfo("127.0.0.1:5000".parse().unwrap())))
    }

    async fn body_of(response: Response) -> Value {
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    #[tokio::test]
    async fn every_write_route_refuses_a_non_loopback_caller() {
        // The parity harness drives both servers from loopback, so it can
        // never see this gate. If these four assertions go, nothing else
        // notices that the backup write path became remotely reachable.
        let state = test_state().await;
        for (label, response) in [
            (
                "create",
                backup_create(State(state.clone()), None, remote()).await,
            ),
            (
                "restore",
                backup_restore(State(state.clone()), None, remote(), None).await,
            ),
            (
                "delete",
                backup_delete(State(state.clone()), None, remote(), None).await,
            ),
            (
                "download",
                backup_download(State(state.clone()), None, remote()).await,
            ),
        ] {
            assert_eq!(
                response.status(),
                StatusCode::FORBIDDEN,
                "{label} must reject a remote caller"
            );
        }
    }

    #[tokio::test]
    async fn a_missing_connect_info_is_not_treated_as_local() {
        // `is_local` returns false when the address is absent. Were it to
        // default the other way, a misconfigured proxy chain would open the
        // whole write path.
        let state = test_state().await;
        let response = backup_create(State(state), None, None).await;
        assert_eq!(response.status(), StatusCode::FORBIDDEN);
    }

    #[tokio::test]
    async fn restore_rejects_a_traversing_filename_before_touching_the_disk() {
        let state = test_state().await;
        let response = backup_restore(
            State(state),
            None,
            loopback(),
            Some(Json(json!({"filename": "../../etc/passwd"}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(body_of(response).await["error"], "Invalid filename");
    }

    #[tokio::test]
    async fn restore_rejects_a_foreign_filename_format() {
        let state = test_state().await;
        let response = backup_restore(
            State(state),
            None,
            loopback(),
            Some(Json(json!({"filename": "other_20260101_000000.db"}))),
        )
        .await;
        assert_eq!(
            body_of(response).await["error"],
            "Invalid backup filename format"
        );
    }

    #[tokio::test]
    async fn a_missing_filename_is_reported_as_missing_input() {
        let state = test_state().await;
        let response = backup_delete(State(state), None, loopback(), Some(Json(json!({})))).await;
        assert_eq!(body_of(response).await["error"], "filename is required");
    }

    #[tokio::test]
    async fn delete_reports_a_missing_backup_rather_than_succeeding() {
        let state = test_state().await;
        let response = backup_delete(
            State(state),
            None,
            loopback(),
            Some(Json(
                json!({"filename": "yu_ai_manager_20260101_000000.db"}),
            )),
        )
        .await;
        assert_eq!(body_of(response).await["error"], "Backup file not found");
    }

    #[tokio::test]
    async fn the_localhost_refusal_names_the_operation() {
        // Python builds the message from the label passed to `require_local`;
        // a single shared string would lose which operation was refused.
        let state = test_state().await;
        let create = body_of(backup_create(State(state.clone()), None, remote()).await).await;
        let restore =
            body_of(backup_restore(State(state.clone()), None, remote(), None).await).await;
        assert_eq!(
            create["error"],
            "Backup create is only available from localhost"
        );
        assert_eq!(
            restore["error"],
            "Backup restore is only available from localhost"
        );
    }

    /// Write a backup-shaped database at `version` into `dir`, returning its
    /// filename. It carries `files` so it clears the existing validity check,
    /// and `schema_version` so the new one has something to read.
    ///
    /// `stamp` keeps concurrent tests apart: `resolve_backup_dir` gives every
    /// test in this module the same directory, and cargo runs them in
    /// parallel, so a shared filename makes one test's fixture land in
    /// another's `CREATE TABLE`.
    async fn backup_at_version(dir: &Path, version: i64, stamp: &str) -> String {
        let filename = format!("yu_ai_manager_{stamp}.db");
        let path = dir.join(&filename);
        let _ = std::fs::remove_file(&path);
        let url = format!("sqlite://{}?mode=rwc", path.display());
        let pool = sqlx::SqlitePool::connect(&url)
            .await
            .expect("create backup");
        sqlx::query("CREATE TABLE files (id INTEGER PRIMARY KEY)")
            .execute(&pool)
            .await
            .expect("files");
        sqlx::query(
            "CREATE TABLE schema_version (version INTEGER PRIMARY KEY, \
             applied_at INTEGER NOT NULL, note TEXT NOT NULL)",
        )
        .execute(&pool)
        .await
        .expect("schema_version");
        sqlx::query("INSERT INTO schema_version VALUES (?, 0, 'fixture')")
            .bind(version)
            .execute(&pool)
            .await
            .expect("seed");
        pool.close().await;
        filename
    }

    #[tokio::test]
    async fn restore_refuses_a_backup_newer_than_this_build() {
        // Restoring is the one path that *creates* a database this build
        // cannot open, and the process doing it keeps running -- so the
        // operator sees success and finds out at the next start. An ahead
        // backup is the unrecoverable half: no migration goes backwards.
        let state = test_state().await;
        let dir = super::super::resolve_backup_dir(
            None,
            &backup_config(&state),
            Path::new(&state.config.db_path),
        );
        std::fs::create_dir_all(&dir).expect("backup dir");
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        let filename = backup_at_version(&dir, expected + 1, "20260101_000001").await;

        let response = backup_restore(
            State(state),
            None,
            loopback(),
            Some(Json(json!({ "filename": filename }))),
        )
        .await;
        let status = response.status();
        let body = body_of(response).await;
        let _ = std::fs::remove_file(dir.join(&filename));

        assert_eq!(status, StatusCode::BAD_REQUEST, "{body}");
        let error = body["error"].as_str().unwrap_or_default();
        assert!(
            error.contains("newer than this build"),
            "the refusal must name the direction: {error}"
        );
        assert!(
            error.contains("Nothing has been modified"),
            "the operator needs to know the live database is untouched: {error}"
        );
    }

    #[tokio::test]
    async fn restore_allows_an_older_backup_but_says_it_needs_migrating() {
        // Refusing the behind case would take away the recovery itself: an old
        // backup is a legitimate thing to restore, and the launchers migrate it
        // on the next start. What must not happen is restoring it *silently*.
        let state = test_state().await;
        let dir = super::super::resolve_backup_dir(
            None,
            &backup_config(&state),
            Path::new(&state.config.db_path),
        );
        std::fs::create_dir_all(&dir).expect("backup dir");
        let expected = tagdb_core::EXPECTED_PYTHON_SCHEMA_VERSION;
        let filename = backup_at_version(&dir, expected - 1, "20260101_000002").await;

        let response = backup_restore(
            State(state),
            None,
            loopback(),
            Some(Json(json!({ "filename": filename }))),
        )
        .await;
        let body = body_of(response).await;
        let _ = std::fs::remove_file(dir.join(&filename));

        // The copy itself runs against an in-memory live database here; what
        // this pins is the verdict and the notice, not the byte copy.
        assert_eq!(body["needs_migration"], json!(true), "{body}");
        assert_eq!(body["schema_version"], json!(expected - 1), "{body}");
        let notice = body["migration_notice"].as_str().unwrap_or_default();
        assert!(
            notice.contains("headless") || notice.contains("systemd"),
            "the notice must reach the deployment that cannot self-migrate: {notice}"
        );
    }

    #[test]
    fn retention_reads_max_generations_from_config_and_defaults_to_five() {
        assert_eq!(max_generations(&json!({})), 5);
        assert_eq!(
            max_generations(&json!({"backup": {"max_generations": 2}})),
            2
        );
        // A configured zero must survive: it disables retention, and treating
        // it as "unset" would silently start deleting backups.
        assert_eq!(
            max_generations(&json!({"backup": {"max_generations": 0}})),
            0
        );
    }

    #[test]
    fn a_second_backup_in_the_same_second_gets_its_own_filename() {
        // The live server produced `restored_from == pre_restore_backup`:
        // the pre-restore snapshot landed on the name of the backup being
        // restored and overwrote it, mid-read. Reusing a name here is data
        // loss, not an aesthetic problem.
        use chrono::TimeZone;
        let dir = tempfile::tempdir().unwrap();
        let now = chrono::Local
            .with_ymd_and_hms(2026, 9, 5, 7, 34, 23)
            .unwrap();

        let (first_name, first_path) = unique_destination(dir.path(), now);
        std::fs::write(&first_path, b"the backup being restored from").unwrap();

        let (second_name, second_path) = unique_destination(dir.path(), now);
        assert_ne!(
            first_name, second_name,
            "the same instant must not yield the same filename twice"
        );
        assert!(!second_path.exists(), "the new name must be free");
        assert_eq!(
            std::fs::read(&first_path).unwrap(),
            b"the backup being restored from",
            "the existing backup must be left untouched"
        );
    }

    #[test]
    fn the_deduplicated_name_still_passes_the_restore_validator() {
        // A name the validator rejects would be worse than the collision:
        // the backup would exist but could never be restored.
        use chrono::TimeZone;
        let dir = tempfile::tempdir().unwrap();
        let now = chrono::Local
            .with_ymd_and_hms(2026, 9, 5, 7, 34, 23)
            .unwrap();
        let (_, first) = unique_destination(dir.path(), now);
        std::fs::write(&first, b"x").unwrap();

        let (name, _) = unique_destination(dir.path(), now);
        assert!(
            super::super::validate_backup_filename(&name).is_ok(),
            "{name} must remain restorable"
        );
    }
}
