use axum::{
    body::Bytes,
    extract::{Extension, Path, Query, State},
    http::{header, HeaderValue, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::json;
use sqlx::Row;
use std::{
    io::{Cursor, Write},
    path::{Component, Path as FsPath, PathBuf},
    time::Duration,
};
use zip::{write::SimpleFileOptions, CompressionMethod, ZipWriter};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    state::SharedState,
};

/// POST /api/ocr/translate/{file_id}
pub async fn ocr_translate(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    body: Bytes,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|entry| &entry.0),
    ) {
        return resp;
    }

    let body = match serde_json::from_slice::<serde_json::Value>(&body) {
        Ok(body) => body,
        Err(_) => serde_json::Value::Null,
    };
    let params = TranslateParams {
        target_lang: match body.get("target_lang") {
            Some(serde_json::Value::String(value)) => value.to_owned(),
            Some(_) => String::new(),
            None => default_target_lang(),
        },
        task: match body.get("task").and_then(serde_json::Value::as_str) {
            Some(value) => value.to_owned(),
            None => String::new(),
        },
        server_id: body
            .get("server_id")
            .and_then(serde_json::Value::as_str)
            .map(str::to_owned),
    };
    if params.target_lang.is_empty() {
        return translate_error(StatusCode::BAD_REQUEST, "target_lang is required");
    }

    let row = if params.task.is_empty() {
        sqlx::query("SELECT id, task, regions_json, full_text, language FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC LIMIT 1")
            .bind(file_id)
            .fetch_optional(&state.db_read)
            .await
    } else {
        sqlx::query("SELECT id, task, regions_json, full_text, language FROM file_ocr_results WHERE file_id=? AND task=? ORDER BY created_at DESC, id DESC LIMIT 1")
            .bind(file_id)
            .bind(&params.task)
            .fetch_optional(&state.db_read)
            .await
    };
    match row {
        Ok(Some(row)) => {
            let ocr_result_id = row.try_get::<i64, _>("id").unwrap_or_default();
            let task = row.try_get::<String, _>("task").unwrap_or_default();
            let full_text = row
                .try_get::<Option<String>, _>("full_text")
                .ok()
                .flatten()
                .unwrap_or_default();
            let language = row
                .try_get::<Option<String>, _>("language")
                .ok()
                .flatten()
                .unwrap_or_default();
            let regions = row
                .try_get::<Option<String>, _>("regions_json")
                .ok()
                .flatten()
                .and_then(|text| serde_json::from_str(&text).ok())
                .unwrap_or_default();
            let result = crate::ocr::translate::translate_ocr_result(
                &full_text,
                &language,
                regions,
                &task,
                &params.target_lang,
                params.server_id.as_deref(),
                &state.config.app_config,
                &state.config.project_root,
                state.infer_client.as_ref(),
            )
            .await;
            let result = match result {
                Ok(result) => result,
                Err(error) => {
                    tracing::error!(%error, "Translation failed for file_id={file_id}");
                    return translate_error(
                        StatusCode::INTERNAL_SERVER_ERROR,
                        &format!("Translation failed: {error}"),
                    );
                }
            };
            if ocr_result_id != 0 {
                if let Err(error) =
                    crate::ocr::translate::save_translation(&state.db, ocr_result_id, &result).await
                {
                    tracing::error!(%error, "ocr_translate save failed");
                    return translate_error(
                        StatusCode::INTERNAL_SERVER_ERROR,
                        "ocr_translate_save_failed",
                    );
                }
            }
            Json(json!({
                "ok": true,
                "error": null,
                "data": null,
                "file_id": file_id,
                "target_lang": params.target_lang,
                "translated_text": result.translated_text,
                "engine": result.engine,
                "region_translations": result.region_translations,
            }))
            .into_response()
        }
        Ok(None) => translate_error(
            StatusCode::NOT_FOUND,
            "OCR result not found. Run OCR first.",
        ),
        Err(error) => {
            tracing::error!(%error, "ocr_translate result query failed");
            translate_error(
                StatusCode::INTERNAL_SERVER_ERROR,
                "ocr_translate_query_failed",
            )
        }
    }
}

struct TranslateParams {
    target_lang: String,
    task: String,
    server_id: Option<String>,
}

fn default_target_lang() -> String {
    "en".to_owned()
}

fn translate_error(status: StatusCode, error: &str) -> Response {
    (status, Json(json!({"ok": false, "error": error}))).into_response()
}

/// GET /api/ocr/overlay/{file_id}
pub async fn ocr_overlay(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Query(params): Query<OverlayParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|entry| &entry.0),
    ) {
        return resp;
    }
    let Some(mode) = crate::ocr::overlay::parse_mode(params.mode.as_deref()) else {
        return overlay_error(StatusCode::BAD_REQUEST, "invalid_overlay_mode");
    };
    let Some(format) = crate::ocr::overlay::parse_format(params.format.as_deref()) else {
        return overlay_error(StatusCode::BAD_REQUEST, "invalid_overlay_format");
    };
    let font = match crate::ocr::overlay::load_font(&state.config.cache_dir) {
        Ok(font) => font,
        Err(crate::ocr::overlay::Error::FontMissing) => {
            return overlay_error(StatusCode::SERVICE_UNAVAILABLE, "overlay_font_missing")
        }
        Err(crate::ocr::overlay::Error::FontInvalid) => {
            tracing::error!("OCR overlay font hash or parse verification failed");
            return overlay_error(StatusCode::SERVICE_UNAVAILABLE, "overlay_font_invalid");
        }
        Err(_) => {
            return overlay_error(StatusCode::SERVICE_UNAVAILABLE, "overlay_font_unavailable")
        }
    };
    let row = match sqlx::query(&format!(
        "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC LIMIT 1"
    ))
    .bind(file_id)
    .fetch_optional(&state.db_read)
    .await
    {
        Ok(Some(row)) => row,
        Ok(None) => return overlay_error(StatusCode::NOT_FOUND, "ocr_result_not_found"),
        Err(error) => {
            tracing::error!(%error, "ocr_overlay result query failed");
            return overlay_error(StatusCode::INTERNAL_SERVER_ERROR, "ocr_overlay_query_failed");
        }
    };
    let regions = row
        .try_get::<Option<String>, _>("regions_json")
        .ok()
        .flatten()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_default();
    let full_text = row
        .try_get::<Option<String>, _>("full_text")
        .ok()
        .flatten()
        .unwrap_or_default();
    let (region_translations, _) =
        match export_translations(&state, file_id, params.target_lang.as_deref().unwrap_or(""))
            .await
        {
            Ok(translations) => translations,
            Err(error) => {
                tracing::error!(%error, "ocr_overlay translations query failed");
                return overlay_error(
                    StatusCode::INTERNAL_SERVER_ERROR,
                    "ocr_overlay_query_failed",
                );
            }
        };
    let translations = region_translations
        .into_iter()
        .filter_map(|(id, text)| Some((id.parse().ok()?, text.as_str()?.to_owned())))
        .collect();
    let image_path = match crate::ocr::media::file_path(&state, file_id).await {
        Ok(path) => path,
        Err(_) => return overlay_error(StatusCode::NOT_FOUND, "overlay_source_missing"),
    };
    match crate::ocr::overlay::render(
        &image_path,
        regions,
        &full_text,
        &translations,
        mode,
        format,
        &font,
    ) {
        Ok(bytes) => {
            let content_type = match format {
                crate::ocr::overlay::Format::Png => "image/png",
                crate::ocr::overlay::Format::Jpeg => "image/jpeg",
            };
            (
                [(header::CONTENT_TYPE, HeaderValue::from_static(content_type))],
                bytes,
            )
                .into_response()
        }
        Err(crate::ocr::overlay::Error::TooLarge) => {
            overlay_error(StatusCode::BAD_REQUEST, "overlay_too_large")
        }
        Err(error) => {
            tracing::error!(?error, "OCR overlay render failed");
            overlay_error(StatusCode::INTERNAL_SERVER_ERROR, "overlay_render_failed")
        }
    }
}

#[derive(Deserialize, Default)]
pub struct OverlayParams {
    pub mode: Option<String>,
    pub format: Option<String>,
    pub target_lang: Option<String>,
}

fn overlay_error(status: StatusCode, error: &str) -> Response {
    (status, Json(json!({"ok": false, "error": error}))).into_response()
}

/// GET /api/ocr/bbox/{params}
pub async fn ocr_bbox() -> impl IntoResponse {
    Json(json!({"ok": false, "error": "ocr-bbox not available"}))
}

/// Mirror of `core/infra_core/api_errors.py::api_success`: the payload plus the
/// `ok`/`error`/`data` keys every Python response carries. Several handlers in
/// this file built the payload bare, which is a body difference wherever the
/// parity comparison is live -- v4.732.16 measured three of them.
fn ocr_ok(payload: serde_json::Value) -> Response {
    let mut body = match payload {
        serde_json::Value::Object(map) => map,
        other @ (serde_json::Value::Null
        | serde_json::Value::Bool(_)
        | serde_json::Value::Number(_)
        | serde_json::Value::String(_)
        | serde_json::Value::Array(_)) => {
            let mut map = serde_json::Map::new();
            map.insert("data".to_string(), other);
            map
        }
    };
    body.insert("ok".to_string(), serde_json::Value::Bool(true));
    body.insert("error".to_string(), serde_json::Value::Null);
    body.entry("data".to_string())
        .or_insert(serde_json::Value::Null);
    Json(serde_json::Value::Object(body)).into_response()
}

/// GET /api/ocr/engines
pub async fn ocr_engines(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }
    // ponytail: ai_servers is not wired here yet; Phase 2 can read config.
    //
    // This is a fabricated answer, not a stub with no consequence: Python builds
    // the list from the real server registry and the per-model OCR scores
    // (core/ocr_api/single_ops.py -> core.ocr_core.router, which the extension
    // loader aliases onto extensions/builtin_ocr/core_impl/). So Rust reports
    // "no OCR engines" whatever the configuration says. Tracked as
    // todo(rust-gap, v4.732.18); the envelope below is fixed regardless so the
    // remaining difference is the content alone.
    ocr_ok(json!({"engines": [], "manga_ocr_available": false}))
}

#[derive(Deserialize, Default)]
pub struct ExportParams {
    pub format: Option<String>,
    pub task: Option<String>,
    pub include_translation: Option<String>,
    pub target_lang: Option<String>,
}

#[derive(Deserialize, Default)]
pub struct BatchExportParams {
    #[serde(default)]
    pub file_ids: Vec<i64>,
    #[serde(default)]
    pub format: String,
    #[serde(default)]
    pub output_dir: String,
    #[serde(default = "default_overlay_mode")]
    pub overlay_mode: String,
    #[serde(default)]
    pub target_lang: String,
    #[serde(default)]
    pub include_translation: bool,
}

fn default_overlay_mode() -> String {
    "translated".to_owned()
}

#[derive(Clone, Copy)]
enum ExportFormat {
    Txt,
    Md,
    Json,
}

impl ExportFormat {
    const fn extension(self) -> &'static str {
        match self {
            Self::Txt => "txt",
            Self::Md => "md",
            Self::Json => "json",
        }
    }
}

