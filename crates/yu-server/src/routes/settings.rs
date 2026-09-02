use std::collections::HashMap;
use std::future::Future;
use std::net::SocketAddr;
use std::path::{Path, PathBuf};
use std::pin::Pin;
use std::process::Stdio;
use std::time::Duration;

use axum::{
    extract::{ConnectInfo, Extension, Path as AxumPath, State},
    http::StatusCode,
    response::{IntoResponse, Response},
    Json,
};
use base64::Engine;
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::process::Command;

use crate::config_io::{load as load_config_json, write as write_config_json};
use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    secret_store,
    state::SharedState,
};

const OP_TIMEOUT: Duration = Duration::from_secs(10);
const BW_TIMEOUT: Duration = Duration::from_secs(15);

#[derive(Clone, Debug, Deserialize, Serialize)]
struct SettingDef {
    key: String,
    #[serde(rename = "type")]
    type_name: String,
    description: String,
    default: Value,
    secret: bool,
    category: String,
    op_eligible: bool,
    #[serde(default)]
    options: Option<Vec<String>>,
}

#[derive(Debug, Deserialize)]
pub struct SettingValueRequest {
    value: Option<Value>,
    op_uri: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct PushToBwRequest {
    folder_id: Option<String>,
    item_name: Option<String>,
}

#[derive(Debug, Deserialize)]
pub struct PushToOpRequest {
    vault: Option<String>,
    item_title: Option<String>,
    remove_local: Option<bool>,
}

#[derive(Clone, Debug)]
struct CliOutput {
    status: i32,
    stdout: String,
    stderr: String,
}

#[derive(Debug)]
enum CliError {
    NotFound,
    Timeout,
    Io(std::io::Error),
}

trait VaultCli: Send + Sync {
    fn is_available(&self, program: &str) -> bool;
    fn run<'a>(
        &'a self,
        program: &'a str,
        args: &'a [&'a str],
        stdin_data: Option<String>,
        timeout: Duration,
    ) -> Pin<Box<dyn Future<Output = Result<CliOutput, CliError>> + Send + 'a>>;
}

struct CommandVaultCli;

impl VaultCli for CommandVaultCli {
    fn is_available(&self, program: &str) -> bool {
        executable_on_path(program)
    }

    fn run<'a>(
        &'a self,
        program: &'a str,
        args: &'a [&'a str],
        stdin_data: Option<String>,
        timeout: Duration,
    ) -> Pin<Box<dyn Future<Output = Result<CliOutput, CliError>> + Send + 'a>> {
        Box::pin(async move { run_command_with_timeout(program, args, stdin_data, timeout).await })
    }
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

fn api_error(message: &str, status: StatusCode, code: &str) -> Response {
    (
        status,
        Json(json!({"ok": false, "error": message, "code": code})),
    )
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

pub async fn api_settings_schema(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match load_schema_json(&state.config.project_root) {
        Ok(schema) => api_result(json!({"schema": schema})),
        Err(error) => internal_error(error, "failed to load settings schema"),
    }
}

pub async fn api_settings_all(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_all_settings(&state) {
        Ok(settings) => api_result(json!({"settings": settings})),
        Err(error) => internal_error(error, "failed to build settings list"),
    }
}

pub async fn api_settings_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(key): AxumPath<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match build_single_setting(&state, &key) {
        Ok(Some(setting)) => api_result(setting),
        Ok(None) => api_error("Unknown setting key", StatusCode::NOT_FOUND, "not_found"),
        Err(error) => internal_error(error, "failed to build setting value"),
    }
}

pub async fn api_settings_put(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(key): AxumPath<String>,
    Json(body): Json<SettingValueRequest>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match update_setting(&state, &key, body) {
        Ok(true) => api_result(json!({"key": key, "updated": true})),
        Ok(false) => api_error("Unknown setting key", StatusCode::NOT_FOUND, "not_found"),
        Err(SettingsWriteError::BadRequest(message)) => {
            api_error(&message, StatusCode::BAD_REQUEST, "bad_request")
        }
        Err(SettingsWriteError::Io(error)) => internal_error(error, "failed to write setting"),
    }
}

pub async fn api_secrets_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(secret_status(&state.config.project_root))
}

pub async fn api_secrets_keyring(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(secret_store::keyring_info(&state.config.project_root))
}

pub async fn api_secrets_export(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(password) = body.get("password").and_then(Value::as_str) else {
        return api_error(
            "Request body must contain 'password'",
            StatusCode::BAD_REQUEST,
            "bad_request",
        );
    };
    let result = secret_store::export_key(password, &state.config.project_root);
    if result["success"].as_bool() == Some(false) {
        return api_error(
            result["message"].as_str().unwrap_or("export failed"),
            StatusCode::BAD_REQUEST,
            "export_failed",
        );
    }
    api_result(result)
}

pub async fn api_secrets_import(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let missing = body.get("export_data").is_none() || body.get("password").is_none();
    if missing {
        return api_error(
            "Request body must contain 'export_data' and 'password'",
            StatusCode::BAD_REQUEST,
            "bad_request",
        );
    }
    let export_data = &body["export_data"];
    let password = body["password"].as_str().unwrap_or("");
    let result = secret_store::import_key(export_data, password, &state.config.project_root);
    if result["success"].as_bool() == Some(false) {
        return api_error(
            result["message"].as_str().unwrap_or("import failed"),
            StatusCode::BAD_REQUEST,
            "import_failed",
        );
    }
    api_result(result)
}

pub async fn api_secrets_migrate_keychain(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let result = secret_store::migrate_to_keychain(&state.config.project_root);
    if result["success"].as_bool() == Some(false) {
        return api_error(
            result["message"].as_str().unwrap_or("migration failed"),
            StatusCode::BAD_REQUEST,
            "migration_failed",
        );
    }
    api_result(result)
}

pub async fn api_secrets_migrate(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match migrate_plaintext_secrets(&state) {
        Ok(migrated) => api_result(json!({"migrated": migrated})),
        Err(error) => internal_error(error, "failed to migrate plaintext secrets"),
    }
}

pub async fn api_secrets_rotate(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match rotate_secrets(&state) {
        Ok(value) => api_result(value),
        Err(error) => internal_error(error, "failed to rotate secrets"),
    }
}

pub async fn api_settings_bw_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(bw_status_with_cli(&CommandVaultCli).await)
}

pub async fn api_secrets_bw_folders(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match bw_folders_with_cli(&CommandVaultCli).await {
        Ok(folders) => api_result(json!({"folders": folders})),
        Err(VaultApiError::Unavailable) => api_error(
            "Bitwarden CLI (bw) が利用できません",
            StatusCode::SERVICE_UNAVAILABLE,
            "bw_unavailable",
        ),
        Err(VaultApiError::PushFailed(message)) => api_error(
            &message,
            StatusCode::INTERNAL_SERVER_ERROR,
            "bw_push_failed",
        ),
        Err(VaultApiError::NoSecrets | VaultApiError::BadRequest(_) | VaultApiError::Io(_)) => {
            internal_error("unexpected bw folders error", "failed to list bw folders")
        }
    }
}

pub async fn api_secrets_push_to_bw(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<PushToBwRequest>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(Json(body)) = body else {
        return api_error(
            "リクエストボディが必要です",
            StatusCode::BAD_REQUEST,
            "bad_request",
        );
    };
    match push_to_bw_with_cli(&state, &CommandVaultCli, body).await {
        Ok(value) => api_result(value),
        Err(VaultApiError::Unavailable) => api_error(
            "Bitwarden CLI (bw) が利用できません",
            StatusCode::SERVICE_UNAVAILABLE,
            "bw_unavailable",
        ),
        Err(VaultApiError::NoSecrets) => api_error(
            "書き込み対象のシークレットがありません",
            StatusCode::BAD_REQUEST,
            "no_secrets",
        ),
        Err(VaultApiError::BadRequest(message)) => {
            api_error(&message, StatusCode::BAD_REQUEST, "bad_request")
        }
        Err(VaultApiError::PushFailed(message)) => api_error(
            &message,
            StatusCode::INTERNAL_SERVER_ERROR,
            "bw_push_failed",
        ),
        Err(VaultApiError::Io(error)) => internal_error(error, "failed to push secrets to bw"),
    }
}

pub async fn api_settings_bw_mapping_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(key): AxumPath<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match delete_vault_mapping(&state.config.config_path, "bw_secrets", &key) {
        Ok(true) => api_result(json!({"key": key, "unlinked": true})),
        Ok(false) => api_error(
            "Key not in bw_secrets mapping",
            StatusCode::NOT_FOUND,
            "not_found",
        ),
        Err(error) => internal_error(error, "failed to delete bw mapping"),
    }
}

pub async fn api_settings_op_status(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    api_result(op_status_with_cli(&CommandVaultCli).await)
}

pub async fn api_settings_op_mapping_delete(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    AxumPath(key): AxumPath<String>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match delete_vault_mapping(&state.config.config_path, "op_secrets", &key) {
        Ok(true) => api_result(json!({"key": key, "unlinked": true})),
        Ok(false) => api_error(
            "Key not in op_secrets mapping",
            StatusCode::NOT_FOUND,
            "not_found",
        ),
        Err(error) => internal_error(error, "failed to delete op mapping"),
    }
}

pub async fn api_secrets_op_vaults(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    match op_vaults_with_cli(&CommandVaultCli).await {
        Ok(vaults) => api_result(json!({"vaults": vaults})),
        Err(VaultApiError::Unavailable) => api_error(
            "1Password CLI (op) が利用できません",
            StatusCode::SERVICE_UNAVAILABLE,
            "op_unavailable",
        ),
        Err(VaultApiError::PushFailed(message)) => api_error(
            &message,
            StatusCode::INTERNAL_SERVER_ERROR,
            "op_push_failed",
        ),
        Err(VaultApiError::NoSecrets | VaultApiError::BadRequest(_) | VaultApiError::Io(_)) => {
            internal_error("unexpected op vaults error", "failed to list op vaults")
        }
    }
}

pub async fn api_secrets_push_to_op(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<PushToOpRequest>>,
) -> Response {
    if let Some(response) = admin_scope_error(&state, auth_context.as_ref()) {
        return response;
    }
    let Some(Json(body)) = body else {
        return api_error(
            "リクエストボディに 'vault' が必要です",
            StatusCode::BAD_REQUEST,
            "bad_request",
        );
    };
    if body.vault.as_deref().is_none_or(str::is_empty) {
        return api_error(
            "リクエストボディに 'vault' が必要です",
            StatusCode::BAD_REQUEST,
            "bad_request",
        );
    }
    match push_to_op_with_cli(&state, &CommandVaultCli, body).await {
        Ok(value) => api_result(value),
        Err(VaultApiError::Unavailable) => api_error(
            "1Password CLI (op) が利用できません",
            StatusCode::SERVICE_UNAVAILABLE,
            "op_unavailable",
        ),
        Err(VaultApiError::NoSecrets) => api_error(
            "書き込み対象のシークレットがありません",
            StatusCode::BAD_REQUEST,
            "no_secrets",
        ),
        Err(VaultApiError::BadRequest(message)) => {
            api_error(&message, StatusCode::BAD_REQUEST, "bad_request")
        }
        Err(VaultApiError::PushFailed(message)) => api_error(
            &message,
            StatusCode::INTERNAL_SERVER_ERROR,
            "op_push_failed",
        ),
        Err(VaultApiError::Io(error)) => internal_error(error, "failed to push secrets to op"),
    }
}

