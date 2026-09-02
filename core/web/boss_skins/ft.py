"""Boss-mode skin: FT-pink refined broadsheet."""

from __future__ import annotations

import os
import random
from datetime import UTC, datetime
from typing import Any

ROMAN_VOLS = ['CXXI', 'CXXII', 'CXXIII', 'CXXIV', 'CXXV', 'CXXVI', 'CLIII', 'CLXXXVIII']
EDITION_TAGS = ['Late Edition', 'Final Edition', 'Morning Edition', 'City Edition', 'National Edition']
WEATHER_LINES = [
    'Tokyo: Mostly Cloudy 18°C', 'London: Showers 11°C',
    'New York: Clear 14°C', 'Hong Kong: Humid 24°C',
    'Frankfurt: Overcast 9°C', 'Singapore: Storms 28°C',
]
PRICES = ['¥350', '¥420', '£3.50', '$4.00', '€3.20', 'HK$15']

CSS = """
:root{
  --bm-paper:#fff1e5;--bm-paper-deep:#f6e7d8;
  --bm-ink:#1a1410;--bm-ink-soft:#433c35;--bm-ink-faint:#6f665b;
  --bm-rule:#c6b9a6;--bm-rule-soft:#ddd0bd;
  --bm-accent:#b30f0f;--bm-green:#1f3f1f;--bm-red:#7b1e1e;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bm-paper);color:var(--bm-ink);
  font-family:'Iowan Old Style','Palatino Linotype',Palatino,P052,'Book Antiqua',Georgia,'Hiragino Mincho ProN','Yu Mincho',serif;
  font-feature-settings:"kern" 1,"liga" 1,"onum" 1;
  min-height:100vh;overflow:auto;
  background-image:
    radial-gradient(at 12% 18%,rgba(80,40,20,0.04),transparent 38%),
    radial-gradient(at 88% 76%,rgba(80,40,20,0.03),transparent 42%),
    repeating-linear-gradient(0deg,rgba(0,0,0,0.012) 0 1px,transparent 1px 3px);
  animation:bm-fade 540ms ease-out both}
@keyframes bm-fade{from{opacity:0;transform:translateY(4px);filter:blur(2px)}to{opacity:1;transform:none;filter:none}}
.wrap{max-width:1180px;margin:0 auto;padding:24px 40px 56px;position:relative}
.eyebrow{display:flex;justify-content:space-between;align-items:center;
  font-size:10.5px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink-faint);padding-bottom:6px}
.eyebrow strong{color:var(--bm-ink);font-weight:600;letter-spacing:0.36em}
.masthead{text-align:center;padding:4px 0 12px;
  border-top:1px solid var(--bm-ink);border-bottom:3px double var(--bm-ink)}
.brand{font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text','Big Caslon',Garamond,'Times New Roman',serif;
  font-weight:800;font-size:clamp(40px,6.4vw,72px);letter-spacing:-0.005em;
  line-height:1;margin:10px 0 6px;color:var(--bm-ink)}
.brand-flank{font-weight:400;opacity:.55;padding:0 18px;font-size:.58em;vertical-align:0.32em;letter-spacing:0}
.tagline{font-style:italic;font-size:13px;color:var(--bm-ink-faint);letter-spacing:0.04em;margin-bottom:4px}
.dateline{display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:7px 6px;margin-top:8px;
  border-top:1px solid var(--bm-ink);border-bottom:1px solid var(--bm-ink);
  font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--bm-ink-soft)}
.dateline span{white-space:nowrap}
.dateline .mid{letter-spacing:0.22em;color:var(--bm-ink)}
.auth-bar{display:flex;align-items:center;justify-content:center;gap:8px;
  margin:14px 0 8px;padding:10px 12px;border:1px solid var(--bm-rule);
  background:var(--bm-paper-deep)}
.auth-bar .auth-label{font-size:10.5px;letter-spacing:0.28em;text-transform:uppercase;color:var(--bm-ink-soft);font-weight:600}
.auth-bar input[type=password],.auth-bar input[type=text]{
  font-size:14px;padding:7px 10px;border:1px solid var(--bm-ink);
  background:var(--bm-paper);width:140px;letter-spacing:3px;text-align:center;
  font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace}
.auth-bar input:focus{outline:2px solid var(--bm-accent);outline-offset:1px}
.auth-bar button{padding:8px 14px;border:1px solid var(--bm-ink);background:var(--bm-paper);
  cursor:pointer;font-family:inherit;font-size:11px;letter-spacing:0.28em;text-transform:uppercase;
  color:var(--bm-ink);transition:background 160ms ease,color 160ms ease}
.auth-bar button:hover{background:var(--bm-ink);color:var(--bm-paper)}
.auth-bar .eye{padding:7px 9px;letter-spacing:0;font-size:13px}
.breaking{margin:14px 0 4px;background:var(--bm-accent);color:#fff;padding:8px 12px;
  font-size:11px;font-weight:700;letter-spacing:0.5em;text-transform:uppercase;text-align:center}
.sec-line{display:flex;justify-content:center;flex-wrap:wrap;gap:4px 14px;
  margin:14px 0 18px;padding-bottom:12px;border-bottom:1px solid var(--bm-rule);
  font-size:10.5px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink-soft)}
.sec-line span{display:inline-flex;align-items:center}
.sec-line span+span::before{content:'◆';opacity:.4;margin-right:14px;font-size:7px;letter-spacing:0;transform:translateY(-1px)}
.grid{display:grid;grid-template-columns:minmax(0,2.1fr) 1px minmax(280px,1fr);gap:0 26px}
.rule-v{background:var(--bm-rule);margin:6px 0}
.desk{display:inline-block;font-size:10.5px;letter-spacing:0.36em;text-transform:uppercase;
  color:var(--bm-accent);font-weight:700;margin-bottom:10px;
  border-top:1px solid var(--bm-accent);border-bottom:1px solid var(--bm-accent);padding:4px 8px 3px}
h1{font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text','Big Caslon',Garamond,serif;
  margin:0 0 14px;font-size:clamp(34px,4.2vw,50px);line-height:1.05;font-weight:700;
  letter-spacing:-0.005em;color:var(--bm-ink)}
.sub{margin:0 0 18px;color:var(--bm-ink-soft);line-height:1.55;font-size:19px;max-width:56ch;font-style:italic}
.sub::first-letter{font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text',Garamond,serif;
  font-style:normal;font-weight:800;float:left;font-size:4.4em;line-height:.85;
  padding:4px 10px 0 0;color:var(--bm-ink)}
.byline{margin:0 0 18px;font-size:11px;color:var(--bm-ink-faint);letter-spacing:0.2em;text-transform:uppercase}
.byline em{font-style:normal;color:var(--bm-ink-soft)}
.stories{border-top:3px double var(--bm-rule);padding-top:14px;margin-top:6px}
.stories h3{margin:0 0 10px;font-size:11px;letter-spacing:0.36em;text-transform:uppercase;color:var(--bm-ink);font-weight:700}
.stories ul{list-style:none;margin:0;padding:0}
.stories li{padding:8px 0;border-bottom:1px solid var(--bm-rule-soft);
  font-size:15px;line-height:1.45;color:var(--bm-ink-soft);position:relative;padding-left:22px}
.stories li::before{content:'§';position:absolute;left:0;top:8px;
  font-family:'Bodoni 72','Hoefler Text',Garamond,serif;color:var(--bm-accent);font-weight:700;font-size:14px}
.sidebar{background:linear-gradient(180deg,var(--bm-paper-deep) 0%,var(--bm-paper) 100%);
  border:1px solid var(--bm-rule);padding:16px 18px;height:max-content;position:relative}
.sidebar::before{content:'';position:absolute;inset:4px;border:1px solid var(--bm-rule-soft);pointer-events:none}
.sidebar-title{font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text',Garamond,serif;
  font-size:22px;font-weight:700;letter-spacing:0.02em;margin:0 0 4px;color:var(--bm-ink);text-align:center}
.sidebar-sub{font-size:9.5px;letter-spacing:0.3em;text-transform:uppercase;color:var(--bm-ink-faint);
  text-align:center;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--bm-rule)}
.quotes{font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;
  font-size:12.5px;line-height:2;color:var(--bm-ink);font-feature-settings:"tnum" 1,"zero" 1}
.q-row{display:flex;justify-content:space-between;gap:12px;padding:0 2px;border-bottom:1px dotted var(--bm-rule-soft)}
.q-row:last-child{border-bottom:0}
.q-row[data-delta="up"]   .q-val{color:var(--bm-green)}
.q-row[data-delta="down"] .q-val{color:var(--bm-red)}
.q-label{letter-spacing:0.05em}
.q-val{font-weight:700;font-variant-numeric:tabular-nums}
.q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
.q-meta{margin-top:10px;padding-top:8px;font-size:10px;color:var(--bm-ink-faint);
  letter-spacing:0.18em;text-transform:uppercase;text-align:center;border-top:1px solid var(--bm-rule-soft)}
.q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-rule);font-weight:700;letter-spacing:0.26em;background:var(--bm-paper)}
.hint{margin-top:8px;font-size:10px;color:var(--bm-ink-faint);letter-spacing:0.18em;text-transform:uppercase;text-align:center}
#error{color:var(--bm-accent);font-size:11px;min-height:16px;margin-top:8px;text-align:center;letter-spacing:0.16em;text-transform:uppercase;font-weight:600}
.fold-shadow{pointer-events:none;position:absolute;left:0;right:0;top:38%;height:14px;
  background:linear-gradient(180deg,transparent,rgba(0,0,0,0.05),transparent);filter:blur(0.5px)}
@media(max-width:720px){
  .grid{grid-template-columns:1fr}
  .rule-v{display:none}
  .sidebar{margin-top:22px}
  .dateline{font-size:9.5px;gap:6px;flex-wrap:wrap;justify-content:center}
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
    edit_tag = random.choice(EDITION_TAGS)
    weather = random.choice(WEATHER_LINES)
    price = random.choice(PRICES)
    fmt = '%A, %B %#d, %Y' if os.name == 'nt' else '%A, %B %-d, %Y'
    date_str = datetime.now(tz=UTC).astimezone().strftime(fmt).upper()

    return f'''<style>{CSS}</style>
<div class="wrap">
  <div class="eyebrow">
    <span>EST. <strong>MCMLXXXVIII</strong></span>
    <span>{edit_tag}</span>
    <span>{price}</span>
  </div>
  <header class="masthead">
    <div class="brand"><span class="brand-flank">&#x2766;</span>{ctx["brand"]}<span class="brand-flank">&#x2766;</span></div>
    <div class="tagline">All the markets, fit to print.</div>
    <div class="dateline">
      <span>Vol. {vol} &middot; No. {issue_no}</span>
      <span class="mid">{date_str}</span>
      <span>{weather}</span>
    </div>
  </header>
  {ctx["auth_bar"]}
  {ctx["breaking_html"]}
  <div class="sec-line">{ctx["sections_html"]}</div>
  <div class="grid">
    <main>
      <span class="desk">{ctx["desk_label"]}</span>
      <h1>{ctx["headline"]}</h1>
      <p class="sub">{ctx["subhead"]}</p>
      <div class="byline"><em>{ctx["byline"]}</em></div>
      <section class="stories">
        <h3>Top Stories</h3>
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
  <div class="fold-shadow"></div>
</div>'''
