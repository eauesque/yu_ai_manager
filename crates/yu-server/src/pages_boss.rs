//! Boss-mode camouflage login/lock gate — WSJ skin (the only skin ported to
//! Rust). Ports `core/web/pages_boss_render.py` (orchestrator), the WSJ skin
//! `core/web/boss_skins/wsj.py` (CSS + body layout), and the edition
//! randomisation pools in `core/web/pages_boss_data.py` (RSS live-headline
//! fetching is intentionally skipped — fake stories suffice for camouflage).

use rand::seq::{IndexedRandom, SliceRandom};
use rand::Rng;
use serde_json::Value;

use crate::pages::html_escape;

/// Which gate is being rendered: the full PIN-entry page, or the quick-lock
/// overlay (unlock happens client-side via `/api/lock/unlock`).
pub enum BossMode {
    Pin,
    Lock,
}

// ── edition randomisation pools (ported from core/web/pages_boss_data.py) ──

const BRANDS: &[&str] = &[
    "Nikkei-ish Times",
    "Keizai Observer",
    "Shachiku Standard",
    "Kabushiki Chronicle",
    "Ledger Shinpo",
    "Toushi Weekly",
    "The Wall Treat Journal",
    "Bloomsburg Review",
    "Fishing Tyres",
    "The Econonomist",
    "Barrons Weekday",
    "Dow Janes Newswire",
    "Markit Watch",
    "Investors Dairy",
    "The Motley Fuel",
    "CNBN World",
    "Forex Factory Outlet",
    "The Guardiun Business",
    "FAX NEWS",
    "BVC WORLD NEWS",
    "MPR Breakable NEWS",
    "CBG NEWS",
    "Ski News",
    "ABG NEWS and Headlines",
    "PB$ Public Broadband for $",
];

const HEADLINES: &[(&str, &str)] = &[
    (
        "Bond Yields Ease as Investors Reprice Policy Path",
        "Major indices traded in narrow ranges, while sector rotation remained active beneath the surface.",
    ),
    (
        "AI Capex Wave Lifts Outlook for Chipmakers and Software Groups",
        "Investors balanced growth concerns with stronger enterprise spending signals, keeping tech leadership intact.",
    ),
    (
        "Commodities Retreat as Traders Lock in Gains from Recent Rally",
        "Energy-linked equities softened while defensive sectors outperformed in late-session trading.",
    ),
    (
        "Dollar Strengthens on Diverging Rate Expectations Across G7",
        "Currency markets responded to widening policy differentials, with exporters rallying.",
    ),
    (
        "Trade Tensions Resurface as Tariff Fears Rattle Asian Markets",
        "Uncertainty over trade policy rippled through global supply chains, lifting demand for hedging.",
    ),
    (
        "Real Estate Recovery Takes Shape as REIT Index Hits Year-High",
        "Expectations of peak interest rates are drawing capital back into property trusts.",
    ),
    (
        "Emerging Markets Draw Fresh Inflows as Rate Cuts Begin",
        "Narrowing interest-rate differentials spur a rotation into EM debt and equities.",
    ),
    (
        "IPO Pipeline Swells as Tech and Healthcare Deals Multiply",
        "Improved risk appetite is accelerating the pace of listings.",
    ),
    (
        "Global Inflation Cools, Markets Price In Policy Pivot",
        "Slowing consumer-price gains have fueled expectations of coordinated monetary easing.",
    ),
    (
        "ESG Scrutiny Intensifies as Regulators Push for Disclosure Standards",
        "Investors recalibrate sustainability strategies as greenwashing concerns grow.",
    ),
];

