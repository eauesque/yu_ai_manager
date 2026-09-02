use std::sync::OnceLock;
use std::time::{SystemTime, UNIX_EPOCH};

use axum::{
    extract::State,
    response::{IntoResponse, Response},
    Json,
};
use serde_json::{json, Value};
use tokio::sync::Mutex;

use crate::state::SharedState;

const CACHE_TTL_SECS: u64 = 60;
/// Wall-clock cap on one refresh of the whole symbol list, per-symbol budgets
/// included. Mirrors the Python side's cap so both answer within a caller's
/// patience when the network is dead.
const OVERALL_FETCH_BUDGET: std::time::Duration = std::time::Duration::from_secs(6);
const YAHOO_UA: &str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36";

struct Cache {
    data: Option<(u64, Value)>,
}

static QUOTES_CACHE: OnceLock<Mutex<Cache>> = OnceLock::new();

fn cache() -> &'static Mutex<Cache> {
    QUOTES_CACHE.get_or_init(|| Mutex::new(Cache { data: None }))
}

fn now_secs() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs())
        .unwrap_or(0)
}

fn fallback(now: u64) -> Value {
    json!({
        "source": "fallback",
        "updated_at": now,
        "quotes": [
            {"label": "DOW",  "value": "+0.21%"},
            {"label": "NAS",  "value": "+0.34%"},
            {"label": "SPX",  "value": "+0.18%"},
            {"label": "FTSE", "value": "+0.11%"},
            {"label": "USDX", "value": "-0.09%"},
        ]
    })
}

async fn fetch_one(client: &reqwest::Client, sym: &str) -> Option<(f64, f64)> {
    let url = format!(
        "https://query1.finance.yahoo.com/v8/finance/chart/{}?range=1d&interval=1d",
        urlencoding::encode(sym)
    );
    let resp = client
        .get(&url)
        .header("User-Agent", YAHOO_UA)
        .header("Accept", "application/json")
        .timeout(std::time::Duration::from_secs_f64(2.5))
        .send()
        .await
        .ok()?;
    let body: Value = resp.json().await.ok()?;
    let meta = body.pointer("/chart/result/0/meta")?;
    let price = meta.get("regularMarketPrice")?.as_f64()?;
    let prev = meta
        .get("chartPreviousClose")
        .and_then(|v| v.as_f64())
        .or_else(|| meta.get("previousClose").and_then(|v| v.as_f64()))?;
    if prev == 0.0 {
        return None;
    }
    Some((price, prev))
}

async fn fetch_quotes(client: &reqwest::Client, now: u64) -> Value {
    let symbols = [
        ("DOW", "^DJI"),
        ("NAS", "^IXIC"),
        ("SPX", "^GSPC"),
        ("FTSE", "^FTSE"),
        ("USDX", "DX-Y.NYB"),
    ];
    // Per-request budgets alone do not bound this loop: five symbols at 2.5s
    // each is 12.5s, past any caller's patience, and a widget that reports the
    // market has no business holding a request that long. Whatever has been
    // collected when the deadline passes is what the caller gets.
    let deadline = tokio::time::Instant::now() + OVERALL_FETCH_BUDGET;
    let mut quotes = Vec::new();
    for (label, sym) in &symbols {
        if tokio::time::Instant::now() >= deadline {
            break;
        }
        if let Some((price, prev)) = fetch_one(client, sym).await {
            let pct = (price - prev) / prev * 100.0;
            let sign = if pct >= 0.0 { "+" } else { "" };
            quotes.push(json!({"label": label, "value": format!("{}{:.2}%", sign, pct)}));
        }
    }
    if quotes.is_empty() {
        return fallback(now);
    }
    json!({ "source": "yahoo", "updated_at": now, "quotes": quotes })
}

/// Non-blocking read of the quotes cache for the boss-mode gate: never
/// awaits Yahoo, ignores TTL (stale is fine for camouflage), and falls back
/// to the static fallback payload if there's no cached data yet or the lock
/// is momentarily contended.
pub(crate) fn cached_quotes_or_fallback() -> Value {
    if let Ok(guard) = cache().try_lock() {
        if let Some((_, ref data)) = guard.data {
            return data.clone();
        }
    }
    fallback(now_secs())
}

pub async fn market_quotes(State(state): State<SharedState>) -> Response {
    let now = now_secs();
    {
        let guard = cache().lock().await;
        if let Some((ts, ref data)) = guard.data {
            if now.saturating_sub(ts) < CACHE_TTL_SECS {
                return Json(data.clone()).into_response();
            }
        }
    }

    let data = fetch_quotes(&state.inference_client, now).await;

    {
        let mut guard = cache().lock().await;
        guard.data = Some((now, data.clone()));
    }

    Json(data).into_response()
}