/// GET /api/ocr/export/{file_id}
pub async fn ocr_export(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    Query(params): Query<ExportParams>,
) -> Response {
    let format = match params.format.as_deref().unwrap_or("md") {
        "txt" => ExportFormat::Txt,
        "md" => ExportFormat::Md,
        "json" => ExportFormat::Json,
        "pdf" => return export_error(
            "PDF OCR export is not available in the Rust server yet; run the Python server for this feature",
            StatusCode::NOT_IMPLEMENTED,
        ),
        format => return export_error(
            &format!("Invalid format: {format}. Supported: txt, md, json, pdf"),
            StatusCode::BAD_REQUEST,
        ),
    };

    let task = params.task.as_deref().unwrap_or("");
    let row = if task.is_empty() {
        sqlx::query(&format!(
            "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC LIMIT 1"
        ))
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
    } else {
        sqlx::query(&format!(
            "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? AND task=? ORDER BY created_at DESC, id DESC LIMIT 1"
        ))
        .bind(file_id)
        .bind(task)
        .fetch_optional(&state.db_read)
        .await
    };
    let row = match row {
        Ok(Some(row)) => row,
        Ok(None) => return export_error("OCR result not found", StatusCode::NOT_FOUND),
        Err(error) => {
            tracing::error!(%error, "ocr_export query failed");
            return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let result = row_to_export_result(&row);
    let include_translation = params
        .include_translation
        .as_deref()
        .is_some_and(|value| !value.is_empty());
    let (translations, translated_full_text) = if include_translation {
        match export_translations(&state, file_id, params.target_lang.as_deref().unwrap_or(""))
            .await
        {
            Ok(translations) => translations,
            Err(error) => {
                tracing::error!(%error, "ocr_export translations query failed");
                return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
            }
        }
    } else {
        (serde_json::Map::new(), String::new())
    };
    let target_lang = params.target_lang.as_deref().unwrap_or("");
    let (content, filename, content_type) = export_content(
        &result,
        format,
        file_id,
        &translations,
        &translated_full_text,
        target_lang,
    );
    let mut response = content.into_response();
    response
        .headers_mut()
        .insert(header::CONTENT_TYPE, HeaderValue::from_static(content_type));
    let disposition = match HeaderValue::from_str(&content_disposition(&filename)) {
        Ok(disposition) => disposition,
        Err(_) => return export_error("Invalid export filename", StatusCode::BAD_REQUEST),
    };
    response
        .headers_mut()
        .insert(header::CONTENT_DISPOSITION, disposition);
    response
}

/// POST /api/ocr/export/batch
pub async fn ocr_export_batch(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Json(mut params): Json<BatchExportParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|entry| &entry.0),
    ) {
        return resp;
    }

    let config = crate::ext_config::read_config_for_profile(
        &state.config.config_path,
        &state.config.project_root,
        state.config.active_profile.as_deref(),
    );
    if params.format.is_empty() {
        params.format =
            crate::ext_config::extension_value(&config, "builtin-ocr", "batch_export_format")
                .and_then(|value| value.as_str().map(str::to_owned))
                .unwrap_or_else(|| "md".to_owned());
    }
    if params.output_dir.is_empty() {
        params.output_dir =
            crate::ext_config::extension_value(&config, "builtin-ocr", "batch_output_dir")
                .and_then(|value| value.as_str().map(str::to_owned))
                .unwrap_or_default();
    }
    let format = match params.format.as_str() {
        "txt" => ExportFormat::Txt,
        "md" => ExportFormat::Md,
        "json" => ExportFormat::Json,
        "overlay" => {
            if params.file_ids.is_empty() {
                return export_error("file_ids is required", StatusCode::BAD_REQUEST);
            }
            return ocr_export_batch_overlay(&state, params).await;
        }
        "pdf" => {
            if params.file_ids.is_empty() {
                return export_error("file_ids is required", StatusCode::BAD_REQUEST);
            }
            return ocr_export_batch_unsupported(&state, params).await;
        }
        format => {
            return export_error(
                &format!("Invalid format: {format}. Supported: txt, md, json, pdf, overlay"),
                StatusCode::BAD_REQUEST,
            )
        }
    };
    if params.file_ids.is_empty() {
        return export_error("file_ids is required", StatusCode::BAD_REQUEST);
    }
    ocr_export_batch_zip(&state, params, format).await
}

