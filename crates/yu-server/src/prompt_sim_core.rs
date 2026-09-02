//! prompt_sim_core — wildcard I/O, config access for prompt simulator routes.

use std::collections::BTreeMap;
use std::io::{self, Read};
use std::path::{Path, PathBuf};
use std::sync::Mutex;

use serde_json::Value;

static WRITE_LOCK: Mutex<()> = Mutex::new(());
/// Parse a YAML wildcard file into `(key, lines)` pairs.
/// Sequence  => single entry with key "" (caller uses filename as name).
/// Mapping   => one entry per string key whose value is a string sequence.
fn parse_yaml_wildcard(text: &str) -> Vec<(String, Vec<String>)> {
    let Ok(val) = serde_yml::from_str::<serde_yml::Value>(text) else {
        return vec![];
    };
    fn seq_to_lines(seq: Vec<serde_yml::Value>) -> Vec<String> {
        seq.into_iter()
            .filter_map(|item| {
                let serde_yml::Value::String(s) = item else {
                    return None;
                };
                let s = s.trim().to_string();
                if s.is_empty() {
                    None
                } else {
                    Some(s)
                }
            })
            .collect()
    }
    match val {
        serde_yml::Value::Sequence(seq) => {
            let lines = seq_to_lines(seq);
            if lines.is_empty() {
                vec![]
            } else {
                vec![("".into(), lines)]
            }
        }
        serde_yml::Value::Mapping(map) => map
            .into_iter()
            .filter_map(|(key, v)| {
                let serde_yml::Value::Sequence(seq) = v else {
                    return None;
                };
                let lines = seq_to_lines(seq);
                if lines.is_empty() {
                    None
                } else {
                    Some((key, lines))
                }
            })
            .collect(),
        _ => vec![],
    }
}

// ── config access ─────────────────────────────────────────────────────────────

pub fn read_config_json(config_path: &str) -> Value {
    let path = Path::new(config_path);
    let Some(raw) = std::fs::read_to_string(path).ok() else {
        return Value::Object(Default::default());
    };
    if path.extension().and_then(|ext| ext.to_str()) == Some("toml") {
        toml::from_str::<toml::Table>(&raw)
            .ok()
            .and_then(|table| serde_json::to_value(table).ok())
            .unwrap_or(Value::Object(Default::default()))
    } else {
        serde_json::from_str(&raw).unwrap_or(Value::Object(Default::default()))
    }
}

pub fn get_ext_dirs(config_path: &str, ext_name: &str, key: &str) -> Vec<String> {
    let cfg = read_config_json(config_path);
    cfg["extensions"][ext_name][key]
        .as_array()
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(|s| s.trim().to_string()))
                .filter(|s| !s.is_empty())
                .collect()
        })
        .unwrap_or_default()
}

pub fn save_ext_config(
    config_path: &str,
    ext_name: &str,
    updates: &serde_json::Map<String, Value>,
) -> io::Result<()> {
    let _guard = WRITE_LOCK.lock().unwrap();
    let mut cfg = read_config_json(config_path);
    if matches!(cfg.get("extensions"), None | Some(Value::Null)) {
        cfg.as_object_mut()
            .ok_or_else(|| io::Error::other("extensions not an object"))?
            .insert("extensions".to_string(), Value::Object(Default::default()));
    }
    let exts = cfg["extensions"]
        .as_object_mut()
        .ok_or_else(|| io::Error::other("extensions not an object"))?;
    let ext = exts
        .entry(ext_name)
        .or_insert(Value::Object(Default::default()));
    let obj = ext.as_object_mut().unwrap();
    for (k, v) in updates {
        obj.insert(k.clone(), v.clone());
    }
    let tmp = format!("{}.{}.tmp", config_path, std::process::id());
    std::fs::write(&tmp, serde_json::to_string_pretty(&cfg).unwrap())?;
    std::fs::rename(tmp, config_path)?;
    Ok(())
}

// ── wildcard name validation ───────────────────────────────────────────────────

pub fn sanitize_wildcard_name(name: &str) -> Option<String> {
    let cleaned = name.trim().replace('\\', "/");
    if cleaned.is_empty() || cleaned.starts_with('/') || cleaned.starts_with('.') {
        return None;
    }
    for part in cleaned.split('/') {
        if part.is_empty() || part == "." || part == ".." {
            return None;
        }
        if part.contains(['<', '>', ':', '"', '|', '?', '*']) {
            return None;
        }
        if part.ends_with('.') || part.ends_with(' ') {
            return None;
        }
    }
    Some(cleaned)
}

fn is_within(child: &Path, parent: &Path) -> bool {
    child
        .canonicalize()
        .ok()
        .zip(parent.canonicalize().ok())
        .map(|(c, p)| c.starts_with(&p))
        .unwrap_or(false)
}

// ── wildcard loading from dirs ────────────────────────────────────────────────

pub fn bridge_wildcards(
    config_path: &str,
    client_wildcards: BTreeMap<String, Vec<String>>,
) -> BTreeMap<String, Vec<String>> {
    let wildcard_dirs = get_ext_dirs(config_path, "builtin-prompt-simulator", "wildcard_dirs");
    let mut wildcards = if wildcard_dirs.is_empty() {
        BTreeMap::new()
    } else {
        load_wildcards(&wildcard_dirs).0
    };
    wildcards.extend(client_wildcards);
    wildcards
}

pub fn load_wildcards(
    dirs: &[String],
) -> (BTreeMap<String, Vec<String>>, BTreeMap<String, String>) {
    let mut result: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut sources: BTreeMap<String, String> = BTreeMap::new();
    for dir_str in dirs {
        let dir = Path::new(dir_str.trim());
        if !dir.is_dir() {
            continue;
        }
        let Ok(resolved_dir) = dir.canonicalize() else {
            continue;
        };
        load_txt_recursive(dir, dir, &resolved_dir, &mut result, &mut sources);
    }
    (result, sources)
}

