import type { RetagSinglePayload } from './retag-modal-types';
import { t } from './retag-modal-ui';

export function renderResult(resultEl: HTMLElement, payload: RetagSinglePayload): void {
  resultEl.textContent = '';
  const tags = payload.tags || [];
  const inserted = payload.inserted ?? tags.length;
  const elapsed = Math.round(payload.elapsed_ms || 0);

  const summary = document.createElement('div');
  summary.style.marginBottom = '8px';
  summary.textContent = t('tools.wt_retag_summary', 'Inserted {n} tags in {ms} ms')
    .replace('{n}', String(inserted))
    .replace('{ms}', String(elapsed));
  resultEl.appendChild(summary);

  const tagsWrap = document.createElement('div');
  tagsWrap.style.cssText = 'display:flex;flex-wrap:wrap;gap:4px;max-height:240px;overflow:auto;';
  for (const tag of tags) {
    const span = document.createElement('span');
    span.className = `wt-tag wt-tag-${tag.category || 'general'}`;
    const conf = (tag.confidence * 100).toFixed(0) + '%';
    span.title = conf;
    span.style.cssText = [
      'display:inline-block', 'padding:2px 6px',
      'border-radius:4px',
      'background:var(--tag-bg,rgba(0,0,0,0.05))',
      'font-size:11px',
    ].join(';');
    span.appendChild(document.createTextNode(tag.tag + ' '));
    const confSpan = document.createElement('span');
    confSpan.style.opacity = '0.6';
    confSpan.textContent = conf;
    span.appendChild(confSpan);
    tagsWrap.appendChild(span);
  }
  resultEl.appendChild(tagsWrap);
}
