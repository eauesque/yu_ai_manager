import { safeViewTransition } from '../shared/view-transition';
import { formatElapsedHms } from '../shared/date-format';
import { openFullsize } from './fullsize-overlay';
import type { AdetailerEntry, CharacterPrompt, ResultData, ResultPanelAction } from './result-panel';

export interface HistoryEntry {
  src: string;
  base64: string;
  seed: string;
  elapsed: string;
  expandedPrompt?: string | undefined;
  originalPrompt?: string | undefined;
  finalNegative?: string | undefined;
  characters?: CharacterPrompt[] | undefined;
  adetailer?: AdetailerEntry[] | undefined;
  saved?: string[] | undefined;
}

function appendDetails(parent: HTMLElement, label: string, content: string, color?: string, faded?: boolean): void {
  const details = document.createElement('details');
  details.className = 'brp-expanded';
  const summary = document.createElement('summary');
  summary.textContent = label;
  if (color) summary.style.color = color;
  details.appendChild(summary);
  const pre = document.createElement('div');
  pre.className = 'brp-expanded-text';
  pre.textContent = content;
  if (faded) pre.style.opacity = '0.5';
  details.appendChild(pre);
  parent.appendChild(details);
}

export function showEntry(entry: HistoryEntry, latestEl: HTMLElement, metaEl: HTMLElement, actions: ResultPanelAction[]): void {
  safeViewTransition(() => {
    latestEl.textContent = '';
    const img = document.createElement('img');
    img.src = entry.src;
    img.alt = 'Generated';
    img.className = 'brp-latest-img';
    img.title = 'クリックで原寸表示';
    img.addEventListener('click', () => openFullsize(entry.src));
    latestEl.appendChild(img);
    if (actions.length > 0) {
      const bar = document.createElement('div');
      bar.className = 'brp-actions';
      actions.forEach((act) => {
        const btn = document.createElement('button');
        btn.className = 'brp-action-btn';
        btn.textContent = act.label;
        if (act.title) btn.title = act.title;
        btn.addEventListener('click', () => act.onClick(entry.base64));
        bar.appendChild(btn);
      });
      latestEl.appendChild(bar);
    }
    metaEl.textContent = '';
    if (entry.seed) {
      const seedSpan = document.createElement('span');
      seedSpan.textContent = 'Seed: ' + entry.seed;
      metaEl.appendChild(seedSpan);
    }
    if (entry.elapsed) {
      if (entry.seed) metaEl.appendChild(Object.assign(document.createElement('span'), { textContent: ' \u00A0 ' }));
      const elapsedSpan = document.createElement('span');
      elapsedSpan.textContent = entry.elapsed;
      metaEl.appendChild(elapsedSpan);
    }
    if (entry.expandedPrompt) appendDetails(metaEl, entry.originalPrompt ? 'Expanded Prompt' : 'Prompt', entry.expandedPrompt, '#4fc3f7');
    if (typeof entry.finalNegative === 'string') appendDetails(metaEl, 'Negative', entry.finalNegative || '(none)', '#ef9a9a', !entry.finalNegative);
    if (entry.characters?.length) {
      entry.characters.forEach((ch, ci) => {
        const parts: string[] = [];
        if (ch.prompt) parts.push(ch.prompt);
        if (ch.negative) parts.push('[Negative] ' + ch.negative);
        appendDetails(metaEl, 'Character ' + (ci + 1), parts.join('\n') || '(empty)', '#ce93d8');
      });
    }
    if (entry.adetailer?.length) {
      entry.adetailer.forEach((ad, ai) => {
        const parts: string[] = [];
        if (ad.model) parts.push('[Model] ' + ad.model);
        if (ad.prompt) parts.push(ad.prompt);
        if (ad.negative) parts.push('[Negative] ' + ad.negative);
        appendDetails(metaEl, 'ADetailer ' + (ai + 1), parts.join('\n') || '(empty)', '#ffb74d');
      });
    }
    if (entry.saved?.length) {
      const savedDiv = document.createElement('div');
      savedDiv.className = 'brp-saved';
      savedDiv.textContent = 'Saved: ' + entry.saved.join(', ');
      metaEl.appendChild(savedDiv);
    }
  });
}

export function buildHistoryEntry(img: { base64?: string; seed?: number | string }, mime: string, resultData?: ResultData): HistoryEntry | null {
  if (!img.base64) return null;
  return {
    src: 'data:' + mime + ';base64,' + img.base64,
    base64: img.base64,
    seed: String(img.seed || '?'),
    elapsed: resultData?.elapsed_ms ? formatElapsedHms(resultData.elapsed_ms / 1000) : '',
    expandedPrompt: resultData?.expanded_prompt,
    originalPrompt: resultData?.original_prompt,
    finalNegative: resultData?.final_negative,
    characters: resultData?.characters,
    adetailer: resultData?.adetailer,
    saved: resultData?.saved,
  };
}
