use axum::{
    body::Body,
    extract::{Extension, Query, State},
    http::{Request, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::json;
use sqlx::{QueryBuilder, Row, Sqlite};

use crate::{
    auth::{scope::require_admin_scope, AuthContext},
    config_io::load as load_config_json,
    groups_index::GroupsIndex,
    routes::tag_reads::{
        active_model as wd_active_model_name, resolve_model_id_readonly as resolve_wd_model_db_id,
    },
    routes::wd_tagger_normalize::{normalize_tag_name, normalize_tag_name_canonical},
    state::SharedState,
};

fn admin_scope_error(
    state: &SharedState,
    auth_context: Option<&Extension<AuthContext>>,
) -> Option<Response> {
    require_admin_scope(state.config.pin_auth_enabled, auth_context.map(|c| &c.0))
}

fn safe_int(s: Option<&str>, default: i64) -> i64 {
    match s {
        None | Some("") => default,
        Some(v) => v.trim().parse::<i64>().unwrap_or(default).max(0),
    }
}

fn safe_uint(s: Option<&str>, default: u64) -> u64 {
    match s {
        None | Some("") => default,
        Some(v) => {
            u64::try_from(v.trim().parse::<i64>().unwrap_or(default as i64).max(0)).unwrap_or(0)
        }
    }
}

fn safe_isdigit(s: Option<&str>) -> Option<i64> {
    let v = s?.trim();
    if !v.is_empty() && v.chars().all(|c| c.is_ascii_digit()) {
        v.parse().ok()
    } else {
        None
    }
}

fn parse_bool(s: Option<&str>, default: bool) -> bool {
    match s.map(|v| v.trim().to_lowercase()).as_deref() {
        Some("1") | Some("true") | Some("yes") | Some("on") => true,
        Some(_) => false,
        None => default,
    }
}

fn first_alias<'a>(values: &[Option<&'a str>]) -> Option<&'a str> {
    values.iter().find_map(|v| *v)
}

// ── SearchQueryRaw (axum Query extractor) ────────────────────────────────

#[derive(Debug, Deserialize, Default, Clone)]
pub struct SearchQueryRaw {
    q: Option<String>,
    query: Option<String>,
    tag: Option<String>,
    tags: Option<String>,
    artist: Option<String>,
    a: Option<String>,
    from: Option<String>,
    start: Option<String>,
    start_date: Option<String>,
    to: Option<String>,
    end: Option<String>,
    end_date: Option<String>,
    from_ts: Option<String>,
    start_ts: Option<String>,
    to_ts: Option<String>,
    end_ts: Option<String>,
    in_prompt: Option<String>,
    prompt: Option<String>,
    in_negative: Option<String>,
    negative: Option<String>,
    in_char_negative: Option<String>,
    char_negative: Option<String>,
    in_char_positive: Option<String>,
    char_positive: Option<String>,
    format: Option<String>,
    file_format: Option<String>,
    #[serde(rename = "type")]
    file_type: Option<String>,
    format_exts: Option<String>,
    exts: Option<String>,
    extensions: Option<String>,
    sort: Option<String>,
    sort_by: Option<String>,
    order: Option<String>,
    limit: Option<String>,
    n: Option<String>,
    page_size: Option<String>,
    offset: Option<String>,
    skip: Option<String>,
    cursor: Option<String>,
    after: Option<String>,
    in_prompt_regex: Option<String>,
    prompt_regex: Option<String>,
    regex_prompt: Option<String>,
    tag_regex: Option<String>,
    q_regex: Option<String>,
    regex: Option<String>,
    tag_case: Option<String>,
    case_sensitive: Option<String>,
    model_filter: Option<String>,
    model_type: Option<String>,
    checkpoint: Option<String>,
    ckpt: Option<String>,
    in_path: Option<String>,
    path: Option<String>,
    or_tags: Option<String>,
    tags_or: Option<String>,
    also_path: Option<String>,
    search_path: Option<String>,
    fav_only: Option<String>,
    favorites: Option<String>,
    ai_analyzed: Option<String>,
    has_tags: Option<String>,
    tagged: Option<String>,
    has_annotation: Option<String>,
    has_sweep: Option<String>,
    sweep_only: Option<String>,
    collection_id: Option<String>,
    coll: Option<String>,
    min_rating: Option<String>,
    rating_min: Option<String>,
    max_rating: Option<String>,
    rating_max: Option<String>,
    min_width: Option<String>,
    w_min: Option<String>,
    max_width: Option<String>,
    w_max: Option<String>,
    min_height: Option<String>,
    h_min: Option<String>,
    max_height: Option<String>,
    h_max: Option<String>,
    wd_model: Option<String>,
    wd_tagger_model: Option<String>,
}

// ── SearchParams (parsed, normalized) ────────────────────────────────────

#[derive(Debug)]
pub struct SearchParams {
    pub tag_query: String,
    pub artist: String,
    pub from_date: String,
    pub to_date: String,
    pub from_ts: Option<i64>,
    pub to_ts: Option<i64>,
    pub in_prompt: String,
    pub in_negative: String,
    pub in_char_negative: String,
    pub in_char_positive: String,
    pub file_format: String,
    pub format_exts: String,
    pub sort_by: String,
    pub limit: u32,
    pub offset: u64,
    pub cursor: String,
    pub in_prompt_regex: bool,
    pub tag_query_regex: bool,
    pub tag_query_case_sensitive: bool,
    pub model_filter: String,
    pub checkpoint_filter: String,
    pub in_path: String,
    pub or_tags: String,
    pub wd_model: String,
    pub also_path: bool,
    pub fav_only: bool,
    pub ai_analyzed: bool,
    pub has_tags: bool,
    pub has_annotation: bool,
    pub has_sweep: bool,
    pub collection_id: i64,
    pub min_rating: Option<i64>,
    pub max_rating: Option<i64>,
    pub min_width: Option<i64>,
    pub max_width: Option<i64>,
    pub min_height: Option<i64>,
    pub max_height: Option<i64>,
}

