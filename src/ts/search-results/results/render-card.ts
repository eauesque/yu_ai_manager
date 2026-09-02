/**
 * results/render-card.ts
 *
 * HTML builders for individual result cards and container (folder/ZIP) cards.
 *
 * Converted from runtime-results-render-card.js (IIFE -> named exports).
 */

import { getAppApi, getDetailModalApi, getRuntimeToolsApi, getSearchResultsApi } from '../../shared/browser-apis';
import { icon } from '../../shared/icon';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

interface GroupInfo {
  type: 'zip' | 'archive' | 'folder';
  key: string;
  label: string;
  count: number;
  representativeIds: number[];
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  firstResult: Record<string, any>;
}

function _shortPositive(text: string | undefined): string {
  const v = text || '';
  return v.substring(0, 100) + (v.length > 100 ? '...' : '');
}

/** Map internal meta_source to short display label + CSS class. */
function _metaSourceBadge(src: string | undefined): string {
  const s = (src || '').toLowerCase();
  let label = '';
  let cls = 'meta-badge';
  if (s.startsWith('novelai')) { label = 'NAI'; cls += ' meta-nai'; }
  else if (s.startsWith('a1111')) { label = 'SD'; cls += ' meta-sd'; }
  else if (s.startsWith('comfy')) { label = 'Comfy'; cls += ' meta-comfy'; }
  else if (s === 'semantic') { label = ''; }
  else if (s && s !== 'unknown') { label = s.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase()); cls += ' meta-other'; }
  if (!label) return '';
  return `<span class="${cls}">${label}</span>`;
}

export function buildResultCardInnerHtml(result: ResultRecord): string {
  const { apiUrl, escapeHtml, tr } = getAppApi();
  const { renderFileName } = getRuntimeToolsApi();
  const date = new Date(result.mtime * 1000).toLocaleString('ja-JP');
  const filename = renderFileName(result.path);
  const positiveShort = _shortPositive(result.positive || '');

  let pdfBadge = '';
  if (result.path && result.path.toLowerCase().endsWith('.pdf')) {
    pdfBadge = '<span class="card-pdf-badge">PDF</span>';
  }

  return `<div role="gridcell">
      <label class="fav-select-cb-wrap">
        <input type="checkbox" class="fav-select-cb" name="fav-select" data-file-id="${result.id}" aria-label="Select for favorites">
        <span class="fav-select-check"></span>
      </label>
      <button type="button" class="card-fav-btn" data-file-id="${result.id}"
        title="Toggle favorite">${icon('star', { className: 'card-fav-icon' })}</button>
      ${pdfBadge}
      <img class="result-image"
           src="${apiUrl(`/api/thumbnail/${result.id}`)}"
           data-native-src="${apiUrl(`/api/thumbnail/${result.id}`)}"
           alt="${escapeHtml(filename)}"
           loading="lazy"
           decoding="async"
           role="button" tabindex="0"
           data-file-id="${result.id}">

      <div class="result-info">
        <div class="result-meta">${_metaSourceBadge(result.meta_source)}${escapeHtml(date)}</div>
        <div class="result-prompt collapsed prompt-toggle" id="prompt-${result.id}"
          role="button" tabindex="0" aria-expanded="false"
          data-prompt-toggle="${result.id}">
          <span class="prompt-label">${tr('result.positive_label', 'Positive:')}</span>${escapeHtml(positiveShort)}
          <span class="prompt-chev" aria-hidden="true">\u25B8</span>
        </div>
        <div class="result-actions">
          <span class="copy-wrap"><button class="btn-small copy-action" type="button" data-copy-prompt-id="${result.id}" data-copy-prompt-type="positive" title="${escapeHtml(tr('result.copy_prompt_title'))}">\uD83D\uDCCB</button><span class="copy-pop" aria-hidden="true"></span></span>
        </div>
      </div>
    </div>`;
}

export function applyResultCardData(card: HTMLElement, result: ResultRecord): void {
  card.dataset.id = String(result.id || '');
  card.dataset.path = result.path || '';
  card.dataset.positive = result.positive || '';
  card.dataset.negative = result.negative || '';
}

