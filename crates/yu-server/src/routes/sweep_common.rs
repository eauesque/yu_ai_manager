/// Sweep-meta native Rust implementation — PNG XMP write + DB upsert.
/// Shared by SD WebUI bridge and ComfyUI bridge.
/// Replaces Python proxy for sweep_meta post-processing.
use std::collections::{BTreeMap, HashMap};
use std::path::Path;
use std::sync::OnceLock;

use regex::Regex;
use serde_json::{json, Value};
use sqlx::SqlitePool;
use std::time::UNIX_EPOCH;
use tagdb_core::import::fallback_chain;
use tagdb_core::import::persist::persist_regular_scan_result;
use tagdb_core::import::version_authority::{should_rescan, PARSER_VERSION_SENTINEL};
use tagdb_core::CURRENT_PARSER_VERSION;

use crate::state::SharedState;

// ── constants ─────────────────────────────────────────────────────────────────

const PNG_SIG: &[u8; 8] = b"\x89PNG\r\n\x1a\n";
const XMP_KEY: &[u8] = b"XML:com.adobe.xmp";
const SWEEP_NS_URI: &str = "http://ns.yu-ai-manager/sweep/1.0/";
const RDF_NS_URI: &str = "http://www.w3.org/1999/02/22-rdf-syntax-ns#";
// U+FEFF BOM in the xpacket begin attr — matches Python packet.py
const XPACKET_HEADER: &str = "<?xpacket begin=\"\u{FEFF}\" id=\"W5M0MpCehiHzreSzNTczkc9d\"?>\n";
const XPACKET_TRAILER: &str = "\n<?xpacket end=\"w\"?>";
const MACROS_PARAM: &str = "_macros";

// ── CRC32 (IEEE 802.3 / PNG) ─────────────────────────────────────────────────

fn crc32_table() -> &'static [u32; 256] {
    static T: OnceLock<[u32; 256]> = OnceLock::new();
    T.get_or_init(|| {
        let mut t = [0u32; 256];
        for n in 0..256u32 {
            let mut c = n;
            for _ in 0..8 {
                c = if c & 1 != 0 {
                    0xEDB8_8320 ^ (c >> 1)
                } else {
                    c >> 1
                };
            }
            t[n as usize] = c;
        }
        t
    })
}

fn crc32(data: &[u8]) -> u32 {
    let t = crc32_table();
    let mut c = 0xFFFF_FFFFu32;
    for &b in data {
        c = t[((c ^ b as u32) & 0xFF) as usize] ^ (c >> 8);
    }
    c ^ 0xFFFF_FFFF
}

// ── helpers ───────────────────────────────────────────────────────────────────

fn xml_attr_escape(s: &str) -> String {
    s.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
}

/// Replicate Python's {:g} — 6 significant digits, no trailing zeros.
fn fmt_g(v: f64) -> String {
    if v.fract() == 0.0 && v.abs() < 1e15 {
        return format!("{:.0}", v);
    }
    // Determine decimal places needed for 6 significant digits
    let magnitude = if v == 0.0 {
        0
    } else {
        crate::num::sat_i32(v.abs().log10().floor())
    };
    let decimals = usize::try_from((5 - magnitude).max(0)).unwrap_or(0);
    let s = format!("{:.prec$}", v, prec = decimals);
    let s = s.trim_end_matches('0');
    s.trim_end_matches('.').to_string()
}

fn value_g(v: &Value) -> String {
    match v {
        Value::Number(n) => n.as_f64().map(fmt_g).unwrap_or_else(|| n.to_string()),
        Value::String(s) => s.clone(),
        Value::Bool(b) => b.to_string(),
        _ => v.to_string(),
    }
}

fn series_to_str(series: &[Value], param: &str) -> String {
    if param == MACROS_PARAM {
        serde_json::to_string(series).unwrap_or_default()
    } else {
        series.iter().map(value_g).collect::<Vec<_>>().join(",")
    }
}

// ── validated sweep structs ───────────────────────────────────────────────────

