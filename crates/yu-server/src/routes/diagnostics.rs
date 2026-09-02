use std::{
    fs,
    path::{Path, PathBuf},
    process::Command,
    sync::{LazyLock, Mutex},
};

use axum::{
    body::Bytes,
    extract::{Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use chrono::{DateTime, NaiveDateTime, Utc};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::{
    mcp::diagnostics::{collect_checks, CheckResult, CheckStatus},
    state::SharedState,
};

const SAFE_MODE_FLAG: &str = "--safe-mode";
const SAFE_MODE_MARKER_NAME: &str = ".safe_mode_marker";
const STALE_UPDATE_PENDING_SECONDS: i64 = 7 * 24 * 60 * 60;

/// Cap on the number of doctor job results kept in memory, mirroring
/// Python's `routes/diagnostics.py::_MAX_DOCTOR_JOBS`.
const MAX_DOCTOR_JOBS: usize = 10;

/// In-process doctor job registry, mirroring Python's
/// `_doctor_jobs: OrderedDict[str, dict]`.
///
/// A `Vec<(String, Value)>` is used instead of a `HashMap` because Python's
/// `OrderedDict` has FIFO eviction semantics *and* leaves the position of an
/// existing key unchanged on reassignment (`_doctor_jobs[job_id] = value`
/// does not move `job_id` to the end). A `HashMap` has no order to preserve
/// that invariant; a `Vec` with in-place update (see `register_job`) does.
static DOCTOR_JOBS: LazyLock<Mutex<Vec<(String, Value)>>> =
    LazyLock::new(|| Mutex::new(Vec::new()));

/// Registers/updates a doctor job result, mirroring Python's
/// `_register_job`: an existing `job_id` is replaced in place (no reorder);
/// a new `job_id` is appended and the oldest entries are evicted (FIFO)
/// while the registry exceeds `MAX_DOCTOR_JOBS`.
fn register_job(jobs: &mut Vec<(String, Value)>, job_id: &str, value: Value) {
    if let Some(entry) = jobs.iter_mut().find(|(id, _)| id == job_id) {
        entry.1 = value;
        return;
    }
    jobs.push((job_id.to_string(), value));
    while jobs.len() > MAX_DOCTOR_JOBS {
        jobs.remove(0);
    }
}

fn register_doctor_job(job_id: &str, value: Value) {
    // Lock is dropped before this function returns; callers must not hold
    // it across an `.await` (std::sync::Mutex is not Send-safe to hold
    // across await points).
    let mut jobs = DOCTOR_JOBS
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    register_job(&mut jobs, job_id, value);
}

fn get_doctor_job(job_id: &str) -> Option<Value> {
    let jobs = DOCTOR_JOBS
        .lock()
        .unwrap_or_else(|poisoned| poisoned.into_inner());
    jobs.iter()
        .find(|(id, _)| id == job_id)
        .map(|(_, v)| v.clone())
}

fn check_status_str(status: CheckStatus) -> &'static str {
    match status {
        CheckStatus::Ok => "OK",
        CheckStatus::Warn => "WARN",
        CheckStatus::Error => "ERROR",
    }
}

/// Mirrors Python's `core/diagnostics/doctor_report.py::summarize`.
fn doctor_summary(results: &[CheckResult]) -> Value {
    let errors = results
        .iter()
        .filter(|r| r.status == CheckStatus::Error)
        .count();
    let warnings = results
        .iter()
        .filter(|r| r.status == CheckStatus::Warn)
        .count();
    json!({"errors": errors, "warnings": warnings})
}

/// Mirrors Python's `doctor_report.py::render_markdown` byte-for-byte,
/// including the escape order (`|` first, then newline) and the trailing
/// newline produced by appending an empty element before `join`.
///
/// Known divergence: Rust's `CheckResult` (ported in `mcp/diagnostics.rs`)
/// carries an extra `name` field that Python's 3-field `CheckResult` does
/// not have. `render_markdown` does not surface it (same table columns as
/// Python), but `render_json`'s `results` array will include it. This is an
/// accepted, documented difference -- see module docs on `mcp/diagnostics.rs`.
fn render_markdown(results: &[CheckResult]) -> String {
    let summary = doctor_summary(results);
    let errors = summary["errors"].as_u64().unwrap_or(0);
    let warnings = summary["warnings"].as_u64().unwrap_or(0);
    let mut lines: Vec<String> = vec![
        "# Environment Diagnosis".to_string(),
        String::new(),
        format!("- Errors: {errors}"),
        format!("- Warnings: {warnings}"),
        String::new(),
        "| Status | Check | Fix hint |".to_string(),
        "|---|---|---|".to_string(),
    ];
    for result in results {
        // NOTE: table column is labeled "Check" but Python fills it with
        // `message`, not the check's name. This is intentional -- do not
        // change to `result.name`, it would diverge from Python's output.
        let message = result.message.replace('|', "\\|").replace('\n', " ");
        let hint = result
            .fix_hint
            .clone()
            .unwrap_or_default()
            .replace('|', "\\|")
            .replace('\n', " ");
        lines.push(format!(
            "| {} | {} | {} |",
            check_status_str(result.status),
            message,
            hint
        ));
    }
    lines.push(String::new());
    lines.join("\n")
}

/// Mirrors Python's `doctor_report.py::render_json`. `created_at` uses
/// second-precision RFC3339 with a `+00:00` offset (not a `Z` suffix), to
/// match `dt.datetime.now(dt.UTC).isoformat(timespec="seconds")`.
fn render_json(results: &[CheckResult]) -> Value {
    let created_at = Utc::now().to_rfc3339_opts(chrono::SecondsFormat::Secs, false);
    json!({
        "schema": "yu://diagnostics/doctor/1",
        "created_at": created_at,
        "summary": doctor_summary(results),
        "results": results,
    })
}

/// Mirrors Python's `doctor_report.py::write_report_files`: writes a
/// `doctor_<local-timestamp>.md` and `.json` pair to `report_dir`,
/// appending `-1`, `-2`, ... if either file already exists for that
/// timestamp (matching Python's "either exists -> advance" collision rule).
///
/// JSON key order: Python serializes with `sort_keys=True`. This crate does
/// not enable serde_json's `preserve_order` feature anywhere in the
/// dependency graph (verified via `cargo tree -i serde_json` / grep over
/// `Cargo.lock` for `preserve_order`: no hits), so `serde_json::Map` is
/// backed by `BTreeMap` and already serializes keys in sorted order. Key
/// order therefore matches Python without any extra sorting step.
fn write_report_files(
    report_dir: &Path,
    report_md: &str,
    report_json: &Value,
) -> std::io::Result<(PathBuf, PathBuf)> {
    fs::create_dir_all(report_dir)?;
    let stem = format!("doctor_{}", chrono::Local::now().format("%Y%m%d-%H%M%S"));
    let mut md_path = report_dir.join(format!("{stem}.md"));
    let mut json_path = report_dir.join(format!("{stem}.json"));
    let mut suffix = 1;
    while md_path.exists() || json_path.exists() {
        md_path = report_dir.join(format!("{stem}-{suffix}.md"));
        json_path = report_dir.join(format!("{stem}-{suffix}.json"));
        suffix += 1;
    }
    fs::write(&md_path, report_md)?;
    let json_body = format!("{}\n", serde_json::to_string_pretty(report_json)?);
    fs::write(&json_path, json_body)?;
    Ok((md_path, json_path))
}

/// Builds the "done" job payload, mirroring Python's `_run_doctor_job`
/// success branch.
///
/// Extracted from `run_doctor_job` purely so the key names can be pinned by a
/// unit test without constructing an `AppState`. They are a contract with two
/// consumers at once: `src/ts/diagnostics-page/index.ts` reads `status`,
/// `summary` and `report_md` straight off the top level of the response
/// (`api_result` flattens this map), and Python emits the same six keys.
fn done_job_payload(
    report_md: &str,
    report_json: &Value,
    md_path: &Path,
    json_path: &Path,
) -> Value {
    json!({
        "status": "done",
        "report_md": report_md,
        "report_json": report_json,
        "summary": report_json["summary"].clone(),
        // Raw (non-redacted) path, matching Python's `str(md_path)`.
        "report_md_path": md_path.to_string_lossy(),
        "report_json_path": json_path.to_string_lossy(),
    })
}

async fn run_doctor_job(state: SharedState, job_id: String) {
    let checks = collect_checks(&state).await;
    let report_md = render_markdown(&checks);
    let report_json = render_json(&checks);
    let report_dir = state.config.project_root.join("reports");
    match write_report_files(&report_dir, &report_md, &report_json) {
        Ok((md_path, json_path)) => {
            register_doctor_job(
                &job_id,
                done_job_payload(&report_md, &report_json, &md_path, &json_path),
            );
        }
        Err(err) => {
            register_doctor_job(
                &job_id,
                json!({"status": "error", "error": err.to_string()}),
            );
        }
    }
}

#[derive(Deserialize)]
pub struct OpenRepairFolderBody {
    pub repair_dir: Option<String>,
}

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

fn api_error(msg: &str, code: &str, status: StatusCode) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": msg, "code": code})),
    )
        .into_response()
}