enum SettingsWriteError {
    BadRequest(String),
    Io(std::io::Error),
}

#[derive(Debug)]
enum VaultApiError {
    Unavailable,
    NoSecrets,
    BadRequest(String),
    PushFailed(String),
    Io(std::io::Error),
}

impl From<std::io::Error> for VaultApiError {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}

impl From<std::io::Error> for SettingsWriteError {
    fn from(error: std::io::Error) -> Self {
        Self::Io(error)
    }
}

fn build_all_settings(state: &SharedState) -> Result<Vec<Value>, std::io::Error> {
    let schema = load_schema_defs(&state.config.project_root)?;
    let config = load_config_json(&state.config.config_path);
    Ok(schema
        .iter()
        .map(|setting| setting_value(setting, &config, &state.config.project_root))
        .collect())
}

fn update_setting(
    state: &SharedState,
    key: &str,
    body: SettingValueRequest,
) -> Result<bool, SettingsWriteError> {
    let schema = load_schema_defs(&state.config.project_root)?;
    let Some(setting) = schema.iter().find(|setting| setting.key == key) else {
        return Ok(false);
    };
    let Some(value) = body.value else {
        return Err(SettingsWriteError::BadRequest(
            "Request body must contain 'value'".to_string(),
        ));
    };
    let value = coerce_value(value, &setting.type_name)?;
    let mut config = load_config_json(&state.config.config_path);
    if let Some(op_uri) = body.op_uri.as_deref().filter(|uri| !uri.is_empty()) {
        ensure_object_field(&mut config, "op_secrets")?.insert(key.to_string(), json!(op_uri));
    } else {
        let stored = if setting.secret {
            value
                .as_str()
                .filter(|raw| !raw.is_empty())
                .map(|raw| json!(secret_store::encrypt(raw, &state.config.project_root)))
                .unwrap_or(value)
        } else {
            value
        };
        set_dotted_key(&mut config, key, stored)?;
    }
    write_config_json(&state.config.config_path, &config)?;
    Ok(true)
}

fn build_single_setting(state: &SharedState, key: &str) -> Result<Option<Value>, std::io::Error> {
    let schema = load_schema_defs(&state.config.project_root)?;
    let Some(setting) = schema.iter().find(|setting| setting.key == key) else {
        return Ok(None);
    };
    let config = load_config_json(&state.config.config_path);
    Ok(Some(setting_value(
        setting,
        &config,
        &state.config.project_root,
    )))
}

fn coerce_value(value: Value, type_name: &str) -> Result<Value, SettingsWriteError> {
    if value.is_null() {
        return Ok(value);
    }
    match type_name {
        "bool" if value.is_boolean() => Ok(value),
        "bool" => Err(SettingsWriteError::BadRequest(
            "value must be a boolean".to_string(),
        )),
        "int" if value.as_i64().is_some() => Ok(value),
        "int" => Err(SettingsWriteError::BadRequest(
            "value must be an integer".to_string(),
        )),
        "float" if value.as_f64().is_some() => Ok(value),
        "float" => Err(SettingsWriteError::BadRequest(
            "value must be a number".to_string(),
        )),
        "str" if value.is_string() => Ok(value),
        "str" => Err(SettingsWriteError::BadRequest(
            "value must be a string".to_string(),
        )),
        _ => Ok(value),
    }
}

fn setting_value(setting: &SettingDef, config: &Value, project_root: &Path) -> Value {
    let op_map = config.get("op_secrets").and_then(Value::as_object);
    let bw_map = config.get("bw_secrets").and_then(Value::as_object);
    let raw = resolve_dotted_key(config, &setting.key);

    let mut source = "default";
    let mut display = setting.default.clone();

    if op_map.is_some_and(|map| map.contains_key(&setting.key)) {
        source = "1password";
        display = if setting.secret {
            Value::String("****".to_string())
        } else {
            Value::Null
        };
    } else if bw_map.is_some_and(|map| map.contains_key(&setting.key)) {
        source = "bitwarden";
        display = if setting.secret {
            Value::String("****".to_string())
        } else {
            Value::Null
        };
    } else if let Some(raw) = raw {
        if setting.secret {
            source = if is_encrypted_value(raw) {
                "encrypted"
            } else {
                "config"
            };
            display = Value::String(mask_config_secret(raw, project_root));
        } else {
            source = "config";
            display = raw.clone();
        }
    } else if setting.key == "timezone" && display.is_null() {
        if let Some(timezone) = detect_system_timezone() {
            source = "system";
            display = Value::String(timezone);
        }
    }

    json!({
        "key": setting.key,
        "value": display,
        "source": source,
        "secret": setting.secret,
        "category": setting.category,
    })
}

fn load_schema_json(project_root: &Path) -> Result<Value, std::io::Error> {
    let raw = std::fs::read_to_string(schema_path(project_root))?;
    Ok(serde_json::from_str::<Value>(&raw).unwrap_or_else(|_| json!([])))
}

fn load_schema_defs(project_root: &Path) -> Result<Vec<SettingDef>, std::io::Error> {
    let raw = std::fs::read_to_string(schema_path(project_root))?;
    Ok(serde_json::from_str::<Vec<SettingDef>>(&raw).unwrap_or_default())
}

/// Canonical location of the generated settings schema. `misc_admin`
/// reads the same file for its config hints, so keep this the only
/// place the path is spelled out.
pub(crate) fn schema_path(project_root: &Path) -> PathBuf {
    project_root.join("config").join("settings_schema.json")
}

fn resolve_dotted_key<'a>(config: &'a Value, key: &str) -> Option<&'a Value> {
    let mut current = config;
    for part in key.split('.') {
        let object = current.as_object()?;
        current = object.get(part)?;
    }
    Some(current)
}

fn set_dotted_key(config: &mut Value, key: &str, value: Value) -> Result<(), SettingsWriteError> {
    let mut current = config;
    let mut parts = key.split('.').peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            ensure_object(current)?.insert(part.to_string(), value);
            return Ok(());
        }
        current = ensure_object(current)?
            .entry(part.to_string())
            .or_insert_with(|| json!({}));
    }
    Ok(())
}

fn ensure_object(
    value: &mut Value,
) -> Result<&mut serde_json::Map<String, Value>, SettingsWriteError> {
    if !value.is_object() {
        *value = json!({});
    }
    value
        .as_object_mut()
        .ok_or_else(|| SettingsWriteError::BadRequest("config object is invalid".to_string()))
}

fn ensure_object_field<'a>(
    config: &'a mut Value,
    field: &str,
) -> Result<&'a mut serde_json::Map<String, Value>, SettingsWriteError> {
    let object = ensure_object(config)?;
    let field_value = object.entry(field.to_string()).or_insert_with(|| json!({}));
    ensure_object(field_value)
}

fn is_encrypted_value(value: &Value) -> bool {
    value
        .as_str()
        .map(|raw| raw.starts_with("enc:"))
        .unwrap_or(false)
}

fn mask_config_secret(value: &Value, project_root: &Path) -> String {
    let raw = value
        .as_str()
        .map(str::to_string)
        .unwrap_or_else(|| value.to_string());
    let plaintext = if raw.starts_with("enc:") {
        secret_store::decrypt(&raw, project_root)
    } else {
        raw
    };
    secret_store::mask_secret(&plaintext)
}

fn detect_system_timezone() -> Option<String> {
    if let Ok(tz) = std::env::var("TZ") {
        let tz = tz.trim();
        if !tz.is_empty() {
            return Some(tz.to_string());
        }
    }
    let raw = std::fs::read_to_string("/etc/timezone").ok()?;
    let tz = raw.trim();
    (!tz.is_empty()).then(|| tz.to_string())
}

fn secret_status(project_root: &Path) -> Value {
    let data_dir = secret_store::data_dir(project_root);
    let key_path = data_dir.join("secret.key");
    let has_passphrase = std::env::var_os("YU_SECRET_PASSPHRASE").is_some();
    let file_available = key_path.exists();
    let active_backend = if has_passphrase { "passphrase" } else { "file" };

    json!({
        "active_backend": active_backend,
        "backends": {
            "passphrase": {
                "available": has_passphrase,
                "active": active_backend == "passphrase",
            },
            "keychain": {
                "available": false,
                "active": false,
                "backend_name": Value::Null,
            },
            "file": {
                "available": file_available,
                "active": active_backend == "file",
                "path": key_path
                    .canonicalize()
                    .unwrap_or(key_path)
                    .to_string_lossy()
                    .to_string(),
            },
        },
    })
}

fn migrate_plaintext_secrets(state: &SharedState) -> Result<usize, std::io::Error> {
    let schema = load_schema_defs(&state.config.project_root)?;
    let mut config = load_config_json(&state.config.config_path);
    let mut count = 0;
    for setting in schema.iter().filter(|setting| setting.secret) {
        let Some(raw) = resolve_dotted_key(&config, &setting.key).and_then(Value::as_str) else {
            continue;
        };
        if raw.is_empty() || raw.starts_with("enc:") || raw.contains("****") || raw.contains("...")
        {
            continue;
        }
        let encrypted = secret_store::encrypt(raw, &state.config.project_root);
        set_dotted_key(&mut config, &setting.key, json!(encrypted))
            .map_err(settings_write_to_io)?;
        count += 1;
    }
    if count > 0 {
        write_config_json(&state.config.config_path, &config)?;
    }
    Ok(count)
}