async fn ocr_export_batch_overlay(state: &SharedState, params: BatchExportParams) -> Response {
    let results = match batch_export_results(state, &params.file_ids).await {
        Ok(results) if results.is_empty() => {
            return export_error(
                "No OCR results found for given file_ids",
                StatusCode::NOT_FOUND,
            );
        }
        Ok(results) => results,
        Err(error) => {
            tracing::error!(%error, "ocr_export_batch overlay query failed");
            return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    if !params.output_dir.is_empty() {
        return export_not_ported("Saving OCR batch exports to a server-side directory");
    }
    let Some(mode) = crate::ocr::overlay::parse_mode(Some(&params.overlay_mode)) else {
        return overlay_error(StatusCode::BAD_REQUEST, "invalid_overlay_mode");
    };
    let Some(format) = crate::ocr::overlay::parse_format(None) else {
        return overlay_error(StatusCode::INTERNAL_SERVER_ERROR, "overlay_render_failed");
    };
    let font = match crate::ocr::overlay::load_font(&state.config.cache_dir) {
        Ok(font) => font,
        Err(crate::ocr::overlay::Error::FontMissing) => {
            return overlay_error(StatusCode::SERVICE_UNAVAILABLE, "overlay_font_missing");
        }
        Err(crate::ocr::overlay::Error::FontInvalid) => {
            tracing::error!("OCR overlay font hash or parse verification failed");
            return overlay_error(StatusCode::SERVICE_UNAVAILABLE, "overlay_font_invalid");
        }
        Err(_) => {
            return overlay_error(StatusCode::SERVICE_UNAVAILABLE, "overlay_font_unavailable")
        }
    };
    ocr_export_batch_overlay_zip(state, results, &params, mode, format, &font).await
}

async fn ocr_export_batch_overlay_zip(
    state: &SharedState,
    results: Vec<(i64, serde_json::Value)>,
    params: &BatchExportParams,
    mode: crate::ocr::overlay::Mode,
    format: crate::ocr::overlay::Format,
    font: &ab_glyph::FontArc,
) -> Response {
    let mut exports = Vec::with_capacity(results.len());
    for (file_id, result) in results {
        let image_path = match crate::ocr::media::file_path(state, file_id).await {
            Ok(path) => path,
            Err(_) => continue,
        };
        let (region_translations, translated_full_text) =
            match export_translations(state, file_id, &params.target_lang).await {
                Ok(translations) => translations,
                Err(error) => {
                    tracing::error!(%error, "ocr_export_batch overlay translations query failed");
                    return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
                }
            };
        let translations = region_translations
            .into_iter()
            .filter_map(|(id, text)| Some((id.parse().ok()?, text.as_str()?.to_owned())))
            .collect();
        let regions =
            serde_json::from_value(result.get("regions").cloned().unwrap_or_else(|| json!([])))
                .unwrap_or_default();
        let full_text = result
            .get("full_text")
            .and_then(serde_json::Value::as_str)
            .unwrap_or("");
        let bytes = match crate::ocr::overlay::render(
            &image_path,
            regions,
            full_text,
            &translations,
            mode,
            format,
            font,
        ) {
            Ok(bytes) => bytes,
            Err(crate::ocr::overlay::Error::TooLarge) => {
                return overlay_error(StatusCode::BAD_REQUEST, "overlay_too_large");
            }
            Err(error) => {
                tracing::error!(?error, "OCR batch overlay render failed");
                return overlay_error(StatusCode::INTERNAL_SERVER_ERROR, "overlay_render_failed");
            }
        };
        exports.push((bytes, format!("ocr_overlay_{file_id}.png")));
    }
    let bytes = match build_ocr_overlay_zip(exports) {
        Ok(bytes) => bytes,
        Err(error) => {
            tracing::error!(%error, "ocr_export_batch overlay zip failed");
            return export_error("OCR batch export failed", StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let disposition = HeaderValue::from_static("attachment; filename=\"ocr_overlay_batch.zip\"");
    let mut response = bytes.into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/zip"),
    );
    response
        .headers_mut()
        .insert(header::CONTENT_DISPOSITION, disposition);
    response
}

async fn ocr_export_batch_unsupported(state: &SharedState, params: BatchExportParams) -> Response {
    let results = match batch_export_results(state, &params.file_ids).await {
        Ok(results) if results.is_empty() => {
            return export_error(
                "No OCR results found for given file_ids",
                StatusCode::NOT_FOUND,
            );
        }
        Ok(results) => results,
        Err(error) => {
            tracing::error!(%error, "ocr_export_batch query failed");
            return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let _ = results;
    if !params.output_dir.is_empty() {
        return export_not_ported("Saving OCR batch exports to a server-side directory");
    }
    match params.format.as_str() {
        "overlay" => export_not_ported("OCR overlay image export"),
        "pdf" => export_not_ported("PDF OCR export"),
        _ => export_error("Invalid format", StatusCode::BAD_REQUEST),
    }
}

async fn ocr_export_batch_zip(
    state: &SharedState,
    params: BatchExportParams,
    format: ExportFormat,
) -> Response {
    let results = match batch_export_results(state, &params.file_ids).await {
        Ok(results) if results.is_empty() => {
            return export_error(
                "No OCR results found for given file_ids",
                StatusCode::NOT_FOUND,
            );
        }
        Ok(results) => results,
        Err(error) => {
            tracing::error!(%error, "ocr_export_batch query failed");
            return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    if !params.output_dir.is_empty() {
        return export_not_ported("Saving OCR batch exports to a server-side directory");
    }
    let mut exports = Vec::with_capacity(results.len());
    for (file_id, result) in results {
        let (translations, translated_full_text) = if params.include_translation {
            match export_translations(state, file_id, &params.target_lang).await {
                Ok(translations) => translations,
                Err(error) => {
                    tracing::error!(%error, "ocr_export_batch translations query failed");
                    return export_error(&error.to_string(), StatusCode::INTERNAL_SERVER_ERROR);
                }
            }
        } else {
            (serde_json::Map::new(), String::new())
        };
        exports.push(export_content(
            &result,
            format,
            file_id,
            &translations,
            &translated_full_text,
            &params.target_lang,
        ));
    }
    let bytes = match build_ocr_export_zip(exports) {
        Ok(bytes) => bytes,
        Err(error) => {
            tracing::error!(%error, "ocr_export_batch zip failed");
            return export_error("OCR batch export failed", StatusCode::INTERNAL_SERVER_ERROR);
        }
    };
    let suffix = if params.target_lang.is_empty() {
        ""
    } else {
        "_"
    };
    let filename = format!(
        "ocr_export_{}{suffix}{}.zip",
        params.format, params.target_lang
    );
    let disposition = match HeaderValue::from_str(&content_disposition(&filename)) {
        Ok(disposition) => disposition,
        Err(_) => return export_error("Invalid export filename", StatusCode::BAD_REQUEST),
    };
    let mut response = bytes.into_response();
    response.headers_mut().insert(
        header::CONTENT_TYPE,
        HeaderValue::from_static("application/zip"),
    );
    response
        .headers_mut()
        .insert(header::CONTENT_DISPOSITION, disposition);
    response
}

async fn batch_export_results(
    state: &SharedState,
    file_ids: &[i64],
) -> Result<Vec<(i64, serde_json::Value)>, sqlx::Error> {
    let mut results = Vec::new();
    for file_id in file_ids {
        if let Some(row) = sqlx::query(&format!(
            "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC LIMIT 1"
        ))
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await?
        {
            results.push((*file_id, row_to_export_result(&row)));
        }
    }
    Ok(results)
}

fn build_ocr_export_zip(
    exports: Vec<(String, String, &'static str)>,
) -> zip::result::ZipResult<Vec<u8>> {
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
    for (content, filename, _) in exports {
        writer.start_file(filename, options)?;
        writer.write_all(content.as_bytes())?;
    }
    writer.finish().map(Cursor::into_inner)
}

fn build_ocr_overlay_zip(exports: Vec<(Vec<u8>, String)>) -> zip::result::ZipResult<Vec<u8>> {
    let mut writer = ZipWriter::new(Cursor::new(Vec::new()));
    let options = SimpleFileOptions::default().compression_method(CompressionMethod::Deflated);
    for (content, filename) in exports {
        writer.start_file(filename, options)?;
        writer.write_all(&content)?;
    }
    writer.finish().map(Cursor::into_inner)
}

fn export_not_ported(feature: &str) -> Response {
    (
        StatusCode::NOT_IMPLEMENTED,
        Json(json!({
            "ok": false,
            "code": "not_ported",
            "error": format!(
                "{feature} is not available in the Rust server yet; run the Python server for this feature"
            ),
        })),
    )
        .into_response()
}

fn export_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

fn row_to_export_result(row: &sqlx::sqlite::SqliteRow) -> serde_json::Value {
    let regions = row
        .try_get::<Option<String>, _>("regions_json")
        .ok()
        .flatten()
        .and_then(|text| serde_json::from_str(&text).ok())
        .unwrap_or_else(|| json!([]));
    let task = row.get::<String, _>("task");
    let mut data = serde_json::Map::from_iter([
        ("file_id".into(), json!(row.get::<i64, _>("file_id"))),
        ("engine".into(), json!(row.get::<String, _>("engine"))),
        ("task".into(), json!(task.clone())),
        ("regions".into(), regions),
        (
            "full_text".into(),
            json!(row
                .try_get::<Option<String>, _>("full_text")
                .ok()
                .flatten()
                .unwrap_or_default()),
        ),
        (
            "language".into(),
            json!(row
                .try_get::<Option<String>, _>("language")
                .ok()
                .flatten()
                .unwrap_or_default()),
        ),
    ]);
    if task == "ocr_document" {
        let structured = row
            .try_get::<Option<String>, _>("structured_json")
            .ok()
            .flatten()
            .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
            .unwrap_or_else(|| json!({}));
        data.insert(
            "headings".into(),
            structured
                .get("headings")
                .cloned()
                .unwrap_or_else(|| json!([])),
        );
        data.insert(
            "tables".into(),
            structured
                .get("tables")
                .cloned()
                .unwrap_or_else(|| json!([])),
        );
        data.insert(
            "page_layout".into(),
            structured
                .get("page_layout")
                .cloned()
                .unwrap_or_else(|| json!("")),
        );
    }
    serde_json::Value::Object(data)
}

async fn export_translations(
    state: &SharedState,
    file_id: i64,
    target_lang: &str,
) -> Result<(serde_json::Map<String, serde_json::Value>, String), sqlx::Error> {
    let rows = sqlx::query(
        "SELECT t.translated_text, t.region_translations_json FROM file_translations t \
         JOIN file_ocr_results r ON r.id=t.ocr_result_id WHERE r.file_id=? \
         AND (?='' OR t.target_lang=?) ORDER BY t.created_at DESC",
    )
    .bind(file_id)
    .bind(target_lang)
    .bind(target_lang)
    .fetch_all(&state.db_read)
    .await?;
    let mut regions = serde_json::Map::new();
    let mut full_text = String::new();
    for row in rows {
        if full_text.is_empty() {
            full_text = row
                .try_get::<Option<String>, _>("translated_text")?
                .unwrap_or_default();
        }
        let entries = row
            .try_get::<Option<String>, _>("region_translations_json")?
            .and_then(|text| serde_json::from_str::<serde_json::Value>(&text).ok())
            .and_then(|value| value.as_array().cloned())
            .unwrap_or_default();
        for entry in entries {
            if let (Some(id), Some(text)) = (
                entry.get("region_id").and_then(serde_json::Value::as_i64),
                entry.get("translated").and_then(serde_json::Value::as_str),
            ) {
                if !text.is_empty() {
                    regions.insert(id.to_string(), json!(text));
                }
            }
        }
    }
    Ok((regions, full_text))
}

fn export_content(
    result: &serde_json::Value,
    format: ExportFormat,
    file_id: i64,
    translations: &serde_json::Map<String, serde_json::Value>,
    translated_full_text: &str,
    target_lang: &str,
) -> (String, String, &'static str) {
    let suffix = if target_lang.is_empty() {
        String::new()
    } else {
        format!("_{target_lang}")
    };
    let filename = format!("ocr_{file_id}{suffix}.{}", format.extension());
    let full_text = result["full_text"].as_str().unwrap_or("");
    let regions = result["regions"].as_array().cloned().unwrap_or_default();
    let has_trans = !translations.is_empty() || !translated_full_text.is_empty();
    let content = match format {
        ExportFormat::Txt if has_trans && !translations.is_empty() && !regions.is_empty() => {
            let mut lines = Vec::new();
            for region in &regions {
                lines.push(region["text"].as_str().unwrap_or("").to_owned());
                let text = translated_region(translations, region);
                if !text.is_empty() {
                    lines.extend([format!(">> {text}"), String::new()]);
                }
            }
            format!("{}\n", lines.join("\n").trim_end())
        }
        ExportFormat::Txt if has_trans && !translated_full_text.is_empty() => {
            format!("{full_text}\n\n--- Translation ---\n\n{translated_full_text}\n")
        }
        ExportFormat::Txt => format!("{full_text}\n"),
        ExportFormat::Md => export_markdown(
            result,
            &regions,
            translations,
            translated_full_text,
            has_trans,
        ),
        ExportFormat::Json => export_json(result, translations, translated_full_text, has_trans),
    };
    let content_type = match format {
        ExportFormat::Txt => "text/plain; charset=utf-8",
        ExportFormat::Md => "text/markdown; charset=utf-8",
        ExportFormat::Json => "application/json",
    };
    (content, filename, content_type)
}

fn export_json(
    result: &serde_json::Value,
    translations: &serde_json::Map<String, serde_json::Value>,
    translated_full_text: &str,
    has_trans: bool,
) -> String {
    let quoted =
        |value: &serde_json::Value| serde_json::to_string(value).unwrap_or_else(|_| "null".into());
    let region = |value: &serde_json::Value| {
        let mut fields = vec![
            (
                "region_id",
                value.get("region_id").cloned().unwrap_or_else(|| json!(0)),
            ),
            (
                "bbox",
                value.get("bbox").cloned().unwrap_or_else(|| json!([])),
            ),
            (
                "text",
                value.get("text").cloned().unwrap_or_else(|| json!("")),
            ),
            (
                "confidence",
                value
                    .get("confidence")
                    .cloned()
                    .unwrap_or_else(|| json!(0.0)),
            ),
            (
                "direction",
                value
                    .get("direction")
                    .cloned()
                    .unwrap_or_else(|| json!("horizontal")),
            ),
            (
                "label",
                value.get("label").cloned().unwrap_or_else(|| json!("")),
            ),
        ];
        let translated = translated_region(translations, value);
        if has_trans && !translated.is_empty() {
            fields.push(("translated", json!(translated)));
        }
        let fields = fields
            .into_iter()
            .map(|(key, value)| {
                format!(
                    "\"{key}\": {}",
                    serde_json::to_string_pretty(&value)
                        .unwrap_or_else(|_| "null".into())
                        .replace('\n', "\n  ")
                )
            })
            .collect::<Vec<_>>()
            .join(",\n  ");
        format!("{{\n  {fields}\n}}")
    };
    let regions = result["regions"]
        .as_array()
        .into_iter()
        .flatten()
        .map(region)
        .map(|region| format!("    {}", region.replace('\n', "\n    ")))
        .collect::<Vec<_>>()
        .join(",\n");
    let mut fields = vec![
        format!("\"file_id\": {}", quoted(&result["file_id"])),
        format!("\"engine\": {}", quoted(&result["engine"])),
        format!("\"task\": {}", quoted(&result["task"])),
        format!(
            "\"regions\": [{}]",
            if regions.is_empty() {
                String::new()
            } else {
                format!("\n{regions}\n  ")
            }
        ),
        format!("\"full_text\": {}", quoted(&result["full_text"])),
        format!("\"language\": {}", quoted(&result["language"])),
    ];
    if result["task"] == "ocr_document" {
        for key in ["headings", "tables", "page_layout"] {
            fields.push(format!("\"{key}\": {}", quoted(&result[key])));
        }
    }
    if has_trans {
        fields.push("\"translations\": {}".into());
    }
    if !translated_full_text.is_empty() {
        fields.push(format!(
            "\"translated_full_text\": {}",
            quoted(&json!(translated_full_text))
        ));
    }
    format!("{{\n  {}\n}}", fields.join(",\n  "))
}

fn export_markdown(
    result: &serde_json::Value,
    regions: &[serde_json::Value],
    translations: &serde_json::Map<String, serde_json::Value>,
    translated_full_text: &str,
    has_trans: bool,
) -> String {
    let mut lines = Vec::new();
    let full_text = result["full_text"].as_str().unwrap_or("");
    match result["task"].as_str().unwrap_or("ocr") {
        "ocr_document" if !regions.is_empty() => {
            for region in regions {
                let text = region["text"].as_str().unwrap_or("");
                match region["label"].as_str().unwrap_or("") {
                    "heading" => {
                        lines.push(format!("## {text}"));
                        if !translations.is_empty()
                            && !translated_region(translations, region).is_empty()
                        {
                            lines.push(format!("*{}*", translated_region(translations, region)));
                        }
                        lines.push(String::new());
                    }
                    "table" => {
                        lines.push(text.to_owned());
                        lines.push(String::new());
                    }
                    _ => {
                        lines.push(text.to_owned());
                        if !translations.is_empty()
                            && !translated_region(translations, region).is_empty()
                        {
                            lines.extend([
                                String::new(),
                                format!("> {}", translated_region(translations, region)),
                            ]);
                        }
                        lines.push(String::new());
                    }
                }
            }
        }
        "ocr_manga" => {
            for region in regions {
                let label = region["label"].as_str().unwrap_or("");
                let prefix = if label.is_empty() {
                    String::new()
                } else {
                    format!("[{label}] ")
                };
                let vertical = if region["direction"].as_str() == Some("vertical") {
                    " (vertical)"
                } else {
                    ""
                };
                lines.push(format!(
                    "{prefix}{}{vertical}",
                    region["text"].as_str().unwrap_or("")
                ));
                if !translations.is_empty() && !translated_region(translations, region).is_empty() {
                    lines.push(format!("> {}", translated_region(translations, region)));
                }
            }
        }
        _ => {
            for region in regions {
                lines.push(region["text"].as_str().unwrap_or("").to_owned());
                if !translations.is_empty() && !translated_region(translations, region).is_empty() {
                    lines.extend([
                        format!("> {}", translated_region(translations, region)),
                        String::new(),
                    ]);
                }
            }
        }
    }
    if lines.is_empty() {
        lines.push(full_text.to_owned());
    }
    if has_trans && translations.is_empty() && !translated_full_text.is_empty() {
        lines.extend([
            String::new(),
            "---".into(),
            String::new(),
            "**Translation:**".into(),
            String::new(),
            translated_full_text.into(),
        ]);
    }
    format!("{}\n", lines.join("\n").trim_end())
}

fn translated_region<'a>(
    translations: &'a serde_json::Map<String, serde_json::Value>,
    region: &serde_json::Value,
) -> &'a str {
    region
        .get("region_id")
        .and_then(serde_json::Value::as_i64)
        .and_then(|id| translations.get(&id.to_string()))
        .and_then(serde_json::Value::as_str)
        .unwrap_or("")
}

fn content_disposition(filename: &str) -> String {
    if filename.is_ascii() {
        return format!("attachment; filename=\"{filename}\"");
    }
    format!(
        "attachment; filename*=UTF-8''{}",
        urlencoding::encode(filename)
    )
}

#[derive(Deserialize)]
pub struct BenchmarkCasesParams {
    dir: Option<String>,
}

/// GET /api/ocr/benchmark/cases
pub async fn ocr_benchmark_cases(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(params): Query<BenchmarkCasesParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    match load_benchmark_cases(
        &benchmark_root(&state),
        params.dir.as_deref().filter(|dir| !dir.is_empty()),
    ) {
        Ok(cases) => Json(json!({"cases": cases, "total": cases.len()})).into_response(),
        Err(error) => (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": error})),
        )
            .into_response(),
    }
}

fn benchmark_root(state: &SharedState) -> PathBuf {
    state
        .config
        .project_root
        .join("extensions/builtin_ocr/benchmarks")
}

fn load_benchmark_cases(
    root: &FsPath,
    requested_dir: Option<&str>,
) -> Result<Vec<serde_json::Value>, String> {
    let bdir = match requested_dir {
        Some(dir) => validate_benchmark_dir(root, dir)?,
        None => root.to_path_buf(),
    };
    if !bdir.exists() {
        return Ok(Vec::new());
    }
    let manifest = bdir.join("manifest.json");
    if manifest.exists() {
        return Ok(load_manifest_cases(&manifest, &bdir));
    }
    Ok(auto_detect_cases(&bdir))
}

fn validate_benchmark_dir(root: &FsPath, dir: &str) -> Result<PathBuf, String> {
    if dir.contains('\0') {
        return Err("Invalid benchmark_dir: null byte detected".to_owned());
    }
    if FsPath::new(dir)
        .components()
        .any(|component| component == Component::ParentDir)
    {
        return Err(format!(
            "Invalid benchmark_dir: '..' traversal not allowed: {dir}"
        ));
    }
    let bdir = std::fs::canonicalize(dir)
        .map_err(|_| format!("Invalid benchmark_dir: not an existing directory: {dir}"))?;
    if !bdir.is_dir() {
        return Err(format!(
            "Invalid benchmark_dir: not an existing directory: {dir}"
        ));
    }
    let resolved_root = std::fs::canonicalize(root).unwrap_or_else(|_| root.to_path_buf());
    if !bdir.starts_with(&resolved_root) {
        return Err(format!(
            "Invalid benchmark_dir: must be inside benchmark root: {}",
            resolved_root.display()
        ));
    }
    Ok(bdir)
}

fn contain_under(root: &FsPath, relative: &str) -> Result<PathBuf, ()> {
    if relative.contains('\0') {
        return Err(());
    }
    let relative = FsPath::new(relative);
    if relative.is_absolute()
        || relative
            .components()
            .any(|component| component == Component::ParentDir)
    {
        return Err(());
    }
    let resolved_root = std::fs::canonicalize(root).map_err(|_| ())?;
    let mut candidate = resolved_root.clone();
    for component in relative.components() {
        let Component::Normal(part) = component else {
            continue;
        };
        candidate.push(part);
        candidate = resolve_component(&candidate)?;
        if !candidate.starts_with(&resolved_root) {
            return Err(());
        }
    }
    Ok(candidate)
}

/// Resolves each path component before the caller checks containment.
/// A dangling symlink is still expanded so its target cannot escape unnoticed.
fn resolve_component(candidate: &FsPath) -> Result<PathBuf, ()> {
    match std::fs::canonicalize(candidate) {
        Ok(path) => Ok(path),
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => {
            match std::fs::read_link(candidate) {
                Ok(target) => {
                    let target = if target.is_absolute() {
                        target
                    } else {
                        candidate.parent().ok_or(())?.join(target)
                    };
                    let target = normalize_path(&target);
                    Ok(std::fs::canonicalize(&target).unwrap_or(target))
                }
                Err(error) if error.kind() == std::io::ErrorKind::InvalidInput => {
                    Ok(candidate.to_path_buf())
                }
                Err(_) => Err(()),
            }
        }
        Err(_) => Err(()),
    }
}

fn normalize_path(path: &FsPath) -> PathBuf {
    let mut normalized = PathBuf::new();
    for component in path.components() {
        match component {
            Component::Prefix(prefix) => normalized.push(prefix.as_os_str()),
            Component::RootDir => normalized.push(component.as_os_str()),
            Component::CurDir => {}
            Component::ParentDir => {
                normalized.pop();
            }
            Component::Normal(part) => normalized.push(part),
        }
    }
    normalized
}

fn load_manifest_cases(manifest: &FsPath, base_dir: &FsPath) -> Vec<serde_json::Value> {
    let Ok(data) = std::fs::read_to_string(manifest)
        .ok()
        .and_then(|contents| serde_json::from_str::<serde_json::Value>(&contents).ok())
        .ok_or(())
    else {
        tracing::warn!(path = %manifest.display(), "failed to load benchmark manifest");
        return Vec::new();
    };
    data.get("cases")
        .and_then(serde_json::Value::as_array)
        .into_iter()
        .flatten()
        .filter_map(|item| manifest_case(item, base_dir))
        .collect()
}

fn manifest_case(item: &serde_json::Value, base_dir: &FsPath) -> Option<serde_json::Value> {
    let image = item.get("image")?.as_str()?;
    let path = contain_under(base_dir, image).ok()?;
    if !path.exists() {
        tracing::warn!(image, "benchmark image not found");
        return None;
    }
    Some(json!({
        "image": path.file_name()?.to_string_lossy(),
        "task": item.get("task").and_then(serde_json::Value::as_str).unwrap_or("ocr"),
        "language": item.get("language").and_then(serde_json::Value::as_str).unwrap_or("auto"),
        "expected_length": item.get("expected_text").and_then(serde_json::Value::as_str).unwrap_or("").chars().count(),
        "tags": item.get("tags").and_then(serde_json::Value::as_array).cloned().unwrap_or_default(),
    }))
}

fn auto_detect_cases(bdir: &FsPath) -> Vec<serde_json::Value> {
    let mut images = match std::fs::read_dir(bdir) {
        Ok(entries) => entries
            .filter_map(Result::ok)
            .map(|entry| entry.path())
            .collect::<Vec<_>>(),
        Err(_) => return Vec::new(),
    };
    images.sort();
    images
        .into_iter()
        .filter(|image| matches!(image.extension().and_then(|ext| ext.to_str()).map(str::to_ascii_lowercase).as_deref(), Some("png" | "jpg" | "jpeg" | "webp" | "bmp")))
        .filter_map(|image| {
            let text_name = image.file_stem()?.to_string_lossy() + ".txt";
            let text = contain_under(bdir, &text_name).ok()?;
            let expected = std::fs::read_to_string(text).ok()?.trim().to_owned();
            let stem = image.file_stem()?.to_string_lossy().to_ascii_lowercase();
            let task = if stem.contains("manga") || stem.contains("comic") { "ocr_manga" } else if stem.contains("doc") || stem.contains("invoice") { "ocr_document" } else { "ocr" };
            Some(json!({"image": image.file_name()?.to_string_lossy(), "task": task, "language": "auto", "expected_length": expected.chars().count(), "tags": []}))
        })
        .collect()
}

/// GET /api/ocr/benchmark/report/{report_id}
pub async fn ocr_benchmark_report(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(report_id): Path<String>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }
    if report_id.contains('/') || report_id.contains('\\') || report_id.contains("..") {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "invalid_report_id"})),
        )
            .into_response();
    }
    let reports = state
        .config
        .project_root
        .join("extensions/builtin_ocr/benchmarks/reports");
    match std::fs::read(reports.join(format!("{report_id}.json"))) {
        Ok(bytes) => match serde_json::from_slice::<serde_json::Value>(&bytes) {
            Ok(report) => Json(report).into_response(),
            Err(_) => (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "invalid_report"})),
            )
                .into_response(),
        },
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => (
            StatusCode::NOT_FOUND,
            Json(json!({"ok": false, "error": "report_not_found"})),
        )
            .into_response(),
        Err(_) => (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "report_read_failed"})),
        )
            .into_response(),
    }
}

