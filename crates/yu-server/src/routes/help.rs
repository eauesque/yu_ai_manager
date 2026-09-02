use std::path::Path;

use axum::{
    extract::{Extension, Path as AxumPath, Query, State},
    http::{header, HeaderMap, StatusCode},
    response::{IntoResponse, Response},
    Json,
};
use serde::Deserialize;
use serde_json::{json, Value};

use crate::security::CspNonce;
use crate::state::SharedState;

#[derive(Debug, Deserialize)]
pub struct HelpQuery {
    q: Option<String>,
    lang: Option<String>,
    limit: Option<usize>,
}

pub async fn help_toc(
    State(_state): State<SharedState>,
    headers: HeaderMap,
    Query(params): Query<HelpQuery>,
) -> Response {
    let lang = detect_lang(params.lang.as_deref(), accept_language(&headers));
    api_success(json!({"toc": build_toc(lang), "lang": lang}))
}

pub async fn help_search(
    State(state): State<SharedState>,
    headers: HeaderMap,
    Query(params): Query<HelpQuery>,
) -> Response {
    let lang = detect_lang(params.lang.as_deref(), accept_language(&headers));
    let query = params.q.unwrap_or_default().trim().to_string();
    if query.is_empty() {
        return api_error("Query parameter 'q' is required", StatusCode::BAD_REQUEST);
    }
    let limit = params.limit.unwrap_or(5).min(20);
    let docs_dir = state.config.project_root.join("docs");
    api_success(json!({
        "query": query,
        "lang": lang,
        "results": search_content(&docs_dir, &query, lang, limit),
    }))
}

/// GET /api/help/content/{section}
pub async fn help_content(
    State(state): State<SharedState>,
    headers: HeaderMap,
    Query(params): Query<HelpQuery>,
    AxumPath(section): AxumPath<String>,
) -> Response {
    let lang = detect_lang(params.lang.as_deref(), accept_language(&headers));
    let docs_dir = state.config.project_root.join("docs");

    let Some((cat, sec)) = all_sections().find(|(_, s)| s.slug == section) else {
        return api_error("Section not found", StatusCode::NOT_FOUND);
    };
    let Some(md) = read_section(&docs_dir, &section, lang) else {
        return api_error("Content not found", StatusCode::NOT_FOUND);
    };

    let title_str = title(*sec, lang);
    let cat_sections: Vec<&'static str> = cat.sections.iter().map(|s| s.slug).collect();
    let idx = cat_sections
        .iter()
        .position(|&s| s == section.as_str())
        .unwrap_or(0);
    let mut related: Vec<&str> = Vec::new();
    if idx > 0 {
        related.push(cat_sections[idx - 1]);
    }
    if idx + 1 < cat_sections.len() {
        related.push(cat_sections[idx + 1]);
    }
    let content_html = md_to_html(&md);
    api_success(json!({
        "section": section,
        "category": cat.slug,
        "title": title_str,
        "lang": lang,
        "content": md,
        "content_html": content_html,
        "related": related,
    }))
}

fn inline_md(text: &str) -> String {
    let mut s = escape_html(text);
    // code
    let mut out = String::new();
    let mut i = 0;
    let bytes = s.as_bytes();
    while i < bytes.len() {
        if bytes[i] == b'`' {
            if let Some(j) = s[i + 1..].find('`') {
                out.push_str("<code>");
                out.push_str(&s[i + 1..i + 1 + j]);
                out.push_str("</code>");
                i += 1 + j + 1;
                continue;
            }
        }
        out.push(s.chars().nth(i).unwrap_or(' '));
        i += 1;
    }
    s = out;
    // bold
    let re_bold = regex_replace_all(&s, r"\*\*([^*]+)\*\*", |cap: &str| {
        format!("<strong>{}</strong>", cap)
    });
    s = re_bold;
    // italic (not preceded/followed by *)
    s = simple_replace_italic(&s);
    // links
    s = replace_links(&s);
    s
}

fn regex_replace_all(input: &str, pat: &str, replace: impl Fn(&str) -> String) -> String {
    // Manual implementation: find ** ... ** pairs
    if pat == r"\*\*([^*]+)\*\*" {
        let mut result = String::new();
        let mut rest = input;
        while let Some(start) = rest.find("**") {
            result.push_str(&rest[..start]);
            rest = &rest[start + 2..];
            if let Some(end) = rest.find("**") {
                let cap = &rest[..end];
                result.push_str(&replace(cap));
                rest = &rest[end + 2..];
            } else {
                result.push_str("**");
            }
        }
        result.push_str(rest);
        result
    } else {
        input.to_string()
    }
}