fn rotate_secrets(state: &SharedState) -> Result<Value, std::io::Error> {
    let schema = load_schema_defs(&state.config.project_root)?;
    let mut config = load_config_json(&state.config.config_path);
    let (new_key_id, new_key) =
        secret_store::generate_new_active_key(&state.config.project_root)
            .ok_or_else(|| std::io::Error::other("failed to generate new secret key"))?;
    let mut rotated = 0;
    for setting in schema.iter().filter(|setting| setting.secret) {
        let Some(raw) = resolve_dotted_key(&config, &setting.key).and_then(Value::as_str) else {
            continue;
        };
        if raw.is_empty() {
            continue;
        }
        let plaintext = secret_store::decrypt(raw, &state.config.project_root);
        if plaintext.is_empty() && raw.starts_with("enc:") {
            continue;
        }
        if plaintext.is_empty() {
            continue;
        }
        let encrypted = secret_store::encrypt_with_key_id(&plaintext, &new_key_id, &new_key)
            .ok_or_else(|| std::io::Error::other("encrypt failed"))?;
        set_dotted_key(&mut config, &setting.key, json!(encrypted))
            .map_err(settings_write_to_io)?;
        rotated += 1;
    }
    write_config_json(&state.config.config_path, &config)?;
    Ok(json!({"ok": true, "rotated": rotated, "new_key_id": new_key_id}))
}

async fn bw_status_with_cli(cli: &dyn VaultCli) -> Value {
    let has_session = bw_session().is_some();
    if !cli.is_available("bw") {
        return json!({
            "available": false,
            "signed_in": false,
            "status": "not_installed",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        });
    }
    let args = bw_args(&["status"]);
    match cli.run("bw", &arg_refs(&args), None, BW_TIMEOUT).await {
        Ok(output) if output.status == 0 => {
            let info = serde_json::from_str::<Value>(&output.stdout).unwrap_or_else(|_| json!({}));
            let status = info
                .get("status")
                .and_then(Value::as_str)
                .unwrap_or("unauthenticated");
            json!({
                "available": true,
                "signed_in": status == "unlocked",
                "status": status,
                "user_email": info.get("userEmail").and_then(Value::as_str).unwrap_or(""),
                "server_url": info.get("serverUrl").and_then(Value::as_str).unwrap_or(""),
                "has_session": has_session,
            })
        }
        Err(CliError::Timeout) => json!({
            "available": true,
            "signed_in": false,
            "status": "timeout",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        }),
        Err(CliError::NotFound) | Err(CliError::Io(_)) => json!({
            "available": false,
            "signed_in": false,
            "status": "error",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        }),
        Ok(_) => json!({
            "available": true,
            "signed_in": false,
            "status": "error",
            "user_email": "",
            "server_url": "",
            "has_session": has_session,
        }),
    }
}

async fn bw_folders_with_cli(cli: &dyn VaultCli) -> Result<Value, VaultApiError> {
    if !cli.is_available("bw") {
        return Err(VaultApiError::Unavailable);
    }
    let args = bw_args(&["list", "folders"]);
    let output = cli.run("bw", &arg_refs(&args), None, BW_TIMEOUT).await;
    let Ok(output) = output else {
        return Ok(json!([]));
    };
    if output.status != 0 {
        return Ok(json!([]));
    }
    let folders = serde_json::from_str::<Vec<Value>>(&output.stdout).unwrap_or_default();
    Ok(Value::Array(
        folders
            .into_iter()
            .map(|folder| {
                json!({
                    "id": folder.get("id").and_then(Value::as_str).unwrap_or(""),
                    "name": folder.get("name").and_then(Value::as_str).unwrap_or(""),
                })
            })
            .collect(),
    ))
}

async fn push_to_bw_with_cli(
    state: &SharedState,
    cli: &dyn VaultCli,
    body: PushToBwRequest,
) -> Result<Value, VaultApiError> {
    if !cli.is_available("bw") {
        return Err(VaultApiError::Unavailable);
    }
    let item_name = body
        .item_name
        .unwrap_or_else(|| "YU AI Manager".to_string());
    let mut config = load_config_json(&state.config.config_path);
    let schema = load_schema_defs(&state.config.project_root)?;
    let secrets = collect_plaintext_secrets(&schema, &config, &state.config.project_root);
    if secrets.is_empty() {
        return Err(VaultApiError::NoSecrets);
    }
    let result = push_secrets_to_bw(cli, body.folder_id.as_deref(), &item_name, &secrets).await;
    drop(secrets);
    let result = result?;
    config["bw_secrets"] = result["mappings"].clone();
    write_config_json(&state.config.config_path, &config)?;
    Ok(json!({
        "message": result["message"].clone(),
        "pushed_keys": result["pushed_keys"].clone(),
        "mappings": result["mappings"].clone(),
    }))
}

async fn push_secrets_to_bw(
    cli: &dyn VaultCli,
    folder_id: Option<&str>,
    item_name: &str,
    secrets: &HashMap<String, String>,
) -> Result<Value, VaultApiError> {
    if let Some(message) = validate_name(item_name, "アイテム名") {
        return Err(VaultApiError::PushFailed(message));
    }
    let mut key_to_field = HashMap::new();
    let mut new_fields = Vec::new();
    for (key, value) in secrets {
        let field_name = key_to_field_name(key);
        key_to_field.insert(key.clone(), field_name.clone());
        new_fields.push(json!({"name": field_name, "value": value, "type": 1}));
    }
    let search_args = bw_args(&["list", "items", "--search", item_name]);
    let mut existing_item = None;
    match cli
        .run("bw", &arg_refs(&search_args), None, BW_TIMEOUT)
        .await
    {
        Ok(output) if output.status == 0 => {
            let items = serde_json::from_str::<Vec<Value>>(&output.stdout).unwrap_or_default();
            existing_item = items
                .into_iter()
                .find(|item| item.get("name").and_then(Value::as_str) == Some(item_name));
        }
        Err(CliError::Timeout) => {
            return Err(VaultApiError::PushFailed(
                "bw list items タイムアウト".to_string(),
            ));
        }
        _ => {}
    }
    let (args, stdin_data, item_id_for_fallback, action) = if let Some(mut item) = existing_item {
        let item_id = item
            .get("id")
            .and_then(Value::as_str)
            .unwrap_or("")
            .to_string();
        let new_names: std::collections::HashSet<String> = new_fields
            .iter()
            .filter_map(|field| {
                field
                    .get("name")
                    .and_then(Value::as_str)
                    .map(str::to_string)
            })
            .collect();
        let mut merged = item
            .get("fields")
            .and_then(Value::as_array)
            .cloned()
            .unwrap_or_default()
            .into_iter()
            .filter(|field| {
                field
                    .get("name")
                    .and_then(Value::as_str)
                    .is_none_or(|name| !new_names.contains(name))
            })
            .collect::<Vec<_>>();
        merged.extend(new_fields);
        item["fields"] = Value::Array(merged);
        let encoded = base64::engine::general_purpose::STANDARD
            .encode(serde_json::to_vec(&item).unwrap_or_default());
        let args = bw_args(&["edit", "item", &item_id]);
        (args, encoded, item_id, "更新")
    } else {
        let item = json!({
            "type": 2,
            "name": item_name,
            "notes": "",
            "folderId": folder_id,
            "fields": new_fields,
            "secureNote": {"type": 0},
        });
        let encoded = base64::engine::general_purpose::STANDARD
            .encode(serde_json::to_vec(&item).unwrap_or_default());
        (bw_args(&["create", "item"]), encoded, String::new(), "作成")
    };
    let output = cli
        .run("bw", &arg_refs(&args), Some(stdin_data), BW_TIMEOUT)
        .await
        .map_err(|error| match error {
            CliError::Timeout => VaultApiError::PushFailed(format!(
                "bw {} item タイムアウト ({}秒)",
                if action == "更新" { "edit" } else { "create" },
                BW_TIMEOUT.as_secs()
            )),
            CliError::NotFound => VaultApiError::PushFailed("bw CLI が見つかりません".to_string()),
            CliError::Io(error) => VaultApiError::Io(error),
        })?;
    if output.status != 0 {
        return Err(VaultApiError::PushFailed(parse_bw_error(&output.stderr)));
    }
    let created = serde_json::from_str::<Value>(&output.stdout).unwrap_or_else(|_| json!({}));
    let result_id = created
        .get("id")
        .and_then(Value::as_str)
        .unwrap_or(&item_id_for_fallback);
    let mappings = key_to_field
        .into_iter()
        .map(|(key, field)| (key, json!({"item": result_id, "field": field})))
        .collect::<serde_json::Map<_, _>>();
    let pushed_keys = mappings
        .keys()
        .cloned()
        .map(Value::String)
        .collect::<Vec<_>>();
    Ok(json!({
        "message": format!("{} 件のシークレットを Bitwarden に{}しました", mappings.len(), action),
        "pushed_keys": pushed_keys,
        "mappings": mappings,
    }))
}

async fn op_status_with_cli(cli: &dyn VaultCli) -> Value {
    let platform = platform_name();
    let has_service_account_token = std::env::var_os("OP_SERVICE_ACCOUNT_TOKEN").is_some();
    if !cli.is_available("op") {
        return json!({
            "available": false,
            "signed_in": false,
            "account": "",
            "auth_method": "none",
            "platform": platform,
            "has_service_account_token": has_service_account_token,
            "has_biometric": false,
        });
    }
    let mut auth_method = detect_op_auth_method();
    let mut account = String::new();
    let mut signed_in = false;
    match cli
        .run("op", &["whoami", "--format=json"], None, OP_TIMEOUT)
        .await
    {
        Ok(output) if output.status == 0 => {
            let info = serde_json::from_str::<Value>(&output.stdout).unwrap_or_else(|_| json!({}));
            account = info
                .get("email")
                .or_else(|| info.get("url"))
                .and_then(Value::as_str)
                .unwrap_or("")
                .to_string();
            signed_in = true;
        }
        _ => {}
    }
    if !signed_in {
        match cli
            .run(
                "op",
                &["account", "list", "--format=json"],
                None,
                OP_TIMEOUT,
            )
            .await
        {
            Ok(output) if output.status == 0 => {
                let accounts =
                    serde_json::from_str::<Vec<Value>>(&output.stdout).unwrap_or_default();
                if let Some(first) = accounts.first() {
                    signed_in = true;
                    account = first
                        .get("email")
                        .or_else(|| first.get("url"))
                        .and_then(Value::as_str)
                        .unwrap_or("")
                        .to_string();
                    if auth_method == "manual" {
                        auth_method = "biometric".to_string();
                    }
                }
            }
            _ => {}
        }
    }
    json!({
        "available": true,
        "signed_in": signed_in,
        "account": account,
        "auth_method": auth_method,
        "platform": platform,
        "has_service_account_token": has_service_account_token,
        "has_biometric": auth_method == "biometric",
    })
}

async fn op_vaults_with_cli(cli: &dyn VaultCli) -> Result<Value, VaultApiError> {
    if !cli.is_available("op") {
        return Err(VaultApiError::Unavailable);
    }
    let output = cli
        .run(
            "op",
            &["vault", "list", "--format", "json"],
            None,
            OP_TIMEOUT,
        )
        .await;
    let Ok(output) = output else {
        return Ok(json!([]));
    };
    if output.status != 0 {
        return Ok(json!([]));
    }
    let vaults = serde_json::from_str::<Vec<Value>>(&output.stdout).unwrap_or_default();
    Ok(Value::Array(
        vaults
            .into_iter()
            .map(|vault| {
                json!({
                    "id": vault.get("id").and_then(Value::as_str).unwrap_or(""),
                    "name": vault.get("name").and_then(Value::as_str).unwrap_or(""),
                })
            })
            .collect(),
    ))
}

