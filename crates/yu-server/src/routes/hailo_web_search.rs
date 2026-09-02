//! `chat/search` for hailo-genai: DuckDuckGo web search + Japanese-query
//! heuristics. Not Hailo-dependent (no HEF, no VDevice, no `infer_client`) —
//! see `docs/development/development_docs/HAILO_RUST_MIGRATION_REMAINING_WORK.md`
//! ("`chat/search` は genai 拡張に置かれているだけで Hailo に触らない").
//!
//! Faithful port of:
//! - `extensions/builtin_hailo_genai/core_impl/web_search_query.py`
//! - `extensions/builtin_hailo_genai/core_impl/web_search_detect.py`
//! - `extensions/builtin_hailo_genai/core_impl/web_search_format.py`
//!
//! The Python side uses the `ddgs` package; this queries DuckDuckGo's
//! HTML-only endpoint directly and scrapes it with regex instead of pulling
//! in an HTML parser crate.

use std::collections::HashSet;
use std::sync::OnceLock;
use std::time::Duration;

use axum::{extract::State, response::IntoResponse, Json};
use regex::Regex;
use serde::Serialize;
use serde_json::json;

use crate::state::SharedState;

const USER_AGENT: &str = "Mozilla/5.0 (compatible; YU-AI-Manager chat/search)";
const SEARCH_URL: &str = "https://html.duckduckgo.com/html/";
const SNIPPET_MAX_LEN: usize = 200;
const DEFAULT_MAX_RESULTS: usize = 5;
const MAX_ALLOWED_RESULTS: u64 = 10;
const REQUEST_TIMEOUT: Duration = Duration::from_secs(10);

#[derive(Debug, Clone, PartialEq, Eq, Serialize)]
pub(crate) struct SearchResult {
    pub title: String,
    pub url: String,
    pub snippet: String,
}

const CN_DOMAINS: &[&str] = &[
    "zhihu.com",
    "baidu.com",
    "bilibili.com",
    "163.com",
    "sohu.com",
    "qq.com",
    "sina.com.cn",
    "csdn.net",
    "douban.com",
    "weibo.com",
    "toutiao.com",
];

const KEYWORD_MAP: &[(&str, &str)] = &[
    ("仮想通貨", "cryptocurrency"),
    ("ビットコイン", "bitcoin"),
    ("半導体", "semiconductor"),
    ("原油価格", "crude oil price"),
    ("石油価格", "crude oil price"),
    ("原油", "crude oil"),
    ("石油", "crude oil"),
    ("ガソリン", "gasoline"),
    ("天然ガス", "natural gas"),
    ("株価", "stock price"),
    ("為替レート", "exchange rate"),
    ("為替", "exchange rate"),
    ("金価格", "gold price"),
    ("金利", "interest rate"),
    ("天気予報", "weather forecast"),
    ("天気", "weather"),
    ("ニュース", "news"),
    ("最新", "latest"),
    ("本日", "today"),
    ("今日", "today"),
    ("明日", "tomorrow"),
    ("昨日", "yesterday"),
    ("推移", "trend"),
    ("価格", "price"),
    ("レシピ", "recipe"),
    ("ドル", "USD"),
    ("円安", "yen weak"),
    ("円高", "yen strong"),
    ("円", "yen"),
    ("金", "gold"),
    ("銀", "silver"),
    ("地震", "earthquake"),
    ("台風", "typhoon"),
    ("選挙", "election"),
    ("結果", "results"),
    ("スポーツ", "sports"),
    ("サッカー", "soccer"),
    ("野球", "baseball"),
    ("映画", "movie"),
    ("アニメ", "anime"),
    ("ゲーム", "game"),
    ("日本", "Japan"),
    ("東京", "Tokyo"),
    ("大阪", "Osaka"),
    ("京都", "Kyoto"),
    ("北海道", "Hokkaido"),
    ("沖縄", "Okinawa"),
];

fn anchor_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"(?s)<a\s+([^>]*)>(.*?)</a>").unwrap())
}

fn href_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r#"href="([^"]*)""#).unwrap())
}

fn class_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r#"class="([^"]*)""#).unwrap())
}

fn tag_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"<[^>]+>").unwrap())
}

