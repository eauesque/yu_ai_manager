//! Per-IP three-tier rate limiter.
//!
//! Port of `core/web/api_rate_limit.py`. Rust had no per-IP tier at all, so
//! every mutating endpoint was unlimited by address: `auth/rate.rs` guards PIN
//! brute force only, and `auth/apikey.rs::check_rate_limit` is keyed by API key
//! id, which leaves PIN sessions and key-less callers uncapped.
//!
//! Tier numbers come from `api_rate_limit.py:78-80`, not from
//! `arch-constraints.yaml` -- the latter rounds them to `~20/~12/~120 req/min`
//! and cannot express `rate = 0.33` (20/60 = 0.3333, which is not 0.33).

use std::collections::HashMap;
use std::sync::Mutex;
use std::time::Instant;

/// Which bucket a request draws from. `None` from [`classify`] means unlimited.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum Tier {
    /// CPU/IO heavy work: scans, hashing, inference.
    Heavy,
    /// Data-loss risk: purge, restore, config overwrite.
    Destructive,
    /// Every other mutation.
    Write,
}

impl Tier {
    /// Tokens per second, from `api_rate_limit.py:78-80`.
    pub fn rate(self) -> f64 {
        match self {
            Tier::Heavy => 0.33,
            Tier::Destructive => 0.2,
            Tier::Write => 2.0,
        }
    }

    /// Bucket depth, i.e. how many requests may arrive back to back.
    pub fn burst(self) -> u32 {
        match self {
            Tier::Heavy => 5,
            Tier::Destructive => 3,
            Tier::Write => 30,
        }
    }

    /// `Retry-After`, matching `request_hooks.py:106`: `max(1, int(1.0 / rate))`.
    ///
    /// `int()` truncates, so Heavy advertises 3 while actually needing 3.03s to
    /// earn a token. Reproduced rather than rounded up: a client that trusts the
    /// header must see the same number from both implementations.
    pub fn retry_after_secs(self) -> u64 {
        // Saturating rather than `as`: the ratchet denies raw float casts
        // because a negative value through `as u64` becomes ~1.8e19, which is
        // how a `timeout` of -1 once became "no timeout". The rates here are
        // positive constants, but the conversion should not be the one place
        // that assumes so.
        let advertised = crate::num::sat_u64(1.0 / self.rate());
        advertised.max(1)
    }
}

/// Paths that are heavy on every method, GET included.
///
/// From `api_rate_limit.py:86-111`. Matched by prefix, so `/api/wd-tagger/tag/`
/// covers `/api/wd-tagger/tag/42`.
const HEAVY_PATHS: &[&str] = &[
    "/api/tools/archive-cleanup/scan",
    "/api/tools/archive-cleanup/llm-verify",
    "/api/tools/archive-cleanup/llm-verify-batch",
    "/api/tools/find-similar",
    "/api/tools/compute-hashes",
    "/api/analysis/analyze",
    "/api/analysis/batch",
    "/api/ocr/translate",
    "/api/scan/start",
    "/api/scan-all",
    "/api/wd-tagger/tag/",
    "/api/wd-tagger/batch",
    "/api/wd-tagger/model/download",
    "/ext/hailo-semantic/api/index/start",
    "/ext/hailo-yolo/api/detect/start",
    "/ext/hailo-yolo/api/detect/search",
    "/ext/hailo-yolo/api/model/download",
    "/ext/hailo-genai/api/llm/generate",
    "/ext/hailo-genai/api/vlm/generate",
    "/ext/hailo-genai/api/s2t/transcribe",
    "/ext/hailo-genai/api/model/download",
    "/ext/freeze-pullback/api/generate",
    "/api/download/batch-zip",
    "/api/sns/bluesky/post",
    "/api/sns/bluesky/test",
];

/// Destructive on EVERY method, GET included.
///
/// From `api_rate_limit.py:119-124`. The GET on `/api/settings/config-toml`
/// returns the config file verbatim -- `api_keys`, `webhook_secret`,
/// `server.pin` -- so reading it *is* the sensitive operation. A method guard
/// here would drop that GET through to the unlimited branch.
const DESTRUCTIVE_PATHS_ALL_METHODS: &[&str] = &["/api/settings/config-toml"];