async fn push_to_op_with_cli(
    state: &SharedState,
    cli: &dyn VaultCli,
    body: PushToOpRequest,
) -> Result<Value, VaultApiError> {
    if !cli.is_available("op") {
        return Err(VaultApiError::Unavailable);
    }
    let vault = body.vault.unwrap_or_default();
    let item_title = body
        .item_title
        .unwrap_or_else(|| "YU AI Manager".to_string());
    let remove_local = body.remove_local.unwrap_or(false);
    let mut config = load_config_json(&state.config.config_path);
    let schema = load_schema_defs(&state.config.project_root)?;
    let secrets = collect_plaintext_secrets(&schema, &config, &state.config.project_root);
    if secrets.is_empty() {
        return Err(VaultApiError::NoSecrets);
    }
    let result = push_secrets_to_op(cli, &vault, &item_title, &secrets).await;
    drop(secrets);
    let result = result?;
    let uris = result
        .get("uris")
        .and_then(Value::as_object)
        .cloned()
        .unwrap_or_default();
    ensure_object_field(&mut config, "op_secrets")
        .map_err(settings_write_to_io)?
        .extend(uris.clone());
    if remove_local {
        for key in uris.keys() {
            delete_dotted_key(&mut config, key);
        }
    }
    write_config_json(&state.config.config_path, &config)?;
    Ok(json!({
        "message": result["message"].clone(),
        "pushed_keys": result["pushed_keys"].clone(),
        "uris": result["uris"].clone(),
        "remove_local": remove_local,
    }))
}

async fn push_secrets_to_op(
    cli: &dyn VaultCli,
    vault: &str,
    item_title: &str,
    secrets: &HashMap<String, String>,
) -> Result<Value, VaultApiError> {
    if let Some(message) = validate_name(vault, "Vault 名") {
        return Err(VaultApiError::PushFailed(message));
    }
    if let Some(message) = validate_name(item_title, "アイテムタイトル") {
        return Err(VaultApiError::PushFailed(message));
    }
    let mut key_to_field = HashMap::new();
    let fields = secrets
        .iter()
        .map(|(key, value)| {
            let field = key_to_field_name(key);
            key_to_field.insert(key.clone(), field.clone());
            json!({"id": field, "type": "CONCEALED", "value": value})
        })
        .collect::<Vec<_>>();
    let mut item_exists = false;
    match cli
        .run(
            "op",
            &[
                "item", "get", item_title, "--vault", vault, "--format", "json",
            ],
            None,
            OP_TIMEOUT,
        )
        .await
    {
        Ok(output) if output.status == 0 => item_exists = true,
        Err(CliError::Timeout) => {
            return Err(VaultApiError::PushFailed(
                "op item get タイムアウト".to_string(),
            ));
        }
        _ => {}
    }
    let template = json!({
        "title": item_title,
        "vault": {"name": vault},
        "category": "SECURE_NOTE",
        "fields": fields,
    });
    let template_json = serde_json::to_string(&template).unwrap_or_default();
    let (args, action) = if item_exists {
        (
            vec![
                "item", "edit", item_title, "--vault", vault, "--format", "json",
            ],
            "更新",
        )
    } else {
        (vec!["item", "create", "--format", "json"], "作成")
    };
    let output = cli
        .run("op", &args, Some(template_json), OP_TIMEOUT)
        .await
        .map_err(|error| match error {
            CliError::Timeout => VaultApiError::PushFailed(format!(
                "op item {} タイムアウト ({}秒)",
                if item_exists { "edit" } else { "create" },
                OP_TIMEOUT.as_secs()
            )),
            CliError::NotFound => VaultApiError::PushFailed("op CLI が見つかりません".to_string()),
            CliError::Io(error) => VaultApiError::Io(error),
        })?;
    if output.status != 0 {
        return Err(VaultApiError::PushFailed(parse_op_error(&output.stderr)));
    }
    let uris = key_to_field
        .into_iter()
        .map(|(key, field)| {
            (
                key,
                Value::String(format!("op://{vault}/{item_title}/{field}")),
            )
        })
        .collect::<serde_json::Map<_, _>>();
    let pushed_keys = uris.keys().cloned().map(Value::String).collect::<Vec<_>>();
    Ok(json!({
        "message": format!("{} 件のシークレットを 1Password に{}しました", uris.len(), action),
        "pushed_keys": pushed_keys,
        "uris": uris,
    }))
}

fn collect_plaintext_secrets(
    schema: &[SettingDef],
    config: &Value,
    project_root: &Path,
) -> HashMap<String, String> {
    schema
        .iter()
        .filter(|setting| setting.secret)
        .filter_map(|setting| {
            let raw = resolve_dotted_key(config, &setting.key)?;
            if raw.is_null() {
                return None;
            }
            let raw = raw
                .as_str()
                .map(str::to_string)
                .unwrap_or_else(|| raw.to_string());
            if raw.is_empty() {
                return None;
            }
            let plaintext = if raw.starts_with("enc:") {
                secret_store::decrypt(&raw, project_root)
            } else {
                raw
            };
            (!plaintext.is_empty()).then(|| (setting.key.clone(), plaintext))
        })
        .collect()
}

fn delete_vault_mapping(
    config_path: &Path,
    field: &str,
    key: &str,
) -> Result<bool, std::io::Error> {
    let mut config = load_config_json(config_path);
    let Some(map) = config.get_mut(field).and_then(Value::as_object_mut) else {
        return Ok(false);
    };
    if map.remove(key).is_none() {
        return Ok(false);
    }
    if map.is_empty() {
        if let Some(config_map) = config.as_object_mut() {
            config_map.remove(field);
        }
    }
    write_config_json(config_path, &config)?;
    Ok(true)
}

fn delete_dotted_key(config: &mut Value, key: &str) -> bool {
    let mut current = config;
    let mut parts = key.split('.').peekable();
    while let Some(part) = parts.next() {
        if parts.peek().is_none() {
            return current
                .as_object_mut()
                .and_then(|object| object.remove(part))
                .is_some();
        }
        let Some(next) = current
            .as_object_mut()
            .and_then(|object| object.get_mut(part))
        else {
            return false;
        };
        current = next;
    }
    false
}

fn bw_session() -> Option<String> {
    std::env::var("BW_SESSION")
        .ok()
        .map(|session| session.trim().to_string())
        .filter(|session| !session.is_empty())
}

fn bw_args(args: &[&str]) -> Vec<String> {
    let mut out = args
        .iter()
        .map(|arg| (*arg).to_string())
        .collect::<Vec<_>>();
    out.push("--nointeraction".to_string());
    if let Some(session) = bw_session() {
        out.push("--session".to_string());
        out.push(session);
    }
    out
}

fn arg_refs(args: &[String]) -> Vec<&str> {
    args.iter().map(String::as_str).collect()
}

fn key_to_field_name(key: &str) -> String {
    key.replace('.', "_")
}

fn validate_name(value: &str, label: &str) -> Option<String> {
    if value.trim().is_empty() {
        return Some(format!("{label} が空です"));
    }
    if value.chars().count() > 200 {
        return Some(format!("{label} が長すぎます (200 文字以内)"));
    }
    if value.chars().any(|ch| {
        matches!(
            ch,
            ';' | '|' | '&' | '`' | '$' | '\\' | '<' | '>' | '"' | '\'' | '\n' | '\r' | '\0'
        )
    }) {
        return Some(format!("{label} に使用できない文字が含まれています"));
    }
    None
}

fn parse_bw_error(stderr: &str) -> String {
    let lower = stderr.to_lowercase();
    if lower.contains("not logged in") || lower.contains("unauthenticated") {
        return "Bitwarden にログインされていません。bw login を実行してください".to_string();
    }
    if lower.contains("vault is locked") || lower.contains("locked") {
        return "Bitwarden の保管庫がロックされています。bw unlock を実行してください".to_string();
    }
    if lower.contains("not found") {
        return "指定されたアイテムが見つかりません".to_string();
    }
    if lower.contains("session key") {
        return "セッションkeyが無効です。BW_SESSION 環境変数を確認してください".to_string();
    }
    if lower.contains("more than one") || lower.contains("multiple") {
        return "同名のアイテムが複数存在します。アイテム ID を指定してください".to_string();
    }
    let trimmed = stderr.trim();
    if trimmed.is_empty() {
        "不明なエラーが発生しました".to_string()
    } else {
        trimmed.to_string()
    }
}

fn parse_op_error(stderr: &str) -> String {
    let lower = stderr.to_lowercase();
    if lower.contains("not signed in") || lower.contains("sign in") {
        return "1Password にサインインされていません。op signin を実行してください".to_string();
    }
    if lower.contains("could not be found") {
        return "指定されたアイテムまたは vault が見つかりません".to_string();
    }
    if lower.contains("not authorized") || lower.contains("permission") {
        return "1Password のアクセス権限がありません".to_string();
    }
    if lower.contains("more than one item") {
        return "同名のアイテムが複数存在します。vault を確認してください".to_string();
    }
    let trimmed = stderr.trim();
    if trimmed.is_empty() {
        "不明なエラーが発生しました".to_string()
    } else {
        trimmed.to_string()
    }
}

fn detect_op_auth_method() -> String {
    if std::env::var_os("OP_SERVICE_ACCOUNT_TOKEN").is_some() {
        return "service_account".to_string();
    }
    if std::env::var("OP_BIOMETRIC_UNLOCK_ENABLED").ok().as_deref() == Some("true") {
        return "biometric".to_string();
    }
    #[cfg(target_os = "macos")]
    {
        let socket = std::env::var_os("HOME").map(PathBuf::from).map(|home| {
            home.join("Library")
                .join("Group Containers")
                .join("2BUA8C4S2C.com.1password")
                .join("t")
                .join("agent.sock")
        });
        if socket.is_some_and(|path| path.exists()) {
            return "biometric".to_string();
        }
    }
    "manual".to_string()
}

fn platform_name() -> &'static str {
    #[cfg(target_os = "macos")]
    {
        "Darwin"
    }
    #[cfg(target_os = "windows")]
    {
        "Windows"
    }
    #[cfg(all(not(target_os = "macos"), not(target_os = "windows")))]
    {
        "Linux"
    }
}

