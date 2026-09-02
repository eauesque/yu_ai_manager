/**
 * tools/analysis.ts -- AI image analysis: run, engine selection,
 * and load saved results.
 *
 * Display/rendering logic is in analysis-display.ts.
 */

import { showAiTabBadge } from '../../detail-modal/tabs/modal-tabs';
import { getAppApi } from '../../shared/browser-apis';
import {
  AnalysisResult,
  displayAnalysisResult,
  displayMultipleResults,
} from './analysis-display';

// Re-export display functions for external consumers
export { displayAnalysisResult } from './analysis-display';
export type { AnalysisResult } from './analysis-display';

const _VIDEO_EXTS = new Set(['.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv', '.flv', '.ts']);
const _AUDIO_EXTS = new Set(['.mp3', '.wav', '.flac', '.ogg', '.m4a', '.aac', '.wma', '.opus']);
const { apiFetch, tr } = getAppApi();

function _detectFileExt(fileId: number): string {
  const footer = document.querySelector('.meta-footer');
  if (!footer) return '';
  const path = footer.childNodes[0]?.textContent?.trim() || '';
  const dot = path.lastIndexOf('.');
  return dot >= 0 ? path.slice(dot).toLowerCase() : '';
}

export async function analyzeCurrentImage(fileId: number): Promise<void> {
  const status = document.getElementById(`aiAnalysisStatus-${fileId}`);
  const panel = document.getElementById(`aiAnalysisPanel-${fileId}`);
  const modeSelect = document.getElementById(`aiAnalysisMode-${fileId}`) as HTMLSelectElement | null;
  const engineSelect = document.getElementById(`aiEngineSelect-${fileId}`) as HTMLSelectElement | null;
  const modelSelect = document.getElementById(`aiModelSelect-${fileId}`) as HTMLSelectElement | null;
  const mode = modeSelect?.value || 'full';
  const engine = engineSelect?.value || '';
  const model = modelSelect?.value || '';
  if (status) status.textContent = tr('analysis.status_running');

  const ext = _detectFileExt(fileId);
  const isVideo = _VIDEO_EXTS.has(ext);
  const isAudio = _AUDIO_EXTS.has(ext);

  try {
    let url: string;
    let body: Record<string, unknown>;

    if (isVideo) {
      // Video: run multi-keyframe analysis + audio transcription in parallel
      url = `/api/video-analysis/analyze/${fileId}`;
      body = {};
      if (engine) body.engine = engine;
      if (model) body.model = model;
    } else if (isAudio) {
      // Audio: Whisper transcription
      url = `/api/audio-analysis/transcribe/${fileId}`;
      body = {};
    } else {
      // Image: standard image analysis
      url = `/api/analysis/analyze/${fileId}`;
      body = { mode };
      if (engine) body.engine = engine;
      if (model) body.model = model;
    }

    // For video, run video analysis and audio transcription in parallel
    const requests: Promise<Response>[] = [
      apiFetch(url, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      }),
    ];
    if (isVideo) {
      requests.push(
        apiFetch(`/api/audio-analysis/transcribe/${fileId}`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({}),
        }).catch(() => new Response(JSON.stringify({ error: 'Audio transcription unavailable' }))),
      );
    }

    const responses = await Promise.all(requests);
    const res = responses[0];
    const data = await res.json();
    if (data.error) {
      if (status) status.textContent = tr('analysis.status_error', { error: data.error });
      return;
    }
    const engineName = data.engine || '';
    if (status) {
      status.textContent = engineName
        ? tr('analysis.status_done_engine', { engine: engineName })
        : tr('analysis.status_done');
    }
    // After analysis, reload and display all results
    await loadSavedAnalysis(fileId);
    _updateAnalyzeButton(fileId, true);
    showAiTabBadge();
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    if (status) status.textContent = tr('analysis.status_error', { error: message });
  }
}

function _updateAnalyzeButton(fileId: number, hasSaved: boolean): void {
  const btn = document.getElementById(`aiAnalyzeBtn-${fileId}`);
  if (!btn) return;
  const label = hasSaved
    ? tr('analysis.btn_reanalyze')
    : tr('result.ai_analysis');
  btn.textContent = label;
}

/* ------------------------------------------------------------------ */
/* Engine dropdown                                                     */
/* ------------------------------------------------------------------ */

