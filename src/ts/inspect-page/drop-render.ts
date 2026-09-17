/**
 * Inspect page — file handler + result renderer.
 * Main module: orchestrates drop-zone (leaf) and rendering logic.
 */

import {
  type InspectData,
  initDropZone as _initDropZone,
  renderZipSelector,
  hideZipSelector,
  setLastZipFile,
  _t,
} from './drop-zone';
import { createPagePerfTracker } from '../shared/page-perf';
import {
  copyRawMeta as copyRawMetaHelper,
  esc,
  initCopyB64Handler,
  openInSimulator as openInSimulatorHelper,
  renderInspectCharGrid as renderInspectCharGridHelper,
  renderInspectCharacterPrompts as renderInspectCharacterPromptsHelper,
} from './drop-render-helpers';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

// Re-export types and helpers consumed by other modules
export type { InspectData };

/** Module-level state for the last inspected data (used by openInSimulator). */
let _lastInspectData: InspectData | null = null;

/** Accessor for the last inspected data (used by OCR handler in index.ts). */
export function getLastInspectData(): InspectData | null {
  return _lastInspectData;
}
const _perf = createPagePerfTracker('inspect');
_perf.markOnce('module_ready');
let _metaRendererPromise: Promise<typeof import('../meta-renderer/core')> | null = null;
let _characterGridPromise: Promise<typeof import('../runtime-init/novelai/character-grid')> | null = null;
let _characterParsePromise: Promise<typeof import('../runtime-init/novelai/character-parse')> | null = null;
let _characterRenderPromise: Promise<typeof import('../runtime-init/novelai/character-render')> | null = null;

function _loadMetaRenderer(): Promise<typeof import('../meta-renderer/core')> {
  if (!_metaRendererPromise) _metaRendererPromise = import('../meta-renderer/core');
  return _metaRendererPromise;
}

function _loadCharacterGrid(): Promise<typeof import('../runtime-init/novelai/character-grid')> {
  if (!_characterGridPromise) _characterGridPromise = import('../runtime-init/novelai/character-grid');
  return _characterGridPromise;
}

function _loadCharacterParse(): Promise<typeof import('../runtime-init/novelai/character-parse')> {
  if (!_characterParsePromise) _characterParsePromise = import('../runtime-init/novelai/character-parse');
  return _characterParsePromise;
}

function _loadCharacterRender(): Promise<typeof import('../runtime-init/novelai/character-render')> {
  if (!_characterRenderPromise) _characterRenderPromise = import('../runtime-init/novelai/character-render');
  return _characterRenderPromise;
}

// ─── Drop zone wrapper ──────────────────────────────────────────

/**
 * Initialise drop zone with handleFile wired as the file callback.
 * Re-exported under the original name so index.ts is unchanged.
 */
export function initDropZone(): void {
  _initDropZone((file, zipEntry) => handleFile(file, zipEntry));
}

// ─── File handler ────────────────────────────────────────────────

export async function handleFile(file: File, zipEntry?: string): Promise<void> {
  if (!file) return;

  const isZip = file.name.toLowerCase().endsWith('.zip');

  // Preview
  const previewImg = document.getElementById('previewImg') as HTMLImageElement | null;
  if (previewImg) {
    previewImg.src = isZip ? '' : URL.createObjectURL(file);
  }

  const fileInfoEl = document.getElementById('fileInfo');
  if (fileInfoEl) {
    fileInfoEl.textContent =
      file.name + ' (' + (file.size / 1024).toFixed(1) + ' KB)' + (zipEntry ? ' \u2014 ' + zipEntry : '');
  }

  const resultArea = document.getElementById('resultArea');
  const loadingArea = document.getElementById('loadingArea');
  if (resultArea) resultArea.style.display = 'none';
  if (loadingArea) loadingArea.style.display = 'block';

  try {
    _perf.markOnce('inspect_started');
    const formData = new FormData();
    formData.append('file', file);
    if (zipEntry) formData.append('zip_entry', zipEntry);

    const res = await fetch('/api/inspect', { method: 'POST', headers: XHR_HEADERS, body: formData });
    const data: InspectData = await res.json();

    // ZIP: show image selector
    if (data.zip_images && data.zip_images.length > 0) {
      setLastZipFile(file);
      renderZipSelector(data.zip_images, data.zip_current);
    } else {
      setLastZipFile(null);
      hideZipSelector();
    }

    await renderResult(data);
    _perf.markOnce('result_ready');
  } catch (err: unknown) {
    const metaPanel = document.getElementById('metaPanel');
    if (metaPanel) {
      const message = err instanceof Error ? err.message : String(err);
      metaPanel.innerHTML =
        '<div style="color:#e74c3c;">' + _t('inspect.parse_error', 'Parse error') + ': ' + esc(message) + '</div>';
    }
  }

  if (loadingArea) loadingArea.style.display = 'none';
  if (resultArea) resultArea.style.display = 'block';
}

// ─── Result renderer ─────────────────────────────────────────────

async function renderResult(data: InspectData): Promise<void> {
  const panel = document.getElementById('metaPanel');
  if (!panel) return;

  if (data.error) {
    panel.innerHTML = '<div style="color:#e74c3c;">' + _t('inspect.error', 'Error') + ': ' + esc(data.error) + '</div>';
    return;
  }

  _lastInspectData = data;
  const { renderMetaInfo } = await _loadMetaRenderer();

  panel.innerHTML = renderMetaInfo(data, {
    mode: 'inspect',
    showCopyButtons: true,
    showConvertButtons: true,
    showTagSearch: false,
    showSimulatorLink: true,
    convertApiNs: 'inspectPageApi',
  });

  // Character prompts section (same as detail modal)
  await renderInspectCharacterPromptsHelper(panel, data, _loadCharacterRender, _loadCharacterParse);

  // Raw metadata
  const raw = data.raw_metadata || {};
  const rawMetaEl = document.getElementById('rawMeta');
  if (rawMetaEl) rawMetaEl.textContent = JSON.stringify(raw, null, 2);

  // Character position grid overlay for NAI V4
  await renderInspectCharGridHelper(data, _loadCharacterGrid);

  // Show OCR section only when file is in DB (has id)
  const ocrSection = document.getElementById('ocrSection');
  if (ocrSection) {
    ocrSection.style.display = typeof data.id === 'number' ? 'block' : 'none';
  }
  // Reset OCR result on new file load
  const ocrResult = document.getElementById('ocrResult');
  const ocrError = document.getElementById('ocrError');
  if (ocrResult) ocrResult.style.display = 'none';
  if (ocrError) ocrError.style.display = 'none';
}

export function copyRawMeta(): void {
  copyRawMetaHelper(_t);
}

export { initCopyB64Handler };

// ─── Open in Simulator ───────────────────────────────────────────

export function openInSimulator(which: string): void {
  openInSimulatorHelper(_lastInspectData, which);
}