/// Destructive when they mutate; a GET on these is a plain read.
///
/// From `api_rate_limit.py:135-153`.
const DESTRUCTIVE_PATHS: &[&str] = &[
    "/api/scanned-roots/purge",
    "/api/tools/archive-cleanup/execute",
    "/api/tools/delete-duplicates",
    "/api/tools/clear-cache",
    "/api/tools/rebuild-groups",
    "/api/settings/config",
    "/api/settings/config/legacy-migration",
    "/api/tools/backup/create",
    "/api/tools/backup/restore",
    "/api/tools/backup/delete",
    "/ext/hailo-yolo/api/detect/clear",
    "/api/sns/config",
    "/api/settings/secrets/export",
    "/api/settings/secrets/import",
    "/api/settings/secrets/migrate-keychain",
    "/api/settings/secrets/push-to-op",
    "/api/system/update/apply",
];

/// DELETE on these triggers auto-purge or other significant side effects.
///
/// From `api_rate_limit.py:156-159`.
const DESTRUCTIVE_DELETE_PREFIXES: &[&str] = &["/api/scan-roots/", "/api/scheduler/jobs/"];

/// Pick the bucket for a request, or `None` when it is unlimited.
///
/// Port of `api_rate_limit.py::classify` (`:200-226`). Pass `path` exactly as
/// axum reports it (`uri().path()`) and do NOT percent-decode: the router and
/// the limiter must agree on the string, and Python classifies the same shape
/// Quart routes on.
///
/// Read-only GET is unlimited on purpose (`api_rate_limit.py:9-11`): thumbnail
/// grids fire hundreds of concurrent requests and browsers do not retry a failed
/// `<img>`. Two exceptions survive that rule -- a heavy path stays heavy on GET,
/// and the method-agnostic table above catches `config-toml`.
pub fn classify(method: &str, path: &str) -> Option<Tier> {
    if !path.starts_with("/api/") && !path.starts_with("/ext/") {
        return None;
    }
    if HEAVY_PATHS.iter().any(|p| path.starts_with(p)) {
        return Some(Tier::Heavy);
    }

    let is_read = matches!(method, "GET" | "HEAD" | "OPTIONS");

    if DESTRUCTIVE_PATHS_ALL_METHODS
        .iter()
        .any(|p| path.starts_with(p))
    {
        return Some(Tier::Destructive);
    }
    if !is_read && DESTRUCTIVE_PATHS.iter().any(|p| path.starts_with(p)) {
        return Some(Tier::Destructive);
    }
    if method == "DELETE"
        && DESTRUCTIVE_DELETE_PREFIXES
            .iter()
            .any(|p| path.starts_with(p))
    {
        return Some(Tier::Destructive);
    }

    if !is_read {
        return Some(Tier::Write);
    }
    None
}

/// Evict IPs untouched for this long, so a burst of one-shot addresses does not
/// pin memory. `api_rate_limit.py:27`.
const STALE_SECS: u64 = 300;
/// Sweep every N checks rather than on a timer. `api_rate_limit.py:42`.
const SWEEP_EVERY: u64 = 500;
/// Hard ceiling on tracked addresses. `api_rate_limit.py:27`.
const MAX_IPS: usize = 10_000;

struct Bucket {
    tokens: f64,
    last_seen: Instant,
}

/// One tier's token buckets, keyed by client IP.
///
/// Eviction is not optional. `auth/rate.rs::PinRateLimiter` has none -- its
/// `remove` is a reset on successful auth, not a sweep -- so it is the wrong
/// model to copy here: without eviction a spoofed source address grows the map
/// without bound.
pub struct TokenBucket {
    tier: Tier,
    buckets: Mutex<HashMap<String, Bucket>>,
    checks: Mutex<u64>,
}

impl TokenBucket {
    pub fn new(tier: Tier) -> Self {
        Self {
            tier,
            buckets: Mutex::new(HashMap::new()),
            checks: Mutex::new(0),
        }
    }

    /// Spend a token. Returns whether the request may proceed, and how many
    /// tokens remain.
    pub fn check(&self, ip: &str) -> (bool, u32) {
        self.check_at(ip, Instant::now())
    }