fn alnum_re() -> &'static Regex {
    static RE: OnceLock<Regex> = OnceLock::new();
    RE.get_or_init(|| Regex::new(r"[A-Za-z0-9]+").unwrap())
}

fn has_class(attrs: &str, class: &str) -> bool {
    class_re()
        .captures(attrs)
        .map(|c| c[1].split_whitespace().any(|token| token == class))
        .unwrap_or(false)
}

fn html_unescape(text: &str) -> String {
    text.replace("&amp;", "&")
        .replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", "\"")
        .replace("&#39;", "'")
        .replace("&nbsp;", " ")
}

fn strip_tags(html: &str) -> String {
    html_unescape(tag_re().replace_all(html, "").trim())
}

/// DDG's HTML endpoint links each result through `duckduckgo.com/l/?uddg=<real url>`.
fn resolve_href(href: &str) -> String {
    let full = match href.strip_prefix("//") {
        Some(rest) => format!("https://{rest}"),
        None => href.to_string(),
    };
    let Ok(parsed) = reqwest::Url::parse(&full) else {
        return href.to_string();
    };
    parsed
        .query_pairs()
        .find(|(k, _)| k == "uddg")
        .map(|(_, v)| v.into_owned())
        .unwrap_or(full)
}

fn parse_results(html: &str, max_results: usize) -> Vec<SearchResult> {
    let mut titles: Vec<(String, String)> = Vec::new();
    let mut snippets: Vec<String> = Vec::new();
    for caps in anchor_re().captures_iter(html) {
        let attrs = &caps[1];
        let inner = &caps[2];
        if has_class(attrs, "result__a") {
            let href = href_re()
                .captures(attrs)
                .map(|c| c[1].to_string())
                .unwrap_or_default();
            titles.push((resolve_href(&href), strip_tags(inner)));
        } else if has_class(attrs, "result__snippet") {
            snippets.push(strip_tags(inner));
        }
    }
    titles
        .into_iter()
        .zip(snippets.into_iter().chain(std::iter::repeat(String::new())))
        .take(max_results)
        .map(|((url, title), snippet)| SearchResult {
            title,
            url,
            snippet: snippet.chars().take(SNIPPET_MAX_LEN).collect(),
        })
        .collect()
}

/// DuckDuckGo serves this same challenge page under a 200 status when it
/// decides to block a request, so an empty result set alone can't tell a
/// caller "no matches" from "upstream refused us" — `blocked` carries that
/// distinction through so `chat_search` can report it instead of silently
/// returning an empty success.
struct DdgsOutcome {
    results: Vec<SearchResult>,
    blocked: bool,
}

/// Markers unique to DuckDuckGo's HTML-endpoint anomaly/CAPTCHA challenge
/// page (observed directly: a normal result page never contains these).
fn looks_blocked(html: &str) -> bool {
    html.contains("anomaly-modal") || html.contains("id=\"challenge-form\"")
}

async fn ddgs_search(
    client: &reqwest::Client,
    query: &str,
    region: &str,
    max_results: usize,
) -> DdgsOutcome {
    let resp = match client
        .get(SEARCH_URL)
        .header(reqwest::header::USER_AGENT, USER_AGENT)
        .query(&[("q", query), ("kl", region)])
        .timeout(REQUEST_TIMEOUT)
        .send()
        .await
    {
        Ok(r) if r.status().is_success() => r,
        Ok(r) => {
            tracing::warn!(status = %r.status(), "hailo-genai web search request failed");
            return DdgsOutcome {
                results: Vec::new(),
                blocked: true,
            };
        }
        Err(err) => {
            tracing::warn!(error = %err, "hailo-genai web search request failed");
            return DdgsOutcome {
                results: Vec::new(),
                blocked: true,
            };
        }
    };
    match resp.text().await {
        Ok(body) => {
            let blocked = looks_blocked(&body);
            if blocked {
                tracing::warn!("hailo-genai web search blocked by upstream anomaly/CAPTCHA page");
            }
            DdgsOutcome {
                results: parse_results(&body, max_results),
                blocked,
            }
        }
        Err(_) => DdgsOutcome {
            results: Vec::new(),
            blocked: true,
        },
    }
}