pub struct SweepAxis {
    pub param: String,
    pub index: i64,
    pub total: i64,
    pub series: Vec<Value>,
    pub value: Option<Value>,
}

pub struct SweepMeta {
    pub id: String,
    pub bridge: String,
    pub axes: Vec<SweepAxis>,
    pub base_seed: i64,
    pub created_at: i64,
    pub prompt_template: Option<String>,
    pub negative_template: Option<String>,
    pub checkpoint: Option<String>,
    pub vae: Option<String>,
    pub sampler: Option<String>,
    pub width: Option<i64>,
    pub height: Option<i64>,
    pub steps: Option<i64>,
    pub cfg: Option<f64>,
}

pub fn validate_sweep_meta(v: &Value) -> Option<SweepMeta> {
    let obj = v.as_object()?;
    let id = obj.get("id")?.as_str()?.to_string();
    if id.is_empty() {
        return None;
    }
    let bridge = obj.get("bridge")?.as_str()?.to_string();
    if !["nai", "comfyui", "sd-webui"].contains(&bridge.as_str()) {
        return None;
    }
    let axes_raw = obj.get("axes")?.as_array()?;
    if axes_raw.is_empty() || axes_raw.len() > 3 {
        return None;
    }
    let mut axes = Vec::new();
    for ax in axes_raw {
        let ax_obj = ax.as_object()?;
        let param = ax_obj.get("param")?.as_str()?.to_string();
        if param.is_empty() {
            return None;
        }
        let index = ax_obj.get("index").and_then(Value::as_i64).unwrap_or(0);
        let total = ax_obj.get("total").and_then(Value::as_i64).unwrap_or(0);
        if total <= 0 || index < 0 || index >= total {
            return None;
        }
        let series = ax_obj.get("series")?.as_array()?.to_vec();
        let value = ax_obj.get("value").cloned();
        axes.push(SweepAxis {
            param,
            index,
            total,
            series,
            value,
        });
    }
    Some(SweepMeta {
        id,
        bridge,
        axes,
        base_seed: obj.get("base_seed").and_then(Value::as_i64).unwrap_or(-1),
        created_at: obj.get("created_at").and_then(Value::as_i64).unwrap_or(0),
        prompt_template: obj
            .get("prompt_template")
            .and_then(Value::as_str)
            .map(String::from),
        negative_template: obj
            .get("negative_template")
            .and_then(Value::as_str)
            .map(String::from),
        checkpoint: obj
            .get("checkpoint")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .map(String::from),
        vae: obj
            .get("vae")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .map(String::from),
        sampler: obj
            .get("sampler")
            .and_then(Value::as_str)
            .filter(|s| !s.is_empty())
            .map(String::from),
        width: obj.get("width").and_then(Value::as_i64).filter(|&v| v > 0),
        height: obj.get("height").and_then(Value::as_i64).filter(|&v| v > 0),
        steps: obj.get("steps").and_then(Value::as_i64).filter(|&v| v > 0),
        cfg: obj.get("cfg").and_then(Value::as_f64),
    })
}

