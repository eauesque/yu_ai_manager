/**
 * ocr-export.ts -- OCR translation, export, and overlay handlers.
 *
 * Extracted from ocr-actions.ts to keep each module under 300 lines.
 */

import { _esc, TranslationData } from './ocr-types';
import { getAppApi } from '../../shared/browser-apis';

/* ------------------------------------------------------------------ */
/* Translation                                                         */
/* ------------------------------------------------------------------ */

export function bindTranslateBtn(fileId: number): void {
  const appApi = getAppApi();
  const btn = document.getElementById(`ocrTranslateBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const langSel = document.getElementById(`ocrTargetLang-${fileId}`) as HTMLSelectElement | null;
    const targetLang = langSel?.value || 'en';
    const status = document.getElementById(`ocrTranslateStatus-${fileId}`);

    btn.setAttribute('disabled', 'true');
    btn.setAttribute('aria-disabled', 'true');
    if (status) status.textContent = 'Translating...';

    try {
      const taskSel = document.getElementById(`ocrTask-${fileId}`) as HTMLSelectElement | null;
      const task = taskSel?.value || '';
      const resp = await appApi.apiFetch(`/api/ocr/translate/${fileId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ target_lang: targetLang, task }),
      });
      const json = await resp.json();
      if (!resp.ok) {
        throw new Error(json.error || 'Translation failed');
      }
      const data = json.data || json;
      if (status) status.textContent = '';
      showTranslationResult(fileId, data);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (status) status.textContent = msg;
    } finally {
      btn.removeAttribute('disabled');
      btn.removeAttribute('aria-disabled');
    }
  });
}

export function showTranslationResult(fileId: number, data: TranslationData): void {
  const display = document.getElementById(`ocrTranslationDisplay-${fileId}`);
  if (!display) return;
  display.style.display = 'block';

  let html = '<div class="ocr-translation-header">';
  html += '<span class="ocr-lang-badge">\u2192 ' + _esc(data.target_lang) + '</span>';
  if (data.engine) html += ' <span class="ocr-engine-badge">' + _esc(data.engine) + '</span>';
  html += '</div>';

  // Per-region translation
  if (data.region_translations && data.region_translations.length > 0) {
    html += '<div class="ocr-parallel-view">';
    for (const rt of data.region_translations) {
      html += '<div class="ocr-parallel-row">';
      if (rt.label) html += '<span class="ocr-region-label">' + _esc(rt.label) + '</span>';
      html += '<div class="ocr-parallel-original">' + _esc(rt.original) + '</div>';
      html += '<div class="ocr-parallel-arrow">\u2192</div>';
      html += '<div class="ocr-parallel-translated">' + _esc(rt.translated) + '</div>';
      html += '</div>';
    }
    html += '</div>';
  }

  // Full text translation
  if (data.translated_text) {
    html += '<div class="ocr-translated-full">';
    html += '<pre class="ocr-full-text">' + _esc(data.translated_text) + '</pre>';
    html += '</div>';
  }

  display.innerHTML = html;
}

/* ------------------------------------------------------------------ */
/* Export                                                               */
/* ------------------------------------------------------------------ */

export function bindExportBtns(fileId: number): void {
  const panel = document.getElementById(`ocrResultPanel-${fileId}`);
  if (!panel) return;
  panel.querySelectorAll<HTMLButtonElement>('.ocr-btn-export').forEach(btn => {
    btn.addEventListener('click', () => {
      const fmt = btn.dataset.fmt || 'md';
      const fid = btn.dataset.fid || String(fileId);
      // Export with translation if translation is being displayed
      const transDisplay = document.getElementById(`ocrTranslationDisplay-${fileId}`);
      const langSel = document.getElementById(`ocrTargetLang-${fileId}`) as HTMLSelectElement | null;
      let url = `/api/ocr/export/${encodeURIComponent(fid)}?format=${encodeURIComponent(fmt)}`;
      const hasTranslation = transDisplay
        && transDisplay.style.display !== 'none'
        && transDisplay.innerHTML.trim() !== '';
      if (hasTranslation) {
        url += '&include_translation=1';
        if (langSel?.value) url += '&target_lang=' + encodeURIComponent(langSel.value);
      }
      window.open(url, '_blank');
    });
  });
}

/* ------------------------------------------------------------------ */
/* Overlay                                                             */
/* ------------------------------------------------------------------ */

export function bindOverlayBtn(fileId: number): void {
  const btn = document.getElementById(`ocrOverlayBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', () => {
    const modeSel = document.getElementById(`ocrOverlayMode-${fileId}`) as HTMLSelectElement | null;
    const mode = modeSel?.value || 'original';
    const langSel = document.getElementById(`ocrTargetLang-${fileId}`) as HTMLSelectElement | null;
    const lang = langSel?.value || '';
    const taskSel = document.getElementById(`ocrTask-${fileId}`) as HTMLSelectElement | null;
    const task = taskSel?.value || '';
    let url = `/api/ocr/overlay/${fileId}?mode=${encodeURIComponent(mode)}&format=png`;
    if (lang) url += `&target_lang=${encodeURIComponent(lang)}`;
    if (task) url += `&task=${encodeURIComponent(task)}`;
    window.open(url, '_blank');
  });
}