const STORIES: &[&str] = &[
    "Central banks signal a data-dependent pause at upcoming meetings",
    "Freight rates ease as shipping lanes continue to normalize",
    "Housing indicators show tentative signs of stabilization",
    "Emerging-market currencies trade mixed versus the dollar",
    "AI capex plans lift guidance across enterprise software names",
    "Semiconductor inventory metrics improve, boosting order outlook",
    "Cloud providers reiterate infrastructure investment targets",
    "Large-cap tech earnings surpass consensus on revenue growth",
    "Energy stocks pull back as commodities retreat from recent highs",
    "Consumer staples attract inflows on valuation appeal",
    "Strong payrolls data reinforces higher-for-longer rate outlook",
    "Gold extends rally as investors seek safe-haven assets",
    "Office vacancy rates drop for the first time in four quarters",
    "Data center REITs surge on AI-driven infrastructure demand",
    "Brazil central bank delivers third consecutive rate cut",
    "Indian equity market climbs to fourth-largest by capitalization",
    "AI startups filing for IPOs at fastest pace on record",
    "Green bond issuance surges 40% year over year",
    "US CPI undershoots consensus, boosting rate-cut bets",
    "Carbon credit trading volumes reach record highs globally",
];

const SECTIONS: &[&str] = &[
    "World",
    "Markets",
    "Economy",
    "Companies",
    "Tech",
    "Policy",
    "Opinion",
    "Commodities",
    "Currencies",
    "Fixed Income",
    "Regulation",
    "IPO Watch",
    "Real Estate",
    "Climate & Energy",
];

const BYLINES: &[&str] = &[
    "By Lionel Beige",
    "By Markets Desk",
    "By A. Ledger",
    "By C. Margin, London Bureau",
    "By R. Dividend & S. Yield",
    "By Capital Markets Team",
    "By D. Leverage, New York",
    "By Desk Tokyo",
    "By K. Sato",
    "By Y. Suzuki, Kabutocho Bureau",
];

const BREAKING: &[&str] = &[
    "Breaking: Equity futures swing sharply higher",
    "Breaking: Major central banks signal joint statement",
    "Breaking: FX moves ahead of key macro release",
    "Breaking: Crude oil drops 5% on supply concerns",
    "Breaking: US payrolls smash expectations, yields spike",
    "Breaking: ECB delivers surprise rate cut",
    "Breaking: Chipmaker raises full-year guidance sharply",
    "Breaking: Gold hits record high amid safe-haven demand",
];

const DESK_LABELS: &[&str] = &[
    "Analysis",
    "Briefing",
    "Markets Live",
    "Morning Note",
    "Desk View",
    "Deep Dive",
    "The Big Read",
    "Macro Pulse",
];

// ── WSJ skin-specific random pools (ported from core/web/boss_skins/wsj.py) ──

const ROMAN_VOLS: &[&str] = &[
    "CXXI",
    "CXXII",
    "CXXIII",
    "CXXIV",
    "CXXV",
    "CXXVI",
    "CLIII",
    "CLXXXVIII",
];
const WEATHER_LINES: &[&str] = &[
    "Tokyo: Mostly Cloudy 18\u{b0}C",
    "London: Showers 11\u{b0}C",
    "New York: Clear 14\u{b0}C",
    "Hong Kong: Humid 24\u{b0}C",
];
const PRICES: &[&str] = &["\u{a5}350", "\u{a3}3.50", "$4.00", "\u{20ac}3.20"];

/// CSS ported verbatim from `core/web/boss_skins/wsj.py::CSS`.
const WSJ_CSS: &str = r#"
:root{
  --bm-paper:#fdf9ef;--bm-paper-2:#f7f1e2;
  --bm-ink:#0d0c0a;--bm-ink-soft:#2a2620;--bm-ink-faint:#5e574b;
  --bm-rule:#7a6f5d;--bm-rule-soft:#c9bfa9;
  --bm-navy:#0e1a3a;--bm-accent:#9a1d1d;
  --bm-green:#1c4a1c;--bm-red:#8a1a1a;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bm-paper);color:var(--bm-ink);
  font-family:'Hoefler Text','Garamond Premier Pro','Adobe Caslon Pro','Iowan Old Style',Georgia,'Times New Roman',serif;
  font-feature-settings:"kern" 1,"liga" 1,"onum" 1;
  min-height:100vh;overflow:auto;
  background-image:
    radial-gradient(at 30% 0%,rgba(120,90,40,0.03),transparent 50%),
    repeating-linear-gradient(0deg,rgba(0,0,0,0.012) 0 1px,transparent 1px 4px);
  animation:bm-fade 540ms ease-out both}
