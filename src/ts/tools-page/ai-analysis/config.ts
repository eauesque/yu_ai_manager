/**
 * ai-analysis/config.ts -- AI engine config load/save and engine switching.
 */

import { apiFetch } from '../api';
import { _t, _isPrivateUrl, getConfigLoaded, setIsLocalEngine } from './helpers';
import { loadOllamaModels, loadOpenaiCompatModels, checkHailoStatus } from './connections';

/** Update UI section visibility and local-engine flag based on selected engine. */
export function onAiEngineChange(): void {
  const engineEl = document.getElementById('aiEngine') as HTMLSelectElement | null;
  const engine = engineEl?.value || '';
  const apiSection = document.getElementById('aiApiKeySection');
  const openaiSection = document.getElementById('aiOpenaiSection');
  const openaiCompatSection = document.getElementById('aiOpenaiCompatSection');
  const ollamaSection = document.getElementById('aiOllamaSection');
  const hailoSection = document.getElementById('aiHailoSection');
  if (apiSection) apiSection.style.display = engine === 'claude_api' ? '' : 'none';
  if (openaiSection) openaiSection.style.display = engine === 'openai' ? '' : 'none';
  if (openaiCompatSection) openaiCompatSection.style.display = engine === 'openai_compat' ? '' : 'none';
  if (ollamaSection) ollamaSection.style.display = engine === 'ollama' ? '' : 'none';
  if (hailoSection) hailoSection.style.display = engine === 'hailo_vlm' ? '' : 'none';

  // Show/hide hailo-ollama warning in OpenAI Compatible section
  const hailoWarnEl = document.getElementById('openaiCompatHailoWarn');
  if (hailoWarnEl) {
    if (engine === 'openai_compat') {
      const url = (document.getElementById('openaiCompatUrl') as HTMLInputElement)?.value.trim() || '';
      hailoWarnEl.style.display = (url.includes(':8000') || url.toLowerCase().includes('hailo')) ? '' : 'none';
    } else {
      hailoWarnEl.style.display = 'none';
    }
  }

  // Update local engine flag based on current UI state
  if (engine === 'hailo_vlm') {
    setIsLocalEngine(true);
  } else if (engine === 'ollama') {
    const url = (document.getElementById('ollamaUrl') as HTMLInputElement | null)?.value.trim() || '';
    setIsLocalEngine(_isPrivateUrl(url));
  } else if (engine === 'openai_compat') {
    const url = (document.getElementById('openaiCompatUrl') as HTMLInputElement | null)?.value.trim() || '';
    setIsLocalEngine(_isPrivateUrl(url));
  } else {
    setIsLocalEngine(false);
  }

  // Notify core to refresh batch button (imported lazily to avoid circular dep)
  _updateBatchButtonCallback?.();

  // Auto-save engine selection (skip during initial config load)
  if (getConfigLoaded() && engine) {
    _autoSaveEngine(engine);
  }
}

/**
 * Callback set by core.ts to update the batch button label.
 * This avoids a circular dependency (config -> core).
 */
let _updateBatchButtonCallback: (() => void) | null = null;
export function setUpdateBatchButtonCallback(cb: () => void): void {
  _updateBatchButtonCallback = cb;
}

async function _autoSaveEngine(engine: string): Promise<void> {
  const statusEl = document.getElementById('aiEngineSaveStatus');
  try {
    await apiFetch('/api/analysis/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ engine }),
    });
    if (statusEl) {
      statusEl.textContent = '\u2705 ' + _t('tools.engine_saved', 'Engine saved');
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    }
    // Auto-load models when switching engines
    if (engine === 'openai_compat') {
      loadOpenaiCompatModels();
    }
    if (engine === 'ollama') {
      loadOllamaModels();
    }
    // Auto-check Hailo status when switching to Hailo VLM
    if (engine === 'hailo_vlm') {
      checkHailoStatus();
    }
  } catch {
    if (statusEl) {
      statusEl.textContent = '\u274C ' + _t('tools.save_failed', 'Save failed');
    }
  }
}

