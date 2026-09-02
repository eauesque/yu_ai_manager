#![allow(clippy::result_large_err)]

use std::collections::HashMap;
use std::time::Duration;

use axum::{
    body::{to_bytes, Body},
    extract::{Extension, Path, Query, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use regex::Regex;
use serde_json::{json, Map, Value};
use sqlx::Row;

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    ext_config, secret_store,
    state::SharedState,
};

const USER_AGENT: &str = "YU-AI-Manager-GitHub-Integration/1.0";
const API_VERSION: &str = "2022-11-28";

const DEFAULT_TRIAGE_PROMPT_ISSUE: &str = "Review the following GitHub issue and determine whether it is a technically valid bug report.\n\nValid (valid) criteria:\n- Concrete reproduction steps are provided\n- Error log or stack trace is included\n- Environment info (OS, version, etc.) is present\n\nInvalid (invalid) criteria:\n- Emotional text only, no technical facts\n- Feature request, not a bug\n- Written in a language other than English\n- No actionable technical information\n\nReturn your verdict (valid / invalid) and the reason.";
const DEFAULT_TRIAGE_PROMPT_PR: &str = "Do not accept pull requests. Close automatically.";
const DEFAULT_TRIAGE_PROMPT_DISCUSSION: &str = "Discussions are closed. No action required.";

fn api_success(payload: Value, status: StatusCode) -> Response {
    let mut body = match payload {
        Value::Object(map) => map,
        other => {
            return (
                status,
                Json(json!({"ok": true, "error": null, "data": other})),
            )
                .into_response()
        }
    };
    body.insert("ok".to_string(), Value::Bool(true));
    body.insert("error".to_string(), Value::Null);
    body.entry("data".to_string()).or_insert(Value::Null);
    (status, Json(Value::Object(body))).into_response()
}

fn api_result(payload: Value) -> Response {
    api_success(payload, StatusCode::OK)
}

fn api_error(message: impl Into<String>, status: StatusCode) -> Response {
    (
        status,
        Json(json!({
            "ok": false,
            "error": message.into(),
        })),
    )
        .into_response()
}

fn internal_error(error: impl std::fmt::Debug, message: &'static str) -> Response {
    tracing::error!(?error, "{message}");
    api_error("internal_server_error", StatusCode::INTERNAL_SERVER_ERROR)
}

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

async fn json_object_from_body(body: Body) -> Result<Value, Response> {
    let bytes = to_bytes(body, usize::MAX)
        .await
        .map_err(|_| api_error("JSON object required", StatusCode::BAD_REQUEST))?;
    if bytes.is_empty() {
        return Ok(json!({}));
    }
    let value = serde_json::from_slice::<Value>(&bytes).unwrap_or_else(|_| json!({}));
    if value.is_null() {
        Ok(json!({}))
    } else if value.is_object() {
        Ok(value)
    } else {
        Err(api_error("JSON object required", StatusCode::BAD_REQUEST))
    }
}

fn github_section(config: &Value) -> Value {
    config
        .get("github_integration")
        .cloned()
        .unwrap_or_else(|| json!({}))
}

fn github_section_mut(config: &mut Value) -> &mut Map<String, Value> {
    if !config.is_object() {
        *config = json!({});
    }
    if !config
        .get("github_integration")
        .is_some_and(Value::is_object)
    {
        config["github_integration"] = json!({});
    }
    config["github_integration"]
        .as_object_mut()
        .expect("object set above")
}

fn token_setting_key(label: &str) -> String {
    format!("github_integration.tokens.{label}")
}

fn load_config(state: &SharedState) -> Result<Value, std::io::Error> {
    ext_config::read_config(&state.config.config_path)
}

fn save_config(state: &SharedState, config: &Value) -> Result<(), std::io::Error> {
    crate::config_io::write(&state.config.config_path, config)
}

fn get_token_from_section(sec: &Value, label: &str, project_root: &std::path::Path) -> String {
    let raw = sec
        .get("tokens")
        .and_then(Value::as_object)
        .and_then(|tokens| tokens.get(label))
        .and_then(Value::as_str)
        .or_else(|| {
            sec.get("accounts")
                .and_then(Value::as_array)
                .and_then(|accounts| {
                    accounts
                        .iter()
                        .find(|acc| acc.get("label").and_then(Value::as_str) == Some(label))
                })
                .and_then(|acc| acc.get("token"))
                .and_then(Value::as_str)
        })
        .unwrap_or("");
    secret_store::decrypt(raw, project_root)
}

fn account_from_value(acc: &Value, token: String) -> Value {
    json!({
        "label": acc.get("label").and_then(Value::as_str).unwrap_or(""),
        "token": token,
        "repos": acc.get("repos").and_then(Value::as_array).cloned().unwrap_or_default(),
        "enabled": acc.get("enabled").and_then(Value::as_bool).unwrap_or(true),
    })
}

fn get_account(state: &SharedState, label: &str) -> Result<Option<Value>, std::io::Error> {
    let config = load_config(state)?;
    let sec = github_section(&config);
    let account = sec
        .get("accounts")
        .and_then(Value::as_array)
        .and_then(|accounts| {
            accounts
                .iter()
                .find(|acc| acc.get("label").and_then(Value::as_str) == Some(label))
        })
        .map(|acc| {
            account_from_value(
                acc,
                get_token_from_section(&sec, label, &state.config.project_root),
            )
        });
    Ok(account)
}

fn account_not_found(label: &str) -> Response {
    api_error(
        format!("Account '{label}' not found"),
        StatusCode::NOT_FOUND,
    )
}

pub async fn list_accounts(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section(&config);
    let accounts = sec
        .get("accounts")
        .and_then(Value::as_array)
        .map(|accounts| {
            accounts
                .iter()
                .map(|acc| {
                    let label = acc.get("label").and_then(Value::as_str).unwrap_or("");
                    let token = get_token_from_section(&sec, label, &state.config.project_root);
                    json!({
                        "label": label,
                        "repos": acc.get("repos").and_then(Value::as_array).cloned().unwrap_or_default(),
                        "enabled": acc.get("enabled").and_then(Value::as_bool).unwrap_or(true),
                        "token_masked": secret_store::mask_secret(&token),
                        "token_setting_key": token_setting_key(label),
                    })
                })
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    api_result(json!({"data": accounts}))
}

pub async fn add_account(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    request: axum::extract::Request,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    let label = data
        .get("label")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let token = data
        .get("token")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    if label.is_empty() {
        return api_error("label is required", StatusCode::BAD_REQUEST);
    }
    if token.is_empty() {
        return api_error("token is required", StatusCode::BAD_REQUEST);
    }
    if !data.get("repos").is_none_or(Value::is_array) {
        return api_error("repos must be a list", StatusCode::BAD_REQUEST);
    }
    let repos = data
        .get("repos")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let _guard = state.settings_lock.lock().await;
    let mut config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section_mut(&mut config);
    if !sec.get("accounts").is_some_and(Value::is_array) {
        sec.insert("accounts".to_string(), json!([]));
    }
    let accounts = sec
        .get_mut("accounts")
        .and_then(Value::as_array_mut)
        .expect("array set above");
    if accounts
        .iter()
        .any(|acc| acc.get("label").and_then(Value::as_str) == Some(label.as_str()))
    {
        return api_error("GitHub account could not be added", StatusCode::CONFLICT);
    }
    accounts.push(json!({"label": label, "repos": repos, "enabled": true}));
    if !sec.get("tokens").is_some_and(Value::is_object) {
        sec.insert("tokens".to_string(), json!({}));
    }
    sec.get_mut("tokens")
        .and_then(Value::as_object_mut)
        .expect("object set above")
        .insert(
            label.clone(),
            Value::String(secret_store::encrypt(&token, &state.config.project_root)),
        );
    if let Err(error) = save_config(&state, &config) {
        return internal_error(error, "failed to write github config");
    }
    api_result(json!({"data": {"label": label, "repos": repos, "enabled": true}}))
}

pub async fn update_account(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    request: axum::extract::Request,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    let _guard = state.settings_lock.lock().await;
    let mut config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section_mut(&mut config);
    let Some(accounts) = sec.get_mut("accounts").and_then(Value::as_array_mut) else {
        return account_not_found(&label);
    };
    let Some(account) = accounts
        .iter_mut()
        .find(|acc| acc.get("label").and_then(Value::as_str) == Some(label.as_str()))
    else {
        return account_not_found(&label);
    };
    if let Some(repos) = data.get("repos").filter(|v| v.is_array()) {
        account["repos"] = repos.clone();
    }
    if let Some(enabled) = data.get("enabled").and_then(Value::as_bool) {
        account["enabled"] = json!(enabled);
    }
    let result = json!({
        "label": label,
        "repos": account.get("repos").and_then(Value::as_array).cloned().unwrap_or_default(),
        "enabled": account.get("enabled").and_then(Value::as_bool).unwrap_or(true),
    });
    if let Some(token) = data.get("token").and_then(Value::as_str) {
        if !sec.get("tokens").is_some_and(Value::is_object) {
            sec.insert("tokens".to_string(), json!({}));
        }
        sec.get_mut("tokens")
            .and_then(Value::as_object_mut)
            .expect("object set above")
            .insert(
                label.clone(),
                Value::String(secret_store::encrypt(token, &state.config.project_root)),
            );
    }
    if let Err(error) = save_config(&state, &config) {
        return internal_error(error, "failed to write github config");
    }
    api_result(json!({"data": result}))
}

pub async fn remove_account(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let _guard = state.settings_lock.lock().await;
    let mut config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section_mut(&mut config);
    let Some(accounts) = sec.get_mut("accounts").and_then(Value::as_array_mut) else {
        return account_not_found(&label);
    };
    let before = accounts.len();
    accounts.retain(|acc| acc.get("label").and_then(Value::as_str) != Some(label.as_str()));
    if accounts.len() == before {
        return account_not_found(&label);
    }
    if let Some(tokens) = sec.get_mut("tokens").and_then(Value::as_object_mut) {
        tokens.remove(&label);
    }
    if let Err(error) = save_config(&state, &config) {
        return internal_error(error, "failed to write github config");
    }
    api_result(json!({"ok": true}))
}

fn github_base_url(state: &SharedState) -> String {
    state
        .config
        .app_config
        .get("github_api_base")
        .and_then(Value::as_str)
        .unwrap_or("https://api.github.com")
        .trim_end_matches('/')
        .to_string()
}

async fn github_request(
    state: &SharedState,
    token: &str,
    method: reqwest::Method,
    path: &str,
    params: Vec<(&str, String)>,
    body: Option<Value>,
) -> (u16, Value) {
    if let Some(mock) = state.config.app_config.get("github_api_mock") {
        let key = format!("{} {path}", method.as_str());
        if let Some(entry) = mock.get(&key) {
            // A status outside u16 is not a status; fall back rather than wrap.
            let status = entry
                .get("status")
                .and_then(Value::as_u64)
                .and_then(|code| u16::try_from(code).ok())
                .unwrap_or(200);
            return (
                status,
                entry.get("body").cloned().unwrap_or_else(|| json!({})),
            );
        }
        return (404, json!({"message": format!("mock not found: {key}")}));
    }
    let client = match reqwest::Client::builder()
        .timeout(Duration::from_secs(15))
        .user_agent(USER_AGENT)
        .build()
    {
        Ok(client) => client,
        Err(error) => return (0, json!({"message": format!("Request failed: {error}")})),
    };
    let url = format!("{}{}", github_base_url(state), path);
    let mut request = client
        .request(method, url)
        .bearer_auth(token)
        .header("Accept", "application/vnd.github.v3+json")
        .header("X-GitHub-Api-Version", API_VERSION);
    if !params.is_empty() {
        request = request.query(&params);
    }
    if let Some(body) = body {
        request = request.json(&body);
    }
    match request.send().await {
        Ok(response) => {
            let status = response.status().as_u16();
            let data = response.json::<Value>().await.unwrap_or_else(|_| json!({}));
            (status, data)
        }
        Err(_) => (0, json!({"message": "Request failed"})),
    }
}

fn trunc(value: Option<&Value>, max: usize) -> String {
    value
        .and_then(Value::as_str)
        .unwrap_or("")
        .chars()
        .take(max)
        .collect()
}

fn labels(raw: &Value) -> Vec<Value> {
    raw.get("labels")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(|label| label.get("name").and_then(Value::as_str))
                .map(|name| json!(name))
                .collect()
        })
        .unwrap_or_default()
}

fn normalize_issue(raw: &Value) -> Value {
    json!({
        "number": raw.get("number").cloned().unwrap_or(Value::Null),
        "title": trunc(raw.get("title"), usize::MAX),
        "state": trunc(raw.get("state"), usize::MAX),
        "user": raw.get("user").and_then(|u| u.get("login")).and_then(Value::as_str).unwrap_or(""),
        "labels": labels(raw),
        "created_at": trunc(raw.get("created_at"), usize::MAX),
        "updated_at": trunc(raw.get("updated_at"), usize::MAX),
        "body": trunc(raw.get("body"), 3000),
        "comments_count": raw.get("comments").and_then(Value::as_i64).unwrap_or(0),
        "html_url": trunc(raw.get("html_url"), usize::MAX),
        "is_pull_request": raw.get("pull_request").is_some(),
    })
}

fn normalize_pull(raw: &Value) -> Value {
    json!({
        "number": raw.get("number").cloned().unwrap_or(Value::Null),
        "title": trunc(raw.get("title"), usize::MAX),
        "state": trunc(raw.get("state"), usize::MAX),
        "user": raw.get("user").and_then(|u| u.get("login")).and_then(Value::as_str).unwrap_or(""),
        "labels": labels(raw),
        "created_at": trunc(raw.get("created_at"), usize::MAX),
        "updated_at": trunc(raw.get("updated_at"), usize::MAX),
        "body": trunc(raw.get("body"), 3000),
        "html_url": trunc(raw.get("html_url"), usize::MAX),
        "head_ref": raw.get("head").and_then(|v| v.get("ref")).and_then(Value::as_str).unwrap_or(""),
        "base_ref": raw.get("base").and_then(|v| v.get("ref")).and_then(Value::as_str).unwrap_or(""),
        "draft": raw.get("draft").and_then(Value::as_bool).unwrap_or(false),
        "merged": if raw.get("merged").is_some() { raw.get("merged").cloned().unwrap_or(Value::Null) } else { Value::Null },
        "mergeable": raw.get("mergeable").cloned().unwrap_or(Value::Null),
        "additions": raw.get("additions").and_then(Value::as_i64).unwrap_or(0),
        "deletions": raw.get("deletions").and_then(Value::as_i64).unwrap_or(0),
        "changed_files": raw.get("changed_files").and_then(Value::as_i64).unwrap_or(0),
        "comments_count": raw.get("comments").and_then(Value::as_i64).unwrap_or(0),
        "review_comments": raw.get("review_comments").and_then(Value::as_i64).unwrap_or(0),
        "repo": raw.get("base").and_then(|v| v.get("repo")).and_then(|v| v.get("full_name")).and_then(Value::as_str).unwrap_or(""),
    })
}

fn normalize_notification(raw: &Value) -> Value {
    let subject = raw.get("subject").unwrap_or(&Value::Null);
    let repo = raw.get("repository").unwrap_or(&Value::Null);
    let sub_url = subject.get("url").and_then(Value::as_str).unwrap_or("");
    let number = if sub_url.contains("/issues/") || sub_url.contains("/pulls/") {
        sub_url.rsplit('/').next().unwrap_or("")
    } else {
        ""
    };
    json!({
        "id": trunc(raw.get("id"), usize::MAX),
        "reason": trunc(raw.get("reason"), usize::MAX),
        "unread": raw.get("unread").and_then(Value::as_bool).unwrap_or(false),
        "updated_at": trunc(raw.get("updated_at"), usize::MAX),
        "subject_title": trunc(subject.get("title"), usize::MAX),
        "subject_type": trunc(subject.get("type"), usize::MAX),
        "subject_number": number,
        "repo_full_name": trunc(repo.get("full_name"), usize::MAX),
        "repo_html_url": trunc(repo.get("html_url"), usize::MAX),
    })
}

fn normalize_release(raw: &Value) -> Value {
    json!({
        "tag_name": trunc(raw.get("tag_name"), usize::MAX),
        "name": trunc(raw.get("name"), usize::MAX),
        "draft": raw.get("draft").and_then(Value::as_bool).unwrap_or(false),
        "prerelease": raw.get("prerelease").and_then(Value::as_bool).unwrap_or(false),
        "published_at": trunc(raw.get("published_at"), usize::MAX),
        "html_url": trunc(raw.get("html_url"), usize::MAX),
        "body": trunc(raw.get("body"), 2000),
        "author": raw.get("author").and_then(|u| u.get("login")).and_then(Value::as_str).unwrap_or(""),
    })
}

fn normalize_repo(raw: &Value) -> Value {
    json!({
        "full_name": trunc(raw.get("full_name"), usize::MAX),
        "description": trunc(raw.get("description"), 300),
        "stars": raw.get("stargazers_count").and_then(Value::as_i64).unwrap_or(0),
        "forks": raw.get("forks_count").and_then(Value::as_i64).unwrap_or(0),
        "open_issues": raw.get("open_issues_count").and_then(Value::as_i64).unwrap_or(0),
        "watchers": raw.get("watchers_count").and_then(Value::as_i64).unwrap_or(0),
        "language": trunc(raw.get("language"), usize::MAX),
        "html_url": trunc(raw.get("html_url"), usize::MAX),
        "updated_at": trunc(raw.get("updated_at"), usize::MAX),
        "default_branch": raw.get("default_branch").and_then(Value::as_str).unwrap_or("main"),
        "topics": raw.get("topics").and_then(Value::as_array).cloned().unwrap_or_default(),
    })
}

fn validate_repo(repo: &str) -> Option<String> {
    let re = Regex::new(r"^[A-Za-z0-9_.\-]+/[A-Za-z0-9_.\-]+$").expect("repo regex");
    (!re.is_match(repo)).then(|| format!("Invalid repo format: '{repo}'. Expected 'owner/repo'."))
}

pub async fn rate_limit(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let (code, data) = github_request(
        &state,
        token,
        reqwest::Method::GET,
        "/rate_limit",
        vec![],
        None,
    )
    .await;
    let result = if code == 200 {
        let core = data
            .get("resources")
            .and_then(|r| r.get("core"))
            .unwrap_or(&Value::Null);
        let reset = core.get("reset").and_then(Value::as_i64).unwrap_or(0);
        json!({
            "remaining": core.get("remaining").and_then(Value::as_i64).unwrap_or(0),
            "limit": core.get("limit").and_then(Value::as_i64).unwrap_or(0),
            "reset": reset,
            "reset_at": if reset > 0 {
                chrono::DateTime::from_timestamp(reset, 0).map(|dt| dt.to_rfc3339()).unwrap_or_default()
            } else {
                String::new()
            },
        })
    } else {
        json!({"error": data.get("message").and_then(Value::as_str).unwrap_or("Failed to fetch rate limit")})
    };
    api_result(json!({"data": result}))
}

pub async fn fetch_issues(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    if !acc.get("enabled").and_then(Value::as_bool).unwrap_or(true) {
        return api_error(
            format!("Account '{label}' is disabled"),
            StatusCode::BAD_REQUEST,
        );
    }
    let repos = if let Some(repo) = query.get("repo").filter(|s| !s.is_empty()) {
        vec![repo.clone()]
    } else {
        acc.get("repos")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default()
    };
    if repos.is_empty() {
        return api_error(
            "No repositories configured for this account",
            StatusCode::BAD_REQUEST,
        );
    }
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let mut issues = Vec::new();
    let mut errors = Vec::new();
    for repo in repos {
        let params = vec![
            (
                "state",
                query
                    .get("state")
                    .cloned()
                    .unwrap_or_else(|| "open".to_string()),
            ),
            ("per_page", "30".to_string()),
            ("page", "1".to_string()),
            ("sort", "created".to_string()),
            ("direction", "desc".to_string()),
            ("labels", query.get("labels").cloned().unwrap_or_default()),
            ("since", query.get("since").cloned().unwrap_or_default()),
        ]
        .into_iter()
        .filter(|(_, v)| !v.is_empty())
        .collect();
        let (code, data) = github_request(
            &state,
            token,
            reqwest::Method::GET,
            &format!("/repos/{repo}/issues"),
            params,
            None,
        )
        .await;
        if code == 200 && data.is_array() {
            for raw in data.as_array().unwrap_or(&Vec::new()) {
                let mut issue = normalize_issue(raw);
                issue["repo"] = json!(repo);
                if !issue
                    .get("is_pull_request")
                    .and_then(Value::as_bool)
                    .unwrap_or(false)
                {
                    issues.push(issue);
                }
            }
        } else {
            let msg = data
                .get("message")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| format!("HTTP {code}"));
            errors.push(json!(format!("{repo}: {msg}")));
        }
    }
    api_result(json!({"data": {"issues": issues, "count": issues.len(), "errors": errors}}))
}

