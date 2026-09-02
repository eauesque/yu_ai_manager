use std::{
    cmp::Ordering,
    path::{Path, PathBuf},
};

use axum::{
    body::Bytes,
    extract::{Extension, Path as AxumPath, State},
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

fn api_result(payload: Value) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => return Json(json!({"ok": true, "error": null, "data": other})).into_response(),
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    Json(Value::Object(body)).into_response()
}

/// Error branch mirrors Python `core/infra_core/api_errors.py::api_result`
/// exactly: it merges every extra key from the payload (not just `code`) onto
/// the top-level response, so `hint`/`zip_path`/`entry` etc. survive too.
fn api_result_status(payload: Value, status: StatusCode) -> Response {
    if status.is_client_error() || status.is_server_error() {
        let mut body = match payload {
            Value::Object(map) => map,
            other => {
                let mut map = serde_json::Map::new();
                map.insert("error".to_string(), other);
                map
            }
        };
        let message = body
            .get("error")
            .or_else(|| body.get("message"))
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| "Request failed".to_string());
        body.remove("error");
        body.remove("message");
        body.remove("ok");
        body.insert("ok".to_string(), Value::Bool(false));
        body.insert("error".to_string(), Value::String(message));
        return (status, Json(Value::Object(body))).into_response();
    }
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return (
                status,
                Json(json!({"ok": true, "error": null, "data": other})),
            )
                .into_response();
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    (status, Json(Value::Object(body))).into_response()
}

fn api_error(message: &str, code: &str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({
            "ok": false,
            "error": message,
            "code": code,
        })),
    )
        .into_response()
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn fwd_post(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return (
            StatusCode::SERVICE_UNAVAILABLE,
            Json(json!({"ok":false,"error":"unavailable"})),
        )
            .into_response();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .post(&url)
        .header("Content-Type", "application/json")
        .header("X-Remote-User", "yu-proxy-auth")
        .header("X-Requested-With", "XMLHttpRequest")
        .body(body)
        .send()
        .await
    {
        Ok(r) => {
            let s = r.status();
            r.bytes().await.map_or_else(
                |_| StatusCode::BAD_GATEWAY.into_response(),
                |b| (s, b).into_response(),
            )
        }
        Err(_) => StatusCode::BAD_GATEWAY.into_response(),
    }
}

// ===== extract-from-zip: native port of core/services_core/zip_extract_service.py =====
//
// Source of truth: `core/services_core/zip_extract_service.py` (also mirrored
// verbatim in `core/zip_api/extract_helpers.py`). Status codes, `code`
// values, and Japanese error strings below are copied 1:1 from those files.

/// Mirrors Python `_validate_internal_path`
/// (zip_extract_service.py:18-24). Rejects NUL bytes, absolute paths, and any
/// ".." path component. Runs *before* extraction on all three archive types.
fn validate_internal_path(internal_path: &str) -> bool {
    if internal_path.contains('\0') {
        return false;
    }
    let normalized = internal_path.replace('\\', "/");
    if normalized.starts_with('/') {
        return false;
    }
    !normalized.split('/').any(|part| part == "..")
}

/// Mirrors Python `_verify_extracted_path` (zip_extract_service.py:27-34):
/// a post-extraction containment check via `Path.resolve()`. Uses
/// `std::fs::canonicalize` (sequential realpath) rather than a "deepest
/// existing ancestor" shortcut — this repo has a prior incident where that
/// shortcut let a symlink escape the guard — and reuses `path_guard::path_is_within`
/// the same way `comfyui_bridge::resolve_checkpoint_path` does for already-canonical
/// paths. Both `extracted_path` and `extract_dir` are expected to already exist
/// on disk when this runs (the extraction wrote the file; `extract_dir` was
/// `create_dir_all`'d beforehand), matching when Python's `resolve()` call fires.
fn verify_extracted_path(extracted_path: &Path, extract_dir: &Path) -> bool {
    let (Ok(real_extracted), Ok(real_extract_dir)) =
        (extracted_path.canonicalize(), extract_dir.canonicalize())
    else {
        return false;
    };
    crate::path_guard::path_is_within(&real_extracted, &real_extract_dir)
}

fn is_7z_archive(path: &str) -> bool {
    path.to_lowercase().ends_with(".7z")
}

fn is_rar_archive(path: &str) -> bool {
    path.to_lowercase().ends_with(".rar")
}

/// Mirrors Python `validate_extract_target`
/// (zip_extract_service.py:37-43 / extract_helpers.py:47-53): `file_id`
/// falsy (missing/0) -> 400 `missing_file_id`; row missing or `path` has no
/// `!` separator -> 400 `not_zip_member`. Returns `(zip_path, internal_path)`
/// on success, split at the first `!` exactly like Python's
/// `path.split("!", 1)`.
async fn validate_extract_target(
    pool: &SqlitePool,
    file_id: Option<i64>,
) -> Result<Result<(String, String), (Value, StatusCode)>, sqlx::Error> {
    let Some(file_id) = file_id else {
        return Ok(Err((
            json!({"error": "file_id is required", "code": "missing_file_id"}),
            StatusCode::BAD_REQUEST,
        )));
    };
    let row: Option<String> = sqlx::query_scalar("SELECT path FROM files WHERE id=?")
        .bind(file_id)
        .fetch_optional(pool)
        .await?;
    let not_zip_member = || {
        Err((
            json!({"error": "アーカイブ内ファイルではありません", "code": "not_zip_member"}),
            StatusCode::BAD_REQUEST,
        ))
    };
    let Some(path) = row else {
        return Ok(not_zip_member());
    };
    match path.split_once('!') {
        Some((zip_path, internal_path)) => {
            Ok(Ok((zip_path.to_string(), internal_path.to_string())))
        }
        None => Ok(not_zip_member()),
    }
}

