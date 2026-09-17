"""Boss-mode skin: WSJ-style cream broadsheet."""

from __future__ import annotations

import os
import random
from datetime import UTC, datetime
from typing import Any

ROMAN_VOLS = ['CXXI', 'CXXII', 'CXXIII', 'CXXIV', 'CXXV', 'CXXVI', 'CLIII', 'CLXXXVIII']
WEATHER_LINES = [
    'Tokyo: Mostly Cloudy 18°C', 'London: Showers 11°C',
    'New York: Clear 14°C', 'Hong Kong: Humid 24°C',
]
PRICES = ['¥350', '£3.50', '$4.00', '€3.20']

CSS = """
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
.sec-line span+span::before{content:'▪';color:var(--bm-ink);opacity:.6;margin-right:18px;font-size:8px;letter-spacing:0;transform:translateY(-1px)}
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
.stories li::before{content:'▪';position:absolute;left:0;top:7px;color:var(--bm-ink);font-size:10px}
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
"""


def render(ctx: dict[str, Any]) -> str:
    quotes_html = ctx['quotes_html']
    src_label = ctx['src_label']
    src_color = 'var(--bm-green)' if src_label == 'LIVE' else 'var(--bm-red)'
    q_meta = f'<span class="q-badge" style="color:{src_color};">{src_label}</span>'

    vol = random.choice(ROMAN_VOLS)
    issue_no = f'{3000 + random.randint(0, 4999):,}'
    weather = random.choice(WEATHER_LINES)
    price = random.choice(PRICES)
    fmt = '%A, %B %#d, %Y' if os.name == 'nt' else '%A, %B %-d, %Y'
    date_str = datetime.now(tz=UTC).astimezone().strftime(fmt).upper()

    return f'''<style>{CSS}</style>
<div class="wrap">
  <div class="eyebrow">
    <span>VOL. {vol} &middot; NO. {issue_no}</span>
    <span class="stars">&#x2605; &#x2605; &#x2605; &#x2605;</span>
    <span>{date_str}</span>
    <span>&copy; 2026 &middot; {price}</span>
  </div>
  <header class="masthead">
    <h1 class="brand">{ctx["brand"]}</h1>
    <div class="tagline">{weather} &nbsp;&middot;&nbsp; wsjt.com</div>
  </header>
  {ctx["auth_bar"]}
  <nav class="sec-line">{ctx["sections_html"]}</nav>
  {ctx["breaking_html"]}
  <div class="grid">
    <main>
      <span class="desk">{ctx["desk_label"]}</span>
      <h1>{ctx["headline"]}</h1>
      <p class="sub">{ctx["subhead"]}</p>
      <div class="byline"><em>{ctx["byline"]}</em></div>
      <section class="stories">
        <h3>What's News &mdash; Top Stories</h3>
        <ul>{ctx["stories_html"]}</ul>
      </section>
    </main>
    <div class="rule-v"></div>
    <aside class="sidebar">
      <div class="sidebar-title">Watchlist</div>
      <div class="sidebar-sub">Late-Session &middot; Indicative</div>
      <div class="quotes">{quotes_html}</div>
      <div class="q-meta">{q_meta}</div>
      {ctx["error_html"]}
      <div class="hint">Press Esc to return</div>
    </aside>
  </div>
</div>'''
