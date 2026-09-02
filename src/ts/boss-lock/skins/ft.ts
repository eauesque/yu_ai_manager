/**
 * boss-lock / skins / ft — Refined FT-pink broadsheet skin.
 *
 * Bodoni masthead, Iowan/Palatino body, double-rule dateline, drop cap,
 * § dingbat stories, ▲▼ delta watchlist on FT salmon paper (#fff1e5).
 */

import type { BossModeEdition } from '../edition-data';
import { renderStaticQuoteRows } from './quote-rows';
import {
  type EscFn, type TrFn, type Skin,
  ROMAN_VOLS, EDITION_TAGS, WEATHER_LINES, PRICES,
  pick, formatDateUS, buildIssueNo,
} from './types';

const CSS = `
#bossModeOverlay {
  --bm-paper:#fff1e5; --bm-paper-deep:#f6e7d8;
  --bm-ink:#1a1410; --bm-ink-soft:#433c35; --bm-ink-faint:#6f665b;
  --bm-rule:#c6b9a6; --bm-rule-soft:#ddd0bd;
  --bm-accent:#b30f0f; --bm-green:#1f3f1f; --bm-red:#7b1e1e;
  position:fixed;inset:0;z-index:9999;
  background:var(--bm-paper);color:var(--bm-ink);
  font-family:'Iowan Old Style','Palatino Linotype',Palatino,P052,'Book Antiqua',Georgia,'Hiragino Mincho ProN','Yu Mincho',serif;
  font-feature-settings:"kern" 1,"liga" 1,"onum" 1;
  overflow:auto;
  background-image:
    radial-gradient(at 12% 18%,rgba(80,40,20,0.04),transparent 38%),
    radial-gradient(at 88% 76%,rgba(80,40,20,0.03),transparent 42%),
    repeating-linear-gradient(0deg,rgba(0,0,0,0.012) 0 1px,transparent 1px 3px);
  animation:bm-fade 540ms ease-out both;
}
@keyframes bm-fade{from{opacity:0;transform:translateY(4px);filter:blur(2px)}to{opacity:1;transform:none;filter:none}}
#bossModeOverlay .bm-wrap{max-width:1180px;margin:0 auto;padding:24px 40px 56px}
#bossModeOverlay .bm-eyebrow{display:flex;justify-content:space-between;align-items:center;
  font-family:'Iowan Old Style',Georgia,serif;
  font-size:10.5px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink-faint);padding-bottom:6px}
#bossModeOverlay .bm-eyebrow strong{color:var(--bm-ink);font-weight:600;letter-spacing:0.36em}
#bossModeOverlay .bm-masthead{text-align:center;padding:4px 0 12px;
  border-top:1px solid var(--bm-ink);border-bottom:3px double var(--bm-ink)}
#bossModeOverlay .bm-brand{
  font-family:'Bodoni 72','Bodoni Moda',Didot,'Didot LT STD','Hoefler Text','Big Caslon',Garamond,'Times New Roman',serif;
  font-weight:800;font-size:clamp(40px,6.4vw,72px);letter-spacing:-0.005em;line-height:1;
  margin:10px 0 6px;color:var(--bm-ink)}
#bossModeOverlay .bm-brand-flank{font-weight:400;opacity:.55;padding:0 18px;font-size:.58em;vertical-align:0.32em;letter-spacing:0}
#bossModeOverlay .bm-tagline{font-style:italic;font-size:13px;color:var(--bm-ink-faint);letter-spacing:0.04em;margin-bottom:4px}
#bossModeOverlay .bm-dateline{display:flex;justify-content:space-between;align-items:center;gap:12px;
  padding:7px 6px;margin-top:8px;
  border-top:1px solid var(--bm-ink);border-bottom:1px solid var(--bm-ink);
  font-family:'Iowan Old Style',Georgia,serif;
  font-size:10.5px;letter-spacing:0.18em;text-transform:uppercase;color:var(--bm-ink-soft)}
#bossModeOverlay .bm-dateline span{white-space:nowrap}
#bossModeOverlay .bm-dateline .bm-dateline-mid{letter-spacing:0.22em;color:var(--bm-ink)}
#bossModeOverlay .bm-breaking{margin:14px 0 4px;background:var(--bm-accent);color:#fff;padding:8px 12px;
  font-size:11px;font-weight:700;letter-spacing:0.5em;text-transform:uppercase;text-align:center;
  box-shadow:0 1px 0 rgba(0,0,0,0.15)}
#bossModeOverlay .bm-section-line{display:flex;justify-content:center;flex-wrap:wrap;gap:4px 14px;
  margin:14px 0 18px;padding-bottom:12px;border-bottom:1px solid var(--bm-rule);
  font-family:'Iowan Old Style',Georgia,serif;
  font-size:10.5px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink-soft)}
#bossModeOverlay .bm-section-line span{display:inline-flex;align-items:center}
#bossModeOverlay .bm-section-line span+span::before{content:'◆';opacity:.4;margin-right:14px;font-size:7px;letter-spacing:0;transform:translateY(-1px)}
#bossModeOverlay .bm-grid{display:grid;grid-template-columns:minmax(0,2.1fr) 1px minmax(280px,1fr);gap:0 26px}
#bossModeOverlay .bm-rule-v{background:var(--bm-rule);margin:6px 0}
#bossModeOverlay .bm-desk{display:inline-block;font-family:'Iowan Old Style',Georgia,serif;
  font-size:10.5px;letter-spacing:0.36em;text-transform:uppercase;color:var(--bm-accent);font-weight:700;
  margin-bottom:10px;border-top:1px solid var(--bm-accent);border-bottom:1px solid var(--bm-accent);padding:4px 8px 3px}
#bossModeOverlay h1.bm-headline{
  font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text','Big Caslon',Garamond,serif;
  margin:0 0 14px;font-size:clamp(34px,4.2vw,50px);line-height:1.05;font-weight:700;
  letter-spacing:-0.005em;color:var(--bm-ink)}
#bossModeOverlay .bm-sub{margin:0 0 18px;color:var(--bm-ink-soft);line-height:1.55;
  font-size:19px;max-width:56ch;font-style:italic}
#bossModeOverlay .bm-sub::first-letter{
  font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text',Garamond,serif;
  font-style:normal;font-weight:800;float:left;font-size:4.4em;line-height:.85;
  padding:4px 10px 0 0;color:var(--bm-ink)}
#bossModeOverlay .bm-byline{margin:0 0 18px;font-size:11px;color:var(--bm-ink-faint);
  letter-spacing:0.2em;text-transform:uppercase}
#bossModeOverlay .bm-byline em{font-style:normal;color:var(--bm-ink-soft)}
#bossModeOverlay .bm-stories{border-top:3px double var(--bm-rule);padding-top:14px;margin-top:6px}
#bossModeOverlay .bm-stories h3{margin:0 0 10px;font-size:11px;letter-spacing:0.36em;text-transform:uppercase;
  font-family:'Iowan Old Style',Georgia,serif;color:var(--bm-ink);font-weight:700}
#bossModeOverlay .bm-stories ul{list-style:none;margin:0;padding:0}
#bossModeOverlay .bm-stories li{padding:8px 0;border-bottom:1px solid var(--bm-rule-soft);
  font-size:15px;line-height:1.45;color:var(--bm-ink-soft);position:relative;padding-left:22px}
#bossModeOverlay .bm-stories li::before{content:'§';position:absolute;left:0;top:8px;
  font-family:'Bodoni 72','Hoefler Text',Garamond,serif;color:var(--bm-accent);font-weight:700;font-size:14px}
#bossModeOverlay .bm-aside{background:linear-gradient(180deg,var(--bm-paper-deep) 0%,var(--bm-paper) 100%);
  border:1px solid var(--bm-rule);padding:16px 18px;height:max-content;position:relative}
#bossModeOverlay .bm-aside::before{content:'';position:absolute;inset:4px;border:1px solid var(--bm-rule-soft);pointer-events:none}
#bossModeOverlay .bm-aside-title{
  font-family:'Bodoni 72','Bodoni Moda',Didot,'Hoefler Text',Garamond,serif;
  font-size:22px;font-weight:700;letter-spacing:0.02em;margin:0 0 4px;color:var(--bm-ink);text-align:center}
#bossModeOverlay .bm-aside-sub{font-family:'Iowan Old Style',Georgia,serif;
  font-size:9.5px;letter-spacing:0.3em;text-transform:uppercase;color:var(--bm-ink-faint);
  text-align:center;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid var(--bm-rule)}
#bossModeOverlay .bm-quotes{font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;
  font-size:12.5px;line-height:2;color:var(--bm-ink);font-feature-settings:"tnum" 1,"zero" 1}
#bossModeOverlay .bm-q-row{display:flex;justify-content:space-between;gap:12px;padding:0 2px;
  border-bottom:1px dotted var(--bm-rule-soft)}
#bossModeOverlay .bm-q-row:last-child{border-bottom:0}
#bossModeOverlay .bm-q-row[data-delta="up"]   .bm-q-val{color:var(--bm-green)}
#bossModeOverlay .bm-q-row[data-delta="down"] .bm-q-val{color:var(--bm-red)}
#bossModeOverlay .bm-q-label{letter-spacing:0.05em}
#bossModeOverlay .bm-q-val{font-weight:700;font-variant-numeric:tabular-nums}
#bossModeOverlay .bm-q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
#bossModeOverlay .bm-q-meta{margin-top:10px;padding-top:8px;font-size:10px;color:var(--bm-ink-faint);
  letter-spacing:0.18em;text-transform:uppercase;text-align:center;border-top:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-rule);
  font-weight:700;letter-spacing:0.26em;background:var(--bm-paper)}
#bossModeOverlay .bm-back{margin-top:14px;width:100%;padding:10px;
  border:1px solid var(--bm-ink);background:var(--bm-paper);
  font-family:'Iowan Old Style',Georgia,serif;
  font-size:11px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink);
  cursor:pointer;transition:background 160ms ease,color 160ms ease}
#bossModeOverlay .bm-back:hover{background:var(--bm-ink);color:var(--bm-paper)}
#bossModeOverlay .bm-hint{margin-top:8px;font-size:10px;color:var(--bm-ink-faint);
  letter-spacing:0.18em;text-transform:uppercase;text-align:center}
#bossModeOverlay .bm-fold-shadow{pointer-events:none;position:absolute;left:0;right:0;top:38%;height:14px;
  background:linear-gradient(180deg,transparent,rgba(0,0,0,0.05),transparent);filter:blur(0.5px)}
@media(max-width:720px){
  #bossModeOverlay .bm-grid{grid-template-columns:1fr}
  #bossModeOverlay .bm-rule-v{display:none}
  #bossModeOverlay .bm-aside{margin-top:22px}
  #bossModeOverlay .bm-dateline{font-size:9.5px;gap:6px;flex-wrap:wrap;justify-content:center}
}
`;

