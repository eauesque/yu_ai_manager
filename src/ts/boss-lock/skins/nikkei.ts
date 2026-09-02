/**
 * boss-lock / skins / nikkei — Japanese broadsheet (Mincho, red 罫 lines).
 *
 * Cream paper, Yu Mincho headlines, red square brand block, dense 4-stripe
 * dateline 罫, 【】 section brackets, 「」-bulleted stories, JIS era date.
 */

import type { BossModeEdition } from '../edition-data';
import { renderStaticQuoteRows } from './quote-rows';
import {
  type EscFn, type TrFn, type Skin, pick,
} from './types';

const KANJI_NUM = ['〇', '一', '二', '三', '四', '五', '六', '七', '八', '九'];
const WEEKDAYS_JP = ['日', '月', '火', '水', '木', '金', '土'];

function toKanjiNum(n: number): string {
  if (n === 0) return KANJI_NUM[0];
  if (n <= 10) return n === 10 ? '十' : KANJI_NUM[n];
  if (n < 20) return '十' + KANJI_NUM[n - 10];
  if (n < 100) {
    const tens = Math.floor(n / 10);
    const ones = n % 10;
    return KANJI_NUM[tens] + '十' + (ones ? KANJI_NUM[ones] : '');
  }
  return String(n);
}

function buildJpDate(d: Date): string {
  const reiwa = d.getFullYear() - 2018; // Reiwa year
  const month = toKanjiNum(d.getMonth() + 1);
  const day = toKanjiNum(d.getDate());
  const wk = WEEKDAYS_JP[d.getDay()];
  return `令和${toKanjiNum(reiwa)}年${month}月${day}日　${wk}曜日`;
}

const ISSUE_BRACKET_NUMS = ['四八、二〇五', '四八、二一二', '四八、二三六', '四八、二九七', '四九、〇一二'];