fn data_dir(project_root: &Path) -> PathBuf {
    std::env::var_os("TAGDB_DATA_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| project_root.join("data"))
}

fn default_repair_root(project_root: &Path) -> PathBuf {
    data_dir(project_root).join("repair")
}

fn is_safe_mode_from_args<I, S>(args: I) -> bool
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    args.into_iter()
        .skip(1)
        .any(|arg| arg.as_ref() == SAFE_MODE_FLAG)
}

fn safe_mode_payload<I, S>(data_dir: &Path, args: I) -> Value
where
    I: IntoIterator<Item = S>,
    S: AsRef<str>,
{
    json!({
        "safe_mode": is_safe_mode_from_args(args),
        "marker_exists": data_dir.join(SAFE_MODE_MARKER_NAME).is_file(),
    })
}

fn resolve_repair_dir(repair_root: &Path, value: Option<&str>) -> Result<PathBuf, String> {
    let value = value
        .filter(|value| !value.trim().is_empty())
        .ok_or_else(|| "repair_dir is required".to_string())?;
    let root = repair_root
        .canonicalize()
        .map_err(|err| format!("repair root unavailable: {err}"))?;
    let path = PathBuf::from(value)
        .canonicalize()
        .map_err(|err| format!("repair_dir unavailable: {err}"))?;
    if !path.starts_with(&root) {
        return Err("repair_dir must be under repair root".to_string());
    }
    Ok(path)
}

