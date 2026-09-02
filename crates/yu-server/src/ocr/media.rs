use std::{
    fs,
    path::{Path, PathBuf},
    time::{Instant, SystemTime, UNIX_EPOCH},
};

use serde_json::{json, Value};
use sqlx::Row;
use tokio_util::sync::CancellationToken;

use crate::{
    analysis_engines::{AnalysisEngine, AnalyzeContext, AnalyzeMode},
    ocr::{
        parsers::{manga_parse_quality, parse_response, should_retry_manga, OcrResult},
        prompts::{lang_hint, prompt_for, schema_for, MANGA_RETRY_PROMPT},
    },
    sse::SseEvent,
    state::SharedState,
};

fn cancelled(token: &CancellationToken) -> Result<(), String> {
    if token.is_cancelled() {
        Err("OCR job cancelled".to_string())
    } else {
        Ok(())
    }
}

pub async fn file_path(state: &SharedState, file_id: i64) -> Result<PathBuf, String> {
    sqlx::query_scalar::<_, String>("SELECT path FROM files WHERE id=? AND is_deleted=0")
        .bind(file_id)
        .fetch_optional(&state.db_read)
        .await
        .map_err(|e| e.to_string())?
        .map(PathBuf::from)
        .ok_or_else(|| "File not found".to_string())
}

async fn extract(
    engine: &dyn AnalysisEngine,
    image: &Path,
    task: &str,
    language: &str,
    prompt: &str,
) -> Result<OcrResult, String> {
    let mut text = prompt.to_string();
    if let Some(hint) = lang_hint(language) {
        text.push('\n');
        text.push_str(hint);
    }
    let result = engine
        .analyze_image(
            image,
            &AnalyzeContext {
                existing_tags: Vec::new(),
                existing_prompt: Some(text),
                mode: AnalyzeMode::Ocr,
                language: language.to_string(),
                json_schema: schema_for(task),
            },
        )
        .await
        .map_err(|e| e.to_string())?;
    Ok(parse_response(&result.raw_response, task, language))
}

pub async fn extract_text_cancellable(
    engine: &dyn AnalysisEngine,
    image: &Path,
    task: &str,
    language: &str,
    token: &CancellationToken,
) -> Result<OcrResult, String> {
    cancelled(token)?;
    let first = extract(engine, image, task, language, prompt_for(task)).await?;
    if task != "ocr_manga" || !should_retry_manga(&first) {
        return Ok(first);
    }
    cancelled(token)?;
    match extract(engine, image, task, language, MANGA_RETRY_PROMPT).await {
        Ok(retry) if manga_parse_quality(&retry) > manga_parse_quality(&first) => Ok(retry),
        Ok(_) | Err(_) => Ok(first),
    }
}

async fn persist(
    state: &SharedState,
    file_id: i64,
    engine: &str,
    task: &str,
    result: &OcrResult,
) -> Result<i64, String> {
    sqlx::query("INSERT INTO file_ocr_results (file_id,engine,task,regions_json,full_text,structured_json,language,created_at) VALUES (?,?,?,?,?,?,?,?) ON CONFLICT(file_id,engine,task) DO UPDATE SET regions_json=excluded.regions_json,full_text=excluded.full_text,structured_json=excluded.structured_json,language=excluded.language,created_at=excluded.created_at")
        .bind(file_id).bind(engine).bind(task)
        .bind(serde_json::to_string(&result.regions).map_err(|e| e.to_string())?)
        .bind(&result.full_text).bind(result.structured.as_ref().map(|v| v.to_string())).bind(&result.language)
        .bind(SystemTime::now().duration_since(UNIX_EPOCH).map_err(|e| e.to_string())?.as_secs() as i64)
        .execute(&state.db).await.map_err(|e| e.to_string())?;
    let row_id = sqlx::query_scalar(
        "SELECT id FROM file_ocr_results WHERE file_id=? AND engine=? AND task=?",
    )
    .bind(file_id)
    .bind(engine)
    .bind(task)
    .fetch_one(&state.db_read)
    .await
    .map_err(|e| e.to_string())?;
    state.sse_hub.send(SseEvent {
        event_type: "OCR_COMPLETE".to_string(),
        timestamp: SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap_or_default()
            .as_secs_f64(),
        data: json!({"file_id": file_id, "row_id": row_id}),
        source: "ocr".to_string(),
    });
    Ok(row_id)
}

