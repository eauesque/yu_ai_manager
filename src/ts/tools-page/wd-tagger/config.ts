/**
 * wd-tagger/config.ts -- Config CRUD and engine UI toggle.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import { fetchWdTaggerProfiles, type WdTaggerProfile } from './profiles';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// ── Shared helper ────────────────────────────────────

/**
 * Ensure an <option> with the given value exists in the select element.
 * Used by wtLoadConfigData and wtLoadVlmModels (model.ts).
 */
export function _ensureModelOption(sel: HTMLSelectElement, modelId: string): void {
  for (const opt of Array.from(sel.options)) {
    if (opt.value === modelId) return;
  }
  const opt = document.createElement('option');
  opt.value = modelId;
  opt.textContent = modelId;
  sel.appendChild(opt);
}

function _profileLabel(profile: WdTaggerProfile): string {
  return profile.display_name || profile.model_id || profile.id;
}

function _modelDisplayName(modelId: string, profiles: WdTaggerProfile[]): string {
  const profile = profiles.find((p) => p.model_id === modelId || p.id === modelId);
  return profile ? _profileLabel(profile) : modelId;
}

function _populateModelOptions(sel: HTMLSelectElement, profiles: WdTaggerProfile[]): void {
  sel.textContent = '';
  for (const profile of profiles) {
    if (!profile.model_id) continue;
    const opt = document.createElement('option');
    opt.value = profile.model_id;
    opt.textContent = _profileLabel(profile);
    sel.appendChild(opt);
  }
}

function _setActiveModelLabel(modelId: string | null, profiles: WdTaggerProfile[] = []): void {
  const valueEl = document.getElementById('wtActiveModelValue');
  if (!valueEl) return;
  valueEl.textContent = modelId
    ? _modelDisplayName(modelId, profiles)
    : _t('tools.wt_active_model_none', '(none)');
}

async function _loadProfilesIntoModelSelect(selectedModel: string): Promise<WdTaggerProfile[]> {
  const modelSel = document.getElementById('wtModel') as HTMLSelectElement | null;
  if (!modelSel) return [];

  try {
    const payload = await fetchWdTaggerProfiles();
    _populateModelOptions(modelSel, payload.profiles);
    if (selectedModel) _ensureModelOption(modelSel, selectedModel);
    modelSel.value = selectedModel || payload.profiles[0]?.model_id || '';
    _setActiveModelLabel(payload.active_model_id, payload.profiles);
    return payload.profiles;
  } catch {
    if (selectedModel) {
      _ensureModelOption(modelSel, selectedModel);
      modelSel.value = selectedModel;
    }
    _setActiveModelLabel(null);
    return [];
  }
}

// ── Config load (DOM only) ───────────────────────────

/**
 * Load config from the API and populate DOM inputs.
 * Calls wtToggleEngineUI() at the end.
 * NOTE: Does NOT call wtLoadModelStatus / wtLoadStats -- the caller
 *       (core.ts wtLoadConfig) is responsible for that.
 */
