/**
 * boss-lock / skins / bloomberg — Terminal-style market feed.
 *
 * Black background, monospace, amber/orange accents, function-key bar,
 * ASCII sparklines, scrolling ticker tape. Looks like a 1990s trading desk.
 */

import type { BossModeEdition } from '../edition-data';
import { renderStaticQuoteRows } from './quote-rows';
import {
  type EscFn, type TrFn, type Skin, pick,
} from './types';

const CSS = `
#bossModeOverlay {
  --bm-bg:#0a0a14; --bm-bg-2:#11111c; --bm-bg-panel:#0e0e18;
  --bm-text:#f3e6c7; --bm-text-soft:#c9b890; --bm-text-faint:#7a6e50;
  --bm-rule:#3a3024; --bm-rule-soft:#26201a;
  --bm-accent:#fb8500; --bm-accent-deep:#cc6900;
  --bm-green:#7dffaf; --bm-red:#ff5572; --bm-cyan:#5ed5ff;
  position:fixed;inset:0;z-index:9999;
  background:var(--bm-bg);color:var(--bm-text);
  font-family:'JetBrains Mono','Cascadia Mono','Consolas','SF Mono',Menlo,monospace;
  font-feature-settings:"calt" 0,"liga" 0,"tnum" 1,"zero" 1;
  overflow:auto;
  background-image:
    repeating-linear-gradient(0deg,rgba(255,200,80,0.018) 0 1px,transparent 1px 3px),
    radial-gradient(at 50% -10%,rgba(251,133,0,0.07),transparent 60%);
  animation:bm-fade 380ms ease-out both;
}
@keyframes bm-fade{from{opacity:0;filter:blur(2px)}to{opacity:1;filter:none}}
#bossModeOverlay::before{
  content:'';position:fixed;inset:0;pointer-events:none;
  background:repeating-linear-gradient(0deg,rgba(255,255,255,0.014) 0 2px,transparent 2px 4px);
  mix-blend-mode:overlay;
}
#bossModeOverlay .bm-fnbar{
  display:flex;gap:0;border-bottom:1px solid var(--bm-rule);
  background:linear-gradient(180deg,var(--bm-bg-2),var(--bm-bg));
  font-size:11px;line-height:1;letter-spacing:0.04em;
}
#bossModeOverlay .bm-fnbar span{padding:8px 11px;color:var(--bm-text-soft);border-right:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-fnbar span b{color:var(--bm-accent);font-weight:700;margin-right:6px}
#bossModeOverlay .bm-fnbar .bm-fn-status{margin-left:auto;color:var(--bm-text-faint);border-right:0;border-left:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-wrap{max-width:1280px;margin:0 auto;padding:14px 22px 28px}
#bossModeOverlay .bm-eyebrow{display:flex;justify-content:space-between;align-items:center;
  font-size:10.5px;color:var(--bm-text-faint);padding:0 0 10px;letter-spacing:0.06em}
#bossModeOverlay .bm-eyebrow b{color:var(--bm-accent)}
#bossModeOverlay .bm-masthead{
  background:var(--bm-accent);color:#0c0a06;
  padding:8px 14px;display:flex;justify-content:space-between;align-items:center;
  border:1px solid var(--bm-accent-deep);
  box-shadow:inset 0 -1px 0 rgba(0,0,0,0.3);
}
#bossModeOverlay .bm-brand{font-size:18px;font-weight:800;letter-spacing:0.04em;text-transform:uppercase}
#bossModeOverlay .bm-brand::before{content:'< ';opacity:.55}
#bossModeOverlay .bm-brand::after{content:' >';opacity:.55}
#bossModeOverlay .bm-mast-meta{font-size:11px;letter-spacing:0.06em;font-weight:700}
#bossModeOverlay .bm-section-line{display:flex;flex-wrap:wrap;gap:0;margin:14px 0 0;
  border-top:1px solid var(--bm-rule);border-bottom:1px solid var(--bm-rule);
  font-size:11px;letter-spacing:0.06em;color:var(--bm-text-soft)}
#bossModeOverlay .bm-section-line span{padding:6px 12px;border-right:1px solid var(--bm-rule-soft);text-transform:uppercase}
#bossModeOverlay .bm-section-line span:first-child{background:var(--bm-bg-2);color:var(--bm-accent);font-weight:700}
#bossModeOverlay .bm-section-line span::before{content:'[ ';opacity:.45}
#bossModeOverlay .bm-section-line span::after{content:' ]';opacity:.45}
#bossModeOverlay .bm-breaking{margin:14px 0 0;background:var(--bm-red);color:#0c0a06;padding:6px 12px;
  font-size:11px;font-weight:800;letter-spacing:0.5em;text-transform:uppercase;text-align:center;
  border:1px solid #d83a55}
#bossModeOverlay .bm-grid{display:grid;grid-template-columns:minmax(0,2.0fr) minmax(280px,1fr);gap:16px;margin-top:14px}
#bossModeOverlay .bm-panel{
  border:1px solid var(--bm-rule);background:var(--bm-bg-panel);position:relative;
  box-shadow:inset 0 0 0 1px rgba(251,133,0,0.04);
}
#bossModeOverlay .bm-panel-head{
  background:linear-gradient(180deg,#1a1a26,#10101c);color:var(--bm-accent);
  padding:5px 10px;font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;
  border-bottom:1px solid var(--bm-rule);font-weight:700;
  display:flex;justify-content:space-between;align-items:center}
#bossModeOverlay .bm-panel-head .bm-go{color:var(--bm-cyan);font-weight:700}
#bossModeOverlay .bm-panel-body{padding:14px 16px}
#bossModeOverlay .bm-desk{display:inline-block;
  background:#1a1408;color:var(--bm-accent);padding:3px 8px;font-size:10.5px;
  letter-spacing:0.18em;text-transform:uppercase;font-weight:700;
  border:1px solid var(--bm-accent);margin-bottom:14px}
#bossModeOverlay .bm-desk::before{content:'> '}
#bossModeOverlay h1.bm-headline{
  margin:0 0 12px;font-size:clamp(20px,2.6vw,28px);line-height:1.2;font-weight:700;
  color:var(--bm-text);letter-spacing:0.005em;font-family:inherit;
  text-transform:none;
}
#bossModeOverlay h1.bm-headline::before{content:'> ';color:var(--bm-accent)}
#bossModeOverlay .bm-sub{margin:0 0 12px;font-size:14px;line-height:1.55;color:var(--bm-text-soft);max-width:62ch;font-style:normal}
#bossModeOverlay .bm-byline{margin:0 0 14px;font-size:11px;color:var(--bm-text-faint);letter-spacing:0.06em}
#bossModeOverlay .bm-byline em{font-style:normal;color:var(--bm-cyan)}
#bossModeOverlay .bm-stories{margin-top:6px;border-top:1px dashed var(--bm-rule)}
#bossModeOverlay .bm-stories h3{margin:14px 0 10px;font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--bm-accent);font-weight:700}
#bossModeOverlay .bm-stories h3::before{content:'NEWS> ';color:var(--bm-text-faint)}
#bossModeOverlay .bm-stories ul{list-style:none;margin:0;padding:0}
#bossModeOverlay .bm-stories li{padding:6px 0;border-bottom:1px dashed var(--bm-rule-soft);font-size:13px;
  line-height:1.45;color:var(--bm-text);display:flex;gap:10px;align-items:baseline}
#bossModeOverlay .bm-stories li::before{
  content:attr(data-stamp);
  flex-shrink:0;color:var(--bm-text-faint);font-size:11px;
  font-variant-numeric:tabular-nums;letter-spacing:0.02em;
  width:50px;
}
#bossModeOverlay .bm-aside{display:flex;flex-direction:column;gap:14px}
#bossModeOverlay .bm-quotes{font-size:12.5px;line-height:1.95;color:var(--bm-text);font-feature-settings:"tnum" 1,"zero" 1}
#bossModeOverlay .bm-q-row{display:grid;grid-template-columns:auto 1fr auto;gap:12px;align-items:center;
  padding:1px 4px;border-bottom:1px dashed var(--bm-rule-soft)}
#bossModeOverlay .bm-q-row:last-child{border-bottom:0}
#bossModeOverlay .bm-q-row[data-delta="up"]   .bm-q-val{color:var(--bm-green)}
#bossModeOverlay .bm-q-row[data-delta="down"] .bm-q-val{color:var(--bm-red)}
#bossModeOverlay .bm-q-row[data-delta="up"]   .bm-q-spark{color:var(--bm-green)}
#bossModeOverlay .bm-q-row[data-delta="down"] .bm-q-spark{color:var(--bm-red)}
#bossModeOverlay .bm-q-label{color:var(--bm-cyan);letter-spacing:0.04em}
#bossModeOverlay .bm-q-spark{font-size:11px;color:var(--bm-text-faint);letter-spacing:-1px}
#bossModeOverlay .bm-q-val{font-weight:700;font-variant-numeric:tabular-nums;text-align:right}
#bossModeOverlay .bm-q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
#bossModeOverlay .bm-q-meta{padding:6px 10px;font-size:10px;color:var(--bm-text-faint);letter-spacing:0.12em;text-transform:uppercase;border-top:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-accent);color:var(--bm-accent);font-weight:700;letter-spacing:0.18em}
#bossModeOverlay .bm-back{margin-top:6px;width:100%;padding:8px;
  border:1px solid var(--bm-accent);background:transparent;
  font-family:inherit;font-size:11px;letter-spacing:0.18em;text-transform:uppercase;
  color:var(--bm-accent);cursor:pointer;font-weight:700;
  transition:background 160ms ease,color 160ms ease}
#bossModeOverlay .bm-back:hover{background:var(--bm-accent);color:#0c0a06}
#bossModeOverlay .bm-hint{margin-top:6px;font-size:10px;color:var(--bm-text-faint);letter-spacing:0.12em;text-transform:uppercase;text-align:center}
#bossModeOverlay .bm-ticker{
  position:fixed;left:0;right:0;bottom:0;height:28px;
  background:#000007;border-top:1px solid var(--bm-rule);
  overflow:hidden;color:var(--bm-text-soft);font-size:12px;font-feature-settings:"tnum" 1
}
#bossModeOverlay .bm-ticker-inner{display:inline-block;padding:6px 16px;white-space:nowrap;animation:bm-tick 60s linear infinite}
@keyframes bm-tick{from{transform:translateX(0)}to{transform:translateX(-50%)}}
#bossModeOverlay .bm-ticker .bm-up{color:var(--bm-green)}
#bossModeOverlay .bm-ticker .bm-down{color:var(--bm-red)}
@media(max-width:720px){
  #bossModeOverlay .bm-grid{grid-template-columns:1fr}
}
`;