fn executable_on_path(program: &str) -> bool {
    if program.contains(std::path::MAIN_SEPARATOR) {
        return Path::new(program).is_file();
    }
    std::env::var_os("PATH")
        .map(|paths| {
            std::env::split_paths(&paths).any(|path| {
                let candidate = path.join(program);
                if candidate.is_file() {
                    return true;
                }
                #[cfg(windows)]
                {
                    return path.join(format!("{program}.exe")).is_file();
                }
                #[allow(unreachable_code)]
                false
            })
        })
        .unwrap_or(false)
}

async fn run_command_with_timeout(
    program: &str,
    args: &[&str],
    stdin_data: Option<String>,
    timeout: Duration,
) -> Result<CliOutput, CliError> {
    let mut command = Command::new(program);
    command
        .args(args)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .stdin(if stdin_data.is_some() {
            Stdio::piped()
        } else {
            Stdio::null()
        });
    let mut child = command.spawn().map_err(|error| {
        if error.kind() == std::io::ErrorKind::NotFound {
            CliError::NotFound
        } else {
            CliError::Io(error)
        }
    })?;
    if let Some(input) = stdin_data {
        if let Some(mut stdin) = child.stdin.take() {
            tokio::spawn(async move {
                let _ = stdin.write_all(input.as_bytes()).await;
            });
        }
    }
    let mut stdout = child.stdout.take();
    let mut stderr = child.stderr.take();
    let stdout_task = tokio::spawn(async move {
        let mut bytes = Vec::new();
        if let Some(ref mut stdout) = stdout {
            let _ = stdout.read_to_end(&mut bytes).await;
        }
        bytes
    });
    let stderr_task = tokio::spawn(async move {
        let mut bytes = Vec::new();
        if let Some(ref mut stderr) = stderr {
            let _ = stderr.read_to_end(&mut bytes).await;
        }
        bytes
    });
    let status = tokio::select! {
        status = child.wait() => status.map_err(CliError::Io)?,
        _ = tokio::time::sleep(timeout) => {
            let _ = child.kill().await;
            let _ = child.wait().await;
            let _ = stdout_task.await;
            let _ = stderr_task.await;
            return Err(CliError::Timeout);
        }
    };
    let stdout = stdout_task.await.unwrap_or_default();
    let stderr = stderr_task.await.unwrap_or_default();
    Ok(CliOutput {
        status: status.code().unwrap_or(-1),
        stdout: String::from_utf8_lossy(&stdout).into_owned(),
        stderr: String::from_utf8_lossy(&stderr).into_owned(),
    })
}

fn settings_write_to_io(error: SettingsWriteError) -> std::io::Error {
    match error {
        SettingsWriteError::BadRequest(message) => {
            std::io::Error::new(std::io::ErrorKind::InvalidData, message)
        }
        SettingsWriteError::Io(error) => error,
    }
}

// --- GET /api/settings/config helpers ---

fn default_config() -> Value {
    serde_json::json!({
        "timezone": null,
        "ui": null,
        "direct_prompt_convert": false,
        "preserve_templates": true,
        "brace_choice": false,
        "extract_comfyui": true,
        "extract_a1111": true,
        "enable_fts": true,
        "lowercase_tags": true,
        "compute_hash": false,
        "archive_throttle_ms": 20,
        "media_cache": {"l1_max_items": 20000, "l1_max_mb": 512},
        "server": {
            "host": "127.0.0.1",
            "port": 5000,
            "lan": false,
            "pin": null,
            "pin_boss_login_ui": true,
            "quick_lock_enabled": true,
            "allow_restart": false,
            "allow_remote_restart": false,
            "restart_token": null
        },
        "remote_fs": {
            "probe_retries": 6,
            "probe_wait": 5.0,
            "enumerate_retries": 5,
            "enumerate_wait": 10.0
        },
        "scan_exclude_dirs": [
            ".git", ".svn", ".hg",
            "node_modules", "__pycache__", ".pytest_cache",
            "venv", ".venv", "env",
            "site-packages", "dist-packages",
            "custom_nodes", "extensions", "extensions-builtin",
            "screenshots", "reports"
        ],
        "video_analysis": {
            "enabled": true,
            "keyframe_count": 4,
            "strategy": "uniform",
            "scene_threshold": 0.4,
            "store_per_keyframe": false
        },
        "inference_worker": {"enabled": false},
        "hailo": {
            "auto_reboot": {
                "mode": "off",
                "dry_run": false,
                "prewarn_threshold_mb": 80,
                "prewarn_duration_seconds": 180,
                "drain_threshold_mb": 30,
                "drain_duration_seconds": 60,
                "drain_consecutive_rejects": 3,
                "fire_grace_seconds": 120,
                "poll_interval_seconds": 30,
                "min_uptime_minutes": 30,
                "max_reboots_per_day": 4,
                "cooldown_minutes": 15
            }
        },
        "hailo_genai": {"llm_subprocess": false},
        "api_keys": [],
        "webhooks": [],
        "webhook_secret": null,
        "backup": {
            "enabled": true,
            "backup_dir": "",
            "max_generations": 5,
            "periodic_interval_hours": 24,
            "backup_on_scan_complete": true,
            "cooldown_minutes": 5
        },
        "scheduler": {
            "enabled": true,
            "jobs": {
                "db_vacuum": {"enabled": true, "trigger": "cron", "day_of_week": "sun", "hour": 3, "minute": 0},
                "db_integrity_check": {"enabled": true, "trigger": "cron", "hour": 4, "minute": 0},
                "thumbnail_cleanup": {"enabled": true, "trigger": "cron", "hour": 5, "minute": 0},
                "thumbnail_cleanup_pressure": {"enabled": true, "trigger": "interval", "hours": 4},
                "thumbnail_integrity_check": {"enabled": true, "trigger": "cron", "day_of_week": "sat", "hour": 4, "minute": 30},
                "extension_audit_periodic": {"enabled": true, "trigger": "cron", "day_of_week": "wed", "hour": 2, "minute": 30},
                "extension_audit_surprise": {"enabled": true, "trigger": "interval", "hours": 6, "jitter": 3600}
            }
        },
        "agent_safety": {
            "circuit_breaker": {
                "enabled": true,
                "max_actions_per_minute": 60,
                "max_identical_consecutive": 3,
                "max_same_tool_per_minute": 15,
                "max_consecutive_errors": 10,
                "error_rate_threshold": 0.5,
                "cooldown_seconds": 60
            },
            "budget": {"preset": "standard"}
        }
    })
}

fn merge_config(mut base: Value, overlay: Value) -> Value {
    if let (Some(base_obj), Some(overlay_obj)) = (base.as_object_mut(), overlay.as_object()) {
        for (k, v) in overlay_obj {
            base_obj.insert(k.clone(), v.clone());
        }
    }
    base
}

fn value_is_truthy(v: &Value) -> bool {
    match v {
        Value::Null => false,
        Value::Bool(b) => *b,
        Value::Number(n) => n.as_f64().map(|f| f != 0.0).unwrap_or(false),
        Value::String(s) => !s.is_empty(),
        Value::Array(a) => !a.is_empty(),
        Value::Object(o) => !o.is_empty(),
    }
}

fn apply_config_redactions(mut merged: Value) -> Value {
    let pin_configured = merged
        .get("server")
        .and_then(|s| s.get("pin"))
        .map(value_is_truthy)
        .unwrap_or(false);
    let restart_token_configured = merged
        .get("server")
        .and_then(|s| s.get("restart_token"))
        .map(value_is_truthy)
        .unwrap_or(false);

    for key in &["api_keys", "webhooks"] {
        if merged.get(*key).is_some() {
            merged[*key] = serde_json::json!([]);
        }
    }
    for key in &["webhook_secret", "sns"] {
        if merged.get(*key).is_some() {
            merged[*key] = Value::Null;
        }
    }

    if let Some(server) = merged.get_mut("server").and_then(|v| v.as_object_mut()) {
        if server.contains_key("pin") {
            server.insert("pin".to_string(), Value::Null);
        }
        if server.contains_key("restart_token") {
            server.insert("restart_token".to_string(), Value::Null);
        }
        server.insert(
            "_pin_configured".to_string(),
            serde_json::json!(pin_configured),
        );
        server.insert(
            "_restart_token_configured".to_string(),
            serde_json::json!(restart_token_configured),
        );
    }

    merged
}

pub async fn api_settings_config(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let raw = load_config_json(&state.config.config_path);
    let merged = merge_config(default_config(), raw);
    let redacted = apply_config_redactions(merged);
    api_result(redacted)
}

/// The path `config.toml` lives at, next to whatever config file is in use.
///
/// `--config` may point at a `.json`; the TOML editor still edits the `.toml`
/// Admin scope AND a loopback client, for the raw config editor.
///
/// `api_settings_config` answers with `apply_config_redactions` applied --
/// `api_keys`, `webhooks`, `webhook_secret`, `sns`, `server.pin` and
/// `server.restart_token` are blanked. The TOML editor cannot do that: it
/// round-trips the file, and `..._toml_save` writes what it is given verbatim,
/// so serving redacted text would have the operator's first Save destroy every
/// secret in it. The redaction writes `null`/`[]`, which is indistinguishable
/// from "cleared on purpose", so a merge on save cannot recover them either --
/// that needs a distinct sentinel the editor UI cooperates with.
///
/// The gate is therefore the control: whoever reaches this route can already
/// open the same file in a text editor on that machine. A LAN client holding an
/// admin PIN cannot.
fn config_toml_gate(
    pin_auth_enabled: bool,
    auth_context: Option<&Extension<AuthContext>>,
    addr: Option<&Extension<ConnectInfo<SocketAddr>>>,
) -> Option<Response> {
    if let Some(err) = require_admin_scope(pin_auth_enabled, auth_context.map(|e| &e.0)) {
        return Some(err);
    }
    if !crate::routes::tools_fs::is_local(addr.map(|e| &e.0)) {
        return Some(api_error(
            "the raw config editor is only available from the local machine",
            StatusCode::FORBIDDEN,
            "forbidden",
        ));
    }
    None
}

/// beside it, which is what `config_migrate` treats as the primary.
fn toml_config_path(config_path: &Path) -> PathBuf {
    if config_path.extension().and_then(|e| e.to_str()) == Some("toml") {
        return config_path.to_path_buf();
    }
    config_path
        .parent()
        .unwrap_or_else(|| Path::new("."))
        .join("config.toml")
}

/// What the editor shows when neither config file exists yet.
const TOML_DEFAULT: &str = "compute_hash = false\nenable_fts   = true\nscan_roots   = []\n";

