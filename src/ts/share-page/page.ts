/**
 * Share page — decodes and renders shared prompt data from URL parameters.
 * Converted from static/js/share/share-page.js
 */

import { getAppApi } from '../shared/browser-apis';
import { getShareData, setShareData } from '../shared/runtime-state/share-page-state';
import { copyToClipboard } from '../shared/clipboard';

/** i18n helper: use window.tr if available, otherwise return fallback. */
function _t(key: string, fallback: string = ''): string {
  return getAppApi().tr(key, fallback);
}

/** Shared prompt data structure encoded in the URL `data` parameter. */
export interface ShareData {
  /** Positive prompt */
  p?: string;
  /** Negative prompt */
  n?: string;
  /** Model name */
  m?: string;
  /** Seed */
  s?: string;
  /** Steps */
  st?: string;
  /** CFG scale */
  cfg?: string;
  /** Sampler */
  sa?: string;
  /** Size (e.g. "512x768") */
  sz?: string;
}

/**
 * Escape a string for safe HTML insertion.
 */
export function escHtml(s: unknown): string {
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Decode the share data from URL search params and render.
 */
export function decodeShareData(): void {
  const params = new URLSearchParams(window.location.search);
  const encoded = params.get('data');

  if (!encoded) {
    const content = document.getElementById('content');
    if (content) {
      const div = document.createElement('div');
      div.className = 'error';
      div.textContent = _t('share.no_data', '共有データはありません');
      content.replaceChildren(div);
    }
    return;
  }

  try {
    const json = decodeURIComponent(escape(atob(encoded)));
    const data: ShareData = JSON.parse(json);
    renderShareData(data);
  } catch (e: unknown) {
    const message = e instanceof Error ? e.message : String(e);
    const content = document.getElementById('content');
    if (content) {
      const div = document.createElement('div');
      div.className = 'error';
      div.textContent = _t('share.parse_failed', '共有データの解析に失敗しました');
      const br = document.createElement('br');
      const small = document.createElement('small');
      small.textContent = message;
      div.append(br, small);
      content.replaceChildren(div);
    }
  }
}

/**
 * Render decoded share data into #content.
 */
export function renderShareData(d: ShareData): void {
  let html = `
    <h1>\uD83D\uDCF1 ${_t('share.prompt_share', 'Prompt Share')} <span class="badge">Tag Database</span></h1>
  `;

  if (d.p) {
    html += `
      <div class="section">
        <h3>\u2728 Positive Prompt</h3>
        <div class="prompt-text" id="positiveText">${escHtml(d.p)}</div>
      </div>
    `;
  }

  if (d.n) {
    html += `
      <div class="section">
        <h3>\uD83D\uDEAB Negative Prompt</h3>
        <div class="prompt-text" id="negativeText">${escHtml(d.n)}</div>
      </div>
    `;
  }

  const meta: string[] = [];
  if (d.m) meta.push(`<b>Model:</b> ${escHtml(d.m)}`);
  if (d.s) meta.push(`<b>Seed:</b> ${escHtml(d.s)}`);
  if (d.st) meta.push(`<b>Steps:</b> ${escHtml(d.st)}`);
  if (d.cfg) meta.push(`<b>CFG:</b> ${escHtml(d.cfg)}`);
  if (d.sa) meta.push(`<b>Sampler:</b> ${escHtml(d.sa)}`);
  if (d.sz) meta.push(`<b>Size:</b> ${escHtml(d.sz)}`);

  if (meta.length) {
    html += `
      <div class="section">
        <h3>\u2699\uFE0F ${_t('share.gen_params', 'Generation Parameters')}</h3>
        <div class="meta-row">${meta.map((m) => `<span class="meta-item">${m}</span>`).join('')}</div>
      </div>
    `;
  }

  html += `
    <div class="actions">
      <button type="button" class="btn btn-primary" data-share-copy="positive">\uD83D\uDCCB ${_t('share.copy_prompt', 'Copy Prompt')}</button>
      ${d.n ? '<button type="button" class="btn btn-secondary" data-share-copy="negative">\uD83D\uDCCB ' + _t('share.copy_negative', 'Copy Negative') + '</button>' : ''}
      <button type="button" class="btn btn-secondary" data-share-copy-all="1">\uD83D\uDCCB ${_t('share.copy_all', 'Copy All')}</button>
    </div>
  `;

  const content = document.getElementById('content');
  if (content) {
    content.innerHTML = html;
    content.querySelectorAll<HTMLElement>('[data-share-copy]').forEach((btn) => {
      btn.addEventListener('click', () => {
        const type = btn.dataset.shareCopy;
        if (type) copyPrompt(type);
      });
    });
    content.querySelector<HTMLElement>('[data-share-copy-all="1"]')?.addEventListener('click', () => {
      copyAll();
    });
  }
  setShareData(d);
}

/**
 * Copy a prompt (positive or negative) to the clipboard.
 */
export function copyPrompt(type: string): void {
  const d = getShareData();
  if (!d) return;

  const text = type === 'positive' ? d.p : d.n;
  if (!text) return;

  void copyToClipboard(text).then(() => {
    const activeEl = document.activeElement as HTMLElement | null;
    if (activeEl) showCopied(activeEl);
  });
}

/**
 * Copy all prompt data (positive + negative + metadata) to the clipboard.
 */
export function copyAll(): void {
  const d = getShareData();
  if (!d) return;

  let text = d.p || '';
  if (d.n) text += '\n\nNegative prompt: ' + d.n;
  if (d.m) text += '\nModel: ' + d.m;
  if (d.s) text += '\nSeed: ' + d.s;
  if (d.st) text += '\nSteps: ' + d.st;
  if (d.cfg) text += '\nCFG scale: ' + d.cfg;
  if (d.sa) text += '\nSampler: ' + d.sa;

  void copyToClipboard(text).then(() => {
    const activeEl = document.activeElement as HTMLElement | null;
    if (activeEl) showCopied(activeEl);
  });
}

/**
 * Show a brief "Copied" feedback near the button.
 */
export function showCopied(btn: HTMLElement): void {
  const span = document.createElement('span');
  span.className = 'copied';
  span.textContent = _t('share.copied', 'Copied');
  if (btn.parentNode) {
    btn.parentNode.appendChild(span);
  }
  setTimeout(() => span.remove(), 2000);
}
