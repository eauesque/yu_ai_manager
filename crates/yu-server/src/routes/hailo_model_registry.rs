//! Hailo GenAI model manifest registry: parses `MODELS.rst`, resolves the
//! GenAI model name -> HEF file -> download URL registry, with a
//! remote-fetch -> local-cache -> bundled-fallback chain.
//!
//! Faithful Rust port of the Python reference implementation:
//! - `extensions/builtin_hailo_genai/core_impl/genai_types.py`
//! - `extensions/builtin_hailo_genai/core_impl/model_manifest_parse.py`
//! - `extensions/builtin_hailo_genai/core_impl/model_registry.py`
//! - the manifest fetch/cache helpers duplicated in `model_download.py` /
//!   `model_manifest_cache.py` (unified here into a single implementation).

use std::collections::HashMap;
use std::path::PathBuf;
use std::sync::OnceLock;
use std::time::Duration;

use regex::Regex;

/// HailoRT / hailo_model_zoo_genai version this server targets.
pub(crate) const HAILORT_VERSION: &str = "5.3.0";

const USER_AGENT: &str = "YU-AI-Manager/2.56 (Hailo GenAI Download)";

const MODELS_RST_URL_TEMPLATES: &[&str] = &[
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/v{version}/docs/MODELS.rst",
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/{version}/docs/MODELS.rst",
    "https://raw.githubusercontent.com/hailo-ai/hailo_model_zoo_genai/main/docs/MODELS.rst",
];

/// Section-underline characters recognized by reStructuredText.
const SECTION_UNDERLINE_CHARS: &[char] = &['=', '-', '~'];

/// Sections whose rows should never enter the registry (image/vision
/// encoder-only sections don't correspond to standalone downloadable LLM/VLM
/// models).
const SKIP_SECTION_KEYWORDS: &[&str] = &["image encoders only", "vision encoders only"];

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub(crate) enum GenAiModelType {
    Llm,
    Vlm,
    Speech2Text,
}

impl GenAiModelType {
    /// Matches Python's `GenAIModelType.value`.
    pub(crate) fn as_str(&self) -> &'static str {
        match self {
            GenAiModelType::Llm => "llm",
            GenAiModelType::Vlm => "vlm",
            GenAiModelType::Speech2Text => "s2t",
        }
    }
}