fn is_wsl() -> bool {
    fs::read_to_string("/proc/version")
        .map(|text| {
            let lower = text.to_ascii_lowercase();
            lower.contains("microsoft") || lower.contains("wsl")
        })
        .unwrap_or(false)
}

fn spawn_repair_folder(path: &Path) -> std::io::Result<()> {
    let mut command = if cfg!(target_os = "windows") {
        Command::new("explorer")
    } else if is_wsl() {
        Command::new("explorer.exe")
    } else if cfg!(target_os = "macos") {
        Command::new("open")
    } else {
        Command::new("xdg-open")
    };
    command.arg(path).spawn().map(|_| ())
}

fn parse_created_at(raw: &str) -> Result<DateTime<Utc>, chrono::ParseError> {
    DateTime::parse_from_rfc3339(raw)
        .map(|dt| dt.with_timezone(&Utc))
        .or_else(|_| {
            NaiveDateTime::parse_from_str(raw, "%Y-%m-%dT%H:%M:%S%.f").map(|naive| naive.and_utc())
        })
}

fn cleanup_stale_update_pending(
    project_root: &Path,
    now_rfc3339: &str,
) -> Result<(usize, Vec<String>), String> {
    let pending_dir = project_root.join("data").join("update_pending");
    if !pending_dir.exists() {
        return Ok((0, Vec::new()));
    }
    let now = parse_created_at(now_rfc3339).map_err(|err| err.to_string())?;
    let mut paths: Vec<PathBuf> = fs::read_dir(&pending_dir)
        .map_err(|err| err.to_string())?
        .filter_map(Result::ok)
        .map(|entry| entry.path())
        .filter(|path| path.extension().is_some_and(|ext| ext == "json"))
        .collect();
    paths.sort();

    let mut deleted = Vec::new();
    for path in paths {
        let mut remove = false;
        if let Ok(raw) = fs::read_to_string(&path) {
            match serde_json::from_str::<Value>(&raw)
                .ok()
                .and_then(|value| value.get("created_at").map(ToString::to_string))
            {
                Some(raw_created_at) => {
                    let trimmed = raw_created_at.trim_matches('"');
                    match parse_created_at(trimmed) {
                        Ok(created_at) => {
                            if (now - created_at).num_seconds() > STALE_UPDATE_PENDING_SECONDS {
                                remove = true;
                            }
                        }
                        Err(_) => remove = true,
                    }
                }
                None => remove = true,
            }
        } else {
            remove = true;
        }
        if remove && fs::remove_file(&path).is_ok() {
            if let Some(name) = path.file_name().and_then(|name| name.to_str()) {
                deleted.push(name.to_string());
            }
        }
    }
    Ok((deleted.len(), deleted))
}

