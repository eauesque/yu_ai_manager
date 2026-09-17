"""Boss-mode skin: Bloomberg-style terminal feed."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

SPARKS = ['▁▂▃▅▇▆▄', '▇▅▃▂▁▂▃', '▃▄▅▆▇▆▅', '▁▁▂▃▅▆▇', '▇▆▄▃▂▁▁', '▂▃▄▅▄▃▂']

CSS = """
:root{
  --bm-bg:#0a0a14;--bm-bg-2:#11111c;--bm-bg-panel:#0e0e18;
  --bm-text:#f3e6c7;--bm-text-soft:#c9b890;--bm-text-faint:#7a6e50;
  --bm-rule:#3a3024;--bm-rule-soft:#26201a;
  --bm-accent:#fb8500;--bm-accent-deep:#cc6900;
  --bm-green:#7dffaf;--bm-red:#ff5572;--bm-cyan:#5ed5ff;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bm-bg);color:var(--bm-text);
  font-family:'JetBrains Mono','Cascadia Mono','Consolas','SF Mono',Menlo,monospace;
  font-feature-settings:"tnum" 1,"zero" 1;
  min-height:100vh;overflow:auto;
  background-image:
    repeating-linear-gradient(0deg,rgba(255,200,80,0.018) 0 1px,transparent 1px 3px),
    radial-gradient(at 50% -10%,rgba(251,133,0,0.07),transparent 60%);
  animation:bm-fade 380ms ease-out both}
@keyframes bm-fade{from{opacity:0;filter:blur(2px)}to{opacity:1;filter:none}}
body::before{content:'';position:fixed;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(255,255,255,0.014) 0 2px,transparent 2px 4px);mix-blend-mode:overlay}
.fnbar{display:flex;gap:0;border-bottom:1px solid var(--bm-rule);
  background:linear-gradient(180deg,var(--bm-bg-2),var(--bm-bg));
  font-size:11px;line-height:1;letter-spacing:0.04em}
.fnbar span{padding:8px 11px;color:var(--bm-text-soft);border-right:1px solid var(--bm-rule-soft)}
.fnbar span b{color:var(--bm-accent);font-weight:700;margin-right:6px}
.fnbar .fn-status{margin-left:auto;color:var(--bm-text-faint);border-right:0;border-left:1px solid var(--bm-rule-soft)}
.wrap{max-width:1280px;margin:0 auto;padding:14px 22px 28px}
.eyebrow{display:flex;justify-content:space-between;align-items:center;
  font-size:10.5px;color:var(--bm-text-faint);padding:0 0 10px;letter-spacing:0.06em}
.eyebrow b{color:var(--bm-accent)}
.masthead{background:var(--bm-accent);color:#0c0a06;padding:8px 14px;
  display:flex;justify-content:space-between;align-items:center;
  border:1px solid var(--bm-accent-deep);box-shadow:inset 0 -1px 0 rgba(0,0,0,0.3)}
.brand{font-size:18px;font-weight:800;letter-spacing:0.04em;text-transform:uppercase}
.brand::before{content:'< ';opacity:.55}
.brand::after{content:' >';opacity:.55}
.mast-meta{font-size:11px;letter-spacing:0.06em;font-weight:700}
.auth-bar{display:flex;align-items:center;justify-content:flex-start;gap:8px;
  margin:14px 0 0;padding:8px 12px;border:1px solid var(--bm-rule);background:var(--bm-bg-panel)}
.auth-bar .auth-label{font-size:10.5px;letter-spacing:0.18em;color:var(--bm-accent);font-weight:700}
.auth-bar .auth-label::before{content:'> '}
.auth-bar input[type=password],.auth-bar input[type=text]{
  font-size:14px;padding:7px 10px;border:1px solid var(--bm-rule);background:#000;color:var(--bm-text);
  width:160px;letter-spacing:3px;text-align:left;font-family:inherit;outline:none}
.auth-bar input:focus{border-color:var(--bm-accent);box-shadow:0 0 0 1px var(--bm-accent)}
.auth-bar button{padding:7px 14px;border:1px solid var(--bm-accent);background:transparent;
  cursor:pointer;font-family:inherit;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;
  color:var(--bm-accent);font-weight:700;transition:background 160ms ease,color 160ms ease}