fn simple_replace_italic(input: &str) -> String {
    // Match *text* not surrounded by *
    let mut result = String::new();
    let chars: Vec<char> = input.chars().collect();
    let mut i = 0;
    while i < chars.len() {
        if chars[i] == '*'
            && (i == 0 || chars[i - 1] != '*')
            && i + 1 < chars.len()
            && chars[i + 1] != '*'
        {
            if let Some(j) = chars[i + 1..].iter().position(|&c| c == '*') {
                let text: String = chars[i + 1..i + 1 + j].iter().collect();
                if !text.contains('*') {
                    result.push_str("<em>");
                    result.push_str(&text);
                    result.push_str("</em>");
                    i += 1 + j + 1;
                    continue;
                }
            }
        }
        result.push(chars[i]);
        i += 1;
    }
    result
}

fn replace_links(input: &str) -> String {
    let mut result = String::new();
    let mut rest = input;
    while let Some(start) = rest.find('[') {
        result.push_str(&rest[..start]);
        rest = &rest[start..];
        if let Some(mid) = rest.find("](") {
            let label = &rest[1..mid];
            let tail = &rest[mid + 2..];
            if let Some(end) = tail.find(')') {
                let href = &tail[..end];
                rest = &tail[end + 1..];
                let lower = href.to_ascii_lowercase();
                let lower = lower.trim();
                if lower.starts_with("javascript:")
                    || lower.starts_with("data:")
                    || lower.starts_with("vbscript:")
                {
                    result.push_str(label);
                } else {
                    result.push_str(&format!("<a href=\"{href}\">{label}</a>"));
                }
                continue;
            }
        }
        result.push('[');
        rest = &rest[1..];
    }
    result.push_str(rest);
    result
}

fn md_to_html(md_text: &str) -> String {
    let mut html_lines: Vec<String> = Vec::new();
    let mut in_code_block = false;
    let mut in_list = false;
    let mut in_ol = false;
    let mut in_table = false;
    let mut table_header_done = false;

    let close_list = |html_lines: &mut Vec<String>, in_list: &mut bool, in_ol: &mut bool| {
        if *in_list {
            html_lines.push("</ul>".into());
            *in_list = false;
        }
        if *in_ol {
            html_lines.push("</ol>".into());
            *in_ol = false;
        }
    };

    for line in md_text.lines() {
        let stripped = line.trim();

        // Code block fence
        if stripped.starts_with("```") {
            if in_code_block {
                html_lines.push("</code></pre>".into());
                in_code_block = false;
            } else {
                let lang_hint = stripped.trim_start_matches('`').trim();
                let cls = if lang_hint.is_empty() {
                    String::new()
                } else {
                    format!(" class=\"language-{}\"", escape_html(lang_hint))
                };
                html_lines.push(format!("<pre><code{cls}>"));
                in_code_block = true;
            }
            continue;
        }
        if in_code_block {
            html_lines.push(
                line.replace('&', "&amp;")
                    .replace('<', "&lt;")
                    .replace('>', "&gt;"),
            );
            continue;
        }

        // Table row
        if stripped.starts_with('|') && stripped.ends_with('|') {
            if !in_table {
                close_list(&mut html_lines, &mut in_list, &mut in_ol);
                in_table = true;
                table_header_done = false;
                html_lines.push("<div class=\"table-wrap\"><table>".into());
            }
            // Separator row
            if stripped.chars().all(|c| matches!(c, '|' | '-' | ':' | ' ')) {
                table_header_done = true;
                continue;
            }
            let cells: Vec<&str> = stripped
                .trim_matches('|')
                .split('|')
                .map(str::trim)
                .collect();
            let tag = if table_header_done { "td" } else { "th" };
            let row: String = cells
                .iter()
                .map(|c| format!("<{tag}>{}</{tag}>", inline_md(c)))
                .collect();
            html_lines.push(format!("<tr>{row}</tr>"));
            continue;
        } else if in_table {
            html_lines.push("</table></div>".into());
            in_table = false;
            table_header_done = false;
        }

        // Empty line
        if stripped.is_empty() {
            close_list(&mut html_lines, &mut in_list, &mut in_ol);
            html_lines.push(String::new());
            continue;
        }

        // Heading
        if stripped.starts_with('#') {
            let level = stripped.chars().take_while(|&c| c == '#').count().min(6);
            let text_raw = stripped[level..].trim();
            let text = inline_md(text_raw);
            close_list(&mut html_lines, &mut in_list, &mut in_ol);
            if level == 2 {
                let slug_id: String = text
                    .chars()
                    .map(|c| {
                        if c.is_alphanumeric() {
                            c.to_ascii_lowercase()
                        } else {
                            '-'
                        }
                    })
                    .collect::<String>()
                    .trim_matches('-')
                    .to_string();
                html_lines.push(format!("<h{level} id=\"{slug_id}\">{text}</h{level}>"));
            } else {
                html_lines.push(format!("<h{level}>{text}</h{level}>"));
            }
            continue;
        }

        // Blockquote
        if let Some(rest) = stripped.strip_prefix("> ") {
            close_list(&mut html_lines, &mut in_list, &mut in_ol);
            let bq_text = inline_md(rest);
            if bq_text.starts_with("<strong>Note</strong>")
                || bq_text.starts_with("<strong>注意</strong>")
            {
                html_lines.push(format!("<div class=\"help-note\">{bq_text}</div>"));
            } else if bq_text.starts_with("<strong>Tip</strong>")
                || bq_text.starts_with("<strong>ヒント</strong>")
            {
                html_lines.push(format!("<div class=\"help-tip\">{bq_text}</div>"));
            } else if bq_text.starts_with("<strong>Warning</strong>")
                || bq_text.starts_with("<strong>警告</strong>")
            {
                html_lines.push(format!("<div class=\"help-warning\">{bq_text}</div>"));
            } else {
                html_lines.push(format!("<blockquote>{bq_text}</blockquote>"));
            }
            continue;
        }

        // Ordered list
        if stripped.chars().next().is_some_and(|c| c.is_ascii_digit()) {
            if let Some(dot_pos) = stripped.find(". ") {
                let prefix = &stripped[..dot_pos];
                if prefix.chars().all(|c| c.is_ascii_digit()) {
                    if !in_ol {
                        close_list(&mut html_lines, &mut in_list, &mut in_ol);
                        html_lines.push("<ol>".into());
                        in_ol = true;
                    }
                    html_lines.push(format!("<li>{}</li>", inline_md(&stripped[dot_pos + 2..])));
                    continue;
                }
            }
        }

        // Unordered list
        if stripped.starts_with("- ") || stripped.starts_with("* ") {
            if !in_list {
                close_list(&mut html_lines, &mut in_list, &mut in_ol);
                html_lines.push("<ul>".into());
                in_list = true;
            }
            html_lines.push(format!("<li>{}</li>", inline_md(&stripped[2..])));
            continue;
        }

        close_list(&mut html_lines, &mut in_list, &mut in_ol);

        // Horizontal rule
        if stripped.len() >= 3 && stripped.chars().all(|c| matches!(c, '-' | '*' | '_')) {
            html_lines.push("<hr>".into());
            continue;
        }

        // Paragraph
        html_lines.push(format!("<p>{}</p>", inline_md(stripped)));
    }

    close_list(&mut html_lines, &mut in_list, &mut in_ol);
    if in_table {
        html_lines.push("</table></div>".into());
    }
    if in_code_block {
        html_lines.push("</code></pre>".into());
    }

    html_lines.join("\n")
}