const CSS = `
#bossModeOverlay {
  --bm-paper:#f5efe2; --bm-paper-2:#ece4d2;
  --bm-ink:#15110c; --bm-ink-soft:#3a322a; --bm-ink-faint:#73685a;
  --bm-rule:#a59883; --bm-rule-soft:#d2c8b4;
  --bm-accent:#a52a2a; --bm-accent-deep:#7a1c1c;
  --bm-green:#1a4d1a; --bm-red:#8a1a1a;
  position:fixed;inset:0;z-index:9999;
  background:var(--bm-paper);color:var(--bm-ink);
  font-family:'Yu Mincho','YuMincho','Hiragino Mincho ProN','Hiragino Mincho Pro','MS PMincho','Noto Serif JP',serif;
  font-feature-settings:"palt" 1,"pkna" 1;
  overflow:auto;
  background-image:
    repeating-linear-gradient(0deg,rgba(60,30,10,0.014) 0 1px,transparent 1px 4px),
    radial-gradient(at 20% 0%,rgba(165,42,42,0.04),transparent 50%);
  animation:bm-fade 540ms ease-out both;
}
@keyframes bm-fade{from{opacity:0;transform:translateY(4px);filter:blur(2px)}to{opacity:1;transform:none;filter:none}}
#bossModeOverlay .bm-wrap{max-width:1180px;margin:0 auto;padding:18px 32px 50px}
#bossModeOverlay .bm-eyebrow{display:flex;justify-content:space-between;align-items:center;
  font-size:10.5px;letter-spacing:0.18em;color:var(--bm-ink-faint);padding-bottom:8px}
#bossModeOverlay .bm-eyebrow b{color:var(--bm-accent);font-weight:700}
#bossModeOverlay .bm-masthead{
  display:grid;grid-template-columns:auto 1fr auto;align-items:center;gap:20px;
  padding:14px 0 8px;
  border-top:3px solid var(--bm-accent);
  border-bottom:1px solid var(--bm-accent);
  position:relative;
}
#bossModeOverlay .bm-masthead::after{
  content:'';position:absolute;left:0;right:0;bottom:-5px;height:1px;background:var(--bm-accent);
}
#bossModeOverlay .bm-mark{
  width:64px;height:64px;display:grid;place-items:center;
  background:var(--bm-accent);color:var(--bm-paper);
  font-size:34px;font-weight:900;letter-spacing:0;line-height:1;
  font-family:'Yu Mincho','Hiragino Mincho ProN',serif;
  box-shadow:inset 0 0 0 2px rgba(255,255,255,0.18),0 1px 0 rgba(0,0,0,0.15);
}
#bossModeOverlay .bm-brand-wrap{text-align:left}
#bossModeOverlay .bm-brand{
  font-family:'Yu Mincho','Hiragino Mincho ProN','MS PMincho',serif;
  font-weight:900;font-size:clamp(34px,5.4vw,58px);letter-spacing:0.04em;line-height:1;
  margin:0;color:var(--bm-ink);
}
#bossModeOverlay .bm-tagline{margin-top:6px;font-size:12px;color:var(--bm-ink-faint);letter-spacing:0.12em}
#bossModeOverlay .bm-issue{text-align:right;font-size:11px;color:var(--bm-ink-soft);letter-spacing:0.12em;line-height:1.5}
#bossModeOverlay .bm-issue b{color:var(--bm-accent);font-weight:700}
#bossModeOverlay .bm-dateline{display:flex;justify-content:space-between;align-items:center;
  margin-top:14px;padding:6px 0;
  border-top:2px solid var(--bm-ink);border-bottom:1px solid var(--bm-ink);
  font-size:11px;letter-spacing:0.18em;color:var(--bm-ink-soft)}
#bossModeOverlay .bm-dateline-mid{color:var(--bm-ink);font-weight:700;letter-spacing:0.22em}
#bossModeOverlay .bm-breaking{margin:14px 0 0;background:var(--bm-accent);color:var(--bm-paper);
  padding:7px 12px;font-size:11px;font-weight:700;letter-spacing:0.5em;text-align:center}
#bossModeOverlay .bm-breaking::before{content:'【速報】';margin-right:8px;letter-spacing:0.16em}
#bossModeOverlay .bm-section-line{display:flex;justify-content:flex-start;flex-wrap:wrap;gap:0 14px;
  margin:14px 0 16px;padding:8px 0;border-bottom:1px solid var(--bm-rule);
  font-size:12px;letter-spacing:0.06em;color:var(--bm-ink);font-weight:700}
#bossModeOverlay .bm-section-line span{display:inline-flex;align-items:center}
#bossModeOverlay .bm-section-line span::before{content:'【';color:var(--bm-accent);margin-right:1px}
#bossModeOverlay .bm-section-line span::after{content:'】';color:var(--bm-accent);margin-left:1px}
#bossModeOverlay .bm-grid{display:grid;grid-template-columns:minmax(0,2.0fr) 1px minmax(280px,1fr);gap:0 22px}
#bossModeOverlay .bm-rule-v{background:var(--bm-rule);margin:0}
#bossModeOverlay .bm-desk{display:inline-block;
  background:var(--bm-accent);color:var(--bm-paper);
  font-size:12px;letter-spacing:0.18em;padding:3px 10px;font-weight:700;margin-bottom:14px}
#bossModeOverlay h1.bm-headline{
  font-family:'Yu Mincho','Hiragino Mincho ProN','MS PMincho',serif;
  margin:0 0 12px;font-size:clamp(30px,4.0vw,44px);line-height:1.18;font-weight:900;
  letter-spacing:0.01em;color:var(--bm-ink);
}
#bossModeOverlay h1.bm-headline::before{
  content:'';display:block;width:34px;height:3px;background:var(--bm-accent);margin:0 0 12px}
#bossModeOverlay .bm-sub{margin:0 0 14px;line-height:1.65;
  font-size:16px;color:var(--bm-ink-soft);max-width:62ch;
  text-align:justify;text-justify:inter-character}
#bossModeOverlay .bm-sub::first-letter{
  font-family:'Yu Mincho','Hiragino Mincho ProN',serif;
  font-weight:900;float:left;font-size:3.4em;line-height:.9;padding:6px 8px 0 0;color:var(--bm-accent)}
#bossModeOverlay .bm-byline{margin:0 0 18px;font-size:11px;color:var(--bm-ink-faint);letter-spacing:0.18em}
#bossModeOverlay .bm-byline em{font-style:normal;color:var(--bm-ink)}
#bossModeOverlay .bm-stories{margin-top:8px;padding-top:14px;
  border-top:2px solid var(--bm-ink);position:relative}
#bossModeOverlay .bm-stories::before{content:'';position:absolute;left:0;right:0;top:3px;height:1px;background:var(--bm-ink)}
#bossModeOverlay .bm-stories h3{margin:0 0 12px;font-size:13px;letter-spacing:0.18em;color:var(--bm-ink);font-weight:700}
#bossModeOverlay .bm-stories h3::before{content:'■';color:var(--bm-accent);margin-right:8px}
#bossModeOverlay .bm-stories ul{list-style:none;margin:0;padding:0}
#bossModeOverlay .bm-stories li{padding:8px 0;border-bottom:1px solid var(--bm-rule-soft);
  font-size:14.5px;line-height:1.55;color:var(--bm-ink-soft);position:relative;padding-left:22px}
#bossModeOverlay .bm-stories li::before{
  content:'「';position:absolute;left:0;top:5px;color:var(--bm-accent);font-weight:700;font-size:14px}
#bossModeOverlay .bm-stories li::after{content:'」';color:var(--bm-accent);font-weight:700;margin-left:4px}
#bossModeOverlay .bm-aside{padding-left:4px;height:max-content}
#bossModeOverlay .bm-aside-title{
  font-family:'Yu Mincho','Hiragino Mincho ProN',serif;
  font-size:22px;font-weight:900;letter-spacing:0.08em;margin:0 0 4px;color:var(--bm-ink);text-align:center}
#bossModeOverlay .bm-aside-title::before{content:'■ ';color:var(--bm-accent);font-size:0.7em}
#bossModeOverlay .bm-aside-sub{font-size:10.5px;letter-spacing:0.22em;color:var(--bm-ink-faint);
  text-align:center;margin:0 0 14px;padding-bottom:10px;border-bottom:1px solid var(--bm-rule)}
#bossModeOverlay .bm-quotes{font-family:'JetBrains Mono','SF Mono',Menlo,Consolas,'Yu Mincho',serif;
  font-size:12.5px;line-height:2;color:var(--bm-ink);font-feature-settings:"tnum" 1,"zero" 1;
  background:var(--bm-paper-2);padding:8px 12px;border:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-q-row{display:flex;justify-content:space-between;gap:12px}
#bossModeOverlay .bm-q-row[data-delta="up"]   .bm-q-val{color:var(--bm-green)}
#bossModeOverlay .bm-q-row[data-delta="down"] .bm-q-val{color:var(--bm-red)}
#bossModeOverlay .bm-q-label{letter-spacing:0.04em}
#bossModeOverlay .bm-q-val{font-weight:700;font-variant-numeric:tabular-nums}
#bossModeOverlay .bm-q-glyph{font-size:9px;margin-right:4px;vertical-align:1px}
#bossModeOverlay .bm-q-meta{margin-top:10px;padding-top:8px;font-size:10px;color:var(--bm-ink-faint);letter-spacing:0.18em;text-align:center;border-top:1px solid var(--bm-rule-soft)}
#bossModeOverlay .bm-q-badge{display:inline-block;padding:1px 8px;border:1px solid var(--bm-rule);font-weight:700;letter-spacing:0.22em}
#bossModeOverlay .bm-back{margin-top:14px;width:100%;padding:10px;
  border:1px solid var(--bm-ink);background:var(--bm-paper);
  font-family:inherit;font-size:13px;letter-spacing:0.32em;color:var(--bm-ink);
  cursor:pointer;font-weight:700;
  transition:background 160ms ease,color 160ms ease}
#bossModeOverlay .bm-back:hover{background:var(--bm-ink);color:var(--bm-paper)}
#bossModeOverlay .bm-hint{margin-top:8px;font-size:10.5px;color:var(--bm-ink-faint);letter-spacing:0.16em;text-align:center}
@media(max-width:720px){
  #bossModeOverlay .bm-grid{grid-template-columns:1fr}
  #bossModeOverlay .bm-rule-v{display:none}
  #bossModeOverlay .bm-aside{margin-top:22px}
  #bossModeOverlay .bm-masthead{grid-template-columns:1fr}
  #bossModeOverlay .bm-mark{justify-self:center}
  #bossModeOverlay .bm-issue{display:none}
}
`;