@keyframes bm-fade{from{opacity:0;transform:translateY(4px);filter:blur(2px)}to{opacity:1;transform:none;filter:none}}
.wrap{max-width:1180px;margin:0 auto;padding:18px 36px 54px}
.eyebrow{display:flex;justify-content:space-between;gap:24px;align-items:center;
  padding:6px 0;border-top:1px solid var(--bm-ink);border-bottom:1px solid var(--bm-ink);
  font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--bm-ink-soft)}
.eyebrow .stars{color:var(--bm-accent);letter-spacing:0.4em}
.masthead{text-align:center;padding:22px 0 12px;border-bottom:5px double var(--bm-ink)}
.brand{font-family:'Hoefler Text','Adobe Caslon Pro',Georgia,serif;
  font-weight:900;font-size:clamp(46px,7.6vw,84px);letter-spacing:-0.012em;line-height:.95;
  color:var(--bm-ink);margin:0;text-transform:uppercase}
.tagline{margin-top:6px;font-style:italic;font-size:12px;color:var(--bm-ink-faint);letter-spacing:0.04em}
.auth-bar{display:flex;align-items:center;justify-content:center;gap:8px;
  margin:12px 0 0;padding:10px 12px;background:var(--bm-paper-2);border-bottom:1px solid var(--bm-ink)}
.auth-bar .auth-label{font-size:10.5px;letter-spacing:0.28em;text-transform:uppercase;color:var(--bm-navy);font-weight:800}
.auth-bar input[type=password],.auth-bar input[type=text]{
  font-size:14px;padding:7px 10px;border:1px solid var(--bm-ink);background:var(--bm-paper);width:140px;
  letter-spacing:3px;text-align:center;font-family:'JetBrains Mono','SF Mono',Menlo,monospace}
.auth-bar input:focus{outline:2px solid var(--bm-accent);outline-offset:1px}
.auth-bar button{padding:8px 14px;border:1px solid var(--bm-ink);background:var(--bm-paper);
  cursor:pointer;font:inherit;font-size:11px;letter-spacing:0.28em;text-transform:uppercase;font-weight:700;
  color:var(--bm-ink);transition:background 160ms ease,color 160ms ease}
.auth-bar button:hover{background:var(--bm-ink);color:var(--bm-paper)}
.auth-bar .eye{padding:7px 9px;letter-spacing:0;font-size:13px}
.sec-line{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:0 18px;
  margin:10px 0 0;padding:8px 0;border-bottom:1px solid var(--bm-ink);
  font-size:11px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink);font-weight:700}
.sec-line span+span::before{content:'\25aa';color:var(--bm-ink);opacity:.6;margin-right:18px;font-size:8px;letter-spacing:0;transform:translateY(-1px)}
.breaking{margin:14px 0 8px;background:var(--bm-accent);color:#fff;padding:7px 12px;
  font-size:11px;font-weight:800;letter-spacing:0.5em;text-transform:uppercase;text-align:center}
.grid{display:grid;grid-template-columns:minmax(0,2.3fr) 1px minmax(260px,1fr);gap:0 24px;margin-top:18px}
.rule-v{background:var(--bm-rule-soft);margin:0}
.desk{display:inline-block;font-size:11px;letter-spacing:0.36em;text-transform:uppercase;
  color:var(--bm-navy);font-weight:800;margin-bottom:8px;border-bottom:2px solid var(--bm-navy);padding:0 0 3px}
h1{font-family:'Hoefler Text','Adobe Caslon Pro',Georgia,serif;
  margin:0 0 10px;font-size:clamp(34px,4.2vw,52px);line-height:1.02;font-weight:900;
  letter-spacing:-0.012em;color:var(--bm-ink)}