#[derive(Clone, Copy)]
struct Section {
    slug: &'static str,
    ja: &'static str,
    en: &'static str,
}

#[derive(Clone, Copy)]
struct Category {
    slug: &'static str,
    ja: &'static str,
    en: &'static str,
    sections: &'static [Section],
}

const USER_SECTIONS: &[Section] = &[
    Section {
        slug: "getting-started",
        ja: "はじめに",
        en: "Getting Started",
    },
    Section {
        slug: "quickstart",
        ja: "クイックスタート",
        en: "Quickstart",
    },
    Section {
        slug: "use-cases",
        ja: "ユースケース集",
        en: "Use Cases",
    },
    Section {
        slug: "search",
        ja: "検索",
        en: "Search",
    },
    Section {
        slug: "scan",
        ja: "スキャン",
        en: "Scan",
    },
    Section {
        slug: "scheduler",
        ja: "タスクスケジューラ",
        en: "Task Scheduler",
    },
    Section {
        slug: "bridges",
        ja: "Bridge 連携",
        en: "Bridge Integration",
    },
    Section {
        slug: "social",
        ja: "SNS・外部連携",
        en: "SNS & External",
    },
    Section {
        slug: "sns",
        ja: "SNS 共有・Bluesky",
        en: "SNS Share & Bluesky",
    },
    Section {
        slug: "github",
        ja: "GitHub 連携",
        en: "GitHub Integration",
    },
    Section {
        slug: "lora-training-guide",
        ja: "LoRA 学習",
        en: "LoRA Training",
    },
    Section {
        slug: "deployment",
        ja: "デプロイメント・運用",
        en: "Deployment",
    },
    Section {
        slug: "performance-tuning",
        ja: "パフォーマンス調整",
        en: "Performance Tuning",
    },
    Section {
        slug: "hailo-setup",
        ja: "Hailo-10H セットアップ",
        en: "Hailo-10H Setup",
    },
    Section {
        slug: "os-isolation",
        ja: "OS レベル隔離",
        en: "OS Isolation",
    },
    Section {
        slug: "settings",
        ja: "設定",
        en: "Settings",
    },
    Section {
        slug: "troubleshooting",
        ja: "トラブルシューティング",
        en: "Troubleshooting",
    },
];