pub async fn get_issue_detail(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path((label, owner, repo_name, number)): Path<(String, String, String, i64)>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let repo = format!("{owner}/{repo_name}");
    if let Some(err) = validate_repo(&repo) {
        return api_error(err, StatusCode::BAD_REQUEST);
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let (code, raw) = github_request(
        &state,
        token,
        reqwest::Method::GET,
        &format!("/repos/{repo}/issues/{number}"),
        vec![],
        None,
    )
    .await;
    if code != 200 {
        let msg = raw
            .get("message")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| format!("HTTP {code}"));
        return api_error(
            format!("Failed to fetch issue: {msg}"),
            StatusCode::from_u16(code).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        );
    }
    let mut issue = normalize_issue(&raw);
    issue["repo"] = json!(repo);
    let mut comments = Vec::new();
    if issue
        .get("comments_count")
        .and_then(Value::as_i64)
        .unwrap_or(0)
        > 0
    {
        let (c_code, c_data) = github_request(
            &state,
            token,
            reqwest::Method::GET,
            &format!(
                "/repos/{}/issues/{}/comments",
                issue["repo"].as_str().unwrap_or(""),
                number
            ),
            vec![("per_page", "10".to_string())],
            None,
        )
        .await;
        if c_code == 200 {
            comments = c_data.as_array().cloned().unwrap_or_default();
        }
    }
    let formatted = format_for_claude_code(&issue, &comments);
    api_result(
        json!({"data": {"issue": issue, "formatted": formatted, "comments_count": comments.len()}}),
    )
}