    /// `check` with an explicit clock, so refill and eviction are testable
    /// without sleeping.
    pub fn check_at(&self, ip: &str, now: Instant) -> (bool, u32) {
        let burst = f64::from(self.tier.burst());
        let mut buckets = self.buckets.lock().unwrap_or_else(|e| e.into_inner());

        {
            let mut checks = self.checks.lock().unwrap_or_else(|e| e.into_inner());
            *checks += 1;
            if checks.is_multiple_of(SWEEP_EVERY) {
                Self::evict_stale(&mut buckets, now);
            }
        }

        if !buckets.contains_key(ip) {
            if buckets.len() >= MAX_IPS {
                Self::evict_stale(&mut buckets, now);
                if buckets.len() >= MAX_IPS {
                    Self::evict_oldest(&mut buckets);
                }
            }
            buckets.insert(
                ip.to_string(),
                Bucket {
                    tokens: burst,
                    last_seen: now,
                },
            );
        }

        let bucket = match buckets.get_mut(ip) {
            Some(bucket) => bucket,
            // Unreachable: inserted just above. Refusing is the safe answer if
            // it ever happens.
            None => return (false, 0),
        };
        let elapsed = now
            .saturating_duration_since(bucket.last_seen)
            .as_secs_f64();
        bucket.last_seen = now;
        bucket.tokens = (bucket.tokens + elapsed * self.tier.rate()).min(burst);

        if bucket.tokens < 1.0 {
            return (false, 0);
        }
        bucket.tokens -= 1.0;
        (true, crate::num::sat_u32(bucket.tokens))
    }

    fn evict_stale(buckets: &mut HashMap<String, Bucket>, now: Instant) {
        buckets.retain(|_, b| now.saturating_duration_since(b.last_seen).as_secs() < STALE_SECS);
    }

    fn evict_oldest(buckets: &mut HashMap<String, Bucket>) {
        if let Some(oldest) = buckets
            .iter()
            .min_by_key(|(_, b)| b.last_seen)
            .map(|(ip, _)| ip.clone())
        {
            buckets.remove(&oldest);
        }
    }

    #[cfg(test)]
    fn tracked(&self) -> usize {
        self.buckets.lock().unwrap_or_else(|e| e.into_inner()).len()
    }
}

/// The three tiers, held on `AppState` rather than in statics so each test
/// builds its own and no test order dependency creeps in.
pub struct RateLimiters {
    pub heavy: TokenBucket,
    pub destructive: TokenBucket,
    pub write: TokenBucket,
}

impl RateLimiters {
    pub fn new() -> Self {
        Self {
            heavy: TokenBucket::new(Tier::Heavy),
            destructive: TokenBucket::new(Tier::Destructive),
            write: TokenBucket::new(Tier::Write),
        }
    }

    pub fn for_tier(&self, tier: Tier) -> &TokenBucket {
        match tier {
            Tier::Heavy => &self.heavy,
            Tier::Destructive => &self.destructive,
            Tier::Write => &self.write,
        }
    }
}

impl Default for RateLimiters {
    fn default() -> Self {
        Self::new()
    }
}