.auth-bar button:hover{background:var(--bm-accent);color:#0c0a06}
.auth-bar .eye{padding:7px 9px;letter-spacing:0;font-size:13px}
.sec-line{display:flex;flex-wrap:wrap;gap:0;margin:14px 0 0;
  border-top:1px solid var(--bm-rule);border-bottom:1px solid var(--bm-rule);
  font-size:11px;letter-spacing:0.06em;color:var(--bm-text-soft)}
.sec-line span{padding:6px 12px;border-right:1px solid var(--bm-rule-soft);text-transform:uppercase}
.sec-line span:first-child{background:var(--bm-bg-2);color:var(--bm-accent);font-weight:700}
.sec-line span::before{content:'[ ';opacity:.45}
.sec-line span::after{content:' ]';opacity:.45}
.breaking{margin:14px 0 0;background:var(--bm-red);color:#0c0a06;padding:6px 12px;
  font-size:11px;font-weight:800;letter-spacing:0.5em;text-transform:uppercase;text-align:center;
  border:1px solid #d83a55}
.grid{display:grid;grid-template-columns:minmax(0,2.0fr) minmax(280px,1fr);gap:16px;margin-top:14px}
.panel{border:1px solid var(--bm-rule);background:var(--bm-bg-panel);position:relative;
  box-shadow:inset 0 0 0 1px rgba(251,133,0,0.04)}
.panel-head{background:linear-gradient(180deg,#1a1a26,#10101c);color:var(--bm-accent);
  padding:5px 10px;font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;
  border-bottom:1px solid var(--bm-rule);font-weight:700;
  display:flex;justify-content:space-between;align-items:center}
.panel-head .go{color:var(--bm-cyan);font-weight:700}
.panel-body{padding:14px 16px}
.desk{display:inline-block;background:#1a1408;color:var(--bm-accent);padding:3px 8px;font-size:10.5px;
  letter-spacing:0.18em;text-transform:uppercase;font-weight:700;
  border:1px solid var(--bm-accent);margin-bottom:14px}
.desk::before{content:'> '}
h1{margin:0 0 12px;font-size:clamp(20px,2.6vw,28px);line-height:1.2;font-weight:700;
  color:var(--bm-text);letter-spacing:0.005em;font-family:inherit}
h1::before{content:'> ';color:var(--bm-accent)}
.sub{margin:0 0 12px;font-size:14px;line-height:1.55;color:var(--bm-text-soft);max-width:62ch}
.byline{margin:0 0 14px;font-size:11px;color:var(--bm-text-faint);letter-spacing:0.06em}
.byline em{font-style:normal;color:var(--bm-cyan)}
.stories{margin-top:6px;border-top:1px dashed var(--bm-rule)}
.stories h3{margin:14px 0 10px;font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--bm-accent);font-weight:700}
.stories h3::before{content:'NEWS> ';color:var(--bm-text-faint)}
.stories ul{list-style:none;margin:0;padding:0}
.stories li{padding:6px 0;border-bottom:1px dashed var(--bm-rule-soft);font-size:13px;line-height:1.45;color:var(--bm-text);display:flex;gap:10px;align-items:baseline}
.stories li::before{content:attr(data-stamp);flex-shrink:0;color:var(--bm-text-faint);font-size:11px;
  font-variant-numeric:tabular-nums;letter-spacing:0.02em;width:50px}
.aside{display:flex;flex-direction:column;gap:14px}
.quotes{font-size:12.5px;line-height:1.95;color:var(--bm-text)}
.q-row{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;
  padding:1px 4px;border-bottom:1px dashed var(--bm-rule-soft)}
.q-row:last-child{border-bottom:0}
.q-row[data-delta="up"]   .q-val{color:var(--bm-green)}
.q-row[data-delta="down"] .q-val{color:var(--bm-red)}
.q-row[data-delta="up"]   .q-spark{color:var(--bm-green)}
.q-row[data-delta="down"] .q-spark{color:var(--bm-red)}
.q-label{color:var(--bm-cyan);letter-spacing:0.04em}
.q-spark{font-size:11px;color:var(--bm-text-faint);letter-spacing:-1px}
.q-val{font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
.q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
.q-meta{padding:6px 10px;font-size:10px;color:var(--bm-text-faint);letter-spacing:0.12em;text-transform:uppercase;border-top:1px solid var(--bm-rule-soft)}
.q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-accent);color:var(--bm-accent);font-weight:700;letter-spacing:0.18em}
.hint{margin-top:6px;font-size:10px;color:var(--bm-text-faint);letter-spacing:0.12em;text-transform:uppercase;text-align:center}
#error{color:var(--bm-red);font-size:11px;min-height:16px;margin-top:8px;text-align:center;letter-spacing:0.12em;text-transform:uppercase;font-weight:700}
@media(max-width:720px){.grid{grid-template-columns:1fr}}
"""


def render(ctx: dict[str, Any]) -> str:
    raw_quotes = ctx.get('quotes', [])
    rows: list[str] = []
    for q in raw_quotes:
        label = str(q.get('label', ''))[:8]
        value = str(q.get('value', ''))
        if value.startswith('-'):
            sign, glyph = 'down', '▼'
        elif value.startswith('+'):
            sign, glyph = 'up', '▲'
        else:
            sign, glyph = 'flat', '·'
        spark = random.choice(SPARKS)
        rows.append(
            f'<div class="q-row" data-delta="{sign}">'
            f'<span class="q-label">{label}</span>'
            f'<span class="q-spark">{spark}</span>'
            f'<span class="q-val"><span class="q-glyph">{glyph}</span>{value}</span>'
            f'</div>'
        )
    quotes_html = ''.join(rows) or ctx['quotes_html']

    src_label = ctx['src_label']
    src_color = 'var(--bm-green)' if src_label == 'LIVE' else 'var(--bm-red)'
    q_meta = f'<span class="q-badge" style="color:{src_color};">{src_label}</span>'

    now = datetime.now(tz=UTC).astimezone()
    session = now.strftime('%H:%M:%S JST')
    story_times = ['08:14', '08:42', '09:03', '09:27', '09:51', '10:16']

    # Re-render stories with timestamps (the orchestrator passed them as <li>X</li>;
    # decompose to inject data-stamp).
    stories_raw = ctx.get('stories_raw', [])
    if stories_raw:
        stories_html = ''.join(
            f'<li data-stamp="{story_times[i % len(story_times)]}">{s}</li>'
            for i, s in enumerate(stories_raw)
        )
    else:
        stories_html = ctx['stories_html']

    return f'''<style>{CSS}</style>
<div class="fnbar">
  <span><b>F1</b>HELP</span>
  <span><b>F2</b>EQTY</span>
  <span><b>F3</b>CMDTY</span>
  <span><b>F4</b>CRNCY</span>
  <span><b>F5</b>FI</span>
  <span><b>F6</b>NEWS</span>
  <span><b>F7</b>PORT</span>
  <span class="fn-status">SESSION {session} &middot; UID 0x4F</span>
</div>
<div class="wrap">
  <div class="eyebrow">
    <span><b>TERMINAL</b> v3.4.1</span>
    <span>UPLINK: STABLE &middot; LATENCY 12ms &middot; QUOTES: <b>LIVE</b></span>
    <span>{session}</span>
  </div>
  <header class="masthead">
    <div class="brand">{ctx["brand"]}</div>
    <div class="mast-meta">{ctx["desk_label"]} &middot; {str(ctx["byline"]).upper()}</div>
  </header>
  {ctx["auth_bar"]}
  <nav class="sec-line">{ctx["sections_html"]}</nav>
  {ctx["breaking_html"]}
  <div class="grid">
    <section class="panel">
      <div class="panel-head"><span>HEADLINE FEED</span><span class="go">&lt;GO&gt;</span></div>
      <div class="panel-body">
        <span class="desk">{ctx["desk_label"]}</span>
        <h1>{ctx["headline"]}</h1>
        <p class="sub">{ctx["subhead"]}</p>
        <div class="byline">FILED BY <em>{str(ctx["byline"]).upper()}</em></div>
        <div class="stories">
          <h3>Top Stories &middot; Watchlist Feed</h3>
          <ul>{stories_html}</ul>
        </div>
      </div>
    </section>
    <aside class="aside">
      <div class="panel">
        <div class="panel-head"><span>Watchlist</span><span class="go">&lt;GO&gt;</span></div>
        <div class="panel-body">
          <div class="quotes">{quotes_html}</div>
          <div class="q-meta">{q_meta}</div>
          {ctx["error_html"]}
        </div>
      </div>
      <div class="panel">
        <div class="panel-body" style="padding:10px 12px">
          <div class="hint">Press Esc to return</div>
        </div>
      </div>
    </aside>
  </div>
</div>'''