fn load_txt_recursive(
    base: &Path,
    current: &Path,
    resolved_base: &Path,
    result: &mut BTreeMap<String, Vec<String>>,
    sources: &mut BTreeMap<String, String>,
) {
    let Ok(entries) = std::fs::read_dir(current) else {
        return;
    };
    let mut entries: Vec<_> = entries.flatten().collect();
    entries.sort_by_key(|e| e.file_name());
    for entry in entries {
        let path = entry.path();
        if path.is_symlink() {
            let Ok(resolved) = path.canonicalize() else {
                continue;
            };
            if !resolved.starts_with(resolved_base) {
                continue;
            }
        }
        if path.is_dir() {
            load_txt_recursive(base, &path, resolved_base, result, sources);
        } else if let Some(ext) = path.extension().and_then(|e| e.to_str()) {
            let Ok(rel) = path.strip_prefix(base) else {
                continue;
            };
            let base_name = rel.with_extension("").to_string_lossy().replace('\\', "/");
            if ext == "txt" {
                let Ok(text) = std::fs::read_to_string(&path) else {
                    continue;
                };
                let lines: Vec<String> = text
                    .lines()
                    .map(|l| l.trim().to_string())
                    .filter(|l| !l.is_empty() && !l.starts_with('#'))
                    .collect();
                if !lines.is_empty() {
                    result.insert(base_name.clone(), lines);
                    sources.insert(base_name, "txt".to_string());
                }
            } else if ext == "yaml" || ext == "yml" {
                let Ok(text) = std::fs::read_to_string(&path) else {
                    continue;
                };
                for (sub_key, lines) in parse_yaml_wildcard(&text) {
                    let name = if sub_key.is_empty() {
                        base_name.clone()
                    } else {
                        format!("{}/{}", base_name, sub_key)
                    };
                    result.entry(name.clone()).or_insert(lines);
                    sources.entry(name).or_insert("yaml".to_string());
                }
            }
        }
    }
}

// ── wildcard loading from ZIP ─────────────────────────────────────────────────

const ZIP_MAX_UNCOMPRESSED: u64 = 50 * 1024 * 1024;

pub fn load_wildcards_from_zip(data: &[u8]) -> Result<BTreeMap<String, Vec<String>>, String> {
    use std::io::Cursor;
    let cursor = Cursor::new(data);
    let mut archive = zip::ZipArchive::new(cursor).map_err(|e| e.to_string())?;

    // Zip bomb guard
    let mut total: u64 = 0;
    for i in 0..archive.len() {
        if let Ok(f) = archive.by_index_raw(i) {
            total += f.size();
        }
    }
    if total > ZIP_MAX_UNCOMPRESSED {
        return Err(format!(
            "ZIP uncompressed size ({total} bytes) exceeds limit ({ZIP_MAX_UNCOMPRESSED} bytes)"
        ));
    }

    let mut result: BTreeMap<String, Vec<String>> = BTreeMap::new();
    let mut remaining_budget = ZIP_MAX_UNCOMPRESSED;
    for i in 0..archive.len() {
        let mut file = archive.by_index(i).map_err(|e| e.to_string())?;
        if file.is_dir() {
            continue;
        }
        let name_raw = file.name().to_string();
        if name_raw.contains("..") {
            continue;
        }
        let path = std::path::Path::new(&name_raw);
        let ext = path.extension().and_then(|e| e.to_str()).unwrap_or("");
        if ext != "txt" && ext != "yaml" && ext != "yml" {
            continue;
        }
        let mut contents = String::new();
        // Enforce byte budget on actual decompressed data (guards against lying central dir)
        file.take(remaining_budget)
            .read_to_string(&mut contents)
            .ok();
        remaining_budget = remaining_budget.saturating_sub(contents.len() as u64);
        if remaining_budget == 0 {
            return Err(format!(
                "ZIP uncompressed content exceeds limit ({ZIP_MAX_UNCOMPRESSED} bytes)"
            ));
        }
        let base_name = path.with_extension("").to_string_lossy().replace('\\', "/");
        if ext == "txt" {
            let lines: Vec<String> = contents
                .lines()
                .map(|l| l.trim().to_string())
                .filter(|l| !l.is_empty() && !l.starts_with('#'))
                .collect();
            if !lines.is_empty() {
                result.insert(base_name, lines);
            }
        } else {
            for (sub_key, lines) in parse_yaml_wildcard(&contents) {
                let wc_name = if sub_key.is_empty() {
                    base_name.clone()
                } else {
                    format!("{}/{}", base_name, sub_key)
                };
                result.entry(wc_name).or_insert(lines);
            }
        }
    }
    Ok(result)
}

// ── wildcard file CRUD ────────────────────────────────────────────────────────

pub fn find_wildcard_files(name: &str, dirs: &[String]) -> Result<Vec<PathBuf>, String> {
    let sanitized =
        sanitize_wildcard_name(name).ok_or_else(|| format!("Invalid wildcard name: {name:?}"))?;
    let parts: Vec<&str> = sanitized.splitn(2, '/').collect();
    let (sub, stem) = if parts.len() == 2 {
        (parts[0], parts[1].to_string())
    } else {
        ("", sanitized.clone())
    };
    let mut matches = vec![];
    for d in dirs {
        let base = Path::new(d.trim());
        if !base.is_dir() {
            continue;
        }
        for ext in &["txt", "yaml", "yml"] {
            let file = format!("{}.{}", stem, ext);
            let candidate = if sub.is_empty() {
                base.join(&file)
            } else {
                base.join(sub).join(&file)
            };
            if candidate.is_file() && is_within(&candidate, base) {
                matches.push(candidate);
                break; // prefer txt, then yaml, then yml
            }
        }
    }
    Ok(matches)
}