/// GET /api/settings/config-toml — raw `config.toml` text, as `text/plain`.
///
/// Until this existed the UI's request fell through to the catch-all
/// `/api/settings/{*key}`, which answered 200 with a *settings key lookup* for
/// the literal key "config-toml" -- a wrong answer that looks like a right one,
/// which is worse than the 404 a missing route would have given.
///
/// When only `config.json` is present its contents are converted, so that
/// saving from the editor does not shadow settings the user already has --
/// mirrors Python's `get_toml_config_payload`.
pub async fn api_settings_config_toml_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
) -> Response {
    if let Some(err) = config_toml_gate(
        state.config.pin_auth_enabled,
        auth_context.as_ref(),
        addr.as_ref(),
    ) {
        return err;
    }
    let toml_path = toml_config_path(&state.config.config_path);
    let text = std::fs::read_to_string(&toml_path).ok().or_else(|| {
        let json_path = toml_path
            .parent()
            .unwrap_or_else(|| Path::new("."))
            .join("config.json");
        let raw = std::fs::read_to_string(&json_path).ok()?;
        let value: Value = serde_json::from_str(&raw).ok()?;
        if !value.is_object() {
            return None;
        }
        let table = toml::Value::try_from(&value).ok()?;
        toml::to_string_pretty(&table).ok()
    });
    (
        StatusCode::OK,
        [(
            axum::http::header::CONTENT_TYPE,
            "text/plain; charset=utf-8",
        )],
        text.unwrap_or_else(|| TOML_DEFAULT.to_string()),
    )
        .into_response()
}

/// POST /api/settings/config-toml — validate and save raw TOML text.
pub async fn api_settings_config_toml_save(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    addr: Option<Extension<ConnectInfo<SocketAddr>>>,
    body: String,
) -> Response {
    if let Some(err) = config_toml_gate(
        state.config.pin_auth_enabled,
        auth_context.as_ref(),
        addr.as_ref(),
    ) {
        return err;
    }
    // Parse before writing: an unparseable file would leave the server unable
    // to read its own config on the next start.
    if let Err(error) = body.parse::<toml::Table>() {
        return api_error(
            &format!("TOML parse error: {error}"),
            StatusCode::BAD_REQUEST,
            "bad_request",
        );
    }
    let _guard = state.settings_lock.lock().await;
    let toml_path = toml_config_path(&state.config.config_path);
    if let Some(parent) = toml_path.parent() {
        if let Err(error) = std::fs::create_dir_all(parent) {
            return internal_error(error, "failed to create the config directory");
        }
    }
    if let Err(error) = std::fs::write(&toml_path, body.as_bytes()) {
        return internal_error(error, "failed to write config.toml");
    }
    api_result(json!({"status": "saved"}))
}

pub async fn api_settings_config_legacy_migration(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    api_result(json!(crate::config_migrate::legacy_migration_status(
        &state.config.config_path,
    )))
}

pub async fn api_settings_config_legacy_migration_run(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let _guard = state.settings_lock.lock().await;
    api_result(json!(crate::config_migrate::migrate_legacy_config(
        &state.config.config_path,
    )))
}

pub async fn api_settings_config_save(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<Value>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }

    let data = match body.as_object() {
        Some(m) if !m.is_empty() => m.clone(),
        _ => {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({"error": "No data", "code": "no_data"})),
            )
                .into_response()
        }
    };

    const ALLOWED_KEYS: &[&str] = &[
        "timezone",
        "server",
        "extract_a1111",
        "extract_comfyui",
        "lowercase_tags",
        "compute_hash",
        "enable_fts",
        "remote_fs",
        "fast_mode_source",
    ];
    const ALLOWED_SERVER_KEYS: &[&str] = &[
        "host",
        "port",
        "lan",
        "pin",
        "pin_boss_login_ui",
        "allow_remote_restart",
        "restart_token",
    ];

    for key in data.keys() {
        if !ALLOWED_KEYS.contains(&key.as_str()) {
            return (
                StatusCode::BAD_REQUEST,
                Json(json!({
                    "error": format!("Unsupported config keys: {key}"),
                    "code": "invalid_config_keys",
                })),
            )
                .into_response();
        }
    }

    if let Some(server) = data.get("server").and_then(|v| v.as_object()) {
        for key in server.keys() {
            if !ALLOWED_SERVER_KEYS.contains(&key.as_str()) {
                return (
                    StatusCode::BAD_REQUEST,
                    Json(json!({
                        "error": format!("Unsupported server keys: {key}"),
                        "code": "invalid_config_keys",
                    })),
                )
                    .into_response();
            }
        }
    }

    let mut config = load_config_json(&state.config.config_path);

    for (key, val) in &data {
        let existing_is_object = config.get(key).and_then(|v| v.as_object()).is_some();
        match (val, existing_is_object) {
            (Value::Object(incoming), true) => {
                let obj = config[key].as_object_mut().unwrap();
                for (k, v) in incoming {
                    // Never overwrite secrets with blank/null values
                    if (k == "pin" || k == "restart_token")
                        && (v.is_null() || v.as_str() == Some(""))
                    {
                        continue;
                    }
                    obj.insert(k.clone(), v.clone());
                }
            }
            _ => {
                config[key] = val.clone();
            }
        }
    }

    if let Err(e) = write_config_json(&state.config.config_path, &config) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": e.to_string()})),
        )
            .into_response();
    }

    Json(json!({"status": "saved"})).into_response()
}

#[cfg(test)]
mod tests {
    use super::{
        CliError, CliOutput, PushToBwRequest, PushToOpRequest, SettingValueRequest, VaultCli,
    };

    use axum::extract::{ConnectInfo, Extension};
    use std::collections::{HashMap, HashSet, VecDeque};
    use std::future::Future;
    use std::net::SocketAddr;
    use std::path::{Path, PathBuf};
    use std::pin::Pin;
    use std::sync::{Arc, Mutex};
    use std::time::Duration;

    use axum::{
        body::{to_bytes, Body},
        http::{Method, Request, StatusCode},
        middleware,
        routing::{any, delete, get, post},
        Json, Router,
    };
    use serde_json::{json, Value};
    use tower::ServiceExt;

    use crate::{
        auth::{middleware::auth_middleware, PinRateLimiter, QuickLock},
        groups_index::GroupsIndexCache,
        routes::settings,
        secret_store,
        state::{AppState, Config, SharedState},
    };

    struct TestRoot {
        path: PathBuf,
    }

    #[derive(Clone, Debug)]
    struct FakeRun {
        program: String,
        args: Vec<String>,
        stdin_data: Option<String>,
        output: Result<CliOutput, FakeCliError>,
    }

    #[derive(Clone, Debug)]
    enum FakeCliError {
        NotFound,
        Timeout,
        Io(String),
    }

    struct FakeCli {
        available: HashSet<String>,
        runs: Mutex<VecDeque<FakeRun>>,
    }

    impl FakeCli {
        fn new(available: &[&str], runs: Vec<FakeRun>) -> Self {
            Self {
                available: available.iter().map(|value| (*value).to_string()).collect(),
                runs: Mutex::new(VecDeque::from(runs)),
            }
        }

        fn output(program: &str, args: &[&str], status: i32, stdout: Value) -> FakeRun {
            FakeRun {
                program: program.to_string(),
                args: args.iter().map(|arg| (*arg).to_string()).collect(),
                stdin_data: None,
                output: Ok(CliOutput {
                    status,
                    stdout: stdout.to_string(),
                    stderr: String::new(),
                }),
            }
        }

        fn output_with_stdin(
            program: &str,
            args: &[&str],
            stdin_data: Option<&str>,
            status: i32,
            stdout: Value,
            stderr: &str,
        ) -> FakeRun {
            FakeRun {
                program: program.to_string(),
                args: args.iter().map(|arg| (*arg).to_string()).collect(),
                stdin_data: stdin_data.map(str::to_string),
                output: Ok(CliOutput {
                    status,
                    stdout: stdout.to_string(),
                    stderr: stderr.to_string(),
                }),
            }
        }

        fn assert_empty(&self) {
            assert!(self.runs.lock().unwrap().is_empty());
        }
    }

    impl VaultCli for FakeCli {
        fn is_available(&self, program: &str) -> bool {
            self.available.contains(program)
        }

