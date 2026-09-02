/**
 * ai-analysis/connections.ts -- Ollama / OpenAI Compatible / Hailo connection tests.
 */

import { apiFetch } from '../api';
import { _t } from './helpers';

/* ------------------------------------------------------------------ */
/* Ollama                                                              */
/* ------------------------------------------------------------------ */

interface OllamaModel {
  name: string;
  size: number;
}

interface OllamaConnectionResult {
  connected: boolean;
  models: OllamaModel[];
  error?: string | null;
}

export async function loadOllamaModels(): Promise<void> {
  const selectEl = document.getElementById('ollamaModel') as HTMLSelectElement | null;
  const statusEl = document.getElementById('ollamaConnStatus');
  if (!selectEl) return;

  try {
    const res = await apiFetch('/api/analysis/ollama/models');
    const data: OllamaConnectionResult = await res.json();
    if (!data.connected) {
      if (statusEl)
        statusEl.textContent =
          '\u274C ' + _t('tools.ollama_not_connected', 'Not connected') +
          (data.error ? ': ' + data.error : '');
      return;
    }
    const prev = selectEl.value;
    selectEl.innerHTML = '';
    if (data.models.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = _t('tools.ollama_no_models', 'No models found. Run: ollama pull llava');
      selectEl.appendChild(opt);
    } else {
      for (const m of data.models) {
        const opt = document.createElement('option');
        opt.value = m.name;
        opt.textContent = m.name;
        selectEl.appendChild(opt);
      }
      // Restore previous selection if still available
      if (prev && Array.from(selectEl.options).some((o) => o.value === prev)) {
        selectEl.value = prev;
      }
    }
    if (statusEl)
      statusEl.textContent =
        '\u2705 ' +
        _t('tools.ollama_connected', 'Connected') +
        ` (${data.models.length} models)`;
  } catch {
    if (statusEl)
      statusEl.textContent =
        '\u274C ' + _t('tools.ollama_not_connected', 'Not connected');
  }
}

export async function testOllamaConnection(): Promise<void> {
  const statusEl = document.getElementById('ollamaConnStatus');
  const urlEl = document.getElementById('ollamaUrl') as HTMLInputElement | null;
  const url = urlEl?.value.trim() || 'http://localhost:11434';
  if (statusEl) statusEl.textContent = '...';

  try {
    const res = await apiFetch('/api/analysis/ollama/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ ollama_url: url }),
    });
    const data: OllamaConnectionResult = await res.json();
    if (data.connected) {
      if (statusEl)
        statusEl.textContent =
          '\u2705 ' +
          _t('tools.ollama_connected', 'Connected') +
          ` (${data.models.length} models)`;
      // Also refresh the model list
      loadOllamaModels();
    } else {
      if (statusEl)
        statusEl.textContent =
          '\u274C ' + _t('tools.ollama_not_connected', 'Not connected') +
          (data.error ? ': ' + data.error : '');
    }
  } catch {
    if (statusEl)
      statusEl.textContent =
        '\u274C ' + _t('tools.ollama_not_connected', 'Not connected');
  }
}

/* ------------------------------------------------------------------ */
/* OpenAI Compatible                                                   */
/* ------------------------------------------------------------------ */

interface OpenaiCompatModel {
  id: string;
  owned_by: string;
}

interface OpenaiCompatConnectionResult {
  connected: boolean;
  models: OpenaiCompatModel[];
  error?: string | null;
}

export async function loadOpenaiCompatModels(): Promise<void> {
  const selectEl = document.getElementById('openaiCompatModel') as HTMLSelectElement | null;
  const statusEl = document.getElementById('openaiCompatConnStatus');
  if (!selectEl) return;

  try {
    const res = await apiFetch('/api/analysis/openai-compat/models');
    const data: OpenaiCompatConnectionResult = await res.json();
    if (!data.connected) {
      if (statusEl)
        statusEl.textContent =
          '\u274C ' + _t('tools.openai_compat_not_connected', 'Not connected') +
          (data.error ? ': ' + data.error : '');
      return;
    }
    const prev = selectEl.value;
    selectEl.innerHTML = '';
    if (data.models.length === 0) {
      const opt = document.createElement('option');
      opt.value = '';
      opt.textContent = _t('tools.openai_compat_no_models', 'No models found');
      selectEl.appendChild(opt);
    } else {
      for (const m of data.models) {
        const opt = document.createElement('option');
        opt.value = m.id;
        opt.textContent = m.id;
        selectEl.appendChild(opt);
      }
      if (prev && Array.from(selectEl.options).some((o) => o.value === prev)) {
        selectEl.value = prev;
      }
    }
    if (statusEl)
      statusEl.textContent =
        '\u2705 ' +
        _t('tools.openai_compat_connected', 'Connected') +
        ` (${data.models.length} models)`;
  } catch {
    if (statusEl)
      statusEl.textContent =
        '\u274C ' + _t('tools.openai_compat_not_connected', 'Not connected');
  }
}