#[derive(Debug, Clone)]
pub(crate) struct GenAiModelInfo {
    pub(crate) name: String,
    pub(crate) model_type: GenAiModelType,
    pub(crate) hef_filename: String,
    pub(crate) description: String,
    pub(crate) url: String,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub(crate) struct ParsedModel {
    pub(crate) section: String,
    pub(crate) hef_filename: String,
    pub(crate) url: String,
}

/// `hef_filename -> (name, description)` overrides. Not every bundled
/// filename has an override (e.g. `Whisper-Tiny.hef` intentionally falls
/// through to `auto_name`/`auto_description`).
const MODEL_OVERRIDES: &[(&str, &str, &str)] = &[
    (
        "Qwen2.5-1.5B-Instruct.hef",
        "qwen2.5-1.5b-chat",
        "Qwen 2.5 1.5B Chat (general purpose)",
    ),
    (
        "Llama3.2-1B-Instruct.hef",
        "llama3.2-1b",
        "Llama 3.2 1B Instruct",
    ),
    (
        "DeepSeek-R1-Distill-Qwen-1.5B.hef",
        "deepseek-r1-1.5b",
        "DeepSeek R1 1.5B (reasoning)",
    ),
    (
        "Qwen2.5-Coder-1.5B-Instruct.hef",
        "qwen2.5-coder-1.5b",
        "Qwen 2.5 Coder 1.5B (code generation)",
    ),
    (
        "Qwen3-1.7B-Instruct.hef",
        "qwen3-1.7b-instruct",
        "Qwen 3 1.7B Instruct (general purpose, default)",
    ),
    (
        "Qwen3-VL-2B-Instruct.hef",
        "qwen3-vl-2b-instruct",
        "Qwen3 VL 2B (image/video understanding)",
    ),
    (
        "Qwen2-VL-2B-Instruct.hef",
        "qwen2-vl-2b-instruct",
        "Qwen2 VL 2B (image/video understanding)",
    ),
    (
        "Whisper-Base.hef",
        "whisper-base",
        "Whisper Base (fast, English-optimised)",
    ),
    (
        "Whisper-Small.hef",
        "whisper-small",
        "Whisper Small (better accuracy)",
    ),
];

/// `(section, hef_filename, url)` — bundled fallback rows, used only when
/// both the remote manifest fetch and the local cache are unavailable.
const BUNDLED_ROWS: &[(&str, &str, &str)] = &[
    (
        "Language Models",
        "DeepSeek-R1-Distill-Qwen-1.5B.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/DeepSeek-R1-Distill-Qwen-1.5B.hef",
    ),
    (
        "Language Models",
        "Llama3.2-1B-Instruct.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Llama3.2-1B-Instruct.hef",
    ),
    (
        "Language Models",
        "Qwen2.5-1.5B-Instruct.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Qwen2.5-1.5B-Instruct.hef",
    ),
    (
        "Language Models",
        "Qwen2.5-Coder-1.5B-Instruct.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Qwen2.5-Coder-1.5B-Instruct.hef",
    ),
    (
        "Language Models",
        "Qwen3-1.7B-Instruct.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Qwen3-1.7B-Instruct.hef",
    ),
    (
        "Multimodal Vision-Language Models",
        "Qwen2-VL-2B-Instruct.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Qwen2-VL-2B-Instruct.hef",
    ),
    (
        "Multimodal Vision-Language Models",
        "Qwen3-VL-2B-Instruct.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Qwen3-VL-2B-Instruct.hef",
    ),
    (
        "Speech Recognition (Whisper)",
        "Whisper-Tiny.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Whisper-Tiny.hef",
    ),
    (
        "Speech Recognition (Whisper)",
        "Whisper-Base.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Whisper-Base.hef",
    ),
    (
        "Speech Recognition (Whisper)",
        "Whisper-Small.hef",
        "https://dev-public.hailo.ai/v5.3.0/blob/Whisper-Small.hef",
    ),
];

fn hef_url_regex() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| {
        Regex::new(r#"https?://[^\s)>"']+?\.hef[^\s)>"']*"#).expect("static HEF URL regex is valid")
    })
}

fn should_skip_section(name: &str) -> bool {
    let lowered = name.to_lowercase();
    SKIP_SECTION_KEYWORDS.iter().any(|kw| lowered.contains(kw))
}

/// Faithful port of `model_manifest_parse.parse_models_rst`.
pub(crate) fn parse_models_rst(text: &str) -> Vec<ParsedModel> {
    let lines: Vec<&str> = text.lines().collect();
    let mut rows = Vec::new();
    let mut current_section = String::new();
    let mut skip_current = false;
    let hef_re = hef_url_regex();

    for i in 0..lines.len() {
        let stripped = lines[i].trim();
        let is_underline = {
            let unique_chars: std::collections::HashSet<char> = stripped.chars().collect();
            !stripped.is_empty()
                && unique_chars.len() == 1
                && SECTION_UNDERLINE_CHARS.contains(&stripped.chars().next().unwrap())
                && i > 0
                && !lines[i - 1].trim().is_empty()
                && stripped.len() >= lines[i - 1].trim().len()
        };

        if is_underline {
            current_section = lines[i - 1].trim().to_string();
            skip_current = should_skip_section(&current_section);
            continue;
        }

        if skip_current || current_section.is_empty() {
            continue;
        }

        if let Some(m) = hef_re.find(lines[i]) {
            let url = m.as_str().to_string();
            let hef_filename = url.rsplit('/').next().unwrap_or(&url).to_string();
            rows.push(ParsedModel {
                section: current_section.clone(),
                hef_filename,
                url,
            });
        }
    }

    rows
}