#[derive(Deserialize, Default)]
pub struct ResultGetParams {
    pub task: Option<String>,
    pub engine: Option<String>,
    pub all: Option<String>,
}

#[derive(Deserialize, Default)]
pub struct ResultDeleteParams {
    pub task: Option<String>,
    pub engine: Option<String>,
}

#[derive(Deserialize, Default)]
pub struct TranslationsParams {
    pub target_lang: Option<String>,
}

const RESULT_COLS: &str =
    "id, file_id, engine, task, regions_json, full_text, language, structured_json, created_at";

fn row_to_result(row: &sqlx::sqlite::SqliteRow) -> serde_json::Value {
    let regions: serde_json::Value = row
        .try_get::<Option<String>, _>("regions_json")
        .ok()
        .flatten()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!([]));
    let structured: serde_json::Value = row
        .try_get::<Option<String>, _>("structured_json")
        .ok()
        .flatten()
        .and_then(|s| serde_json::from_str(&s).ok())
        .unwrap_or_else(|| json!({}));

    json!({
        "ok": true,
        "error": null,
        "data": null,
        "id": row.get::<i64, _>("id"),
        "file_id": row.get::<i64, _>("file_id"),
        "engine": row.get::<String, _>("engine"),
        "task": row.get::<String, _>("task"),
        "regions": regions,
        "full_text": row.try_get::<Option<String>, _>("full_text").ok().flatten().unwrap_or_default(),
        "language": row.try_get::<Option<String>, _>("language").ok().flatten().unwrap_or_default(),
        "headings": structured.get("headings").cloned().unwrap_or_else(|| json!([])),
        "tables": structured.get("tables").cloned().unwrap_or_else(|| json!([])),
        "page_layout": structured.get("page_layout").cloned().unwrap_or_else(|| json!("")),
        "created_at": row.get::<i64, _>("created_at"),
    })
}