fn format_for_claude_code(issue: &Value, comments: &[Value]) -> String {
    let labels = issue
        .get("labels")
        .and_then(Value::as_array)
        .map(|items| {
            items
                .iter()
                .filter_map(Value::as_str)
                .collect::<Vec<_>>()
                .join(", ")
        })
        .filter(|s| !s.is_empty())
        .unwrap_or_else(|| "none".to_string());
    let html_url = issue.get("html_url").and_then(Value::as_str).unwrap_or("");
    let mut lines = vec![
        format!(
            "## GitHub Issue #{} — {}",
            issue.get("number").and_then(Value::as_i64).unwrap_or(0),
            issue.get("title").and_then(Value::as_str).unwrap_or("")
        ),
        format!(
            "**Repository:** {}",
            html_url
                .rsplit_once("/issues/")
                .map(|(base, _)| base)
                .unwrap_or(html_url)
        ),
        format!("**URL:** {html_url}"),
        format!(
            "**Reporter:** {}",
            issue.get("user").and_then(Value::as_str).unwrap_or("")
        ),
        format!("**Labels:** {labels}"),
        format!(
            "**Created:** {}",
            issue
                .get("created_at")
                .and_then(Value::as_str)
                .unwrap_or("")
        ),
        String::new(),
        "### Description".to_string(),
        issue
            .get("body")
            .and_then(Value::as_str)
            .unwrap_or("(empty)")
            .to_string(),
    ];
    if !comments.is_empty() {
        lines.push(String::new());
        lines.push("### Comments".to_string());
        for comment in comments.iter().take(5) {
            lines.push(format!(
                "**{}** ({}):",
                comment
                    .get("user")
                    .and_then(|u| u.get("login"))
                    .and_then(Value::as_str)
                    .unwrap_or("unknown"),
                comment
                    .get("created_at")
                    .and_then(Value::as_str)
                    .unwrap_or("")
            ));
            lines.push(trunc(comment.get("body"), 1000));
            lines.push(String::new());
        }
    }
    lines.join("\n")
}