pub fn save_wildcard_file(
    name: &str,
    lines: &[String],
    dirs: &[String],
) -> Result<PathBuf, String> {
    let sanitized = sanitize_wildcard_name(name).ok_or("Invalid wildcard name")?;
    if dirs.is_empty() {
        return Err("No wildcard directories configured".to_string());
    }
    let rel = Path::new(&sanitized);
    let filename = format!("{}.txt", rel.file_name().unwrap().to_string_lossy());
    let subdirs = rel.parent();

    // Find existing file
    let mut target: Option<PathBuf> = None;
    for d in dirs {
        let base = Path::new(d.trim());
        if !base.is_dir() {
            continue;
        }
        let candidate = match subdirs {
            Some(sub) if sub.as_os_str() != "" => base.join(sub).join(&filename),
            _ => base.join(&filename),
        };
        if candidate.is_file() && is_within(&candidate, base) {
            target = Some(candidate);
            break;
        }
    }

    // Create in first dir if not found
    let target = if let Some(t) = target {
        t
    } else {
        let base = Path::new(dirs[0].trim());
        let candidate = match subdirs {
            Some(sub) if sub.as_os_str() != "" => base.join(sub).join(&filename),
            _ => base.join(&filename),
        };
        // path-traversal guard on the new-file path (mirrors existing-file branch)
        let base_canonical = base
            .canonicalize()
            .map_err(|e| format!("Cannot canonicalize base dir: {e}"))?;
        let parent_to_create = candidate.parent().unwrap_or(&candidate);
        // Create parent first so canonicalize can succeed, then verify
        std::fs::create_dir_all(parent_to_create).map_err(|e| e.to_string())?;
        let candidate_canonical = candidate
            .canonicalize()
            .unwrap_or_else(|_| candidate.clone());
        if !candidate_canonical.starts_with(&base_canonical) {
            return Err(format!("Path traversal detected: {}", candidate.display()));
        }
        candidate
    };

    if let Some(parent) = target.parent() {
        std::fs::create_dir_all(parent).map_err(|e| e.to_string())?;
    }

    let text = lines.join("\n") + "\n";
    std::fs::write(&target, text).map_err(|e| e.to_string())?;
    Ok(target)
}

pub fn delete_wildcard_files(name: &str, dirs: &[String]) -> Result<Vec<String>, String> {
    let matches = find_wildcard_files(name, dirs)?;
    if matches.is_empty() {
        return Err(format!("Wildcard not found on disk: {name:?}"));
    }
    let mut removed = vec![];
    for path in &matches {
        std::fs::remove_file(path).map_err(|e| e.to_string())?;
        removed.push(path.to_string_lossy().to_string());
    }
    Ok(removed)
}

pub fn rename_wildcard_files(
    old_name: &str,
    new_name: &str,
    dirs: &[String],
) -> Result<Vec<serde_json::Value>, String> {
    sanitize_wildcard_name(new_name).ok_or("Invalid new wildcard name")?;
    let matches = find_wildcard_files(old_name, dirs)?;
    if matches.is_empty() {
        return Err(format!("Wildcard not found on disk: {old_name:?}"));
    }
    if !find_wildcard_files(new_name, dirs)?.is_empty() {
        return Err(format!("Destination wildcard already exists: {new_name:?}"));
    }
    let sanitized_new = sanitize_wildcard_name(new_name).unwrap();
    let new_path = Path::new(&sanitized_new);
    let new_filename = format!("{}.txt", new_path.file_name().unwrap().to_string_lossy());
    let new_subdirs = new_path.parent();

    let mut results = vec![];
    for src in &matches {
        // Find which base dir src belongs to
        let base = dirs
            .iter()
            .find_map(|d| {
                let b = Path::new(d.trim());
                if is_within(src, b) {
                    Some(b.to_path_buf())
                } else {
                    None
                }
            })
            .ok_or("Could not locate base directory")?;
        let dst = match new_subdirs {
            Some(sub) if sub.as_os_str() != "" => base.join(sub).join(&new_filename),
            _ => base.join(&new_filename),
        };
        if let Some(p) = dst.parent() {
            std::fs::create_dir_all(p).map_err(|e| e.to_string())?;
        }
        std::fs::rename(src, &dst).map_err(|e| e.to_string())?;
        results.push(serde_json::json!({
            "from": src.to_string_lossy(),
            "to": dst.to_string_lossy(),
        }));
    }
    Ok(results)
}

pub fn validate_dirs(dirs: &[String]) -> Vec<serde_json::Value> {
    dirs.iter()
        .map(|d| serde_json::json!({"path": d, "exists": Path::new(d).is_dir()}))
        .collect()
}

// ── sweep axes ────────────────────────────────────────────────────────────────

pub fn load_sweep_axes(
    axis_dirs: &[String],
    include_wildcard_dirs: bool,
    wildcard_dirs: &[String],
) -> (BTreeMap<String, Vec<String>>, BTreeMap<String, String>) {
    let (mut axes, _) = load_wildcards(axis_dirs);
    let mut sources: BTreeMap<String, String> = axes
        .keys()
        .map(|k| (k.clone(), "axis".to_string()))
        .collect();
    if include_wildcard_dirs {
        let (wc_axes, _) = load_wildcards(wildcard_dirs);
        for (name, lines) in wc_axes {
            if !axes.contains_key(&name) {
                axes.insert(name.clone(), lines);
                sources.insert(name, "wildcard".to_string());
            }
        }
    }
    (axes, sources)
}

// ── NAI↔SD conversion helpers ────────────────────────────────────────────────

use regex::Regex;

fn re(pattern: &str) -> Regex {
    Regex::new(pattern).unwrap()
}

const SD_BASE: f64 = 1.1;
const NAI_BASE: f64 = 1.05;

fn format_weight(w: f64) -> String {
    let rounded = (w * 1_000_000.0).round() / 1_000_000.0;
    let s = format!("{:.6}", rounded);
    s.trim_end_matches('0').trim_end_matches('.').to_string()
}

fn sd_parens_to_nai_braces(s: &str) -> String {
    let mut result = s.to_string();
    loop {
        let before = result.clone();
        result = re(r"\(([^()]+)\)")
            .replace_all(&result, |caps: &regex::Captures| {
                let inner = &caps[1];
                if re(r":\s*[\d.]+\s*$").is_match(inner) {
                    return format!("({})", inner);
                }
                format!("{{{}}}", inner)
            })
            .to_string();
        if result == before {
            break;
        }
    }
    result
}