pub async fn run_single(
    engine: &dyn AnalysisEngine,
    state: &SharedState,
    file_id: i64,
    task: &str,
    language: &str,
    token: &CancellationToken,
) -> Result<Value, String> {
    let path = file_path(state, file_id).await?;
    let result = extract_text_cancellable(engine, &path, task, language, token).await?;
    cancelled(token)?;
    let row_id = persist(state, file_id, &engine.name(), task, &result).await?;
    Ok(
        json!({"file_id":file_id,"engine":engine.name(),"task":task,"regions_count":result.regions.len(),"row_id":row_id}),
    )
}

pub async fn run_batch(
    engine: &dyn AnalysisEngine,
    state: &SharedState,
    file_ids: &[i64],
    task: &str,
    language: &str,
    token: &CancellationToken,
) -> Result<Value, String> {
    let mut last = json!(null);
    for &file_id in file_ids {
        cancelled(token)?;
        last = run_single(engine, state, file_id, task, language, token).await?;
    }
    Ok(last)
}

pub async fn run_video(
    engine: &dyn AnalysisEngine,
    state: &SharedState,
    file_id: i64,
    task: &str,
    language: &str,
    count: u32,
    token: &CancellationToken,
) -> Result<Value, String> {
    let video = file_path(state, file_id).await?;
    let dir = tempfile::tempdir().map_err(|e| e.to_string())?;
    let frames =
        crate::routes::wd_tagger_video::extract_keyframes(&video, dir.path(), count, "uniform")
            .await;
    if frames.is_empty() {
        return Err("keyframe extraction failed".to_string());
    }
    let mut regions = Vec::new();
    let mut text = String::new();
    let mut language_out = String::new();
    for frame in frames {
        cancelled(token)?;
        let result = extract_text_cancellable(engine, &frame, task, language, token).await?;
        text.push_str(&result.full_text);
        regions.extend(result.regions);
        language_out = result.language;
    }
    let result = OcrResult {
        full_text: text,
        language: language_out,
        regions,
        structured: None,
    };
    let row_id = persist(state, file_id, &engine.name(), task, &result).await?;
    Ok(
        json!({"file_id":file_id,"engine":engine.name(),"task":task,"frame_count":result.regions.len(),"row_id":row_id}),
    )
}

pub async fn run_pdf(
    engine: &dyn AnalysisEngine,
    state: &SharedState,
    file_id: i64,
    task: &str,
    language: &str,
    pages: &[usize],
    dpi: u32,
    library_dir: &Path,
    fallback: bool,
    token: &CancellationToken,
) -> Result<Value, String> {
    let pdf = file_path(state, file_id).await?;
    let dir = tempfile::tempdir().map_err(|e| e.to_string())?;
    let mut regions = Vec::new();
    let mut text = String::new();
    let mut language_out = String::new();
    for &page in pages {
        cancelled(token)?;
        let image = crate::ocr::pdf::render_page(&pdf, page, dpi, library_dir, fallback)?;
        let path = dir.path().join(format!("page-{page}.png"));
        image.save(&path).map_err(|e| e.to_string())?;
        let result = extract_text_cancellable(engine, &path, task, language, token).await?;
        text.push_str(&result.full_text);
        regions.extend(result.regions);
        language_out = result.language;
    }
    let result = OcrResult {
        full_text: text,
        language: language_out,
        regions,
        structured: None,
    };
    let row_id = persist(state, file_id, &engine.name(), task, &result).await?;
    Ok(
        json!({"file_id":file_id,"engine":engine.name(),"task":task,"page_count":result.regions.len(),"row_id":row_id}),
    )
}

fn contain_under(root: &Path, relative: &str) -> Result<PathBuf, String> {
    if relative.contains('\0') {
        return Err("Invalid benchmark entry".to_string());
    }
    let relative = Path::new(relative);
    if relative.is_absolute()
        || relative
            .components()
            .any(|part| matches!(part, std::path::Component::ParentDir))
    {
        return Err("Invalid benchmark entry".to_string());
    }
    let root = root
        .canonicalize()
        .map_err(|_| "Invalid benchmark directory".to_string())?;
    let mut candidate = root.clone();
    for part in relative.components() {
        if let std::path::Component::Normal(part) = part {
            candidate.push(part);
            let resolved = candidate
                .canonicalize()
                .unwrap_or_else(|_| candidate.clone());
            if !resolved.starts_with(&root) {
                return Err("Invalid benchmark entry".to_string());
            }
            candidate = resolved;
        }
    }
    Ok(candidate)
}