pub async fn create_issue(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    request: axum::extract::Request,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    let repo = data
        .get("repo")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    let title = data
        .get("title")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim();
    if repo.is_empty() {
        return api_error("repo is required", StatusCode::BAD_REQUEST);
    }
    if title.is_empty() {
        return api_error("title is required", StatusCode::BAD_REQUEST);
    }
    let allowed = acc
        .get("repos")
        .and_then(Value::as_array)
        .is_some_and(|items| items.iter().any(|item| item.as_str() == Some(repo)));
    if !allowed {
        return api_error(
            format!("Repo '{repo}' not in account's configured repos"),
            StatusCode::BAD_REQUEST,
        );
    }
    let mut payload = json!({"title": title});
    if let Some(body) = data
        .get("body")
        .and_then(Value::as_str)
        .filter(|s| !s.is_empty())
    {
        payload["body"] = json!(body);
    }
    if let Some(labels) = data
        .get("labels")
        .and_then(Value::as_array)
        .filter(|v| !v.is_empty())
    {
        payload["labels"] = json!(labels);
    }
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let (code, raw) = github_request(
        &state,
        token,
        reqwest::Method::POST,
        &format!("/repos/{repo}/issues"),
        vec![],
        Some(payload),
    )
    .await;
    if code != 200 && code != 201 {
        let msg = raw
            .get("message")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| format!("HTTP {code}"));
        return api_error(
            format!("Failed to create issue: {msg}"),
            StatusCode::from_u16(code).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        );
    }
    api_result(json!({"data": normalize_issue(&raw)}))
}

pub async fn fetch_pulls(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    if !acc.get("enabled").and_then(Value::as_bool).unwrap_or(true) {
        return api_error(
            format!("Account '{label}' is disabled"),
            StatusCode::BAD_REQUEST,
        );
    }
    let repos = if let Some(repo) = query.get("repo").filter(|s| !s.is_empty()) {
        vec![repo.clone()]
    } else {
        acc.get("repos")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default()
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let mut pulls = Vec::new();
    let mut errors = Vec::new();
    for repo in repos {
        let params = vec![
            (
                "state",
                query
                    .get("state")
                    .cloned()
                    .unwrap_or_else(|| "open".to_string()),
            ),
            ("per_page", "30".to_string()),
            ("page", "1".to_string()),
            ("sort", "created".to_string()),
            ("direction", "desc".to_string()),
        ];
        let (code, data) = github_request(
            &state,
            token,
            reqwest::Method::GET,
            &format!("/repos/{repo}/pulls"),
            params,
            None,
        )
        .await;
        if code == 200 && data.is_array() {
            for raw in data.as_array().unwrap_or(&Vec::new()) {
                let mut pr = normalize_pull(raw);
                pr["repo"] = json!(repo);
                pulls.push(pr);
            }
        } else {
            let msg = data
                .get("message")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| format!("HTTP {code}"));
            errors.push(json!(format!("{repo}: {msg}")));
        }
    }
    api_result(json!({"data": {"pulls": pulls, "count": pulls.len(), "errors": errors}}))
}

pub async fn get_pull_detail(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path((label, owner, repo_name, number)): Path<(String, String, String, i64)>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let repo = format!("{owner}/{repo_name}");
    if let Some(err) = validate_repo(&repo) {
        return api_error(err, StatusCode::BAD_REQUEST);
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let (code, raw) = github_request(
        &state,
        token,
        reqwest::Method::GET,
        &format!("/repos/{repo}/pulls/{number}"),
        vec![],
        None,
    )
    .await;
    if code != 200 {
        let msg = raw
            .get("message")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| format!("HTTP {code}"));
        return api_error(
            format!("Failed to fetch PR: {msg}"),
            StatusCode::from_u16(code).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        );
    }
    let mut pr = normalize_pull(&raw);
    pr["repo"] = json!(repo);
    let (f_code, files_raw) = github_request(
        &state,
        token,
        reqwest::Method::GET,
        &format!(
            "/repos/{}/pulls/{}/files",
            pr["repo"].as_str().unwrap_or(""),
            number
        ),
        vec![("per_page", "100".to_string())],
        None,
    )
    .await;
    let files =
        if f_code == 200 {
            files_raw
                .as_array()
                .map(|items| {
                    items
                    .iter()
                    .take(50)
                    .map(|f| json!({
                        "filename": trunc(f.get("filename"), usize::MAX),
                        "status": trunc(f.get("status"), usize::MAX),
                        "additions": f.get("additions").and_then(Value::as_i64).unwrap_or(0),
                        "deletions": f.get("deletions").and_then(Value::as_i64).unwrap_or(0),
                        "patch": trunc(f.get("patch"), 2000),
                    }))
                    .collect::<Vec<_>>()
                })
                .unwrap_or_default()
        } else {
            Vec::new()
        };
    api_result(json!({"data": {"pull": pr, "files": files}}))
}

pub async fn get_notifications(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let show_all = query.get("all").is_some_and(|v| v == "true");
    let (code, data) = github_request(
        &state,
        token,
        reqwest::Method::GET,
        "/notifications",
        vec![
            ("per_page", "50".to_string()),
            ("all", if show_all { "true" } else { "false" }.to_string()),
        ],
        None,
    )
    .await;
    if code != 200 {
        let msg = data
            .get("message")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| format!("HTTP {code}"));
        return api_error(
            format!("Notifications fetch failed: {msg}"),
            StatusCode::from_u16(code).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        );
    }
    let notifications = data
        .as_array()
        .map(|items| items.iter().map(normalize_notification).collect::<Vec<_>>())
        .unwrap_or_default();
    api_result(json!({"data": {"notifications": notifications, "count": notifications.len()}}))
}

