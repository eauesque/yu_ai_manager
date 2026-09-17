/**
 * Search preset save/load functionality.
 */

import { getAppApi, getNavApi, getSearchResultsApi } from '../../shared/browser-apis';
import { restoreSearchState, SEARCH_STATE_KEY } from './core';

const PRESETS_KEY = 'tagdb_search_presets';

function _getPresets(): Record<string, string> {
  try {
    return JSON.parse(localStorage.getItem(PRESETS_KEY) || '{}');
  } catch (_) {
    return {};
  }
}

function _setPresets(presets: Record<string, string>): void {
  localStorage.setItem(PRESETS_KEY, JSON.stringify(presets));
}

function _refreshPresetMenu(): void {
  const { escapeHtml, tr } = getAppApi();
  const container = document.getElementById('presetMenu');
  if (!container) return;
  const presets = _getPresets();
  const names = Object.keys(presets);
  if (names.length === 0) {
    container.innerHTML = '<span style="color:#666;font-size:11px;padding:4px;">' +
      escapeHtml(tr('presets.empty') || 'No saved presets') + '</span>';
    return;
  }
  container.innerHTML = names.map(function (name) {
    return '<div style="display:flex;align-items:center;gap:4px;padding:2px 0;">' +
      '<button type="button" data-preset-action="load" data-preset-name="' + escapeHtml(name) + '" ' +
      'style="flex:1;text-align:left;padding:3px 8px;font-size:11px;background:rgba(102,126,234,0.1);border:1px solid rgba(102,126,234,0.3);color:#9bb;border-radius:3px;cursor:pointer;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">' +
      escapeHtml(name) + '</button>' +
      '<button type="button" data-preset-action="rename" data-preset-name="' + escapeHtml(name) + '" ' +
      'title="Rename" style="padding:2px 6px;font-size:10px;background:none;border:1px solid rgba(128,128,128,0.3);color:#9aa;border-radius:3px;cursor:pointer;">\u270F</button>' +
      '<button type="button" data-preset-action="delete" data-preset-name="' + escapeHtml(name) + '" ' +
      'title="Delete" style="padding:2px 6px;font-size:10px;background:none;border:1px solid rgba(255,100,100,0.3);color:#a66;border-radius:3px;cursor:pointer;">\u00d7</button>' +
      '</div>';
  }).join('');
  container.querySelectorAll<HTMLElement>('[data-preset-action][data-preset-name]').forEach((el) => {
    el.addEventListener('click', () => {
      const action = el.dataset.presetAction;
      const name = el.dataset.presetName;
      if (!name) return;
      if (action === 'load') {
        loadPreset(name);
        return;
      }
      if (action === 'rename') {
        renamePreset(name);
        return;
      }
      if (action === 'delete') {
        deletePreset(name);
      }
    });
  });
}

export function savePreset(): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const name = prompt(tr('presets.save_prompt') || 'Preset name:');
  if (!name || !name.trim()) return;
  const key = name.trim();
  const saved = localStorage.getItem(SEARCH_STATE_KEY);
  if (!saved) {
    showToast(tr('presets.nothing_to_save') || 'No search state to save');
    return;
  }
  const presets = _getPresets();
  presets[key] = saved;
  _setPresets(presets);
  showToast(tr('presets.saved', { name: key }) || 'Preset saved: ' + key);
  _refreshPresetMenu();
}

export function loadPreset(name: string): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const { runSearch } = getSearchResultsApi();
  const presets = _getPresets();
  const data = presets[name];
  if (!data) return;
  localStorage.setItem(SEARCH_STATE_KEY, data);
  restoreSearchState();
  runSearch();
  showToast(tr('presets.loaded', { name: name }) || 'Preset loaded: ' + name);
}

export function renamePreset(oldName: string): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const newName = prompt(tr('presets.rename_prompt') || 'New name:', oldName);
  if (!newName || !newName.trim() || newName.trim() === oldName) return;
  const key = newName.trim();
  const presets = _getPresets();
  if (!(oldName in presets)) return;
  presets[key] = presets[oldName];
  delete presets[oldName];
  _setPresets(presets);
  showToast(tr('presets.renamed', { old: oldName, name: key }) || 'Renamed: ' + oldName + ' → ' + key);
  _refreshPresetMenu();
}

export function deletePreset(name: string): void {
  const { tr } = getAppApi();
  const { showToast } = getNavApi();
  const presets = _getPresets();
  delete presets[name];
  _setPresets(presets);
  showToast(tr('presets.deleted', { name: name }) || 'Preset deleted: ' + name);
  _refreshPresetMenu();
}

export function togglePresetMenu(): void {
  const menu = document.getElementById('presetDropdown');
  if (!menu) return;
  const isVisible = menu.style.display !== 'none';
  menu.style.display = isVisible ? 'none' : 'block';
  if (!isVisible) _refreshPresetMenu();
}