const LAN_SECTIONS: &[Section] = &[
    Section {
        slug: "llm-router",
        ja: "LLM Router 概要",
        en: "LLM Router Overview",
    },
    Section {
        slug: "llm-router-setup",
        ja: "LLM Router セットアップ",
        en: "LLM Router Setup",
    },
    Section {
        slug: "gateway",
        ja: "Gateway",
        en: "Gateway",
    },
    Section {
        slug: "lan-cowork",
        ja: "LAN Cowork 概要",
        en: "LAN Cowork Overview",
    },
    Section {
        slug: "lan-cowork-auth",
        ja: "ピア認証・ペアリング",
        en: "Peer Auth & Pairing",
    },
    Section {
        slug: "distributed-inference",
        ja: "分散推論 セットアップ",
        en: "Distributed Inference Setup",
    },
];

const DEV_SECTIONS: &[Section] = &[
    Section {
        slug: "api",
        ja: "API 概要",
        en: "API Overview",
    },
    Section {
        slug: "api-security",
        ja: "API セキュリティ指針",
        en: "API Security Guidelines",
    },
    Section {
        slug: "api-reference",
        ja: "API リファレンス",
        en: "API Reference",
    },
    Section {
        slug: "mcp",
        ja: "MCP 連携",
        en: "MCP Integration",
    },
    Section {
        slug: "extensions",
        ja: "拡張機能",
        en: "Extensions",
    },
    Section {
        slug: "extension-security",
        ja: "Extension セキュリティ",
        en: "Extension Security",
    },
    Section {
        slug: "plugin-development",
        ja: "Extension 開発",
        en: "Extension Development",
    },
    Section {
        slug: "custom-ui",
        ja: "カスタム UI",
        en: "Custom UI",
    },
    Section {
        slug: "events",
        ja: "SSE イベント",
        en: "SSE Events",
    },
    Section {
        slug: "theming",
        ja: "テーマ開発",
        en: "Theming",
    },
    Section {
        slug: "debugging",
        ja: "デバッグ",
        en: "Debugging",
    },
    Section {
        slug: "dev-docs",
        ja: "開発ドキュメント索引",
        en: "Dev Documents Index",
    },
];

const CATEGORIES: &[Category] = &[
    Category {
        slug: "user",
        ja: "ユーザーガイド",
        en: "User Guide",
        sections: USER_SECTIONS,
    },
    Category {
        slug: "lan",
        ja: "LAN・AI 連携",
        en: "LAN & AI",
        sections: LAN_SECTIONS,
    },
    Category {
        slug: "developer",
        ja: "開発者ガイド",
        en: "Developer Guide",
        sections: DEV_SECTIONS,
    },
];

const SEARCH_ALIASES: &[(&str, &[&str])] = &[
    ("port", &["getting-started"]),
    ("url", &["getting-started"]),
    ("5000", &["getting-started"]),
    ("address", &["getting-started"]),
    ("localhost", &["getting-started"]),
    ("start", &["getting-started"]),
    ("install", &["getting-started"]),
    ("setup", &["getting-started"]),
    ("uv", &["getting-started"]),
    ("pip", &["getting-started"]),
    ("pin", &["settings", "getting-started"]),
    ("password", &["settings"]),
    ("lan", &["getting-started", "settings"]),
    ("network", &["settings", "getting-started"]),
    ("bluesky", &["social"]),
    ("github", &["social"]),
    ("bsky", &["social"]),
];

/// `?lang=` first, then `Accept-Language`, then ja — matching the Python
/// `detect_lang()` in core/help_api/help_data.py.
fn detect_lang(lang: Option<&str>, accept: Option<&str>) -> &'static str {
    if let Some(explicit) = supported_lang(lang) {
        return explicit;
    }
    for part in accept.unwrap_or("").split(',') {
        let code = part.split(';').next().unwrap_or("");
        let code = code
            .trim()
            .split('-')
            .next()
            .unwrap_or("")
            .to_ascii_lowercase();
        let code = if code == "jp" { "ja".to_string() } else { code };
        if let Some(matched) = supported_lang(Some(&code)) {
            return matched;
        }
    }
    "ja"
}

fn supported_lang(lang: Option<&str>) -> Option<&'static str> {
    match lang.map(str::trim).map(str::to_ascii_lowercase).as_deref() {
        Some("en") => Some("en"),
        Some("ja") => Some("ja"),
        _ => None,
    }
}

/// Reads the raw Accept-Language header; non-UTF-8 values are ignored.
fn accept_language(headers: &HeaderMap) -> Option<&str> {
    headers
        .get(header::ACCEPT_LANGUAGE)
        .and_then(|value| value.to_str().ok())
}