impl From<SearchQueryRaw> for SearchParams {
    fn from(r: SearchQueryRaw) -> Self {
        let tag_query = first_alias(&[
            r.q.as_deref(),
            r.query.as_deref(),
            r.tag.as_deref(),
            r.tags.as_deref(),
        ])
        .unwrap_or_default()
        .trim()
        .to_string();

        let limit_raw = first_alias(&[r.limit.as_deref(), r.n.as_deref(), r.page_size.as_deref()]);
        let limit = u32::try_from(safe_int(limit_raw, 100).clamp(1, 2000)).unwrap_or(100);

        SearchParams {
            tag_query,
            artist: first_alias(&[r.artist.as_deref(), r.a.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            from_date: first_alias(&[
                r.from.as_deref(),
                r.start.as_deref(),
                r.start_date.as_deref(),
            ])
            .unwrap_or_default()
            .trim()
            .to_string(),
            to_date: first_alias(&[r.to.as_deref(), r.end.as_deref(), r.end_date.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            from_ts: first_alias(&[r.from_ts.as_deref(), r.start_ts.as_deref()])
                .and_then(|v| v.trim().parse::<i64>().ok()),
            to_ts: first_alias(&[r.to_ts.as_deref(), r.end_ts.as_deref()])
                .and_then(|v| v.trim().parse::<i64>().ok()),
            in_prompt: first_alias(&[r.in_prompt.as_deref(), r.prompt.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            in_negative: first_alias(&[r.in_negative.as_deref(), r.negative.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            in_char_negative: first_alias(&[
                r.in_char_negative.as_deref(),
                r.char_negative.as_deref(),
            ])
            .unwrap_or_default()
            .trim()
            .to_string(),
            in_char_positive: first_alias(&[
                r.in_char_positive.as_deref(),
                r.char_positive.as_deref(),
            ])
            .unwrap_or_default()
            .trim()
            .to_string(),
            file_format: first_alias(&[
                r.format.as_deref(),
                r.file_format.as_deref(),
                r.file_type.as_deref(),
            ])
            .unwrap_or("all")
            .trim()
            .to_string(),
            format_exts: first_alias(&[
                r.format_exts.as_deref(),
                r.exts.as_deref(),
                r.extensions.as_deref(),
            ])
            .unwrap_or_default()
            .trim()
            .to_string(),
            sort_by: first_alias(&[r.sort.as_deref(), r.sort_by.as_deref(), r.order.as_deref()])
                .unwrap_or("date")
                .trim()
                .to_string(),
            limit,
            offset: safe_uint(first_alias(&[r.offset.as_deref(), r.skip.as_deref()]), 0),
            cursor: first_alias(&[r.cursor.as_deref(), r.after.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            in_prompt_regex: parse_bool(
                first_alias(&[
                    r.in_prompt_regex.as_deref(),
                    r.prompt_regex.as_deref(),
                    r.regex_prompt.as_deref(),
                ]),
                false,
            ),
            tag_query_regex: parse_bool(
                first_alias(&[
                    r.tag_regex.as_deref(),
                    r.q_regex.as_deref(),
                    r.regex.as_deref(),
                ]),
                false,
            ),
            tag_query_case_sensitive: parse_bool(
                first_alias(&[r.tag_case.as_deref(), r.case_sensitive.as_deref()]),
                false,
            ),
            model_filter: first_alias(&[r.model_filter.as_deref(), r.model_type.as_deref()])
                .unwrap_or("all")
                .trim()
                .to_string(),
            checkpoint_filter: first_alias(&[r.checkpoint.as_deref(), r.ckpt.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            in_path: first_alias(&[r.in_path.as_deref(), r.path.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            or_tags: first_alias(&[r.or_tags.as_deref(), r.tags_or.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            wd_model: first_alias(&[r.wd_model.as_deref(), r.wd_tagger_model.as_deref()])
                .unwrap_or_default()
                .trim()
                .to_string(),
            also_path: parse_bool(
                first_alias(&[r.also_path.as_deref(), r.search_path.as_deref()]),
                true,
            ),
            fav_only: parse_bool(
                first_alias(&[r.fav_only.as_deref(), r.favorites.as_deref()]),
                false,
            ),
            ai_analyzed: parse_bool(r.ai_analyzed.as_deref(), false),
            has_tags: parse_bool(
                first_alias(&[r.has_tags.as_deref(), r.tagged.as_deref()]),
                false,
            ),
            has_annotation: parse_bool(r.has_annotation.as_deref(), false),
            has_sweep: parse_bool(
                first_alias(&[r.has_sweep.as_deref(), r.sweep_only.as_deref()]),
                false,
            ),
            collection_id: safe_int(
                first_alias(&[r.collection_id.as_deref(), r.coll.as_deref()]),
                0,
            ),
            min_rating: safe_isdigit(first_alias(&[
                r.min_rating.as_deref(),
                r.rating_min.as_deref(),
            ])),
            max_rating: safe_isdigit(first_alias(&[
                r.max_rating.as_deref(),
                r.rating_max.as_deref(),
            ])),
            min_width: safe_isdigit(first_alias(&[r.min_width.as_deref(), r.w_min.as_deref()])),
            max_width: safe_isdigit(first_alias(&[r.max_width.as_deref(), r.w_max.as_deref()])),
            min_height: safe_isdigit(first_alias(&[r.min_height.as_deref(), r.h_min.as_deref()])),
            max_height: safe_isdigit(first_alias(&[r.max_height.as_deref(), r.h_max.as_deref()])),
        }
    }
}

// ── handler stubs (SQL implementation in later tasks) ────────────────────

// ── helpers ───────────────────────────────────────────────────────────────────

fn path_fts_phrase(text: &str) -> Option<String> {
    let cleaned = text.trim();
    if cleaned.chars().count() < 3 {
        return None;
    }
    Some(format!("\"{}\"", cleaned.replace('"', "\"\"")))
}

fn escape_like(text: &str) -> String {
    text.replace('\\', "\\\\")
        .replace('%', "\\%")
        .replace('_', "\\_")
}

fn like_sub(text: &str) -> String {
    format!("%{}%", escape_like(text))
}

pub fn has_conditions(p: &SearchParams) -> bool {
    !p.tag_query.is_empty()
        || !p.artist.is_empty()
        || !p.from_date.is_empty()
        || !p.to_date.is_empty()
        || !p.in_prompt.is_empty()
        || !p.in_negative.is_empty()
        || !p.in_char_negative.is_empty()
        || !p.in_char_positive.is_empty()
        || !p.checkpoint_filter.is_empty()
        || p.from_ts.is_some()
        || p.to_ts.is_some()
        || p.file_format != "all"
        || !p.format_exts.is_empty()
        || p.model_filter != "all"
        || p.fav_only
        || p.collection_id != 0
        || !p.in_path.is_empty()
        || p.ai_analyzed
        || p.has_tags
        || p.has_annotation
        || p.has_sweep
        || p.min_rating.is_some()
        || p.max_rating.is_some()
        || !p.wd_model.is_empty()
}

fn validate_iso_date(s: &str) -> bool {
    let b = s.as_bytes();
    b.len() == 10
        && b[4] == b'-'
        && b[7] == b'-'
        && b.iter().enumerate().all(|(i, &c)| {
            if i == 4 || i == 7 {
                true
            } else {
                c.is_ascii_digit()
            }
        })
}

fn parse_a1111_prompt(raw: &str) -> (String, String) {
    if !raw.contains("Steps:") && !raw.contains("Negative prompt:") {
        return (raw.to_string(), String::new());
    }
    let lines: Vec<&str> = raw.split('\n').collect();
    let mut pos: Vec<&str> = Vec::new();
    let mut neg: Vec<String> = Vec::new();
    let mut i = 0;
    while i < lines.len() {
        let t = lines[i].trim();
        if t.starts_with("Negative prompt:") || t.starts_with("Steps:") {
            break;
        }
        pos.push(lines[i]);
        i += 1;
    }
    if i < lines.len() && lines[i].trim().starts_with("Negative prompt:") {
        let first = lines[i].trim()["Negative prompt:".len()..]
            .trim()
            .to_string();
        if !first.is_empty() {
            neg.push(first);
        }
        i += 1;
        while i < lines.len() && !lines[i].trim().starts_with("Steps:") {
            neg.push(lines[i].trim().to_string());
            i += 1;
        }
    }
    (
        pos.join("\n").trim().to_string(),
        neg.join("\n").trim().to_string(),
    )
}

async fn active_wd_model_id(db: &sqlx::SqlitePool) -> Option<i64> {
    // Bug fix: this previously queried a nonexistent `wd_models` table
    // (always None, silently disabling ai_analyzed's active-model scoping).
    // The active model lives in kv_state, resolved to a db id via wd_model_dict
    // — the same lookup tag_reads::active_model / resolve_model_id_readonly use.
    let model = wd_active_model_name(db).await?;
    resolve_wd_model_db_id(db, &model).await.ok().flatten()
}

// The WD-tagger model scope resolved from the wd_model search param.
#[derive(Debug, Clone, Copy, PartialEq)]
enum WdModelScope {
    /// No wd_model override and no active model set — WD tags are not
    /// matched at all (neither the tag_query OR clause nor a standalone
    /// filter); preserves the prior no-op behavior for unrelated searches.
    Unset,
    /// wd_model="all" — match tags/files from any model.
    Any,
    /// wd_model=<name> (or the active model) resolved to this db id.
    Model(i64),
    /// wd_model=<name> was given but does not exist in wd_model_dict —
    /// must match nothing, not "no filter" (distinct from Unset).
    NoMatch,
}

async fn resolve_wd_tag_search_model(db: &sqlx::SqlitePool, wd_model_param: &str) -> WdModelScope {
    if wd_model_param.eq_ignore_ascii_case("all") {
        return WdModelScope::Any;
    }
    if !wd_model_param.is_empty() {
        return match resolve_wd_model_db_id(db, wd_model_param).await {
            Ok(Some(id)) => WdModelScope::Model(id),
            _ => WdModelScope::NoMatch,
        };
    }
    match active_wd_model_id(db).await {
        Some(id) => WdModelScope::Model(id),
        None => WdModelScope::Unset,
    }
}

pub(crate) async fn table_exists(db: &sqlx::SqlitePool, name: &str) -> Result<bool, sqlx::Error> {
    sqlx::query_scalar::<_, bool>(
        "SELECT EXISTS(SELECT 1 FROM sqlite_master WHERE type='table' AND name=?)",
    )
    .bind(name)
    .fetch_one(db)
    .await
}

async fn collection_exists(db: &sqlx::SqlitePool, id: i64) -> bool {
    sqlx::query_scalar::<_, i64>("SELECT 1 FROM collections WHERE id=? LIMIT 1")
        .bind(id)
        .fetch_optional(db)
        .await
        .ok()
        .flatten()
        .is_some()
}

// ── SQL ビルダ ─────────────────────────────────────────────────────────────────

fn apply_format_filter(qb: &mut QueryBuilder<'_, Sqlite>, file_format: &str, format_exts: &str) {
    let ff = if file_format.is_empty() || file_format == "all" {
        ""
    } else {
        file_format
    };
    let clause: &str = match ff {
        "image" => "f.file_ext IN ('.png','.jpg','.jpeg','.webp','.gif','.bmp','.tif','.tiff','.avif','.heif','.heic','.jxl','.svg')",
        "video" => "(f.file_ext IN ('.webm','.mp4','.mov','.m4v','.avi','.mkv','.ogv','.ts','.m2ts') OR f.meta_source LIKE '%webm%' OR f.meta_source LIKE 'media_video_%')",
        "audio" => "(f.file_ext IN ('.mp3','.wav','.ogg','.opus','.m4a','.aac','.flac') OR f.meta_source LIKE 'media_audio_%')",
        "webm"  => "(f.file_ext = '.webm' OR f.meta_source LIKE '%webm%')",
        "mp4"   => "f.file_ext = '.mp4'",
        "gif"   => "f.file_ext = '.gif'",
        "zip_member" => "(f.path LIKE '%.zip!%' OR f.path LIKE '%.7z!%')",
        "png"   => "(f.file_ext = '.png' OR f.meta_source LIKE '%png%')",
        "webp"  => "(f.file_ext = '.webp' OR f.meta_source LIKE '%webp%')",
        "jpg" | "jpeg" => "f.file_ext IN ('.jpg','.jpeg')",
        "avif"  => "f.file_ext = '.avif'",
        "jxl"   => "f.file_ext = '.jxl'",
        "heif" | "heic" => "f.file_ext IN ('.heif','.heic')",
        "svg"   => "f.file_ext = '.svg'",
        _ => "",
    };
    if !clause.is_empty() {
        qb.push(" AND ").push(clause);
    }
    if format_exts.is_empty() {
        return;
    }
    let mut seen = std::collections::HashSet::new();
    let exts: Vec<String> = format_exts
        .split(',')
        .filter_map(|s| {
            let s = s.trim().to_lowercase();
            if !s.is_empty()
                && s.len() <= 8
                && s.chars().all(|c| c.is_ascii_alphanumeric())
                && seen.insert(s.clone())
            {
                Some(s)
            } else {
                None
            }
        })
        .collect();
    if exts.is_empty() {
        return;
    }
    let terms: Vec<String> = exts
        .iter()
        .map(|e| match e.as_str() {
            "zip" => "f.path LIKE '%.zip!%'".to_string(),
            "7z" => "f.path LIKE '%.7z!%'".to_string(),
            _ => format!("f.file_ext = '.{}'", e),
        })
        .collect();
    qb.push(" AND (").push(terms.join(" OR ")).push(")");
}

fn push_wd_tag_or_clause(
    qb: &mut QueryBuilder<'_, Sqlite>,
    tag_query: &str,
    wd_search_model: WdModelScope,
) {
    let model_id = match wd_search_model {
        WdModelScope::Unset | WdModelScope::NoMatch => return,
        WdModelScope::Any => None,
        WdModelScope::Model(id) => Some(id),
    };
    let normalized = normalize_tag_name_canonical(&normalize_tag_name(tag_query));
    if normalized.is_empty() {
        return;
    }
    match model_id {
        Some(model_id) => {
            qb.push(" OR EXISTS(SELECT 1 FROM file_wd_tags fwt JOIN wd_tag_dict td ON td.id=fwt.tag_id WHERE fwt.file_id=f.id AND fwt.model_id=")
                .push_bind(model_id)
                .push(" AND td.tag_name_normalized=")
                .push_bind(normalized)
                .push(")");
        }
        None => {
            qb.push(" OR EXISTS(SELECT 1 FROM file_wd_tags fwt JOIN wd_tag_dict td ON td.id=fwt.tag_id WHERE fwt.file_id=f.id AND td.tag_name_normalized=")
                .push_bind(normalized)
                .push(")");
        }
    }
}

// Standalone AND filter: restrict to files that have at least one WD-tagger
// tag from the resolved model scope. Independent of tag_query — without this,
// selecting a WD Model with no tag typed had no effect at all (bug report:
// picking a model didn't narrow results), because push_wd_tag_or_clause only
// ran inside the tag_query block above.
fn push_wd_model_filter(qb: &mut QueryBuilder<'_, Sqlite>, wd_search_model: WdModelScope) {
    match wd_search_model {
        WdModelScope::Unset => {}
        WdModelScope::NoMatch => {
            qb.push(" AND 0=1");
        }
        WdModelScope::Any => {
            qb.push(" AND EXISTS(SELECT 1 FROM file_wd_tags fwt WHERE fwt.file_id=f.id)");
        }
        WdModelScope::Model(id) => {
            qb.push(" AND EXISTS(SELECT 1 FROM file_wd_tags fwt WHERE fwt.file_id=f.id AND fwt.model_id=")
                .push_bind(id)
                .push(")");
        }
    }
}

fn push_where_filters(
    qb: &mut QueryBuilder<'_, Sqlite>,
    p: &SearchParams,
    active_wd: Option<i64>,
    wd_search_model: WdModelScope,
    include_templates: bool,
) {
    qb.push(" AND f.is_deleted=0");

    // tag_query（regex mode は SQL フィルタをスキップし Rust 側で処理）
    if !p.tag_query.is_empty() && !p.tag_query_regex {
        let fts_phrase = if p.also_path {
            path_fts_phrase(&p.tag_query)
        } else {
            None
        };
        qb.push(" AND (");
        if p.tag_query_case_sensitive {
            qb.push("EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.file_id=f.id AND t.tag=")
                .push_bind(p.tag_query.clone())
                .push(")");
        } else {
            let lc = p.tag_query.to_lowercase();
            qb.push("EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.file_id=f.id AND LOWER(t.tag)=")
                .push_bind(lc)
                .push(")");
        }
        if let Some(phrase) = fts_phrase {
            qb.push(" OR f.id IN (SELECT rowid FROM files_path_fts WHERE path MATCH ")
                .push_bind(phrase)
                .push(")");
        }
        push_wd_tag_or_clause(qb, &p.tag_query, wd_search_model);
        qb.push(")");
    }

    push_wd_model_filter(qb, wd_search_model);

    // artist
    if !p.artist.is_empty() {
        let base = p.artist.trim_start_matches('@').trim().to_string();
        if !base.is_empty() {
            let at_tag = format!("@{}", base);
            qb.push(" AND EXISTS(SELECT 1 FROM file_tags ft JOIN tags t ON t.id=ft.tag_id WHERE ft.file_id=f.id AND ((t.namespace='artist' AND LOWER(t.tag)=LOWER(")
              .push_bind(base)
              .push(")) OR ((t.namespace IS NULL OR t.namespace='') AND LOWER(t.tag)=LOWER(")
              .push_bind(at_tag)
              .push("))))");
        }
    }

    // 日付フィルタ（from_ts が優先）
    if let Some(ts) = p.from_ts {
        qb.push(" AND f.mtime>=").push_bind(ts);
    } else if !p.from_date.is_empty() {
        qb.push(" AND f.mtime >= CAST(strftime('%s', ")
            .push_bind(p.from_date.clone())
            .push(" || ' 00:00:00', 'utc') AS INTEGER)");
    }
    if let Some(ts) = p.to_ts {
        qb.push(" AND f.mtime<=").push_bind(ts);
    } else if !p.to_date.is_empty() {
        qb.push(" AND f.mtime <= CAST(strftime('%s', ")
            .push_bind(p.to_date.clone())
            .push(" || ' 23:59:59', 'utc') AS INTEGER)");
    }

    // prompt/negative LIKE（templates JOIN 有効時のみ）
    // regex mode: skip SQL LIKE — Rust regex post-filter handles matching
    if include_templates {
        if !p.in_prompt.is_empty() && !p.in_prompt_regex {
            qb.push(" AND tm.raw_prompt LIKE ? ESCAPE '\\'")
                .push_bind(like_sub(&p.in_prompt));
        }
        if !p.in_negative.is_empty() {
            qb.push(" AND tm.raw_negative LIKE ? ESCAPE '\\'")
                .push_bind(like_sub(&p.in_negative));
        }
        if !p.in_char_positive.is_empty() {
            qb.push(" AND tm.raw_prompt LIKE ? ESCAPE '\\'")
                .push_bind(like_sub(&p.in_char_positive));
        }
        if !p.in_char_negative.is_empty() {
            qb.push(" AND tm.raw_negative LIKE ? ESCAPE '\\'")
                .push_bind(like_sub(&p.in_char_negative));
        }
    }

    // file_format / format_exts
    apply_format_filter(qb, &p.file_format, &p.format_exts);

    // model_filter（パラメータなし固定 SQL）
    if p.model_filter != "all" && !p.model_filter.is_empty() {
        let mut conds: Vec<&str> = Vec::new();
        for mf in p.model_filter.split(',').map(str::trim) {
            match mf {
                "sd" => {
                    conds.push("(f.meta_source LIKE '%a1111%' OR f.meta_source LIKE '%forge%')")
                }
                "nai" => conds.push("f.meta_source LIKE '%novel%'"),
                "comfy" => conds.push("f.meta_source LIKE '%comfy%'"),
                "tensor" => conds.push("f.meta_source LIKE '%tensor%'"),
                "unknown" => conds.push("(f.meta_source IS NULL OR f.meta_source = '')"),
                _ => {}
            }
        }
        if !conds.is_empty() {
            qb.push(" AND (").push(conds.join(" OR ")).push(")");
        }
    }

    // 解像度
    if let Some(v) = p.min_width {
        qb.push(" AND f.width>=").push_bind(v);
    }
    if let Some(v) = p.max_width {
        qb.push(" AND f.width<=").push_bind(v);
    }
    if let Some(v) = p.min_height {
        qb.push(" AND f.height>=").push_bind(v);
    }
    if let Some(v) = p.max_height {
        qb.push(" AND f.height<=").push_bind(v);
    }

    // rating（rt JOIN は外側で行われる）
    match (p.min_rating, p.max_rating) {
        (Some(lo), Some(hi)) => {
            qb.push(" AND rt.rating BETWEEN ")
                .push_bind(lo)
                .push(" AND ")
                .push_bind(hi);
        }
        (Some(lo), None) => {
            qb.push(" AND rt.rating >= ").push_bind(lo);
        }
        (None, Some(hi)) => {
            qb.push(" AND rt.rating <= ").push_bind(hi);
        }
        _ => {}
    }

    // in_path — case-insensitive substring match on file path
    if !p.in_path.is_empty() {
        let pat = format!("%{}%", p.in_path.trim().to_lowercase().replace('\\', "/"));
        qb.push(" AND LOWER(REPLACE(f.path, '\\', '/')) LIKE ? ESCAPE '\\'")
            .push_bind(pat);
    }

    // checkpoint_filter — model name/hash substring match via templates
    if !p.checkpoint_filter.is_empty() {
        let term = p.checkpoint_filter.trim().to_lowercase();
        let like_pat = format!("%{term}%");
        let fts_phrase = if term.len() >= 3 {
            let escaped = term.replace('"', "\"\"");
            Some(format!("\"model: {escaped}\""))
        } else {
            None
        };
        if let Some(phrase) = fts_phrase {
            qb.push(
                " AND (EXISTS(SELECT 1 FROM templates tm2 WHERE tm2.file_id=f.id \
                 AND tm2.model_name IS NOT NULL \
                 AND (lower(tm2.model_name) LIKE ? OR lower(tm2.model_hash) LIKE ?)) \
                 OR f.id IN (\
                 SELECT tm2.file_id FROM templates_fts tf2 \
                 JOIN templates tm2 ON tm2.id = tf2.rowid \
                 WHERE tm2.model_name IS NULL AND tf2.raw_prompt MATCH ?))",
            )
            .push_bind(like_pat.clone())
            .push_bind(like_pat)
            .push_bind(phrase);
        } else {
            // term < 3 chars: skip FTS, use correlated EXISTS only
            qb.push(
                " AND EXISTS(SELECT 1 FROM templates tm2 WHERE tm2.file_id=f.id \
                 AND (lower(tm2.model_name) LIKE ? OR lower(tm2.model_hash) LIKE ?))",
            )
            .push_bind(like_pat.clone())
            .push_bind(like_pat);
        }
    }

    // boolean フラグ
    if p.has_tags {
        qb.push(" AND EXISTS(SELECT 1 FROM file_tags ft2 WHERE ft2.file_id=f.id)");
    }
    if p.has_annotation {
        qb.push(" AND EXISTS(SELECT 1 FROM file_annotations fa WHERE fa.file_id=f.id)");
    }
    if p.has_sweep {
        qb.push(" AND f.has_sweep=1");
    }
    if p.ai_analyzed {
        if let Some(mid) = active_wd {
            qb.push(" AND (EXISTS(SELECT 1 FROM analysis a WHERE a.file_id=f.id) OR EXISTS(SELECT 1 FROM file_wd_tags wt WHERE wt.file_id=f.id AND wt.model_id=")
              .push_bind(mid)
              .push("))");
        } else {
            qb.push(" AND (EXISTS(SELECT 1 FROM analysis a WHERE a.file_id=f.id) OR EXISTS(SELECT 1 FROM file_wd_tags wt WHERE wt.file_id=f.id))");
        }
    }
}

fn folder_sort_key(path: &str, roots: &[String]) -> (usize, String) {
    let norm = path.replace('\\', "/");
    for (i, root) in roots.iter().enumerate() {
        if !root.is_empty() && norm.starts_with(root.as_str()) {
            return (i, norm);
        }
    }
    (9999, norm)
}

fn push_order_by(qb: &mut QueryBuilder<'_, Sqlite>, sort_by: &str) {
    let clause = match sort_by {
        "date_old" => " ORDER BY f.mtime ASC, f.id ASC",
        "path" | "name" => " ORDER BY f.path ASC, f.id ASC",
        "rating_desc" => " ORDER BY rt.rating IS NULL, rt.rating DESC, f.mtime DESC, f.id DESC",
        "rating_asc" => " ORDER BY rt.rating IS NULL, rt.rating ASC, f.mtime ASC, f.id ASC",
        "random" => " ORDER BY RANDOM()",
        _ => " ORDER BY f.mtime DESC, f.id DESC", // date, date_new, default
    };
    qb.push(clause);
}

// ── ハンドラ ───────────────────────────────────────────────────────────────────

pub async fn search(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(raw): Query<SearchQueryRaw>,
    req: Request<Body>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let mut p = SearchParams::from(raw);
    if !table_exists(&state.db_read, "files").await.unwrap_or(false) {
        return Json(json!({"ok": true, "results": [], "total": 0, "total_count": 0, "has_more": false, "limit": p.limit, "offset": p.offset})).into_response();
    }
    let also_path_requested = p.also_path;
    if p.also_path
        && !table_exists(&state.db_read, "files_path_fts")
            .await
            .unwrap_or(false)
    {
        p.also_path = false;
    }

    // 日付バリデーション
    if !p.from_date.is_empty() && p.from_ts.is_none() && !validate_iso_date(&p.from_date) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "message": "invalid from_date"})),
        )
            .into_response();
    }
    if !p.to_date.is_empty() && p.to_ts.is_none() && !validate_iso_date(&p.to_date) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "message": "invalid to_date"})),
        )
            .into_response();
    }

    // collection 存在確認
    if p.collection_id > 0 && !collection_exists(&state.db_read, p.collection_id).await {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({
                "status": "error",
                "message": "Collection not found",
                "total": 0,
                "total_count": 0,
                "results": []
            })),
        )
            .into_response();
    }

    let active_wd = active_wd_model_id(&state.db_read).await;
    let wd_search_model = resolve_wd_tag_search_model(&state.db_read, &p.wd_model).await;
    let include_templates = !p.in_prompt.is_empty()
        || !p.in_negative.is_empty()
        || !p.in_char_negative.is_empty()
        || !p.in_char_positive.is_empty();
    let need_rating = p.min_rating.is_some() || p.max_rating.is_some();
    let path_search_active =
        also_path_requested && !p.tag_query.is_empty() && path_fts_phrase(&p.tag_query).is_some();

    // rows クエリ
    let mut qb = if include_templates {
        QueryBuilder::<Sqlite>::new(
            "SELECT f.id, f.path, f.mtime, f.meta_source, tm.raw_prompt, tm.raw_negative \
             FROM files f LEFT JOIN templates tm ON tm.file_id=f.id",
        )
    } else {
        QueryBuilder::<Sqlite>::new(
            "SELECT f.id, f.path, f.mtime, f.meta_source, NULL AS raw_prompt, NULL AS raw_negative \
             FROM files f",
        )
    };

    // favorites JOIN
    if p.collection_id > 0 {
        qb.push(" JOIN favorites fav ON fav.file_id=f.id AND fav.collection_id=")
            .push_bind(p.collection_id);
    } else if p.collection_id == -1 || p.fav_only {
        qb.push(" JOIN favorites fav ON fav.file_id=f.id");
    }
    if need_rating {
        qb.push(" JOIN file_ratings rt ON rt.file_id=f.id");
    }

    qb.push(" WHERE 1=1");
    push_where_filters(&mut qb, &p, active_wd, wd_search_model, include_templates);
    let regex_filter = p.in_prompt_regex || p.tag_query_regex;
    let folder_sort = p.sort_by == "folder";
    if folder_sort || regex_filter {
        // full scan — limit/offset applied in Rust post-processing
        if !folder_sort {
            push_order_by(&mut qb, &p.sort_by);
        }
    } else {
        push_order_by(&mut qb, &p.sort_by);
        qb.push(" LIMIT ").push_bind(p.limit as i64);
        qb.push(" OFFSET ").push_bind(p.offset as i64);
    }

    let rows = match qb.build().fetch_all(&state.db_read).await {
        Ok(r) => r,
        Err(e) => {
            tracing::error!("search query failed: {e}");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": "database error"})),
            )
                .into_response();
        }
    };

    let mut results: Vec<serde_json::Value> = rows
        .iter()
        .map(|row| {
            let id: i64 = row.get(0);
            let path: String = row.get(1);
            let mtime: i64 = row.get(2);
            let meta_source: Option<String> = row.get(3);
            let raw_prompt: Option<String> = row.get(4);
            let raw_negative: Option<String> = row.get(5);

            let (positive, negative) = if let Some(rp) = &raw_prompt {
                if rp.contains("Steps:") || rp.contains("Negative prompt:") {
                    parse_a1111_prompt(rp)
                } else {
                    (rp.clone(), raw_negative.clone().unwrap_or_default())
                }
            } else {
                (String::new(), String::new())
            };

            json!({
                "id": id,
                "path": path,
                "mtime": mtime,
                "meta_source": meta_source.unwrap_or_default(),
                "positive": positive,
                "negative": negative,
            })
        })
        .collect();

    // COUNT クエリ
    let mut cqb = if include_templates {
        QueryBuilder::<Sqlite>::new(
            "SELECT COUNT(*) FROM files f LEFT JOIN templates tm ON tm.file_id=f.id",
        )
    } else {
        QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM files f")
    };
    if p.collection_id > 0 {
        cqb.push(" JOIN favorites fav ON fav.file_id=f.id AND fav.collection_id=")
            .push_bind(p.collection_id);
    } else if p.collection_id == -1 || p.fav_only {
        cqb.push(" JOIN favorites fav ON fav.file_id=f.id");
    }
    if need_rating {
        cqb.push(" JOIN file_ratings rt ON rt.file_id=f.id");
    }
    cqb.push(" WHERE 1=1");
    push_where_filters(&mut cqb, &p, active_wd, wd_search_model, include_templates);

    let total_count: i64 = match cqb.build_query_scalar().fetch_one(&state.db_read).await {
        Ok(n) => n,
        Err(e) => {
            tracing::error!("search count failed: {e}");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": "database error"})),
            )
                .into_response();
        }
    };

    if regex_filter {
        let pat = if p.in_prompt_regex {
            p.in_prompt.trim()
        } else {
            p.tag_query.trim()
        };
        let case_sensitive = p.tag_query_case_sensitive && p.tag_query_regex;
        let re_result = if case_sensitive {
            regex::Regex::new(pat)
        } else {
            regex::Regex::new(&format!("(?i){pat}"))
        };
        if let Ok(re) = re_result {
            results.retain(|row| {
                if p.in_prompt_regex {
                    let prompt = row["prompt"].as_str().unwrap_or("");
                    let negative = row["negative"].as_str().unwrap_or("");
                    re.is_match(prompt) || re.is_match(negative)
                } else {
                    // tag_query_regex: search tags field (comma-separated string in results)
                    let tags = row["tags"].as_str().unwrap_or("");
                    re.is_match(tags)
                }
            });
        }
        results = results
            .into_iter()
            .skip(usize::try_from(p.offset).unwrap_or(0))
            .take(p.limit as usize)
            .collect();
    }

    if folder_sort {
        let config = load_config_json(
            &std::path::Path::new(&state.config.db_path)
                .parent()
                .unwrap_or_else(|| std::path::Path::new("."))
                .join("config.json"),
        );
        let roots: Vec<String> = config["scan_roots"]
            .as_array()
            .map(|arr| {
                arr.iter()
                    .filter_map(|r| r["path"].as_str().map(|s| s.replace('\\', "/")))
                    .collect()
            })
            .unwrap_or_default();
        results.sort_by(|a, b| {
            let ka = folder_sort_key(a["path"].as_str().unwrap_or(""), &roots);
            let kb = folder_sort_key(b["path"].as_str().unwrap_or(""), &roots);
            ka.cmp(&kb).then_with(|| {
                a["id"]
                    .as_i64()
                    .unwrap_or(0)
                    .cmp(&b["id"].as_i64().unwrap_or(0))
            })
        });
        results = results
            .into_iter()
            .skip(usize::try_from(p.offset).unwrap_or(0))
            .take(p.limit as usize)
            .collect();
    }

    let total = results.len() as i64;
    let status = if total_count == 0 {
        "empty"
    } else if total < total_count {
        "partial"
    } else {
        "ok"
    };
    let has_more = (p.offset as i64 + total) < total_count;
    let has_cond = has_conditions(&p);

    Json(json!({
        "ok": true,
        "status": status,
        "total": total,
        "total_count": total_count,
        "limit": p.limit,
        "offset": p.offset,
        "has_more": has_more,
        "has_conditions": has_cond,
        "path_search_active": path_search_active,
        "count_pending": false,
        "next_cursor": null,
        "results": results,
    }))
    .into_response()
}

pub async fn search_count(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(raw): Query<SearchQueryRaw>,
    req: Request<Body>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let p = SearchParams::from(raw);

    if !p.from_date.is_empty() && p.from_ts.is_none() && !validate_iso_date(&p.from_date) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "message": "invalid from_date"})),
        )
            .into_response();
    }
    if !p.to_date.is_empty() && p.to_ts.is_none() && !validate_iso_date(&p.to_date) {
        return (
            StatusCode::BAD_REQUEST,
            Json(json!({"ok": false, "message": "invalid to_date"})),
        )
            .into_response();
    }

    if p.collection_id > 0 && !collection_exists(&state.db_read, p.collection_id).await {
        return (
            StatusCode::NOT_FOUND,
            Json(json!({"status": "error", "message": "Collection not found"})),
        )
            .into_response();
    }

    let active_wd = active_wd_model_id(&state.db_read).await;
    let wd_search_model = resolve_wd_tag_search_model(&state.db_read, &p.wd_model).await;
    let include_templates = !p.in_prompt.is_empty()
        || !p.in_negative.is_empty()
        || !p.in_char_negative.is_empty()
        || !p.in_char_positive.is_empty();
    let need_rating = p.min_rating.is_some() || p.max_rating.is_some();

    let mut cqb = if include_templates {
        QueryBuilder::<Sqlite>::new(
            "SELECT COUNT(*) FROM files f LEFT JOIN templates tm ON tm.file_id=f.id",
        )
    } else {
        QueryBuilder::<Sqlite>::new("SELECT COUNT(*) FROM files f")
    };
    if p.collection_id > 0 {
        cqb.push(" JOIN favorites fav ON fav.file_id=f.id AND fav.collection_id=")
            .push_bind(p.collection_id);
    } else if p.collection_id == -1 || p.fav_only {
        cqb.push(" JOIN favorites fav ON fav.file_id=f.id");
    }
    if need_rating {
        cqb.push(" JOIN file_ratings rt ON rt.file_id=f.id");
    }
    cqb.push(" WHERE 1=1");
    push_where_filters(&mut cqb, &p, active_wd, wd_search_model, include_templates);

    match cqb
        .build_query_scalar::<i64>()
        .fetch_one(&state.db_read)
        .await
    {
        // Match Python and this route's {"status": "error", ...} error responses.
        Ok(n) => Json(json!({"status": "ok", "total_count": n})).into_response(),
        Err(e) => {
            tracing::error!("search_count query failed: {e}");
            (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "message": "database error"})),
            )
                .into_response()
        }
    }
}