pub fn sweep_meta_to_attrs(meta: &SweepMeta) -> BTreeMap<String, String> {
    let mut attrs = BTreeMap::new();
    attrs.insert("id".into(), meta.id.clone());
    attrs.insert("bridge".into(), meta.bridge.clone());
    attrs.insert("axis_count".into(), meta.axes.len().to_string());
    attrs.insert("base_seed".into(), meta.base_seed.to_string());
    attrs.insert("created_at".into(), meta.created_at.to_string());
    if let Some(v) = &meta.prompt_template {
        attrs.insert("prompt_template".into(), v.clone());
    }
    if let Some(v) = &meta.negative_template {
        attrs.insert("negative_template".into(), v.clone());
    }
    if let Some(v) = &meta.checkpoint {
        attrs.insert("checkpoint".into(), v.clone());
    }
    if let Some(v) = &meta.vae {
        attrs.insert("vae".into(), v.clone());
    }
    if let Some(v) = &meta.sampler {
        attrs.insert("sampler".into(), v.clone());
    }
    if let Some(v) = meta.width {
        attrs.insert("width".into(), v.to_string());
    }
    if let Some(v) = meta.height {
        attrs.insert("height".into(), v.to_string());
    }
    if let Some(v) = meta.steps {
        attrs.insert("steps".into(), v.to_string());
    }
    if let Some(v) = meta.cfg {
        attrs.insert("cfg".into(), fmt_g(v));
    }
    for (i, ax) in meta.axes.iter().enumerate() {
        let pfx = format!("axis_{i}_");
        attrs.insert(format!("{pfx}param"), ax.param.clone());
        attrs.insert(format!("{pfx}total"), ax.total.to_string());
        attrs.insert(format!("{pfx}index"), ax.index.to_string());
        attrs.insert(format!("{pfx}series"), series_to_str(&ax.series, &ax.param));
        if let Some(v) = &ax.value {
            let s = if ax.param == MACROS_PARAM {
                serde_json::to_string(v).unwrap_or_default()
            } else {
                value_g(v)
            };
            attrs.insert(format!("{pfx}value"), s);
        }
    }
    attrs
}

// ── XMP packet build / merge ──────────────────────────────────────────────────

fn build_fresh_xmp(attrs: &BTreeMap<String, String>) -> String {
    let mut decl = format!("\n      xmlns:sweep=\"{}\"", SWEEP_NS_URI);
    for (k, v) in attrs {
        decl.push_str(&format!("\n      sweep:{}=\"{}\"", k, xml_attr_escape(v)));
    }
    format!(
        "{}<x:xmpmeta xmlns:x=\"adobe:ns:meta/\">\n  <rdf:RDF xmlns:rdf=\"{}\">\n    \
         <rdf:Description{}></rdf:Description>\n  </rdf:RDF>\n</x:xmpmeta>{}",
        XPACKET_HEADER, RDF_NS_URI, decl, XPACKET_TRAILER
    )
}