const SPARKS = ['▁▂▃▅▇▆▄', '▇▅▃▂▁▂▃', '▃▄▅▆▇▆▅', '▁▁▂▃▅▆▇', '▇▆▄▃▂▁▁', '▂▃▄▅▄▃▂'];

function buildSparkline(): string {
  return pick(SPARKS);
}

function quoteRowWithSpark(label: string, value: string, escFn: EscFn): string {
  const sign = value.startsWith('-') ? 'down' : (value.startsWith('+') ? 'up' : 'flat');
  const glyph = sign === 'down' ? '▼' : (sign === 'up' ? '▲' : '·');
  return `<div class="bm-q-row" data-delta="${sign}">`
    + `<span class="bm-q-label">${escFn(label)}</span>`
    + `<span class="bm-q-spark">${buildSparkline()}</span>`
    + `<span class="bm-q-val"><span class="bm-q-glyph">${glyph}</span>${escFn(value)}</span>`
    + `</div>`;
}

function quotesWithSparks(quotes: string[], escFn: EscFn): string {
  return (quotes || []).map((q) => {
    const s = String(q);
    const idx = s.indexOf('  ');
    const label = idx >= 0 ? s.slice(0, idx).trim() : s;
    const value = idx >= 0 ? s.slice(idx).trim() : '';
    return quoteRowWithSpark(label, value, escFn);
  }).join('');
}