/// Axum layer: refuse a request whose tier bucket is empty.
///
/// **Position matters and is not obvious.** Python registers the limiter before
/// auth (`runtime_runner.py:249` runs `create_app`, which installs the hook at
/// `request_hooks.py:92`; `:285` installs auth afterwards, and Quart runs
/// `before_request` in registration order). Rust's `auth_middleware` early-returns
/// 401/423 (`auth/middleware.rs:157-201`), so a limiter placed *inside* it would
/// only ever see authenticated traffic: legitimate users capped, attackers
/// uncapped. The limiter must therefore sit outside auth and inside CSRF, which
/// in axum's inverted `.layer()` order means it is applied between
/// `auth_middleware` and `session_layer` in `main.rs`.
///
/// Resolves the client address itself rather than reading an extension, because
/// `auth_middleware` populates that and runs later.
pub async fn layer(
    axum::extract::State(state): axum::extract::State<crate::state::SharedState>,
    axum::extract::ConnectInfo(peer): axum::extract::ConnectInfo<std::net::SocketAddr>,
    request: axum::extract::Request,
    next: axum::middleware::Next,
) -> axum::response::Response {
    use axum::response::IntoResponse;

    let Some(tier) = classify(request.method().as_str(), request.uri().path()) else {
        return next.run(request).await;
    };

    let xff = request
        .headers()
        .get("x-forwarded-for")
        .and_then(|v| v.to_str().ok());
    let ip = crate::auth::client_ip::resolve_client_ip(
        &peer.ip().to_string(),
        xff,
        // The limiter trusts proxies named by `server.trusted_proxy_ips`, which
        // is the condition Python's ProxyFix installs on. Deliberately not
        // `trusted_proxy_enabled`: that flag governs `X-Remote-User` delegation,
        // and binding IP resolution to an auth decision resolves every request
        // behind a reverse proxy to the proxy's own address -- one bucket for
        // the whole LAN.
        !state.config.rate_limit_trusted_proxies.is_empty(),
        &state.config.rate_limit_trusted_proxies,
    );

    let (allowed, _remaining) = state.api_rate_limiters.for_tier(tier).check(&ip);
    if allowed {
        return next.run(request).await;
    }

    (
        axum::http::StatusCode::TOO_MANY_REQUESTS,
        [(
            axum::http::header::RETRY_AFTER,
            tier.retry_after_secs().to_string(),
        )],
        axum::Json(serde_json::json!({
            "ok": false,
            "error": "Rate limit exceeded",
            "code": "rate_limit_exceeded",
        })),
    )
        .into_response()
}

#[cfg(test)]
mod layer_tests {
    //! Test ⑬ and its neighbours, driven through a router carrying the same
    //! layer stack `main.rs` builds.
    //!
    //! NOT written with a bare `Router::oneshot`: `arch-constraints.yaml:59`
    //! records that such a test never runs process middleware, so it would pass
    //! before the injection as readily as after -- the very failure mode the
    //! doc comment at `hailo_yolo_stream/handlers.rs:1511-1516` warns about
    //! ("a route could be wired into main.rs without ever passing through
    //! auth_middleware and these oneshot tests would not notice").

    use super::*;
    use axum::body::Body;
    use axum::http::{Request, StatusCode};
    use axum::routing::post;
    use axum::Router;
    use sqlx::sqlite::{SqliteConnectOptions, SqlitePoolOptions};
    use std::collections::HashSet;
    use std::net::SocketAddr;
    use std::path::PathBuf;
    use std::str::FromStr;
    use std::sync::Arc;
    use tower::ServiceExt;
    use tower_sessions::{MemoryStore, SessionManagerLayer};

