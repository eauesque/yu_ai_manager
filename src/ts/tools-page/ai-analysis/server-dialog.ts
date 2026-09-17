/**
 * ai-analysis/server-dialog.ts -- Add/Edit dialog for AI servers,
 * including type-specific form fields and model refresh.
 */

import { apiFetch } from '../api';
import { _t, _esc } from './helpers';
import { ServerEntry, getServers, errMsg } from './server-types';
import { loadAiServers } from './server-list';

/* ------------------------------------------------------------------ */
/* Public entry points                                                 */
/* ------------------------------------------------------------------ */

export function aisCloseDialog(): void {
  document.getElementById('aisDialog')?.remove();
}

export function aisShowAddDialog(): void {
  _showDialog(null);
}

export function aisShowEditDialog(serverId: string): void {
  const server = getServers().find(s => s.id === serverId);
  if (!server) return;
  _showDialog(server);
}

/* ------------------------------------------------------------------ */
/* Dialog construction                                                 */
/* ------------------------------------------------------------------ */

function _showDialog(server: ServerEntry | null): void {
  const isEdit = !!server;
  const title = isEdit
    ? _t('tools.edit_server', 'Edit AI Server')
    : _t('tools.add_server', 'Add AI Server');

  // Remove existing dialog
  document.getElementById('aisDialog')?.remove();

  const overlay = document.createElement('div');
  overlay.id = 'aisDialog';
  overlay.className = 'ais-overlay';
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });

  const type = server?.type || 'openai_compat';

  overlay.innerHTML = `
    <div class="ais-dialog" role="dialog" aria-label="${title}">
      <h3 style="margin:0 0 14px;">${title}</h3>
      <div class="ais-form">
        <label>${_t('tools.server_name', 'Server Name')}:</label>
        <input type="text" id="aisFormName" value="${_esc(server?.name || '')}" placeholder="e.g. RTX Server, Pi Ollama">

        <label>${_t('tools.engine_type', 'Engine Type')}:</label>
        <select id="aisFormType" data-action="toolsPageApi.aisOnTypeChange" data-action-event="change">
          <option value="claude_api"${type === 'claude_api' ? ' selected' : ''}>Claude API</option>
          <option value="openai"${type === 'openai' ? ' selected' : ''}>OpenAI API</option>
          <option value="openai_compat"${type === 'openai_compat' ? ' selected' : ''}>OpenAI Compatible</option>
          <option value="ollama"${type === 'ollama' ? ' selected' : ''}>Ollama</option>
          <option value="hailo_vlm"${type === 'hailo_vlm' ? ' selected' : ''}>Hailo VLM</option>
        </select>

        <div id="aisFormFields"></div>

        <label>${_t('tools.priority', 'Priority')} <span style="font-weight:normal;color:var(--muted);">(lower = higher)</span>:</label>
        <input type="number" id="aisFormPriority" value="${server?.priority ?? 50}" min="1" max="999" style="max-width:100px;">
      </div>
      <div style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end;">
        <button class="btn btn-secondary" data-action="toolsPageApi.aisCloseDialog">
          ${_t('tools.cancel', 'Cancel')}
        </button>
        <button class="btn btn-primary" data-action="toolsPageApi.aisSaveDialog" data-action-arg="${isEdit ? server!.id : ''}">
          ${isEdit ? _t('tools.save', 'Save') : _t('tools.add', 'Add')}
        </button>
      </div>
      <div id="aisFormError" style="color:#e74c3c;font-size:12px;margin-top:8px;"></div>
    </div>`;

  document.body.appendChild(overlay);

  // Render type-specific fields
  _updateDialogFields(type, server?.config || {});

  // Focus first input
  const nameInput = document.getElementById('aisFormName') as HTMLInputElement;
  nameInput?.focus();

  // Escape to close
  overlay.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') overlay.remove();
  });
}

/* ------------------------------------------------------------------ */
/* Type-specific form fields                                           */
/* ------------------------------------------------------------------ */

export function aisOnTypeChange(): void {
  const typeEl = document.getElementById('aisFormType') as HTMLSelectElement;
  _updateDialogFields(typeEl.value, {});
}