h1::after{content:'';display:block;width:64px;height:2px;background:var(--bm-ink);margin:14px 0 0}
.sub{margin:14px 0 8px;font-style:italic;line-height:1.45;font-size:18px;color:var(--bm-ink-soft);max-width:60ch;font-weight:500}
.byline{margin:8px 0 16px;font-size:10.5px;color:var(--bm-ink-faint);letter-spacing:0.22em;text-transform:uppercase;font-weight:700}
.byline em{font-style:normal;color:var(--bm-ink)}
.stories{margin-top:16px;padding-top:14px;border-top:1px solid var(--bm-ink)}
.stories h3{margin:0 0 10px;font-size:11.5px;letter-spacing:0.36em;text-transform:uppercase;color:var(--bm-navy);font-weight:800}
.stories ul{list-style:none;margin:0;padding:0;column-count:2;column-gap:24px;column-rule:1px solid var(--bm-rule-soft)}
.stories li{padding:6px 0 8px;border-bottom:1px dotted var(--bm-rule-soft);font-size:14px;line-height:1.4;
  color:var(--bm-ink-soft);position:relative;padding-left:18px;break-inside:avoid}
.stories li::before{content:'\25aa';position:absolute;left:0;top:7px;color:var(--bm-ink);font-size:10px}
.sidebar{padding:0 4px;height:max-content}
.sidebar-title{font-family:'Hoefler Text','Adobe Caslon Pro',Georgia,serif;
  font-size:24px;font-weight:900;letter-spacing:-0.005em;margin:0 0 4px;color:var(--bm-ink);
  border-bottom:3px double var(--bm-ink);padding-bottom:6px}
.sidebar-sub{font-size:9.5px;letter-spacing:0.3em;text-transform:uppercase;color:var(--bm-ink-faint);margin:6px 0 14px;font-weight:700}
.quotes{font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;
  font-size:12.5px;line-height:2;color:var(--bm-ink);font-feature-settings:"tnum" 1;
  border-top:1px solid var(--bm-ink);padding-top:8px;margin-top:8px}
.quotes::before{content:'WHAT MARKETS DID';display:block;font-family:'Hoefler Text',Georgia,serif;
  font-size:10.5px;letter-spacing:0.32em;color:var(--bm-navy);font-weight:800;margin-bottom:6px}
.q-row{display:flex;justify-content:space-between;gap:12px}
.q-row[data-delta="up"]   .q-val{color:var(--bm-green)}
.q-row[data-delta="down"] .q-val{color:var(--bm-red)}
.q-label{letter-spacing:0.05em}
.q-val{font-weight:700;font-variant-numeric:tabular-nums}
.q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
.q-meta{margin-top:10px;padding-top:8px;font-size:10px;color:var(--bm-ink-faint);
  letter-spacing:0.18em;text-transform:uppercase;border-top:1px solid var(--bm-rule-soft)}
.q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-ink);font-weight:700;letter-spacing:0.26em}
.hint{margin-top:8px;font-size:10px;color:var(--bm-ink-faint);letter-spacing:0.18em;text-transform:uppercase;text-align:center}
#error{color:var(--bm-accent);font-size:11px;min-height:16px;margin-top:8px;text-align:center;letter-spacing:0.16em;text-transform:uppercase;font-weight:700}
@media(max-width:720px){
  .grid{grid-template-columns:1fr}.rule-v{display:none}.sidebar{margin-top:22px}.stories ul{column-count:1}
  .auth-bar{flex-wrap:wrap}
}
"#;

/// Base toggle-visibility script, present on both Pin and Lock modes
/// (ported from `pages_boss_render.py::render_boss_page`). Together with
/// `LOCK_JS` this is emitted inside a single nonce'd `<script nonce="{nonce}">`
/// tag in `boss_gate_html` — the nonce comes from the per-request
/// `security::CspNonce` extension — so it satisfies the strict
/// `script-src 'strict-dynamic' 'nonce-…'` CSP.
const TOGGLE_SCRIPT: &str = r#"
function toggleVis(id,btn){
  var inp=document.getElementById(id);if(!inp)return;
  var h=inp.type==='password';inp.type=h?'text':'password';
  if(btn)btn.textContent=h?'🙈':'👁';
}
document.addEventListener('click',function(ev){
  var b=ev.target.closest('[data-toggle-vis]');
  if(b)toggleVis(b.getAttribute('data-toggle-vis'),b);
});"#;