export async function wtLoadConfigData(): Promise<void> {
  try {
    const res = await fetch('/api/wd-tagger/config');
    const data = await res.json();
    if (!data.ok) return;
    const cfg = data.config || data.data?.config;
    if (!cfg) return;

    await _loadProfilesIntoModelSelect(cfg.model || 'SmilingWolf/wd-swinv2-tagger-v3');

    const genSlider = document.getElementById('wtGeneralThreshold') as HTMLInputElement | null;
    if (genSlider) {
      genSlider.value = String(cfg.general_threshold ?? 0.35);
      const valEl = document.getElementById('wtGeneralVal');
      if (valEl) valEl.textContent = genSlider.value;
    }

    const charSlider = document.getElementById('wtCharThreshold') as HTMLInputElement | null;
    if (charSlider) {
      charSlider.value = String(cfg.character_threshold ?? 0.85);
      const valEl = document.getElementById('wtCharVal');
      if (valEl) valEl.textContent = charSlider.value;
    }

    const xmpChk = document.getElementById('wtWriteXmp') as HTMLInputElement | null;
    if (xmpChk) xmpChk.checked = cfg.write_xmp !== false;

    // Engine type
    const engineSel = document.getElementById('wtEngineType') as HTMLSelectElement | null;
    if (engineSel) engineSel.value = cfg.engine_type || 'onnx';

    // VLM settings
    const vlmUrl = document.getElementById('wtVlmUrl') as HTMLInputElement | null;
    if (vlmUrl && cfg.vlm_url) vlmUrl.value = cfg.vlm_url;

    const vlmTimeout = document.getElementById('wtVlmTimeout') as HTMLInputElement | null;
    if (vlmTimeout) vlmTimeout.value = String(cfg.vlm_timeout ?? 60);

    // NSFW filter
    const nsfwChk = document.getElementById('wtNsfwFilter') as HTMLInputElement | null;
    if (nsfwChk) nsfwChk.checked = !!cfg.nsfw_filter;

    // If VLM model is set, add it as option and select it
    const vlmModelSel = document.getElementById('wtVlmModel') as HTMLSelectElement | null;
    if (vlmModelSel && cfg.vlm_model) {
      _ensureModelOption(vlmModelSel, cfg.vlm_model);
      vlmModelSel.value = cfg.vlm_model;
    }
  } catch { /* ignore */ }

  wtToggleEngineUI();
}

// ── Config save ──────────────────────────────────────

export async function wtSaveConfig(): Promise<void> {
  const model = (document.getElementById('wtModel') as HTMLSelectElement | null)?.value || '';
  const general_threshold = parseFloat(
    (document.getElementById('wtGeneralThreshold') as HTMLInputElement | null)?.value || '0.35',
  );
  const character_threshold = parseFloat(
    (document.getElementById('wtCharThreshold') as HTMLInputElement | null)?.value || '0.85',
  );
  const write_xmp = (document.getElementById('wtWriteXmp') as HTMLInputElement | null)?.checked ?? true;
  const engine_type = (document.getElementById('wtEngineType') as HTMLSelectElement | null)?.value || 'onnx';
  const vlm_url = (document.getElementById('wtVlmUrl') as HTMLInputElement | null)?.value || '';
  const vlm_model = (document.getElementById('wtVlmModel') as HTMLSelectElement | null)?.value || '';
  const vlm_timeout = parseInt(
    (document.getElementById('wtVlmTimeout') as HTMLInputElement | null)?.value || '60', 10,
  );
  const nsfw_filter = (document.getElementById('wtNsfwFilter') as HTMLInputElement | null)?.checked ?? false;

  try {
    const res = await apiFetch('/api/wd-tagger/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model, general_threshold, character_threshold, write_xmp,
        engine_type, vlm_url, vlm_model, vlm_timeout, nsfw_filter,
      }),
    });
    const data = await res.json();
    if (data.ok !== false) {
      const modelSel = document.getElementById('wtModel') as HTMLSelectElement | null;
      const modelName = modelSel?.selectedOptions[0]?.textContent || model;
      _setActiveModelLabel(model, modelName ? [{ id: model, model_id: model, display_name: modelName }] : []);
      const synced = _t('tools.wt_active_model_synced', 'Active model set to {model}')
        .replace('{model}', modelName || model);
      getNavApi().showToast(`${_t('tools.wt_config_saved', 'WD-Tagger config saved')}. ${synced}`);
    }
  } catch (err) {
    getNavApi().showToast(_t('tools.wt_config_failed', 'Failed to save config'), true);
  }
}

// ── Engine UI toggle ─────────────────────────────────

export function wtToggleEngineUI(): void {
  const engineType = (document.getElementById('wtEngineType') as HTMLSelectElement | null)?.value || 'onnx';
  const onnxSection = document.getElementById('wtOnnxSection');
  const vlmSection = document.getElementById('wtVlmSection');

  if (onnxSection) onnxSection.style.display = (engineType === 'vlm') ? 'none' : '';
  if (vlmSection) vlmSection.style.display = (engineType === 'onnx') ? 'none' : '';
}
