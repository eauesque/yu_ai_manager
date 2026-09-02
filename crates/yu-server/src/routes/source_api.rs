#![allow(clippy::result_large_err)]
//! Source code browsing API — read-only filesystem reads.
//!
//! Native port of Python `routes/source_api.py` (`GET /api/source/tree`,
//! `GET /api/source/read`, `GET /api/source/search`). The security layer mirrors
//! `core/source_core/source_browser_security.py` exactly: project-root
//! containment (`resolve_safe`), an extension allow-list, a blocked-pattern /
//! blocked-dir deny-list, symlink rejection, and size/line caps. `source_search`
//! shells out to the same `rg` with identical arguments as the Python side, so
//! the live results match byte-for-byte; an in-process walk mirrors the Python
//! fallback when rg is unavailable.
//!
//! The path-traversal containment is the security boundary, so it is transcribed
//! line-for-line from the Python source rather than re-derived.

use std::collections::HashMap;
use std::path::{Path, PathBuf};
use std::process::Command;

use axum::{
    extract::{Extension, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

// ── Security definitions (mirror source_browser_security.py) ──────────────────

const ALLOWED_EXTENSIONS: &[&str] = &[
    ".py",
    ".ts",
    ".js",
    ".mjs",
    ".tsx",
    ".jsx",
    ".html",
    ".css",
    ".scss",
    ".json",
    ".yaml",
    ".yml",
    ".toml",
    ".cfg",
    ".ini",
    ".md",
    ".txt",
    ".rst",
    ".sh",
    ".bat",
    ".cmd",
    ".ps1",
    ".sql",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
    ".prettierrc",
    ".eslintrc",
];

const ALLOWED_EXTENSIONLESS: &[&str] = &[
    "Dockerfile",
    "Makefile",
    "Procfile",
    "VERSION",
    "LICENSE",
    "CHANGELOG",
    "TODO",
    ".gitignore",
    ".gitattributes",
    ".editorconfig",
];

const BLOCKED_PATTERNS: &[&str] = &[
    "*.env",
    ".env.*",
    "secret.salt",
    "*.key",
    "*.pem",
    "*.cert",
    "*.crt",
    "config.json",
    "config_*.json",
    "credentials*",
    "*token*",
    "*secret*",
    "*.db",
    "*.sqlite",
    "*.sqlite3",
    "*.pyc",
    "*.pyo",
    "*.whl",
    "*.egg",
    "*.tar.gz",
    "*.zip",
    "*.7z",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.webp",
    "*.ico",
    "*.svg",
    "*.mp4",
    "*.webm",
    "*.mov",
    "*.avi",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "*.hef",
    "*.onnx",
    "*.bin",
    "*.pt",
    "*.safetensors",
    "pnpm-lock.yaml",
    "package-lock.json",
    "yarn.lock",
    "uv.lock",
    "poetry.lock",
    "Pipfile.lock",
];

const BLOCKED_DIRS: &[&str] = &[
    ".git",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "dist",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".tox",
    ".eggs",
    "*.egg-info",
    "src-tauri",
    "data",
    "reports",
    "screenshots",
    "backups",
];

const MAX_FILE_SIZE_BYTES: u64 = 1024 * 1024; // 1 MB
const MAX_LINES: i64 = 2000;
const MAX_TREE_DEPTH: i64 = 6;
const MAX_SEARCH_RESULTS: i64 = 50;

// ── Glob / allow-list helpers ─────────────────────────────────────────────────

/// `fnmatch`-style wildcard match supporting `*` (any run) and `?` (one char).
/// `*` is the only metachar in the deny-lists; `?` is supported for user-supplied
/// search globs. Two-pointer backtracking; callers lower-case as needed.
fn glob_match(pat: &str, name: &str) -> bool {
    let p: Vec<char> = pat.chars().collect();
    let s: Vec<char> = name.chars().collect();
    let (mut i, mut j) = (0usize, 0usize);
    let mut star: Option<usize> = None;
    let mut mark = 0usize;
    while j < s.len() {
        if i < p.len() && (p[i] == '?' || p[i] == s[j]) {
            i += 1;
            j += 1;
        } else if i < p.len() && p[i] == '*' {
            star = Some(i);
            mark = j;
            i += 1;
        } else if let Some(si) = star {
            i = si + 1;
            mark += 1;
            j = mark;
        } else {
            return false;
        }
    }
    while i < p.len() && p[i] == '*' {
        i += 1;
    }
    i == p.len()
}

fn is_dir_blocked(name: &str) -> bool {
    BLOCKED_DIRS.iter().any(|d| {
        if d.contains('*') {
            glob_match(d, name)
        } else {
            *d == name
        }
    })
}

fn is_file_blocked(name: &str) -> bool {
    let lower = name.to_lowercase();
    BLOCKED_PATTERNS
        .iter()
        .any(|p| glob_match(&p.to_lowercase(), &lower))
}

fn is_file_allowed(path: &Path) -> bool {
    let name = match path.file_name().and_then(|n| n.to_str()) {
        Some(n) => n,
        None => return false,
    };
    if is_file_blocked(name) {
        return false;
    }
    if ALLOWED_EXTENSIONLESS.contains(&name) {
        return true;
    }
    // Path::extension() returns the suffix WITHOUT the dot; Python compares with
    // the dot, so re-add it. Dot-leading names (".gitignore") have no extension
    // in both languages and fall through to the allow-list above.
    match path.extension().and_then(|e| e.to_str()) {
        Some(ext) => {
            let dotted = format!(".{}", ext.to_lowercase());
            ALLOWED_EXTENSIONS.contains(&dotted.as_str())
        }
        None => false,
    }
}

// ── Path containment (mirror _resolve_safe) ───────────────────────────────────

/// Resolve a client-supplied relative path to an absolute path inside `root`.
/// Returns `Err(message)` for traversal/invalid input, matching the Python
/// error strings so the proxy/native bodies stay identical.
fn resolve_safe(root: &Path, rel_path: &str) -> Result<PathBuf, String> {
    if rel_path.is_empty() || rel_path == "." || rel_path == "/" || rel_path == "\\" {
        return Ok(root.to_path_buf());
    }
    if rel_path.contains('\0') {
        return Err("不正なパスです".to_string());
    }
    let cleaned = rel_path.replace('\\', "/");
    let cleaned = cleaned.trim_start_matches('/');

    // Normalize lexically; a `..` that would escape the root is rejected, matching
    // Python's `(root / cleaned).resolve()` + `relative_to(root)` raising.
    let mut stack: Vec<&str> = Vec::new();
    for comp in cleaned.split('/') {
        match comp {
            "" | "." => continue,
            ".." => {
                if stack.pop().is_none() {
                    return Err("プロジェクトルート外へのアクセスは禁止されています".to_string());
                }
            }
            other => stack.push(other),
        }
    }
    let mut target = root.to_path_buf();
    for c in &stack {
        target.push(c);
    }

    // Symlink-escape recheck: if the target exists, its real path must stay under
    // the real root (a symlink pointing outside is rejected here, as Python's
    // resolve() would surface it before relative_to()).
    if let Ok(canon) = std::fs::canonicalize(&target) {
        let canon_root = std::fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
        if !canon.starts_with(&canon_root) {
            return Err("プロジェクトルート外へのアクセスは禁止されています".to_string());
        }
    }
    Ok(target)
}

/// Relative path string with forward slashes, mirroring `relative_to(root)`.
fn rel_display(path: &Path, root: &Path) -> String {
    path.strip_prefix(root)
        .map(|p| p.to_string_lossy().replace('\\', "/"))
        .unwrap_or_default()
}

fn is_symlink(path: &Path) -> bool {
    std::fs::symlink_metadata(path)
        .map(|m| m.file_type().is_symlink())
        .unwrap_or(false)
}

fn is_inside_root(path: &Path, canon_root: &Path) -> bool {
    match std::fs::canonicalize(path) {
        Ok(c) => c.starts_with(canon_root),
        Err(_) => false,
    }
}

// ── tree ──────────────────────────────────────────────────────────────────────

fn walk(dir: &Path, root: &Path, canon_root: &Path, current_depth: i64, depth: i64) -> Vec<Value> {
    let mut items: Vec<PathBuf> = match std::fs::read_dir(dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => return Vec::new(),
    };
    // Python sort key: (not is_dir, name.lower()) → dirs first, then alphabetical.
    items.sort_by(|a, b| {
        let a_dir = a.is_dir();
        let b_dir = b.is_dir();
        let a_name = a
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        let b_name = b
            .file_name()
            .map(|n| n.to_string_lossy().to_lowercase())
            .unwrap_or_default();
        (!a_dir, a_name).cmp(&(!b_dir, b_name))
    });

    let mut entries: Vec<Value> = Vec::new();
    for item in items {
        let name = match item.file_name().and_then(|n| n.to_str()) {
            Some(n) => n.to_string(),
            None => continue,
        };
        if is_symlink(&item) || !is_inside_root(&item, canon_root) {
            continue;
        }
        if item.is_dir() {
            if is_dir_blocked(&name) {
                continue;
            }
            let mut node = json!({
                "name": name,
                "type": "dir",
                "path": rel_display(&item, root),
            });
            if current_depth < depth {
                node["children"] =
                    Value::Array(walk(&item, root, canon_root, current_depth + 1, depth));
            }
            entries.push(node);
        } else {
            if !is_file_allowed(&item) {
                continue;
            }
            let size = std::fs::metadata(&item).map(|m| m.len()).unwrap_or(0);
            entries.push(json!({
                "name": name,
                "type": "file",
                "path": rel_display(&item, root),
                "size": size,
            }));
        }
    }
    entries
}

fn source_tree(root: &Path, rel_path: &str, depth: i64) -> Result<Value, String> {
    let depth = depth.clamp(1, MAX_TREE_DEPTH);
    let target = resolve_safe(root, rel_path)?;
    if !target.is_dir() {
        return Err(format!("ディレクトリが見つかりません: {}", rel_path));
    }
    let canon_root = std::fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let tree = walk(&target, root, &canon_root, 1, depth);
    let root_field = {
        let r = rel_display(&target, root);
        if r.is_empty() {
            ".".to_string()
        } else {
            r
        }
    };
    Ok(json!({
        "root": root_field,
        "depth": depth,
        "entries": tree,
    }))
}

// ── read ────────────────────────────────────────────────────────────────────

/// Format an integer with comma thousands separators (Python `f"{n:,}"`).
fn comma(n: u64) -> String {
    let s = n.to_string();
    let bytes = s.as_bytes();
    let mut out = String::new();
    let len = bytes.len();
    for (i, b) in bytes.iter().enumerate() {
        if i > 0 && (len - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(*b as char);
    }
    out
}

/// Split text into lines the way Python file iteration + `rstrip("\n\r")` does:
/// a trailing newline does not produce a final empty line, and each line has its
/// trailing CR/LF stripped.
fn split_lines(text: &str) -> Vec<&str> {
    if text.is_empty() {
        return Vec::new();
    }
    let mut parts: Vec<&str> = text.split('\n').collect();
    if text.ends_with('\n') {
        parts.pop();
    }
    parts
        .into_iter()
        .map(|l| l.trim_end_matches(['\n', '\r']))
        .collect()
}

fn source_read(root: &Path, rel_path: &str, offset: i64, limit: i64) -> Result<Value, String> {
    if rel_path.is_empty() {
        return Err("ファイルパスを指定してください".to_string());
    }
    let target = resolve_safe(root, rel_path)?;

    // Reject symlinks even if they resolve inside the root (matches Python's
    // literal-path symlink check, which guards against allow-list bypass).
    let literal = root.join(rel_path.trim_start_matches(['/', '\\']).replace('\\', "/"));
    if is_symlink(&literal) {
        return Err("シンボリックリンクへのアクセスは禁止されています".to_string());
    }
    if !target.is_file() {
        return Err(format!("ファイルが見つかりません: {}", rel_path));
    }
    if !is_file_allowed(&target) {
        return Err("このファイルは読み取り対象外です".to_string());
    }
    let size = std::fs::metadata(&target).map(|m| m.len()).unwrap_or(0);
    if size > MAX_FILE_SIZE_BYTES {
        return Err(format!(
            "ファイルサイズが上限を超えています ({} bytes > {} bytes)",
            comma(size),
            comma(MAX_FILE_SIZE_BYTES)
        ));
    }

    let bytes = std::fs::read(&target).map_err(|e| format!("読み取りエラー: {}", e))?;
    let text = String::from_utf8_lossy(&bytes);
    let lines = split_lines(&text);
    let total_lines = lines.len() as i64;

    let offset = offset.max(0);
    let limit = limit.clamp(1, MAX_LINES);
    // Clamp the window to [0, total_lines]. `end >= start` always holds because
    // min() is monotonic, so an offset past EOF yields an empty slice (matching
    // Python, which simply selects no lines) rather than panicking.
    let start = usize::try_from(offset.min(total_lines)).unwrap_or(0);
    let end = usize::try_from((offset + limit).min(total_lines)).unwrap_or(0);
    let selected = &lines[start..end];

    let content = selected
        .iter()
        .enumerate()
        .map(|(i, line)| format!("{:>5}\t{}", offset + i as i64 + 1, line))
        .collect::<Vec<_>>()
        .join("\n");

    Ok(json!({
        "path": rel_display(&target, root),
        "total_lines": total_lines,
        "offset": offset,
        "limit": limit,
        "content": content,
    }))
}

// ── search ────────────────────────────────────────────────────────────────────

fn source_search(
    root: &Path,
    query: &str,
    glob_pattern: &str,
    max_results: i64,
) -> Result<Value, String> {
    // Python: `len(query) < 2` (code-point length).
    if query.chars().count() < 2 {
        return Err("検索クエリは 2 文字以上必要です".to_string());
    }
    let max_results = usize::try_from(max_results.clamp(1, MAX_SEARCH_RESULTS)).unwrap_or(1);
    let results = rg_search(root, query, glob_pattern, max_results)
        .unwrap_or_else(|| walk_search(root, query, glob_pattern, max_results));
    Ok(json!({
        "query": query,
        "glob": if glob_pattern.is_empty() { "*" } else { glob_pattern },
        "total": results.len(),
        "results": results,
    }))
}

/// Build the rg argument vector, identical (and identically ordered) to Python
/// `_search_with_rg`. The untrusted `query` is placed after a `--` separator so
/// it can never be parsed as an rg flag (argv flag smuggling — e.g. a
/// `--pre=<cmd>` query would otherwise run an arbitrary preprocessor command).
fn build_rg_args(root: &Path, query: &str) -> Vec<String> {
    let mut args: Vec<String> = [
        "--json",
        "--fixed-strings",
        "--ignore-case",
        "--line-number",
        "--no-heading",
        "--color",
        "never",
    ]
    .iter()
    .map(|s| s.to_string())
    .collect();
    // -g globs are derived from the (sorted) allow/deny lists, identical to Python.
    let mut exts: Vec<&str> = ALLOWED_EXTENSIONS.to_vec();
    exts.sort_unstable();
    for ext in exts {
        args.push("-g".to_string());
        args.push(format!("*{ext}"));
    }
    let mut names: Vec<&str> = ALLOWED_EXTENSIONLESS.to_vec();
    names.sort_unstable();
    for name in names {
        args.push("-g".to_string());
        args.push(name.to_string());
    }
    let mut dirs: Vec<&str> = BLOCKED_DIRS
        .iter()
        .copied()
        .filter(|d| !d.contains('*'))
        .collect();
    dirs.sort_unstable();
    for d in dirs {
        args.push("-g".to_string());
        args.push(format!("!{d}/**"));
    }
    // `--` ends option parsing; with --fixed-strings a `-`-prefixed query is
    // searched literally, so this is behaviour- and parity-preserving (the
    // Python side gets the same `--`).
    args.push("--".to_string());
    args.push(query.to_string());
    args.push(root.to_string_lossy().to_string());
    args
}

/// Run ripgrep with the exact arguments Python `_search_with_rg` builds, so the
/// match order is identical. Returns None when rg is missing or exits abnormally
/// (the caller then falls back to the in-process walk, mirroring Python).
fn rg_search(
    root: &Path,
    query: &str,
    glob_pattern: &str,
    max_results: usize,
) -> Option<Vec<Value>> {
    let args = build_rg_args(root, query);
    let output = Command::new("rg").args(&args).output().ok()?;
    // rg exit codes: 0 = matches, 1 = no matches (both normal); else -> fallback.
    match output.status.code() {
        Some(0) | Some(1) => {}
        _ => return None,
    }

    let stdout = String::from_utf8_lossy(&output.stdout);
    let canon_root = std::fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    let mut results: Vec<Value> = Vec::new();
    for raw in stdout.lines() {
        let event: Value = match serde_json::from_str(raw) {
            Ok(v) => v,
            Err(_) => continue,
        };
        if event.get("type").and_then(|t| t.as_str()) != Some("match") {
            continue;
        }
        let data = match event.get("data") {
            Some(d) => d,
            None => continue,
        };
        let path_text = data
            .get("path")
            .and_then(|p| p.get("text"))
            .and_then(|t| t.as_str())
            .unwrap_or("")
            .trim();
        if path_text.is_empty() {
            continue;
        }
        let path = Path::new(path_text);
        if is_symlink(path) || !is_file_allowed(path) {
            continue;
        }
        if !glob_pattern.is_empty() {
            let fname = path.file_name().and_then(|n| n.to_str()).unwrap_or("");
            if !glob_match(glob_pattern, fname) {
                continue;
            }
        }
        match std::fs::metadata(path) {
            Ok(m) if m.len() > MAX_FILE_SIZE_BYTES => continue,
            Ok(_) => {}
            Err(_) => continue,
        }
        let rel = match std::fs::canonicalize(path) {
            Ok(c) => match c.strip_prefix(&canon_root) {
                Ok(r) => r.to_string_lossy().replace('\\', "/"),
                Err(_) => continue,
            },
            Err(_) => continue,
        };
        let line = data
            .get("line_number")
            .and_then(|n| n.as_i64())
            .unwrap_or(0);
        let text_raw = data
            .get("lines")
            .and_then(|l| l.get("text"))
            .and_then(|t| t.as_str())
            .unwrap_or("");
        let text: String = text_raw.trim_end().chars().take(200).collect();
        results.push(json!({ "file": rel, "line": line, "text": text }));
        if results.len() >= max_results {
            return Some(results);
        }
    }
    Some(results)
}

/// In-process fallback mirroring Python `_search_with_python` (case-insensitive
/// fixed-string match). Only used when rg is unavailable; rg is the parity path.
fn walk_search(root: &Path, query: &str, glob_pattern: &str, max_results: usize) -> Vec<Value> {
    let needle = query.to_lowercase();
    let mut results: Vec<Value> = Vec::new();
    walk_search_dir(root, root, &needle, glob_pattern, max_results, &mut results);
    results
}

fn walk_search_dir(
    dir: &Path,
    root: &Path,
    needle: &str,
    glob_pattern: &str,
    max_results: usize,
    results: &mut Vec<Value>,
) {
    if results.len() >= max_results {
        return;
    }
    let mut paths: Vec<PathBuf> = match std::fs::read_dir(dir) {
        Ok(rd) => rd.filter_map(|e| e.ok().map(|e| e.path())).collect(),
        Err(_) => return,
    };
    paths.sort();
    for path in &paths {
        if results.len() >= max_results {
            return;
        }
        let name = match path.file_name().and_then(|n| n.to_str()) {
            Some(n) => n,
            None => continue,
        };
        if is_symlink(path) {
            continue;
        }
        if path.is_dir() {
            if !is_dir_blocked(name) {
                walk_search_dir(path, root, needle, glob_pattern, max_results, results);
            }
            continue;
        }
        if !is_file_allowed(path) {
            continue;
        }
        if !glob_pattern.is_empty() && !glob_match(glob_pattern, name) {
            continue;
        }
        match std::fs::metadata(path) {
            Ok(m) if m.len() > MAX_FILE_SIZE_BYTES => continue,
            Ok(_) => {}
            Err(_) => continue,
        }
        let bytes = match std::fs::read(path) {
            Ok(b) => b,
            Err(_) => continue,
        };
        let text = String::from_utf8_lossy(&bytes);
        for (i, line) in text.lines().enumerate() {
            if line.to_lowercase().contains(needle) {
                let rel = path
                    .strip_prefix(root)
                    .map(|r| r.to_string_lossy().replace('\\', "/"))
                    .unwrap_or_default();
                let t: String = line.trim_end().chars().take(200).collect();
                results.push(json!({ "file": rel, "line": (i as i64) + 1, "text": t }));
                if results.len() >= max_results {
                    return;
                }
            }
        }
    }
}

// ── handlers ──────────────────────────────────────────────────────────────────

fn parse_int(params: &HashMap<String, String>, key: &str, default: i64) -> i64 {
    params
        .get(key)
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(default)
}

/// GET /api/source/tree — directory tree listing.
pub async fn source_tree_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let rel_path = params.get("path").cloned().unwrap_or_default();
    let depth = parse_int(&params, "depth", 3);
    match source_tree(&state.config.project_root, &rel_path, depth) {
        Ok(result) => api_result(result),
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
    }
}

/// GET /api/source/read — file contents with line numbers.
pub async fn source_read_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    let rel_path = params.get("path").cloned().unwrap_or_default();
    let offset = parse_int(&params, "offset", 0);
    let limit = parse_int(&params, "limit", 2000);
    match source_read(&state.config.project_root, &rel_path, offset, limit) {
        Ok(result) => api_result(result),
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
    }
}

/// GET /api/source/search — text search via rg (Python proxy fallback removed).
pub async fn source_search_handler(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|c| &c.0),
    ) {
        return response;
    }
    // Python reads `q`, `glob`, `limit` (default 30).
    let query = params.get("q").cloned().unwrap_or_default();
    let glob = params.get("glob").cloned().unwrap_or_default();
    let limit = parse_int(&params, "limit", 30);
    match source_search(&state.config.project_root, &query, &glob, limit) {
        Ok(result) => api_result(result),
        Err(message) => api_error(&message, StatusCode::BAD_REQUEST),
    }
}