fn classify_by_filename(filename: &str) -> GenAiModelType {
    if filename.starts_with("Whisper-") {
        GenAiModelType::Speech2Text
    } else if filename.contains("-VL-") {
        GenAiModelType::Vlm
    } else {
        GenAiModelType::Llm
    }
}

fn auto_name(filename: &str) -> String {
    filename
        .strip_suffix(".hef")
        .unwrap_or(filename)
        .to_lowercase()
}

fn auto_description(filename: &str) -> String {
    filename
        .strip_suffix(".hef")
        .unwrap_or(filename)
        .replace('-', " ")
}

pub(crate) fn rows_to_registry(rows: &[ParsedModel]) -> HashMap<String, GenAiModelInfo> {
    let mut registry = HashMap::new();
    for row in rows {
        let filename = row.hef_filename.as_str();
        let override_entry = MODEL_OVERRIDES.iter().find(|(f, _, _)| *f == filename);
        let name = override_entry
            .map(|(_, n, _)| n.to_string())
            .unwrap_or_else(|| auto_name(filename));
        let description = override_entry
            .map(|(_, _, d)| d.to_string())
            .unwrap_or_else(|| auto_description(filename));
        let model_type = classify_by_filename(filename);
        registry.insert(
            name.clone(),
            GenAiModelInfo {
                name,
                model_type,
                hef_filename: row.hef_filename.clone(),
                description,
                url: row.url.clone(),
            },
        );
    }
    registry
}

fn bundled_parsed_models() -> Vec<ParsedModel> {
    BUNDLED_ROWS
        .iter()
        .map(|(section, hef_filename, url)| ParsedModel {
            section: section.to_string(),
            hef_filename: hef_filename.to_string(),
            url: url.to_string(),
        })
        .collect()
}

fn cache_dir() -> PathBuf {
    std::env::var_os("HOME")
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."))
        .join(".cache")
        .join("yu_ai_manager")
}

fn cache_path(version: &str) -> PathBuf {
    cache_dir().join(format!("hailo_models_{version}.json"))
}

/// Best-effort cache write: logs a warning and returns on any I/O/serde
/// error, never panics or propagates.
fn save_cached_manifest(version: &str, rows: &[ParsedModel]) {
    let path = cache_path(version);
    if let Some(parent) = path.parent() {
        if let Err(e) = std::fs::create_dir_all(parent) {
            tracing::warn!(error = %e, "Failed to create hailo genai manifest cache dir");
            return;
        }
    }

    let payload = serde_json::json!({
        "version": version,
        "rows": rows
            .iter()
            .map(|r| serde_json::json!({
                "section": r.section,
                "hef_filename": r.hef_filename,
                "url": r.url,
            }))
            .collect::<Vec<_>>(),
    });

    match serde_json::to_string(&payload) {
        Ok(text) => {
            if let Err(e) = std::fs::write(&path, text) {
                tracing::warn!(error = %e, path = %path.display(), "Failed to write hailo genai manifest cache");
            }
        }
        Err(e) => {
            tracing::warn!(error = %e, "Failed to serialize hailo genai manifest cache");
        }
    }
}

/// Returns `None` if the cache is missing, unreadable, malformed, or was
/// written for a different version — matching Python's None-on-any-error
/// semantics.
fn load_cached_manifest(version: &str) -> Option<Vec<ParsedModel>> {
    let path = cache_path(version);
    let text = std::fs::read_to_string(&path).ok()?;
    let payload: serde_json::Value = serde_json::from_str(&text).ok()?;
    if payload.get("version")?.as_str()? != version {
        return None;
    }
    let rows = payload.get("rows")?.as_array()?;
    let parsed: Vec<ParsedModel> = rows
        .iter()
        .filter_map(|r| {
            Some(ParsedModel {
                section: r.get("section")?.as_str()?.to_string(),
                hef_filename: r.get("hef_filename")?.as_str()?.to_string(),
                url: r.get("url")?.as_str()?.to_string(),
            })
        })
        .collect();
    Some(parsed)
}