pub async fn mark_notification_read(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path((label, thread_id)): Path<(String, String)>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let _ = github_request(
        &state,
        token,
        reqwest::Method::PATCH,
        &format!("/notifications/threads/{thread_id}"),
        vec![],
        None,
    )
    .await;
    api_result(json!({"ok": true}))
}

pub async fn mark_all_notifications_read(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let _ = github_request(
        &state,
        token,
        reqwest::Method::PUT,
        "/notifications",
        vec![],
        None,
    )
    .await;
    api_result(json!({"ok": true}))
}

fn normalize_discussion(raw: &Value) -> Value {
    let cat = raw.get("category").unwrap_or(&Value::Null);
    json!({
        "number": raw.get("number").cloned().unwrap_or(Value::Null),
        "title": trunc(raw.get("title"), usize::MAX),
        "author": raw.get("author").and_then(|a| a.get("login")).and_then(Value::as_str).unwrap_or(""),
        "created_at": trunc(raw.get("createdAt"), usize::MAX),
        "updated_at": trunc(raw.get("updatedAt"), usize::MAX),
        "body": trunc(raw.get("bodyText"), 1500),
        "url": trunc(raw.get("url"), usize::MAX),
        "category": trunc(cat.get("name"), usize::MAX),
        "category_emoji": trunc(cat.get("emoji"), usize::MAX),
        "comments_count": raw.get("comments").and_then(|c| c.get("totalCount")).and_then(Value::as_i64).unwrap_or(0),
        "labels": raw.get("labels").and_then(|l| l.get("nodes")).and_then(Value::as_array).map(|items| items.iter().filter_map(|l| l.get("name").and_then(Value::as_str)).map(|s| json!(s)).collect::<Vec<_>>()).unwrap_or_default(),
        "answered": raw.get("answerChosenAt").is_some_and(|v| !v.is_null()),
    })
}