fn has_hiragana_katakana(text: &str) -> bool {
    text.chars().any(|c| ('\u{3040}'..='\u{30ff}').contains(&c))
}

/// Requires kana rather than falling back to "any CJK ideograph" (Python
/// falls back to `core.tools.lang_detect`, defaulting to `true` when that
/// detector is unavailable/fails — but its zh/ko branches are unreachable
/// dead code, so in practice Python also treats bare Chinese/Korean text as
/// Japanese). Natural Japanese sentences of any real length carry hiragana
/// particles, so requiring kana avoids misrouting a pure-Chinese query into
/// the JP-region/"について"-suffix path instead of mirroring that bug.
fn is_japanese_query(text: &str) -> bool {
    has_hiragana_katakana(text)
}

fn is_cn_result(result: &SearchResult) -> bool {
    CN_DOMAINS.iter().any(|domain| result.url.contains(domain))
}

fn ja_to_en_keywords(query: &str) -> String {
    let mut en_parts: Vec<String> = Vec::new();
    let mut remaining = query.to_string();
    for (ja, en) in KEYWORD_MAP {
        if remaining.contains(ja) {
            en_parts.push((*en).to_string());
            remaining = remaining.replace(ja, " ");
        }
    }
    for m in alnum_re().find_iter(&remaining) {
        en_parts.push(m.as_str().to_string());
    }
    if en_parts.is_empty() {
        query.to_string()
    } else {
        en_parts.join(" ")
    }
}

/// Returns the merged results plus whether the search was blocked: `true`
/// only when every upstream fetch this call made was blocked/failed (a
/// legitimate zero-match query where at least one fetch actually went
/// through is not "blocked").
pub(crate) async fn search_web(
    client: &reqwest::Client,
    query: &str,
    max_results: usize,
) -> (Vec<SearchResult>, bool) {
    if !is_japanese_query(query) {
        let outcome = ddgs_search(client, query, "wt-wt", max_results).await;
        return (outcome.results, outcome.blocked);
    }

    let en_keywords = ja_to_en_keywords(query);
    let en_outcome = ddgs_search(client, &en_keywords, "wt-wt", max_results).await;
    let mut en_results = en_outcome.results;
    if en_results.len() >= max_results {
        en_results.truncate(max_results);
        return (en_results, en_outcome.blocked);
    }

    let hiragana_count = query
        .chars()
        .filter(|c| ('\u{3040}'..='\u{309f}').contains(c))
        .count();
    let ja_query = if hiragana_count < 3 {
        format!("{query} について")
    } else {
        query.to_string()
    };
    let ja_outcome = ddgs_search(client, &ja_query, "jp-jp", max_results).await;

    let mut seen: HashSet<String> = en_results.iter().map(|r| r.url.clone()).collect();
    let mut merged = en_results;
    for result in ja_outcome.results.into_iter().filter(|r| !is_cn_result(r)) {
        if seen.contains(&result.url) {
            continue;
        }
        seen.insert(result.url.clone());
        merged.push(result);
    }
    merged.truncate(max_results);
    (merged, en_outcome.blocked && ja_outcome.blocked)
}

pub(crate) fn format_search_context(results: &[SearchResult], query: &str) -> String {
    if results.is_empty() {
        return String::new();
    }
    let mut lines = vec![
        "IMPORTANT: The following are LIVE web search results retrieved just now.".to_string(),
        "You MUST use these results to answer. Do NOT use your training data.".to_string(),
        format!("Search query: \"{query}\""),
        String::new(),
    ];
    for (i, result) in results.iter().enumerate() {
        lines.push(format!("[{}] {}", i + 1, result.title));
        if !result.snippet.is_empty() {
            lines.push(format!("    {}", result.snippet));
        }
    }
    lines.push(String::new());
    lines.push(
        "Answer based ONLY on the search results above. Cite sources by number [1], [2], etc."
            .to_string(),
    );
    lines.join("\n")
}

