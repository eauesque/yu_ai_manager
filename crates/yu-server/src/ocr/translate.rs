use std::time::{SystemTime, UNIX_EPOCH};

use serde_json::{json, Value};

use super::{
    overlay_layout::maybe_reparse_jsonl_regions,
    parsers::OcrRegion,
    translate_llm::call_llm,
    translate_parse::{clean_jsonl_text, parse_numbered_response},
    translate_resolve::resolve_active_server,
};

#[derive(Debug, Clone, PartialEq)]
pub struct TranslationResult {
    pub translated_text: String,
    pub target_lang: String,
    pub engine: String,
    pub region_translations: Vec<Value>,
}

pub async fn translate_ocr_result(
    full_text: &str,
    language: &str,
    regions: Vec<OcrRegion>,
    task: &str,
    target_lang: &str,
    server_id: Option<&str>,
    config: &Value,
    project_root: &std::path::Path,
    infer_client: Option<&crate::infer_client::InferClient>,
) -> Result<TranslationResult, String> {
    let source_lang = if language.is_empty() {
        "auto"
    } else {
        language
    };
    let clean_text = clean_jsonl_text(full_text);
    let text = if clean_text.is_empty() {
        full_text
    } else {
        &clean_text
    };
    let is_manga = task == "ocr_manga";
    let mut result = translate_text(
        text,
        source_lang,
        target_lang,
        server_id,
        is_manga,
        config,
        project_root,
        infer_client,
    )
    .await?;
    if !regions.is_empty() {
        result.region_translations = translate_regions_batch(
            maybe_reparse_jsonl_regions(regions),
            source_lang,
            target_lang,
            server_id,
            config,
            project_root,
            infer_client,
        )
        .await;
    }
    Ok(result)
}

async fn translate_text(
    text: &str,
    source_lang: &str,
    target_lang: &str,
    server_id: Option<&str>,
    is_manga: bool,
    config: &Value,
    project_root: &std::path::Path,
    infer_client: Option<&crate::infer_client::InferClient>,
) -> Result<TranslationResult, String> {
    if text.trim().is_empty() {
        return Ok(result("", target_lang, ""));
    }
    if source_lang == target_lang {
        return Ok(result(text, target_lang, ""));
    }
    let resolution = resolve_active_server(config, project_root, server_id).await;
    let Some(engine_type) = resolution.engine_type else {
        return Err(format!(
            "Translation server not available: {}",
            resolution.error.unwrap_or_default()
        ));
    };
    let translated = call_llm(
        &engine_type,
        &resolution.kwargs.unwrap_or_default(),
        &translation_prompt(text, source_lang, target_lang, is_manga),
        infer_client,
    )
    .await
    .map_err(|error| error.to_string())?;
    Ok(result(
        &translated,
        target_lang,
        &engine_name(config, server_id),
    ))
}

async fn translate_regions_batch(
    regions: Vec<OcrRegion>,
    source_lang: &str,
    target_lang: &str,
    server_id: Option<&str>,
    config: &Value,
    project_root: &std::path::Path,
    infer_client: Option<&crate::infer_client::InferClient>,
) -> Vec<Value> {
    let valid: Vec<_> = regions
        .into_iter()
        .filter(|region| !region.text.trim().is_empty())
        .collect();
    if valid.is_empty() {
        return Vec::new();
    }
    let numbered = valid
        .iter()
        .map(|region| format!("[{}] {}", region.region_id, region.text))
        .collect::<Vec<_>>()
        .join("\n");
    let resolution = resolve_active_server(config, project_root, server_id).await;
    let (Some(engine_type), Some(kwargs)) = (resolution.engine_type, resolution.kwargs) else {
        tracing::warn!("Region batch translation server unavailable");
        return Vec::new();
    };
    let prompt = format!(
        "Translate each numbered line from {} to {}. Keep the [number] prefix. Return ONLY the translated lines.\n\n{}",
        language_name(source_lang), language_name(target_lang), numbered
    );
    let Ok(raw) = call_llm(&engine_type, &kwargs, &prompt, infer_client).await else {
        tracing::warn!("Region batch translation failed");
        return Vec::new();
    };
    let translated = parse_numbered_response(&raw);
    valid
        .into_iter()
        .map(|region| json!({
            "region_id": region.region_id,
            "original": region.text,
            "translated": translated.get(&(region.region_id as u64)).cloned().unwrap_or_default(),
            "label": region.label,
        }))
        .collect()
}

pub fn engine_name(config: &Value, server_id: Option<&str>) -> String {
    if let Some(server_id) = server_id.filter(|id| !id.is_empty()) {
        return server_id.to_owned();
    }
    let servers = config
        .get("ai_servers")
        .and_then(Value::as_array)
        .cloned()
        .unwrap_or_default();
    let active_id = config
        .get("ai_servers_active")
        .and_then(Value::as_str)
        .unwrap_or_default();
    // Python derives this independently of the resolved fallback server; preserve that divergence.
    servers
        .iter()
        .find(|server| server.get("id").and_then(Value::as_str) == Some(active_id))
        .and_then(|server| server.get("name"))
        .and_then(Value::as_str)
        .or_else(|| {
            servers
                .first()
                .and_then(|server| server.get("name"))
                .and_then(Value::as_str)
        })
        .unwrap_or("unknown")
        .to_owned()
}