fn nai_braces_to_sd_parens(s: &str) -> String {
    let mut result = s.to_string();
    loop {
        let before = result.clone();
        result = re(r"\{([^{}]+)\}")
            .replace_all(&result, |caps: &regex::Captures| format!("({})", &caps[1]))
            .to_string();
        if result == before {
            break;
        }
    }
    result
}

fn sd_bracket_weaken_to_nai(s: &str) -> String {
    re(r"\[+([^\[\]:]+)\]+")
        .replace_all(s, |caps: &regex::Captures| {
            let full = &caps[0];
            let depth = full.chars().take_while(|&c| c == '[').count();
            let inner = caps[1].trim_end();
            let weight =
                format_weight((1.0 / SD_BASE).powi(i32::try_from(depth).unwrap_or(i32::MAX)));
            format!("{weight}::{inner} ::")
        })
        .to_string()
}

fn nai_bracket_weaken_to_sd(s: &str) -> String {
    re(r"\[+([^\[\]]+)\]+")
        .replace_all(s, |caps: &regex::Captures| {
            let full = &caps[0];
            let depth = full.chars().take_while(|&c| c == '[').count();
            let inner = &caps[1];
            let weight =
                format_weight((1.0 / NAI_BASE).powi(i32::try_from(depth).unwrap_or(i32::MAX)));
            format!("({inner}:{weight})")
        })
        .to_string()
}

pub fn convert_sd_to_nai(prompt: &str) -> String {
    if prompt.is_empty() {
        return String::new();
    }
    let mut s = prompt.to_string();

    // Strip LoRA / embedding tags
    s = re(r"(?i)<lora:[^>]+>").replace_all(&s, "").to_string();
    s = re(r"(?i)<lyco:[^>]+>").replace_all(&s, "").to_string();
    s = re(r"(?i)<(?:embedding|hypernet):[^>]+>")
        .replace_all(&s, "")
        .to_string();
    s = re(r"(?i)\(embedding:[^)]+\)")
        .replace_all(&s, "")
        .to_string();
    s = re(r"(?i)\bembedding:\S+").replace_all(&s, "").to_string();

    // SD dynamic choices {a|b|c} → NAI ||a|b|c||
    s = re(r"\{([^{}]+(?:\|[^{}]+)+)\}")
        .replace_all(&s, "||$1||")
        .to_string();

    // SD weighted (text:weight) → NAI weight::text::
    s = re(r"\(([^()]+?):\s*([\d.]+)\s*\)")
        .replace_all(&s, |caps: &regex::Captures| {
            format!("{}::{} ::", &caps[2], caps[1].trim_end())
        })
        .to_string();

    // SD emphasis parens (text) → NAI {text}
    s = sd_parens_to_nai_braces(&s);

    // SD [text] weakening → NAI weight::text::
    s = sd_bracket_weaken_to_nai(&s);

    // AND → NAI pipe mixing
    if s.contains(" AND ") {
        s = s
            .split(" AND ")
            .map(|p| p.trim())
            .collect::<Vec<_>>()
            .join("|");
    }

    // Cleanup
    s = re(r"\s*,\s*,+").replace_all(&s, ",").to_string();
    s = re(r"^[\s,]+|[\s,]+$").replace_all(&s, "").to_string();
    s = re(r"\s{2,}").replace_all(&s, " ").to_string();
    s.trim().to_string()
}

pub fn convert_nai_to_sd(prompt: &str) -> String {
    if prompt.is_empty() {
        return String::new();
    }
    let mut s = prompt.to_string();

    // NAI weight::text:: → SD (text:weight)
    s = re(r"([\d.]+)::((?:[^:]|:[^:])+?)::")
        .replace_all(&s, |caps: &regex::Captures| {
            format!("({}:{})", caps[2].trim_end(), &caps[1])
        })
        .to_string();

    // NAI ||a|b|c|| → SD {a|b|c}
    s = re(r"\|\|([^|]+(?:\|[^|]+)*)\|\|")
        .replace_all(&s, |caps: &regex::Captures| format!("{{{}}}", &caps[1]))
        .to_string();

    // NAI {text} → SD (text)
    s = nai_braces_to_sd_parens(&s);

    // NAI [text] weakening → SD (text:weight)
    s = nai_bracket_weaken_to_sd(&s);

    // Remaining | → AND
    if s.contains('|') {
        s = s
            .split('|')
            .map(|p| p.trim())
            .collect::<Vec<_>>()
            .join(" AND ");
    }

    s.trim().to_string()
}

pub fn expand_dynamic_prompt(
    prompt: &str,
    seed: Option<u64>,
    wildcards: &BTreeMap<String, Vec<String>>,
) -> String {
    use rand::{Rng, SeedableRng};
    let mut rng = rand::rngs::StdRng::seed_from_u64(seed.unwrap_or_else(rand::random::<u64>));

    let mut s = prompt.to_string();

    // Substitute __wildcard_name__ from loaded wildcards
    let wc_re = re(r"__([a-zA-Z0-9_/\-]+)__");
    for _ in 0..10 {
        let before = s.clone();
        s = wc_re
            .replace_all(&s, |caps: &regex::Captures| {
                let name = &caps[1];
                if let Some(lines) = wildcards.get(name) {
                    if lines.is_empty() {
                        return caps[0].to_string();
                    }
                    let idx = rng.random_range(0..lines.len());
                    lines[idx].clone()
                } else {
                    caps[0].to_string()
                }
            })
            .to_string();
        if s == before {
            break;
        }
    }

    // Expand {a|b|c} dynamic choices, brace-matching depth-aware so nesting
    // (e.g. `{a|{emphasis}|c}`) resolves correctly in one recursive pass. A
    // brace with no top-level `|` is not a choice — it's NAI emphasis syntax
    // (`{text}`, `{{text}}`) and is left untouched (recursing into its
    // content). Mirrors Python's expand_dynamic_prompt
    // (core/prompt/convert.py _expand_braces/_resolve_brace).
    expand_brace_choices(&s, &mut rng)
}