/// `POST /ext/hailo-genai/api/chat/search`
pub async fn chat_search(
    State(state): State<SharedState>,
    body: axum::body::Bytes,
) -> axum::response::Response {
    let payload: serde_json::Value = serde_json::from_slice(&body).unwrap_or(json!({}));
    let query = payload
        .get("query")
        .and_then(|v| v.as_str())
        .unwrap_or("")
        .trim()
        .to_string();
    if query.is_empty() {
        return (
            axum::http::StatusCode::BAD_REQUEST,
            Json(json!({"status": "error", "message": "query is required"})),
        )
            .into_response();
    }
    let max_results = payload
        .get("max_results")
        .and_then(|v| v.as_u64())
        .unwrap_or(DEFAULT_MAX_RESULTS as u64)
        .min(MAX_ALLOWED_RESULTS) as usize;

    let (results, blocked) = search_web(&state.inference_client, &query, max_results).await;
    if results.is_empty() && blocked {
        return (
            axum::http::StatusCode::BAD_GATEWAY,
            Json(json!({
                "status": "error",
                "message": "web search upstream unavailable (blocked or unreachable)",
                "query": query,
            })),
        )
            .into_response();
    }
    Json(json!({"status": "ok", "results": results, "query": query})).into_response()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn ja_query_requires_kana_and_does_not_misclassify_bare_cjk() {
        assert!(is_japanese_query("今日の天気")); // kana present -> Japanese
        assert!(!is_japanese_query("价格")); // bare Chinese, no kana -> not Japanese
        assert!(!is_japanese_query("価格")); // bare CJK, no kana -> ambiguous, not assumed Japanese
        assert!(!is_japanese_query("today's weather"));
    }

    #[test]
    fn keyword_map_translates_known_terms_and_keeps_alnum_leftovers() {
        assert_eq!(ja_to_en_keywords("ビットコイン価格"), "bitcoin price");
        assert_eq!(ja_to_en_keywords("Rust 1.80 リリース"), "Rust 1 80");
        assert_eq!(ja_to_en_keywords("こんにちは"), "こんにちは");
    }

    #[test]
    fn cn_domain_detection_matches_python_list() {
        let hit = SearchResult {
            title: "t".into(),
            url: "https://www.zhihu.com/question/1".into(),
            snippet: String::new(),
        };
        let miss = SearchResult {
            title: "t".into(),
            url: "https://example.com".into(),
            snippet: String::new(),
        };
        assert!(is_cn_result(&hit));
        assert!(!is_cn_result(&miss));
    }

    #[test]
    fn format_search_context_matches_python_shape() {
        assert_eq!(format_search_context(&[], "q"), "");
        let results = vec![
            SearchResult {
                title: "Title A".into(),
                url: "https://a.example".into(),
                snippet: "snippet a".into(),
            },
            SearchResult {
                title: "Title B".into(),
                url: "https://b.example".into(),
                snippet: String::new(),
            },
        ];
        let ctx = format_search_context(&results, "my query");
        assert!(ctx.contains("Search query: \"my query\""));
        assert!(ctx.contains("[1] Title A"));
        assert!(ctx.contains("    snippet a"));
        assert!(ctx.contains("[2] Title B"));
        assert!(ctx.contains(
            "Answer based ONLY on the search results above. Cite sources by number [1], [2], etc."
        ));
    }

    #[test]
    fn parse_results_extracts_title_url_and_snippet_regardless_of_attr_order() {
        let html = r#"
            <h2 class="result__title">
              <a rel="nofollow" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage&amp;rut=x" class="result__a">Example <b>Title</b></a>
            </h2>
            <a class="result__snippet" href="//duckduckgo.com/l/?uddg=https%3A%2F%2Fexample.com%2Fpage">A snippet with <b>bold</b> text.</a>
        "#;
        let results = parse_results(html, 5);
        assert_eq!(results.len(), 1);
        assert_eq!(results[0].title, "Example Title");
        assert_eq!(results[0].url, "https://example.com/page");
        assert_eq!(results[0].snippet, "A snippet with bold text.");
    }

    #[test]
    fn looks_blocked_detects_the_anomaly_challenge_page_but_not_real_results() {
        let normal = r#"<a class="result__a" href="//duckduckgo.com/l/?uddg=x">Title</a>"#;
        let challenge = r#"<div class="anomaly-modal__box" data-index="3">...</div>"#;
        assert!(!looks_blocked(normal));
        assert!(looks_blocked(challenge));
    }
}