/// Lock-mode-only inline JS: calls `/api/lock/unlock` and reloads on success
/// (ported verbatim from `pages_boss_render.py::render_boss_page`).
const LOCK_JS: &str = r#"
    async function unlockApp(){
      var pin=document.getElementById('lockPin').value;
      var res=await fetch('/api/lock/unlock',{
        method:'POST',headers:{'Content-Type':'application/json','X-Requested-With':'XMLHttpRequest'},
        body:JSON.stringify({pin:pin})
      });
      if(res.ok){window.location.reload()}else{
        var d=await res.json();
        document.getElementById('error').textContent=d.error||'Failed';
        document.getElementById('lockPin').value='';
        document.getElementById('lockPin').focus();
      }
    }
    document.addEventListener('click',function(ev){
      if(ev.target.closest('#unlockBtn'))unlockApp();
    });
    document.addEventListener('keydown',function(ev){
      if(ev.key==='Enter'&&ev.target&&ev.target.id==='lockPin')unlockApp();
    });"#;

struct Edition {
    brand: String,
    headline: String,
    subhead: String,
    stories: Vec<String>,
    sections: Vec<String>,
    byline: String,
    show_breaking: bool,
    breaking_text: String,
    desk_label: String,
}

/// Mirrors `pick_boss_edition()` in `pages_boss_data.py`, minus the RSS
/// real-headline mixing (fake `STORIES` suffice for camouflage).
fn pick_edition() -> Edition {
    let mut rng = rand::rng();

    let brand: &str = BRANDS.choose(&mut rng).unwrap();
    let (headline, subhead) = *HEADLINES.choose(&mut rng).unwrap();

    let mut stories: Vec<String> = STORIES
        .choose_multiple(&mut rng, 3.min(STORIES.len()))
        .map(|s| (*s).to_string())
        .collect();
    stories.shuffle(&mut rng);

    let sections: Vec<String> = SECTIONS
        .choose_multiple(&mut rng, 5.min(SECTIONS.len()))
        .map(|s| (*s).to_string())
        .collect();

    let byline: &str = BYLINES.choose(&mut rng).unwrap();
    let show_breaking = rng.random_bool(0.38);
    let breaking_text = if show_breaking {
        (*BREAKING.choose(&mut rng).unwrap()).to_string()
    } else {
        String::new()
    };
    let desk_label: &str = DESK_LABELS.choose(&mut rng).unwrap();

    Edition {
        brand: brand.to_string(),
        headline: headline.to_string(),
        subhead: subhead.to_string(),
        stories,
        sections,
        byline: byline.to_string(),
        show_breaking,
        breaking_text,
        desk_label: desk_label.to_string(),
    }
}

/// `{n:,}` thousands-grouping, matching Python's `f'{n:,}'` for non-negative
/// integers (only ever called with the small positive issue-number range).
fn format_thousands(n: u32) -> String {
    let digits = n.to_string();
    let bytes = digits.as_bytes();
    let mut out = String::with_capacity(bytes.len() + bytes.len() / 3);
    for (i, b) in bytes.iter().enumerate() {
        if i > 0 && (bytes.len() - i).is_multiple_of(3) {
            out.push(',');
        }
        out.push(*b as char);
    }
    out
}