fn benchmark_cases(root: &Path) -> Result<Vec<(PathBuf, String, String, String)>, String> {
    let manifest = root.join("manifest.json");
    if manifest.exists() {
        let data: Value = serde_json::from_slice(&fs::read(manifest).map_err(|e| e.to_string())?)
            .map_err(|e| e.to_string())?;
        return Ok(data
            .get("cases")
            .and_then(Value::as_array)
            .into_iter()
            .flatten()
            .filter_map(|case| {
                Some((
                    contain_under(root, case.get("image")?.as_str()?).ok()?,
                    case.get("expected_text")
                        .and_then(Value::as_str)
                        .unwrap_or_default()
                        .to_string(),
                    case.get("task")
                        .and_then(Value::as_str)
                        .unwrap_or("ocr")
                        .to_string(),
                    case.get("language")
                        .and_then(Value::as_str)
                        .unwrap_or("auto")
                        .to_string(),
                ))
            })
            .collect::<Vec<_>>());
    }
    let mut cases = Vec::new();
    for entry in fs::read_dir(root).map_err(|e| e.to_string())? {
        let image = entry.map_err(|e| e.to_string())?.path();
        if !matches!(
            image
                .extension()
                .and_then(|x| x.to_str())
                .map(str::to_ascii_lowercase)
                .as_deref(),
            Some("png" | "jpg" | "jpeg" | "webp" | "bmp")
        ) {
            continue;
        }
        let name = image
            .file_name()
            .and_then(|x| x.to_str())
            .ok_or_else(|| "Invalid benchmark entry".to_string())?;
        let image = contain_under(root, name)?;
        let txt = contain_under(
            root,
            &format!(
                "{}.txt",
                image
                    .file_stem()
                    .and_then(|x| x.to_str())
                    .unwrap_or_default()
            ),
        )?;
        if txt.exists() {
            cases.push((
                image,
                fs::read_to_string(txt)
                    .map_err(|e| e.to_string())?
                    .trim()
                    .to_string(),
                "ocr".to_string(),
                "auto".to_string(),
            ));
        }
    }
    Ok(cases)
}

pub async fn run_benchmark(
    engine: &dyn AnalysisEngine,
    state: &SharedState,
    task_override: Option<&str>,
    token: &CancellationToken,
) -> Result<Value, String> {
    let root = state
        .config
        .project_root
        .join("extensions/builtin_ocr/benchmarks");
    let cases = benchmark_cases(&root)?;
    let mut results = Vec::new();
    for (image, expected, task, language) in cases {
        cancelled(token)?;
        let task = task_override.unwrap_or(&task);
        let started = Instant::now();
        let result = extract_text_cancellable(engine, &image, task, &language, token).await;
        let actual = result
            .as_ref()
            .map(|r| r.full_text.trim().to_string())
            .unwrap_or_default();
        let similarity = similarity(&expected, &actual);
        // `as_millis()` is u128; narrowing one OCR case's duration to u64 needs
        // it to have run for ~584 million years before anything is lost.
        #[allow(clippy::cast_possible_truncation)]
        results.push(json!({"case_name":image.file_stem().and_then(|x|x.to_str()).unwrap_or_default(),"task":task,"expected_text":expected,"actual_text":actual,"similarity":similarity,"char_accuracy":char_accuracy(&expected, &actual),"elapsed_ms":started.elapsed().as_millis() as u64,"engine":engine.name(),"error":result.err()}));
    }
    let valid: Vec<_> = results.iter().filter(|r| r["error"].is_null()).collect();
    let avg = |key: &str| {
        valid.iter().filter_map(|r| r[key].as_f64()).sum::<f64>() / valid.len().max(1) as f64
    };
    let mut scores = serde_json::Map::new();
    for result in &results {
        let task = result["task"].as_str().unwrap_or_default();
        let entry = scores.entry(task.to_string()).or_insert_with(|| json!([]));
        entry
            .as_array_mut()
            .unwrap()
            .push(result["similarity"].clone());
    }
    for value in scores.values_mut() {
        *value = json!(
            value
                .as_array()
                .unwrap()
                .iter()
                .filter_map(Value::as_f64)
                .sum::<f64>()
                / value.as_array().unwrap().len().max(1) as f64
        );
    }
    let report_id = uuid::Uuid::new_v4().to_string();
    let report = json!({"report_id":report_id,"engine":engine.name(),"total_cases":results.len(),"avg_similarity":avg("similarity"),"avg_char_accuracy":avg("char_accuracy"),"avg_elapsed_ms":avg("elapsed_ms"),"task_scores":scores,"cases":results});
    let reports = root.join("reports");
    fs::create_dir_all(&reports).map_err(|e| e.to_string())?;
    fs::write(
        reports.join(format!("{report_id}.json")),
        serde_json::to_vec_pretty(&report).map_err(|e| e.to_string())?,
    )
    .map_err(|e| e.to_string())?;
    Ok(
        json!({"report_id":report_id,"engine":engine.name(),"total_cases":report["total_cases"],"avg_similarity":report["avg_similarity"],"avg_char_accuracy":report["avg_char_accuracy"],"avg_elapsed_ms":report["avg_elapsed_ms"],"task_scores":report["task_scores"]}),
    )
}