/// Tries each `MODELS_RST_URL_TEMPLATES` entry in order; returns the first
/// successful response body, or `None` if all fail. Never propagates errors.
pub(crate) async fn fetch_remote_manifest(version: &str, timeout: Duration) -> Option<String> {
    fetch_remote_manifest_from_templates(version, timeout, MODELS_RST_URL_TEMPLATES).await
}

/// Same as [`fetch_remote_manifest`] but with an injectable template list,
/// so tests can point at an unreachable local address instead of the real
/// `raw.githubusercontent.com` host.
async fn fetch_remote_manifest_from_templates(
    version: &str,
    timeout: Duration,
    templates: &[&str],
) -> Option<String> {
    let client = reqwest::Client::builder()
        .timeout(timeout)
        .redirect(reqwest::redirect::Policy::limited(5))
        .build()
        .ok()?;

    for template in templates {
        let url = template.replace("{version}", version);
        let resp = match client
            .get(&url)
            .header(reqwest::header::USER_AGENT, USER_AGENT)
            .send()
            .await
        {
            Ok(resp) if resp.status().is_success() => resp,
            _ => continue,
        };
        if let Ok(text) = resp.text().await {
            return Some(text);
        }
    }
    None
}

/// Remote fetch -> cache write -> cached load -> bundled fallback chain.
/// Faithful port of `model_registry.build_models_registry`.
pub(crate) async fn build_models_registry(version: &str) -> HashMap<String, GenAiModelInfo> {
    if let Some(text) = fetch_remote_manifest(version, Duration::from_secs(5)).await {
        let rows = parse_models_rst(&text);
        if !rows.is_empty() {
            let registry = rows_to_registry(&rows);
            if !registry.is_empty() {
                save_cached_manifest(version, &rows);
                return registry;
            }
        }
    }

    if let Some(cached) = load_cached_manifest(version) {
        let registry = rows_to_registry(&cached);
        if !registry.is_empty() {
            return registry;
        }
    }

    tracing::info!(
        version,
        "Using bundled Hailo GenAI model registry; remote fetch and cache both unavailable"
    );
    rows_to_registry(&bundled_parsed_models())
}

/// Same as [`build_models_registry`] but with an injectable template list
/// and timeout, for offline-safe testing.
#[cfg(test)]
async fn build_models_registry_from_templates(
    version: &str,
    templates: &[&str],
    timeout: Duration,
) -> HashMap<String, GenAiModelInfo> {
    if let Some(text) = fetch_remote_manifest_from_templates(version, timeout, templates).await {
        let rows = parse_models_rst(&text);
        if !rows.is_empty() {
            let registry = rows_to_registry(&rows);
            if !registry.is_empty() {
                save_cached_manifest(version, &rows);
                return registry;
            }
        }
    }

    if let Some(cached) = load_cached_manifest(version) {
        let registry = rows_to_registry(&cached);
        if !registry.is_empty() {
            return registry;
        }
    }

    tracing::info!(
        version,
        "Using bundled Hailo GenAI model registry; remote fetch and cache both unavailable"
    );
    rows_to_registry(&bundled_parsed_models())
}

static GENAI_MODELS: tokio::sync::OnceCell<HashMap<String, GenAiModelInfo>> =
    tokio::sync::OnceCell::const_new();

/// Lazily builds (once) and returns the process-wide GenAI model registry,
/// mirroring Python's module-import-time `GENAI_MODELS` global.
pub(crate) async fn genai_models() -> &'static HashMap<String, GenAiModelInfo> {
    GENAI_MODELS
        .get_or_init(|| build_models_registry(HAILORT_VERSION))
        .await
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE_RST: &str = "\
Language Models
===============

Download: https://dev-public.hailo.ai/v5.3.0/blob/Qwen3-1.7B-Instruct.hef

Vision Encoders Only
=====================

This section should be skipped entirely.

Encoder: https://dev-public.hailo.ai/v5.3.0/blob/Should-Skip.hef

Multimodal Vision-Language Models
==================================