/// GET /api/ocr/result/{file_id}
pub async fn ocr_result_get(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Query(params): Query<ResultGetParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let all_truthy = params
        .all
        .as_deref()
        .is_some_and(|v| !v.is_empty() && v != "0" && v != "false");
    if all_truthy {
        let rows = sqlx::query(&format!(
            "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC"
        ))
        .bind(file_id)
        .fetch_all(&state.db_read)
        .await;
        return match rows {
            Ok(rows) => Json(json!({
                "ok": true,
                "error": null,
                "data": null,
                "file_id": file_id,
                "results": rows.iter().map(row_to_result).collect::<Vec<_>>()
            }))
            .into_response(),
            Err(e) => {
                tracing::error!("ocr_result_get all: {e}");
                (
                    StatusCode::INTERNAL_SERVER_ERROR,
                    Json(json!({"ok": false, "error": "db_error"})),
                )
                    .into_response()
            }
        };
    }

    let row = match (&params.task, &params.engine) {
        (Some(task), Some(engine)) => {
            sqlx::query(&format!(
                "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? AND task=? AND engine=? LIMIT 1"
            ))
            .bind(file_id)
            .bind(task)
            .bind(engine)
            .fetch_optional(&state.db_read)
            .await
        }
        (Some(task), None) => {
            sqlx::query(&format!(
                "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? AND task=? ORDER BY created_at DESC, id DESC LIMIT 1"
            ))
            .bind(file_id)
            .bind(task)
            .fetch_optional(&state.db_read)
            .await
        }
        _ => {
            sqlx::query(&format!(
                "SELECT {RESULT_COLS} FROM file_ocr_results WHERE file_id=? ORDER BY created_at DESC, id DESC LIMIT 1"
            ))
            .bind(file_id)
            .fetch_optional(&state.db_read)
            .await
        }
    };

    match row {
        Ok(Some(row)) => Json(row_to_result(&row)).into_response(),
        Ok(None) => Json(json!({"ok": true, "error": null, "data": null, "status": "not_found"}))
            .into_response(),
        Err(e) => {
            tracing::error!("ocr_result_get: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

/// GET /api/ocr/translations/{file_id}
pub async fn ocr_translations(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Path(file_id): Path<i64>,
    Query(params): Query<TranslationsParams>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let base_sql = r#"
        SELECT
            t.id,
            t.ocr_result_id,
            t.target_lang,
            t.translated_text,
            t.engine,
            t.region_translations_json,
            t.created_at,
            r.file_id,
            r.task,
            r.engine AS ocr_engine
        FROM file_translations t
        JOIN file_ocr_results r ON r.id = t.ocr_result_id
        WHERE r.file_id=?
    "#;

    let rows = if let Some(target_lang) = params.target_lang.as_deref().filter(|s| !s.is_empty()) {
        sqlx::query(&format!(
            "{base_sql} AND t.target_lang=? ORDER BY t.created_at DESC, t.id DESC"
        ))
        .bind(file_id)
        .bind(target_lang)
        .fetch_all(&state.db_read)
        .await
    } else {
        sqlx::query(&format!("{base_sql} ORDER BY t.created_at DESC, t.id DESC"))
            .bind(file_id)
            .fetch_all(&state.db_read)
            .await
    };

    match rows {
        Ok(rows) => {
            let translations: Vec<_> = rows
                .iter()
                .map(|row| {
                    let region_translations: serde_json::Value = row
                        .try_get::<Option<String>, _>("region_translations_json")
                        .ok()
                        .flatten()
                        .and_then(|s| serde_json::from_str(&s).ok())
                        .unwrap_or_else(|| json!([]));
                    json!({
                        "id": row.get::<i64, _>("id"),
                        "ocr_result_id": row.get::<i64, _>("ocr_result_id"),
                        "target_lang": row.get::<String, _>("target_lang"),
                        "translated_text": row.try_get::<Option<String>, _>("translated_text").ok().flatten(),
                        "engine": row.try_get::<Option<String>, _>("engine").ok().flatten().unwrap_or_default(),
                        "created_at": row.get::<i64, _>("created_at"),
                        "region_translations": region_translations,
                        "file_id": row.get::<i64, _>("file_id"),
                        "task": row.get::<String, _>("task"),
                        "ocr_engine": row.get::<String, _>("ocr_engine"),
                    })
                })
                .collect();
            Json(json!({
                "ok": true,
                "error": null,
                "data": null,
                "file_id": file_id,
                "translations": translations,
            }))
            .into_response()
        }
        Err(e) => {
            tracing::error!("ocr_translations: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

/// DELETE /api/ocr/result/{file_id}
pub async fn ocr_result_delete(
    State(state): State<SharedState>,
    Path(file_id): Path<i64>,
    Query(params): Query<ResultDeleteParams>,
) -> Response {
    let (trans_sql, results_sql) = match (&params.task, &params.engine) {
        (Some(_), Some(_)) => (
            "DELETE FROM file_translations WHERE ocr_result_id IN (SELECT id FROM file_ocr_results WHERE file_id=? AND task=? AND engine=?)",
            "DELETE FROM file_ocr_results WHERE file_id=? AND task=? AND engine=?",
        ),
        (Some(_), None) => (
            "DELETE FROM file_translations WHERE ocr_result_id IN (SELECT id FROM file_ocr_results WHERE file_id=? AND task=?)",
            "DELETE FROM file_ocr_results WHERE file_id=? AND task=?",
        ),
        _ => (
            "DELETE FROM file_translations WHERE ocr_result_id IN (SELECT id FROM file_ocr_results WHERE file_id=?)",
            "DELETE FROM file_ocr_results WHERE file_id=?",
        ),
    };

    let trans_result = match (&params.task, &params.engine) {
        (Some(task), Some(engine)) => {
            sqlx::query(trans_sql)
                .bind(file_id)
                .bind(task)
                .bind(engine)
                .execute(&state.db)
                .await
        }
        (Some(task), None) => {
            sqlx::query(trans_sql)
                .bind(file_id)
                .bind(task)
                .execute(&state.db)
                .await
        }
        _ => {
            sqlx::query(trans_sql)
                .bind(file_id)
                .execute(&state.db)
                .await
        }
    };
    if let Err(e) = trans_result {
        tracing::error!("ocr_result_delete translations: {e}");
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": "db_error"})),
        )
            .into_response();
    }

    let result = match (&params.task, &params.engine) {
        (Some(task), Some(engine)) => {
            sqlx::query(results_sql)
                .bind(file_id)
                .bind(task)
                .bind(engine)
                .execute(&state.db)
                .await
        }
        (Some(task), None) => {
            sqlx::query(results_sql)
                .bind(file_id)
                .bind(task)
                .execute(&state.db)
                .await
        }
        _ => {
            sqlx::query(results_sql)
                .bind(file_id)
                .execute(&state.db)
                .await
        }
    };

    match result {
        Ok(r) => ocr_ok(json!({"deleted": r.rows_affected()})),
        Err(e) => {
            tracing::error!("ocr_result_delete: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "db_error"})),
            )
                .into_response()
        }
    }
}

/// PUT /api/ocr/profiles/{model_prefix}
///
/// Ports `core/ocr_api/benchmark_ops.py::api_ocr_profile_update`.
///
/// Storage is the extension's own `profiles/model_profiles.json`, NOT the
/// unrelated `profiles_dir()` in auto_stubs.rs (which resolves
/// TAGDB_PROFILES_DIR / project_root/profiles and belongs to a different
/// feature). Writing there would silently split the store in two.
///
/// The Python side clamps each score to 0..=100 via `max(0, min(100, int(v)))`
/// and drops non-numeric values; the file carries `{version, updated_at,
/// profiles}` and the reader also accepts a bare mapping. Both behaviours are
/// reproduced here so a file written by either side stays readable by the other.
pub async fn ocr_profiles_update(
    State(state): State<SharedState>,
    Path(model_prefix): Path<String>,
    auth_context: Option<Extension<AuthContext>>,
    Json(body): Json<serde_json::Value>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let scores = body.get("scores").and_then(|v| v.as_object());
    let Some(scores) = scores.filter(|m| !m.is_empty()) else {
        // Python: `if not scores: return api_error("scores is required", 400)`.
        // An empty object takes this branch there too, so it does here.
        // Python's api_error always marks the body `ok: false`; this one had
        // no `ok` key at all.
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "scores is required"})),
        )
            .into_response();
    };

    // Same clamp and same "numbers only" filter as update_model_profile().
    let mut clamped = serde_json::Map::new();
    for (k, v) in scores {
        if let Some(n) = v.as_f64() {
            let i = crate::num::sat_i64(n.trunc());
            clamped.insert(k.clone(), json!(i.clamp(0, 100)));
        }
    }

    let path = ocr_profiles_path(&state);
    let mut store = read_ocr_profiles(&path);
    store.insert(
        model_prefix.clone(),
        serde_json::Value::Object(clamped.clone()),
    );

    if let Err(e) = write_ocr_profiles(&path, &store) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"error": format!("failed to save profiles: {e}")})),
        )
            .into_response();
    }

    ocr_ok(json!({"model": model_prefix, "scores": clamped}))
}

/// GET /api/ocr/profiles
pub async fn ocr_profiles_list(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let local = read_ocr_profiles(&ocr_profiles_path(&state));
    let mut profiles = builtin_ocr_profiles();
    profiles.extend(local.clone());
    let mut profiles = profiles.into_iter().collect::<Vec<_>>();
    profiles.sort_unstable_by(|(model, _), (other, _)| model.cmp(other));

    Json(
        json!({"profiles": profiles.into_iter().map(|(model, scores)| {
        json!({
            "model": model,
            "scores": scores,
            "source": if local.contains_key(&model) { "local" } else { "builtin" },
        })
    }).collect::<Vec<_>>() }),
    )
    .into_response()
}

/// POST /api/ocr/profiles/fetch
pub async fn ocr_profiles_fetch(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    body: Option<Json<serde_json::Value>>,
) -> Response {
    ocr_profiles_fetch_with_policy(
        state,
        auth_context,
        body.map(|Json(body)| body).unwrap_or_default(),
        false,
    )
    .await
}

async fn ocr_profiles_fetch_with_policy(
    state: SharedState,
    auth_context: Option<Extension<AuthContext>>,
    body: serde_json::Value,
    allow_local: bool,
) -> Response {
    if let Some(resp) = require_admin_scope(
        state.config.pin_auth_enabled,
        auth_context.as_ref().map(|e| &e.0),
    ) {
        return resp;
    }

    let url = body
        .get("url")
        .and_then(serde_json::Value::as_str)
        .unwrap_or("");
    if url.is_empty() {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "error": "url is required"})),
        )
            .into_response();
    }
    if let Some(error) = crate::routes::analysis_net::validate_openai_compat_url(url, allow_local) {
        let status = if error == "Blocked address" || error.to_lowercase().contains("http/https") {
            StatusCode::BAD_REQUEST
        } else {
            StatusCode::INTERNAL_SERVER_ERROR
        };
        return (status, Json(json!({"ok": false, "error": error}))).into_response();
    }

    let fetched = async {
        let client = crate::analysis_engines::http_client::build_pinned_client(
            url,
            allow_local,
            Duration::from_secs(15),
        )
        .await?;
        let response = client
            .get(url)
            .header(reqwest::header::USER_AGENT, "YU-AI-Manager")
            .header(reqwest::header::ACCEPT, "application/json")
            .send()
            .await
            .map_err(|error| {
                crate::analysis_engines::EngineError::msg(format!(
                    "Failed to fetch profiles: {error}"
                ))
            })?
            .error_for_status()
            .map_err(|error| {
                crate::analysis_engines::EngineError::msg(format!(
                    "Failed to fetch profiles: {error}"
                ))
            })?;
        let body =
            crate::analysis_engines::http_client::read_response_capped(response, 1_048_576).await?;
        serde_json::from_str::<serde_json::Value>(&body).map_err(|error| {
            crate::analysis_engines::EngineError::msg(format!("Failed to fetch profiles: {error}"))
        })
    }
    .await;

    let data = match fetched {
        Ok(data) => data,
        Err(error) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": error.to_string()})),
            )
                .into_response()
        }
    };
    let profiles = match data {
        serde_json::Value::Object(mut data) => match data.remove("profiles") {
            Some(serde_json::Value::Object(profiles)) => profiles,
            Some(_) => return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "Invalid profile format: expected JSON object"})),
            )
                .into_response(),
            None => data,
        },
        serde_json::Value::Null
        | serde_json::Value::Bool(_)
        | serde_json::Value::Number(_)
        | serde_json::Value::String(_)
        | serde_json::Value::Array(_) => {
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"ok": false, "error": "Invalid profile format: expected JSON object"})),
            )
                .into_response()
        }
    };

    let mut fetched = serde_json::Map::new();
    for (model, scores) in profiles {
        let Some(scores) = scores.as_object() else {
            continue;
        };
        let mut clamped = serde_json::Map::new();
        for (name, score) in scores {
            if let Some(score) = score.as_f64() {
                clamped.insert(
                    name.clone(),
                    json!(crate::num::sat_i64(score.trunc()).clamp(0, 100)),
                );
            }
        }
        fetched.insert(model, serde_json::Value::Object(clamped));
    }

    let path = ocr_profiles_path(&state);
    let existing = read_ocr_profiles(&path);
    let new_models = fetched
        .keys()
        .filter(|model| !existing.contains_key(*model))
        .count();
    let updated_models = fetched.len() - new_models;
    let mut merged = existing;
    merged.extend(fetched.clone());
    if let Err(error) = write_ocr_profiles(&path, &merged) {
        return (
            StatusCode::INTERNAL_SERVER_ERROR,
            Json(json!({"ok": false, "error": format!("failed to save profiles: {error}")})),
        )
            .into_response();
    }

    let fetched_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|duration| duration.as_secs() as i64)
        .unwrap_or(0);
    Json(json!({
        "profiles": fetched,
        "source": url,
        "fetched_at": fetched_at,
        "model_count": fetched.len(),
        "merged_count": merged.len(),
        "new_models": new_models,
        "updated_models": updated_models,
    }))
    .into_response()
}