fn title(section: Section, lang: &str) -> &'static str {
    if lang == "en" {
        section.en
    } else {
        section.ja
    }
}

fn category_title(category: Category, lang: &str) -> &'static str {
    if lang == "en" {
        category.en
    } else {
        category.ja
    }
}

fn build_toc(lang: &str) -> Value {
    Value::Array(
        CATEGORIES
            .iter()
            .map(|category| {
                json!({
                    "category": category.slug,
                    "category_title": category_title(*category, lang),
                    "sections": category.sections.iter().map(|section| {
                        json!({"slug": section.slug, "title": title(*section, lang)})
                    }).collect::<Vec<_>>(),
                })
            })
            .collect(),
    )
}

fn path_map(slug: &str) -> Option<&'static str> {
    match slug {
        "api-reference" => Some("api/README.md"),
        "plugin-development" => Some("plugin-development/getting-started.md"),
        "custom-ui" => Some("custom-ui/README.md"),
        "events" => Some("api/events.md"),
        "theming" => Some("api/theming.md"),
        "llm-router" => Some("llm-router/README.md"),
        "llm-router-setup" => Some("llm-router/setup.md"),
        "gateway" => Some("guides/gateway.md"),
        "lan-cowork" => Some("lan-cowork/README.md"),
        "lan-cowork-auth" => Some("lan-cowork/peer-auth.md"),
        "distributed-inference" => Some("mesh-inference/setup.md"),
        _ => None,
    }
}

fn read_section(docs_dir: &Path, slug: &str, lang: &str) -> Option<String> {
    if !all_sections().any(|(_, section)| section.slug == slug) {
        return None;
    }
    read_section_for_lang(docs_dir, slug, lang).or_else(|| {
        if lang != "ja" {
            read_section_for_lang(docs_dir, slug, "ja")
        } else {
            None
        }
    })
}

fn read_section_for_lang(docs_dir: &Path, slug: &str, lang: &str) -> Option<String> {
    if let Some(rel_path) = path_map(slug) {
        let path = docs_dir.join(lang).join(rel_path);
        if path.is_file() {
            return std::fs::read_to_string(path).ok();
        }
    }
    for cat in ["user", "developer"] {
        let path = docs_dir
            .join(lang)
            .join("help")
            .join(cat)
            .join(format!("{slug}.md"));
        if path.is_file() {
            return std::fs::read_to_string(path).ok();
        }
    }
    None
}

fn all_sections() -> impl Iterator<Item = (&'static Category, &'static Section)> {
    CATEGORIES.iter().flat_map(|category| {
        category
            .sections
            .iter()
            .map(move |section| (category, section))
    })
}

fn search_content(docs_dir: &Path, query: &str, lang: &str, limit: usize) -> Vec<Value> {
    // Python uses Unicode str.lower(). Rust keeps ASCII-only lowering here so
    // byte offsets in content_lower always align with content for snippet slicing.
    // Non-ASCII case folding is therefore narrower than Python's behavior.
    let query_lower = query.to_ascii_lowercase();
    let tokens: Vec<&str> = query_lower.split_whitespace().collect();
    if tokens.is_empty() {
        return vec![];
    }
    let mut priority_slugs = Vec::new();
    for (alias, slugs) in SEARCH_ALIASES {
        if query_lower.contains(alias) {
            for slug in *slugs {
                if !priority_slugs.contains(slug) {
                    priority_slugs.push(*slug);
                }
            }
        }
    }

    let mut results = Vec::new();
    search_sections(
        docs_dir,
        lang,
        &tokens,
        limit,
        all_sections().filter(|(_, section)| priority_slugs.contains(&section.slug)),
        &mut results,
    );
    if results.len() < limit {
        search_sections(
            docs_dir,
            lang,
            &tokens,
            limit,
            all_sections().filter(|(_, section)| !priority_slugs.contains(&section.slug)),
            &mut results,
        );
    }
    results
}

fn search_sections<'a>(
    docs_dir: &Path,
    lang: &str,
    tokens: &[&str],
    limit: usize,
    sections: impl Iterator<Item = (&'a Category, &'a Section)>,
    results: &mut Vec<Value>,
) {
    for (category, section) in sections {
        if results.len() >= limit {
            return;
        }
        let Some(content) = read_section(docs_dir, section.slug, lang) else {
            continue;
        };
        let content_lower = content.to_ascii_lowercase();
        if !tokens.iter().all(|token| content_lower.contains(token)) {
            continue;
        }
        let idx = content_lower.find(tokens[0]).unwrap_or(0);
        let mut start = idx.saturating_sub(50);
        while !content.is_char_boundary(start) {
            start -= 1;
        }
        let mut end = (idx + tokens[0].len() + 100).min(content.len());
        while end < content.len() && !content.is_char_boundary(end) {
            end += 1;
        }
        let mut snippet = content[start..end].replace('\n', " ").trim().to_string();
        if start > 0 {
            snippet.insert_str(0, "...");
        }
        if end < content.len() {
            snippet.push_str("...");
        }
        results.push(json!({
            "section": section.slug,
            "category": category.slug,
            "category_title": escape_html(category_title(*category, lang)),
            "title": escape_html(title(*section, lang)),
            "snippet": escape_html(&snippet),
        }));
    }
}