pub async fn safe_mode(State(state): State<SharedState>) -> Response {
    api_result(safe_mode_payload(
        &data_dir(&state.config.project_root),
        std::env::args(),
    ))
}

pub async fn open_repair_folder(
    State(state): State<SharedState>,
    body: Option<Json<OpenRepairFolderBody>>,
) -> Response {
    let repair_dir = body.and_then(|Json(body)| body.repair_dir);
    match resolve_repair_dir(
        &default_repair_root(&state.config.project_root),
        repair_dir.as_deref(),
    )
    .and_then(|path| {
        spawn_repair_folder(&path)
            .map_err(|err| err.to_string())
            .map(|_| path)
    }) {
        Ok(path) => api_result(json!({"repair_dir": path.to_string_lossy()})),
        Err(err) => api_error(&err, "open_repair_folder_failed", StatusCode::BAD_REQUEST),
    }
}

pub async fn cleanup_update_pending(State(state): State<SharedState>) -> Response {
    let now = Utc::now().to_rfc3339();
    match cleanup_stale_update_pending(&state.config.project_root, &now) {
        Ok((deleted, names)) => api_result(json!({"deleted": deleted, "names": names})),
        Err(err) => api_error(
            &err,
            "cleanup_update_pending_failed",
            StatusCode::BAD_REQUEST,
        ),
    }
}

fn py_unavailable() -> Response {
    (
        StatusCode::SERVICE_UNAVAILABLE,
        Json(json!({"ok": false, "error": "Python backend unavailable", "code": "python_unavailable"})),
    )
        .into_response()
}