/// Shared `.q-row[data-delta]` markup (ported from
/// `core/web/boss_skins/__init__.py::_quote_rows`, which is what actually
/// feeds `ctx['quotes_html']` for the WSJ skin at runtime).
fn quote_rows_html(quotes: &[Value]) -> String {
    let mut out = String::new();
    for q in quotes {
        let label_full = q.get("label").and_then(|v| v.as_str()).unwrap_or("");
        let label: String = label_full.chars().take(8).collect();
        let value = q.get("value").and_then(|v| v.as_str()).unwrap_or("");
        let (sign, glyph) = if value.starts_with('-') {
            ("down", "\u{25bc}")
        } else if value.starts_with('+') {
            ("up", "\u{25b2}")
        } else {
            ("flat", "\u{b7}")
        };
        out.push_str(&format!(
            r#"<div class="q-row" data-delta="{sign}"><span class="q-label">{}</span><span class="q-val"><span class="q-glyph">{glyph}</span>{}</span></div>"#,
            html_escape(&label),
            html_escape(value),
        ));
    }
    out
}

/// Auth bar + error placeholder for the requested mode (mirrors the
/// `mode == 'pin'` / else branches of `render_boss_page`).
fn render_auth_bar(mode: &BossMode, error: &str, next_url: &str) -> (String, String) {
    match mode {
        BossMode::Pin => {
            let next_val = html_escape(next_url);
            let auth_bar = format!(
                r#"<form class="auth-bar" method="POST" action="/_pin_check" autocomplete="off"><input type="hidden" name="next" value="{next_val}"><span class="auth-label">Subscriber Login</span><input type="password" id="pinInput" name="pin" maxlength="64" autofocus placeholder="PIN"><button type="button" class="eye" data-toggle-vis="pinInput">&#x1f441;</button><button type="submit">Sign in</button></form>"#
            );
            let error_html = format!(r#"<div id="error">{}</div>"#, html_escape(error));
            (auth_bar, error_html)
        }
        BossMode::Lock => {
            let auth_bar = r#"<div class="auth-bar"><span class="auth-label">Subscriber Login</span><input type="password" id="lockPin" maxlength="64" autofocus placeholder="PIN" autocomplete="off"><button type="button" class="eye" data-toggle-vis="lockPin">&#x1f441;</button><button type="button" id="unlockBtn">Sign in</button></div>"#.to_string();
            // Lock-mode errors are surfaced client-side by the inline
            // unlockApp() script; the server-rendered placeholder stays
            // empty regardless of `error` (matches Python's else branch).
            let error_html = r#"<div id="error"></div>"#.to_string();
            (auth_bar, error_html)
        }
    }
}

/// Ported from `core/web/boss_skins/wsj.py::render`.
fn render_wsj_body(
    auth_bar: &str,
    error_html: &str,
    ed: &Edition,
    quotes_html: &str,
    src_label: &str,
) -> String {
    let mut rng = rand::rng();
    let vol: &str = ROMAN_VOLS.choose(&mut rng).unwrap();
    let issue_no = format_thousands(rng.random_range(3000..=7999));
    let weather: &str = WEATHER_LINES.choose(&mut rng).unwrap();
    let price: &str = PRICES.choose(&mut rng).unwrap();
    let date_str = chrono::Local::now()
        .format("%A, %B %-d, %Y")
        .to_string()
        .to_uppercase();

    let brand = html_escape(&ed.brand);
    let headline = html_escape(&ed.headline);
    let subhead = html_escape(&ed.subhead);
    let byline = html_escape(&ed.byline);
    let desk_label = html_escape(&ed.desk_label);
    let stories_html: String = ed
        .stories
        .iter()
        .map(|s| format!("<li>{}</li>", html_escape(s)))
        .collect();
    let sections_html: String = ed
        .sections
        .iter()
        .map(|s| format!("<span>{}</span>", html_escape(s)))
        .collect();
    let breaking_html = if ed.show_breaking {
        format!(
            r#"<div class="breaking">{}</div>"#,
            html_escape(&ed.breaking_text)
        )
    } else {
        String::new()
    };

    let src_color = if src_label == "LIVE" {
        "var(--bm-green)"
    } else {
        "var(--bm-red)"
    };
    let q_meta = format!(
        r#"<span class="q-badge" style="color:{src_color};">{}</span>"#,
        html_escape(src_label)
    );

    format!(
        r#"<style>{WSJ_CSS}</style>
<div class="wrap">
  <div class="eyebrow">
    <span>VOL. {vol} &middot; NO. {issue_no}</span>
    <span class="stars">&#x2605; &#x2605; &#x2605; &#x2605;</span>
    <span>{date_str}</span>
    <span>&copy; 2026 &middot; {price}</span>
  </div>
  <header class="masthead">
    <h1 class="brand">{brand}</h1>
    <div class="tagline">{weather} &nbsp;&middot;&nbsp; wsjt.com</div>
  </header>
  {auth_bar}
  <nav class="sec-line">{sections_html}</nav>
  {breaking_html}
  <div class="grid">
    <main>
      <span class="desk">{desk_label}</span>
      <h1>{headline}</h1>
      <p class="sub">{subhead}</p>
      <div class="byline"><em>{byline}</em></div>
      <section class="stories">
        <h3>What's News &mdash; Top Stories</h3>
        <ul>{stories_html}</ul>
      </section>
    </main>
    <div class="rule-v"></div>
    <aside class="sidebar">
      <div class="sidebar-title">Watchlist</div>
      <div class="sidebar-sub">Late-Session &middot; Indicative</div>
      <div class="quotes">{quotes_html}</div>
      <div class="q-meta">{q_meta}</div>
      {error_html}
      <div class="hint">Press Esc to return</div>
    </aside>
  </div>
</div>"#
    )
}

/// Renders the full self-contained boss-mode gate page (`<!DOCTYPE html>` …
/// `</html>`) for the requested mode. Ported from
/// `pages_boss_render.py::render_boss_page`, restricted to the WSJ skin.
pub async fn boss_gate_html(mode: BossMode, error: &str, next_url: &str, nonce: &str) -> String {
    let quotes_val = crate::routes::market_quotes::cached_quotes_or_fallback();
    let source = quotes_val
        .get("source")
        .and_then(|v| v.as_str())
        .unwrap_or("fallback");
    let src_label = if source == "yahoo" {
        "LIVE"
    } else {
        "FALLBACK"
    };
    let quotes_arr: Vec<Value> = quotes_val
        .get("quotes")
        .and_then(|v| v.as_array())
        .cloned()
        .unwrap_or_default();
    let quotes_html = quote_rows_html(&quotes_arr);

    let ed = pick_edition();
    let (auth_bar, error_html) = render_auth_bar(&mode, error, next_url);
    let body_html = render_wsj_body(&auth_bar, &error_html, &ed, &quotes_html, src_label);

    let lock_js = match mode {
        BossMode::Lock => LOCK_JS,
        BossMode::Pin => "",
    };
    let script = format!("{TOGGLE_SCRIPT}{lock_js}");

    let title_brand = html_escape(&ed.brand);

    format!(
        r#"<!DOCTYPE html><html lang="ja"><head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title_brand} - Subscriber Access</title>
</head><body data-skin="wsj">
{body_html}
<script nonce="{nonce}">{script}
</script>
</body></html>"#
    )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    async fn pin_mode_renders_form_and_escapes_error() {
        let html = boss_gate_html(BossMode::Pin, "<x>", "/n", "testnonce").await;
        assert!(html.contains(r#"action="/_pin_check""#));
        assert!(html.contains(r#"type="password""#));
        assert!(!html.contains("<x>"));
        assert!(html.contains("&lt;x&gt;"));
        assert!(html.contains("/n"));
        assert!(!html.contains("_csrf_token"));
    }

    #[tokio::test]
    async fn lock_mode_renders_unlock_button_and_endpoint() {
        let html = boss_gate_html(BossMode::Lock, "", "", "testnonce").await;
        assert!(html.contains(r#"id="unlockBtn""#));
        assert!(html.contains("/api/lock/unlock"));
        assert!(html.contains("<script nonce="));
    }

    #[test]
    fn format_thousands_groups_correctly() {
        assert_eq!(format_thousands(3421), "3,421");
        assert_eq!(format_thousands(999), "999");
        assert_eq!(format_thousands(7999), "7,999");
    }
}