        fn run<'a>(
            &'a self,
            program: &'a str,
            args: &'a [&'a str],
            stdin_data: Option<String>,
            _timeout: Duration,
        ) -> Pin<Box<dyn Future<Output = Result<CliOutput, CliError>> + Send + 'a>> {
            Box::pin(async move {
                let mut runs = self.runs.lock().unwrap();
                let run = runs.pop_front().expect("unexpected CLI call");
                assert_eq!(run.program, program);
                assert_eq!(
                    run.args,
                    args.iter()
                        .map(|arg| (*arg).to_string())
                        .collect::<Vec<_>>()
                );
                if run.stdin_data.as_deref() == Some("<any>") {
                    assert!(stdin_data.is_some());
                } else if let Some(expected) = run.stdin_data.as_deref() {
                    assert_eq!(stdin_data.as_deref(), Some(expected));
                } else if run.stdin_data.is_none() {
                    assert!(stdin_data.is_none());
                }
                match run.output {
                    Ok(output) => Ok(output),
                    Err(FakeCliError::NotFound) => Err(CliError::NotFound),
                    Err(FakeCliError::Timeout) => Err(CliError::Timeout),
                    Err(FakeCliError::Io(message)) => {
                        Err(CliError::Io(std::io::Error::other(message)))
                    }
                }
            })
        }
    }

    impl Drop for TestRoot {
        fn drop(&mut self) {
            let _ = std::fs::remove_dir_all(&self.path);
        }
    }

    fn test_root(name: &str) -> TestRoot {
        let path = std::env::temp_dir().join(format!("yu-settings-{name}-{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&path);
        std::fs::create_dir_all(path.join("config")).unwrap();
        std::fs::create_dir_all(path.join("data")).unwrap();
        TestRoot { path }
    }

    fn write_json(path: &Path, value: &Value) {
        std::fs::write(path, serde_json::to_string_pretty(value).unwrap()).unwrap();
    }

    async fn test_state(root: &TestRoot, config: Value, schema: Value) -> SharedState {
        write_json(&root.path.join("config.json"), &config);
        write_json(
            &root.path.join("config").join("settings_schema.json"),
            &schema,
        );
        let pool = sqlx::SqlitePool::connect("sqlite::memory:").await.unwrap();
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
                pin_auth_enabled: false,
                min_pin_length: 4,
                python_url: String::new(),
                config_path: root.path.join("config.json"),
                project_root: root.path.clone(),
                app_config: json!({}),
                cache_dir: root.path.join("cache"),
                server_mode: "full".to_string(),
                headless: false,
                safe_mode: false,
                standalone: false,
                infer_standalone: true,
                active_profile: None,
                python_executable: String::new(),
                mcp_native: false,
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
            groups_index_cache: GroupsIndexCache::new(root.path.join("cache")),
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

    fn sample_schema() -> Value {
        json!([
            {
                "key": "server.pin",
                "type": "str",
                "description": "PIN",
                "default": null,
                "secret": true,
                "category": "server",
                "op_eligible": true
            },
            {
                "key": "timezone",
                "type": "str",
                "description": "Timezone",
                "default": null,
                "secret": false,
                "category": "ui",
                "op_eligible": false
            },
            {
                "key": "feature.enabled",
                "type": "bool",
                "description": "Feature",
                "default": false,
                "secret": false,
                "category": "ui",
                "op_eligible": false
            }
        ])
    }

    async fn json_body(response: axum::response::Response) -> Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn schema_returns_committed_schema_json() {
        let root = test_root("schema");
        let schema = sample_schema();
        let response = settings::api_settings_schema(
            axum::extract::State(test_state(&root, json!({}), schema).await),
            None,
        )
        .await;
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["error"], Value::Null);
        assert_eq!(value["schema"][0]["key"], "server.pin");
    }

    #[tokio::test]
    async fn all_masks_secret_values_and_never_returns_plaintext() {
        let root = test_root("all");
        let response = settings::api_settings_all(
            axum::extract::State(
                test_state(
                    &root,
                    json!({"server": {"pin": "super-secret-pin"}}),
                    sample_schema(),
                )
                .await,
            ),
            None,
        )
        .await;
        let value = json_body(response).await;
        let text = serde_json::to_string(&value).unwrap();
        assert!(!text.contains("super-secret-pin"));
        assert_eq!(value["settings"][0]["value"], "s****n");
        assert_eq!(value["settings"][0]["source"], "config");
    }

    #[tokio::test]
    async fn single_unknown_key_returns_python_compatible_not_found() {
        let root = test_root("missing");
        let response = settings::api_settings_get(
            axum::extract::State(test_state(&root, json!({}), sample_schema()).await),
            None,
            axum::extract::Path("missing.key".to_string()),
        )
        .await;
        let value = json_body(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["error"], "Unknown setting key");
        assert_eq!(value["code"], "not_found");
    }

    #[tokio::test]
    async fn secrets_status_reports_backend_shape() {
        let root = test_root("status");
        let state = test_state(&root, json!({}), sample_schema()).await;
        std::fs::write(root.path.join("data").join("secret.key"), "test-key").unwrap();
        let response = settings::api_secrets_status(axum::extract::State(state), None).await;
        let value = json_body(response).await;
        assert_eq!(value["active_backend"], "file");
        assert_eq!(value["backends"]["file"]["available"], true);
        assert_eq!(value["backends"]["file"]["active"], true);
    }

    #[tokio::test]
    async fn put_updates_plain_setting_with_strict_type_validation() {
        let root = test_root("put-plain");
        let state = test_state(&root, json!({}), sample_schema()).await;
        let response = settings::api_settings_put(
            axum::extract::State(state),
            None,
            axum::extract::Path("feature.enabled".to_string()),
            Json(SettingValueRequest {
                value: Some(json!(true)),
                op_uri: None,
            }),
        )
        .await;
        let value = json_body(response).await;
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();

        assert_eq!(value["updated"], true);
        assert_eq!(config["feature"]["enabled"], true);
    }

    #[tokio::test]
    async fn put_rejects_wrong_schema_type() {
        let root = test_root("put-type");
        let state = test_state(&root, json!({}), sample_schema()).await;
        let response = settings::api_settings_put(
            axum::extract::State(state),
            None,
            axum::extract::Path("feature.enabled".to_string()),
            Json(SettingValueRequest {
                value: Some(json!("true")),
                op_uri: None,
            }),
        )
        .await;
        let status = response.status();
        let value = json_body(response).await;

        assert_eq!(status, StatusCode::BAD_REQUEST);
        assert_eq!(value["error"], "value must be a boolean");
    }

    #[tokio::test]
    async fn put_encrypts_secret_before_persisting() {
        let root = test_root("put-secret");
        let state = test_state(&root, json!({}), sample_schema()).await;
        let response = settings::api_settings_put(
            axum::extract::State(state),
            None,
            axum::extract::Path("server.pin".to_string()),
            Json(SettingValueRequest {
                value: Some(json!("super-secret-pin")),
                op_uri: None,
            }),
        )
        .await;
        let value = json_body(response).await;
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();
        let stored = config["server"]["pin"].as_str().unwrap();

        assert_eq!(value["updated"], true);
        assert!(stored.starts_with("enc:v2:"));
        assert_ne!(stored, "super-secret-pin");
        assert_eq!(
            secret_store::decrypt(stored, &root.path),
            "super-secret-pin"
        );
    }

    #[tokio::test]
    async fn put_op_uri_updates_mapping_without_plaintext_secret() {
        let root = test_root("put-op");
        let state = test_state(&root, json!({}), sample_schema()).await;
        let response = settings::api_settings_put(
            axum::extract::State(state),
            None,
            axum::extract::Path("server.pin".to_string()),
            Json(SettingValueRequest {
                value: Some(json!("")),
                op_uri: Some("op://Personal/Yu/pin".to_string()),
            }),
        )
        .await;
        let value = json_body(response).await;
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();

        assert_eq!(value["updated"], true);
        assert_eq!(config["op_secrets"]["server.pin"], "op://Personal/Yu/pin");
        assert!(config.pointer("/server/pin").is_none());
    }

    #[tokio::test]
    async fn secrets_migrate_encrypts_plaintext_secret_fields() {
        let root = test_root("migrate");
        let state = test_state(
            &root,
            json!({"server": {"pin": "plain-secret"}}),
            sample_schema(),
        )
        .await;
        let response = settings::api_secrets_migrate(axum::extract::State(state), None).await;
        let value = json_body(response).await;
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();
        let stored = config["server"]["pin"].as_str().unwrap();

        assert_eq!(value["migrated"], 1);
        assert!(stored.starts_with("enc:v2:"));
        assert_eq!(secret_store::decrypt(stored, &root.path), "plain-secret");
    }

    #[tokio::test]
    async fn secrets_rotate_reencrypts_with_new_key_id() {
        let root = test_root("rotate");
        let old = secret_store::encrypt("rotate-secret", &root.path);
        let state = test_state(&root, json!({"server": {"pin": old}}), sample_schema()).await;
        let response = settings::api_secrets_rotate(axum::extract::State(state), None).await;
        let value = json_body(response).await;
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();
        let stored = config["server"]["pin"].as_str().unwrap();
        let new_key_id = value["new_key_id"].as_str().unwrap();

        assert_eq!(value["rotated"], 1);
        assert!(stored.starts_with(&format!("enc:v2:{new_key_id}:")));
        assert_eq!(secret_store::decrypt(stored, &root.path), "rotate-secret");
    }

    #[tokio::test]
    async fn bw_status_reports_unavailable_without_cli_call() {
        let cli = FakeCli::new(&[], vec![]);
        let value = super::bw_status_with_cli(&cli).await;
        assert_eq!(value["available"], false);
        assert_eq!(value["status"], "not_installed");
        cli.assert_empty();
    }

    #[tokio::test]
    async fn bw_folders_returns_python_shape_from_cli_json() {
        let cli = FakeCli::new(
            &["bw"],
            vec![FakeCli::output(
                "bw",
                &["list", "folders", "--nointeraction"],
                0,
                json!([{"id": "f1", "name": "Ops"}]),
            )],
        );
        let folders = super::bw_folders_with_cli(&cli).await.unwrap();
        assert_eq!(folders[0]["id"], "f1");
        assert_eq!(folders[0]["name"], "Ops");
        cli.assert_empty();
    }

    #[tokio::test]
    async fn push_to_bw_writes_mapping_without_returning_secret_values() {
        let root = test_root("push-bw");
        let state = test_state(
            &root,
            json!({"server": {"pin": "plain-secret"}}),
            sample_schema(),
        )
        .await;
        let cli = FakeCli::new(
            &["bw"],
            vec![
                FakeCli::output(
                    "bw",
                    &[
                        "list",
                        "items",
                        "--search",
                        "YU AI Manager",
                        "--nointeraction",
                    ],
                    0,
                    json!([]),
                ),
                FakeCli::output_with_stdin(
                    "bw",
                    &["create", "item", "--nointeraction"],
                    Some("<any>"),
                    0,
                    json!({"id": "item123"}),
                    "",
                ),
            ],
        );
        let value = super::push_to_bw_with_cli(
            &state,
            &cli,
            PushToBwRequest {
                folder_id: None,
                item_name: Some("YU AI Manager".to_string()),
            },
        )
        .await
        .unwrap();
        let text = serde_json::to_string(&value).unwrap();
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();

        assert_eq!(value["pushed_keys"][0], "server.pin");
        assert_eq!(config["bw_secrets"]["server.pin"]["item"], "item123");
        assert!(!text.contains("plain-secret"));
        cli.assert_empty();
    }

    #[tokio::test]
    async fn delete_bw_mapping_removes_empty_map() {
        let root = test_root("delete-bw");
        let state = test_state(
            &root,
            json!({"bw_secrets": {"server.pin": {"item": "i", "field": "server_pin"}}}),
            sample_schema(),
        )
        .await;
        let response = super::api_settings_bw_mapping_delete(
            axum::extract::State(state),
            None,
            axum::extract::Path("server.pin".to_string()),
        )
        .await;
        let value = json_body(response).await;
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();

        assert_eq!(value["unlinked"], true);
        assert!(config.get("bw_secrets").is_none());
    }

    #[tokio::test]
    async fn op_status_falls_back_to_account_list_for_desktop_auth() {
        let cli = FakeCli::new(
            &["op"],
            vec![
                FakeCli::output("op", &["whoami", "--format=json"], 1, json!({})),
                FakeCli::output(
                    "op",
                    &["account", "list", "--format=json"],
                    0,
                    json!([{"email": "user@example.test"}]),
                ),
            ],
        );
        let value = super::op_status_with_cli(&cli).await;
        assert_eq!(value["available"], true);
        assert_eq!(value["signed_in"], true);
        assert_eq!(value["account"], "user@example.test");
        assert_eq!(value["auth_method"], "biometric");
        cli.assert_empty();
    }

    #[tokio::test]
    async fn op_vaults_returns_python_shape_from_cli_json() {
        let cli = FakeCli::new(
            &["op"],
            vec![FakeCli::output(
                "op",
                &["vault", "list", "--format", "json"],
                0,
                json!([{"id": "v1", "name": "Private"}]),
            )],
        );
        let vaults = super::op_vaults_with_cli(&cli).await.unwrap();
        assert_eq!(vaults[0]["id"], "v1");
        assert_eq!(vaults[0]["name"], "Private");
        cli.assert_empty();
    }

    #[tokio::test]
    async fn push_to_op_merges_mapping_without_returning_secret_values() {
        let root = test_root("push-op");
        let state = test_state(
            &root,
            json!({"server": {"pin": "plain-secret"}, "op_secrets": {"old.key": "op://Old"}}),
            sample_schema(),
        )
        .await;
        let cli = FakeCli::new(
            &["op"],
            vec![
                FakeCli::output(
                    "op",
                    &[
                        "item",
                        "get",
                        "YU AI Manager",
                        "--vault",
                        "Private",
                        "--format",
                        "json",
                    ],
                    1,
                    json!({}),
                ),
                FakeCli::output_with_stdin(
                    "op",
                    &["item", "create", "--format", "json"],
                    Some("<any>"),
                    0,
                    json!({"id": "created"}),
                    "",
                ),
            ],
        );
        let value = super::push_to_op_with_cli(
            &state,
            &cli,
            PushToOpRequest {
                vault: Some("Private".to_string()),
                item_title: Some("YU AI Manager".to_string()),
                remove_local: Some(false),
            },
        )
        .await
        .unwrap();
        let text = serde_json::to_string(&value).unwrap();
        let config: Value =
            serde_json::from_str(&std::fs::read_to_string(root.path.join("config.json")).unwrap())
                .unwrap();

        assert_eq!(config["op_secrets"]["old.key"], "op://Old");
        assert_eq!(
            config["op_secrets"]["server.pin"],
            "op://Private/YU AI Manager/server_pin"
        );
        assert_eq!(value["remove_local"], false);
        assert!(!text.contains("plain-secret"));
        cli.assert_empty();
    }

    #[tokio::test]
    async fn delete_op_mapping_returns_not_found_for_missing_key() {
        let root = test_root("delete-op-missing");
        let state = test_state(&root, json!({"op_secrets": {}}), sample_schema()).await;
        let response = super::api_settings_op_mapping_delete(
            axum::extract::State(state),
            None,
            axum::extract::Path("server.pin".to_string()),
        )
        .await;
        let status = response.status();
        let value = json_body(response).await;

        assert_eq!(status, StatusCode::NOT_FOUND);
        assert_eq!(value["code"], "not_found");
    }

    #[tokio::test]
    async fn command_runner_kills_process_on_timeout() {
        let result = super::run_command_with_timeout(
            "sh",
            &["-c", "sleep 2"],
            None,
            Duration::from_millis(50),
        )
        .await;
        assert!(matches!(result, Err(CliError::Timeout)));
    }

    /// The whole point of the new route: `/api/settings/config-toml` must not
    /// be answered by the `/api/settings/{*key}` catch-all. Before it existed
    /// the UI got a 200 describing a settings key literally named
    /// "config-toml" -- a wrong answer shaped like a right one, which is worse
    /// than the 404 a plain missing route would have given.
    ///
    /// Asserts on the *body*, not just the status: both routes answer 200, so a
    /// status-only check would pass either way and fix nothing.
    #[tokio::test]
    async fn config_toml_get_is_not_swallowed_by_the_settings_catch_all() {
        let root = test_root("config_toml_not_swallowed");
        std::fs::write(
            root.path.join("config.toml"),
            "compute_hash = true\nenable_fts = false\n",
        )
        .unwrap();
        let state = test_state(&root, json!({}), json!({"settings": []})).await;

        let response = app(state)
            .oneshot(
                Request::builder()
                    .method(Method::GET)
                    .uri("/api/settings/config-toml")
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let text = String::from_utf8(body.to_vec()).unwrap();
        assert!(
            text.contains("compute_hash = true"),
            "expected the raw TOML file, got: {text}"
        );
        // The catch-all answers JSON; the raw file never starts with `{`.
        assert!(!text.trim_start().starts_with('{'), "got JSON: {text}");
    }

    /// An unparseable body must be refused before it reaches disk: a broken
    /// config.toml would leave the server unable to read its own config on the
    /// next start.
    #[tokio::test]
    async fn config_toml_save_refuses_unparseable_toml_without_writing() {
        let root = test_root("config_toml_refuses_bad");
        let path = root.path.join("config.toml");
        std::fs::write(&path, "compute_hash = true\n").unwrap();
        let state = test_state(&root, json!({}), json!({"settings": []})).await;

        let response = app(state)
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/settings/config-toml")
                    .body(Body::from("this is [not valid toml"))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            std::fs::read_to_string(&path).unwrap(),
            "compute_hash = true\n",
            "the existing config must survive a rejected save"
        );
    }

    /// Valid TOML round-trips to disk verbatim -- the editor shows the file, so
    /// a reformat on save would surprise whoever typed it.
    #[tokio::test]
    async fn config_toml_save_writes_the_body_verbatim() {
        let root = test_root("config_toml_saves");
        let state = test_state(&root, json!({}), json!({"settings": []})).await;
        let body = "enable_fts = true\nscan_roots = []\n";

        let response = app(state)
            .oneshot(
                Request::builder()
                    .method(Method::POST)
                    .uri("/api/settings/config-toml")
                    .body(Body::from(body))
                    .unwrap(),
            )
            .await
            .unwrap();
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            std::fs::read_to_string(root.path.join("config.toml")).unwrap(),
            body
        );
    }

    fn app(state: SharedState) -> Router {
        Router::new()
            .route("/api/settings/schema", get(settings::api_settings_schema))
            .route("/api/settings/all", get(settings::api_settings_all))
            .route(
                "/api/settings/secrets/status",
                get(settings::api_secrets_status),
            )
            .route(
                "/api/settings/op-mapping/{*key}",
                delete(settings::api_settings_op_mapping_delete),
            )
            .route(
                "/api/settings/bw-mapping/{*key}",
                delete(settings::api_settings_bw_mapping_delete),
            )
            .route(
                "/api/settings/secrets/migrate",
                post(settings::api_secrets_migrate),
            )
            .route(
                "/api/settings/secrets/keyring",
                get(settings::api_secrets_keyring),
            )
            .route(
                // Same order as main.rs: before the catch-all. A test router
                // that registered these the other way round would pass while
                // production still answered from the catch-all.
                "/api/settings/config-toml",
                get(settings::api_settings_config_toml_get)
                    .post(settings::api_settings_config_toml_save),
            )
            .route(
                "/api/settings/{*key}",
                get(settings::api_settings_get).put(settings::api_settings_put),
            )
            .fallback(|| async { StatusCode::NOT_FOUND })
            .layer(middleware::from_fn_with_state(
                Arc::clone(&state),
                auth_middleware,
            ))
            // Production gets this from `into_make_service_with_connect_info`;
            // a `oneshot` router has no peer, and `config_toml_gate` reads it.
            // The gate's own behaviour (LAN client, no peer) is covered in
            // `config_toml_gate_tests`, so this cannot mask a broken gate.
            .layer(Extension(ConnectInfo(SocketAddr::from((
                [127, 0, 0, 1],
                1234,
            )))))
            .with_state(state)
    }

    async fn request_json(app: Router, method: Method, path: &str) -> (StatusCode, Value) {
        let response = app
            .oneshot(
                Request::builder()
                    .method(method)
                    .uri(path)
                    .body(Body::empty())
                    .unwrap(),
            )
            .await
            .unwrap();
        let status = response.status();
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        let value = serde_json::from_slice(&body).unwrap_or(Value::Null);
        (status, value)
    }

    #[tokio::test]
    async fn catch_all_does_not_shadow_static_settings_routes() {
        let root = test_root("shadow");
        let state = test_state(&root, json!({}), sample_schema()).await;
        let router = app(state);

        let (_, schema) = request_json(router.clone(), Method::GET, "/api/settings/schema").await;
        let (_, all) = request_json(router.clone(), Method::GET, "/api/settings/all").await;
        let (export_status, export) =
            request_json(router.clone(), Method::POST, "/api/settings/secrets/export").await;
        let (migrate_status, migrate) = request_json(
            router.clone(),
            Method::POST,
            "/api/settings/secrets/migrate",
        )
        .await;
        let (op_delete_status, op_delete) = request_json(
            router,
            Method::DELETE,
            "/api/settings/op-mapping/server.pin",
        )
        .await;

        assert_eq!(schema["schema"][0]["key"], "server.pin");
        assert!(all["settings"].is_array());
        // POST はこの試験用 router に登録されておらず、catch-all
        // `/api/settings/{*key}` が GET/PUT だけを持つ。従って path は一致し
        // method が一致せぬ 405 となる（Quart も同じ）。本試験の主旨は
        // 静的 route が catch-all に飲まれぬことであり、下の schema/all がそれを見る。
        assert_eq!(export_status, StatusCode::METHOD_NOT_ALLOWED);
        assert_eq!(migrate_status, StatusCode::OK);
        assert_eq!(migrate["migrated"], 0);
        assert_eq!(op_delete_status, StatusCode::NOT_FOUND);
        assert_eq!(op_delete["code"], "not_found");
    }
}

