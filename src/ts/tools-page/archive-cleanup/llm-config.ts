/**
 * llm-config.ts -- LLM engine configuration UI and model refresh.
 *
 * Handles loading/saving LLM engine settings (Ollama, Claude API,
 * OpenAI, OpenAI-compatible) and dynamic model list fetching.
 * Extracted from llm.ts to keep each module under 300 lines.
 */

import { apiFetch } from '../api';
import { _t } from './state';

// -- DOM helpers (local to this module) --

function _setInput(id: string, value: string): void {
  const el = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null;
  if (el) el.value = value;
}

export function _getInput(id: string): string {
  const el = document.getElementById(id) as HTMLInputElement | HTMLSelectElement | null;
  return el?.value.trim() || '';
}

export function _toggleLlmFields(engine: string): void {
  const sections: Record<string, string[]> = {
    claude_api: ['acLlmClaudeFields'],
    openai: ['acLlmOpenaiFields'],
    openai_compat: ['acLlmOpenaiCompatFields'],
    ollama: ['acLlmOllamaFields'],
  };
  for (const ids of Object.values(sections)) {
    for (const id of ids) {
      const el = document.getElementById(id);
      if (el) el.style.display = 'none';
    }
  }
  const show = sections[engine];
  if (show) {
    for (const id of show) {
      const el = document.getElementById(id);
      if (el) el.style.display = '';
    }
  }
}

// -- Load LLM Config --

export async function acLoadLlmConfig(): Promise<void> {
  try {
    const res = await apiFetch('/api/tools/archive-cleanup/llm-config');
    const data = await res.json();
    if (data.error) return;

    const engine = data.engine || 'ollama';
    _setInput('acLlmEngine', engine);
    _setInput('acLlmApiKey', data.api_key || '');
    _setInput('acLlmModel', data.model || '');
    _setInput('acLlmOllamaUrl', data.ollama_url || 'http://localhost:11434');
    _setInput('acLlmOpenaiApiKey', data.openai_api_key || '');
    _setInput('acLlmOpenaiModel', data.openai_model || '');
    _setInput('acLlmOpenaiCompatUrl', data.openai_compat_url || '');
    _setInput('acLlmOpenaiCompatApiKey', data.openai_compat_api_key || '');

    _toggleLlmFields(engine);

    // For dynamically fetched engines, retrieve the model list before restoring saved values
    if (engine === 'ollama' || engine === 'openai_compat') {
      await acRefreshModels();
      if (engine === 'ollama') {
        _setInput('acLlmOllamaModel', data.ollama_model || '');
      } else {
        _setInput('acLlmOpenaiCompatModel', data.openai_compat_model || '');
      }
    }
  } catch {
    // silent
  }
}

// -- Save LLM Config --

export async function acSaveLlmConfig(): Promise<void> {
  const statusEl = document.getElementById('acLlmConfigStatus');
  const cfg = {
    engine: _getInput('acLlmEngine'),
    api_key: _getInput('acLlmApiKey'),
    model: _getInput('acLlmModel'),
    ollama_url: _getInput('acLlmOllamaUrl'),
    ollama_model: _getInput('acLlmOllamaModel'),
    openai_api_key: _getInput('acLlmOpenaiApiKey'),
    openai_model: _getInput('acLlmOpenaiModel'),
    openai_compat_url: _getInput('acLlmOpenaiCompatUrl'),
    openai_compat_api_key: _getInput('acLlmOpenaiCompatApiKey'),
    openai_compat_model: _getInput('acLlmOpenaiCompatModel'),
  };

  try {
    const res = await apiFetch('/api/tools/archive-cleanup/llm-config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(cfg),
    });
    const data = await res.json();
    if (statusEl) {
      statusEl.textContent = data.error || _t('tools.ac_llm_saved', 'Saved');
      statusEl.style.color = data.error ? '#e74c3c' : '#27ae60';
      setTimeout(() => { statusEl.textContent = ''; }, 3000);
    }
  } catch (err: unknown) {
    if (statusEl) {
      statusEl.textContent = err instanceof Error ? err.message : String(err);
      statusEl.style.color = '#e74c3c';
    }
  }
}