/** Save the full AI configuration form. */
export async function saveAiConfig(reloadConfig: () => Promise<void>): Promise<void> {
  const engine = (document.getElementById('aiEngine') as HTMLSelectElement).value;
  const apiKey = (document.getElementById('aiApiKey') as HTMLInputElement).value.trim();
  const claudeModel = (document.getElementById('claudeModel') as HTMLSelectElement | null)?.value;
  const ollamaUrl = (document.getElementById('ollamaUrl') as HTMLInputElement | null)?.value.trim();
  const ollamaModel = (document.getElementById('ollamaModel') as HTMLSelectElement | null)?.value;
  const openaiApiKey = (document.getElementById('openaiApiKey') as HTMLInputElement | null)?.value.trim();
  const openaiModel = (document.getElementById('openaiModel') as HTMLSelectElement | null)?.value;
  const openaiCompatUrl = (document.getElementById('openaiCompatUrl') as HTMLInputElement | null)?.value.trim();
  const openaiCompatApiKey = (document.getElementById('openaiCompatApiKey') as HTMLInputElement | null)?.value.trim();
  const openaiCompatModel = (document.getElementById('openaiCompatModel') as HTMLSelectElement | null)?.value;

  const fallbackLocalOnly = (document.getElementById('aiFallbackLocalOnly') as HTMLInputElement | null)?.checked ?? false;
  const analysisLanguage = (document.getElementById('aiAnalysisLanguage') as HTMLSelectElement | null)?.value || 'ja';

  const payload: Record<string, string | boolean | undefined> = {
    engine,
    api_key: apiKey || undefined,
    fallback_local_only: fallbackLocalOnly,
    language: analysisLanguage,
  };
  if (claudeModel) payload.model = claudeModel;
  if (ollamaUrl) payload.ollama_url = ollamaUrl;
  if (ollamaModel) payload.ollama_model = ollamaModel;
  if (openaiApiKey) payload.openai_api_key = openaiApiKey;
  if (openaiModel) payload.openai_model = openaiModel;
  if (openaiCompatUrl) payload.openai_compat_url = openaiCompatUrl;
  if (openaiCompatApiKey) payload.openai_compat_api_key = openaiCompatApiKey;
  if (openaiCompatModel) payload.openai_compat_model = openaiCompatModel;

  try {
    await apiFetch('/api/analysis/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    const keyStatusEl = document.getElementById('aiKeyStatus');
    if (keyStatusEl && engine === 'claude_api')
      keyStatusEl.textContent = '\u2705 ' + _t('tools.saved', 'Saved');
    const openaiStatus = document.getElementById('openaiKeyStatus');
    if (openaiStatus && engine === 'openai')
      openaiStatus.textContent = '\u2705 ' + _t('tools.saved', 'Saved');
    const ollamaStatus = document.getElementById('ollamaConnStatus');
    if (ollamaStatus && engine === 'ollama')
      ollamaStatus.textContent = '\u2705 ' + _t('tools.saved', 'Saved');
    const compatStatus = document.getElementById('openaiCompatConnStatus');
    if (compatStatus && engine === 'openai_compat')
      compatStatus.textContent = '\u2705 ' + _t('tools.saved', 'Saved');
    const apiKeyInput = document.getElementById('aiApiKey') as HTMLInputElement | null;
    if (apiKeyInput) apiKeyInput.value = '';
    const openaiKeyInput = document.getElementById('openaiApiKey') as HTMLInputElement | null;
    if (openaiKeyInput) openaiKeyInput.value = '';
    const compatKeyInput = document.getElementById('openaiCompatApiKey') as HTMLInputElement | null;
    if (compatKeyInput) compatKeyInput.value = '';
    reloadConfig();
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    const keyStatusEl = document.getElementById('aiKeyStatus');
    if (keyStatusEl)
      keyStatusEl.textContent =
        '\u274C ' + _t('tools.save_failed', 'Save failed') + ': ' + msg;
  }
}
