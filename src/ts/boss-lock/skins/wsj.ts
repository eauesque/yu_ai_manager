/**
 * boss-lock / skins / wsj — Wall Street Journal style cream broadsheet.
 *
 * Cream paper, Cheltenham-ish Caslon headlines, ★★★★ dateline,
 * "What's News" sidebar with ▪ bullets, navy accents, dense feel.
 */

import type { BossModeEdition } from '../edition-data';
import { renderStaticQuoteRows } from './quote-rows';
import {
  type EscFn, type TrFn, type Skin,
  ROMAN_VOLS, WEATHER_LINES, PRICES,
  pick, formatDateUS, buildIssueNo,
} from './types';

const CSS = `
#bossModeOverlay {
  --bm-paper:#fdf9ef; --bm-paper-2:#f7f1e2;
  --bm-ink:#0d0c0a; --bm-ink-soft:#2a2620; --bm-ink-faint:#5e574b;
  --bm-rule:#7a6f5d; --bm-rule-soft:#c9bfa9;
  --bm-navy:#0e1a3a; --bm-accent:#9a1d1d;
  --bm-green:#1c4a1c; --bm-red:#8a1a1a;
  position:fixed;inset:0;z-index:9999;
  background:var(--bm-paper);color:var(--bm-ink);
  font-family:'Hoefler Text','Garamond Premier Pro','Adobe Caslon Pro','Iowan Old Style',Georgia,'Times New Roman',serif;
  font-feature-settings:"kern" 1,"liga" 1,"onum" 1;
  overflow:auto;
  background-image:
    radial-gradient(at 30% 0%,rgba(120,90,40,0.03),transparent 50%),
    repeating-linear-gradient(0deg,rgba(0,0,0,0.012) 0 1px,transparent 1px 4px);
  animation:bm-fade 540ms ease-out both;
}
@keyframes bm-fade{from{opacity:0;transform:translateY(4px);filter:blur(2px)}to{opacity:1;transform:none;filter:none}}
#bossModeOverlay .bm-wrap{max-width:1180px;margin:0 auto;padding:18px 36px 54px}
#bossModeOverlay .bm-eyebrow{display:flex;justify-content:space-between;gap:24px;align-items:center;
  padding:6px 0;border-top:1px solid var(--bm-ink);border-bottom:1px solid var(--bm-ink);
  font-family:'Hoefler Text',Georgia,serif;
  font-size:10.5px;letter-spacing:0.16em;text-transform:uppercase;color:var(--bm-ink-soft)}
#bossModeOverlay .bm-eyebrow .bm-stars{color:var(--bm-accent);letter-spacing:0.4em}
#bossModeOverlay .bm-masthead{text-align:center;padding:22px 0 12px;border-bottom:5px double var(--bm-ink)}
#bossModeOverlay .bm-brand{
  font-family:'Hoefler Text','Adobe Caslon Pro','Garamond Premier Pro',Georgia,serif;
  font-weight:900;font-size:clamp(46px,7.6vw,84px);letter-spacing:-0.012em;line-height:.95;
  color:var(--bm-ink);margin:0;
  font-stretch:condensed;
  text-transform:uppercase;
}
#bossModeOverlay .bm-tagline{margin-top:6px;font-style:italic;font-size:12px;color:var(--bm-ink-faint);letter-spacing:0.04em}
#bossModeOverlay .bm-section-line{display:flex;justify-content:center;align-items:center;flex-wrap:wrap;gap:0 18px;
  margin:10px 0 0;padding:8px 0;border-bottom:1px solid var(--bm-ink);
  font-size:11px;letter-spacing:0.32em;text-transform:uppercase;color:var(--bm-ink);font-weight:700}
#bossModeOverlay .bm-section-line span{display:inline-flex;align-items:center}
#bossModeOverlay .bm-section-line span+span::before{content:'▪';color:var(--bm-ink);opacity:.6;margin-right:18px;font-size:8px;letter-spacing:0;transform:translateY(-1px)}
#bossModeOverlay .bm-breaking{margin:14px 0 8px;background:var(--bm-accent);color:#fff;padding:7px 12px;
  font-size:11px;font-weight:800;letter-spacing:0.5em;text-transform:uppercase;text-align:center}
#bossModeOverlay .bm-grid{display:grid;grid-template-columns:minmax(0,2.3fr) 1px minmax(260px,1fr);gap:0 24px;margin-top:18px}
#bossModeOverlay .bm-rule-v{background:var(--bm-rule-soft);margin:0}
#bossModeOverlay .bm-desk{display:inline-block;
  font-size:11px;letter-spacing:0.36em;text-transform:uppercase;color:var(--bm-navy);font-weight:800;
  margin-bottom:8px;border-bottom:2px solid var(--bm-navy);padding:0 0 3px}
#bossModeOverlay h1.bm-headline{
  font-family:'Hoefler Text','Adobe Caslon Pro','Garamond Premier Pro',Georgia,serif;
  margin:0 0 10px;font-size:clamp(34px,4.2vw,52px);line-height:1.02;font-weight:900;
  letter-spacing:-0.012em;color:var(--bm-ink);
  text-rendering:optimizeLegibility;
}
#bossModeOverlay h1.bm-headline::after{content:'';display:block;width:64px;height:2px;background:var(--bm-ink);margin:14px 0 0}
#bossModeOverlay .bm-sub{margin:14px 0 8px;font-style:italic;line-height:1.45;
  font-size:18px;color:var(--bm-ink-soft);max-width:60ch;font-weight:500}
#bossModeOverlay .bm-byline{margin:8px 0 16px;font-size:10.5px;color:var(--bm-ink-faint);
  letter-spacing:0.22em;text-transform:uppercase;font-weight:700}
#bossModeOverlay .bm-byline em{font-style:normal;color:var(--bm-ink)}
#bossModeOverlay .bm-stories{margin-top:16px;padding-top:14px;border-top:1px solid var(--bm-ink)}
#bossModeOverlay .bm-stories h3{margin:0 0 10px;font-size:11.5px;letter-spacing:0.36em;text-transform:uppercase;
  color:var(--bm-navy);font-weight:800}
#bossModeOverlay .bm-stories ul{list-style:none;margin:0;padding:0;column-count:2;column-gap:24px;column-rule:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-stories li{padding:6px 0 8px;border-bottom:1px dotted var(--bm-rule-soft);
  font-size:14px;line-height:1.4;color:var(--bm-ink-soft);position:relative;padding-left:18px;break-inside:avoid}
#bossModeOverlay .bm-stories li::before{content:'▪';position:absolute;left:0;top:7px;color:var(--bm-ink);font-size:10px}
#bossModeOverlay .bm-aside{padding:0 4px;height:max-content}
#bossModeOverlay .bm-aside-title{
  font-family:'Hoefler Text','Adobe Caslon Pro',Georgia,serif;
  font-size:24px;font-weight:900;letter-spacing:-0.005em;margin:0 0 4px;color:var(--bm-ink);
  border-bottom:3px double var(--bm-ink);padding-bottom:6px}
#bossModeOverlay .bm-aside-sub{font-size:9.5px;letter-spacing:0.3em;text-transform:uppercase;
  color:var(--bm-ink-faint);margin:6px 0 14px;font-weight:700}
#bossModeOverlay .bm-quotes{font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,monospace;
  font-size:12.5px;line-height:2;color:var(--bm-ink);font-feature-settings:"tnum" 1,"zero" 1;
  border-top:1px solid var(--bm-ink);padding-top:8px;margin-top:8px}
#bossModeOverlay .bm-quotes::before{content:'WHAT MARKETS DID';display:block;font-family:'Hoefler Text',Georgia,serif;
  font-size:10.5px;letter-spacing:0.32em;color:var(--bm-navy);font-weight:800;margin-bottom:6px}
#bossModeOverlay .bm-q-row{display:flex;justify-content:space-between;gap:12px;padding:0 2px}
#bossModeOverlay .bm-q-row[data-delta="up"]   .bm-q-val{color:var(--bm-green)}
#bossModeOverlay .bm-q-row[data-delta="down"] .bm-q-val{color:var(--bm-red)}
#bossModeOverlay .bm-q-label{letter-spacing:0.05em}
#bossModeOverlay .bm-q-val{font-weight:700;font-variant-numeric:tabular-nums}
#bossModeOverlay .bm-q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
#bossModeOverlay .bm-q-meta{margin-top:10px;padding-top:8px;font-size:10px;color:var(--bm-ink-faint);
  letter-spacing:0.18em;text-transform:uppercase;border-top:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-ink);font-weight:700;letter-spacing:0.26em}
#bossModeOverlay .bm-back{margin-top:14px;width:100%;padding:9px;
  border:1px solid var(--bm-ink);background:var(--bm-paper-2);
  font-family:'Hoefler Text',Georgia,serif;font-size:11px;letter-spacing:0.3em;text-transform:uppercase;
  color:var(--bm-ink);cursor:pointer;font-weight:700;
  transition:background 160ms ease,color 160ms ease}
#bossModeOverlay .bm-back:hover{background:var(--bm-ink);color:var(--bm-paper)}
#bossModeOverlay .bm-hint{margin-top:8px;font-size:10px;color:var(--bm-ink-faint);letter-spacing:0.18em;text-transform:uppercase;text-align:center}
@media(max-width:720px){
  #bossModeOverlay .bm-grid{grid-template-columns:1fr}
  #bossModeOverlay .bm-rule-v{display:none}
  #bossModeOverlay .bm-aside{margin-top:22px}
  #bossModeOverlay .bm-stories ul{column-count:1}
}
`;