export function bindResultCardInteractions(card: HTMLElement): void {
  const { showDetail } = getDetailModalApi();
  const { toggleFavorite } = getRuntimeToolsApi();
  const { copyPrompt, togglePrompt } = getSearchResultsApi();
  const markLoadedIfReady = (img: HTMLImageElement): void => {
    // Cached images can complete before listeners are attached.
    // Require >1px to skip the 1x1 TRANSPARENT_PIXEL placeholder set by
    // VirtualGrid: marking the placeholder as "loaded" makes _isDomThumbnailLoaded
    // return true and causes _fallbackToNative to skip the img, leaving it
    // stuck at the transparent placeholder forever (the "white square that
    // never recovers after fast scroll" bug).
    if (img.complete && img.naturalWidth > 1 && img.naturalHeight > 1) {
      img.dataset.loaded = '1';
    }
  };

  card.querySelector<HTMLLabelElement>('.fav-select-cb-wrap')?.addEventListener('click', (event) => {
    event.stopPropagation();
  });

  card.querySelector<HTMLInputElement>('.fav-select-cb')?.addEventListener('change', () => {
    const runtimeToolsApi = window.runtimeToolsApi as Record<string, unknown> | undefined;
    const fn = runtimeToolsApi?.favSelectChanged;
    if (typeof fn === 'function') {
      (fn as () => void)();
    }
  });

  card.querySelector<HTMLButtonElement>('.card-fav-btn')?.addEventListener('click', (event) => {
    event.stopPropagation();
    const fileId = parseInt((event.currentTarget as HTMLButtonElement).dataset.fileId || '0', 10);
    if (fileId > 0) void toggleFavorite(fileId);
  });

  const resultImage = card.querySelector<HTMLImageElement>('.result-image');
  resultImage?.addEventListener('load', (event) => {
    const img = event.currentTarget as HTMLImageElement;
    // Skip the 1x1 TRANSPARENT_PIXEL placeholder (see markLoadedIfReady comment).
    // Without this guard, the placeholder load marks the img as "loaded" and
    // subsequent _fallbackToNative skips it, leaving fast-scroll regions with
    // permanent white squares when the server fails to return the id in batch.
    if (img.naturalWidth <= 1 && img.naturalHeight <= 1) return;
    img.dataset.loaded = '1';
    delete img.dataset.loadError;
    img.style.opacity = '';
  });
  resultImage?.addEventListener('error', (event) => {
    const img = event.currentTarget as HTMLImageElement;
    // Recovery: a blob: URL may have been revoked (LRU eviction in thumbnail-batch).
    // Fall back to the native endpoint and let the browser re-fetch.
    const currentSrc = img.getAttribute('src') || '';
    const nativeSrc = img.dataset.nativeSrc;
    if (currentSrc.startsWith('blob:') && nativeSrc && currentSrc !== nativeSrc) {
      delete img.dataset.loaded;
      delete img.dataset.loadError;
      img.style.opacity = '';
      img.src = nativeSrc;
      return;
    }
    img.dataset.loadError = '1';
    img.style.opacity = '0.3';
    img.alt = 'Thumbnail unavailable';
  });
  if (resultImage) markLoadedIfReady(resultImage);
  resultImage?.addEventListener('click', (event) => {
    if (event.ctrlKey || event.metaKey || event.shiftKey) return;
    const fileId = parseInt((event.currentTarget as HTMLImageElement).dataset.fileId || '0', 10);
    if (fileId > 0) showDetail(fileId, { source: 'library', scope: 'result_set' });
  });
  resultImage?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    const fileId = parseInt((event.currentTarget as HTMLImageElement).dataset.fileId || '0', 10);
    if (fileId > 0) showDetail(fileId, { source: 'library', scope: 'result_set' });
  });

  card.querySelector<HTMLElement>('.prompt-toggle')?.addEventListener('click', () => {
    const promptId = parseInt(card.querySelector<HTMLElement>('.prompt-toggle')?.dataset.promptToggle || '0', 10);
    if (promptId > 0) togglePrompt(promptId);
  });
  card.querySelector<HTMLElement>('.prompt-toggle')?.addEventListener('keydown', (event) => {
    if (event.key !== 'Enter' && event.key !== ' ') return;
    event.preventDefault();
    const promptId = parseInt((event.currentTarget as HTMLElement).dataset.promptToggle || '0', 10);
    if (promptId > 0) togglePrompt(promptId);
  });

  card.querySelector<HTMLButtonElement>('.copy-action')?.addEventListener('click', (event) => {
    const btn = event.currentTarget as HTMLButtonElement;
    const promptId = parseInt(btn.dataset.copyPromptId || '0', 10);
    const promptType = btn.dataset.copyPromptType || 'positive';
    if (promptId > 0) copyPrompt(promptId, promptType, event);
  });

  card.querySelectorAll<HTMLImageElement>('.stack-thumb').forEach((img) => {
    img.addEventListener('load', () => {
      img.dataset.loaded = '1';
    });
    img.addEventListener('error', () => {
      img.style.opacity = '0.15';
    });
    markLoadedIfReady(img);
  });
}