// ── search-grouped ────────────────────────────────────────────────────────

const GROUP_RETURN_LIMIT: usize = 2000;

fn intersect_group(
    index: &GroupsIndex,
    matching_ids: Option<&std::collections::HashSet<i64>>,
    group_mode: &str,
) -> Vec<serde_json::Value> {
    let source = match group_mode {
        "folder" => &index.folders,
        _ => &index.zips,
    };
    let mut groups: Vec<serde_json::Value> = source
        .iter()
        .filter_map(|(key, entry)| {
            let filtered: Vec<i64> = match matching_ids {
                Some(ids) => entry
                    .ids
                    .iter()
                    .copied()
                    .filter(|id| ids.contains(id))
                    .collect(),
                None => entry.ids.clone(),
            };
            if filtered.is_empty() {
                return None;
            }
            if group_mode == "folder" && filtered.len() < 2 {
                return None;
            }
            let reps: Vec<i64> = filtered.iter().copied().take(8).collect();
            let gtype = if key.starts_with("zip:") || key.starts_with("archive:") {
                "archive"
            } else {
                "folder"
            };
            Some(json!({
                "key": key,
                "type": gtype,
                "label": entry.label,
                "count": entry.ids.len(),
                "matchCount": filtered.len(),
                "reps": reps,
                "memberIds": filtered,
                "max_mtime": entry.max_mtime,
            }))
        })
        .collect();
    groups.sort_by(|a, b| {
        let ma = a["max_mtime"].as_f64().unwrap_or(0.0);
        let mb = b["max_mtime"].as_f64().unwrap_or(0.0);
        mb.partial_cmp(&ma).unwrap_or(std::cmp::Ordering::Equal)
    });
    groups
}