pub async fn save_translation(
    db: &sqlx::SqlitePool,
    ocr_result_id: i64,
    result: &TranslationResult,
) -> Result<(), sqlx::Error> {
    let regions = if result.region_translations.is_empty() {
        None
    } else {
        Some(serde_json::to_string(&result.region_translations).unwrap_or_default())
    };
    let created_at = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs() as i64;
    sqlx::query("INSERT INTO file_translations (ocr_result_id, target_lang, translated_text, region_translations_json, engine, created_at) VALUES (?, ?, ?, ?, ?, ?) ON CONFLICT(ocr_result_id, target_lang) DO UPDATE SET translated_text=excluded.translated_text, region_translations_json=excluded.region_translations_json, engine=excluded.engine, created_at=excluded.created_at")
        .bind(ocr_result_id).bind(&result.target_lang).bind(&result.translated_text).bind(regions).bind(&result.engine).bind(created_at)
        .execute(db).await?;
    Ok(())
}

fn result(translated_text: &str, target_lang: &str, engine: &str) -> TranslationResult {
    TranslationResult {
        translated_text: translated_text.to_owned(),
        target_lang: target_lang.to_owned(),
        engine: engine.to_owned(),
        region_translations: Vec::new(),
    }
}

fn language_name(language: &str) -> &str {
    match language {
        "ja" => "Japanese",
        "en" => "English",
        "zh" => "Chinese",
        "ko" => "Korean",
        "fr" => "French",
        "de" => "German",
        "es" => "Spanish",
        "pt" => "Portuguese",
        "ru" => "Russian",
        "ar" => "Arabic",
        _ => language,
    }
}

fn translation_prompt(text: &str, source: &str, target: &str, manga: bool) -> String {
    let prefix = if manga {
        format!("Translate the following manga/comic dialogue from {} to {}. Preserve the tone, character voice, and emotional nuance. For sound effects (SFX), provide both a translation and the original. Return ONLY the translated text, no explanations.", language_name(source), language_name(target))
    } else {
        format!("Translate the following text from {} to {}. Return ONLY the translated text, no explanations or notes.", language_name(source), language_name(target))
    };
    format!("{prefix}\n\n{text}")
}

#[cfg(test)]
mod tests {
    use std::str::FromStr;

    use serde_json::json;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use sqlx::Row;

    use super::*;

    fn empty_config() -> Value {
        json!({})
    }

    async fn memory_pool() -> sqlx::SqlitePool {
        SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap()
    }