export function buildCollapsedPromptHtml(positive: string): string {
  const { escapeHtml, tr } = getAppApi();
  const positiveShort = _shortPositive(positive || '');
  return `<span class="prompt-label">${tr('result.positive_label', 'Positive:')}</span>${escapeHtml(positiveShort)}<span class="prompt-chev" aria-hidden="true">\u25B8</span>`;
}

export function buildExpandedPromptHtml(positive: string, negative: string): string {
  const { escapeHtml, tr } = getAppApi();
  return `
      <div><span class="prompt-label">${tr('result.positive_label', 'Positive:')}</span>${escapeHtml(positive || '')}</div>
      ${negative ? `<div style="margin-top: 10px;"><span class="prompt-label prompt-negative">${tr('result.negative_label', 'Negative:')}</span>${escapeHtml(negative)}</div>` : ''}
      <span class="prompt-chev" aria-hidden="true">\u25BE</span>
    `;
}

/**
 * Determine how many thumbnails to show based on card width.
 * Uses the CSS --grid-min-size or falls back to grid element measurement.
 */
function _containerThumbCount(): number {
  const grid = document.getElementById('results');
  if (!grid) return 1;
  // Try to read --grid-min-size from the grid element
  const minSizeStr = getComputedStyle(grid).getPropertyValue('--grid-min-size').trim();
  let w = parseInt(minSizeStr, 10);
  if (!w || w <= 0) {
    // Fallback: measure first card width
    const card = grid.querySelector<HTMLElement>('.result-card');
    w = card ? card.offsetWidth : 300;
  }
  if (w < 180) return 1;
  if (w < 250) return 2;
  if (w < 350) return 4;
  return 8;
}

/**
 * Build inner HTML for a container card (ZIP or folder).
 */
export function buildContainerCardInnerHtml(groupInfo: GroupInfo): string {
  const { apiUrl, escapeHtml, tr } = getAppApi();
  const thumbCount = _containerThumbCount();
  let ids = (groupInfo.representativeIds || []).slice(0, thumbCount);
  // Ensure we use a valid data-count that has CSS rules
  const effectiveCount = ids.length >= 8 ? 8 : ids.length >= 4 ? 4 : ids.length >= 2 ? 2 : 1;
  ids = ids.slice(0, effectiveCount);

  const isArchive = groupInfo.type === 'zip' || groupInfo.type === 'archive';
  const icon = isArchive ? '\uD83D\uDCE6' : '\uD83D\uDCC1';
  const thumbsHtml = ids.map(function (id) {
    return '<img class="stack-thumb" src="' + apiUrl('/api/thumbnail/' + id) + '" loading="lazy" decoding="async" alt="">';
  }).join('');

  const i18nKey = isArchive ? 'container.archive_items' : 'container.folder_items';
  const countLabel = tr(i18nKey, '{count} items').replace('{count}', String(groupInfo.count));

  return '<div role="gridcell">' +
    '<div class="container-thumb-stack" data-count="' + effectiveCount + '">' +
      thumbsHtml +
      '<div class="container-overlay">' +
        '<span class="container-icon">' + icon + '</span>' +
        '<span class="container-count">' + escapeHtml(String(groupInfo.count)) + '</span>' +
      '</div>' +
    '</div>' +
    '<div class="result-info">' +
      '<div class="result-meta">' + escapeHtml(groupInfo.label) + '</div>' +
      '<div class="result-prompt collapsed">' + escapeHtml(countLabel) + '</div>' +
    '</div>' +
    '</div>';
}
