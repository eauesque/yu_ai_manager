/**
 * wd-tagger/model.ts -- Model status/download and VLM connection/models.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import { renderWtModelStatus } from './render';
import { _ensureModelOption } from './config';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// ── Model ─────────────────────────────────────────────

export async function wtLoadModelStatus(): Promise<void> {
  const el = document.getElementById('wtModelStatus');
  if (!el) return;
  try {
    const model = (document.getElementById('wtModel') as HTMLSelectElement | null)?.value || '';
    const qs = model ? `?model_id=${encodeURIComponent(model)}` : '';
    const res = await fetch(`/api/wd-tagger/model/status${qs}`);
    const data = await res.json();
    el.innerHTML = renderWtModelStatus(data);
  } catch {
    el.textContent = _t('tools.wt_model_check_failed', 'Model status check failed');
  }
}

export async function wtDownloadModel(): Promise<void> {
  const modelId = (document.getElementById('wtModel') as HTMLSelectElement | null)?.value || '';
  const btn = document.getElementById('wtDownloadBtn') as HTMLButtonElement | null;
  if (btn) btn.disabled = true;

  const statusEl = document.getElementById('wtModelStatus');
  if (statusEl) statusEl.innerHTML = '⏳ ' + _t('tools.wt_downloading', 'Downloading model...');

  try {
    const res = await apiFetch('/api/wd-tagger/model/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data = await res.json();
    if (data.ok !== false) {
      getNavApi().showToast(_t('tools.wt_model_ready', 'Model downloaded and ready'));
      wtLoadModelStatus();
    }
  } catch (err) {
    if (statusEl) statusEl.textContent = _t('tools.wt_download_failed', 'Download failed');
  } finally {
    if (btn) btn.disabled = false;
  }
}


// ── VLM connection ────────────────────────────────────

export async function wtTestVlm(): Promise<void> {
  const urlInput = document.getElementById('wtVlmUrl') as HTMLInputElement | null;
  const resultEl = document.getElementById('wtVlmTestResult');
  const btn = document.getElementById('wtVlmTestBtn') as HTMLButtonElement | null;
  const url = urlInput?.value?.trim() || '';

  if (!url) {
    if (resultEl) resultEl.textContent = _t('tools.wt_vlm_failed', 'VLM connection failed');
    return;
  }

  if (btn) btn.disabled = true;
  if (resultEl) resultEl.textContent = '...';

  try {
    const res = await fetch(`/api/wd-tagger/vlm/test?url=${encodeURIComponent(url)}`);
    const data = await res.json();
    const info = data.data || data;

    if (info.connected) {
      if (resultEl) {
        resultEl.style.color = '#4caf50';
        resultEl.textContent = _t('tools.wt_vlm_connected', 'VLM connected');
      }
      // Auto-load models
      wtLoadVlmModels(url);
    } else {
      if (resultEl) {
        resultEl.style.color = '#f44336';
        resultEl.textContent = `${_t('tools.wt_vlm_failed', 'VLM connection failed')}: ${info.error || ''}`;
      }
    }
  } catch {
    if (resultEl) {
      resultEl.style.color = '#f44336';
      resultEl.textContent = _t('tools.wt_vlm_failed', 'VLM connection failed');
    }
  } finally {
    if (btn) btn.disabled = false;
  }
}

export async function wtLoadVlmModels(url?: string): Promise<void> {
  const vlmUrl = url || (document.getElementById('wtVlmUrl') as HTMLInputElement | null)?.value?.trim() || '';
  if (!vlmUrl) return;

  const sel = document.getElementById('wtVlmModel') as HTMLSelectElement | null;
  if (!sel) return;

  try {
    const res = await fetch(`/api/wd-tagger/vlm/models?url=${encodeURIComponent(vlmUrl)}`);
    const data = await res.json();
    const models: Array<{ id: string; owned_by?: string }> = data.data?.models || data.models || [];

    // Preserve current selection
    const current = sel.value;
    sel.innerHTML = `<option value="" data-i18n="tools.wt_vlm_select_model">${_t('tools.wt_vlm_select_model', 'Select model...')}</option>`;

    for (const m of models) {
      const opt = document.createElement('option');
      opt.value = m.id;
      opt.textContent = m.id;
      sel.appendChild(opt);
    }

    // Restore selection if still valid
    if (current) {
      _ensureModelOption(sel, current);
      sel.value = current;
    }
  } catch { /* ignore */ }
}