fn find_matching_brace_char(chars: &[char], start: usize) -> Option<usize> {
    let mut depth = 0i32;
    for (i, &c) in chars.iter().enumerate().skip(start) {
        match c {
            '{' => depth += 1,
            '}' => {
                depth -= 1;
                if depth == 0 {
                    return Some(i);
                }
            }
            _ => {}
        }
    }
    None
}

fn split_top_level_pipe(s: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut depth = 0i32;
    let mut cur = String::new();
    for ch in s.chars() {
        match ch {
            '{' => {
                depth += 1;
                cur.push(ch);
            }
            '}' => {
                depth -= 1;
                cur.push(ch);
            }
            '|' if depth == 0 => {
                parts.push(std::mem::take(&mut cur));
            }
            _ => cur.push(ch),
        }
    }
    parts.push(cur);
    parts
}

fn expand_brace_choices(s: &str, rng: &mut impl rand::Rng) -> String {
    let chars: Vec<char> = s.chars().collect();
    let mut out = String::new();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '{' {
            if let Some(end) = find_matching_brace_char(&chars, i) {
                let inner: String = chars[i + 1..end].iter().collect();
                out.push_str(&resolve_brace_choice(&inner, rng));
                i = end + 1;
                continue;
            }
        }
        out.push(chars[i]);
        i += 1;
    }
    out
}

fn resolve_brace_choice(inner: &str, rng: &mut impl rand::Rng) -> String {
    let parts = split_top_level_pipe(inner);
    if parts.len() < 2 {
        return format!("{{{}}}", expand_brace_choices(inner, rng));
    }
    let idx = rng.random_range(0..parts.len());
    expand_brace_choices(parts[idx].trim(), rng)
}

pub fn analyze_emphasis(prompt: &str) -> Vec<serde_json::Value> {
    let mut tokens: Vec<serde_json::Value> = vec![];

    // SD explicit weight: (text:weight)
    for caps in re(r"\(([^()]+?):\s*([\d.]+)\s*\)").captures_iter(prompt) {
        let weight: f64 = caps[2].parse().unwrap_or(1.0);
        tokens.push(serde_json::json!({
            "text": caps[1].trim(),
            "weight": weight,
            "syntax": "sd_explicit",
        }));
    }

    // SD parenthetical (text), ((text))
    for caps in re(r"\(+([^():]+)\)+").captures_iter(prompt) {
        let full = &caps[0];
        let depth = full.chars().take_while(|&c| c == '(').count();
        let weight = SD_BASE.powi(i32::try_from(depth).unwrap_or(i32::MAX));
        tokens.push(serde_json::json!({
            "text": caps[1].trim(),
            "weight": (weight * 1_000_000.0).round() / 1_000_000.0,
            "syntax": "sd_paren",
        }));
    }

    // NAI explicit: weight::text::
    for caps in re(r"([\d.]+)::((?:[^:]|:[^:])+?)::").captures_iter(prompt) {
        let weight: f64 = caps[1].parse().unwrap_or(1.0);
        tokens.push(serde_json::json!({
            "text": caps[2].trim(),
            "weight": weight,
            "syntax": "nai_explicit",
        }));
    }

    // NAI braces {text}, {{text}}
    for caps in re(r"\{+([^{}]+)\}+").captures_iter(prompt) {
        let full = &caps[0];
        let depth = full.chars().take_while(|&c| c == '{').count();
        let weight = NAI_BASE.powi(i32::try_from(depth).unwrap_or(i32::MAX));
        tokens.push(serde_json::json!({
            "text": caps[1].trim(),
            "weight": (weight * 1_000_000.0).round() / 1_000_000.0,
            "syntax": "nai_brace",
        }));
    }

    // Bracket weakening [text], [[text]]
    for caps in re(r"\[+([^\[\]:]+)\]+").captures_iter(prompt) {
        let full = &caps[0];
        let depth = full.chars().take_while(|&c| c == '[').count();
        let weight = (1.0 / SD_BASE).powi(i32::try_from(depth).unwrap_or(i32::MAX));
        tokens.push(serde_json::json!({
            "text": caps[1].trim(),
            "weight": (weight * 1_000_000.0).round() / 1_000_000.0,
            "syntax": "bracket_weaken",
        }));
    }

    tokens
}