function build(ed: BossModeEdition, trFn: TrFn, escFn: EscFn): string {
  const topStories = (ed.stories || [trFn('boss_mode.story1'), trFn('boss_mode.story2'), trFn('boss_mode.story3'), trFn('boss_mode.story4')])
    .map((s) => `<li>${escFn(s)}</li>`).join('');
  const sectionLine = (ed.sectionLine || []).map((s) => `<span>${escFn(s)}</span>`).join('');
  const staticQuotes = renderStaticQuoteRows(ed.quotes || [], escFn);

  const vol     = pick(ROMAN_VOLS);
  const issueNo = buildIssueNo();
  const weather = pick(WEATHER_LINES);
  const price   = pick(PRICES);
  const dateStr = formatDateUS(new Date());
  const stars   = '★ ★ ★ ★';

  const breaking = ed.showBreaking ? `<div class="bm-breaking">${escFn(ed.breakingText || 'Breaking')}</div>` : '';

  return `
    <style>${CSS}</style>
    <div class="bm-wrap">
      <div class="bm-eyebrow">
        <span>VOL. ${escFn(vol)} · NO. ${escFn(issueNo)}</span>
        <span class="bm-stars">${stars}</span>
        <span>${escFn(dateStr)}</span>
        <span>© 2026 · ${escFn(price)}</span>
      </div>
      <header class="bm-masthead">
        <h1 class="bm-brand">${escFn(ed.brand || trFn('boss_mode.brand'))}</h1>
        <div class="bm-tagline">${escFn(weather)} &nbsp;·&nbsp; wsjt.com</div>
      </header>
      <nav class="bm-section-line">${sectionLine}</nav>
      ${breaking}
      <div class="bm-grid">
        <main>
          <span class="bm-desk">${escFn(ed.deskLabel)}</span>
          <h1 class="bm-headline">${escFn(ed.headline || trFn('boss_mode.headline'))}</h1>
          <p class="bm-sub">${escFn(ed.subhead || trFn('boss_mode.subhead'))}</p>
          <div class="bm-byline"><em>${escFn(ed.byline || 'By Desk')}</em> · <span id="bossModeTimestamp"></span></div>
          <section class="bm-stories">
            <h3>What's News &mdash; ${trFn('boss_mode.top_stories')}</h3>
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
    </div>
  `;
}

export const wsj: Skin = { id: 'wsj', build };
