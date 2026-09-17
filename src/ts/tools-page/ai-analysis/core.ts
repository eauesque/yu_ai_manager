/**
 * ai-analysis/core.ts -- Entry point: initialization, config loading.
 * Re-exports config, connection, batch/trends, and type functions for
 * external consumers.
 */

import { apiFetch } from '../api';
import * as render from './render';
import { _t, getConfigLoaded, setConfigLoaded, getIsLocalEngine, setIsLocalEngine } from './helpers';
import { onAiEngineChange, saveAiConfig as _saveAiConfigImpl, setUpdateBatchButtonCallback } from './config';
import { loadOllamaModels, loadOpenaiCompatModels, checkHailoStatus } from './connections';
import {
  loadAiServers, getHasServers,
  renderBatchServerCheckboxes,
} from './servers';
import type { AiConfig, AiStats } from './types';

// Re-export types
export type { TrendHistoryItem } from './types';

// Re-export for external consumers (tools-page/index.ts, render.ts, window-bridges.ts)
export { onAiEngineChange } from './config';
export { loadOllamaModels, testOllamaConnection, loadOpenaiCompatModels, testOpenaiCompatConnection, checkHailoStatus } from './connections';
export {
  loadAiServers,
  aisActivate, aisTest, aisRemove, aisToggleEnabled,
  aisMigrateFromLegacy, aisRegisterDiscovered, aisTestDiscovered, aisMatchDiscovered, aisUnmatchDiscovered, aisIgnoreDiscovered, aisUnignoreDiscovered, aisShowAddDialog, aisShowEditDialog,
  aisOnTypeChange, aisSaveDialog, aisRefreshModels,
  renderBatchServerCheckboxes, getSelectedBatchServerIds,
} from './servers';

// Re-export batch/trends functions
export { analyzePromptTrends, cancelAiBatch, loadTrendHistory, deleteTrendHistoryEntry, onFallbackLocalOnlyChange } from './batch-trends';
import { analyzeCurrentBatch as _analyzeCurrentBatchImpl } from './batch-trends';

/* ------------------------------------------------------------------ */
/* Batch button & scan-root helpers                                    */
/* ------------------------------------------------------------------ */

function _updateBatchButton(): void {
  const btn = document.getElementById('aiBatchBtn');
  if (!btn) return;
  const span = btn.querySelector('span[data-i18n]');
  if (!span) return;
  span.setAttribute('data-i18n', 'tools.batch_analyze');
  span.textContent = _t('tools.batch_analyze', 'Batch Analysis');

  // Default to all items for local engine, 10 for cloud
  const limitSel = document.getElementById('aiBatchLimit') as HTMLSelectElement | null;
  const noteEl = document.getElementById('aiBatchLimitNote');
  if (limitSel && !getConfigLoaded()) {
    // Set default value only on initial load
    limitSel.value = getIsLocalEngine() ? '0' : '10';
  }
  if (noteEl) {
    noteEl.textContent = getIsLocalEngine()
      ? _t('tools.ai_local_engine_note', '(local engine)')
      : '';
  }
}

// Wire up the callback so config.ts can trigger batch button update
setUpdateBatchButtonCallback(_updateBatchButton);

async function _loadScanRootsForBatch(): Promise<void> {
  const sel = document.getElementById('aiBatchRoot') as HTMLSelectElement | null;
  if (!sel) return;
  try {
    const res = await apiFetch('/api/scan-roots');
    const data: { roots: Array<{ path: string; enabled?: boolean }> } = await res.json();
    // Keep the first "All folders" option, clear the rest
    while (sel.options.length > 1) sel.remove(1);
    for (const root of data.roots) {
      if (root.enabled === false) continue;
      const opt = document.createElement('option');
      opt.value = root.path;
      opt.textContent = root.path;
      sel.appendChild(opt);
    }
  } catch {
    // silently ignore
  }
}

/* ------------------------------------------------------------------ */
/* Config load                                                         */
/* ------------------------------------------------------------------ */