fn similarity(a: &str, b: &str) -> f64 {
    if a == b {
        1.0
    } else if a.is_empty() || b.is_empty() {
        0.0
    } else {
        a.chars().filter(|c| b.contains(*c)).count() as f64 / a.chars().count() as f64
    }
}
fn char_accuracy(a: &str, b: &str) -> f64 {
    similarity(a, b)
}

#[cfg(test)]
mod tests {
    use super::*;

    /// A benchmark root with one real case file inside it.
    fn root() -> tempfile::TempDir {
        let dir = tempfile::tempdir().expect("tempdir");
        std::fs::create_dir_all(dir.path().join("cases")).expect("mkdir");
        std::fs::write(dir.path().join("cases/a.png"), b"x").expect("write");
        dir
    }

    #[test]
    fn containment_rejects_lexical_traversal() {
        let dir = root();
        for bad in [
            "../secret",
            "a/../../secret",
            "/etc/passwd",
            "cases/../../etc/passwd",
        ] {
            assert!(
                contain_under(dir.path(), bad).is_err(),
                "{bad} must be refused"
            );
        }
    }

    #[test]
    fn containment_rejects_a_null_byte() {
        let dir = root();
        assert!(contain_under(dir.path(), "a\0b").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn containment_rejects_a_symlink_leaf_that_escapes() {
        // The lexical check alone passes this: no ".." appears in the path.
        // Only resolving each component catches it.
        let dir = root();
        std::os::unix::fs::symlink("/etc", dir.path().join("out")).expect("symlink");
        assert!(contain_under(dir.path(), "out/passwd").is_err());
    }

    #[cfg(unix)]
    #[test]
    fn containment_rejects_a_symlink_in_a_middle_component() {
        // Checking only the final component leaves this open.
        let dir = root();
        std::fs::create_dir_all(dir.path().join("a/b")).expect("mkdir");
        std::os::unix::fs::symlink("/tmp", dir.path().join("a/hop")).expect("symlink");
        assert!(contain_under(dir.path(), "a/hop/b/img.png").is_err());
    }

    #[test]
    fn containment_accepts_an_ordinary_relative_path() {
        let dir = root();
        assert!(contain_under(dir.path(), "cases/a.png").is_ok());
    }

    #[cfg(unix)]
    #[test]
    fn containment_accepts_a_symlink_that_stays_inside() {
        // Containment must not become "no symlinks at all": a link within the
        // benchmark set is legitimate.
        let dir = root();
        std::os::unix::fs::symlink(dir.path().join("cases"), dir.path().join("inside"))
            .expect("symlink");
        assert!(contain_under(dir.path(), "inside/a.png").is_ok());
    }

    #[test]
    fn containment_error_does_not_disclose_the_root() {
        // benchmark.py:94 embeds the absolute root in its message; that is a
        // path disclosure to an unauthorised caller and is deliberately not
        // reproduced here (contract §4.4).
        let dir = root();
        let error = contain_under(dir.path(), "../secret").unwrap_err();
        assert!(
            !error.contains(&dir.path().display().to_string()),
            "the message must not carry the root: {error}"
        );
    }
}