pub(crate) async fn fetch_matching_ids(
    pool: &sqlx::SqlitePool,
    p: &SearchParams,
) -> Result<Option<std::collections::HashSet<i64>>, sqlx::Error> {
    if !has_conditions(p) {
        return Ok(None);
    }
    let active_wd = active_wd_model_id(pool).await;
    let wd_search_model = resolve_wd_tag_search_model(pool, &p.wd_model).await;
    // Regression: fetch_matching_ids built `WHERE  AND ...` which is invalid SQL;
    // /api/search-grouped returned 500 for any conditioned request.
    let mut qb: QueryBuilder<Sqlite> = QueryBuilder::new("SELECT f.id FROM files f WHERE 1=1");
    push_where_filters(&mut qb, p, active_wd, wd_search_model, false);
    let rows = qb.build().fetch_all(pool).await?;
    Ok(Some(rows.iter().map(|r| r.get::<i64, _>(0)).collect()))
}

#[derive(Deserialize, Default)]
pub struct SearchGroupedRaw {
    #[serde(flatten)]
    pub search: SearchQueryRaw,
    pub group_mode: Option<String>,
}

pub async fn search_grouped(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(raw): Query<SearchGroupedRaw>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }

    let group_mode_raw = raw.group_mode.as_deref().unwrap_or("folder");
    // `"folder"` and the fallback coincide. The explicit arm is what says
    // "folder" is an accepted value rather than an unrecognised one.
    #[allow(
        clippy::match_same_arms,
        reason = "the explicit arm lists an accepted value"
    )]
    let group_mode = match group_mode_raw {
        "folder" => "folder",
        "zip" | "archive" => "archive",
        _ => "folder",
    };
    let p = SearchParams::from(raw.search);

    let matching_ids = match fetch_matching_ids(&state.db_read, &p).await {
        Ok(ids) => ids,
        Err(e) => {
            tracing::error!("search_grouped ids query failed: {e}");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "groups": [], "total_files": 0, "total_groups": 0})),
            )
                .into_response();
        }
    };

    let index = match state.groups_index_cache.get(&state.db_read).await {
        Ok(idx) => idx,
        Err(e) => {
            tracing::error!("search_grouped index failed: {e:?}");
            return (
                StatusCode::INTERNAL_SERVER_ERROR,
                Json(json!({"status": "error", "groups": [], "total_files": 0, "total_groups": 0})),
            )
                .into_response();
        }
    };

    let mut groups = intersect_group(&index, matching_ids.as_ref(), group_mode);
    let total_groups = groups.len();
    let total_files: usize = groups
        .iter()
        .map(|g| usize::try_from(g["matchCount"].as_u64().unwrap_or(0)).unwrap_or(0))
        .sum();
    let limited = total_groups > GROUP_RETURN_LIMIT;
    if limited {
        groups.truncate(GROUP_RETURN_LIMIT);
    }

    Json(json!({
        "status": "ok",
        "groups": groups,
        "total_files": total_files,
        "total_groups": total_groups,
        "returned_groups": groups.len(),
        "limited": limited,
        "group_mode": group_mode,
    }))
    .into_response()
}