function _updateDialogFields(type: string, config: Record<string, string>): void {
  const container = document.getElementById('aisFormFields');
  if (!container) return;

  let html = '';
  if (type === 'claude_api') {
    html = `
      <label>API Key:</label>
      <input type="password" id="aisFormApiKey" value="${_esc(config.api_key || '')}" placeholder="sk-ant-...">
      <label>Model:</label>
      <select id="aisFormModel">
        <option value="claude-sonnet-4-6"${config.model === 'claude-sonnet-4-6' ? ' selected' : ''}>Claude Sonnet 4.6</option>
        <option value="claude-opus-4-6"${config.model === 'claude-opus-4-6' ? ' selected' : ''}>Claude Opus 4.6</option>
        <option value="claude-haiku-4-5"${config.model === 'claude-haiku-4-5' ? ' selected' : ''}>Claude Haiku 4.5</option>
        <option value="claude-sonnet-4-5"${config.model === 'claude-sonnet-4-5' ? ' selected' : ''}>Claude Sonnet 4.5</option>
      </select>`;
  } else if (type === 'openai') {
    html = `
      <label>API Key:</label>
      <input type="password" id="aisFormApiKey" value="${_esc(config.api_key || '')}" placeholder="sk-...">
      <label>Model:</label>
      <select id="aisFormModel">
        <option value="gpt-4o-mini"${config.model === 'gpt-4o-mini' ? ' selected' : ''}>gpt-4o-mini</option>
        <option value="gpt-4o"${config.model === 'gpt-4o' ? ' selected' : ''}>gpt-4o</option>
        <option value="gpt-4-turbo"${config.model === 'gpt-4-turbo' ? ' selected' : ''}>gpt-4-turbo</option>
      </select>`;
  } else if (type === 'openai_compat') {
    html = `
      <label>Server URL:</label>
      <input type="text" id="aisFormBaseUrl" value="${_esc(config.base_url || '')}" placeholder="http://192.168.1.100:8000">
      <label>API Key <span style="font-weight:normal;color:var(--muted);">(optional)</span>:</label>
      <input type="password" id="aisFormApiKey" value="${_esc(config.api_key || '')}" placeholder="sk-...">
      <label>Model:</label>
      <div style="display:flex;gap:8px;">
        <select id="aisFormModel" style="flex:1;padding:8px;border-radius:5px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.2);color:inherit;">
          ${config.model ? `<option value="${_esc(config.model)}" selected>${_esc(config.model)}</option>` : '<option value="">-- select model --</option>'}
        </select>
        <button type="button" class="btn btn-secondary btn-sm" data-action="toolsPageApi.aisRefreshModels">Refresh</button>
      </div>
      <div id="aisModelStatus" style="font-size:11px;color:var(--muted);margin-top:4px;"></div>`;
  } else if (type === 'ollama') {
    html = `
      <label>Server URL:</label>
      <input type="text" id="aisFormBaseUrl" value="${_esc(config.base_url || 'http://localhost:11434')}" placeholder="http://localhost:11434">
      <label>Model:</label>
      <div style="display:flex;gap:8px;">
        <select id="aisFormModel" style="flex:1;padding:8px;border-radius:5px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.2);color:inherit;">
          ${config.model ? `<option value="${_esc(config.model)}" selected>${_esc(config.model)}</option>` : '<option value="llava:latest" selected>llava:latest</option>'}
        </select>
        <button type="button" class="btn btn-secondary btn-sm" data-action="toolsPageApi.aisRefreshModels">Refresh</button>
      </div>
      <div id="aisModelStatus" style="font-size:11px;color:var(--muted);margin-top:4px;"></div>`;
  } else if (type === 'hailo_vlm') {
    html = `
      <label>Model:</label>
      <input type="text" id="aisFormModelName" value="${_esc(config.model_name || 'qwen2-vl-2b-instruct')}" placeholder="qwen2-vl-2b-instruct">
      <p style="font-size:11px;color:var(--muted);margin:4px 0 0;">On-device NPU inference. No network required.</p>`;
  }

  container.innerHTML = html;
}

/* ------------------------------------------------------------------ */
/* Save dialog                                                         */
/* ------------------------------------------------------------------ */