function build(ed: BossModeEdition, trFn: TrFn, escFn: EscFn): string {
  const topStories = (ed.stories || [trFn('boss_mode.story1'), trFn('boss_mode.story2'), trFn('boss_mode.story3'), trFn('boss_mode.story4')])
    .map((s) => `<li>${escFn(s)}</li>`).join('');
  const sectionLine  = (ed.sectionLine || []).map((s) => `<span>${escFn(s)}</span>`).join('');
  const staticQuotes = renderStaticQuoteRows(ed.quotes || [], escFn);

  const vol     = pick(ROMAN_VOLS);
  const issueNo = buildIssueNo();
  const editTag = pick(EDITION_TAGS);
  const weather = pick(WEATHER_LINES);
  const price   = pick(PRICES);
  const dateStr = formatDateUS(new Date());

  const breaking = ed.showBreaking ? `<div class="bm-breaking">${escFn(ed.breakingText || 'Breaking')}</div>` : '';

  return `
    <style>${CSS}</style>
    <div class="bm-wrap">
      <div class="bm-eyebrow">
        <span>EST. <strong>MCMLXXXVIII</strong></span>
        <span>${escFn(editTag)}</span>
        <span>${escFn(price)}</span>
      </div>
      <header class="bm-masthead">
        <div class="bm-brand">
          <span class="bm-brand-flank">❦</span>${escFn(ed.brand || trFn('boss_mode.brand'))}<span class="bm-brand-flank">❦</span>
        </div>
        <div class="bm-tagline">All the markets, fit to print.</div>
        <div class="bm-dateline">
          <span>Vol. ${escFn(vol)} · No. ${escFn(issueNo)}</span>
          <span class="bm-dateline-mid">${escFn(dateStr)}</span>
          <span>${escFn(weather)}</span>
        </div>
      </header>
      ${breaking}
      <div class="bm-section-line">${sectionLine}</div>
      <div class="bm-grid">
        <main>
          <span class="bm-desk">${escFn(ed.deskLabel)}</span>
          <h1 class="bm-headline">${escFn(ed.headline || trFn('boss_mode.headline'))}</h1>
          <p class="bm-sub">${escFn(ed.subhead || trFn('boss_mode.subhead'))}</p>
          <div class="bm-byline"><em>${escFn(ed.byline || 'By Desk')}</em> · <span id="bossModeTimestamp"></span></div>
          <section class="bm-stories">
            <h3>${trFn('boss_mode.top_stories')}</h3>
            <ul>${topStories}</ul>
          </section>
        </main>
        <div class="bm-rule-v"></div>
        <aside class="bm-aside">
          <div class="bm-aside-title">${trFn('boss_mode.watchlist')}</div>
          <div class="bm-aside-sub">Late-Session · Indicative</div>
          <div id="bossModeQuoteList" class="bm-quotes">${staticQuotes}</div>
          <div id="bossModeQuoteMeta" class="bm-q-meta"><span class="bm-q-badge">SAMPLE</span></div>
          <button type="button" class="bm-back" data-action="bossLockApi.hideBossMode">${trFn('boss_mode.back')}</button>
          <div class="bm-hint">${trFn('boss_mode.esc_hint')}</div>
        </aside>
      </div>
      <div class="bm-fold-shadow"></div>
    </div>
  `;
}

export const ft: Skin = { id: 'ft', build };