pub async fn search_grouped_warm(
    State(state): State<SharedState>,
    auth_context: Option<Extension<AuthContext>>,
    Query(raw): Query<SearchGroupedRaw>,
) -> Response {
    if let Some(err) = admin_scope_error(&state, auth_context.as_ref()) {
        return err;
    }
    let p = SearchParams::from(raw.search);
    let _ = fetch_matching_ids(&state.db_read, &p).await;
    match state.groups_index_cache.get(&state.db_read).await {
        Ok(_) => Json(json!({"status": "ok"})).into_response(),
        Err(_) => (StatusCode::ACCEPTED, Json(json!({"status": "rebuilding"}))).into_response(),
    }
}

// ── tests ─────────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn p(raw: SearchQueryRaw) -> SearchParams {
        SearchParams::from(raw)
    }

    #[test]
    fn alias_first_non_none_wins_even_if_empty() {
        // q="" (empty string) is non-None → wins over query="girl"
        let params = p(SearchQueryRaw {
            q: Some(String::new()),
            query: Some("girl".to_string()),
            ..Default::default()
        });
        assert_eq!(params.tag_query, "");
    }

    #[test]
    fn bool_true_variants() {
        for v in ["1", "true", "yes", "on", "True", "YES", "ON"] {
            let params = p(SearchQueryRaw {
                fav_only: Some(v.to_string()),
                ..Default::default()
            });
            assert!(params.fav_only, "expected true for '{v}'");
        }
    }

    #[test]
    fn bool_false_variants() {
        for v in ["0", "false", "no", "off", "2", "", "random"] {
            let params = p(SearchQueryRaw {
                fav_only: Some(v.to_string()),
                ..Default::default()
            });
            assert!(!params.fav_only, "expected false for '{v}'");
        }
    }

    #[test]
    fn isdigit_rejects_negative_and_decimal() {
        assert_eq!(safe_isdigit(Some("-1")), None);
        assert_eq!(safe_isdigit(Some("1.5")), None);
        assert_eq!(safe_isdigit(Some("abc")), None);
        assert_eq!(safe_isdigit(Some("")), None);
        assert_eq!(safe_isdigit(None), None);
        assert_eq!(safe_isdigit(Some("5")), Some(5));
        assert_eq!(safe_isdigit(Some("100")), Some(100));
    }

    #[test]
    fn limit_clamps_to_2000() {
        let params = p(SearchQueryRaw {
            limit: Some("9999".to_string()),
            ..Default::default()
        });
        assert_eq!(params.limit, 2000);
    }

    #[test]
    fn limit_default_100() {
        assert_eq!(p(SearchQueryRaw::default()).limit, 100);
    }

    #[test]
    fn limit_min_1() {
        let params = p(SearchQueryRaw {
            limit: Some("0".to_string()),
            ..Default::default()
        });
        assert_eq!(params.limit, 1);
    }

    #[test]
    fn defaults() {
        let params = p(SearchQueryRaw::default());
        assert_eq!(params.collection_id, 0);
        assert!(params.also_path);
        assert_eq!(params.file_format, "all");
        assert_eq!(params.sort_by, "date");
        assert_eq!(params.limit, 100);
        assert_eq!(params.offset, 0);
    }

    #[test]
    fn has_conditions_true_for_wd_model_alone() {
        // Regression (Codex review): fetch_matching_ids() (used by
        // /api/search-grouped) short-circuits to "no filter" when
        // has_conditions() is false. wd_model alone must count as a condition,
        // or grouped search would ignore it entirely while plain search
        // (which always applies push_wd_model_filter) respected it.
        let params = p(SearchQueryRaw {
            wd_model: Some("modelA".to_string()),
            ..Default::default()
        });
        assert!(has_conditions(&params));
        assert!(!has_conditions(&p(SearchQueryRaw::default())));
    }

    #[tokio::test]
    async fn search_grouped_conditioned_request_does_not_generate_invalid_where_sql() {
        use crate::routes::wd_tagger::tests::{test_dirs, test_state};
        use axum::{body::to_bytes, extract::State};

        let dirs = test_dirs();
        let state = test_state(&dirs, json!({})).await;
        sqlx::query("ALTER TABLE files ADD COLUMN mtime INTEGER DEFAULT 0")
            .execute(&state.db)
            .await
            .unwrap();
        let response = search_grouped(
            State(state),
            None,
            axum::extract::Query(SearchGroupedRaw {
                search: SearchQueryRaw {
                    wd_model: Some("model-a".to_string()),
                    ..Default::default()
                },
                group_mode: None,
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        assert_eq!(
            serde_json::from_slice::<serde_json::Value>(&body).unwrap()["status"],
            "ok"
        );
    }

    #[tokio::test]
    async fn wd_model_all_is_case_insensitive() {
        // Regression (Codex review): Python's "all" check used to be an exact
        // match while Rust used eq_ignore_ascii_case, so wd_model=ALL behaved
        // differently across languages. Both now treat "all"/"ALL"/"All" the
        // same; this pins the Rust side of that parity.
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        for v in ["all", "ALL", "All"] {
            assert_eq!(
                resolve_wd_tag_search_model(&pool, v).await,
                WdModelScope::Any
            );
        }
    }

    #[tokio::test]
    async fn wd_tag_search_scopes_by_model_and_all() {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, mtime INTEGER, is_deleted INTEGER DEFAULT 0, meta_source TEXT, width INTEGER, height INTEGER);
             CREATE TABLE tags (id INTEGER PRIMARY KEY, tag TEXT NOT NULL);
             CREATE TABLE file_tags (file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL);
             CREATE TABLE wd_tag_dict (id INTEGER PRIMARY KEY, tag_name TEXT NOT NULL, tag_name_normalized TEXT NOT NULL);
             CREATE TABLE file_wd_tags (file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, model_id INTEGER NOT NULL);
             INSERT INTO files(id, path, mtime, is_deleted) VALUES (1,'a.png',1,0), (2,'b.png',2,0);
             INSERT INTO wd_model_dict(id, model) VALUES (10,'modelA'), (20,'modelB');
             INSERT INTO wd_tag_dict(id, tag_name, tag_name_normalized) VALUES (100, 'blue_eyes', 'blue eyes');
             INSERT INTO file_wd_tags(file_id, tag_id, model_id) VALUES (1, 100, 10), (2, 100, 20);",
        )
        .execute(&pool)
        .await
        .unwrap();

        async fn matching_ids(
            pool: &sqlx::SqlitePool,
            tag_query: &str,
            wd_model: &str,
        ) -> Vec<i64> {
            let raw = SearchQueryRaw {
                q: Some(tag_query.to_string()),
                also_path: Some("false".to_string()),
                wd_model: Some(wd_model.to_string()),
                ..Default::default()
            };
            let params = SearchParams::from(raw);
            let wd_search_model = resolve_wd_tag_search_model(pool, &params.wd_model).await;
            let mut qb: QueryBuilder<Sqlite> =
                QueryBuilder::new("SELECT f.id FROM files f WHERE 1=1");
            push_where_filters(&mut qb, &params, None, wd_search_model, false);
            let rows = qb.build().fetch_all(pool).await.unwrap();
            let mut ids: Vec<i64> = rows.iter().map(|r| r.get::<i64, _>(0)).collect();
            ids.sort();
            ids
        }

        assert_eq!(matching_ids(&pool, "blue_eyes", "modelA").await, vec![1]);
        assert_eq!(matching_ids(&pool, "blue_eyes", "modelB").await, vec![2]);
        assert_eq!(matching_ids(&pool, "blue_eyes", "all").await, vec![1, 2]);
        assert_eq!(
            matching_ids(&pool, "blue_eyes", "no-such-model").await,
            Vec::<i64>::new()
        );
    }

    #[tokio::test]
    async fn wd_model_filter_narrows_results_without_a_tag_query() {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE files (id INTEGER PRIMARY KEY, path TEXT, mtime INTEGER, is_deleted INTEGER DEFAULT 0, meta_source TEXT, width INTEGER, height INTEGER);
             CREATE TABLE tags (id INTEGER PRIMARY KEY, tag TEXT NOT NULL);
             CREATE TABLE file_tags (file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL);
             CREATE TABLE wd_tag_dict (id INTEGER PRIMARY KEY, tag_name TEXT NOT NULL, tag_name_normalized TEXT NOT NULL);
             CREATE TABLE file_wd_tags (file_id INTEGER NOT NULL, tag_id INTEGER NOT NULL, model_id INTEGER NOT NULL);
             INSERT INTO files(id, path, mtime, is_deleted) VALUES (1,'a.png',1,0), (2,'b.png',2,0), (3,'c.png',3,0);
             INSERT INTO wd_model_dict(id, model) VALUES (10,'modelA'), (20,'modelB');
             INSERT INTO wd_tag_dict(id, tag_name, tag_name_normalized) VALUES (100, 'blue_eyes', 'blue eyes');
             INSERT INTO file_wd_tags(file_id, tag_id, model_id) VALUES (1, 100, 10), (2, 100, 20);",
        )
        .execute(&pool)
        .await
        .unwrap();

        async fn matching_ids(pool: &sqlx::SqlitePool, wd_model: &str) -> Vec<i64> {
            let raw = SearchQueryRaw {
                also_path: Some("false".to_string()),
                wd_model: Some(wd_model.to_string()),
                ..Default::default()
            };
            let params = SearchParams::from(raw);
            let wd_search_model = resolve_wd_tag_search_model(pool, &params.wd_model).await;
            let mut qb: QueryBuilder<Sqlite> =
                QueryBuilder::new("SELECT f.id FROM files f WHERE 1=1");
            push_where_filters(&mut qb, &params, None, wd_search_model, false);
            let rows = qb.build().fetch_all(pool).await.unwrap();
            let mut ids: Vec<i64> = rows.iter().map(|r| r.get::<i64, _>(0)).collect();
            ids.sort();
            ids
        }

        // Regression: previously wd_model only applied inside a tag_query OR
        // clause, so selecting a model with no tag typed had zero effect.
        assert_eq!(matching_ids(&pool, "modelA").await, vec![1]);
        assert_eq!(matching_ids(&pool, "modelB").await, vec![2]);
        assert_eq!(matching_ids(&pool, "all").await, vec![1, 2]);
        assert_eq!(
            matching_ids(&pool, "no-such-model").await,
            Vec::<i64>::new()
        );
        assert_eq!(matching_ids(&pool, "").await, vec![1, 2, 3]);
    }

    #[tokio::test]
    async fn active_wd_model_id_resolves_from_kv_state_and_wd_model_dict() {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE kv_state (key TEXT PRIMARY KEY, value TEXT);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL);
             INSERT INTO wd_model_dict(id, model) VALUES (10, 'modelA');
             INSERT INTO kv_state(key, value) VALUES ('wd_active_model_id', 'modelA');",
        )
        .execute(&pool)
        .await
        .unwrap();

        assert_eq!(active_wd_model_id(&pool).await, Some(10));
    }

    #[tokio::test]
    async fn active_wd_model_id_is_none_when_unset() {
        use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
        use std::str::FromStr;

        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        sqlx::raw_sql(
            "CREATE TABLE kv_state (key TEXT PRIMARY KEY, value TEXT);
             CREATE TABLE wd_model_dict (id INTEGER PRIMARY KEY, model TEXT NOT NULL);",
        )
        .execute(&pool)
        .await
        .unwrap();

        assert_eq!(active_wd_model_id(&pool).await, None);
    }
}