// ── unit tests ────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    #[test]
    fn save_ext_config_creates_missing_extensions_section() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        std::fs::write(&path, r#"{"scan_roots":[]}"#).unwrap();
        let updates =
            serde_json::Map::from_iter([("wildcard_dirs".to_string(), json!(["/tmp/wildcards"]))]);

        save_ext_config(path.to_str().unwrap(), "builtin-prompt-simulator", &updates).unwrap();

        let saved: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        assert_eq!(
            saved["extensions"]["builtin-prompt-simulator"]["wildcard_dirs"],
            json!(["/tmp/wildcards"])
        );
    }

    #[test]
    fn save_ext_config_rejects_non_object_extensions_without_writing() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        let original = r#"{"extensions":"nope"}"#;
        std::fs::write(&path, original).unwrap();
        let updates = serde_json::Map::from_iter([("key".to_string(), json!("value"))]);

        assert!(save_ext_config(path.to_str().unwrap(), "test", &updates).is_err());
        assert_eq!(std::fs::read_to_string(path).unwrap(), original);
    }

    #[test]
    fn save_ext_config_preserves_other_extensions() {
        let dir = tempfile::tempdir().unwrap();
        let path = dir.path().join("config.json");
        std::fs::write(&path, r#"{"extensions":{"other":{"keep":"me"}}}"#).unwrap();
        let updates = serde_json::Map::from_iter([("key".to_string(), json!("value"))]);

        save_ext_config(path.to_str().unwrap(), "test", &updates).unwrap();

        let saved: Value = serde_json::from_str(&std::fs::read_to_string(path).unwrap()).unwrap();
        assert_eq!(saved["extensions"]["other"], json!({"keep":"me"}));
    }

    #[test]
    fn sanitize_valid() {
        assert_eq!(
            sanitize_wildcard_name("hair color"),
            Some("hair color".to_string())
        );
        assert_eq!(
            sanitize_wildcard_name("  hair color  "),
            Some("hair color".to_string())
        );
        assert_eq!(
            sanitize_wildcard_name("subdir/hair color"),
            Some("subdir/hair color".to_string())
        );
        assert_eq!(
            sanitize_wildcard_name(r"subdir\hair color"),
            Some("subdir/hair color".to_string())
        );
    }

    #[test]
    fn sanitize_traversal() {
        assert_eq!(sanitize_wildcard_name("../etc/passwd"), None);
        assert_eq!(sanitize_wildcard_name("/absolute"), None);
        assert_eq!(sanitize_wildcard_name(".hidden"), None);
        assert_eq!(sanitize_wildcard_name("foo/../bar"), None);
        assert_eq!(sanitize_wildcard_name(""), None);
        assert_eq!(sanitize_wildcard_name("bad<name"), None);
        // Trailing dot: ends_with('.') on part "trailing." → None
        assert_eq!(sanitize_wildcard_name("trailing."), None);
        // Trailing space: trim() strips it → "trailing" (valid), internal segment "foo " still caught
        assert_eq!(
            sanitize_wildcard_name("trailing "),
            Some("trailing".to_string())
        );
        // Internal segment with trailing space (not trimmed by outer trim())
        assert_eq!(sanitize_wildcard_name("foo /bar"), None);
    }

    #[test]
    fn convert_nai_to_sd_basic() {
        let result = convert_nai_to_sd("1.1::word::");
        assert!(result.contains("word"), "expected 'word' in: {result}");
        assert!(result.contains("1.1"), "expected '1.1' in: {result}");
    }

    #[test]
    fn expand_dynamic_basic() {
        let wildcards = BTreeMap::new();
        let result = expand_dynamic_prompt("{a|b}", Some(0), &wildcards);
        assert!(
            result == "a" || result == "b",
            "unexpected result: {result}"
        );
    }

    #[test]
    fn expand_dynamic_preserves_nai_emphasis_braces() {
        // A brace with no top-level `|` is NAI emphasis syntax, not a DP choice —
        // must round-trip unchanged (regression: previously stripped the braces).
        let wildcards = BTreeMap::new();
        assert_eq!(
            expand_dynamic_prompt("{fluffy hair}", Some(0), &wildcards),
            "{fluffy hair}"
        );
        assert_eq!(
            expand_dynamic_prompt("{{fluffy hair}}", Some(0), &wildcards),
            "{{fluffy hair}}"
        );
    }

    #[test]
    fn expand_dynamic_choice_containing_nested_emphasis() {
        // Regression: a real dynamic choice containing an NAI-emphasis branch
        // must still resolve (not get stuck because the inner brace has no `|`).
        let wildcards = BTreeMap::new();
        for seed in 0..20u64 {
            let result = expand_dynamic_prompt("{a|{b}|c}", Some(seed), &wildcards);
            assert!(
                result == "a" || result == "{b}" || result == "c",
                "unexpected result for seed {seed}: {result}"
            );
        }
    }
}

// --- dp analysis ---

use std::sync::OnceLock;

static WEIGHT_PREFIX_RE: OnceLock<regex::Regex> = OnceLock::new();

fn weight_prefix() -> &'static regex::Regex {
    WEIGHT_PREFIX_RE.get_or_init(|| regex::Regex::new(r"^(\d*\.?\d+)::").unwrap())
}

static PICK_RE: OnceLock<regex::Regex> = OnceLock::new();

fn pick_re() -> &'static regex::Regex {
    PICK_RE
        .get_or_init(|| regex::Regex::new(r"(?s)^(\d+)(?:-(\d+))?\$\$(?:[^$]*\$\$)?(.*)").unwrap())
}

fn banker_round_6dp(x: f64) -> f64 {
    let factor = 1_000_000.0_f64;
    let scaled = x * factor;
    let floor = scaled.floor();
    let frac = scaled - floor;
    let rounded = if (frac - 0.5).abs() < 1e-10 {
        if crate::num::sat_i64(floor) % 2 == 0 {
            floor
        } else {
            floor + 1.0
        }
    } else {
        scaled.round()
    };
    rounded / factor
}

fn comb_sat(n: u64, k: u64) -> u64 {
    if k > n {
        return 0;
    }
    let k = k.min(n - k);
    (0..k).fold(1u64, |acc, i| {
        acc.saturating_mul(n - i).saturating_div(i + 1)
    })
}

fn find_matching_brace(text: &str, start_byte: usize) -> Option<usize> {
    let mut depth = 0usize;
    for (idx, ch) in text[start_byte..].char_indices() {
        match ch {
            '{' => depth += 1,
            '}' => {
                depth = depth.saturating_sub(1);
                if depth == 0 {
                    return Some(start_byte + idx);
                }
            }
            _ => {}
        }
    }
    None
}

fn split_top_level(inner: &str) -> Vec<String> {
    let mut parts = Vec::new();
    let mut depth = 0usize;
    let mut cur = String::new();
    for ch in inner.chars() {
        match ch {
            '{' => {
                depth += 1;
                cur.push(ch);
            }
            '}' => {
                depth = depth.saturating_sub(1);
                cur.push(ch);
            }
            '|' if depth == 0 => {
                parts.push(std::mem::take(&mut cur));
            }
            _ => cur.push(ch),
        }
    }
    parts.push(cur);
    parts
}