    async fn translations_pool() -> sqlx::SqlitePool {
        let pool = memory_pool().await;
        sqlx::query(
            "CREATE TABLE file_translations (
                id INTEGER PRIMARY KEY,
                ocr_result_id INTEGER NOT NULL,
                target_lang TEXT NOT NULL,
                translated_text TEXT,
                region_translations_json TEXT,
                engine TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                UNIQUE(ocr_result_id, target_lang)
            )",
        )
        .execute(&pool)
        .await
        .unwrap();
        pool
    }

    // --- translate_text short circuits ---

    #[tokio::test]
    async fn translate_text_empty_input_short_circuits_with_empty_engine() {
        let root = std::path::Path::new(".");
        let translated =
            translate_text("   ", "ja", "en", None, false, &empty_config(), root, None)
                .await
                .unwrap();
        assert_eq!(translated.translated_text, "");
        assert_eq!(translated.target_lang, "en");
        assert_eq!(translated.engine, "");
        assert!(translated.region_translations.is_empty());
    }

    #[tokio::test]
    async fn translate_text_same_language_short_circuits_without_llm_call() {
        let root = std::path::Path::new(".");
        // config has no servers at all, so falling through to resolve_active_server
        // would error out; a successful Ok here proves the short circuit fired
        // before any server resolution/LLM call was attempted.
        let translated = translate_text(
            "hello world",
            "en",
            "en",
            None,
            false,
            &empty_config(),
            root,
            None,
        )
        .await
        .unwrap();
        assert_eq!(translated.translated_text, "hello world");
        assert_eq!(translated.target_lang, "en");
        assert_eq!(translated.engine, "");
    }

    #[tokio::test]
    async fn translate_text_resolution_failure_propagates_as_error() {
        let root = std::path::Path::new(".");
        let error = translate_text(
            "hello world",
            "ja",
            "en",
            None,
            false,
            &empty_config(),
            root,
            None,
        )
        .await
        .unwrap_err();
        assert!(error.contains("Translation server not available"));
    }

    // --- failure asymmetry: full-text path errors, region batch swallows ---

    #[tokio::test]
    async fn translate_regions_batch_swallows_resolution_failure_into_empty_vec() {
        let root = std::path::Path::new(".");
        let regions = vec![OcrRegion {
            region_id: 1,
            bbox: vec![],
            text: "hello".to_owned(),
            confidence: 0.9,
            direction: "horizontal".to_owned(),
            label: String::new(),
        }];
        let translated =
            translate_regions_batch(regions, "ja", "en", None, &empty_config(), root, None).await;
        assert!(translated.is_empty());
    }

    #[tokio::test]
    async fn translate_ocr_result_auto_target_hits_same_language_short_circuit() {
        let root = std::path::Path::new(".");
        // language="" -> source_lang defaults to "auto"; target_lang="auto" too,
        // so this must hit the same-language short circuit rather than erroring
        // out on server resolution.
        let result = translate_ocr_result(
            "plain text",
            "",
            Vec::new(),
            "ocr",
            "auto",
            None,
            &empty_config(),
            root,
            None,
        )
        .await
        .unwrap();
        assert_eq!(result.translated_text, "plain text");
        assert_eq!(result.engine, "");
    }

    // --- engine_name: four outcomes ---

    #[test]
    fn engine_name_prefers_explicit_non_empty_server_id() {
        let config = json!({"ai_servers": [{"id": "s1", "name": "Server One"}]});
        assert_eq!(engine_name(&config, Some("explicit-id")), "explicit-id");
    }

    #[test]
    fn engine_name_ignores_empty_server_id_and_matches_active() {
        let config = json!({
            "ai_servers": [
                {"id": "s1", "name": "Server One"},
                {"id": "s2", "name": "Server Two"}
            ],
            "ai_servers_active": "s2"
        });
        assert_eq!(engine_name(&config, Some("")), "Server Two");
    }

    #[test]
    fn engine_name_falls_back_to_first_server_when_active_does_not_match() {
        let config = json!({
            "ai_servers": [
                {"id": "s1", "name": "Server One"},
                {"id": "s2", "name": "Server Two"}
            ],
            "ai_servers_active": "does-not-exist"
        });
        // The name is derived independently of which server actually resolved;
        // it falls back to the first configured server even though that server
        // was never the one contacted.
        assert_eq!(engine_name(&config, None), "Server One");
    }

    #[test]
    fn engine_name_unknown_when_no_servers_configured() {
        assert_eq!(engine_name(&empty_config(), None), "unknown");
    }

    // --- save_translation ---

    #[tokio::test]
    async fn save_translation_stores_null_region_json_when_regions_empty() {
        let pool = translations_pool().await;
        let result = TranslationResult {
            translated_text: "hi".to_owned(),
            target_lang: "en".to_owned(),
            engine: "test-engine".to_owned(),
            region_translations: Vec::new(),
        };
        save_translation(&pool, 1, &result).await.unwrap();

        let row = sqlx::query("SELECT region_translations_json, created_at FROM file_translations WHERE ocr_result_id=1 AND target_lang='en'")
            .fetch_one(&pool)
            .await
            .unwrap();
        let region_json: Option<String> = row.try_get("region_translations_json").unwrap();
        assert_eq!(region_json, None);
        let created_at: i64 = row.try_get("created_at").unwrap();
        let now = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_secs() as i64;
        assert!(
            (now - created_at).abs() < 60,
            "created_at should be unix seconds close to now"
        );
    }

    #[tokio::test]
    async fn save_translation_upserts_on_ocr_result_id_and_target_lang() {
        let pool = translations_pool().await;
        let first = TranslationResult {
            translated_text: "first".to_owned(),
            target_lang: "en".to_owned(),
            engine: "engine-a".to_owned(),
            region_translations: Vec::new(),
        };
        save_translation(&pool, 1, &first).await.unwrap();

        let second = TranslationResult {
            translated_text: "second".to_owned(),
            target_lang: "en".to_owned(),
            engine: "engine-b".to_owned(),
            region_translations: vec![json!({"region_id": 1, "translated": "x"})],
        };
        save_translation(&pool, 1, &second).await.unwrap();

        let rows = sqlx::query("SELECT translated_text, engine, region_translations_json FROM file_translations WHERE ocr_result_id=1 AND target_lang='en'")
            .fetch_all(&pool)
            .await
            .unwrap();
        assert_eq!(rows.len(), 1, "second write must replace, not duplicate");
        let translated_text: String = rows[0].try_get("translated_text").unwrap();
        let engine: String = rows[0].try_get("engine").unwrap();
        let region_json: Option<String> = rows[0].try_get("region_translations_json").unwrap();
        assert_eq!(translated_text, "second");
        assert_eq!(engine, "engine-b");
        assert!(region_json.is_some());
    }

    // --- pure helpers ---

    #[test]
    fn language_name_maps_known_codes_and_passes_through_unknown() {
        assert_eq!(language_name("ja"), "Japanese");
        assert_eq!(language_name("xx"), "xx");
    }

    #[test]
    fn translation_prompt_includes_manga_specific_instructions() {
        let manga_prompt = translation_prompt("text", "ja", "en", true);
        assert!(manga_prompt.contains("manga/comic"));
        let plain_prompt = translation_prompt("text", "ja", "en", false);
        assert!(!plain_prompt.contains("manga/comic"));
    }
}