    async fn ok_handler() -> &'static str {
        "ok"
    }

    /// A minimal state. `pin_auth_enabled` is on so `auth_middleware` refuses
    /// the unauthenticated requests below -- which is the whole point: the
    /// limiter has to answer first.
    async fn test_state() -> crate::state::SharedState {
        let pool = SqlitePoolOptions::new()
            .connect_with(SqliteConnectOptions::from_str("sqlite::memory:").expect("options"))
            .await
            .expect("in-memory pool");
        // Deliberately never cleaned up: the state holds paths into this
        // directory for the life of the test process. `keep()` is tempfile's
        // supported way to disable the cleanup -- `mem::forget` on a Drop type
        // reaches the same end but is denied by the clippy gate, which is right
        // to: it hides the intent behind a general-purpose leak.
        let dir = tempfile::tempdir().expect("tempdir").keep();
        let config_path = dir.join("config.json");
        std::fs::write(&config_path, "{}").expect("config written");
        Arc::new(
            crate::state::AppState::new(
                crate::state::Config {
                    db_path: "sqlite::memory:".to_string(),
                    pin_hash: String::new(),
                    valid_token: String::new(),
                    secret: String::new(),
                    trusted_proxy_enabled: false,
                    trusted_ips: HashSet::new(),
                    trusted_peer_ips: HashSet::new(),
                    rate_limit_trusted_proxies: HashSet::new(),
                    quick_lock_enabled: true,
                    pin_auth_enabled: true,
                    min_pin_length: 4,
                    python_url: String::new(),
                    config_path,
                    project_root: PathBuf::from("."),
                    app_config: serde_json::json!({}),
                    cache_dir: PathBuf::from("."),
                    server_mode: "full".to_string(),
                    headless: false,
                    safe_mode: false,
                    standalone: true,
                    infer_standalone: true,
                    python_executable: "python3".to_string(),
                    mcp_native: false,
                    active_profile: None,
                    pin_boss_login_ui: false,
                    wd_tagger_root: PathBuf::from("."),
                    clip_model_dir: PathBuf::from("."),
                },
                pool.clone(),
                pool,
                Arc::new(crate::logs::LogRingBuffer::new(16)),
            )
            .await,
        )
    }

    /// The production stack from `main.rs`, in the same order.
    ///
    /// `auth` is applied first and therefore runs last; the limiter is applied
    /// after it and therefore runs before it. Getting that inversion wrong is
    /// what this whole test module exists to catch.
    fn production_stack(state: crate::state::SharedState, with_limiter: bool) -> Router {
        let router = Router::new()
            .route("/api/settings/config", post(ok_handler))
            .layer(axum::middleware::from_fn_with_state(
                state.clone(),
                crate::auth::middleware::auth_middleware,
            ));
        let router = if with_limiter {
            router.layer(axum::middleware::from_fn_with_state(
                state.clone(),
                super::layer,
            ))
        } else {
            router
        };
        router
            .layer(SessionManagerLayer::new(MemoryStore::default()))
            .layer(axum::middleware::from_fn(crate::csrf::layer))
            .layer(axum::middleware::from_fn(crate::security::layer))
            .with_state(state)
    }

    fn unauthenticated_request() -> Request<Body> {
        Request::builder()
            .method("POST")
            .uri("/api/settings/config")
            .header("x-requested-with", "XMLHttpRequest")
            .body(Body::empty())
            .expect("request builds")
    }

    async fn send(app: &Router, peer: SocketAddr) -> StatusCode {
        app.clone()
            .into_service::<Body>()
            .oneshot({
                let mut req = unauthenticated_request();
                req.extensions_mut()
                    .insert(axum::extract::ConnectInfo(peer));
                req
            })
            .await
            .expect("the stack responds")
            .status()
    }

    /// Test ⑬: unauthenticated requests must be limited too.
    ///
    /// This is the invariant that decides whether the limiter is useful at all.
    /// Placed inside `auth_middleware`, the limiter would never see these
    /// requests -- auth returns 401 first -- so the cap would apply only to
    /// legitimate users while an attacker hammered away uncapped.
    #[tokio::test]
    async fn unauthenticated_requests_are_rate_limited() {
        let state = test_state().await;
        let app = production_stack(state, true);
        let peer: SocketAddr = "10.9.9.9:5555".parse().expect("addr parses");

        // DESTRUCTIVE burst is 3; the fourth must be refused by the limiter,
        // not by auth.
        let mut statuses = Vec::new();
        for _ in 0..4 {
            statuses.push(send(&app, peer).await);
        }

        assert_eq!(
            statuses[3],
            StatusCode::TOO_MANY_REQUESTS,
            "the fourth unauthenticated request must be throttled, got {statuses:?}"
        );
        assert!(
            statuses[..3]
                .iter()
                .all(|s| *s != StatusCode::TOO_MANY_REQUESTS),
            "the burst must be spendable before throttling: {statuses:?}"
        );
    }

    /// Without the limiter in the stack, the same traffic is never throttled.
    ///
    /// Proves the assertion above is answering to the limiter rather than to
    /// something else in the chain.
    #[tokio::test]
    async fn the_same_traffic_is_unthrottled_without_the_layer() {
        let state = test_state().await;
        let app = production_stack(state, false);
        let peer: SocketAddr = "10.9.9.8:5555".parse().expect("addr parses");

        for i in 0..6 {
            assert_ne!(
                send(&app, peer).await,
                StatusCode::TOO_MANY_REQUESTS,
                "request {i} was throttled with no limiter in the stack"
            );
        }
    }

    /// One address exhausting its bucket must not throttle another.
    ///
    /// Added after an injection came back green: keying the limiter on a
    /// constant left every test above passing, because they all send from a
    /// single address. A limiter that pools every caller into one bucket is a
    /// denial of service dressed as a safeguard -- and nothing detected it.
    #[tokio::test]
    async fn one_address_cannot_throttle_another() {
        let state = test_state().await;
        let app = production_stack(state, true);
        let noisy: SocketAddr = "10.9.9.1:5555".parse().expect("addr parses");
        let quiet: SocketAddr = "10.9.9.2:5555".parse().expect("addr parses");

        // Exhaust the first address (DESTRUCTIVE burst is 3).
        for _ in 0..4 {
            send(&app, noisy).await;
        }
        assert_eq!(
            send(&app, noisy).await,
            StatusCode::TOO_MANY_REQUESTS,
            "the noisy address should still be throttled"
        );
        assert_ne!(
            send(&app, quiet).await,
            StatusCode::TOO_MANY_REQUESTS,
            "a different address must have its own bucket"
        );
    }

    /// A throttled response must carry `Retry-After`, and the value must be the
    /// tier's -- 5 for DESTRUCTIVE, from Python's truncating `int(1.0/rate)`.
    #[tokio::test]
    async fn a_throttled_response_advertises_retry_after() {
        let state = test_state().await;
        let app = production_stack(state, true);
        let peer: SocketAddr = "10.9.9.7:5555".parse().expect("addr parses");

        let mut last = None;
        for _ in 0..4 {
            let mut req = unauthenticated_request();
            req.extensions_mut()
                .insert(axum::extract::ConnectInfo(peer));
            last = Some(
                app.clone()
                    .into_service::<Body>()
                    .oneshot(req)
                    .await
                    .expect("the stack responds"),
            );
        }
        let response = last.expect("four requests were sent");
        assert_eq!(response.status(), StatusCode::TOO_MANY_REQUESTS);
        assert_eq!(
            response
                .headers()
                .get(axum::http::header::RETRY_AFTER)
                .and_then(|v| v.to_str().ok()),
            Some("5"),
            "DESTRUCTIVE advertises int(1.0/0.2) = 5"
        );
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::time::Duration;

    // ---- classify -------------------------------------------------------

    #[test]
    fn non_api_paths_are_unlimited() {
        assert_eq!(classify("POST", "/login"), None);
        assert_eq!(classify("POST", "/static/app.js"), None);
    }

    /// Plain reads stay unlimited: thumbnail grids fire hundreds of concurrent
    /// GETs and a browser does not retry a failed `<img>`.
    #[test]
    fn a_plain_get_is_unlimited() {
        assert_eq!(classify("GET", "/api/files"), None);
        assert_eq!(classify("HEAD", "/api/files"), None);
        assert_eq!(classify("OPTIONS", "/api/files"), None);
    }

    #[test]
    fn other_mutations_fall_through_to_write() {
        assert_eq!(classify("POST", "/api/apikeys"), Some(Tier::Write));
        assert_eq!(classify("DELETE", "/api/apikeys/ak_1"), Some(Tier::Write));
        assert_eq!(classify("PATCH", "/api/tags/1"), Some(Tier::Write));
    }

    /// Test 5a: the method-agnostic table must carry no method guard.
    ///
    /// The GET on `config-toml` returns the config verbatim -- api_keys,
    /// webhook_secret, server.pin -- so reading it is the sensitive act. Guard
    /// this branch on method and that GET drops through to unlimited.
    #[test]
    fn config_toml_is_destructive_on_get_too() {
        assert_eq!(
            classify("GET", "/api/settings/config-toml"),
            Some(Tier::Destructive),
            "reading config-toml is itself the sensitive operation"
        );
        assert_eq!(
            classify("POST", "/api/settings/config-toml"),
            Some(Tier::Destructive)
        );
    }

    /// Test 5b: `config-toml` must live in the method-agnostic table.
    ///
    /// `/api/settings/config` is a prefix of `/api/settings/config-toml`, so if
    /// only the mutating table carried it, the GET would fall to unlimited
    /// while the POST still looked correct.
    #[test]
    fn plain_config_is_destructive_only_when_it_mutates() {
        assert_eq!(
            classify("POST", "/api/settings/config"),
            Some(Tier::Destructive)
        );
        assert_eq!(
            classify("GET", "/api/settings/config"),
            None,
            "a plain read of /api/settings/config is not the sensitive one"
        );
    }

    /// Test 7: heavy paths ignore the method, so their GETs are heavy too.
    #[test]
    fn a_heavy_path_is_heavy_on_get() {
        assert_eq!(
            classify("GET", "/api/wd-tagger/tag/42"),
            Some(Tier::Heavy),
            "api_rate_limit.py:207 does not look at the method"
        );
        assert_eq!(classify("POST", "/api/scan/start"), Some(Tier::Heavy));
    }

    /// Test 6: heavy is checked before the mutation tiers, and they differ.
    #[test]
    fn heavy_outranks_write_and_destructive() {
        // Heavy and destructive both match /api/tools/... prefixes; heavy wins.
        assert_eq!(
            classify("POST", "/api/tools/compute-hashes"),
            Some(Tier::Heavy)
        );
        assert_eq!(
            classify("POST", "/api/tools/clear-cache"),
            Some(Tier::Destructive)
        );
    }

    /// Test 8: DELETE on these prefixes is destructive, not merely a write.
    #[test]
    fn destructive_delete_prefixes_outrank_write() {
        assert_eq!(
            classify("DELETE", "/api/scan-roots/1"),
            Some(Tier::Destructive)
        );
        assert_eq!(
            classify("DELETE", "/api/scheduler/jobs/abc"),
            Some(Tier::Destructive)
        );
        // A POST to the same prefix is a plain write.
        assert_eq!(classify("POST", "/api/scan-roots/1"), Some(Tier::Write));
    }

    #[test]
    fn ext_paths_are_classified_too() {
        assert_eq!(
            classify("POST", "/ext/hailo-genai/api/llm/generate"),
            Some(Tier::Heavy)
        );
        assert_eq!(classify("POST", "/ext/anything/else"), Some(Tier::Write));
    }

    // ---- tier constants -------------------------------------------------

    /// Test 11: `Retry-After` is `int(1.0/rate)` -- truncated, not rounded up.
    ///
    /// Heavy needs 3.03s to earn a token but advertises 3. Reproduced on
    /// purpose: a client reading the header must see the same number from both
    /// implementations. `ceil` would make it 4 and diverge.
    #[test]
    fn retry_after_matches_pythons_truncation() {
        assert_eq!(Tier::Heavy.retry_after_secs(), 3);
        assert_eq!(Tier::Destructive.retry_after_secs(), 5);
        assert_eq!(Tier::Write.retry_after_secs(), 1);
    }

    // ---- TokenBucket ----------------------------------------------------

    /// Test 1: the burst is spendable, and the next request is refused.
    #[test]
    fn burst_is_spent_then_refused() {
        let bucket = TokenBucket::new(Tier::Destructive); // burst 3
        let now = Instant::now();
        for i in 0..3 {
            let (allowed, _) = bucket.check_at("10.0.0.1", now);
            assert!(allowed, "request {i} within the burst must pass");
        }
        let (allowed, remaining) = bucket.check_at("10.0.0.1", now);
        assert!(!allowed, "the fourth request exceeds a burst of 3");
        assert_eq!(remaining, 0);
    }

    /// Test 2: tokens come back with elapsed time.
    #[test]
    fn tokens_refill_over_time() {
        let bucket = TokenBucket::new(Tier::Destructive); // 0.2/s
        let start = Instant::now();
        for _ in 0..3 {
            bucket.check_at("10.0.0.1", start);
        }
        assert!(!bucket.check_at("10.0.0.1", start).0);

        // 5s at 0.2/s earns exactly one token.
        let later = start + Duration::from_secs(5);
        assert!(
            bucket.check_at("10.0.0.1", later).0,
            "one token must be back after 1/rate seconds"
        );
        assert!(
            !bucket.check_at("10.0.0.1", later).0,
            "only one token was earned"
        );
    }

    #[test]
    fn refill_saturates_at_the_burst() {
        let bucket = TokenBucket::new(Tier::Destructive);
        let start = Instant::now();
        bucket.check_at("10.0.0.1", start);
        // An hour of idling must not bank more than the burst.
        let much_later = start + Duration::from_secs(3600);
        for _ in 0..3 {
            assert!(bucket.check_at("10.0.0.1", much_later).0);
        }
        assert!(
            !bucket.check_at("10.0.0.1", much_later).0,
            "tokens must cap at the burst, not accumulate"
        );
    }

    /// Test 3: one address exhausting its bucket must not affect another.
    #[test]
    fn buckets_are_per_ip() {
        let bucket = TokenBucket::new(Tier::Destructive);
        let now = Instant::now();
        for _ in 0..3 {
            bucket.check_at("10.0.0.1", now);
        }
        assert!(!bucket.check_at("10.0.0.1", now).0);
        assert!(
            bucket.check_at("10.0.0.2", now).0,
            "a second address has its own bucket"
        );
    }

    /// Test 10: idle addresses are swept, so a burst of one-shot IPs does not
    /// pin memory.
    #[test]
    fn stale_entries_are_swept() {
        let bucket = TokenBucket::new(Tier::Write);
        let start = Instant::now();
        for i in 0..(SWEEP_EVERY - 1) {
            bucket.check_at(&format!("10.0.{}.{}", i / 256, i % 256), start);
        }
        assert!(bucket.tracked() > 1);

        // The next check crosses the sweep interval, by which time every entry
        // above is stale.
        let later = start + Duration::from_secs(STALE_SECS + 1);
        bucket.check_at("10.9.9.9", later);
        assert_eq!(
            bucket.tracked(),
            1,
            "the sweep must drop every entry older than STALE_SECS"
        );
    }

    /// Test 9: at the ceiling, the oldest entry is dropped rather than letting
    /// the map grow without bound.
    #[test]
    fn the_map_is_capped_and_drops_the_oldest() {
        let bucket = TokenBucket::new(Tier::Write);
        let start = Instant::now();
        // Fill to the cap with entries that are NOT stale, so only the
        // oldest-eviction path can make room.
        for i in 0..MAX_IPS {
            let at = start + Duration::from_millis(i as u64);
            bucket.check_at(
                &format!("10.{}.{}.{}", i / 65536, (i / 256) % 256, i % 256),
                at,
            );
        }
        assert_eq!(bucket.tracked(), MAX_IPS);

        let at = start + Duration::from_millis(MAX_IPS as u64);
        bucket.check_at("172.16.0.1", at);
        assert_eq!(
            bucket.tracked(),
            MAX_IPS,
            "the map must not grow past MAX_IPS"
        );
    }

    /// Two `RateLimiters` must not share state.
    ///
    /// This is why the limiters live on `AppState` rather than in statics
    /// (`api_rate_limit.py:78-80` uses module-level singletons; Rust must not
    /// copy that). With a static, "the fourth request is refused" would depend
    /// on which tests ran first, and the suite runs them in parallel.
    #[test]
    fn separate_limiters_do_not_share_buckets() {
        let a = RateLimiters::new();
        let b = RateLimiters::new();
        let now = Instant::now();

        for _ in 0..Tier::Destructive.burst() {
            assert!(a.for_tier(Tier::Destructive).check_at("10.0.0.1", now).0);
        }
        assert!(
            !a.for_tier(Tier::Destructive).check_at("10.0.0.1", now).0,
            "the first limiter is exhausted"
        );
        assert!(
            b.for_tier(Tier::Destructive).check_at("10.0.0.1", now).0,
            "a second limiter must start with a full bucket"
        );
    }

    #[test]
    fn tiers_route_to_distinct_buckets() {
        let limiters = RateLimiters::new();
        let now = Instant::now();
        // Exhaust destructive; write must be untouched.
        for _ in 0..3 {
            limiters
                .for_tier(Tier::Destructive)
                .check_at("10.0.0.1", now);
        }
        assert!(
            !limiters
                .for_tier(Tier::Destructive)
                .check_at("10.0.0.1", now)
                .0
        );
        assert!(limiters.for_tier(Tier::Write).check_at("10.0.0.1", now).0);
    }
}