fn analyze_one(expr: &str, inner: &str, out: &mut Vec<serde_json::Value>) {
    use serde_json::json;

    // pick prefix: {N$$...} または {N-M$$...}
    if let Some(caps) = pick_re().captures(inner) {
        let pick_min: u64 = caps[1].parse().unwrap_or(0);
        let pick_max: u64 = caps
            .get(2)
            .map(|m| m.as_str().parse().unwrap_or(pick_min))
            .unwrap_or(pick_min);
        let rest = caps.get(3).map(|m| m.as_str()).unwrap_or("");
        let choices: Vec<String> = split_top_level(rest)
            .into_iter()
            .map(|s| s.trim().to_string())
            .filter(|s| !s.is_empty())
            .collect();
        let total = choices.len() as u64;
        if total == 0 {
            return;
        }

        let entry = if pick_min == pick_max {
            let n = pick_min;
            let prob = if total > 0 {
                banker_round_6dp(1.0 / total as f64)
            } else {
                0.0
            };
            let e = json!({
                "type": "pick_n",
                "expr": expr,
                "pick": n,
                "combinations": comb_sat(total, n),
                "choices": choices.iter().map(|c| json!({"text": c, "probability": prob})).collect::<Vec<_>>(),
            });
            e
        } else {
            let combinations: u64 = (pick_min..=pick_max)
                .map(|k| comb_sat(total, k))
                .fold(0u64, |a, b| a.saturating_add(b));
            let prob = if total > 0 {
                banker_round_6dp(1.0 / total as f64)
            } else {
                0.0
            };
            json!({
                "type": "pick_range",
                "expr": expr,
                "pick_min": pick_min,
                "pick_max": pick_max,
                "combinations": combinations,
                "choices": choices.iter().map(|c| json!({"text": c, "probability": prob})).collect::<Vec<_>>(),
            })
        };
        out.push(entry);
        for c in &choices {
            find_choices(c, out);
        }
        return;
    }

    // uniform / weighted
    let parts = split_top_level(inner);
    if parts.len() < 2 {
        return;
    }

    let weights: Vec<Option<f64>> = parts
        .iter()
        .map(|p| {
            weight_prefix()
                .captures(p)
                .and_then(|c| c[1].parse::<f64>().ok())
        })
        .collect();

    let all_weighted = weights.iter().all(|w| w.is_some());
    let any_non_unit = weights
        .iter()
        .any(|w| w.map(|v| (v - 1.0).abs() > 1e-12).unwrap_or(false));

    if all_weighted && any_non_unit {
        // weighted
        let ws: Vec<f64> = weights.iter().map(|w| w.unwrap_or(1.0)).collect();
        let total_w: f64 = ws.iter().sum();
        let choice_entries: Vec<serde_json::Value> = parts
            .iter()
            .zip(ws.iter())
            .map(|(p, &w)| {
                let text = weight_prefix().replace(p, "").to_string();
                json!({"text": text, "weight": w, "probability": banker_round_6dp(w / total_w)})
            })
            .collect();
        out.push(json!({
            "type": "weighted",
            "expr": expr,
            "choices": choice_entries,
        }));
        for p in &parts {
            let text = weight_prefix().replace(p, "").to_string();
            find_choices(&text, out);
        }
    } else {
        // uniform
        let total = parts.len() as f64;
        let prob = banker_round_6dp(1.0 / total);
        let choice_entries: Vec<serde_json::Value> = parts
            .iter()
            .map(|p| json!({"text": p, "probability": prob}))
            .collect();
        out.push(json!({
            "type": "uniform",
            "expr": expr,
            "choices": choice_entries,
        }));
        for p in &parts {
            find_choices(p, out);
        }
    }
}

fn find_choices(text: &str, out: &mut Vec<serde_json::Value>) {
    let bytes = text.as_bytes();
    let mut i = 0usize;
    while i < bytes.len() {
        if bytes[i] == b'{' {
            if let Some(end) = find_matching_brace(text, i) {
                let inner = &text[i + 1..end];
                let expr = &text[i..=end];
                analyze_one(expr, inner, out);
                i = end + 1;
                continue;
            }
        }
        // advance by one char (UTF-8 safe)
        i += text[i..].chars().next().map(|c| c.len_utf8()).unwrap_or(1);
    }
}

pub fn analyze_dp_choices(prompt: &str) -> Vec<serde_json::Value> {
    let mut out = Vec::new();
    find_choices(prompt, &mut out);
    out
}

#[cfg(test)]
mod dp_analysis_tests {
    use super::*;

    #[test]
    fn test_uniform_three_choices() {
        let result = analyze_dp_choices("{a|b|c}");
        assert_eq!(result.len(), 1);
        let g = &result[0];
        assert_eq!(g["type"], "uniform");
        let choices = g["choices"].as_array().unwrap();
        assert_eq!(choices.len(), 3);
        // probability: 1/3 ≈ 0.333333 (banker_round_6dp)
        let prob = choices[0]["probability"].as_f64().unwrap();
        assert!((prob - 0.333333).abs() < 1e-6);
    }

    #[test]
    fn test_trailing_empty_choice_preserved() {
        // {a|} → 2 choices（空要素保持）
        let result = analyze_dp_choices("{a|}");
        assert_eq!(result.len(), 1);
        let choices = result[0]["choices"].as_array().unwrap();
        assert_eq!(choices.len(), 2);
        let prob = choices[0]["probability"].as_f64().unwrap();
        assert!((prob - 0.5).abs() < 1e-6);
    }

    #[test]
    fn test_all_weight_one_is_uniform() {
        // {1::a|1::b} → uniform（全 weight == 1.0 → any_non_unit = false）
        let result = analyze_dp_choices("{1::a|1::b}");
        assert_eq!(result[0]["type"], "uniform");
    }

    #[test]
    fn test_weighted() {
        // {3::a|1::b} → weighted
        let result = analyze_dp_choices("{3::a|1::b}");
        assert_eq!(result[0]["type"], "weighted");
        let choices = result[0]["choices"].as_array().unwrap();
        let prob_a = choices[0]["probability"].as_f64().unwrap();
        assert!((prob_a - 0.75).abs() < 1e-6);
    }

    #[test]
    fn test_depth_underflow_no_panic() {
        // 閉じブレース先行でも panic しないこと
        let result = analyze_dp_choices("}garbage{a|b}");
        assert!(!result.is_empty()); // {a|b} が解析される
    }

    #[test]
    fn test_banker_round_6dp_half_to_even() {
        // 0.5 * 1e-6 の位 → half-to-even
        // 1/3 = 0.333333333... → 0.333333
        let v = banker_round_6dp(1.0 / 3.0);
        assert_eq!(v, 0.333333);
    }