fn builtin_ocr_profiles() -> serde_json::Map<String, serde_json::Value> {
    serde_json::from_value(json!({
        "openbmb/minicpm-v4.5": {
            "ocr": 97, "ocr_document": 90, "ocr_manga": 70,
            "caption": 95, "tag": 93, "nsfw": 60,
        },
        "openbmb/minicpm-o4.5": {
            "ocr": 95, "ocr_document": 92, "ocr_manga": 65,
            "caption": 93, "tag": 90,
        },
        "huihui_ai/qwen2.5-vl-abliterated": {
            "ocr": 80, "ocr_document": 75, "ocr_manga": 50,
            "caption": 85, "tag": 85, "nsfw": 95,
        },
        "huihui_ai/qwen3-vl-abliterated": {
            "ocr": 85, "ocr_document": 80, "ocr_manga": 55,
            "caption": 88, "tag": 88, "nsfw": 95,
        },
        "qwen2.5vl": {
            "ocr": 80, "ocr_document": 78, "ocr_manga": 50,
            "caption": 85, "tag": 85,
        },
        "llama3.2-vision": {
            "ocr": 70, "ocr_document": 65, "ocr_manga": 30,
            "caption": 80, "tag": 78,
        },
    }))
    .expect("builtin OCR profiles are objects")
}

fn ocr_profiles_path(state: &SharedState) -> std::path::PathBuf {
    state
        .config
        .project_root
        .join("extensions/builtin_ocr/profiles/model_profiles.json")
}

/// Read the profile map, tolerating both the wrapped and the bare shape.
fn read_ocr_profiles(path: &std::path::Path) -> serde_json::Map<String, serde_json::Value> {
    let Ok(text) = std::fs::read_to_string(path) else {
        return serde_json::Map::new();
    };
    let Ok(data) = serde_json::from_str::<serde_json::Value>(&text) else {
        // Python logs and returns {} rather than failing the request.
        return serde_json::Map::new();
    };
    match data.get("profiles") {
        Some(profiles) => profiles.as_object().cloned().unwrap_or_default(),
        None => data.as_object().cloned().unwrap_or_default(),
    }
}

