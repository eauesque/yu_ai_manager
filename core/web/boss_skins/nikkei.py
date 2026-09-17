"""Boss-mode skin: Nikkei-style Japanese broadsheet."""

from __future__ import annotations

import random
from datetime import UTC, datetime
from typing import Any

KANJI_NUM = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九']
WEEKDAYS_JP = ['月', '火', '水', '木', '金', '土', '日']
ISSUE_BRACKET_NUMS = ['四八、二〇五', '四八、二一二', '四八、二三六', '四八、二九七', '四九、〇一二']


def _to_kanji(n: int) -> str:
    if n == 0:
        return KANJI_NUM[0]
    if n <= 10:
        return '十' if n == 10 else KANJI_NUM[n]
    if n < 20:
        return '十' + KANJI_NUM[n - 10]
    if n < 100:
        tens = n // 10
        ones = n % 10
        return KANJI_NUM[tens] + '十' + (KANJI_NUM[ones] if ones else '')
    return str(n)


def _build_jp_date(d: datetime) -> str:
    reiwa = d.year - 2018
    month = _to_kanji(d.month)
    day = _to_kanji(d.day)
    # Python's weekday(): Mon=0..Sun=6
    wk = WEEKDAYS_JP[d.weekday()]
    return f'令和{_to_kanji(reiwa)}年{month}月{day}日　{wk}曜日'