function build(ed: BossModeEdition, trFn: TrFn, escFn: EscFn): string {
  const topStories = (ed.stories || [trFn('boss_mode.story1'), trFn('boss_mode.story2'), trFn('boss_mode.story3'), trFn('boss_mode.story4')])
    .map((s) => `<li>${escFn(s)}</li>`).join('');
  const sectionLine = (ed.sectionLine || []).map((s) => `<span>${escFn(s)}</span>`).join('');
  const staticQuotes = renderStaticQuoteRows(ed.quotes || [], escFn);

  const dateJp = buildJpDate(new Date());
  const issueNo = pick(ISSUE_BRACKET_NUMS);
  const breaking = ed.showBreaking ? `<div class="bm-breaking">${escFn(ed.breakingText || '')}</div>` : '';

  return `
    <style>${CSS}</style>
    <div class="bm-wrap">
      <div class="bm-eyebrow">
        <span><b>朝刊</b> ・ 全国版</span>
        <span>定価 ¥350（本体 ¥318）</span>
      </div>
      <header class="bm-masthead">
        <div class="bm-mark">日</div>
        <div class="bm-brand-wrap">
          <h1 class="bm-brand">${escFn(ed.brand || trFn('boss_mode.brand'))}</h1>
          <div class="bm-tagline">経済の真実を読み解く ・ 創刊 一八八八年</div>
        </div>
        <div class="bm-issue">
          <div>第 <b>${escFn(issueNo)}</b> 號</div>
          <div>本社 ／ 東京・大手町</div>
        </div>
      </header>
      <div class="bm-dateline">
        <span>${escFn(ed.deskLabel)}</span>
        <span class="bm-dateline-mid">${escFn(dateJp)}</span>
        <span><span id="bossModeTimestamp"></span></span>
      </div>
      ${breaking}
      <nav class="bm-section-line">${sectionLine}</nav>
      <div class="bm-grid">
        <main>
          <span class="bm-desk">${escFn(ed.deskLabel)}</span>
          <h1 class="bm-headline">${escFn(ed.headline || trFn('boss_mode.headline'))}</h1>
          <p class="bm-sub">${escFn(ed.subhead || trFn('boss_mode.subhead'))}</p>
          <div class="bm-byline">本紙 <em>${escFn(ed.byline || 'デスク')}</em></div>
          <section class="bm-stories">
            <h3>${trFn('boss_mode.top_stories')} ・ きょうの主要記事</h3>
            <ul>${topStories}</ul>
          </section>
        </main>
        <div class="bm-rule-v"></div>
        <aside class="bm-aside">
          <div class="bm-aside-title">${trFn('boss_mode.watchlist')}</div>
          <div class="bm-aside-sub">市況 ・ 大引け速報</div>
          <div id="bossModeQuoteList" class="bm-quotes">${staticQuotes}</div>
          <div id="bossModeQuoteMeta" class="bm-q-meta"><span class="bm-q-badge">SAMPLE</span></div>
          <button type="button" class="bm-back" data-action="bossLockApi.hideBossMode">${trFn('boss_mode.back')}</button>
          <div class="bm-hint">${trFn('boss_mode.esc_hint')}</div>
        </aside>
      </div>
    </div>
  `;
}

export const nikkei: Skin = { id: 'nikkei', build };