fn escape_html(text: &str) -> String {
    text.replace('&', "&amp;")
        .replace('<', "&lt;")
        .replace('>', "&gt;")
        .replace('"', "&quot;")
        .replace('\'', "&#039;")
}

fn api_success(payload: Value) -> Response {
    let mut body = json!({"ok": true, "error": null, "data": null});
    if let (Some(dst), Value::Object(src)) = (body.as_object_mut(), payload) {
        dst.extend(src);
    }
    Json(body).into_response()
}

fn api_error(message: &str, status: StatusCode) -> Response {
    (status, Json(json!({"ok": false, "error": message}))).into_response()
}

/// GET /help — help top page. Server-renders the TOC and the first
/// user-guide section, matching the Python `help_index` route.
pub async fn page_help(
    State(state): State<SharedState>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
    headers: HeaderMap,
    Query(params): Query<HelpQuery>,
) -> Response {
    let lang = detect_lang(params.lang.as_deref(), accept_language(&headers));
    let first = USER_SECTIONS.first().map(|s| s.slug).unwrap_or("");
    let content_html = if first.is_empty() {
        String::new()
    } else {
        section_html(&state, first, lang).unwrap_or_default()
    };
    render_help(
        &state,
        &nonce,
        lang,
        first,
        if first.is_empty() { "" } else { "user" },
        &content_html,
        StatusCode::OK,
    )
}

/// GET /help/{section} — deep link target for the TOC and search results.
pub async fn page_help_section(
    State(state): State<SharedState>,
    Extension(CspNonce(nonce)): Extension<CspNonce>,
    headers: HeaderMap,
    Query(params): Query<HelpQuery>,
    AxumPath(section): AxumPath<String>,
) -> Response {
    let lang = detect_lang(params.lang.as_deref(), accept_language(&headers));
    let Some((category, _)) = all_sections().find(|(_, s)| s.slug == section) else {
        return render_help(
            &state,
            &nonce,
            lang,
            "",
            "",
            "<p>セクションが見つかりません。</p>",
            StatusCode::NOT_FOUND,
        );
    };
    let content_html = section_html(&state, &section, lang)
        .unwrap_or_else(|| "<p>コンテンツが見つかりません。</p>".to_string());
    render_help(
        &state,
        &nonce,
        lang,
        &section,
        category.slug,
        &content_html,
        StatusCode::OK,
    )
}

fn section_html(state: &SharedState, slug: &str, lang: &str) -> Option<String> {
    let docs_dir = state.config.project_root.join("docs");
    read_section(&docs_dir, slug, lang).map(|md| md_to_html(&md))
}