// -- Engine change handler --

export function acOnLlmEngineChange(): void {
  const engine = _getInput('acLlmEngine');
  _toggleLlmFields(engine);
  acRefreshModels();
}

// -- Refresh Models --

export async function acRefreshModels(): Promise<void> {
  const engine = _getInput('acLlmEngine');

  if (engine === 'ollama') {
    const selectEl = document.getElementById('acLlmOllamaModel') as HTMLSelectElement | null;
    const statusEl = document.getElementById('acLlmOllamaModelStatus');
    if (!selectEl) return;

    const baseUrl = _getInput('acLlmOllamaUrl');
    if (!baseUrl) {
      if (statusEl) { statusEl.textContent = 'URL required'; statusEl.style.color = '#e74c3c'; }
      return;
    }

    if (statusEl) { statusEl.textContent = 'Loading...'; statusEl.style.color = 'var(--text-muted, #999)'; }
    try {
      const res = await apiFetch('/api/tools/archive-cleanup/list-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine: 'ollama', base_url: baseUrl }),
      });
      const data = await res.json();
      if (data.error) {
        if (statusEl) { statusEl.textContent = data.error; statusEl.style.color = '#e74c3c'; }
        return;
      }
      const prev = selectEl.value;
      selectEl.innerHTML = '';
      for (const name of (data.models || [])) {
        const opt = document.createElement('option');
        opt.value = name;
        opt.textContent = name;
        selectEl.appendChild(opt);
      }
      if (prev && [...selectEl.options].some((o) => o.value === prev)) selectEl.value = prev;
      if (statusEl) {
        statusEl.textContent = `${(data.models || []).length} models`;
        statusEl.style.color = '#27ae60';
        setTimeout(() => { statusEl.textContent = ''; }, 3000);
      }
    } catch (err: unknown) {
      if (statusEl) {
        statusEl.textContent = err instanceof Error ? err.message : String(err);
        statusEl.style.color = '#e74c3c';
      }
    }
  } else if (engine === 'openai_compat') {
    const selectEl = document.getElementById('acLlmOpenaiCompatModel') as HTMLSelectElement | null;
    const statusEl = document.getElementById('acLlmOpenaiCompatModelStatus');
    if (!selectEl) return;

    const baseUrl = _getInput('acLlmOpenaiCompatUrl');
    if (!baseUrl) {
      if (statusEl) { statusEl.textContent = 'URL required'; statusEl.style.color = '#e74c3c'; }
      return;
    }

    const apiKey = _getInput('acLlmOpenaiCompatApiKey');
    if (statusEl) { statusEl.textContent = 'Loading...'; statusEl.style.color = 'var(--text-muted, #999)'; }
    try {
      const res = await apiFetch('/api/tools/archive-cleanup/list-models', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ engine: 'openai_compat', base_url: baseUrl, api_key: apiKey }),
      });
      const data = await res.json();
      if (data.error) {
        if (statusEl) { statusEl.textContent = data.error; statusEl.style.color = '#e74c3c'; }
        return;
      }
      const prev = selectEl.value;
      selectEl.innerHTML = '';
      for (const id of (data.models || [])) {
        const opt = document.createElement('option');
        opt.value = id;
        opt.textContent = id;
        selectEl.appendChild(opt);
      }
      if (prev && [...selectEl.options].some((o) => o.value === prev)) selectEl.value = prev;
      if (statusEl) {
        statusEl.textContent = `${(data.models || []).length} models`;
        statusEl.style.color = '#27ae60';
        setTimeout(() => { statusEl.textContent = ''; }, 3000);
      }
    } catch (err: unknown) {
      if (statusEl) {
        statusEl.textContent = err instanceof Error ? err.message : String(err);
        statusEl.style.color = '#e74c3c';
      }
    }
  }
  // claude_api / openai use static selects, so nothing to do
}