export async function testOpenaiCompatConnection(): Promise<void> {
  const statusEl = document.getElementById('openaiCompatConnStatus');
  const urlEl = document.getElementById('openaiCompatUrl') as HTMLInputElement | null;
  const keyEl = document.getElementById('openaiCompatApiKey') as HTMLInputElement | null;
  const url = urlEl?.value.trim() || '';
  const apiKey = keyEl?.value.trim() || '';
  if (statusEl) statusEl.textContent = '...';

  if (!url) {
    if (statusEl) statusEl.textContent = '\u274C URL is required';
    return;
  }

  try {
    const res = await apiFetch('/api/analysis/openai-compat/test', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url, api_key: apiKey }),
    });
    const data: OpenaiCompatConnectionResult = await res.json();
    if (data.connected) {
      if (statusEl)
        statusEl.textContent =
          '\u2705 ' +
          _t('tools.openai_compat_connected', 'Connected') +
          ` (${data.models.length} models)`;
      // Refresh model list with saved config
      loadOpenaiCompatModels();
    } else {
      if (statusEl)
        statusEl.textContent =
          '\u274C ' + _t('tools.openai_compat_not_connected', 'Not connected') +
          (data.error ? ': ' + data.error : '');
    }
  } catch {
    if (statusEl)
      statusEl.textContent =
        '\u274C ' + _t('tools.openai_compat_not_connected', 'Not connected');
  }
}

/* ------------------------------------------------------------------ */
/* Hailo VLM                                                           */
/* ------------------------------------------------------------------ */

interface HailoStatus {
  available?: boolean;
  hailo_available?: boolean;
  genai_available?: boolean;
  device_busy?: boolean;
  device_owner?: string | null;
  models?: Record<string, { available?: boolean; downloaded?: boolean }>;
}

export async function checkHailoStatus(): Promise<void> {
  const statusEl = document.getElementById('hailoVlmStatus');
  if (!statusEl) return;
  statusEl.textContent = '...';

  try {
    const res = await apiFetch('/ext/hailo-genai/api/status');
    const data: HailoStatus = await res.json();

    const isAvailable = data.available || data.hailo_available;
    if (!isAvailable) {
      statusEl.innerHTML =
        '<span style="color:#e74c3c;">\u274C ' +
        _t('tools.hailo_not_available', 'Hailo-10H not detected') +
        '</span>';
      return;
    }

    // Check if VLM model is downloaded/available
    const vlmModel = data.models?.['qwen2-vl-2b-instruct'];
    if (vlmModel && !vlmModel.downloaded && !vlmModel.available) {
      statusEl.innerHTML =
        '<span style="color:#f39c12;">\u26A0 ' +
        _t('tools.hailo_model_not_downloaded', 'VLM model not downloaded. Download it from the Hailo GenAI panel.') +
        '</span>';
      return;
    }

    if (data.device_busy) {
      statusEl.innerHTML =
        '<span style="color:#f39c12;">\u26A0 ' +
        _t('tools.hailo_device_busy', 'Hailo device is currently in use by another task.') +
        '</span>';
      return;
    }

    statusEl.innerHTML =
      '<span style="color:#4ade80;">\u2705 ' +
      _t('tools.hailo_ready', 'Hailo VLM ready') +
      '</span>';
  } catch {
    statusEl.innerHTML =
      '<span style="color:#888;">' +
      _t('tools.hailo_not_available', 'Hailo-10H not detected') +
      '</span>';
  }
}