async fn fwd_get(state: &SharedState, path: &str) -> Response {
    if state.config.python_url.is_empty() {
        return py_unavailable();
    }
    let url = format!("{}{}", state.config.python_url.trim_end_matches('/'), path);
    match state
        .python_client
        .get(&url)
        .header("X-Remote-User", "yu-proxy-auth")
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

async fn fwd_post(state: &SharedState, path: &str, body: Bytes) -> Response {
    if state.config.python_url.is_empty() {
        return py_unavailable();
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

/// POST /api/diagnostics/bug-report
pub async fn bug_report() -> impl IntoResponse {
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(json!({"ok": false, "error": "not implemented"})),
    )
}

/// POST /api/diagnostics/doctor
///
/// Mirrors Python's `api_doctor` + `_run_doctor_job`: registers a "running"
/// job, spawns the check/render/write pipeline in the background, and
/// returns the job id immediately so the client can poll
/// `GET /api/diagnostics/doctor/{job_id}`.
pub async fn doctor_start(State(state): State<SharedState>) -> Response {
    let job_id = uuid::Uuid::new_v4().to_string();
    register_doctor_job(&job_id, json!({"status": "running"}));

    let state_for_task = state.clone();
    let job_id_for_task = job_id.clone();
    tokio::spawn(async move {
        run_doctor_job(state_for_task, job_id_for_task).await;
    });

    api_result(json!({"job_id": job_id, "status": "running"}))
}

/// GET /api/diagnostics/doctor/:job_id
///
/// Mirrors Python's `api_doctor_status`.
pub async fn doctor_status(AxumPath(job_id): AxumPath<String>) -> Response {
    match get_doctor_job(&job_id) {
        Some(job) => api_result(job),
        None => api_error("Job not found", "job_not_found", StatusCode::NOT_FOUND),
    }
}

fn zip_dir_to_path(repair_dir: &Path) -> Result<PathBuf, String> {
    if !repair_dir.is_dir() {
        return Err(format!("{} is not a directory", repair_dir.display()));
    }
    let zip_path = repair_dir.with_extension("zip");
    let file = std::fs::File::create(&zip_path).map_err(|e| e.to_string())?;
    let mut writer = zip::ZipWriter::new(file);
    let options = zip::write::SimpleFileOptions::default()
        .compression_method(zip::CompressionMethod::Deflated);
    zip_collect(repair_dir, repair_dir, &mut writer, options)?;
    writer.finish().map_err(|e| e.to_string())?;
    Ok(zip_path)
}

fn zip_collect(
    root: &Path,
    dir: &Path,
    writer: &mut zip::ZipWriter<std::fs::File>,
    options: zip::write::SimpleFileOptions,
) -> Result<(), String> {
    let mut entries: Vec<PathBuf> = std::fs::read_dir(dir)
        .map_err(|e| e.to_string())?
        .filter_map(|e| e.ok().map(|e| e.path()))
        .collect();
    entries.sort();
    for path in entries {
        if path.is_dir() {
            zip_collect(root, &path, writer, options)?;
        } else {
            let rel = path.strip_prefix(root).map_err(|e| e.to_string())?;
            let name = rel.to_string_lossy().replace('\\', "/");
            writer
                .start_file(name, options)
                .map_err(|e| e.to_string())?;
            let data = std::fs::read(&path).map_err(|e| e.to_string())?;
            use std::io::Write;
            writer.write_all(&data).map_err(|e| e.to_string())?;
        }
    }
    Ok(())
}

/// POST /api/diagnostics/zip-repair
pub async fn zip_repair(
    State(state): State<SharedState>,
    body: Option<Json<serde_json::Value>>,
) -> Response {
    let repair_dir_str = body
        .as_ref()
        .and_then(|Json(v)| v.get("repair_dir"))
        .and_then(|v| v.as_str())
        .unwrap_or("");
    let repair_root = default_repair_root(&state.config.project_root);
    match resolve_repair_dir(&repair_root, Some(repair_dir_str)) {
        Err(err) => api_error(&err, "zip_repair_failed", StatusCode::BAD_REQUEST),
        Ok(path) => match zip_dir_to_path(&path) {
            Ok(zip_path) => api_result(json!({
                "repair_dir": path.to_string_lossy(),
                "zip_path": zip_path.to_string_lossy()
            })),
            Err(err) => api_error(&err, "zip_repair_failed", StatusCode::INTERNAL_SERVER_ERROR),
        },
    }
}

#[cfg(test)]
mod tests {
    use std::fs;

    use axum::http::StatusCode;
    use serde_json::{json, Value};
    use tempfile::TempDir;

    #[test]
    fn safe_mode_uses_args_and_marker_file() {
        let temp = TempDir::new().unwrap();
        let marker = temp.path().join(".safe_mode_marker");
        fs::write(&marker, "safe-mode\n").unwrap();

        assert!(super::is_safe_mode_from_args(["yu-server", "--safe-mode"]));
        assert!(!super::is_safe_mode_from_args(["yu-server"]));
        assert!(
            super::safe_mode_payload(temp.path(), ["yu-server"])["marker_exists"]
                .as_bool()
                .unwrap()
        );
    }

    #[test]
    fn repair_dir_must_stay_under_repair_root() {
        let temp = TempDir::new().unwrap();
        let repair_root = temp.path().join("data").join("repair");
        let allowed = repair_root.join("20260518-153012");
        let outside = temp.path().join("elsewhere");
        fs::create_dir_all(&allowed).unwrap();
        fs::create_dir_all(&outside).unwrap();

        assert_eq!(
            super::resolve_repair_dir(&repair_root, Some(allowed.to_str().unwrap())).unwrap(),
            allowed.canonicalize().unwrap()
        );
        assert_eq!(
            super::resolve_repair_dir(&repair_root, Some(outside.to_str().unwrap()))
                .unwrap_err()
                .to_string(),
            "repair_dir must be under repair root"
        );
        assert_eq!(
            super::resolve_repair_dir(&repair_root, None)
                .unwrap_err()
                .to_string(),
            "repair_dir is required"
        );
    }

    #[cfg(unix)]
    #[test]
    fn repair_dir_rejects_symlink_escape() {
        use std::os::unix::fs::symlink;

        let temp = TempDir::new().unwrap();
        let repair_root = temp.path().join("data").join("repair");
        let outside = temp.path().join("elsewhere");
        let link = repair_root.join("link");
        fs::create_dir_all(&repair_root).unwrap();
        fs::create_dir_all(&outside).unwrap();
        symlink(&outside, &link).unwrap();

        assert_eq!(
            super::resolve_repair_dir(&repair_root, Some(link.to_str().unwrap()))
                .unwrap_err()
                .to_string(),
            "repair_dir must be under repair root"
        );
    }

    #[test]
    fn cleanup_update_pending_deletes_stale_and_unreadable_json_only() {
        let temp = TempDir::new().unwrap();
        let pending = temp.path().join("data").join("update_pending");
        fs::create_dir_all(&pending).unwrap();
        fs::write(
            pending.join("old.json"),
            json!({"created_at": "2026-06-01T00:00:00+00:00"}).to_string(),
        )
        .unwrap();
        fs::write(
            pending.join("fresh.json"),
            json!({"created_at": "2026-06-10T00:00:00+00:00"}).to_string(),
        )
        .unwrap();
        fs::write(pending.join("broken.json"), "{").unwrap();
        fs::write(pending.join("ignore.txt"), "not json").unwrap();

        let result =
            super::cleanup_stale_update_pending(temp.path(), "2026-06-12T00:00:00+00:00").unwrap();

        assert_eq!(
            result,
            (2, vec!["broken.json".to_string(), "old.json".to_string()])
        );
        assert!(pending.join("fresh.json").exists());
        assert!(pending.join("ignore.txt").exists());
    }

    use crate::mcp::diagnostics::{CheckResult, CheckStatus};

    fn sample_check(status: CheckStatus, message: &str, fix_hint: Option<&str>) -> CheckResult {
        CheckResult {
            name: "sample_check",
            status,
            message: message.to_string(),
            fix_hint: fix_hint.map(str::to_string),
        }
    }

    #[test]
    fn check_status_strings_agree_with_the_json_serialization_for_every_variant() {
        // `check_status_str` (used by the markdown table) and serde's
        // `rename_all = "UPPERCASE"` (used by `render_json`'s `results`) are
        // two independent mappings of the same enum. If they drift, a single
        // report's table and its JSON disagree about the same check, and
        // nothing else notices. Python has one mapping, so both must equal it.
        for (status, expected) in [
            (CheckStatus::Ok, "OK"),
            (CheckStatus::Warn, "WARN"),
            (CheckStatus::Error, "ERROR"),
        ] {
            assert_eq!(super::check_status_str(status), expected);
            assert_eq!(
                serde_json::to_value(status).unwrap(),
                json!(expected),
                "JSON serialization must match the markdown string for {expected}"
            );
        }
    }

    #[test]
    fn render_markdown_emits_every_status_string() {
        let md = super::render_markdown(&[
            sample_check(CheckStatus::Ok, "fine", None),
            sample_check(CheckStatus::Warn, "hmm", None),
            sample_check(CheckStatus::Error, "bad", None),
        ]);

        assert!(md.contains("| OK | fine |  |"), "{md:?}");
        assert!(md.contains("| WARN | hmm |  |"), "{md:?}");
        assert!(md.contains("| ERROR | bad |  |"), "{md:?}");
    }

    #[test]
    fn done_job_payload_pins_the_key_names_the_frontend_reads() {
        let report_json =
            json!({"schema": "yu://diagnostics/doctor/1", "summary": {"errors": 2, "warnings": 1}});
        let payload = super::done_job_payload(
            "# md",
            &report_json,
            std::path::Path::new("/tmp/doctor.md"),
            std::path::Path::new("/tmp/doctor.json"),
        );

        let mut keys: Vec<&str> = payload
            .as_object()
            .unwrap()
            .keys()
            .map(String::as_str)
            .collect();
        keys.sort_unstable();
        assert_eq!(
            keys,
            vec![
                "report_json",
                "report_json_path",
                "report_md",
                "report_md_path",
                "status",
                "summary",
            ],
            "these key names are the contract with diagnostics-page/index.ts and Python's _run_doctor_job"
        );
        assert_eq!(payload["status"], json!("done"));
        assert_eq!(payload["report_md"], json!("# md"));
        assert_eq!(payload["summary"], json!({"errors": 2, "warnings": 1}));
        assert_eq!(payload["report_md_path"], json!("/tmp/doctor.md"));
        assert_eq!(payload["report_json_path"], json!("/tmp/doctor.json"));
    }

    #[test]
    fn register_job_updates_existing_key_in_place_without_reordering() {
        let mut jobs: Vec<(String, Value)> = Vec::new();
        super::register_job(&mut jobs, "a", json!({"status": "running"}));
        super::register_job(&mut jobs, "b", json!({"status": "running"}));
        super::register_job(&mut jobs, "a", json!({"status": "done"}));

        assert_eq!(
            jobs.iter().map(|(id, _)| id.as_str()).collect::<Vec<_>>(),
            vec!["a", "b"],
            "updating an existing job_id must not move it to the end"
        );
        assert_eq!(jobs[0].1, json!({"status": "done"}));
    }

    #[test]
    fn register_job_evicts_fifo_only_past_the_cap() {
        let mut jobs: Vec<(String, Value)> = Vec::new();
        for i in 0..super::MAX_DOCTOR_JOBS {
            super::register_job(&mut jobs, &format!("job-{i}"), json!({"status": "running"}));
        }
        assert_eq!(
            jobs.len(),
            super::MAX_DOCTOR_JOBS,
            "at the cap, nothing is evicted yet"
        );
        assert_eq!(jobs[0].0, "job-0");

        super::register_job(
            &mut jobs,
            &format!("job-{}", super::MAX_DOCTOR_JOBS),
            json!({"status": "running"}),
        );
        assert_eq!(
            jobs.len(),
            super::MAX_DOCTOR_JOBS,
            "exceeding the cap evicts exactly one"
        );
        assert_eq!(
            jobs[0].0, "job-1",
            "oldest entry (job-0) must be evicted first"
        );
    }

    #[test]
    fn doctor_summary_counts_errors_and_warnings_only() {
        let results = vec![
            sample_check(CheckStatus::Ok, "ok", None),
            sample_check(CheckStatus::Warn, "warn", None),
            sample_check(CheckStatus::Error, "err1", None),
            sample_check(CheckStatus::Error, "err2", None),
        ];
        assert_eq!(
            super::doctor_summary(&results),
            json!({"errors": 2, "warnings": 1})
        );
    }

    #[test]
    fn render_markdown_escapes_pipes_before_newlines_and_ends_with_newline() {
        let results = vec![sample_check(
            CheckStatus::Error,
            "a | b\nc",
            Some("fix | it\nnow"),
        )];
        let md = super::render_markdown(&results);

        assert!(
            md.ends_with('\n'),
            "output must end with a trailing newline"
        );
        assert!(
            md.contains("| ERROR | a \\| b c | fix \\| it now |"),
            "pipes must be escaped and newlines replaced with spaces, in that order: {md:?}"
        );
        assert!(md.starts_with("# Environment Diagnosis\n\n- Errors: 1\n- Warnings: 0\n"));
    }

    #[test]
    fn render_json_created_at_uses_offset_not_z_suffix() {
        let results = vec![sample_check(CheckStatus::Ok, "ok", None)];
        let rendered = super::render_json(&results);

        assert_eq!(rendered["schema"], json!("yu://diagnostics/doctor/1"));
        let created_at = rendered["created_at"].as_str().unwrap();
        assert!(
            created_at.ends_with("+00:00"),
            "created_at must use a +00:00 offset (Python isoformat), not Z: {created_at}"
        );
        assert!(!created_at.ends_with('Z'));
        assert_eq!(rendered["summary"], json!({"errors": 0, "warnings": 0}));
        assert_eq!(rendered["results"].as_array().unwrap().len(), 1);
    }

    #[test]
    fn write_report_files_appends_suffix_on_collision() {
        let temp = TempDir::new().unwrap();
        let report = json!({"summary": {"errors": 0, "warnings": 0}});
        let (md1, json1) = super::write_report_files(temp.path(), "# a", &report).unwrap();
        let (md2, json2) = super::write_report_files(temp.path(), "# b", &report).unwrap();

        assert_ne!(md1, md2, "second write must not clobber the first (md)");
        assert_ne!(
            json1, json2,
            "second write must not clobber the first (json)"
        );
        assert!(md1.exists() && md2.exists());
        assert!(json1.exists() && json2.exists());
        assert!(
            json2.to_string_lossy().contains('-'),
            "collision suffix expected in second path"
        );
    }

    #[tokio::test]
    async fn doctor_status_returns_404_job_not_found_for_unknown_id() {
        let response =
            super::doctor_status(super::AxumPath("does-not-exist-unit-test".to_string())).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
    }

    #[tokio::test]
    async fn doctor_status_returns_registered_job_payload_flattened_at_top_level() {
        let job_id = "unit-test-job-status-roundtrip";
        super::register_doctor_job(job_id, json!({"status": "done", "summary": {"errors": 0}}));

        let response = super::doctor_status(super::AxumPath(job_id.to_string())).await;
        assert_eq!(response.status(), StatusCode::OK);

        let body = axum::body::to_bytes(response.into_body(), usize::MAX)
            .await
            .unwrap();
        let parsed: Value = serde_json::from_slice(&body).unwrap();
        assert_eq!(parsed["status"], json!("done"));
        assert_eq!(parsed["ok"], json!(true));
    }
}