/// Python `api_result` success path: merge payload + ok/error/data.
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

/// Python `api_error(message, status)` without a code.
fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::fs;

    /// One directory per test. The comment used to say "per-test unique dir"
    /// while the body returned the *shared base*, so every test in this module
    /// wrote into the same directory -- and source_browser's tests live under
    /// that same base. Files another test created or deleted mid-run were
    /// visible to whoever was walking it, which is the flakiness recorded
    /// against walk_search_finds_case_insensitive_with_glob.
    fn tmp_root(name: &str) -> PathBuf {
        let dir = std::env::temp_dir().join("yu_source_api_test").join(name);
        let _ = fs::remove_dir_all(&dir);
        fs::create_dir_all(&dir).expect("create per-test dir");
        dir
    }

    #[test]
    fn glob_matches_wildcards() {
        assert!(glob_match("*.env", ".env"));
        assert!(glob_match("*token*", "my_token_file"));
        assert!(glob_match("config_*.json", "config_dev.json"));
        assert!(!glob_match("*.env", "env.py"));
    }

    #[test]
    fn file_allow_list() {
        assert!(is_file_allowed(Path::new("/x/foo.py")));
        assert!(is_file_allowed(Path::new("/x/VERSION")));
        assert!(!is_file_allowed(Path::new("/x/secret.key")));
        assert!(!is_file_allowed(Path::new("/x/config.json")));
        assert!(!is_file_allowed(Path::new("/x/blob.bin")));
    }

    #[test]
    fn resolve_safe_blocks_traversal() {
        let root = tmp_root("resolve_safe_blocks_traversal");
        assert!(resolve_safe(&root, "../etc/passwd").is_err());
        assert!(resolve_safe(&root, "a/../../b").is_err());
        assert_eq!(resolve_safe(&root, "").unwrap(), root);
        assert!(resolve_safe(&root, "sub/dir").is_ok());
    }

    #[test]
    fn read_formats_line_numbers_and_total() {
        let root = tmp_root("read_formats_line_numbers_and_total");
        let f = root.join("sample.txt");
        fs::write(&f, "alpha\nbravo\ncharlie\n").unwrap();
        let r = source_read(&root, "sample.txt", 0, 2000).unwrap();
        assert_eq!(r["total_lines"], 3);
        assert_eq!(r["content"], "    1\talpha\n    2\tbravo\n    3\tcharlie");
        // offset/limit window
        let r2 = source_read(&root, "sample.txt", 1, 1).unwrap();
        assert_eq!(r2["content"], "    2\tbravo");
        let _ = fs::remove_file(&f);
    }

    #[test]
    fn read_offset_past_eof_is_empty_not_panic() {
        let root = tmp_root("read_offset_past_eof_is_empty_not_panic");
        let f = root.join("short.txt");
        fs::write(&f, "only\nthree\nlines\n").unwrap();
        // offset beyond total_lines must yield empty content, not a slice panic.
        let r = source_read(&root, "short.txt", 100, 2000).unwrap();
        assert_eq!(r["total_lines"], 3);
        assert_eq!(r["content"], "");
        let _ = fs::remove_file(&f);
    }

    #[test]
    fn read_rejects_blocked_and_missing() {
        let root = tmp_root("read_rejects_blocked_and_missing");
        assert!(source_read(&root, "", 0, 10).is_err());
        assert!(source_read(&root, "nope.py", 0, 10).is_err());
    }

    #[test]
    fn rg_args_separate_query_with_double_dash() {
        // Argv flag smuggling guard: a `--pre=...`-style query must land AFTER a
        // `--` separator (and just before the root path), never parsed as a flag.
        let args = build_rg_args(Path::new("/proj"), "--pre=sh");
        let sep = args
            .iter()
            .position(|a| a == "--")
            .expect("missing -- separator");
        assert_eq!(args[sep + 1], "--pre=sh");
        assert_eq!(args[sep + 2], "/proj");
        assert_eq!(sep + 3, args.len());
        // No bare query token may appear before the separator.
        assert!(!args[..sep].iter().any(|a| a == "--pre=sh"));
    }

    #[test]
    fn search_rejects_short_query() {
        let root = tmp_root("search_rejects_short_query");
        assert!(source_search(&root, "x", "", 30).is_err());
        assert!(source_search(&root, "", "", 30).is_err());
    }

    #[test]
    fn walk_search_finds_case_insensitive_with_glob() {
        let root = tmp_root("walk_search_finds_case_insensitive_with_glob").join("search_case");
        let _ = fs::create_dir_all(&root);
        fs::write(root.join("a.py"), "needle_here = 1\nNEEDLE_HERE = 2\n").unwrap();
        fs::write(root.join("b.txt"), "needle_here in text\n").unwrap();
        // glob restricts to *.py; case-insensitive match finds both lines.
        let hits = walk_search(&root, "needle_here", "*.py", 30);
        assert_eq!(hits.len(), 2);
        assert_eq!(hits[0]["file"], "a.py");
        assert_eq!(hits[0]["line"], 1);
        // max_results cap is honoured.
        let capped = walk_search(&root, "needle_here", "", 1);
        assert_eq!(capped.len(), 1);
        let _ = fs::remove_dir_all(&root);
    }
}