export async function aisSaveDialog(existingId: string | null): Promise<void> {
  // data-action-arg passes empty string for "add" mode; treat as null
  if (existingId === '') existingId = null;
  const errEl = document.getElementById('aisFormError');
  const name = (document.getElementById('aisFormName') as HTMLInputElement)?.value.trim();
  const type = (document.getElementById('aisFormType') as HTMLSelectElement)?.value;
  const priority = parseInt((document.getElementById('aisFormPriority') as HTMLInputElement)?.value || '50', 10);

  if (!name) {
    if (errEl) errEl.textContent = 'Server name is required';
    return;
  }

  const config: Record<string, string> = {};
  const apiKeyEl = document.getElementById('aisFormApiKey') as HTMLInputElement | null;
  const modelEl = document.getElementById('aisFormModel') as HTMLInputElement | HTMLSelectElement | null;
  const baseUrlEl = document.getElementById('aisFormBaseUrl') as HTMLInputElement | null;
  const modelNameEl = document.getElementById('aisFormModelName') as HTMLInputElement | null;

  if (apiKeyEl?.value) config.api_key = apiKeyEl.value.trim();
  if (modelEl?.value) config.model = modelEl.value.trim();
  if (baseUrlEl?.value) config.base_url = baseUrlEl.value.trim();
  if (modelNameEl?.value) config.model_name = modelNameEl.value.trim();

  const payload = { name, type, priority, config };

  try {
    if (existingId) {
      await apiFetch(`/api/analysis/servers/${existingId}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    } else {
      await apiFetch('/api/analysis/servers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }
    document.getElementById('aisDialog')?.remove();
    loadAiServers();
  } catch (e) {
    if (errEl) errEl.textContent = errMsg(e);
  }
}

/* ------------------------------------------------------------------ */
/* Model refresh for dialog                                            */
/* ------------------------------------------------------------------ */

export async function aisRefreshModels(): Promise<void> {
  const typeEl = document.getElementById('aisFormType') as HTMLSelectElement | null;
  const baseUrlEl = document.getElementById('aisFormBaseUrl') as HTMLInputElement | null;
  const apiKeyEl = document.getElementById('aisFormApiKey') as HTMLInputElement | null;
  const modelEl = document.getElementById('aisFormModel') as HTMLSelectElement | null;
  const statusEl = document.getElementById('aisModelStatus');
  if (!typeEl || !baseUrlEl || !modelEl) return;

  const baseUrl = baseUrlEl.value.trim();
  if (!baseUrl) {
    if (statusEl) statusEl.textContent = _t('ai_servers.enter_url', 'Please enter URL');
    return;
  }

  const currentModel = modelEl.value;
  if (statusEl) { statusEl.textContent = _t('ai_servers.fetching', 'Fetching...'); statusEl.style.color = 'var(--muted)'; }

  try {
    const engineType = typeEl.value;
    let models: { id: string; name?: string }[] = [];

    if (engineType === 'ollama') {
      const res = await apiFetch('/api/analysis/ollama/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ollama_url: baseUrl }),
      });
      const data = await res.json();
      if (!data.connected) {
        if (statusEl) { statusEl.textContent = data.error || _t('ai_servers.connection_failed', 'Connection failed'); statusEl.style.color = '#e74c3c'; }
        return;
      }
      models = (data.models || []).map((m: { name: string }) => ({ id: m.name, name: m.name }));
    } else {
      // openai_compat
      const apiKey = apiKeyEl?.value.trim() || '';
      const res = await apiFetch('/api/analysis/openai-compat/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ url: baseUrl, api_key: apiKey }),
      });
      const data = await res.json();
      if (!data.connected) {
        if (statusEl) { statusEl.textContent = data.error || _t('ai_servers.connection_failed', 'Connection failed'); statusEl.style.color = '#e74c3c'; }
        return;
      }
      models = (data.models || []).map((m: { id: string }) => ({ id: m.id, name: m.id }));
    }

    if (!models.length) {
      if (statusEl) { statusEl.textContent = _t('ai_servers.no_models', 'No models found'); statusEl.style.color = '#f39c12'; }
      return;
    }

    // Populate select
    modelEl.innerHTML = '';
    for (const m of models) {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.name || m.id;
      if (m.id === currentModel) opt.selected = true;
      modelEl.appendChild(opt);
    }
    // If previous selection not found, select first
    if (currentModel && !models.some(m => m.id === currentModel)) {
      modelEl.selectedIndex = 0;
    }

    if (statusEl) { statusEl.textContent = _t('ai_servers.models_fetched', '{count} models fetched').replace('{count}', String(models.length)); statusEl.style.color = '#4ade80'; }
  } catch (e) {
    if (statusEl) { statusEl.textContent = errMsg(e); statusEl.style.color = '#e74c3c'; }
  }
}
