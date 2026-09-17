/**
 * Inspect page entry point.
 * Bundles: drop-render + theme.
 * Replaces 2 individual <script> tags with one bundled IIFE.
 */

import { initDropZone, handleFile, copyRawMeta, initCopyB64Handler, openInSimulator, getLastInspectData } from './drop-render';
import { initInspectTheme } from './theme';
import { installWindowApi } from '../shared/window-api';
import { copyToClipboard } from '../shared/clipboard';
import { runOcrJob } from '../shared/ocr-job';

// Self-init: set up drop zone, copy handler, theme
initDropZone();
initCopyB64Handler();
initInspectTheme();

function handleFileInput(el: HTMLElement): void {
  const input = el as HTMLInputElement | null;
  const file = input?.files?.[0];
  if (!file) return;
  void handleFile(file);
}

function triggerFileInput(): void {
  const input = document.getElementById('fileInput') as HTMLInputElement | null;
  if (input) input.click();
}

function runOcr(): void {
  const data = getLastInspectData();
  const fileId = typeof data?.id === 'number' ? data.id : null;
  if (!fileId) return;
  const taskSelect = document.getElementById('ocrTaskSelect') as HTMLSelectElement | null;
  const task = taskSelect?.value || 'ocr';
  const loadingEl = document.getElementById('ocrLoading');
  const resultEl = document.getElementById('ocrResult');
  const errorEl = document.getElementById('ocrError');
  const textEl = document.getElementById('ocrText');
  const engineEl = document.getElementById('ocrEngineLabel');
  if (loadingEl) loadingEl.style.display = 'block';
  if (resultEl) resultEl.style.display = 'none';
  if (errorEl) errorEl.style.display = 'none';
  // 202 + poll: the route runs OCR as a job rather than holding the request
  // open for the length of a VLM call.
  runOcrJob(fetch, `/api/ocr/${fileId}`, { task })
    .then(() => fetch(`/api/ocr/result/${fileId}?task=${task}`))
    .then((r) => r.json())
    .then((raw: unknown) => {
      const res = (raw as { data?: Record<string, unknown> }).data || (raw as Record<string, unknown>);
      if (loadingEl) loadingEl.style.display = 'none';
      if ((res as { error?: string }).error) {
        if (errorEl) { errorEl.textContent = String((res as { error?: string }).error); errorEl.style.display = 'block'; }
        return;
      }
      if (textEl) textEl.textContent = String((res as { full_text?: string; text?: string }).full_text
        || (res as { text?: string }).text || '');
      if (engineEl) engineEl.textContent = String((res as { engine?: string }).engine || '');
      if (resultEl) resultEl.style.display = 'block';
    })
    .catch((err: unknown) => {
      if (loadingEl) loadingEl.style.display = 'none';
      const msg = err instanceof Error ? err.message : String(err);
      if (errorEl) { errorEl.textContent = msg; errorEl.style.display = 'block'; }
    });
}

function copyOcrText(): void {
  const textEl = document.getElementById('ocrText');
  if (!textEl) return;
  void copyToClipboard(textEl.textContent || '');
}

installWindowApi('inspectPageApi', {
  handleFileInput,
  copyRawMeta,
  openInSimulator,
  triggerFileInput,
  runOcr,
  copyOcrText,
});

// Bridge: onZipEntryChange is now handled internally via addEventListener,
// but we keep handleFile exposed for any external callers.