export async function loadAiConfig(options: { probeConnections?: boolean } = {}): Promise<void> {
  const { probeConnections = false } = options;
  try {
    const res = await apiFetch('/api/analysis/config');
    const data: AiConfig = await res.json();

    const engineEl = document.getElementById('aiEngine') as HTMLSelectElement | null;
    if (data.engine && engineEl) engineEl.value = data.engine;
    const keyStatusEl = document.getElementById('aiKeyStatus');
    if (data.api_key && keyStatusEl) {
      keyStatusEl.textContent =
        '\u2705 ' +
        _t('tools.api_key_set', 'API key set') +
        ` (${data.api_key})`;
    }
    // Restore Claude model
    const claudeModelEl = document.getElementById('claudeModel') as HTMLSelectElement | null;
    if (data.model && claudeModelEl) claudeModelEl.value = data.model;
    // Restore OpenAI fields
    const openaiKeyStatusEl = document.getElementById('openaiKeyStatus');
    if (data.openai_api_key && openaiKeyStatusEl) {
      openaiKeyStatusEl.textContent =
        '\u2705 ' +
        _t('tools.api_key_set', 'API key set') +
        ` (${data.openai_api_key})`;
    }
    const openaiModelEl = document.getElementById('openaiModel') as HTMLSelectElement | null;
    if (data.openai_model && openaiModelEl) openaiModelEl.value = data.openai_model;
    // Restore OpenAI Compatible fields
    const compatUrlEl = document.getElementById('openaiCompatUrl') as HTMLInputElement | null;
    if (data.openai_compat_url && compatUrlEl) compatUrlEl.value = data.openai_compat_url;
    const compatKeyStatusEl = document.getElementById('openaiCompatKeyStatus');
    if (data.openai_compat_api_key && compatKeyStatusEl) {
      compatKeyStatusEl.textContent =
        '\u2705 ' +
        _t('tools.api_key_set', 'API key set') +
        ` (${data.openai_compat_api_key})`;
    }
    const compatModelEl = document.getElementById('openaiCompatModel') as HTMLSelectElement | null;
    if (data.openai_compat_model && compatModelEl) {
      let found = false;
      for (const opt of Array.from(compatModelEl.options)) {
        if (opt.value === data.openai_compat_model) { found = true; break; }
      }
      if (!found) {
        const opt = document.createElement('option');
        opt.value = data.openai_compat_model;
        opt.textContent = data.openai_compat_model;
        compatModelEl.appendChild(opt);
      }
      compatModelEl.value = data.openai_compat_model;
    }
    // Restore Ollama fields
    const ollamaUrlEl = document.getElementById('ollamaUrl') as HTMLInputElement | null;
    if (data.ollama_url && ollamaUrlEl) ollamaUrlEl.value = data.ollama_url;
    const ollamaModelEl = document.getElementById('ollamaModel') as HTMLSelectElement | null;
    if (data.ollama_model && ollamaModelEl) {
      // Ensure the option exists before selecting
      let found = false;
      for (const opt of Array.from(ollamaModelEl.options)) {
        if (opt.value === data.ollama_model) { found = true; break; }
      }
      if (!found) {
        const opt = document.createElement('option');
        opt.value = data.ollama_model;
        opt.textContent = data.ollama_model;
        ollamaModelEl.appendChild(opt);
      }
      ollamaModelEl.value = data.ollama_model;
    }
    // Restore fallback_local_only checkbox
    const localOnlyEl = document.getElementById('aiFallbackLocalOnly') as HTMLInputElement | null;
    if (localOnlyEl) localOnlyEl.checked = !!data.fallback_local_only;
    // Restore language selection
    const langEl = document.getElementById('aiAnalysisLanguage') as HTMLSelectElement | null;
    if (langEl && data.language) langEl.value = data.language;

    // Load server registry and toggle legacy config visibility
    await loadAiServers();
    const legacyCfg = document.getElementById('aiLegacyConfig');
    if (legacyCfg) {
      legacyCfg.style.display = getHasServers() ? 'none' : '';
    }
    // Render batch server checkboxes
    const batchServersCont = document.getElementById('aiBatchServers');
    if (batchServersCont) {
      renderBatchServerCheckboxes(batchServersCont);
    }

    setIsLocalEngine(!!data.is_local);
    onAiEngineChange();
    // Register URL input listener once (re-evaluate hailo-ollama warning on URL change)
    if (!getConfigLoaded()) {
      const compatUrlInput = document.getElementById('openaiCompatUrl');
      if (compatUrlInput) {
        compatUrlInput.addEventListener('input', () => { onAiEngineChange(); });
      }
    }
    setConfigLoaded(true);
    _updateBatchButton();
    _loadScanRootsForBatch();
    // Avoid network/device probes during passive page load.
    // Users can trigger them explicitly via the existing test controls.
    if (probeConnections) {
      if (data.engine === 'openai_compat') {
        loadOpenaiCompatModels();
      }
      if (data.engine === 'ollama') {
        loadOllamaModels();
      }
      if (data.engine === 'hailo_vlm') {
        checkHailoStatus();
      }
    }

    const statsRes = await apiFetch('/api/analysis/stats');
    const stats: AiStats = await statsRes.json();
    const el = document.getElementById('aiStats');
    render.renderAiStats(el, stats);
  } catch {
    // silently ignore config load failures
  }
}

/* ------------------------------------------------------------------ */
/* Save config (wrapper preserving original no-arg signature)          */
/* ------------------------------------------------------------------ */

export async function saveAiConfig(): Promise<void> {
  return _saveAiConfigImpl(loadAiConfig);
}

/* ------------------------------------------------------------------ */
/* Batch analysis (wrapper passing loadAiConfig callback)              */
/* ------------------------------------------------------------------ */

export async function analyzeCurrentBatch(): Promise<void> {
  return _analyzeCurrentBatchImpl(loadAiConfig);
}