/// Merge sweep attrs into an existing XMP string.
/// Strips previous sweep: namespace decl + all sweep: attrs, injects new ones.
fn merge_sweep_attrs(existing: &str, attrs: &BTreeMap<String, String>) -> String {
    static SWEEP_NS: OnceLock<Regex> = OnceLock::new();
    static SWEEP_ATTR: OnceLock<Regex> = OnceLock::new();
    static RDF_DESC: OnceLock<Regex> = OnceLock::new();

    let ns_re = SWEEP_NS.get_or_init(|| Regex::new(r#"\s+xmlns:sweep="[^"]*""#).unwrap());
    let attr_re =
        SWEEP_ATTR.get_or_init(|| Regex::new(r#"\s+sweep:[A-Za-z0-9_]+="[^"]*""#).unwrap());
    let desc_re = RDF_DESC.get_or_init(|| Regex::new(r"<rdf:Description").unwrap());

    let stripped = ns_re.replace_all(existing, "");
    let stripped = attr_re.replace_all(&stripped, "");

    if let Some(m) = desc_re.find(&stripped) {
        let pos = m.end();
        let mut inject = format!("\n      xmlns:sweep=\"{}\"", SWEEP_NS_URI);
        for (k, v) in attrs {
            inject.push_str(&format!("\n      sweep:{}=\"{}\"", k, xml_attr_escape(v)));
        }
        format!("{}{}{}", &stripped[..pos], inject, &stripped[pos..])
    } else {
        build_fresh_xmp(attrs)
    }
}

// ── PNG chunk I/O ─────────────────────────────────────────────────────────────

/// `None` when the payload cannot be expressed as a PNG chunk.
///
/// Re-exported from `xmp_core`: this file used to carry a byte-for-byte copy
/// (verified identical, constants included, before removing it). The
/// duplication was not academic -- the u32 length wrap that wrote a corrupt
/// PNG had to be found and fixed in both copies, and the second one only got
/// fixed because the lint happened to point at both.
///
/// `crc32`/`crc32_table` stay here: the IEND writer below still calls them.
pub(crate) use xmp_core::io::png::build_itxt_chunk;

pub(crate) fn read_png_xmp(path: &Path) -> Option<String> {
    let data = std::fs::read(path).ok()?;
    if data.len() < 8 || &data[..8] != PNG_SIG {
        return None;
    }
    let mut pos = 8usize;
    while pos + 12 <= data.len() {
        let length =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
        let type_bytes = &data[pos + 4..pos + 8];
        let chunk_end = pos + 8 + length + 4;
        if chunk_end > data.len() {
            break;
        }
        let cd = &data[pos + 8..pos + 8 + length];

        match type_bytes {
            b"tEXt" => {
                if let Some(n) = cd.iter().position(|&b| b == 0) {
                    if &cd[..n] == XMP_KEY {
                        return String::from_utf8_lossy(&cd[n + 1..]).into_owned().into();
                    }
                }
            }
            b"iTXt" => {
                if let Some(n) = cd.iter().position(|&b| b == 0) {
                    if &cd[..n] == XMP_KEY && cd.len() > n + 3 && cd[n + 1] == 0 {
                        // skip lang_tag and translated_keyword
                        let mut i = n + 3;
                        while i < cd.len() && cd[i] != 0 {
                            i += 1;
                        }
                        i += 1;
                        while i < cd.len() && cd[i] != 0 {
                            i += 1;
                        }
                        i += 1;
                        if i <= cd.len() {
                            return String::from_utf8_lossy(&cd[i..]).into_owned().into();
                        }
                    }
                }
            }
            b"IEND" => break,
            _ => {}
        }
        pos = chunk_end;
    }
    None
}

pub(crate) fn write_png_xmp(path: &Path, xmp_xml: &str) -> std::io::Result<()> {
    let data = std::fs::read(path)?;
    if data.len() < 8 || &data[..8] != PNG_SIG {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidData,
            "not a PNG",
        ));
    }
    let Some(new_chunk) = build_itxt_chunk(xmp_xml) else {
        return Err(std::io::Error::new(
            std::io::ErrorKind::InvalidInput,
            "XMP packet does not fit in a PNG chunk",
        ));
    };
    let mut out: Vec<u8> = PNG_SIG.to_vec();
    let mut pos = 8usize;
    let mut inserted = false;

    while pos + 12 <= data.len() {
        let length =
            u32::from_be_bytes([data[pos], data[pos + 1], data[pos + 2], data[pos + 3]]) as usize;
        let type_bytes = &data[pos + 4..pos + 8];
        let chunk_end = pos + 8 + length + 4;
        if chunk_end > data.len() {
            break;
        }
        let cd = &data[pos + 8..pos + 8 + length];

        // Drop existing XMP text chunks (we'll replace with new one)
        if type_bytes == b"tEXt" || type_bytes == b"iTXt" {
            if let Some(n) = cd.iter().position(|&b| b == 0) {
                if &cd[..n] == XMP_KEY {
                    pos = chunk_end;
                    continue;
                }
            }
        }

        if type_bytes == b"IEND" {
            out.extend_from_slice(&new_chunk);
            out.extend_from_slice(&data[pos..chunk_end]);
            inserted = true;
            break;
        }

        out.extend_from_slice(&data[pos..chunk_end]);
        pos = chunk_end;
    }

    if !inserted {
        out.extend_from_slice(&new_chunk);
        // synthesize IEND
        out.extend_from_slice(&0u32.to_be_bytes());
        out.extend_from_slice(b"IEND");
        out.extend_from_slice(&crc32(b"IEND").to_be_bytes());
    }

    let dir = path.parent().unwrap_or(Path::new("."));
    let tmp = tempfile::Builder::new()
        .prefix(".xmp_")
        .suffix(".tmp")
        .tempfile_in(dir)?;
    let (mut file, tmp_path) = tmp.keep().map_err(|e| e.error)?;
    {
        use std::io::Write;
        file.write_all(&out)?;
    }
    std::fs::rename(&tmp_path, path)
}

// ── public API ────────────────────────────────────────────────────────────────

/// Write sweep XMP metadata to each PNG path. Returns count of successful writes.
/// Non-PNG paths are silently skipped (JPEG/WebP not yet supported).
pub fn write_sweep_xmp_to_paths(paths: &[String], meta: &SweepMeta) -> i32 {
    let attrs = sweep_meta_to_attrs(meta);
    let mut ok = 0i32;
    for path_str in paths {
        let path = Path::new(path_str);
        if path.extension().and_then(|e| e.to_str()) != Some("png") {
            continue; // ponytail: PNG only; JPEG/WebP XMP needs Pillow
        }
        let existing = read_png_xmp(path);
        let xmp = match &existing {
            Some(e) => merge_sweep_attrs(e, &attrs),
            None => build_fresh_xmp(&attrs),
        };
        match write_png_xmp(path, &xmp) {
            Ok(_) => ok += 1,
            Err(e) => tracing::warn!("sweep XMP write failed for {}: {}", path_str, e),
        }
    }
    ok
}

/// Full DB import for bridge-saved image paths — the single choke point all
/// bridge generate/save_batch handlers call immediately after
/// save_images_to_disk. Runs a 3-tier fallback chain per path:
///
/// 1. Rust native full import (scan_one_regular equivalent: metadata
///    extraction, prompt→tags, tags/templates/media_extract_state
///    persistence) via `tagdb_core::import`.
/// 2. Python delegation (`/_internal/bridge/import-paths`) for any path the
///    native tier failed on, when `python_url` is configured.
/// 3. Bare `files` row insert (path/mtime/size only) as the final fallback,
///    marked with `PARSER_VERSION_SENTINEL` so a future scan (Python or
///    Rust) always reprocesses it instead of treating it as done.
///
/// Returns a path -> file_id map (None for paths where even the bare
/// insert failed) so sweep/save_batch callers can deep-link results.
pub async fn upsert_files_from_paths(
    state: &SharedState,
    paths: &[String],
) -> HashMap<String, Option<i64>> {
    let mut results: HashMap<String, Option<i64>> = HashMap::new();
    let mut remaining: Vec<String> = Vec::new();

    for path_str in paths {
        match native_import_one(&state.db, path_str, false).await {
            Ok(file_id) => {
                results.insert(path_str.clone(), Some(file_id));
            }
            Err(e) => {
                tracing::warn!("rust-native import failed for {path_str}, falling back: {e}");
                remaining.push(path_str.clone());
            }
        }
    }

    if !remaining.is_empty() {
        let delegated = import_paths_via_python(state, &remaining).await;
        remaining.retain(|path_str| match delegated.get(path_str) {
            Some(file_id) => {
                results.insert(path_str.clone(), *file_id);
                false
            }
            None => true,
        });
    }

    for path_str in &remaining {
        match bare_upsert_one(&state.db, path_str).await {
            Ok(file_id) => {
                results.insert(path_str.clone(), Some(file_id));
            }
            Err(e) => {
                tracing::warn!("bare file index failed for {path_str}: {e}");
                results.insert(path_str.clone(), None);
            }
        }
    }

    if crate::routes::wd_tagger::auto_tag_on_import_enabled(state) {
        for file_id in results.values().flatten() {
            crate::routes::wd_tagger::schedule_auto_tag_on_import(state.clone(), *file_id);
        }
    }
    results
}

/// Tier 1: Rust-native full import for a single path (should_rescan-gated).
/// `force` bypasses the should_rescan skip check (re-extracts even when
/// mtime/size/parser_version are unchanged). Shared with `scan_native`.
pub(crate) async fn native_import_one(
    pool: &SqlitePool,
    path_str: &str,
    force: bool,
) -> Result<i64, String> {
    let p = std::path::Path::new(path_str);
    let meta = p.metadata().map_err(|e| e.to_string())?;
    let mtime = meta
        .modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let size = meta.len() as i64;

    let mut conn = pool.acquire().await.map_err(|e| e.to_string())?;

    let existing: Option<(i64, i64, i64, i64)> = sqlx::query_as(
        "SELECT id, mtime, size, COALESCE(parser_version, 1) FROM files WHERE path = ?",
    )
    .bind(path_str)
    .fetch_optional(&mut *conn)
    .await
    .map_err(|e| e.to_string())?;

    if let Some((file_id, old_mtime, old_size, old_parser_version)) = existing {
        if !should_rescan(old_mtime, old_size, old_parser_version, mtime, size, force) {
            return Ok(file_id);
        }
    }

    let extracted = fallback_chain::extract_regular_metadata(p);
    if extracted.meta_source == "unknown" {
        // Do not commit an unrecognized result with a "confirmed processed"
        // parser_version. The caller tries Python when configured; standalone
        // mode falls through to a bare sentinel row for a future rescan.
        return Err("fallback_chain returned meta_source=unknown".to_string());
    }
    let (width, height) = fallback_chain::extract_resolution(
        extracted.raw_prompt.as_deref(),
        extracted.raw_meta_json.as_deref(),
    );

    let file_id: i64 = sqlx::query_scalar(
        "INSERT INTO files(path, mtime, size, meta_source, is_deleted, is_zip_member,
                           parser_version, width, height)
         VALUES(?, ?, ?, ?, 0, 0, ?, ?, ?)
         ON CONFLICT(path) DO UPDATE SET
           mtime          = excluded.mtime,
           size           = excluded.size,
           meta_source    = excluded.meta_source,
           is_deleted     = 0,
           parser_version = excluded.parser_version,
           width          = COALESCE(excluded.width, files.width),
           height         = COALESCE(excluded.height, files.height)
         RETURNING id",
    )
    .bind(path_str)
    .bind(mtime)
    .bind(size)
    .bind(&extracted.meta_source)
    .bind(CURRENT_PARSER_VERSION)
    .bind(width)
    .bind(height)
    .fetch_one(&mut *conn)
    .await
    .map_err(|e| e.to_string())?;

    persist_regular_scan_result(&mut conn, file_id, &extracted, mtime, true)
        .await
        .map_err(|e| e.to_string())?;

    Ok(file_id)
}

/// Tier 3: bare `files` row insert (no metadata/tags), marked with the
/// parser_version sentinel so a future scan always reprocesses this row.
pub(crate) async fn bare_upsert_one(pool: &SqlitePool, path_str: &str) -> Result<i64, String> {
    let p = std::path::Path::new(path_str);
    let meta = p.metadata().map_err(|e| e.to_string())?;
    let mtime = meta
        .modified()
        .ok()
        .and_then(|t| t.duration_since(UNIX_EPOCH).ok())
        .map(|d| d.as_secs() as i64)
        .unwrap_or(0);
    let size = meta.len() as i64;

    sqlx::query_scalar(
        "INSERT INTO files(path, mtime, size, is_deleted, is_zip_member, parser_version)
         VALUES(?, ?, ?, 0, 0, ?)
         ON CONFLICT(path) DO UPDATE SET
           mtime = excluded.mtime,
           size = excluded.size,
           is_deleted = 0
         RETURNING id",
    )
    .bind(path_str)
    .bind(mtime)
    .bind(size)
    .bind(PARSER_VERSION_SENTINEL)
    .fetch_one(pool)
    .await
    .map_err(|e| e.to_string())
}

/// Import bridge-saved image paths through the Python scanner pipeline.
///
/// Rust bridge generate/save_batch handlers call this immediately after writing images.
/// The loopback Python endpoint runs scan_one_regular-equivalent import work, including
/// tag extraction, width/height, and meta_source. When python_url is not configured
/// (standalone Rust), this returns an empty map so callers can fall back to the legacy
/// bare upsert_files_from_paths path.
pub async fn import_paths_via_python(
    state: &SharedState,
    paths: &[String],
) -> HashMap<String, Option<i64>> {
    if paths.is_empty() || state.config.python_url.trim().is_empty() {
        return HashMap::new();
    }

    let url = format!(
        "{}/_internal/bridge/import-paths",
        state.config.python_url.trim_end_matches('/')
    );
    let Ok(response) = state
        .python_client
        .post(&url)
        .json(&json!({ "paths": paths }))
        .send()
        .await
    else {
        return HashMap::new();
    };
    if !response.status().is_success() {
        return HashMap::new();
    }

    let Ok(payload) = response.json::<Value>().await else {
        return HashMap::new();
    };
    let Some(mapping) = payload.get("mapping").and_then(Value::as_object) else {
        return HashMap::new();
    };

    mapping
        .iter()
        .map(|(path, file_id)| (path.clone(), file_id.as_i64()))
        .collect()
}

pub fn saved_items_from_file_ids(
    paths: &[String],
    file_ids: &HashMap<String, Option<i64>>,
) -> Vec<Value> {
    paths
        .iter()
        .map(|path| json!({"path": path, "file_id": file_ids.get(path).copied().flatten()}))
        .collect()
}

pub async fn upsert_sweep_db(pool: &SqlitePool, meta: &SweepMeta, paths: &[String]) {
    let now = chrono::Utc::now().timestamp();
    let created_at = if meta.created_at > 0 {
        meta.created_at
    } else {
        now
    };
    let axis_count = meta.axes.len() as i64;
    let file_count = paths.len() as i64;

    // Best-effort: resolve file_ids for first/last path if already indexed
    let first_id: Option<i64> = if !paths.is_empty() {
        sqlx::query_scalar("SELECT id FROM files WHERE path = ?")
            .bind(&paths[0])
            .fetch_optional(pool)
            .await
            .unwrap_or(None)
    } else {
        None
    };
    let last_id: Option<i64> = if paths.len() <= 1 {
        first_id
    } else {
        sqlx::query_scalar("SELECT id FROM files WHERE path = ?")
            .bind(paths.last().unwrap())
            .fetch_optional(pool)
            .await
            .unwrap_or(None)
    };

    let r = sqlx::query(
        r#"
        INSERT INTO sweeps (
            id, bridge, base_seed, created_at,
            prompt_template, negative_template,
            checkpoint, vae, sampler,
            width, height, steps, cfg,
            axis_count, first_file_id, last_file_id,
            file_count, status, updated_at
        ) VALUES (
            ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?,
            ?, ?, ?,
            ?, 'completed', ?
        )
        ON CONFLICT(id) DO UPDATE SET
            last_file_id  = COALESCE(excluded.last_file_id, sweeps.last_file_id),
            first_file_id = COALESCE(sweeps.first_file_id, excluded.first_file_id),
            file_count    = sweeps.file_count + excluded.file_count,
            updated_at    = excluded.updated_at
        "#,
    )
    .bind(&meta.id)
    .bind(&meta.bridge)
    .bind(meta.base_seed)
    .bind(created_at)
    .bind(&meta.prompt_template)
    .bind(&meta.negative_template)
    .bind(&meta.checkpoint)
    .bind(&meta.vae)
    .bind(&meta.sampler)
    .bind(meta.width)
    .bind(meta.height)
    .bind(meta.steps)
    .bind(meta.cfg)
    .bind(axis_count)
    .bind(first_id) // first_file_id
    .bind(last_id) // last_file_id
    .bind(file_count)
    .bind(now)
    .execute(pool)
    .await;

    if let Err(e) = r {
        tracing::warn!("sweep DB upsert failed for {}: {}", meta.id, e);
        return;
    }

    for (i, ax) in meta.axes.iter().enumerate() {
        let _ = sqlx::query(
            "INSERT OR IGNORE INTO sweep_axes \
             (sweep_id, axis_index, param, total) VALUES (?, ?, ?, ?)",
        )
        .bind(&meta.id)
        .bind(i as i64)
        .bind(&ax.param)
        .bind(ax.total)
        .execute(pool)
        .await;
    }
}
