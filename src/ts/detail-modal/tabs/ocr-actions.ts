/**
 * ocr-actions.ts -- OCR button bindings, result display, and bbox detection.
 *
 * Translation, export, and overlay handlers are in ocr-export.ts.
 */

import { _esc, OcrData } from './ocr-types';
import { getAppApi } from '../../shared/browser-apis';
import { runOcrJob } from '../../shared/ocr-job';

// Re-export from ocr-export for backward compatibility
export {
  bindTranslateBtn,
  bindExportBtns,
  bindOverlayBtn,
} from './ocr-export';

/* ------------------------------------------------------------------ */
/* Load existing results                                               */
/* ------------------------------------------------------------------ */

export async function loadExistingResult(fileId: number): Promise<void> {
  try {
    const resp = await getAppApi().apiFetch(`/api/ocr/result/${fileId}`);
    if (!resp.ok) return;
    const json = await resp.json();
    const data = json.data || json;
    if (data.full_text) {
      showOcrResult(fileId, data);
      loadExistingTranslations(fileId);
    }
  } catch {
    // Do nothing if no OCR results
  }
}

async function loadExistingTranslations(fileId: number): Promise<void> {
  try {
    const { showTranslationResult } = await import('./ocr-export');
    const resp = await getAppApi().apiFetch(`/api/ocr/translations/${fileId}`);
    if (!resp.ok) return;
    const json = await resp.json();
    const data = json.data || json;
    const translations = data.translations || [];
    if (translations.length > 0) {
      showTranslationResult(fileId, translations[0]);
    }
  } catch {
    // Skip if no translation
  }
}

/* ------------------------------------------------------------------ */
/* OCR execution                                                       */
/* ------------------------------------------------------------------ */

export function bindRunBtn(fileId: number): void {
  const btn = document.getElementById(`ocrRunBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const taskSel = document.getElementById(`ocrTask-${fileId}`) as HTMLSelectElement | null;
    const task = taskSel?.value || 'ocr';
    const status = document.getElementById(`ocrStatus-${fileId}`);

    btn.setAttribute('disabled', 'true');
    btn.setAttribute('aria-disabled', 'true');
    if (status) status.textContent = 'Processing...';

    try {
      // PDF uses dedicated endpoint, others use generic endpoint
      const apiUrl = task === 'ocr_pdf'
        ? `/api/ocr/pdf/${fileId}`
        : `/api/ocr/${fileId}`;
      const apiTask = task === 'ocr_pdf' ? 'ocr_document' : task;

      // The route answers 202 and runs the work as a job: OCR of a PDF or a
      // long page can outlast any reasonable request timeout, so the result
      // arrives by polling rather than in the response body.
      await runOcrJob(
        (url, init) => getAppApi().apiFetch(url, init),
        apiUrl,
        { task: apiTask },
        {
          onProgress: (job) => {
            if (!status) return;
            status.textContent = job.percent != null
              ? `Processing… ${Math.round(job.percent)}%`
              : (job.message || 'Processing…');
          },
        },
      );
      if (status) status.textContent = '';

      // The job result deliberately carries no text — /api/jobs/{id} has no
      // authorization — so the recognised text is read from the admin-gated
      // result endpoint.
      const resultResp = await getAppApi().apiFetch(`/api/ocr/result/${fileId}?task=${apiTask}`);
      const resultJson = await resultResp.json();
      showOcrResult(fileId, resultJson.data || resultJson);
      _showOcrBadge();
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (status) status.textContent = msg;
    } finally {
      btn.removeAttribute('disabled');
      btn.removeAttribute('aria-disabled');
    }
  });
}

/* ------------------------------------------------------------------ */
/* Results display                                                     */
/* ------------------------------------------------------------------ */

export function showOcrResult(fileId: number, data: OcrData): void {
  const panel = document.getElementById(`ocrResultPanel-${fileId}`);
  if (!panel) return;
  panel.style.display = 'block';

  // Header
  const header = document.getElementById(`ocrResultHeader-${fileId}`);
  if (header) {
    header.innerHTML =
      '<span class="ocr-engine-badge">' + _esc(data.engine || 'unknown') + '</span> ' +
      '<span class="ocr-task-badge">' + _esc(data.task) + '</span> ' +
      (data.language ? '<span class="ocr-lang-badge">' + _esc(data.language) + '</span>' : '') +
      (data.regions?.length ? ' <span class="ocr-region-count">' + data.regions.length + ' regions</span>' : '');
  }

  // Text display
  const textDisplay = document.getElementById(`ocrTextDisplay-${fileId}`);
  if (!textDisplay) return;

  if (data.regions && data.regions.length > 0) {
    let hasBbox = false;
    let html = '<div class="ocr-regions">';
    for (const r of data.regions) {
      const labelCls = r.label ? ' ocr-region--' + r.label.replace(/[^a-z_]/g, '') : '';
      html += '<div class="ocr-region' + labelCls + '">';
      if (r.label) {
        html += '<span class="ocr-region-label">' + _esc(r.label) + '</span>';
      }
      if (r.bbox && r.bbox.length >= 4 && r.bbox[2] > 0) {
        html += '<span class="ocr-region-bbox" title="' + r.bbox.join(', ') + '">\u25A1</span>';
        hasBbox = true;
      }
      if (r.direction === 'vertical') {
        html += '<span class="ocr-region-dir">\u2195</span>';
      }
      html += '<div class="ocr-region-text">' + _esc(r.text) + '</div>';
      if (r.confidence > 0) {
        html += '<span class="ocr-confidence">' + Math.round(r.confidence * 100) + '%</span>';
      }
      html += '</div>';
    }
    html += '</div>';
    textDisplay.innerHTML = html;
    // Show Detect button if regions with undetected bboxes exist
    const bboxBtn = document.getElementById(`ocrBboxBtn-${fileId}`);
    if (bboxBtn) {
      bboxBtn.style.display = hasBbox ? 'none' : '';
    }
  } else {
    textDisplay.innerHTML = '<pre class="ocr-full-text">' + _esc(data.full_text) + '</pre>';
  }
}

function _showOcrBadge(): void {
  const badge = document.querySelector('.mi-tab-badge-ocr');
  if (badge) (badge as HTMLElement).style.display = '';
}

/* ------------------------------------------------------------------ */
/* Bbox detection                                                      */
/* ------------------------------------------------------------------ */

export function bindBboxBtn(fileId: number): void {
  const btn = document.getElementById(`ocrBboxBtn-${fileId}`);
  if (!btn) return;
  btn.addEventListener('click', async () => {
    const status = document.getElementById(`ocrStatus-${fileId}`);
    btn.setAttribute('disabled', 'true');
    btn.setAttribute('aria-disabled', 'true');
    if (status) status.textContent = 'Detecting positions...';

    try {
      const resp = await getAppApi().apiFetch(`/api/ocr/bbox/${fileId}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      const json = await resp.json();
      if (!resp.ok) {
        throw new Error(json.error || 'bbox detection failed');
      }
      const data = json.data || json;
      if (status) status.textContent = `${data.detected_bboxes}/${data.total_regions} located`;

      // Re-fetch and display updated results
      const resultResp = await getAppApi().apiFetch(`/api/ocr/result/${fileId}`);
      const resultJson = await resultResp.json();
      showOcrResult(fileId, resultJson.data || resultJson);
    } catch (e: unknown) {
      const msg = e instanceof Error ? e.message : String(e);
      if (status) status.textContent = msg;
    } finally {
      btn.removeAttribute('disabled');
      btn.removeAttribute('aria-disabled');
    }
  });
}