CSS = """
:root{
  --bm-paper:#f5efe2;--bm-paper-2:#ece4d2;
  --bm-ink:#15110c;--bm-ink-soft:#3a322a;--bm-ink-faint:#73685a;
  --bm-rule:#a59883;--bm-rule-soft:#d2c8b4;
  --bm-accent:#a52a2a;--bm-accent-deep:#7a1c1c;
  --bm-green:#1a4d1a;--bm-red:#8a1a1a;
}
*{box-sizing:border-box}
body{margin:0;background:var(--bm-paper);color:var(--bm-ink);
  font-family:'Yu Mincho','YuMincho','Hiragino Mincho ProN','Hiragino Mincho Pro','MS PMincho','Noto Serif JP',serif;
  font-feature-settings:"palt" 1,"pkna" 1;
  min-height:100vh;overflow:auto;
  background-image:
    repeating-linear-gradient(0deg,rgba(60,30,10,0.014) 0 1px,transparent 1px 4px),
    radial-gradient(at 20% 0%,rgba(165,42,42,0.04),transparent 50%);
  animation:bm-fade 540ms ease-out both}
@keyframes bm-fade{from{opacity:0;transform:translateY(4px);filter:blur(2px)}to{opacity:1;transform:none;filter:none}}
.wrap{max-width:1180px;margin:0 auto;padding:18px 32px 50px}
.eyebrow{display:flex;justify-content:space-between;align-items:center;
  font-size:10.5px;letter-spacing:0.18em;color:var(--bm-ink-faint);padding-bottom:8px}
.eyebrow b{color:var(--bm-accent);font-weight:700}
.masthead{display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px;
  padding:14px 0 8px;border-top:3px solid var(--bm-accent);border-bottom:1px solid var(--bm-accent);position:relative}
.masthead::after{content:'';position:absolute;left:0;right:0;bottom:-5px;height:1px;background:var(--bm-accent)}
.mark{width:64px;height:64px;display:grid;place-items:center;
  background:var(--bm-accent);color:var(--bm-paper);
  font-size:34px;font-weight:900;line-height:1;
  font-family:'Yu Mincho','Hiragino Mincho ProN',serif;
  box-shadow:inset 0 0 0 2px rgba(255,255,255,0.18),0 1px 0 rgba(0,0,0,0.15)}
.brand-wrap{text-align:left}
.brand{font-family:'Yu Mincho','Hiragino Mincho ProN','MS PMincho',serif;
  font-weight:900;font-size:clamp(34px,5.4vw,58px);letter-spacing:0.04em;line-height:1;
  margin:0;color:var(--bm-ink)}
.tagline{margin-top:6px;font-size:12px;color:var(--bm-ink-faint);letter-spacing:0.12em}
.issue{text-align:right;font-size:11px;color:var(--bm-ink-soft);letter-spacing:0.12em;line-height:1.5}
.issue b{color:var(--bm-accent);font-weight:700}
.dateline{display:flex;justify-content:space-between;align-items:center;
  margin-top:14px;padding:6px 0;
  border-top:2px solid var(--bm-ink);border-bottom:1px solid var(--bm-ink);
  font-size:11px;letter-spacing:0.18em;color:var(--bm-ink-soft)}
.dateline-mid{color:var(--bm-ink);font-weight:700;letter-spacing:0.22em}
.auth-bar{display:flex;align-items:center;justify-content:center;gap:8px;
  margin:14px 0 8px;padding:10px 12px;border:1px solid var(--bm-rule);background:var(--bm-paper-2)}
.auth-bar .auth-label{font-size:11px;letter-spacing:0.2em;color:var(--bm-accent);font-weight:700}
.auth-bar input[type=password],.auth-bar input[type=text]{
  font-size:14px;padding:7px 10px;border:1px solid var(--bm-ink);background:var(--bm-paper);width:140px;
  letter-spacing:3px;text-align:center;font-family:'JetBrains Mono','SF Mono',Menlo,monospace}
.auth-bar input:focus{outline:2px solid var(--bm-accent);outline-offset:1px}
.auth-bar button{padding:8px 14px;border:1px solid var(--bm-ink);background:var(--bm-paper);
  cursor:pointer;font:inherit;font-size:12px;letter-spacing:0.28em;
  color:var(--bm-ink);font-weight:700;transition:background 160ms ease,color 160ms ease}
.auth-bar button:hover{background:var(--bm-ink);color:var(--bm-paper)}
.auth-bar .eye{padding:7px 9px;letter-spacing:0;font-size:13px}
.breaking{margin:14px 0 0;background:var(--bm-accent);color:var(--bm-paper);padding:7px 12px;
  font-size:11px;font-weight:700;letter-spacing:0.5em;text-align:center}
.breaking::before{content:'【速報】';margin-right:8px;letter-spacing:0.16em}
.sec-line{display:flex;justify-content:flex-start;flex-wrap:wrap;gap:0 14px;
  margin:14px 0 16px;padding:8px 0;border-bottom:1px solid var(--bm-rule);
  font-size:12px;letter-spacing:0.06em;color:var(--bm-ink);font-weight:700}
.sec-line span{display:inline-flex;align-items:center}
.sec-line span::before{content:'【';color:var(--bm-accent);margin-right:1px}
.sec-line span::after{content:'】';color:var(--bm-accent);margin-left:1px}
.grid{display:grid;grid-template-columns:minmax(0,2.0fr) 1px minmax(280px,1fr);gap:0 22px}
.rule-v{background:var(--bm-rule);margin:0}
.desk{display:inline-block;background:var(--bm-accent);color:var(--bm-paper);
  font-size:12px;letter-spacing:0.18em;padding:3px 10px;font-weight:700;margin-bottom:14px}
h1{font-family:'Yu Mincho','Hiragino Mincho ProN','MS PMincho',serif;
  margin:0 0 12px;font-size:clamp(30px,4.0vw,44px);line-height:1.18;font-weight:900;
  letter-spacing:0.01em;color:var(--bm-ink)}
h1::before{content:'';display:block;width:34px;height:3px;background:var(--bm-accent);margin:0 0 12px}
.sub{margin:0 0 14px;line-height:1.65;font-size:16px;color:var(--bm-ink-soft);max-width:62ch;
  text-align:justify;text-justify:inter-character}
.sub::first-letter{font-weight:900;float:left;font-size:3.4em;line-height:.9;padding:6px 8px 0 0;color:var(--bm-accent)}
.byline{margin:0 0 18px;font-size:11px;color:var(--bm-ink-faint);letter-spacing:0.18em}
.byline em{font-style:normal;color:var(--bm-ink)}
.stories{margin-top:8px;padding-top:14px;border-top:2px solid var(--bm-ink);position:relative}
.stories::before{content:'';position:absolute;left:0;right:0;top:3px;height:1px;background:var(--bm-ink)}
.stories h3{margin:0 0 12px;font-size:13px;letter-spacing:0.18em;color:var(--bm-ink);font-weight:700}
.stories h3::before{content:'■';color:var(--bm-accent);margin-right:8px}
.stories ul{list-style:none;margin:0;padding:0}
.stories li{padding:8px 0;border-bottom:1px solid var(--bm-rule-soft);font-size:14.5px;line-height:1.55;
  color:var(--bm-ink-soft);position:relative;padding-left:22px}
.stories li::before{content:'「';position:absolute;left:0;top:5px;color:var(--bm-accent);font-weight:700;font-size:14px}
.stories li::after{content:'」';color:var(--bm-accent);font-weight:700;margin-left:4px}
.sidebar{padding-left:4px;height:max-content}
.sidebar-title{font-family:'Yu Mincho','Hiragino Mincho ProN',serif;
  font-size:22px;font-weight:900;letter-spacing:0.08em;margin:0 0 4px;color:var(--bm-ink);text-align:center}
.sidebar-title::before{content:'■ ';color:var(--bm-accent);font-size:0.7em}
.sidebar-sub{font-size:10.5px;letter-spacing:0.22em;color:var(--bm-ink-faint);text-align:center;
  margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--bm-rule)}
.quotes{font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,'Yu Mincho',serif;
  font-size:12.5px;line-height:2;color:var(--bm-ink);font-feature-settings:"tnum" 1;
  background:var(--bm-paper-2);padding:8px 12px;border:1px solid var(--bm-rule-soft)}
.q-row{display:flex;justify-content:space-between;gap:12px}
.q-row[data-delta="up"]   .q-val{color:var(--bm-green)}
.q-row[data-delta="down"] .q-val{color:var(--bm-red)}
.q-label{letter-spacing:0.04em}
.q-val{font-weight:700;font-variant-numeric:tabular-nums}
.q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
.q-meta{margin-top:10px;padding-top:8px;font-size:10px;color:var(--bm-ink-faint);letter-spacing:0.18em;text-align:center;border-top:1px solid var(--bm-rule-soft)}
.q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-rule);font-weight:700;letter-spacing:0.22em}
.hint{margin-top:8px;font-size:10.5px;color:var(--bm-ink-faint);letter-spacing:0.16em;text-align:center}
#error{color:var(--bm-accent);font-size:11px;min-height:16px;margin-top:8px;text-align:center;letter-spacing:0.16em;font-weight:700}
@media(max-width:720px){
  .grid{grid-template-columns:1fr}.rule-v{display:none}.sidebar{margin-top:22px}
  .masthead{grid-template-columns:1fr}.mark{justify-self:center}.issue{display:none}
  .auth-bar{flex-wrap:wrap}
}
"""