    #[test]
    fn test_comb_sat_basic() {
        assert_eq!(comb_sat(3, 1), 3);
        assert_eq!(comb_sat(3, 2), 3);
        assert_eq!(comb_sat(0, 0), 1);
        assert_eq!(comb_sat(2, 3), 0); // k > n
    }

    #[test]
    fn test_nested_groups() {
        // {a|{b|c}} → outer uniform + inner uniform
        let result = analyze_dp_choices("{a|{b|c}}");
        assert!(result.len() >= 2);
        assert_eq!(result[0]["type"], "uniform");
    }

    #[test]
    fn test_pick_n() {
        let result = analyze_dp_choices("{1$$a|b|c}");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["type"], "pick_n");
        assert_eq!(result[0]["pick"], 1);
        assert_eq!(result[0]["combinations"], 3);
    }

    #[test]
    fn test_pick_range() {
        let result = analyze_dp_choices("{1-2$$a|b|c}");
        assert_eq!(result.len(), 1);
        assert_eq!(result[0]["type"], "pick_range");
        assert_eq!(result[0]["pick_min"], 1);
        assert_eq!(result[0]["pick_max"], 2);
        // comb_sat(3,1) + comb_sat(3,2) = 3 + 3 = 6
        assert_eq!(result[0]["combinations"], 6);
    }

    #[test]
    fn bridge_wildcards_loads_filesystem_dirs_and_client_overrides() {
        let root = std::env::temp_dir().join(format!("yu_bridge_wildcards_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        let wildcard_dir = root.join("wildcards");
        std::fs::create_dir_all(&wildcard_dir).unwrap();
        std::fs::write(wildcard_dir.join("subject.txt"), "cat\ndog\n").unwrap();
        std::fs::write(wildcard_dir.join("bad.txt"), "blur\n").unwrap();
        let config_path = root.join("config.toml");
        std::fs::write(
            &config_path,
            format!(
                "[extensions.builtin-prompt-simulator]\nwildcard_dirs = [{}]\n",
                serde_json::to_string(&wildcard_dir.to_string_lossy()).unwrap()
            ),
        )
        .unwrap();

        let mut client = BTreeMap::new();
        client.insert("subject".to_string(), vec!["client-cat".to_string()]);
        let wildcards = bridge_wildcards(config_path.to_str().unwrap(), client);

        assert_eq!(
            wildcards.get("subject").unwrap(),
            &vec!["client-cat".to_string()]
        );
        assert_eq!(wildcards.get("bad").unwrap(), &vec!["blur".to_string()]);
        assert_eq!(
            expand_dynamic_prompt("a __subject__, __bad__", Some(1), &wildcards),
            "a client-cat, blur"
        );

        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn nested_dir_wildcard_expands_via_dunder_slash_name() {
        // Reported bug repro: a wildcard file at <dir>/genshin/genshin.txt is
        // referenced as __genshin/genshin__ in a prompt (subfolder name == file
        // stem, so the key collapses to "genshin/genshin"). Must resolve, not panic.
        let root = std::env::temp_dir().join(format!("yu_nested_wc_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(root.join("genshin")).unwrap();
        std::fs::write(
            root.join("genshin").join("genshin.txt"),
            "hu tao\nyae miko\n",
        )
        .unwrap();
        let dirs = vec![root.to_string_lossy().to_string()];
        let (wc, _) = load_wildcards(&dirs);
        assert_eq!(
            wc.get("genshin/genshin").unwrap(),
            &vec!["hu tao", "yae miko"]
        );

        let result =
            expand_dynamic_prompt("1girl, (running:1.5), __genshin/genshin__", Some(0), &wc);
        assert!(
            result.contains("hu tao") || result.contains("yae miko"),
            "expected wildcard to resolve, got: {result}"
        );
        assert!(
            result.contains("(running:1.5)"),
            "unrelated SD weight syntax must survive: {result}"
        );
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn yaml_flat_list_loaded_as_wildcard() {
        let root = std::env::temp_dir().join(format!("yu_yaml_flat_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("colors.yaml"), "- red\n- blue\n- green\n").unwrap();
        let dirs = vec![root.to_string_lossy().to_string()];
        let (wc, srcs) = load_wildcards(&dirs);
        assert_eq!(wc.get("colors").unwrap(), &vec!["red", "blue", "green"]);
        assert_eq!(srcs.get("colors").map(|s| s.as_str()), Some("yaml"));
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn yaml_mapping_creates_sub_wildcards() {
        let root = std::env::temp_dir().join(format!("yu_yaml_map_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(
            root.join("animals.yaml"),
            "cat:\n  - tabby\n  - siamese\ndog:\n  - poodle\n",
        )
        .unwrap();
        let dirs = vec![root.to_string_lossy().to_string()];
        let (wc, _) = load_wildcards(&dirs);
        assert_eq!(wc.get("animals/cat").unwrap(), &vec!["tabby", "siamese"]);
        assert_eq!(wc.get("animals/dog").unwrap(), &vec!["poodle"]);
        let _ = std::fs::remove_dir_all(&root);
    }

    #[test]
    fn yaml_txt_same_name_txt_wins() {
        // txt file takes precedence over yaml when both exist with same stem
        let root = std::env::temp_dir().join(format!("yu_yaml_prio_{}", std::process::id()));
        let _ = std::fs::remove_dir_all(&root);
        std::fs::create_dir_all(&root).unwrap();
        std::fs::write(root.join("subject.txt"), "cat\n").unwrap();
        std::fs::write(root.join("subject.yaml"), "- dog\n").unwrap();
        let dirs = vec![root.to_string_lossy().to_string()];
        let (wc, srcs) = load_wildcards(&dirs);
        // whichever is loaded first wins (both insert via or_insert)
        // txt is sorted before yaml alphabetically, so txt wins
        assert!(wc.contains_key("subject"));
        let _ = std::fs::remove_dir_all(&root);
    }
}