#[cfg(test)]
mod config_toml_gate_tests {
    use super::config_toml_gate;
    use axum::extract::{ConnectInfo, Extension};
    use std::net::{IpAddr, Ipv4Addr, SocketAddr};

    fn ci(ip: IpAddr) -> Extension<ConnectInfo<SocketAddr>> {
        Extension(ConnectInfo(SocketAddr::new(ip, 1234)))
    }

    /// This route serves the config file with NO redaction -- unlike
    /// `api_settings_config`, which blanks `api_keys`, `webhooks`,
    /// `webhook_secret`, `sns`, `server.pin` and `server.restart_token`. The
    /// loopback half stands in for that, so it is checked with the admin half
    /// DISABLED: with PIN auth off, this gate is the only thing between a LAN
    /// client and every secret in the file.
    #[test]
    fn a_lan_client_is_refused_even_with_auth_disabled() {
        let refused = config_toml_gate(
            false,
            None,
            Some(&ci(IpAddr::V4(Ipv4Addr::new(192, 168, 1, 50)))),
        );
        assert!(
            refused.is_some(),
            "a LAN client must not read the raw config"
        );
    }

    /// An unknown peer must not be treated as local -- the case a middleware
    /// change could silently create.
    #[test]
    fn a_request_with_no_peer_address_is_refused() {
        assert!(config_toml_gate(false, None, None).is_some());
    }

    #[test]
    fn a_loopback_client_passes_when_auth_is_disabled() {
        let allowed = config_toml_gate(false, None, Some(&ci(IpAddr::V4(Ipv4Addr::LOCALHOST))));
        assert!(allowed.is_none(), "loopback with auth off must be allowed");
    }

    /// Loopback alone must not grant admin: with PIN auth on and no
    /// credentials, the admin half still refuses.
    #[test]
    fn a_loopback_client_still_needs_admin_scope() {
        let refused = config_toml_gate(true, None, Some(&ci(IpAddr::V4(Ipv4Addr::LOCALHOST))));
        assert!(refused.is_some(), "loopback alone must not grant admin");
    }
}