Qwen2-VL-2B-Instruct: https://dev-public.hailo.ai/v5.3.0/blob/Qwen2-VL-2B-Instruct.hef
";

    #[test]
    fn parse_models_rst_extracts_rows_and_skips_marked_sections() {
        let rows = parse_models_rst(SAMPLE_RST);
        assert_eq!(rows.len(), 2);

        assert_eq!(rows[0].section, "Language Models");
        assert_eq!(rows[0].hef_filename, "Qwen3-1.7B-Instruct.hef");
        assert_eq!(
            rows[0].url,
            "https://dev-public.hailo.ai/v5.3.0/blob/Qwen3-1.7B-Instruct.hef"
        );

        assert_eq!(rows[1].section, "Multimodal Vision-Language Models");
        assert_eq!(rows[1].hef_filename, "Qwen2-VL-2B-Instruct.hef");

        // Ensure the "Vision Encoders Only" section row never made it in.
        assert!(rows.iter().all(|r| r.hef_filename != "Should-Skip.hef"));
    }

    #[test]
    fn classify_by_filename_matches_python_rules() {
        assert_eq!(
            classify_by_filename("Whisper-Tiny.hef"),
            GenAiModelType::Speech2Text
        );
        assert_eq!(
            classify_by_filename("Qwen3-VL-2B-Instruct.hef"),
            GenAiModelType::Vlm
        );
        assert_eq!(
            classify_by_filename("Llama3.2-1B-Instruct.hef"),
            GenAiModelType::Llm
        );
    }

    #[test]
    fn rows_to_registry_applies_override_and_falls_back_to_auto() {
        let rows = vec![
            ParsedModel {
                section: "Language Models".to_string(),
                hef_filename: "Llama3.2-1B-Instruct.hef".to_string(),
                url: "https://example.com/Llama3.2-1B-Instruct.hef".to_string(),
            },
            ParsedModel {
                section: "Speech Recognition (Whisper)".to_string(),
                hef_filename: "Whisper-Tiny.hef".to_string(),
                url: "https://example.com/Whisper-Tiny.hef".to_string(),
            },
        ];
        let registry = rows_to_registry(&rows);

        let overridden = registry.get("llama3.2-1b").expect("override name present");
        assert_eq!(overridden.description, "Llama 3.2 1B Instruct");
        assert_eq!(overridden.model_type, GenAiModelType::Llm);

        let auto = registry
            .get("whisper-tiny")
            .expect("auto-derived name present");
        assert_eq!(auto.description, "Whisper Tiny");
        assert_eq!(auto.model_type, GenAiModelType::Speech2Text);
    }

    #[test]
    fn bundled_registry_is_non_empty_and_contains_known_models() {
        let registry = rows_to_registry(&bundled_parsed_models());
        assert!(!registry.is_empty());
        assert!(registry.contains_key("llama3.2-1b"));
        assert!(registry.contains_key("qwen3-1.7b-instruct"));
        assert!(registry.contains_key("whisper-tiny"));
    }

    #[tokio::test]
    async fn build_models_registry_falls_back_to_bundled_when_remote_and_cache_unavailable() {
        let _guard = crate::ENV_MUTATION_TEST_LOCK
            .lock()
            .unwrap_or_else(|e| e.into_inner());
        // Point HOME at an isolated temp dir so any stray cache file from a
        // previous test run can't leak in.
        let tmp = tempfile::tempdir().expect("tempdir");
        let prev_home = std::env::var_os("HOME");
        std::env::set_var("HOME", tmp.path());

        // Use an unreachable local address (never raw.githubusercontent.com)
        // so this test never makes a real network call, with a short
        // timeout to keep it fast.
        let unreachable_templates: &[&str] = &["http://127.0.0.1:1/{version}/MODELS.rst"];
        let registry = build_models_registry_from_templates(
            "0.0.0-test-unique",
            unreachable_templates,
            Duration::from_millis(200),
        )
        .await;
        assert!(!registry.is_empty());
        assert!(registry.contains_key("llama3.2-1b"));
        assert!(registry.contains_key("qwen3-1.7b-instruct"));

        if let Some(home) = prev_home {
            std::env::set_var("HOME", home);
        } else {
            std::env::remove_var("HOME");
        }
    }
}