def render(ctx: dict[str, Any]) -> str:
    quotes_html = ctx['quotes_html']
    src_label = ctx['src_label']
    src_color = 'var(--bm-green)' if src_label == 'LIVE' else 'var(--bm-red)'
    q_meta = f'<span class="q-badge" style="color:{src_color};">{src_label}</span>'

    date_jp = _build_jp_date(datetime.now(tz=UTC).astimezone())
    issue_no = random.choice(ISSUE_BRACKET_NUMS)

    return f'''<style>{CSS}</style>
<div class="wrap">
  <div class="eyebrow">
    <span><b>朝刊</b> ・ 全国版</span>
    <span>定価 ¥350（本体 ¥318）</span>
  </div>
  <header class="masthead">
    <div class="mark">日</div>
    <div class="brand-wrap">
      <h1 class="brand">{ctx["brand"]}</h1>
      <div class="tagline">経済の真実を読み解く ・ 創刊 一八八八年</div>
    </div>
    <div class="issue">
      <div>第 <b>{issue_no}</b> 號</div>
      <div>本社 ／ 東京・大手町</div>
    </div>
  </header>
  <div class="dateline">
    <span>{ctx["desk_label"]}</span>
    <span class="dateline-mid">{date_jp}</span>
    <span>第何版</span>
  </div>
  {ctx["auth_bar"]}
  {ctx["breaking_html"]}
  <nav class="sec-line">{ctx["sections_html"]}</nav>
  <div class="grid">
    <main>
      <span class="desk">{ctx["desk_label"]}</span>
      <h1>{ctx["headline"]}</h1>
      <p class="sub">{ctx["subhead"]}</p>
      <div class="byline">本紙 <em>{ctx["byline"]}</em></div>
      <section class="stories">
        <h3>きょうの主要記事 ・ Top Stories</h3>
        <ul>{ctx["stories_html"]}</ul>
      </section>
    </main>
    <div class="rule-v"></div>
    <aside class="sidebar">
      <div class="sidebar-title">Watchlist</div>
      <div class="sidebar-sub">市況 ・ 大引け速報</div>
      <div class="quotes">{quotes_html}</div>
      <div class="q-meta">{q_meta}</div>
      {ctx["error_html"]}
      <div class="hint">Press Esc to return</div>
    </aside>
  </div>
</div>'''