fn write_ocr_profiles(
    path: &std::path::Path,
    profiles: &serde_json::Map<String, serde_json::Value>,
) -> std::io::Result<()> {
    if let Some(dir) = path.parent() {
        std::fs::create_dir_all(dir)?;
    }
    let updated_at = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let doc = json!({
        "version": 1,
        "updated_at": updated_at,
        "profiles": profiles,
    });
    std::fs::write(path, serde_json::to_string_pretty(&doc)?)
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::state::semantic_test_state_with_root;
    use axum::{
        body::{to_bytes, Body},
        http::{
            header::{CONTENT_TYPE, LOCATION},
            Request,
        },
        routing::{get, post},
        Router,
    };
    use std::sync::{
        atomic::{AtomicUsize, Ordering},
        Arc,
    };
    use tower::ServiceExt;

    async fn body_json(response: Response) -> serde_json::Value {
        let bytes = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&bytes).unwrap()
    }

    async fn test_state(root: &tempfile::TempDir) -> SharedState {
        semantic_test_state_with_root(false, String::new(), root.path().to_path_buf()).await
    }

    async fn translate_request(
        state: SharedState,
        body: Option<&str>,
    ) -> Result<Response, Box<dyn std::error::Error>> {
        let mut request = Request::builder().method("POST").uri("/translate/99");
        if body.is_some() {
            request = request.header(CONTENT_TYPE, "application/json");
        }
        let request =
            request.body(body.map_or_else(Body::empty, |body| Body::from(body.to_owned())))?;
        Ok(Router::new()
            .route("/translate/{file_id}", post(ocr_translate))
            .with_state(state)
            .oneshot(request)
            .await?)
    }

    async fn translate_missing_response(
        body: Option<&str>,
    ) -> Result<Response, Box<dyn std::error::Error>> {
        let root = tempfile::tempdir()?;
        let state = test_state(&root).await;
        create_export_schema(&state).await;
        translate_request(state, body).await
    }

    fn benchmark_dir(root: &tempfile::TempDir) -> PathBuf {
        root.path().join("extensions/builtin_ocr/benchmarks")
    }

    async fn benchmark_cases(state: SharedState, dir: Option<String>) -> Response {
        ocr_benchmark_cases(State(state), None, Query(BenchmarkCasesParams { dir })).await
    }

    async fn test_server(app: Router) -> Option<(String, tokio::task::JoinHandle<()>)> {
        let listener = tokio::net::TcpListener::bind("127.0.0.1:0").await.ok()?;
        let address = listener.local_addr().ok()?;
        let server = tokio::spawn(async move { axum::serve(listener, app).await.unwrap() });
        Some((format!("http://{address}/"), server))
    }

    #[tokio::test]
    async fn ocr_profiles_roundtrip_returns_written_profile() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let updated = ocr_profiles_update(
            State(state.clone()),
            Path("test-model".to_string()),
            None,
            Json(json!({"scores": {"ocr": 91}})),
        )
        .await;
        assert_eq!(updated.status(), StatusCode::OK);

        let body = body_json(ocr_profiles_list(State(state), None).await).await;
        assert_eq!(body["profiles"].as_array().unwrap().len(), 7);
        assert!(body["profiles"].as_array().unwrap().iter().any(|profile| {
            profile == &json!({"model": "test-model", "scores": {"ocr": 91}, "source": "local"})
        }));
    }

    #[tokio::test]
    async fn ocr_profiles_keeps_builtins_when_one_is_overridden_locally() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let path = ocr_profiles_path(&state);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(&path, r#"{"profiles":{"qwen2.5vl":{"ocr":99}}}"#).unwrap();

        let body = body_json(ocr_profiles_list(State(state), None).await).await;
        let profiles = body["profiles"].as_array().unwrap();
        assert_eq!(profiles.len(), 6);
        assert_eq!(profiles[0]["model"], "huihui_ai/qwen2.5-vl-abliterated");
        assert_eq!(profiles[5]["model"], "qwen2.5vl");
        assert!(profiles.iter().all(|profile| {
            profile["source"]
                == if profile["model"] == "qwen2.5vl" {
                    "local"
                } else {
                    "builtin"
                }
        }));
        assert_eq!(
            profiles[5],
            json!({"model": "qwen2.5vl", "scores": {"ocr": 99}, "source": "local"})
        );
    }

    #[tokio::test]
    async fn ocr_profiles_tolerates_missing_or_malformed_local_file() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let missing = ocr_profiles_list(State(state.clone()), None).await;
        assert_eq!(missing.status(), StatusCode::OK);
        assert_eq!(
            body_json(missing).await["profiles"]
                .as_array()
                .unwrap()
                .len(),
            6
        );

        let path = ocr_profiles_path(&state);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(path, "{bad json").unwrap();
        let malformed = ocr_profiles_list(State(state), None).await;
        assert_eq!(malformed.status(), StatusCode::OK);
        assert_eq!(
            body_json(malformed).await["profiles"]
                .as_array()
                .unwrap()
                .len(),
            6
        );
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_merges_and_returns_seven_keys() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let path = ocr_profiles_path(&state);
        std::fs::create_dir_all(path.parent().unwrap()).unwrap();
        std::fs::write(
            &path,
            r#"{"profiles":{"existing":{"ocr":1},"kept":{"ocr":2}}}"#,
        )
        .unwrap();
        let Some((url, server)) = test_server(Router::new().route(
            "/",
            get(|| async {
                Json(json!({"profiles":{"existing":{"ocr":101},"new":{"ocr":-2,"skip":"x"}}}))
            }),
        ))
        .await
        else {
            return;
        };

        let response = ocr_profiles_fetch_with_policy(state, None, json!({"url": url}), true).await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = body_json(response).await;
        assert_eq!(body.as_object().unwrap().len(), 7);
        assert_eq!(body["model_count"], 2);
        assert_eq!(body["merged_count"], 3);
        assert_eq!(body["new_models"], 1);
        assert_eq!(body["updated_models"], 1);
        assert_eq!(
            body["profiles"],
            json!({"existing":{"ocr":100},"new":{"ocr":0}})
        );
        server.abort();
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_does_not_follow_redirects() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let target_hits = Arc::new(AtomicUsize::new(0));
        let target_hits_for_route = target_hits.clone();
        let Some((url, server)) = test_server(
            Router::new()
                .route(
                    "/",
                    get(|| async { (StatusCode::FOUND, [(LOCATION, "/target")]) }),
                )
                .route(
                    "/target",
                    get(move || {
                        let target_hits = target_hits_for_route.clone();
                        async move {
                            target_hits.fetch_add(1, Ordering::SeqCst);
                            Json(json!({"redirected":{"ocr":50}}))
                        }
                    }),
                ),
        )
        .await
        else {
            return;
        };

        let response = ocr_profiles_fetch_with_policy(state, None, json!({"url": url}), true).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(target_hits.load(Ordering::SeqCst), 0);
        server.abort();
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_rejects_oversized_response() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        let Some((url, server)) =
            test_server(Router::new().route("/", get(|| async { "x".repeat(1_048_577) }))).await
        else {
            return;
        };

        let response = ocr_profiles_fetch_with_policy(state, None, json!({"url": url}), true).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(body_json(response).await["error"], "response_too_large");
        server.abort();
    }

    #[tokio::test]
    async fn ocr_profiles_fetch_rejects_loopback() {
        let root = tempfile::tempdir().unwrap();
        let response = ocr_profiles_fetch(
            State(test_state(&root).await),
            None,
            Some(Json(json!({"url":"http://127.0.0.1:8080/profiles.json"}))),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            body_json(response).await,
            json!({"ok":false,"error":"Blocked address"})
        );
    }

    #[tokio::test]
    async fn benchmark_cases_missing_root_returns_empty_list() {
        let root = tempfile::tempdir().unwrap();
        let response = benchmark_cases(test_state(&root).await, None).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(body_json(response).await, json!({"cases": [], "total": 0}));
    }

    #[tokio::test]
    async fn benchmark_cases_manifest_skips_missing_images_and_counts_characters() {
        let root = tempfile::tempdir().unwrap();
        let benchmarks = benchmark_dir(&root);
        std::fs::create_dir_all(&benchmarks).unwrap();
        std::fs::write(benchmarks.join("present.png"), []).unwrap();
        std::fs::write(
            benchmarks.join("manifest.json"),
            r#"{"cases":[{"image":"present.png","expected_text":"é漢","task":"custom","language":"ja","tags":["cjk"]},{"image":"missing.png"}]}"#,
        )
        .unwrap();

        let response = benchmark_cases(test_state(&root).await, None).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            body_json(response).await,
            json!({"cases":[{"image":"present.png","task":"custom","language":"ja","expected_length":2,"tags":["cjk"]}],"total":1})
        );
    }

    #[tokio::test]
    async fn benchmark_cases_auto_detect_skips_images_without_text() {
        let root = tempfile::tempdir().unwrap();
        let benchmarks = benchmark_dir(&root);
        std::fs::create_dir_all(&benchmarks).unwrap();
        std::fs::write(benchmarks.join("present.png"), []).unwrap();
        std::fs::write(benchmarks.join("present.txt"), " expected ").unwrap();
        std::fs::write(benchmarks.join("missing.jpg"), []).unwrap();

        let body = body_json(benchmark_cases(test_state(&root).await, None).await).await;
        assert_eq!(body["total"], 1);
        assert_eq!(body["cases"][0]["image"], "present.png");
        assert_eq!(body["cases"][0]["expected_length"], 8);
    }

    #[tokio::test]
    async fn benchmark_cases_auto_detect_infers_tasks() {
        let root = tempfile::tempdir().unwrap();
        let benchmarks = benchmark_dir(&root);
        std::fs::create_dir_all(&benchmarks).unwrap();
        for name in ["manga_1.png", "invoice_2.png", "plain_3.png"] {
            std::fs::write(benchmarks.join(name), []).unwrap();
            std::fs::write(benchmarks.join(name.replace(".png", ".txt")), "x").unwrap();
        }

        let body = body_json(benchmark_cases(test_state(&root).await, None).await).await;
        assert_eq!(
            body["cases"],
            json!([
                {"image":"invoice_2.png","task":"ocr_document","language":"auto","expected_length":1,"tags":[]},
                {"image":"manga_1.png","task":"ocr_manga","language":"auto","expected_length":1,"tags":[]},
                {"image":"plain_3.png","task":"ocr","language":"auto","expected_length":1,"tags":[]}
            ])
        );
    }

    #[cfg(unix)]
    #[tokio::test]
    async fn benchmark_cases_rejects_symlink_escape_and_invalid_paths() {
        use std::os::unix::fs::symlink;

        let root = tempfile::tempdir().unwrap();
        let benchmarks = benchmark_dir(&root);
        let outside = root.path().join("outside");
        std::fs::create_dir_all(&benchmarks).unwrap();
        std::fs::create_dir_all(&outside).unwrap();
        std::fs::write(outside.join("secret.png"), []).unwrap();
        symlink(outside.join("secret.png"), benchmarks.join("escape.png")).unwrap();
        std::fs::write(
            benchmarks.join("manifest.json"),
            format!(r#"{{"cases":[{{"image":"escape.png"}},{{"image":"{}"}},{{"image":"../outside/secret.png"}}]}}"#, outside.join("secret.png").display()),
        )
        .unwrap();

        let body = body_json(benchmark_cases(test_state(&root).await, None).await).await;
        assert_eq!(body, json!({"cases": [], "total": 0}));

        let response =
            benchmark_cases(test_state(&root).await, Some("../benchmarks".to_owned())).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    #[tokio::test]
    async fn benchmark_cases_rejects_directory_outside_benchmark_root() {
        let root = tempfile::tempdir().unwrap();
        let outside = root.path().join("outside");
        std::fs::create_dir_all(&outside).unwrap();
        let response = benchmark_cases(
            test_state(&root).await,
            Some(outside.to_string_lossy().into_owned()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
    }

    /// Returns the TempDir alongside the state: the caller must keep it bound,
    /// because the state holds paths into it. Leaking it with `mem::forget`
    /// would keep it alive at the cost of never cleaning it up.
    async fn seeded_export_state() -> (SharedState, tempfile::TempDir) {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        create_export_schema(&state).await;
        sqlx::query("INSERT INTO file_ocr_results(id, file_id, engine, task, regions_json, full_text, structured_json, language, created_at) VALUES (1, 1, 'test-engine', 'ocr', ?, ?, '{}', 'ja', 1)")
            .bind(r#"[{"region_id":1,"bbox":[1,2,3,4],"text":"First","confidence":0.9,"direction":"horizontal","label":""},{"region_id":2,"bbox":[],"text":"Second","confidence":0.8,"direction":"vertical","label":"note"}]"#)
            .bind("First\nSecond")
            .execute(&state.db)
            .await
            .unwrap();
        (state, root)
    }

    async fn create_export_schema(state: &SharedState) {
        sqlx::query("CREATE TABLE file_ocr_results (id INTEGER PRIMARY KEY, file_id INTEGER NOT NULL, engine TEXT NOT NULL, task TEXT NOT NULL, regions_json TEXT, full_text TEXT, structured_json TEXT, language TEXT, created_at INTEGER NOT NULL)")
            .execute(&state.db)
            .await
            .unwrap();
        sqlx::query("CREATE TABLE file_translations (id INTEGER PRIMARY KEY, ocr_result_id INTEGER NOT NULL, target_lang TEXT NOT NULL, translated_text TEXT, region_translations_json TEXT, created_at INTEGER NOT NULL)")
            .execute(&state.db)
            .await
            .unwrap();
    }

    #[tokio::test]
    async fn ocr_translate_missing_result_returns_404_without_ai_server() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        assert!(state
            .config
            .app_config
            .as_object()
            .is_some_and(|config| config.is_empty()));
        create_export_schema(&state).await;

        let response = ocr_translate(
            State(state),
            None,
            Path(99),
            Bytes::from_static(br#"{"target_lang":"en"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            body_json(response).await,
            json!({"ok": false, "error": "OCR result not found. Run OCR first."})
        );
    }

    #[tokio::test]
    async fn ocr_translate_rejects_explicit_empty_target_lang() {
        let root = tempfile::tempdir().unwrap();
        let response = ocr_translate(
            State(test_state(&root).await),
            None,
            Path(1),
            Bytes::from_static(br#"{"target_lang":""}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            body_json(response).await,
            json!({"ok": false, "error": "target_lang is required"})
        );
    }

    #[tokio::test]
    async fn ocr_translate_absent_body_defaults_to_en() -> Result<(), Box<dyn std::error::Error>> {
        let response = translate_missing_response(None).await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        Ok(())
    }

    #[tokio::test]
    async fn ocr_translate_empty_object_defaults_to_en() -> Result<(), Box<dyn std::error::Error>> {
        let response = translate_missing_response(Some("{}")).await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        Ok(())
    }

    #[tokio::test]
    async fn ocr_translate_empty_target_lang_returns_bad_request(
    ) -> Result<(), Box<dyn std::error::Error>> {
        let response = translate_missing_response(Some(r#"{"target_lang":""}"#)).await?;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        Ok(())
    }

    #[tokio::test]
    async fn ocr_translate_null_target_lang_returns_bad_request(
    ) -> Result<(), Box<dyn std::error::Error>> {
        let response = translate_missing_response(Some(r#"{"target_lang":null}"#)).await?;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        Ok(())
    }

    #[tokio::test]
    async fn ocr_translate_malformed_json_defaults_to_en() -> Result<(), Box<dyn std::error::Error>>
    {
        let response = translate_missing_response(Some("notjson")).await?;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        Ok(())
    }

    #[tokio::test]
    async fn ocr_translate_existing_result_reaches_translation_and_fails_without_server() {
        // Stage 4 replaced the 501 placeholder with a real implementation: an existing
        // OCR row is now found and handed to translate_ocr_result, which fails because
        // the test config has no AI servers configured, surfacing as a 500.
        let (state, _root) = seeded_export_state().await;
        assert!(state
            .config
            .app_config
            .as_object()
            .is_some_and(|config| config.is_empty()));
        let response = ocr_translate(State(state), None, Path(1), Bytes::new()).await;
        assert_eq!(response.status(), StatusCode::INTERNAL_SERVER_ERROR);
        assert_eq!(
            body_json(response).await,
            json!({"ok": false, "error": "Translation failed: Translation server not available: AI サーバーが登録されていません。"})
        );
    }

    #[tokio::test]
    async fn ocr_translate_task_mismatch_returns_not_found() {
        let (state, _root) = seeded_export_state().await;
        let response = ocr_translate(
            State(state),
            None,
            Path(1),
            Bytes::from_static(br#"{"target_lang":"en","task":"caption"}"#),
        )
        .await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            body_json(response).await,
            json!({"ok": false, "error": "OCR result not found. Run OCR first."})
        );
    }

    async fn export(
        state: SharedState,
        format: &str,
        include_translation: Option<&str>,
        target_lang: Option<&str>,
    ) -> Response {
        ocr_export(
            State(state),
            Path(1),
            Query(ExportParams {
                format: Some(format.to_owned()),
                task: None,
                include_translation: include_translation.map(str::to_owned),
                target_lang: target_lang.map(str::to_owned),
            }),
        )
        .await
    }

    async fn export_batch(state: SharedState, params: BatchExportParams) -> Response {
        ocr_export_batch(State(state), None, Json(params)).await
    }

    fn batch_params(file_ids: Vec<i64>, format: &str) -> BatchExportParams {
        BatchExportParams {
            file_ids,
            format: format.to_owned(),
            overlay_mode: default_overlay_mode(),
            ..Default::default()
        }
    }

    #[tokio::test]
    async fn ocr_export_batch_validates_format_before_file_ids() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        create_export_schema(&state).await;
        let response = export_batch(state, batch_params(Vec::new(), "csv")).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            body_json(response).await.get("error"),
            Some(&json!(
                "Invalid format: csv. Supported: txt, md, json, pdf, overlay"
            ))
        );
    }

    #[tokio::test]
    async fn ocr_export_batch_requires_file_ids() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        create_export_schema(&state).await;
        let response = export_batch(state, batch_params(Vec::new(), "md")).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            body_json(response).await.get("error"),
            Some(&json!("file_ids is required"))
        );
    }

    #[tokio::test]
    async fn ocr_export_batch_missing_results_is_not_found() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        create_export_schema(&state).await;
        let response = export_batch(state, batch_params(vec![99], "md")).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(
            body_json(response).await.get("error"),
            Some(&json!("No OCR results found for given file_ids"))
        );
    }

    #[tokio::test]
    async fn ocr_export_batch_writes_python_named_zip_members(
    ) -> Result<(), Box<dyn std::error::Error>> {
        use std::io::{Cursor, Read};

        let (state, _root) = seeded_export_state().await;
        let response = export_batch(state, batch_params(vec![1], "md")).await;
        assert_eq!(response.status(), StatusCode::OK);
        assert_eq!(
            response.headers().get(header::CONTENT_TYPE),
            Some(&HeaderValue::from_static("application/zip"))
        );
        assert_eq!(
            response.headers().get(header::CONTENT_DISPOSITION),
            Some(&HeaderValue::from_static(
                "attachment; filename=\"ocr_export_md.zip\""
            ))
        );
        let bytes = to_bytes(response.into_body(), usize::MAX).await?;
        let mut archive = zip::ZipArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.file_names().collect::<Vec<_>>(), vec!["ocr_1.md"]);
        let mut member = archive.by_name("ocr_1.md")?;
        let mut content = String::new();
        member.read_to_string(&mut content)?;
        assert_eq!(content, "First\nSecond\n");
        Ok(())
    }

    #[tokio::test]
    async fn ocr_export_batch_skips_missing_ids() -> Result<(), Box<dyn std::error::Error>> {
        use std::io::Cursor;

        let (state, _root) = seeded_export_state().await;
        let response = export_batch(state, batch_params(vec![99, 1], "txt")).await;
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = to_bytes(response.into_body(), usize::MAX).await?;
        let archive = zip::ZipArchive::new(Cursor::new(bytes))?;
        assert_eq!(archive.file_names().collect::<Vec<_>>(), vec!["ocr_1.txt"]);
        Ok(())
    }

    #[tokio::test]
    async fn ocr_export_batch_keeps_pdf_and_output_dir_unported() {
        let (state, _root) = seeded_export_state().await;
        let mut output_dir = batch_params(vec![1], "md");
        output_dir.output_dir = "/exports".to_owned();
        let output_response = export_batch(state.clone(), output_dir).await;
        assert_eq!(output_response.status(), StatusCode::NOT_IMPLEMENTED);
        assert!(body_json(output_response)
            .await
            .get("error")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|error| error.contains("server-side directory")));
        let pdf_response = export_batch(state, batch_params(vec![1], "pdf")).await;
        assert_eq!(pdf_response.status(), StatusCode::NOT_IMPLEMENTED);
        assert!(body_json(pdf_response)
            .await
            .get("error")
            .and_then(serde_json::Value::as_str)
            .is_some_and(|error| error.contains("PDF OCR export")));
    }

    #[test]
    fn ocr_export_batch_overlay_zip_members_are_png() -> Result<(), Box<dyn std::error::Error>> {
        use std::io::{Cursor, Read};

        let bytes = build_ocr_overlay_zip(vec![(
            b"\x89PNG\r\n\x1a\nrendered".to_vec(),
            "ocr_overlay_1.png".to_owned(),
        )])?;
        let mut archive = zip::ZipArchive::new(Cursor::new(bytes))?;
        assert_eq!(
            archive.file_names().collect::<Vec<_>>(),
            vec!["ocr_overlay_1.png"]
        );
        let mut member = archive.by_name("ocr_overlay_1.png")?;
        let mut magic = [0_u8; 8];
        member.read_exact(&mut magic)?;
        assert_eq!(magic, *b"\x89PNG\r\n\x1a\n");
        Ok(())
    }

    #[tokio::test]
    async fn ocr_export_batch_overlay_rejects_invalid_mode() {
        let (state, _root) = seeded_export_state().await;
        let mut params = batch_params(vec![1], "overlay");
        params.overlay_mode = "invalid".to_owned();
        let response = export_batch(state, params).await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_eq!(body_json(response).await["error"], "invalid_overlay_mode");
    }

    #[tokio::test]
    async fn ocr_export_batch_overlay_requires_font() {
        let (state, _root) = seeded_export_state().await;
        let response = export_batch(state, batch_params(vec![1], "overlay")).await;
        assert_eq!(response.status(), StatusCode::SERVICE_UNAVAILABLE);
        assert_eq!(body_json(response).await["error"], "overlay_font_missing");
    }

    fn overlay_test_font() -> Result<ab_glyph::FontArc, Box<dyn std::error::Error>> {
        Ok(ab_glyph::FontArc::try_from_vec(std::fs::read(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        )?)?)
    }

    #[tokio::test]
    async fn ocr_export_batch_overlay_skips_missing_ids() -> Result<(), Box<dyn std::error::Error>>
    {
        use std::io::Cursor;

        let (state, root) = seeded_export_state().await;
        let image_path = root.path().join("overlay.png");
        image::RgbaImage::new(1_000, 1_000).save(&image_path)?;
        sqlx::query("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL, is_deleted INTEGER NOT NULL)")
            .execute(&state.db)
            .await?;
        sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (1, ?, 0)")
            .bind(image_path.to_string_lossy().as_ref())
            .execute(&state.db)
            .await?;

        let results = batch_export_results(&state, &[1, 99]).await?;
        assert_eq!(
            results
                .iter()
                .map(|(file_id, _)| *file_id)
                .collect::<Vec<_>>(),
            [1]
        );
        let response = ocr_export_batch_overlay_zip(
            &state,
            results,
            &batch_params(vec![1, 99], "overlay"),
            crate::ocr::overlay::Mode::Original,
            crate::ocr::overlay::Format::Png,
            &overlay_test_font()?,
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let bytes = to_bytes(response.into_body(), usize::MAX).await?;
        let archive = zip::ZipArchive::new(Cursor::new(bytes))?;
        assert_eq!(
            archive.file_names().collect::<Vec<_>>(),
            ["ocr_overlay_1.png"]
        );
        Ok(())
    }

    #[tokio::test]
    async fn ocr_export_batch_overlay_too_large_aborts_archive(
    ) -> Result<(), Box<dyn std::error::Error>> {
        let (state, root) = seeded_export_state().await;
        let image_path = root.path().join("overlay.png");
        image::RgbaImage::new(1, 1).save(&image_path)?;
        sqlx::query("CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT NOT NULL, is_deleted INTEGER NOT NULL)")
            .execute(&state.db)
            .await?;
        for file_id in [1, 2] {
            sqlx::query("INSERT INTO files (id, path, is_deleted) VALUES (?, ?, 0)")
                .bind(file_id)
                .bind(image_path.to_string_lossy().as_ref())
                .execute(&state.db)
                .await?;
        }
        let regions: Vec<_> = (0..1_001)
            .map(|region_id| json!({"region_id": region_id, "bbox": [], "text": "", "confidence": 1.0, "direction": "horizontal", "label": ""}))
            .collect();
        let response = ocr_export_batch_overlay_zip(
            &state,
            vec![
                (1, json!({"regions": [], "full_text": ""})),
                (2, json!({"regions": regions, "full_text": ""})),
            ],
            &batch_params(vec![1, 2], "overlay"),
            crate::ocr::overlay::Mode::Original,
            crate::ocr::overlay::Format::Png,
            &overlay_test_font()?,
        )
        .await;
        assert_eq!(response.status(), StatusCode::BAD_REQUEST);
        assert_ne!(
            response.headers().get(header::CONTENT_TYPE),
            Some(&HeaderValue::from_static("application/zip"))
        );
        assert_eq!(body_json(response).await["error"], "overlay_too_large");
        Ok(())
    }

    #[tokio::test]
    async fn ocr_export_batch_includes_translations() -> Result<(), Box<dyn std::error::Error>> {
        use std::io::{Cursor, Read};

        let (state, _root) = seeded_export_state().await;
        sqlx::query("INSERT INTO file_translations(ocr_result_id, target_lang, translated_text, region_translations_json, created_at) VALUES (1, 'en', 'Entire translation', ?, 2)")
            .bind(r#"[{"region_id":1,"translated":"Translated first"}]"#)
            .execute(&state.db)
            .await?;
        let plain = export_batch(state.clone(), batch_params(vec![1], "txt")).await;
        let mut translated_params = batch_params(vec![1], "txt");
        translated_params.include_translation = true;
        translated_params.target_lang = "en".to_owned();
        let translated = export_batch(state, translated_params).await;
        let plain_bytes = to_bytes(plain.into_body(), usize::MAX).await?;
        let translated_bytes = to_bytes(translated.into_body(), usize::MAX).await?;
        let mut plain_archive = zip::ZipArchive::new(Cursor::new(plain_bytes))?;
        let mut translated_archive = zip::ZipArchive::new(Cursor::new(translated_bytes))?;
        let mut plain_member = plain_archive.by_name("ocr_1.txt")?;
        let mut translated_member = translated_archive.by_name("ocr_1_en.txt")?;
        let mut plain_content = String::new();
        let mut translated_content = String::new();
        plain_member.read_to_string(&mut plain_content)?;
        translated_member.read_to_string(&mut translated_content)?;
        assert_ne!(plain_content, translated_content);
        assert_eq!(translated_content, "First\n>> Translated first\n\nSecond\n");
        Ok(())
    }

    #[tokio::test]
    async fn ocr_export_rejects_unknown_format_and_pdf() {
        let (state, _root) = seeded_export_state().await;
        let invalid = export(state.clone(), "csv", None, None).await;
        assert_eq!(invalid.status(), StatusCode::BAD_REQUEST);
        assert_eq!(
            body_json(invalid).await["error"],
            "Invalid format: csv. Supported: txt, md, json, pdf"
        );
        let pdf = export(state, "pdf", None, None).await;
        assert_eq!(pdf.status(), StatusCode::NOT_IMPLEMENTED);
        assert!(body_json(pdf).await["error"]
            .as_str()
            .unwrap()
            .contains("PDF OCR export"));
    }

    #[tokio::test]
    async fn ocr_export_missing_file_is_not_found() {
        let root = tempfile::tempdir().unwrap();
        let state = test_state(&root).await;
        create_export_schema(&state).await;
        let response = ocr_export(State(state), Path(99), Query(ExportParams::default())).await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        assert_eq!(body_json(response).await["error"], "OCR result not found");
    }

    #[tokio::test]
    async fn ocr_export_writes_python_txt_md_and_json_bodies() {
        let (state, _root) = seeded_export_state().await;
        let txt = export(state.clone(), "txt", None, None).await;
        assert_eq!(
            to_bytes(txt.into_body(), usize::MAX).await.unwrap(),
            "First\nSecond\n"
        );
        let md = export(state.clone(), "md", None, None).await;
        assert_eq!(
            to_bytes(md.into_body(), usize::MAX).await.unwrap(),
            "First\nSecond\n"
        );
        let json = export(state, "json", None, None).await;
        assert_eq!(
            to_bytes(json.into_body(), usize::MAX).await.unwrap(),
            br#"{
  "file_id": 1,
  "engine": "test-engine",
  "task": "ocr",
  "regions": [
    {
      "region_id": 1,
      "bbox": [
        1,
        2,
        3,
        4
      ],
      "text": "First",
      "confidence": 0.9,
      "direction": "horizontal",
      "label": ""
    },
    {
      "region_id": 2,
      "bbox": [],
      "text": "Second",
      "confidence": 0.8,
      "direction": "vertical",
      "label": "note"
    }
  ],
  "full_text": "First\nSecond",
  "language": "ja"
}"#
            .as_slice()
        );
    }

    #[tokio::test]
    async fn ocr_export_sets_filename_and_includes_translations() {
        let (state, _root) = seeded_export_state().await;
        sqlx::query("INSERT INTO file_translations(ocr_result_id, target_lang, translated_text, region_translations_json, created_at) VALUES (1, '日本', 'Entire translation', ?, 2)")
            .bind(r#"[{"region_id":1,"translated":"Translated first"}]"#)
            .execute(&state.db)
            .await
            .unwrap();
        let plain = export(state.clone(), "txt", None, None).await;
        let translated = export(state, "txt", Some("1"), Some("日本")).await;
        assert_eq!(
            plain.headers()[header::CONTENT_DISPOSITION],
            "attachment; filename=\"ocr_1.txt\""
        );
        assert_eq!(
            translated.headers()[header::CONTENT_DISPOSITION],
            "attachment; filename*=UTF-8''ocr_1_%E6%97%A5%E6%9C%AC.txt"
        );
        assert_eq!(
            to_bytes(translated.into_body(), usize::MAX).await.unwrap(),
            "First\n>> Translated first\n\nSecond\n"
        );
    }
}