pub async fn get_discussions(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let repos = if let Some(repo) = query.get("repo").filter(|s| !s.is_empty()) {
        vec![repo.clone()]
    } else {
        acc.get("repos")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default()
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let mut discussions = Vec::new();
    let mut errors = Vec::new();
    for repo in repos {
        let Some((owner, name)) = repo.split_once('/') else {
            errors.push(json!(format!("{repo}: Invalid repo format: {repo}")));
            continue;
        };
        let body = json!({"query": "query($owner: String!, $name: String!, $first: Int!) { repository(owner: $owner, name: $name) { discussions(first: $first, orderBy: {field: CREATED_AT, direction: DESC}) { nodes { number title author { login } createdAt updatedAt bodyText url category { name emoji } comments { totalCount } labels(first: 5) { nodes { name } } answerChosenAt } } } }", "variables": {"owner": owner, "name": name, "first": 20}});
        let (code, data) = github_request(
            &state,
            token,
            reqwest::Method::POST,
            "/graphql",
            vec![],
            Some(body),
        )
        .await;
        if code == 200 && data.get("errors").is_none() {
            let nodes = data
                .get("data")
                .and_then(|d| d.get("repository"))
                .and_then(|r| r.get("discussions"))
                .and_then(|d| d.get("nodes"))
                .and_then(Value::as_array)
                .cloned()
                .unwrap_or_default();
            for node in nodes {
                let mut item = normalize_discussion(&node);
                item["repo"] = json!(repo);
                discussions.push(item);
            }
        } else {
            let msg = data
                .get("errors")
                .and_then(Value::as_array)
                .and_then(|e| e.first())
                .and_then(|e| e.get("message"))
                .and_then(Value::as_str)
                .or_else(|| data.get("message").and_then(Value::as_str))
                .map(str::to_string)
                .unwrap_or_else(|| format!("HTTP {code}"));
            errors.push(json!(format!("{repo}: {msg}")));
        }
    }
    api_result(
        json!({"data": {"discussions": discussions, "count": discussions.len(), "errors": errors}}),
    )
}

pub async fn get_releases(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let repos = if let Some(repo) = query.get("repo").filter(|s| !s.is_empty()) {
        vec![repo.clone()]
    } else {
        acc.get("repos")
            .and_then(Value::as_array)
            .map(|items| {
                items
                    .iter()
                    .filter_map(Value::as_str)
                    .map(str::to_string)
                    .collect()
            })
            .unwrap_or_default()
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let mut releases = Vec::new();
    let mut errors = Vec::new();
    for repo in repos {
        let (code, data) = github_request(
            &state,
            token,
            reqwest::Method::GET,
            &format!("/repos/{repo}/releases"),
            vec![("per_page", "5".to_string())],
            None,
        )
        .await;
        if code == 200 && data.is_array() {
            for raw in data.as_array().unwrap_or(&Vec::new()) {
                let mut rel = normalize_release(raw);
                rel["repo"] = json!(repo);
                releases.push(rel);
            }
        } else {
            let msg = data
                .get("message")
                .and_then(Value::as_str)
                .map(str::to_string)
                .unwrap_or_else(|| format!("HTTP {code}"));
            errors.push(json!(format!("{repo}: {msg}")));
        }
    }
    api_result(json!({"data": {"releases": releases, "count": releases.len(), "errors": errors}}))
}

pub async fn get_repo_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path((label, owner, repo_name)): Path<(String, String, String)>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let repo = format!("{owner}/{repo_name}");
    if let Some(err) = validate_repo(&repo) {
        return api_error(err, StatusCode::BAD_REQUEST);
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let (code, raw) = github_request(
        &state,
        token,
        reqwest::Method::GET,
        &format!("/repos/{repo}"),
        vec![],
        None,
    )
    .await;
    if code != 200 {
        let msg = raw
            .get("message")
            .and_then(Value::as_str)
            .map(str::to_string)
            .unwrap_or_else(|| format!("HTTP {code}"));
        return api_error(
            format!("Failed to fetch repo: {msg}"),
            StatusCode::from_u16(code).unwrap_or(StatusCode::INTERNAL_SERVER_ERROR),
        );
    }
    api_result(json!({"data": normalize_repo(&raw)}))
}

pub async fn get_all_repo_stats(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(label): Path<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let acc = match get_account(&state, &label) {
        Ok(Some(acc)) => acc,
        Ok(None) => return account_not_found(&label),
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let token = acc.get("token").and_then(Value::as_str).unwrap_or("");
    let mut repos_stats = Vec::new();
    for repo in acc
        .get("repos")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default()
        .iter()
        .filter_map(Value::as_str)
    {
        let (code, raw) = github_request(
            &state,
            token,
            reqwest::Method::GET,
            &format!("/repos/{repo}"),
            vec![],
            None,
        )
        .await;
        if code == 200 {
            repos_stats.push(normalize_repo(&raw));
        }
    }
    api_result(json!({"data": {"repos": repos_stats}}))
}

fn triage_defaults() -> Value {
    json!({
        "issue": DEFAULT_TRIAGE_PROMPT_ISSUE,
        "pr": DEFAULT_TRIAGE_PROMPT_PR,
        "discussion": DEFAULT_TRIAGE_PROMPT_DISCUSSION,
    })
}

fn resolve_triage_prompts(sec: &Value, repo: &str) -> Value {
    let global = sec.get("triage_prompts").unwrap_or(&Value::Null);
    let mut result = triage_defaults();
    for key in ["issue", "pr", "discussion"] {
        if let Some(value) = global.get(key).and_then(Value::as_str) {
            result[key] = json!(value);
        }
    }
    if !repo.is_empty() {
        if let Some(per_repo) = sec.get("triage_prompts_per_repo").and_then(|p| p.get(repo)) {
            for key in ["issue", "pr", "discussion"] {
                if let Some(value) = per_repo
                    .get(key)
                    .and_then(Value::as_str)
                    .filter(|s| !s.is_empty())
                {
                    result[key] = json!(value);
                }
            }
        }
    }
    result
}

pub async fn get_triage_prompts(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section(&config);
    let repo = query.get("repo").cloned().unwrap_or_default();
    api_result(json!({"data": {
        "prompts": resolve_triage_prompts(&sec, &repo),
        "global": resolve_triage_prompts(&sec, ""),
        "per_repo": sec.get("triage_prompts_per_repo").cloned().unwrap_or_else(|| json!({})),
        "defaults": triage_defaults(),
        "repo": repo,
    }}))
}

pub async fn save_triage_prompts(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    request: axum::extract::Request,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    let repo = data
        .get("repo")
        .and_then(Value::as_str)
        .unwrap_or("")
        .trim()
        .to_string();
    let _guard = state.settings_lock.lock().await;
    let mut config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section_mut(&mut config);
    if repo.is_empty() {
        if !sec.get("triage_prompts").is_some_and(Value::is_object) {
            sec.insert("triage_prompts".to_string(), json!({}));
        }
        let prompts = sec
            .get_mut("triage_prompts")
            .and_then(Value::as_object_mut)
            .unwrap();
        for key in ["issue", "pr", "discussion"] {
            if let Some(value) = data.get(key) {
                prompts.insert(key.to_string(), value.clone());
            }
        }
    } else {
        if !sec
            .get("triage_prompts_per_repo")
            .is_some_and(Value::is_object)
        {
            sec.insert("triage_prompts_per_repo".to_string(), json!({}));
        }
        let per_repo = sec
            .get_mut("triage_prompts_per_repo")
            .and_then(Value::as_object_mut)
            .unwrap();
        let entry = per_repo.entry(repo.clone()).or_insert_with(|| json!({}));
        if !entry.is_object() {
            *entry = json!({});
        }
        let entry_map = entry.as_object_mut().unwrap();
        for key in ["issue", "pr", "discussion"] {
            if let Some(value) = data.get(key) {
                if value.as_str() == Some("") {
                    entry_map.remove(key);
                } else {
                    entry_map.insert(key.to_string(), value.clone());
                }
            }
        }
        if entry_map.is_empty() {
            per_repo.remove(&repo);
        }
    }
    if let Err(error) = save_config(&state, &config) {
        return internal_error(error, "failed to write github config");
    }
    let sec = github_section(&config);
    api_result(json!({"data": resolve_triage_prompts(&sec, &repo)}))
}

fn queue_config_from_section(sec: &Value) -> Value {
    let queue = sec.get("queue").unwrap_or(&Value::Null);
    json!({
        "poll_interval_minutes": queue.get("poll_interval_minutes").and_then(Value::as_i64).unwrap_or(60),
        "auto_close_invalid": queue.get("auto_close_invalid").and_then(Value::as_bool).unwrap_or(false),
        "notify_on_connect": queue.get("notify_on_connect").and_then(Value::as_bool).unwrap_or(true),
    })
}

pub async fn get_queue_config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    api_result(json!({"data": queue_config_from_section(&github_section(&config))}))
}

pub async fn save_queue_config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    request: axum::extract::Request,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let data = match json_object_from_body(request.into_body()).await {
        Ok(data) => data,
        Err(response) => return response,
    };
    let _guard = state.settings_lock.lock().await;
    let mut config = match load_config(&state) {
        Ok(config) => config,
        Err(error) => return internal_error(error, "failed to read github config"),
    };
    let sec = github_section_mut(&mut config);
    if !sec.get("queue").is_some_and(Value::is_object) {
        sec.insert("queue".to_string(), json!({}));
    }
    let queue = sec.get_mut("queue").and_then(Value::as_object_mut).unwrap();
    if let Some(minutes) = data.get("poll_interval_minutes").and_then(Value::as_i64) {
        queue.insert("poll_interval_minutes".to_string(), json!(minutes.max(5)));
    }
    if let Some(value) = data.get("auto_close_invalid").and_then(Value::as_bool) {
        queue.insert("auto_close_invalid".to_string(), json!(value));
    }
    if let Some(value) = data.get("notify_on_connect").and_then(Value::as_bool) {
        queue.insert("notify_on_connect".to_string(), json!(value));
    }
    if let Err(error) = save_config(&state, &config) {
        return internal_error(error, "failed to write github config");
    }
    api_result(json!({"data": queue_config_from_section(&github_section(&config))}))
}

pub async fn get_issue_queue(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(query): Query<HashMap<String, String>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let status = query.get("status").cloned().unwrap_or_default();
    let limit = query
        .get("limit")
        .and_then(|v| v.parse::<i64>().ok())
        .unwrap_or(50)
        .clamp(1, 200);
    let rows = if status.is_empty() {
        sqlx::query("SELECT id, repo, issue_number, title, body, created_at, fetched_at, status, triage_result FROM github_issue_queue ORDER BY fetched_at DESC LIMIT ?")
            .bind(limit)
            .fetch_all(&state.db_read)
            .await
    } else {
        sqlx::query("SELECT id, repo, issue_number, title, body, created_at, fetched_at, status, triage_result FROM github_issue_queue WHERE status = ? ORDER BY fetched_at DESC LIMIT ?")
            .bind(&status)
            .bind(limit)
            .fetch_all(&state.db_read)
            .await
    };
    let rows = match rows {
        Ok(rows) => rows,
        Err(error) => return internal_error(error, "failed to read github issue queue"),
    };
    let items = rows.iter().map(queue_row_to_value).collect::<Vec<_>>();
    let stats = queue_stats(&state)
        .await
        .unwrap_or_else(|_| json!({"pending": 0, "notified": 0, "dismissed": 0, "total": 0}));
    api_result(json!({"data": {"items": items, "stats": stats}}))
}

pub async fn get_pending_queue(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let rows = match sqlx::query("SELECT id, repo, issue_number, title, body, created_at, fetched_at, status, triage_result FROM github_issue_queue WHERE status = 'pending' ORDER BY fetched_at DESC")
        .fetch_all(&state.db_read)
        .await {
            Ok(rows) => rows,
            Err(error) => return internal_error(error, "failed to read github issue queue"),
        };
    let items = rows.iter().map(queue_row_to_value).collect::<Vec<_>>();
    let count = items.len();
    api_result(json!({"data": {"items": items, "count": count}}))
}

fn queue_row_to_value(row: &sqlx::sqlite::SqliteRow) -> Value {
    json!({
        "id": row.get::<i64, _>("id"),
        "repo": row.get::<String, _>("repo"),
        "issue_number": row.get::<i64, _>("issue_number"),
        "title": row.get::<String, _>("title"),
        "body": row.try_get::<Option<String>, _>("body").ok().flatten(),
        "created_at": row.try_get::<Option<String>, _>("created_at").ok().flatten(),
        "fetched_at": row.try_get::<Option<String>, _>("fetched_at").ok().flatten(),
        "status": row.get::<String, _>("status"),
        "triage_result": row.try_get::<Option<String>, _>("triage_result").ok().flatten(),
    })
}

async fn queue_stats(state: &SharedState) -> Result<Value, sqlx::Error> {
    let rows =
        sqlx::query("SELECT status, COUNT(*) AS count FROM github_issue_queue GROUP BY status")
            .fetch_all(&state.db_read)
            .await?;
    let mut pending = 0_i64;
    let mut notified = 0_i64;
    let mut dismissed = 0_i64;
    for row in rows {
        match row.get::<String, _>("status").as_str() {
            "pending" => pending = row.get::<i64, _>("count"),
            "notified" => notified = row.get::<i64, _>("count"),
            "dismissed" => dismissed = row.get::<i64, _>("count"),
            _ => {}
        }
    }
    Ok(
        json!({"pending": pending, "notified": notified, "dismissed": dismissed, "total": pending + notified + dismissed}),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::{HashMap, HashSet},
        sync::{Arc, Mutex},
    };

    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
        routing::{get, put},
        Router,
    };
    use serde_json::{json, Value};
    use sqlx::sqlite::SqlitePoolOptions;
    use tower::ServiceExt;

    use crate::{
        auth::{AuthContext, PinRateLimiter, QuickLock},
        groups_index::GroupsIndexCache,
        state::{AppState, Config, SharedState},
    };

    fn temp_root(name: &str) -> tempfile::TempDir {
        tempfile::Builder::new()
            .prefix(&format!("yu-github-{name}-"))
            .tempdir_in(std::env::temp_dir())
            .unwrap()
    }

    async fn test_state(root: &tempfile::TempDir, app_config: Value) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .max_connections(1)
            .connect("sqlite::memory:")
            .await
            .unwrap();
        sqlx::query(
            "CREATE TABLE github_issue_queue (
                id INTEGER PRIMARY KEY,
                repo TEXT NOT NULL,
                issue_number INTEGER NOT NULL,
                title TEXT NOT NULL,
                body TEXT,
                created_at TEXT,
                fetched_at TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                triage_result TEXT
            )",
        )
        .execute(&pool)
        .await
        .unwrap();
        Arc::new(AppState {
            effective_port: 5000,
            gateway_keys: Vec::new(),
            gateway_loopback_bypass: true,
            settings_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            infer_notify_lock: std::sync::Arc::new(tokio::sync::Mutex::new(())),
            scan_roots_generation: std::sync::atomic::AtomicU64::new(0),
            config: Config {
                db_path: "sqlite::memory:".to_string(),
                pin_hash: String::new(),
                valid_token: String::new(),
                secret: String::new(),
                trusted_proxy_enabled: false,

                pin_boss_login_ui: false,
                trusted_ips: HashSet::new(),
                trusted_peer_ips: HashSet::new(),
                quick_lock_enabled: true,
                pin_auth_enabled: true,
                min_pin_length: 4,
                python_url: String::new(),
                config_path: root.path().join("config.json"),
                project_root: root.path().to_path_buf(),
                app_config,
                cache_dir: root.path().join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                mcp_native: false,
                standalone: false,
                infer_standalone: true,
                active_profile: None,
                python_executable: String::new(),
            },
            db: pool.clone(),
            db_read: pool.clone(),
            vectors_db: pool.clone(),
            vectors_db_read: pool,
            clip_index: std::sync::Arc::new(
                crate::routes::clip_index::ClipIndex::new_default(std::env::temp_dir())
                    .expect("clip index test default"),
            ),
            clip_indexer: std::sync::Arc::new(crate::routes::clip_indexer::ClipIndexer::new()),
            caption_runner: std::sync::Arc::new(crate::routes::caption_runner::CaptionRunner::new()),
            s2t_runner: std::sync::Arc::new(crate::routes::s2t_runner::S2tRunner::new()),
            clip_runtime_cache: crate::state::TtlCache::new(crate::state::CLIP_RUNTIME_CACHE_TTL),
            inference_client: reqwest::Client::new(),
            python_client: reqwest::Client::new(),
            quick_lock: QuickLock::new(),
            rate_limiter: PinRateLimiter::new(),
            groups_index_cache: GroupsIndexCache::new(root.path().join("cache")),
            proxy_hits: Mutex::new(HashMap::new()),
            fleet_log_stream_connections: Mutex::new(HashMap::new()),
            sse_hub: Arc::new(crate::sse::SseHub::new()),
            job_manager: Arc::new(crate::jobs::JobManager::new()),
            watcher: Arc::new(crate::watcher::ScanWatcher::new()),
            log_ring: Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            mcp_sessions: Arc::new(crate::mcp::session::McpSessionStore::new(1000, 20, 256)),
            approval_gate: Mutex::new(crate::approval_gate::ApprovalGate::default()),
            env: minijinja::Environment::new(),
            dist_v: "dev".to_string(),
            version: "0.0.0".to_string(),
            start_time: std::time::Instant::now(),
            scheduler_state: std::sync::OnceLock::new(),
            wd_infer: std::sync::Arc::new(std::sync::Mutex::new(std::collections::HashMap::new())),
            infer_client: None,
            infer_child: None,
            scan_manager: std::sync::OnceLock::new(),
            hailo_yolo_stream: None,
            stats_basic_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_models_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_timeline_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            stats_resolutions_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            checkpoints_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
            server_info_stats_cache: crate::state::TtlCache::new(crate::state::STATS_CACHE_TTL),
        })
    }

    fn app(state: SharedState, auth_context: Option<AuthContext>) -> Router {
        let router = Router::new()
            .route("/api/github/accounts", get(list_accounts).post(add_account))
            .route(
                "/api/github/accounts/{label}",
                put(update_account).delete(remove_account),
            )
            .route(
                "/api/github/queue/config",
                get(get_queue_config).put(save_queue_config),
            )
            .route(
                "/api/github/triage-prompts",
                get(get_triage_prompts).put(save_triage_prompts),
            )
            .route("/api/github/issues/{label}", get(fetch_issues))
            .route("/api/github/pulls/{label}", get(fetch_pulls))
            .route("/api/github/notifications/{label}", get(get_notifications))
            .route("/api/github/queue", get(get_issue_queue))
            .route("/api/github/queue/pending", get(get_pending_queue))
            .with_state(state);
        if let Some(context) = auth_context {
            router.layer(axum::Extension(context))
        } else {
            router
        }
    }

    async fn json_request(
        app: Router,
        method: Method,
        path: &str,
        body: Value,
    ) -> (StatusCode, Value) {
        let request = Request::builder()
            .method(method)
            .uri(path)
            .header("content-type", "application/json")
            .body(Body::from(body.to_string()))
            .unwrap();
        let response = app.oneshot(request).await.unwrap();
        let status = response.status();
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        (status, serde_json::from_slice(&bytes).unwrap())
    }

    fn admin_context() -> AuthContext {
        AuthContext {
            reason: "api_key".to_string(),
            scopes: Some(vec!["admin".to_string()]),
        }
    }

    fn write_github_config(root: &tempfile::TempDir) {
        std::fs::write(
            root.path().join("config.json"),
            json!({
                "github_integration": {
                    "accounts": [{
                        "label": "main",
                        "repos": ["owner/repo"],
                        "enabled": true
                    }],
                    "tokens": {"main": "ghp_plain_for_mock"}
                }
            })
            .to_string(),
        )
        .unwrap();
    }

    fn github_mock_config() -> Value {
        json!({
            "github_api_mock": {
                "GET /repos/owner/repo/issues": {
                    "status": 200,
                    "body": [
                    {
                        "number": 7,
                        "title": "bug",
                        "state": "open",
                        "user": {"login": "alice"},
                        "labels": [{"name": "bug"}],
                        "created_at": "2026-01-01T00:00:00Z",
                        "updated_at": "2026-01-02T00:00:00Z",
                        "body": "traceback\nsteps to reproduce",
                        "comments": 2,
                        "html_url": "https://github.com/owner/repo/issues/7"
                    },
                    {
                        "number": 8,
                        "title": "pr",
                        "pull_request": {},
                        "user": {"login": "bob"},
                        "labels": []
                    }
                    ]
                },
                "GET /repos/owner/repo/pulls": {
                    "status": 200,
                    "body": [
                    {
                        "number": 3,
                        "title": "change",
                        "state": "open",
                        "user": {"login": "carol"},
                        "labels": [{"name": "enhancement"}],
                        "head": {"ref": "feature"},
                        "base": {"ref": "main", "repo": {"full_name": "owner/repo"}},
                        "draft": false,
                        "additions": 10,
                        "deletions": 2,
                        "changed_files": 1,
                        "comments": 0,
                        "review_comments": 0,
                        "html_url": "https://github.com/owner/repo/pull/3"
                    }
                    ]
                },
                "GET /notifications": {
                    "status": 403,
                    "body": {"message": "bad creds"}
                }
            }
        })
    }

    #[tokio::test]
    async fn accounts_crud_encrypts_pat_and_never_returns_plaintext() {
        let root = temp_root("accounts");
        let state = test_state(&root, json!({})).await;
        let app = app(state.clone(), Some(admin_context()));

        let (status, value) = json_request(
            app.clone(),
            Method::POST,
            "/api/github/accounts",
            json!({"label": "main", "token": "ghp_secret_token", "repos": ["owner/repo"]}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(
            value["data"],
            json!({"label": "main", "repos": ["owner/repo"], "enabled": true})
        );

        let raw = std::fs::read_to_string(root.path().join("config.json")).unwrap();
        let cfg: Value = serde_json::from_str(&raw).unwrap();
        let stored = cfg["github_integration"]["tokens"]["main"]
            .as_str()
            .unwrap();
        assert!(stored.starts_with("enc:v2:"));
        assert_ne!(stored, "ghp_secret_token");
        assert_eq!(
            crate::secret_store::decrypt(stored, root.path()),
            "ghp_secret_token"
        );

        let (status, value) =
            json_request(app, Method::GET, "/api/github/accounts", json!(null)).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"][0]["token_masked"], "g****n");
        assert!(!value.to_string().contains("ghp_secret_token"));
    }

    #[tokio::test]
    async fn queue_config_round_trips_through_github_integration_config() {
        let root = temp_root("queue-config");
        let state = test_state(&root, json!({})).await;
        let app = app(state, Some(admin_context()));

        let (status, value) = json_request(
            app.clone(),
            Method::PUT,
            "/api/github/queue/config",
            json!({"poll_interval_minutes": 2, "auto_close_invalid": true, "notify_on_connect": false}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(
            value["data"],
            json!({"poll_interval_minutes": 5, "auto_close_invalid": true, "notify_on_connect": false})
        );

        let (status, value) =
            json_request(app, Method::GET, "/api/github/queue/config", json!(null)).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["poll_interval_minutes"], 5);
    }

    #[tokio::test]
    async fn triage_prompts_round_trip_global_and_repo_override() {
        let root = temp_root("triage-prompts");
        let state = test_state(&root, json!({})).await;
        let app = app(state, Some(admin_context()));

        let (status, value) = json_request(
            app.clone(),
            Method::PUT,
            "/api/github/triage-prompts",
            json!({"issue": "global issue", "pr": "global pr"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["issue"], "global issue");
        assert_eq!(value["data"]["pr"], "global pr");

        let (status, value) = json_request(
            app.clone(),
            Method::PUT,
            "/api/github/triage-prompts",
            json!({"repo": "owner/repo", "issue": "repo issue"}),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["issue"], "repo issue");
        assert_eq!(value["data"]["pr"], "global pr");

        let (status, value) = json_request(
            app,
            Method::GET,
            "/api/github/triage-prompts?repo=owner/repo",
            json!(null),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["prompts"]["issue"], "repo issue");
        assert_eq!(value["data"]["global"]["issue"], "global issue");
    }

    #[tokio::test]
    async fn account_mutations_require_admin_scope() {
        let root = temp_root("scope");
        let state = test_state(&root, json!({})).await;
        let app = app(
            state,
            Some(AuthContext {
                reason: "api_key".to_string(),
                scopes: None,
            }),
        );

        let (status, value) = json_request(
            app,
            Method::POST,
            "/api/github/accounts",
            json!({"label": "main", "token": "ghp_secret_token", "repos": []}),
        )
        .await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(
            value,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );
    }

    #[tokio::test]
    async fn github_http_routes_normalize_successes_and_preserve_error_shape() {
        let root = temp_root("http");
        write_github_config(&root);
        let state = test_state(&root, github_mock_config()).await;
        let app = app(state, Some(admin_context()));

        let (status, value) = json_request(
            app.clone(),
            Method::GET,
            "/api/github/issues/main",
            json!(null),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["count"], 1);
        assert_eq!(value["data"]["issues"][0]["repo"], "owner/repo");
        assert_eq!(value["data"]["issues"][0]["labels"], json!(["bug"]));

        let (status, value) = json_request(
            app.clone(),
            Method::GET,
            "/api/github/pulls/main",
            json!(null),
        )
        .await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["count"], 1);
        assert_eq!(value["data"]["pulls"][0]["head_ref"], "feature");

        let (status, value) = json_request(
            app,
            Method::GET,
            "/api/github/notifications/main",
            json!(null),
        )
        .await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(
            value,
            json!({"ok": false, "error": "Notifications fetch failed: bad creds"})
        );

        assert_eq!(USER_AGENT, "YU-AI-Manager-GitHub-Integration/1.0");
    }

    #[tokio::test]
    async fn fetch_issues_requires_admin_scope_for_api_keys() {
        let root = temp_root("issues-scope");
        write_github_config(&root);
        let state = test_state(&root, github_mock_config()).await;
        let app = app(
            state,
            Some(AuthContext {
                reason: "api_key".to_string(),
                scopes: Some(vec!["read".to_string()]),
            }),
        );

        let (status, value) =
            json_request(app, Method::GET, "/api/github/issues/main", json!(null)).await;
        assert_eq!(status, StatusCode::FORBIDDEN);
        assert_eq!(
            value,
            json!({"ok": false, "error": "Insufficient scope: requires 'admin'"})
        );
    }

    #[tokio::test]
    async fn queue_read_routes_return_items_and_stats_without_creating_schema() {
        let root = temp_root("queue-read");
        let state = test_state(&root, json!({})).await;
        sqlx::query(
            "INSERT INTO github_issue_queue
             (id, repo, issue_number, title, body, created_at, fetched_at, status, triage_result)
             VALUES (1, 'owner/repo', 7, 'bug', 'body', '2026-01-01', '2026-01-02', 'pending', NULL)",
        )
        .execute(&state.db)
        .await
        .unwrap();
        let app = app(state, Some(admin_context()));

        let (status, value) =
            json_request(app.clone(), Method::GET, "/api/github/queue", json!(null)).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["items"][0]["repo"], "owner/repo");
        assert_eq!(
            value["data"]["stats"],
            json!({"pending": 1, "notified": 0, "dismissed": 0, "total": 1})
        );

        let (status, value) =
            json_request(app, Method::GET, "/api/github/queue/pending", json!(null)).await;
        assert_eq!(status, StatusCode::OK);
        assert_eq!(value["data"]["count"], 1);
        assert_eq!(value["data"]["items"][0]["issue_number"], 7);
    }
}