function pad2(n: number): string { return String(n).padStart(2, '0'); }

function buildTickerContent(quotes: string[], escFn: EscFn): string {
  const dup = [...quotes, ...quotes, ...quotes, ...quotes];
  return dup.map((q) => {
    const s = String(q);
    const idx = s.indexOf('  ');
    const label = idx >= 0 ? s.slice(0, idx).trim() : s;
    const value = idx >= 0 ? s.slice(idx).trim() : '';
    const cls = value.startsWith('-') ? 'bm-down' : 'bm-up';
    return `<span style="margin:0 16px"><b>${escFn(label)}</b> <span class="${cls}">${escFn(value)}</span></span>`;
  }).join(' · ');
}

function build(ed: BossModeEdition, trFn: TrFn, escFn: EscFn): string {
  const now = new Date();
  const hh = pad2(now.getHours());
  const mm = pad2(now.getMinutes());

  // Stories with timestamp prefix
  const storyTimes = ['08:14', '08:42', '09:03', '09:27', '09:51', '10:16'];
  const topStories = (ed.stories || [trFn('boss_mode.story1'), trFn('boss_mode.story2'), trFn('boss_mode.story3'), trFn('boss_mode.story4')])
    .map((s, i) => `<li data-stamp="${escFn(storyTimes[i % storyTimes.length])}">${escFn(s)}</li>`).join('');

  const sectionLine = (ed.sectionLine || []).map((s) => `<span>${escFn(s)}</span>`).join('');
  const quotesHtml = quotesWithSparks(ed.quotes || [], escFn);
  const tickerHtml = buildTickerContent(ed.quotes || [], escFn);
  const _unused = renderStaticQuoteRows; void _unused; // keep import alive (skin overrides)

  const breaking = ed.showBreaking ? `<div class="bm-breaking">${escFn(ed.breakingText || 'Breaking')}</div>` : '';
  const session = `${hh}:${mm}:${pad2(now.getSeconds())} JST`;

  return `
    <style>${CSS}</style>
    <div class="bm-fnbar">
      <span><b>F1</b>HELP</span>
      <span><b>F2</b>EQTY</span>
      <span><b>F3</b>CMDTY</span>
      <span><b>F4</b>CRNCY</span>
      <span><b>F5</b>FI</span>
      <span><b>F6</b>NEWS</span>
      <span><b>F7</b>PORT</span>
      <span class="bm-fn-status">SESSION ${escFn(session)} · UID 0x4F</span>
    </div>
    <div class="bm-wrap">
      <div class="bm-eyebrow">
        <span><b>TERMINAL</b> v3.4.1</span>
        <span>UPLINK: STABLE · LATENCY 12ms · QUOTES: <b>LIVE</b></span>
        <span><span id="bossModeTimestamp">${escFn(session)}</span></span>
      </div>
      <header class="bm-masthead">
        <div class="bm-brand">${escFn(ed.brand || trFn('boss_mode.brand'))}</div>
        <div class="bm-mast-meta">${escFn(ed.deskLabel)} · ${escFn((ed.byline || 'By Desk').toUpperCase())}</div>
      </header>
      <nav class="bm-section-line">${sectionLine}</nav>
      ${breaking}
      <div class="bm-grid">
        <section class="bm-panel">
          <div class="bm-panel-head"><span>HEADLINE FEED</span><span class="bm-go">&lt;GO&gt;</span></div>
          <div class="bm-panel-body">
            <span class="bm-desk">${escFn(ed.deskLabel)}</span>
            <h1 class="bm-headline">${escFn(ed.headline || trFn('boss_mode.headline'))}</h1>
            <p class="bm-sub">${escFn(ed.subhead || trFn('boss_mode.subhead'))}</p>
            <div class="bm-byline">FILED BY <em>${escFn((ed.byline || 'DESK').toUpperCase())}</em></div>
            <div class="bm-stories">
              <h3>${trFn('boss_mode.top_stories')}</h3>
              <ul>${topStories}</ul>
            </div>
          </div>
        </section>
        <aside class="bm-aside">
          <div class="bm-panel">
            <div class="bm-panel-head"><span>${trFn('boss_mode.watchlist')}</span><span class="bm-go">&lt;GO&gt;</span></div>
            <div class="bm-panel-body">
              <div id="bossModeQuoteList" class="bm-quotes">${quotesHtml}</div>
              <div id="bossModeQuoteMeta" class="bm-q-meta"><span class="bm-q-badge">SAMPLE</span></div>
            </div>
          </div>
          <div class="bm-panel">
            <div class="bm-panel-body" style="padding:10px 12px">
              <button type="button" class="bm-back" data-action="bossLockApi.hideBossMode">${trFn('boss_mode.back')}</button>
              <div class="bm-hint">${trFn('boss_mode.esc_hint')}</div>
            </div>
          </div>
        </aside>
      </div>
    </div>
    <div class="bm-ticker"><div class="bm-ticker-inner">${tickerHtml} · · · ${tickerHtml}</div></div>
  `;
}

export const bloomberg: Skin = { id: 'bloomberg', build };