interface EngineInfo {
  type: string;
  label: string;
  model: string;
  models?: string[];
}

let _enginesCache: EngineInfo[] | null = null;

/**
 * Fetch available engines with session-level caching.
 * Engine availability does not change during a session, so we only
 * fetch once and return the cached result on subsequent calls.
 */
async function _fetchAvailableEngines(): Promise<EngineInfo[]> {
  if (_enginesCache) return _enginesCache;
  try {
    const res = await apiFetch('/api/analysis/available-engines');
    const data = await res.json();
    _enginesCache = data.engines || [];
    return _enginesCache!;
  } catch {
    return _enginesCache || [];
  }
}

/** Update the model dropdown when the engine selection changes */
function _updateModelSelect(fileId: number, engines: EngineInfo[]): void {
  const engineSel = document.getElementById(`aiEngineSelect-${fileId}`) as HTMLSelectElement | null;
  const modelSel = document.getElementById(`aiModelSelect-${fileId}`) as HTMLSelectElement | null;
  if (!engineSel || !modelSel) return;

  const engineType = engineSel.value;
  const engine = engines.find(e => e.type === engineType);
  const models = engine?.models || [];

  // Only show when there are 2 or more models
  modelSel.innerHTML = '';
  if (models.length >= 2) {
    for (const m of models) {
      const opt = document.createElement('option');
      opt.value = m;
      opt.textContent = m;
      if (m === engine?.model) opt.selected = true;
      modelSel.appendChild(opt);
    }
    modelSel.style.display = '';
  } else {
    modelSel.style.display = 'none';
  }
}

export async function populateEngineSelect(fileId: number): Promise<void> {
  const sel = document.getElementById(`aiEngineSelect-${fileId}`) as HTMLSelectElement | null;
  if (!sel) return;
  const engines = await _fetchAvailableEngines();
  // Keep the Auto option, only remove existing dynamic options
  while (sel.options.length > 1) sel.remove(1);
  for (const e of engines) {
    const opt = document.createElement('option');
    opt.value = e.type;
    opt.textContent = e.label;
    sel.appendChild(opt);
  }
  // Update model list when engine changes
  sel.addEventListener('change', () => _updateModelSelect(fileId, engines));
  // Reflect initial state (hide model select when Auto is selected)
  _updateModelSelect(fileId, engines);
}

/* ------------------------------------------------------------------ */
/* Load saved analysis                                                 */
/* ------------------------------------------------------------------ */

/** Monotonic counter -- incremented on each call so stale fetches are discarded. */
let _loadSeq = 0;

export async function loadSavedAnalysis(fileId: number): Promise<void> {
  const seq = ++_loadSeq;
  // Load engine dropdown asynchronously in parallel
  populateEngineSelect(fileId);
  await _loadSavedAnalysisOnce(fileId, seq);
}

async function _loadSavedAnalysisOnce(fileId: number, seq: number, retry = true): Promise<void> {
  try {
    const res = await apiFetch(`/api/analysis/result/${fileId}`);
    if (seq !== _loadSeq) return; // stale -- user navigated away
    // On 429, silently give up -- retrying would worsen the rate-limit storm
    if (res.status === 429) return;
    const data = await res.json();
    if (data.found) {
      const panel = document.getElementById(`aiAnalysisPanel-${fileId}`);
      const status = document.getElementById(`aiAnalysisStatus-${fileId}`);
      const results: AnalysisResult[] = data.results || [data.result];
      if (panel) {
        displayMultipleResults(panel, results);
        panel.classList.remove('meta-panel-hidden');
      }
      if (status) {
        const count = results.length;
        const latest = results[0];
        status.textContent = count > 1
          ? `${count} analyses`
          : tr('analysis.status_saved', {
              engine: latest.engine || tr('analysis.done_label'),
            });
      }
      _updateAnalyzeButton(fileId, true);
      showAiTabBadge();
    }
  } catch (e) {
    // Retry once after 500ms (handles transient DB lock / network errors)
    if (retry && seq === _loadSeq) {
      await new Promise(r => setTimeout(r, 500));
      if (seq !== _loadSeq) return;
      return _loadSavedAnalysisOnce(fileId, seq, false);
    }
    console.warn('[loadSavedAnalysis] failed for file', fileId, e);
  }
}