fn render_help(
    state: &SharedState,
    nonce: &str,
    lang: &str,
    current_section: &str,
    current_category: &str,
    content_html: &str,
    status: StatusCode,
) -> Response {
    match crate::frontend::render(
        state,
        "help.html",
        json!({
            "csp_nonce": nonce,
            "dist_v": state.dist_v,
            "active": "help",
            "toc": build_toc(lang),
            "current_section": current_section,
            "current_category": current_category,
            "current_lang": lang,
            "content_html": content_html,
        }),
    ) {
        Ok(html) => (status, html).into_response(),
        Err(code) => code.into_response(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::{
        collections::HashSet,
        fs,
        path::{Path, PathBuf},
        str::FromStr,
        sync::Arc,
        time::{SystemTime, UNIX_EPOCH},
    };

    use axum::body::to_bytes;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};

    use crate::state::{AppState, Config};

    fn temp_root(name: &str) -> PathBuf {
        let unique = SystemTime::now()
            .duration_since(UNIX_EPOCH)
            .unwrap()
            .as_nanos();
        std::env::temp_dir().join(format!("yu-server-{name}-{unique}"))
    }

    fn write_file(path: &Path, body: &str) {
        fs::create_dir_all(path.parent().unwrap()).unwrap();
        fs::write(path, body).unwrap();
    }

    async fn test_state(project_root: PathBuf) -> SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").unwrap())
            .await
            .unwrap();
        Arc::new(
            AppState::new(
                Config {
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
                    config_path: project_root.join("config.json"),
                    project_root,
                    app_config: json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    mcp_native: false,
                    standalone: false,
                    infer_standalone: true,
                    active_profile: None,
                    python_executable: String::new(),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::ring::LogRingBuffer::new(64)),
            )
            .await,
        )
    }

    async fn json_body(response: Response) -> serde_json::Value {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        serde_json::from_slice(&body).unwrap()
    }

    #[tokio::test]
    async fn help_toc_returns_language_aware_categories() {
        let root = temp_root("help-toc");
        let response = help_toc(
            State(test_state(root.clone()).await),
            HeaderMap::new(),
            Query(HelpQuery {
                q: None,
                lang: Some("en".to_string()),
                limit: None,
            }),
        )
        .await;
        let _ = fs::remove_dir_all(root);
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["ok"], true);
        assert_eq!(value["data"], serde_json::Value::Null);
        assert_eq!(value["lang"], "en");
        assert_eq!(value["toc"][0]["category"], "user");
        assert_eq!(value["toc"][0]["category_title"], "User Guide");
        assert_eq!(value["toc"][0]["sections"][0]["slug"], "getting-started");
        assert_eq!(value["toc"][0]["sections"][0]["title"], "Getting Started");
    }

    #[tokio::test]
    async fn help_search_requires_query() {
        let root = temp_root("help-search-missing");
        let response = help_search(
            State(test_state(root.clone()).await),
            HeaderMap::new(),
            Query(HelpQuery {
                q: Some("   ".to_string()),
                lang: None,
                limit: None,
            }),
        )
        .await;
        let _ = fs::remove_dir_all(root);
        assert_eq!(response.status(), axum::http::StatusCode::BAD_REQUEST);
        let value = json_body(response).await;
        assert_eq!(value["ok"], false);
        assert_eq!(value["error"], "Query parameter 'q' is required");
    }

    #[tokio::test]
    async fn help_search_reads_markdown_and_escapes_snippets() {
        let root = temp_root("help-search");
        write_file(
            &root.join("docs/en/help/user/getting-started.md"),
            "# Start\nUse port 5000 with <script>alert(1)</script> safely.",
        );
        let response = help_search(
            State(test_state(root.clone()).await),
            HeaderMap::new(),
            Query(HelpQuery {
                q: Some("port".to_string()),
                lang: Some("en".to_string()),
                limit: Some(5),
            }),
        )
        .await;
        let _ = fs::remove_dir_all(root);
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["query"], "port");
        assert_eq!(value["lang"], "en");
        assert_eq!(value["results"][0]["section"], "getting-started");
        assert_eq!(value["results"][0]["title"], "Getting Started");
        assert!(value["results"][0]["snippet"]
            .as_str()
            .unwrap()
            .contains("&lt;script&gt;"));
    }

    #[test]
    fn search_content_uses_valid_utf8_snippet_boundaries_for_japanese() {
        let root = temp_root("help-search-ja-boundary");
        write_file(
            &root.join("docs/ja/help/user/getting-started.md"),
            &format!("{}API{}", "あ".repeat(18), "い".repeat(40)),
        );

        let results = search_content(&root.join("docs"), "API", "ja", 5);
        let _ = fs::remove_dir_all(root);

        assert_eq!(results.len(), 1);
        let snippet = results[0]["snippet"].as_str().unwrap();
        assert!(snippet.contains("API"));
        assert!(std::str::from_utf8(snippet.as_bytes()).is_ok());
    }

    #[tokio::test]
    async fn help_search_finds_japanese_docs() {
        let root = temp_root("help-search-ja");
        write_file(
            &root.join("docs/ja/help/user/getting-started.md"),
            "はじめに\n検索 API の説明です。",
        );
        let response = help_search(
            State(test_state(root.clone()).await),
            HeaderMap::new(),
            Query(HelpQuery {
                q: Some("API".to_string()),
                lang: Some("ja".to_string()),
                limit: Some(5),
            }),
        )
        .await;
        let _ = fs::remove_dir_all(root);
        assert_eq!(response.status(), axum::http::StatusCode::OK);
        let value = json_body(response).await;
        assert_eq!(value["lang"], "ja");
        assert_eq!(value["results"][0]["section"], "getting-started");
        assert!(value["results"][0]["snippet"]
            .as_str()
            .unwrap()
            .contains("API"));
    }

    /// ponytail: mirrors the contract of ui/default/templates/help.html
    /// (toc loop, active marker, raw content_html). Kept as a fixture because
    /// crates/ must not read files outside the workspace.
    fn write_help_template(root: &Path) {
        write_file(
            &root.join("ui/default/templates/help.html"),
            "<nav>{% for group in toc %}{% for item in group.sections %}\
<a href=\"/help/{{ item.slug }}\" class=\"{{ 'active' if item.slug == current_section else '' }}\">{{ item.title }}</a>\
{% endfor %}{% endfor %}</nav><main>{{ content_html | safe }}</main>",
        );
    }

    async fn html_body(response: Response) -> String {
        let body = to_bytes(response.into_body(), usize::MAX).await.unwrap();
        String::from_utf8(body.to_vec()).unwrap()
    }

    #[tokio::test]
    async fn help_top_page_renders_toc_and_first_section() {
        let root = temp_root("help-page-top");
        write_help_template(&root);
        let first = USER_SECTIONS[0].slug;
        write_file(
            &root.join(format!("docs/ja/help/user/{first}.md")),
            "# 見出し\n\n本文です。\n",
        );
        let response = page_help(
            State(test_state(root.clone()).await),
            Extension(CspNonce("nonce".to_string())),
            HeaderMap::new(),
            Query(HelpQuery {
                q: None,
                lang: None,
                limit: None,
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let html = html_body(response).await;
        assert!(html.contains(&format!("href=\"/help/{first}\"")), "{html}");
        assert!(html.contains("class=\"active\""), "{html}");
        assert!(html.contains("本文です。"), "{html}");
        fs::remove_dir_all(&root).ok();
    }

    #[tokio::test]
    async fn help_section_page_renders_requested_section() {
        let root = temp_root("help-page-section");
        write_help_template(&root);
        write_file(
            &root.join("docs/ja/help/user/search.md"),
            "# 検索\n\n検索の説明。\n",
        );
        let response = page_help_section(
            State(test_state(root.clone()).await),
            Extension(CspNonce("nonce".to_string())),
            HeaderMap::new(),
            Query(HelpQuery {
                q: None,
                lang: None,
                limit: None,
            }),
            AxumPath("search".to_string()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let html = html_body(response).await;
        assert!(html.contains("検索の説明。"), "{html}");
        fs::remove_dir_all(&root).ok();
    }

    #[tokio::test]
    async fn help_section_page_returns_404_for_unknown_section() {
        let root = temp_root("help-page-404");
        write_help_template(&root);
        let response = page_help_section(
            State(test_state(root.clone()).await),
            Extension(CspNonce("nonce".to_string())),
            HeaderMap::new(),
            Query(HelpQuery {
                q: None,
                lang: None,
                limit: None,
            }),
            AxumPath("no-such-section".to_string()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::NOT_FOUND);
        let html = html_body(response).await;
        assert!(html.contains("セクションが見つかりません"), "{html}");
        fs::remove_dir_all(&root).ok();
    }

    #[tokio::test]
    async fn help_section_page_reports_missing_content() {
        let root = temp_root("help-page-empty");
        write_help_template(&root);
        let response = page_help_section(
            State(test_state(root.clone()).await),
            Extension(CspNonce("nonce".to_string())),
            HeaderMap::new(),
            Query(HelpQuery {
                q: None,
                lang: None,
                limit: None,
            }),
            AxumPath("search".to_string()),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let html = html_body(response).await;
        assert!(html.contains("コンテンツが見つかりません"), "{html}");
        fs::remove_dir_all(&root).ok();
    }

    #[test]
    fn detect_lang_prefers_query_then_accept_language() {
        assert_eq!(detect_lang(Some("en"), Some("ja,en;q=0.9")), "en");
        assert_eq!(detect_lang(None, Some("en-US,en;q=0.9")), "en");
        assert_eq!(detect_lang(None, Some("jp")), "ja");
        assert_eq!(detect_lang(None, Some("fr-FR,de;q=0.8,en;q=0.5")), "en");
        assert_eq!(detect_lang(None, Some("fr-FR,de;q=0.8")), "ja");
        assert_eq!(detect_lang(None, None), "ja");
    }

    #[tokio::test]
    async fn help_page_honours_accept_language_header() {
        let root = temp_root("help-page-accept-lang");
        write_help_template(&root);
        let first = USER_SECTIONS[0].slug;
        write_file(
            &root.join(format!("docs/ja/help/user/{first}.md")),
            "日本語本文\n",
        );
        write_file(
            &root.join(format!("docs/en/help/user/{first}.md")),
            "English body\n",
        );
        let mut headers = HeaderMap::new();
        headers.insert(header::ACCEPT_LANGUAGE, "en-US,en;q=0.9".parse().unwrap());
        let response = page_help(
            State(test_state(root.clone()).await),
            Extension(CspNonce("nonce".to_string())),
            headers,
            Query(HelpQuery {
                q: None,
                lang: None,
                limit: None,
            }),
        )
        .await;
        assert_eq!(response.status(), StatusCode::OK);
        let html = html_body(response).await;
        assert!(html.contains("English body"), "{html}");
        fs::remove_dir_all(&root).ok();
    }
}