/// Mirrors Python zipfile's internal arcname sanitization performed inside
/// `ZipFile.extract()` (stdlib `zipfile.py::_extract_member` on POSIX, where
/// `os.sep == '/'` and there is no `os.altsep`): split on `/`, drop empty and
/// `.` components (`..` is already rejected by `validate_internal_path`
/// before this runs), rejoin as path components. Deliberately does NOT treat
/// `\` as a separator here — Python doesn't either on POSIX, so a literal
/// backslash in an entry name stays inside one filename component.
fn sanitize_arcname(internal_path: &str) -> PathBuf {
    let mut out = PathBuf::new();
    for part in internal_path.split('/') {
        if part.is_empty() || part == "." {
            continue;
        }
        out.push(part);
    }
    out
}

/// Mirrors Python `_extract_zip_member`
/// (zip_extract_service.py:59-90). Deliberately uses `ZipArchive::by_name`
/// for a **strict, exact-name** lookup — NOT
/// `download.rs::resolve_zip_entry_name`'s progressive relaxation (exact ->
/// normalized -> basename). Python's `zf.extract(internal_path, ...)` only
/// ever does an exact `NameToInfo` dict lookup; on miss it raises `KeyError`
/// -> 404 `zip_entry_not_found`. Relaxing the match here would make Rust
/// silently extract a *different* member than Python would reject for the
/// same input — do not "fix" this without re-declaring the divergence.
fn extract_zip_member_native(
    zip_path: &str,
    internal_path: &str,
) -> Result<String, (Value, StatusCode)> {
    if !Path::new(zip_path).exists() {
        return Err((
            json!({
                "error": "ZIPファイルが見つかりません",
                "code": "zip_not_found",
                "hint": "元ZIPが移動/削除されていないか確認してください",
            }),
            StatusCode::NOT_FOUND,
        ));
    }
    if !validate_internal_path(internal_path) {
        return Err((
            json!({"error": "Path traversal blocked", "code": "zip_path_traversal"}),
            StatusCode::BAD_REQUEST,
        ));
    }

    let extract_dir = Path::new(zip_path)
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("extracted");
    if std::fs::create_dir_all(&extract_dir).is_err() {
        return Err((
            json!({"error": "extract failed", "code": "zip_extract_error"}),
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    }

    let bad_zip_file = || {
        Err((
            json!({
                "error": "ZIPファイルが破損しているため解凍できません",
                "code": "bad_zip_file",
            }),
            StatusCode::UNPROCESSABLE_ENTITY,
        ))
    };
    let file = match std::fs::File::open(zip_path) {
        Ok(f) => f,
        Err(_) => return bad_zip_file(),
    };
    let mut archive = match zip::ZipArchive::new(file) {
        Ok(a) => a,
        Err(_) => return bad_zip_file(),
    };

    let mut entry = match archive.by_name(internal_path) {
        Ok(e) => e,
        Err(_) => {
            return Err((
                json!({
                    "error": "ZIP内に対象ファイルが見つかりません",
                    "code": "zip_entry_not_found",
                    "hint": "再スキャンでZIP内エントリを更新してください",
                }),
                StatusCode::NOT_FOUND,
            ));
        }
    };

    let extracted_path = extract_dir.join(sanitize_arcname(internal_path));
    if let Some(parent) = extracted_path.parent() {
        if std::fs::create_dir_all(parent).is_err() {
            return Err((
                json!({"error": "extract failed", "code": "zip_extract_error"}),
                StatusCode::INTERNAL_SERVER_ERROR,
            ));
        }
    }
    let write_result = std::fs::File::create(&extracted_path)
        .and_then(|mut out_file| std::io::copy(&mut entry, &mut out_file).map(|_| ()));
    if let Err(error) = write_result {
        tracing::error!(
            ?error,
            zip_path,
            internal_path,
            "failed to write extracted zip member"
        );
        return Err((
            json!({"error": "extract failed", "code": "zip_extract_error"}),
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    }

    if !verify_extracted_path(&extracted_path, &extract_dir) {
        let _ = std::fs::remove_file(&extracted_path);
        return Err((
            json!({"error": "Path traversal blocked", "code": "zip_path_traversal"}),
            StatusCode::BAD_REQUEST,
        ));
    }
    Ok(extracted_path.to_string_lossy().to_string())
}

/// Rust equivalent of Python's `core/sevenz_core/sevenz_cli.py::_find_cli`:
/// same three candidate binary names, first hit in `PATH` wins.
fn find_7z_cli() -> Option<PathBuf> {
    let path_var = std::env::var_os("PATH")?;
    for dir in std::env::split_paths(&path_var) {
        for name in ["7z", "7za", "7zz"] {
            let candidate = dir.join(name);
            if candidate.is_file() {
                return Some(candidate);
            }
        }
    }
    None
}

/// Mirrors Python `_extract_7z_member` (zip_extract_service.py:97-142).
/// Invokes the external 7z CLI exactly the way `sevenz_cli.extract_to_dir`
/// does: `<cli> x -y -o<extract_dir> -- <archive_path> <internal_path>`.
/// The 7z CLI itself does the real extraction (including path layout), so
/// unlike the native ZIP branch above, the expected output path is a direct
/// join (`extract_dir/internal_path`) with no component sanitization —
/// that matches Python's `os.path.join(extract_dir, internal_path.replace("/", os.sep))`
/// on POSIX exactly.
fn extract_7z_member(
    archive_path: &str,
    internal_path: &str,
) -> Result<String, (Value, StatusCode)> {
    if !Path::new(archive_path).exists() {
        return Err((
            json!({
                "error": "7zファイルが見つかりません",
                "code": "zip_not_found",
                "hint": "元7zが移動/削除されていないか確認してください",
            }),
            StatusCode::NOT_FOUND,
        ));
    }
    if !validate_internal_path(internal_path) {
        return Err((
            json!({"error": "Path traversal blocked", "code": "zip_path_traversal"}),
            StatusCode::BAD_REQUEST,
        ));
    }

    let Some(cli) = find_7z_cli() else {
        return Err((
            json!({
                "error": "7z CLI が必要です (7-Zip をインストールしてください)",
                "code": "missing_dependency",
            }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    };

    let extract_dir = Path::new(archive_path)
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("extracted");
    if std::fs::create_dir_all(&extract_dir).is_err() {
        return Err((
            json!({"error": "extract failed", "code": "zip_extract_error"}),
            StatusCode::INTERNAL_SERVER_ERROR,
        ));
    }

    let extraction_failed = || {
        Err((
            json!({
                "error": "7z extraction failed",
                "code": "zip_entry_not_found",
                "hint": "Rescan to update 7z entries",
            }),
            StatusCode::NOT_FOUND,
        ))
    };

    let output = std::process::Command::new(&cli)
        .arg("x")
        .arg("-y")
        .arg(format!("-o{}", extract_dir.display()))
        .arg("--")
        .arg(archive_path)
        .arg(internal_path)
        .output();

    match output {
        Ok(result) if !result.status.success() => {
            let stderr = String::from_utf8_lossy(&result.stderr).to_lowercase();
            if stderr.contains("corrupt")
                || stderr.contains("bad")
                || stderr.contains("cannot open")
            {
                return Err((
                    json!({
                        "error": "7z file is corrupted",
                        "code": "bad_zip_file",
                        "zip_path": archive_path,
                        "entry": internal_path,
                    }),
                    StatusCode::UNPROCESSABLE_ENTITY,
                ));
            }
            return extraction_failed();
        }
        Err(_) => return extraction_failed(),
        Ok(_) => {}
    }

    let extracted_path = extract_dir.join(internal_path);
    if !verify_extracted_path(&extracted_path, &extract_dir) {
        let _ = std::fs::remove_file(&extracted_path);
        return Err((
            json!({"error": "Path traversal blocked", "code": "zip_path_traversal"}),
            StatusCode::BAD_REQUEST,
        ));
    }
    if !extracted_path.exists() {
        return Err((
            json!({
                "error": "7z内に対象ファイルが見つかりません",
                "code": "zip_entry_not_found",
                "hint": "再スキャンで7z内エントリを更新してください",
            }),
            StatusCode::NOT_FOUND,
        ));
    }
    Ok(extracted_path.to_string_lossy().to_string())
}

/// RAR extraction — declared gap. Python uses the `rarfile` PyPI package;
/// this repo has no non-GPL Rust RAR crate, and CLAUDE.md bans new
/// GPL/LGPL/AGPL dependencies, so native RAR extraction is not implemented
/// here. Mirrors the *shape* of Python's own `ImportError` fallback
/// (`_extract_rar_member` when `rarfile` isn't installed) so the response is
/// identical either way — the only difference is that Rust always takes this
/// branch, where Python only does when `rarfile` is absent.
fn extract_rar_member(
    archive_path: &str,
    internal_path: &str,
) -> Result<String, (Value, StatusCode)> {
    if !Path::new(archive_path).exists() {
        return Err((
            json!({
                "error": "RARファイルが見つかりません",
                "code": "zip_not_found",
                "hint": "元RARが移動/削除されていないか確認してください",
            }),
            StatusCode::NOT_FOUND,
        ));
    }
    if !validate_internal_path(internal_path) {
        return Err((
            json!({"error": "Path traversal blocked", "code": "zip_path_traversal"}),
            StatusCode::BAD_REQUEST,
        ));
    }
    Err((
        json!({
            "error": "rarfile が必要です (pip install rarfile)",
            "code": "missing_dependency",
        }),
        StatusCode::INTERNAL_SERVER_ERROR,
    ))
}

/// Mirrors Python `extract_zip_member` dispatch
/// (zip_extract_service.py:53-57 / extract_helpers.py:60-65).
fn extract_archive_member(
    archive_path: &str,
    internal_path: &str,
) -> Result<String, (Value, StatusCode)> {
    if is_7z_archive(archive_path) {
        extract_7z_member(archive_path, internal_path)
    } else if is_rar_archive(archive_path) {
        extract_rar_member(archive_path, internal_path)
    } else {
        extract_zip_member_native(archive_path, internal_path)
    }
}

/// Mirrors Python `register_extracted_file`
/// (zip_extract_service.py:217-243). Python calls `scan_one(force=True,
/// compute_hash=False)`; the Rust equivalent choke point is
/// `sweep_common::upsert_files_from_paths` (doc'd there as the
/// "scan_one_regular equivalent" — reused as instructed rather than adding a
/// second import path). Column writes match Python exactly:
/// `extracted_from_zip` / `extracted_from_internal` / `extraction_date` go on
/// the *new* row; `extracted_to_file_id` goes on the *original* row
/// (`file_id`) and points at the new row's id — get this backwards and every
/// extracted-file breadcrumb points the wrong way.
async fn register_extracted_file(
    state: &SharedState,
    file_id: i64,
    new_path: &str,
    zip_path: &str,
    internal_path: &str,
) -> Option<i64> {
    let paths = vec![new_path.to_string()];
    let results = crate::routes::sweep_common::upsert_files_from_paths(state, &paths).await;
    let new_id = results.get(new_path).copied().flatten()?;

    let extraction_date = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);

    if let Err(error) = sqlx::query(
        "UPDATE files SET extracted_from_zip=?, extracted_from_internal=?, extraction_date=? WHERE id=?",
    )
    .bind(zip_path)
    .bind(internal_path)
    .bind(extraction_date)
    .bind(new_id)
    .execute(&state.db)
    .await
    {
        tracing::error!(?error, new_id, "extract-from-zip: failed to write extracted_from_zip metadata");
        return None;
    }

    if let Err(error) = sqlx::query("UPDATE files SET extracted_to_file_id=? WHERE id=?")
        .bind(new_id)
        .bind(file_id)
        .execute(&state.db)
        .await
    {
        tracing::error!(
            ?error,
            file_id,
            "extract-from-zip: failed to write extracted_to_file_id"
        );
        return None;
    }

    Some(new_id)
}

/// Mirrors the `file_id` coercion in `routes/zip_files.py::api_extract_from_zip`
/// (`clamp_sqlite_int(int(file_id))`, `TypeError`/`ValueError` suppressed)
/// combined with the Python truthiness check in
/// `validate_extract_target` (`if not file_id`): `0`/missing/non-numeric all
/// collapse to "missing" here. Declared divergence: a non-numeric JSON
/// *string* survives Python's `int()` failure as a truthy value and reaches
/// the DB query (yielding 400 `not_zip_member` there), whereas here it is
/// treated as missing (400 `missing_file_id`) — both are 400s, only the
/// `code` differs, and this input shape is outside the spec's required test
/// matrix.
/// Both narrowing casts below are deliberate and bounded. `f64 as i64`
/// saturates in Rust rather than wrapping (and NaN becomes 0), which matches
/// Python's `int()` refusing the value: either way the result is not a real
/// file id and `raw.filter(|&id| id != 0)` or the DB lookup rejects it. The
/// `i128 as i64` is preceded by a clamp into `i64`'s range on the same
/// expression, so it cannot lose anything.
#[allow(clippy::cast_possible_truncation)]
fn extract_file_id(value: &Value) -> Option<i64> {
    let raw = match value {
        Value::Number(n) => n.as_i64().or_else(|| n.as_f64().map(|f| f as i64)),
        Value::String(s) => s
            .trim()
            .parse::<i128>()
            .ok()
            .map(|v| v.clamp(i64::MIN as i128, i64::MAX as i128) as i64),
        _ => None,
    };
    raw.filter(|&id| id != 0)
}

/// POST /api/extract-from-zip — admin scope required.
///
/// Native Rust port of `routes/zip_files.py::api_extract_from_zip` ->
/// `core/zip_api/extract_ops.py::extract_from_zip` ->
/// `core/services_core/zip_extract_service.py::extract_from_archive`. See the
/// per-branch doc comments on the helpers above for exact source-line
/// mapping and any declared parity gaps (RAR, entry-name matching strictness).
pub async fn extract_from_zip(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Bytes,
) -> Response {
    if let Some(r) = admin_scope_error(&state, auth_context.as_ref()) {
        return r;
    }

    let file_id = serde_json::from_slice::<Value>(&body)
        .ok()
        .as_ref()
        .and_then(|value| value.get("file_id"))
        .and_then(extract_file_id);

    let target = match validate_extract_target(&state.db_read, file_id).await {
        Ok(Ok(pair)) => pair,
        Ok(Err((payload, status))) => return api_result_status(payload, status),
        Err(error) => {
            tracing::error!(
                ?error,
                "extract-from-zip: validate_extract_target query failed"
            );
            return api_result_status(
                json!({"error": "ZIP extraction failed", "code": "zip_extract_error"}),
                StatusCode::INTERNAL_SERVER_ERROR,
            );
        }
    };
    let (zip_path, internal_path) = target;

    let new_path = match extract_archive_member(&zip_path, &internal_path) {
        Ok(path) => path,
        Err((payload, status)) => return api_result_status(payload, status),
    };

    // `validate_extract_target` only reaches `Ok(Ok(..))` when `file_id` was
    // `Some`, so this is always populated by the time we get here.
    let file_id = file_id.expect("file_id validated by validate_extract_target");

    match register_extracted_file(&state, file_id, &new_path, &zip_path, &internal_path).await {
        Some(new_id) => api_result_status(
            json!({"success": true, "new_path": new_path, "new_file_id": new_id}),
            StatusCode::OK,
        ),
        None => api_result_status(
            json!({
                "error": "Failed to register extracted file",
                "code": "extract_register_failed",
            }),
            StatusCode::INTERNAL_SERVER_ERROR,
        ),
    }
}

async fn build_file_info(pool: &SqlitePool, file_id: i64) -> Result<Option<Value>, sqlx::Error> {
    let row = sqlx::query(
        "SELECT path, is_zip_member, extracted_from_zip, extracted_from_internal,
                extraction_date, extracted_to_file_id
         FROM files WHERE id=?",
    )
    .bind(file_id)
    .fetch_optional(pool)
    .await?;
    Ok(row.map(|row| {
        json!({
            "path": row.get::<String, _>("path"),
            "is_zip_member": row
                .try_get::<Option<i64>, _>("is_zip_member")
                .ok()
                .flatten()
                .unwrap_or(0) != 0,
            "extracted_from_zip": row.try_get::<Option<String>, _>("extracted_from_zip").ok().flatten(),
            "extracted_from_internal": row.try_get::<Option<String>, _>("extracted_from_internal").ok().flatten(),
            "extraction_date": row.try_get::<Option<i64>, _>("extraction_date").ok().flatten(),
            "extracted_to_file_id": row.try_get::<Option<i64>, _>("extracted_to_file_id").ok().flatten(),
        })
    }))
}

pub async fn open_folder(
    State(state): State<SharedState>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    let row: Option<String> =
        sqlx::query_scalar("SELECT path FROM files WHERE id=? AND is_deleted=0")
            .bind(file_id)
            .fetch_optional(&state.db_read)
            .await
            .unwrap_or(None);
    let path_str = match row {
        Some(p) => p,
        None => {
            return (
                StatusCode::NOT_FOUND,
                Json(json!({"ok":false,"error":"file_not_found","detail":"File not found"})),
            )
                .into_response();
        }
    };

    // Strip archive member suffix (e.g. "foo.zip!member.png" → "foo.zip")
    let fs_path = if let Some(idx) = path_str.find('!') {
        path_str[..idx].to_string()
    } else {
        path_str.clone()
    };
    let abs_path = std::path::Path::new(&fs_path)
        .canonicalize()
        .unwrap_or_else(|_| std::path::PathBuf::from(&fs_path));
    let dir = abs_path.parent().unwrap_or(&abs_path).to_path_buf();

    let dir_str = dir.to_string_lossy().to_string();

    #[cfg(target_os = "linux")]
    let cmd = std::process::Command::new("xdg-open").arg(&dir_str).spawn();
    #[cfg(target_os = "macos")]
    let cmd = std::process::Command::new("open")
        .arg("-R")
        .arg(&abs_path)
        .spawn();
    #[cfg(target_os = "windows")]
    let cmd = std::process::Command::new("explorer").arg(&dir_str).spawn();
    #[cfg(not(any(target_os = "linux", target_os = "macos", target_os = "windows")))]
    let cmd: Result<_, std::io::Error> = Err(std::io::Error::new(
        std::io::ErrorKind::Unsupported,
        "unsupported",
    ));

    if let Err(e) = cmd {
        tracing::warn!(?e, "open_folder: failed to launch file manager");
    }

    Json(json!({"ok":true,"error":null,"data":{"success":true,"path":dir_str}})).into_response()
}

pub async fn file_info(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_file_info(&state.db_read, file_id).await {
        Ok(Some(value)) => api_result(value),
        Ok(None) => api_result_status(
            json!({"error": "File not found", "code": "file_not_found"}),
            StatusCode::NOT_FOUND,
        ),
        Err(error) => {
            tracing::error!(?error, file_id, "file info failed");
            api_error(
                "Failed to get file info",
                "file_info_error",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

fn archive_part(path: &str) -> String {
    let lower = path.to_lowercase();
    let mut first: Option<(usize, usize)> = None;
    for ext in [".zip!", ".7z!", ".rar!"] {
        if let Some(idx) = lower.find(ext) {
            if first.is_none_or(|(first_idx, _)| idx < first_idx) {
                first = Some((idx, ext.len()));
            }
        }
    }
    if let Some((idx, ext_len)) = first {
        let sep = idx + ext_len - 1;
        return path[..sep].to_string();
    }
    path.to_string()
}

fn container_path(path: &str) -> String {
    let path = path.to_string();
    if path.contains('!') {
        return archive_part(&path);
    }
    let lower = path.to_lowercase();
    if lower.ends_with(".zip") || lower.ends_with(".7z") || lower.ends_with(".rar") {
        return path;
    }
    String::new()
}

fn member_name(path: &str) -> &str {
    path.split_once('!').map_or(path, |(_, name)| name)
}

#[derive(Debug, Eq, PartialEq)]
enum NaturalPart {
    Number(String),
    Text(String),
}

fn natural_parts(path: &str) -> Vec<NaturalPart> {
    let name = member_name(path).replace('\\', "/");
    let mut parts = Vec::new();
    let mut start = 0;
    let mut in_digit: Option<bool> = None;
    for (idx, ch) in name.char_indices() {
        let digit = ch.is_ascii_digit();
        match in_digit {
            None => in_digit = Some(digit),
            Some(current) if current != digit => {
                let part = &name[start..idx];
                if current {
                    parts.push(NaturalPart::Number(part.to_string()));
                } else {
                    parts.push(NaturalPart::Text(part.to_lowercase()));
                }
                start = idx;
                in_digit = Some(digit);
            }
            Some(_) => {}
        }
    }
    if let Some(current) = in_digit {
        let part = &name[start..];
        if current {
            parts.push(NaturalPart::Number(part.to_string()));
        } else {
            parts.push(NaturalPart::Text(part.to_lowercase()));
        }
    }
    parts
}

fn compare_number_text(left: &str, right: &str) -> Ordering {
    let left_trimmed = left.trim_start_matches('0');
    let right_trimmed = right.trim_start_matches('0');
    let left_norm = if left_trimmed.is_empty() {
        "0"
    } else {
        left_trimmed
    };
    let right_norm = if right_trimmed.is_empty() {
        "0"
    } else {
        right_trimmed
    };
    left_norm
        .len()
        .cmp(&right_norm.len())
        .then_with(|| left_norm.cmp(right_norm))
}

fn natural_cmp(left: &str, right: &str) -> Ordering {
    let left_parts = natural_parts(left);
    let right_parts = natural_parts(right);
    for (left_part, right_part) in left_parts.iter().zip(right_parts.iter()) {
        let order = match (left_part, right_part) {
            (NaturalPart::Number(a), NaturalPart::Number(b)) => compare_number_text(a, b),
            (NaturalPart::Number(_), NaturalPart::Text(_)) => Ordering::Less,
            (NaturalPart::Text(_), NaturalPart::Number(_)) => Ordering::Greater,
            (NaturalPart::Text(a), NaturalPart::Text(b)) => a.cmp(b),
        };
        if order != Ordering::Equal {
            return order;
        }
    }
    left_parts.len().cmp(&right_parts.len()).then_with(|| {
        member_name(left)
            .to_lowercase()
            .cmp(&member_name(right).to_lowercase())
    })
}

async fn build_container_members(
    pool: &SqlitePool,
    file_id: i64,
) -> Result<Result<Value, (Value, StatusCode)>, sqlx::Error> {
    let row = sqlx::query("SELECT id, path FROM files WHERE id=?")
        .bind(file_id)
        .fetch_optional(pool)
        .await?;
    let Some(row) = row else {
        return Ok(Err((
            json!({"error": "File not found", "code": "file_not_found"}),
            StatusCode::NOT_FOUND,
        )));
    };
    let row_id = row.get::<i64, _>("id");
    let path = row.get::<String, _>("path");
    let container_path = container_path(&path);
    if container_path.is_empty() {
        return Ok(Err((
            json!({"error": "Container not found for file", "code": "container_not_found"}),
            StatusCode::BAD_REQUEST,
        )));
    }
    let like = format!("{container_path}!%");
    let rows = sqlx::query(
        "SELECT id, path
         FROM files
         WHERE is_deleted=0
           AND path LIKE ?
         ORDER BY path",
    )
    .bind(like)
    .fetch_all(pool)
    .await?;
    let mut members = rows
        .into_iter()
        .map(|row| (row.get::<i64, _>("id"), row.get::<String, _>("path")))
        .collect::<Vec<_>>();
    members.sort_by(|left, right| natural_cmp(&left.1, &right.1));
    let member_ids = members.iter().map(|(id, _)| *id).collect::<Vec<_>>();
    let representatives = member_ids.iter().copied().take(4).collect::<Vec<_>>();
    let focus_id = if member_ids.contains(&row_id) {
        Some(row_id)
    } else {
        member_ids.first().copied()
    };
    Ok(Ok(json!({
        "success": true,
        "container_path": container_path,
        "member_count": member_ids.len(),
        "member_ids": member_ids,
        "representatives": representatives,
        "focus_id": focus_id,
    })))
}

pub async fn container_members(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(file_id): AxumPath<i64>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_container_members(&state.db_read, file_id).await {
        Ok(Ok(value)) => api_result(value),
        Ok(Err((payload, status))) => api_result_status(payload, status),
        Err(error) => {
            tracing::error!(?error, file_id, "container members failed");
            api_error(
                "Failed to get container members",
                "container_members_error",
                StatusCode::INTERNAL_SERVER_ERROR,
            )
        }
    }
}

#[cfg(test)]
mod tests {
    use std::{collections::HashSet, path::PathBuf, str::FromStr, sync::Arc};

    use axum::{
        body::{to_bytes, Bytes},
        extract::{Path as AxumPath, State},
        http::StatusCode,
        response::Response,
    };
    use serde_json::{json, Value};
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config, SharedState};

    async fn test_state(seed: &str) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (
               id INTEGER PRIMARY KEY,
               path TEXT NOT NULL,
               is_deleted INTEGER NOT NULL DEFAULT 0,
               is_zip_member INTEGER,
               extracted_from_zip TEXT,
               extracted_from_internal TEXT,
               extraction_date INTEGER,
               extracted_to_file_id INTEGER,
               mtime INTEGER,
               size INTEGER,
               meta_source TEXT,
               parser_version INTEGER,
               width INTEGER,
               height INTEGER
             );
             CREATE UNIQUE INDEX files_path_idx ON files(path);",
        )
        .execute(&pool)
        .await
        .unwrap();
        if !seed.is_empty() {
            sqlx::raw_sql(seed).execute(&pool).await.unwrap();
        }
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
    async fn file_info_returns_zip_metadata_and_404_payload() {
        let state = test_state(
            "INSERT INTO files(id, path, is_zip_member, extracted_from_zip,
                               extracted_from_internal, extraction_date, extracted_to_file_id)
             VALUES(1, '/tmp/archive.zip!dir/a.png', 1, '/tmp/archive.zip',
                    'dir/a.png', 1234, 9);",
        )
        .await;

        let value =
            json_body(super::file_info(State(state.clone()), None, AxumPath(1)).await).await;
        assert_eq!(value["path"], "/tmp/archive.zip!dir/a.png");
        assert_eq!(value["is_zip_member"], true);
        assert_eq!(value["extracted_from_zip"], "/tmp/archive.zip");
        assert_eq!(value["extracted_from_internal"], "dir/a.png");
        assert_eq!(value["extraction_date"], 1234);
        assert_eq!(value["extracted_to_file_id"], 9);

        let missing = json_body(super::file_info(State(state), None, AxumPath(99)).await).await;
        assert_eq!(
            missing,
            json!({"ok": false, "error": "File not found", "code": "file_not_found"})
        );
    }

    #[tokio::test]
    async fn container_members_resolves_archive_and_natural_sorts_members() {
        let state = test_state(
            "INSERT INTO files(id, path, is_deleted) VALUES
               (1, '/tmp/archive.zip', 0),
               (2, '/tmp/archive.zip!img10.png', 0),
               (3, '/tmp/archive.zip!img2.png', 0),
               (4, '/tmp/archive.zip!dir/img1.png', 0),
               (5, '/tmp/archive.zip!img1.png', 1),
               (6, '/tmp/other.zip!img1.png', 0);",
        )
        .await;

        let value =
            json_body(super::container_members(State(state), None, AxumPath(2)).await).await;

        assert_eq!(value["success"], true);
        assert_eq!(value["container_path"], "/tmp/archive.zip");
        assert_eq!(value["member_count"], 3);
        assert_eq!(value["member_ids"], json!([4, 3, 2]));
        assert_eq!(value["representatives"], json!([4, 3, 2]));
        assert_eq!(value["focus_id"], 2);
    }

    #[tokio::test]
    async fn container_members_rejects_non_archive_files() {
        let state =
            test_state("INSERT INTO files(id, path, is_deleted) VALUES(1, '/tmp/a.png', 0);").await;

        let value =
            json_body(super::container_members(State(state), None, AxumPath(1)).await).await;

        assert_eq!(
            value,
            json!({
                "ok": false,
                "error": "Container not found for file",
                "code": "container_not_found",
            })
        );
    }

    // ===== extract-from-zip =====

    fn make_zip(zip_path: &std::path::Path, entries: &[(&str, &[u8])]) {
        use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};
        let file = std::fs::File::create(zip_path).unwrap();
        let mut writer = ZipWriter::new(file);
        let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
        for (name, contents) in entries {
            writer.start_file(*name, options).unwrap();
            std::io::Write::write_all(&mut writer, contents).unwrap();
        }
        writer.finish().unwrap();
    }

    async fn insert_file_row(state: &SharedState, id: i64, path: &str) {
        sqlx::query("INSERT INTO files(id, path, is_deleted) VALUES(?, ?, 0)")
            .bind(id)
            .bind(path)
            .execute(&state.db)
            .await
            .unwrap();
    }

    async fn call_extract(state: SharedState, file_id_body: Value) -> (StatusCode, Value) {
        let body = Bytes::from(serde_json::to_vec(&file_id_body).unwrap());
        let response = super::extract_from_zip(State(state), None, body).await;
        let status = response.status();
        (status, json_body(response).await)
    }

    #[tokio::test]
    async fn extract_from_zip_success_writes_file_and_registers_row() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        make_zip(&zip_path, &[("dir/a.txt", b"hello world")]);

        let state = test_state("").await;
        insert_file_row(
            &state,
            1,
            &format!("{}!dir/a.txt", zip_path.to_string_lossy()),
        )
        .await;

        let (status, value) = call_extract(state.clone(), json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["success"], true);
        let new_path = value["new_path"].as_str().unwrap().to_string();
        assert!(std::path::Path::new(&new_path).exists());
        assert_eq!(std::fs::read(&new_path).unwrap(), b"hello world".to_vec());
        // Python's `zf.extract` preserves the member's directory structure under
        // the extract dir, so `new_path` — which is returned to the caller and
        // stored in the DB — must end in `extracted/dir/a.txt`, not a flattened
        // `extracted/a.txt`. Without this, replacing `sanitize_arcname` with a
        // basename-only version leaves this test green (verified 2026-08-13:
        // only the symlink-escape test caught that injection).
        let expected_tail = std::path::Path::new("extracted").join("dir").join("a.txt");
        assert!(
            std::path::Path::new(&new_path).ends_with(&expected_tail),
            "extracted path must keep the member's directory structure: {new_path} !~ {}",
            expected_tail.display()
        );
        let new_id = value["new_file_id"].as_i64().unwrap();

        let (extracted_from_zip, extracted_from_internal, extracted_to_file_id_on_original): (
            Option<String>,
            Option<String>,
            Option<i64>,
        ) = sqlx::query_as(
            "SELECT extracted_from_zip, extracted_from_internal, extracted_to_file_id FROM files WHERE id=?",
        )
        .bind(new_id)
        .fetch_one(&state.db)
        .await
        .unwrap();
        assert_eq!(
            extracted_from_zip.as_deref(),
            Some(zip_path.to_string_lossy().as_ref())
        );
        assert_eq!(extracted_from_internal.as_deref(), Some("dir/a.txt"));
        // extracted_to_file_id must be on the *original* (file_id=1) row, not the new one.
        assert_eq!(extracted_to_file_id_on_original, None);

        let original_extracted_to: Option<i64> =
            sqlx::query_scalar("SELECT extracted_to_file_id FROM files WHERE id=1")
                .fetch_one(&state.db)
                .await
                .unwrap();
        assert_eq!(original_extracted_to, Some(new_id));
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_dotdot_traversal() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        make_zip(&zip_path, &[("a.txt", b"x")]);

        let state = test_state("").await;
        insert_file_row(
            &state,
            1,
            &format!("{}!../evil.txt", zip_path.to_string_lossy()),
        )
        .await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["code"], "zip_path_traversal");
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_absolute_path_traversal() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        make_zip(&zip_path, &[("a.txt", b"x")]);

        let state = test_state("").await;
        insert_file_row(
            &state,
            1,
            &format!("{}!/etc/passwd", zip_path.to_string_lossy()),
        )
        .await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["code"], "zip_path_traversal");
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_nul_byte_traversal() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        make_zip(&zip_path, &[("a.txt", b"x")]);

        let state = test_state("").await;
        let internal = "a.txt\0evil";
        insert_file_row(
            &state,
            1,
            &format!("{}!{}", zip_path.to_string_lossy(), internal),
        )
        .await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["code"], "zip_path_traversal");
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_corrupted_zip() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        std::fs::write(&zip_path, b"not a real zip file").unwrap();

        let state = test_state("").await;
        insert_file_row(&state, 1, &format!("{}!a.txt", zip_path.to_string_lossy())).await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::UNPROCESSABLE_ENTITY);
        assert_eq!(value["code"], "bad_zip_file");
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_nonexistent_entry() {
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        make_zip(&zip_path, &[("a.txt", b"x")]);

        let state = test_state("").await;
        insert_file_row(
            &state,
            1,
            &format!("{}!missing.txt", zip_path.to_string_lossy()),
        )
        .await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::NOT_FOUND);
        assert_eq!(value["code"], "zip_entry_not_found");
    }

    #[tokio::test]
    async fn extract_from_zip_uses_strict_name_match_not_basename() {
        // Python's `zf.extract(internal_path)` is a strict `NameToInfo`
        // dict lookup — a request for "a.txt" must NOT resolve to an entry
        // stored as "sub/a.txt" just because the basenames match. Pins
        // fault-injection #3 (relaxing `archive.by_name` to a basename
        // fallback like `download.rs::resolve_zip_entry_name` does).
        let dir = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        make_zip(&zip_path, &[("sub/a.txt", b"nested")]);

        let state = test_state("").await;
        insert_file_row(&state, 1, &format!("{}!a.txt", zip_path.to_string_lossy())).await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::NOT_FOUND);
        assert_eq!(value["code"], "zip_entry_not_found");
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_symlink_escape_via_post_extraction_check() {
        // Pre-extraction validation (`validate_internal_path`) only rejects
        // literal ".."/leading-"/"/NUL entry names; it cannot see that a
        // *directory component* inside the extract dir is itself a symlink
        // pointing outside. This is exactly what the post-extraction
        // containment check (`verify_extracted_path`) exists to catch —
        // pins fault-injection #1 (removing that check).
        let dir = tempfile::tempdir().unwrap();
        let outside = tempfile::tempdir().unwrap();
        let zip_path = dir.path().join("archive.zip");
        // Entry name has no ".." component, so it sails through
        // `validate_internal_path`, but "link" is set up below as a
        // symlink out of the extract dir.
        make_zip(&zip_path, &[("link/evil.txt", b"escaped")]);

        let extract_dir = dir.path().join("extracted");
        std::fs::create_dir_all(&extract_dir).unwrap();
        #[cfg(unix)]
        std::os::unix::fs::symlink(outside.path(), extract_dir.join("link")).unwrap();

        let state = test_state("").await;
        insert_file_row(
            &state,
            1,
            &format!("{}!link/evil.txt", zip_path.to_string_lossy()),
        )
        .await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["code"], "zip_path_traversal");
        assert!(!outside.path().join("evil.txt").exists());
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_path_without_bang() {
        let state = test_state("").await;
        insert_file_row(&state, 1, "/tmp/not_an_archive_member.txt").await;

        let (status, value) = call_extract(state, json!({"file_id": 1})).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["code"], "not_zip_member");
    }

    #[tokio::test]
    async fn extract_from_zip_rejects_missing_file_id() {
        let state = test_state("").await;

        let (status, value) = call_extract(state, json!({})).await;
        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["code"], "missing_file_id");
    }
}
