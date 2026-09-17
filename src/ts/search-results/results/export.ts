/**
 * results/export.ts
 *
 * CSV export and Recipe JSON export for search results.
 *
 * Converted from runtime-results-export.js (IIFE -> named exports).
 */

import { getMode } from './grouping-utils';
import { searchPager } from '../search/pagination';
import { getAppApi } from '../../shared/browser-apis';

// eslint-disable-next-line @typescript-eslint/no-explicit-any
type ResultRecord = Record<string, any>;

/** Absolute hard cap — server-side batch limit. */
const EXPORT_MAX = 500;

const CSV_LIMIT_LS_KEY = 'yu:csv_export_limit';
const CSV_LIMIT_OPTIONS = [50, 100, 200, 300, 500];

// Store raw results from last search
let _exportData: ResultRecord[] = [];

// Shared export limit for both CSV and Recipe JSON — persisted to localStorage
let _csvLimit: number = (() => {
  try {
    const v = parseInt(localStorage.getItem(CSV_LIMIT_LS_KEY) || '100', 10);
    return CSV_LIMIT_OPTIONS.includes(v) ? v : 100;
  } catch (_) {
    return 100;
  }
})();

function _isGroupedMode(): boolean {
  const mode = getMode();
  return mode === 'folder' || mode === 'zip';
}

function _getCsvLimit(): number {
  return _csvLimit;
}

function _getTotalCount(): number {
  return searchPager.getTotalCount() || _exportData.length;
}

function _updateBtnLabel(btn: HTMLElement, label: string): void {
  if (!btn) return;
  const count = _getCsvLimit();
  btn.textContent = '';
  const icon = document.createElement('span');
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '📥';
  btn.appendChild(icon);
  btn.appendChild(document.createTextNode(' ' + label + ' (' + count + ')'));
  if (label === 'CSV') {
    const _t = getAppApi().tr;
    btn.title = _t('search.export_csv_hint', { count }) as string ||
      'Export ' + count + ' results as CSV';
  } else {
    btn.title = label + '（' + count + '件まで）をダウンロード';
  }
}

function _disableSplitBtn(
  btn: HTMLElement | null,
  chev: HTMLElement | null,
  label: string,
  tooltip: string,
): void {
  if (btn) {
    (btn as HTMLButtonElement).disabled = true;
    btn.style.opacity = '0.45';
    btn.style.cursor = 'not-allowed';
    btn.title = tooltip;
    btn.textContent = '';
    const icon = document.createElement('span');
    icon.setAttribute('aria-hidden', 'true');
    icon.textContent = '📥';
    btn.appendChild(icon);
    btn.appendChild(document.createTextNode(' ' + label));
  }
  if (chev) {
    (chev as HTMLButtonElement).disabled = true;
    chev.style.opacity = '0.45';
    chev.style.cursor = 'not-allowed';
  }
}

function _enableSplitBtn(btn: HTMLElement | null, chev: HTMLElement | null): void {
  if (btn) {
    (btn as HTMLButtonElement).disabled = false;
    btn.style.opacity = '';
    btn.style.cursor = '';
  }
  if (chev) {
    (chev as HTMLButtonElement).disabled = false;
    chev.style.opacity = '';
    chev.style.cursor = '';
  }
}

/** Apply state to a split button group (CSV or Recipe JSON). */
function _applySplitGroupState(
  wrapId: string,
  btnId: string,
  chevId: string,
  label: string,
): void {
  const wrap = document.getElementById(wrapId) as HTMLElement | null;
  const btn = document.getElementById(btnId) as HTMLElement | null;
  const chev = document.getElementById(chevId) as HTMLElement | null;

  if (_exportData.length === 0) {
    if (wrap) wrap.style.display = 'none';
    return;
  }
  if (wrap) wrap.style.display = '';

  if (_isGroupedMode()) {
    _disableSplitBtn(btn, chev, label, 'グループ表示中は出力できません — 通常表示に切り替えてください');
  } else {
    _enableSplitBtn(btn, chev);
    if (btn) _updateBtnLabel(btn, label);
  }
}

function _applyExportBtnState(): void {
  _applySplitGroupState('exportCsvSplit', 'exportCsvBtn', 'exportCsvChevron', 'CSV');
}

function _applyRecipeJsonBtnState(): void {
  _applySplitGroupState('exportRecipeJsonSplit', 'exportRecipeJsonBtn', 'exportRecipeJsonChevron', 'Recipe JSON');
}

function _applyAllExportBtns(): void {
  _applyExportBtnState();
  _applyRecipeJsonBtnState();
}

export function setExportData(results: ResultRecord[]): void {
  _exportData = (results || []).slice(0, EXPORT_MAX);
  _applyAllExportBtns();
}

/**
 * loadMore ページが追加されたときに呼ぶ。
 * _exportData が EXPORT_MAX 未満の場合のみ新結果を末尾に追加する。
 * EXPORT_MAX 到達後は no-op。
 *
 * Invariant: _exportData.length <= EXPORT_MAX を常に満たす
 * （setExportData と accumExportData の両エントリポイントで保証）。
 * エクスポート時は _exportData.slice(0, _csvLimit) で切り出す。
 *
 * @param results - regex フィルタ済みの loadMore 結果
 * @remarks Does not call _applyAllExportBtns — button labels are not updated per page.
 */
export function accumExportData(results: unknown[]): void {
  if (_exportData.length >= EXPORT_MAX) return;
  const need = EXPORT_MAX - _exportData.length;
  _exportData = [
    ..._exportData,
    ...(results.filter((r) => r != null) as ResultRecord[]).slice(0, need),
  ];
}

/** Called by grouping module on mode switch to show/hide buttons */
export function updateExportCsvVisibility(): void {
  _applyAllExportBtns();
}

/** Called when CSV limit changes (legacy compat) */
export function updateExportCsvLabel(): void {
  const wrap = document.getElementById('exportCsvSplit') as HTMLElement | null;
  const btn = document.getElementById('exportCsvBtn') as HTMLElement | null;
  if (btn && wrap && wrap.style.display !== 'none') _updateBtnLabel(btn, 'CSV');
}

/** Set shared export limit and persist to localStorage. */
export function setCsvLimit(n: number): void {
  if (!CSV_LIMIT_OPTIONS.includes(n)) return;
  _csvLimit = n;
  try { localStorage.setItem(CSV_LIMIT_LS_KEY, String(n)); } catch (_) { /* storage unavailable */ }
  _applyAllExportBtns();
}

/** Show the export limit picker dropdown anchored to the trigger element. */
export function showCsvLimitDropdown(triggerEl: HTMLElement): void {
  const existingId = 'csvLimitDropdown';
  const existing = document.getElementById(existingId);
  if (existing) {
    existing.remove();
    return;
  }

  const menu = document.createElement('div');
  menu.id = existingId;
  menu.setAttribute('role', 'menu');
  menu.className = 'export-limit-dropdown';
  menu.style.cssText = 'position:fixed;z-index:9001;';

  const rect = triggerEl.getBoundingClientRect();
  menu.style.top = (rect.bottom + 4) + 'px';
  menu.style.right = (window.innerWidth - rect.right) + 'px';

  for (const n of CSV_LIMIT_OPTIONS) {
    const item = document.createElement('button');
    item.type = 'button';
    item.setAttribute('role', 'menuitem');
    item.className = 'export-limit-item' + (n === _csvLimit ? ' active' : '');
    item.textContent = n + ' 件';
    item.addEventListener('click', () => {
      setCsvLimit(n);
      menu.remove();
    });
    menu.appendChild(item);
  }

  document.body.appendChild(menu);

  const dismiss = (e: MouseEvent): void => {
    if (!menu.contains(e.target as Node) && e.target !== triggerEl) {
      menu.remove();
      document.removeEventListener('click', dismiss, true);
    }
  };
  requestAnimationFrame(() => document.addEventListener('click', dismiss, true));
}

function escapeCsvField(val: unknown): string {
  if (val == null) return '';
  const s = String(val);
  if (s.indexOf('"') >= 0 || s.indexOf(',') >= 0 || s.indexOf('\n') >= 0 || s.indexOf('\r') >= 0) {
    return '"' + s.replace(/"/g, '""') + '"';
  }
  return s;
}

function _buildCsv(data: ResultRecord[]): void {
  const headers = ['id', 'filename', 'folder', 'path', 'meta_source', 'mtime', 'positive', 'negative'];
  const rows: string[] = [headers.join(',')];

  for (let i = 0; i < data.length; i++) {
    const r = data[i];
    const p: string = r.path || '';
    const filename = p.replace(/.*[/\\]/, '');
    const folder = filename.length < p.length ? p.substring(0, p.length - filename.length - 1) : '';
    const mtime = r.mtime ? new Date(r.mtime * 1000).toISOString() : '';
    rows.push([
      escapeCsvField(r.id),
      escapeCsvField(filename),
      escapeCsvField(folder),
      escapeCsvField(r.path),
      escapeCsvField(r.meta_source),
      escapeCsvField(mtime),
      escapeCsvField(r.positive),
      escapeCsvField(r.negative)
    ].join(','));
  }

  const bom = '﻿';
  const blob = new Blob([bom + rows.join('\n')], { type: 'text/csv;charset=utf-8' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = 'search_results_' + new Date().toISOString().slice(0, 10) + '.csv';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

function _setBtnLoading(btn: HTMLElement, label: string): void {
  btn.textContent = '';
  const icon = document.createElement('span');
  icon.setAttribute('aria-hidden', 'true');
  icon.textContent = '📥';
  btn.appendChild(icon);
  btn.appendChild(document.createTextNode(' ' + label + ' ...'));
}

export async function exportResultsCsv(): Promise<void> {
  if (_exportData.length === 0) return;

  const maxRows = _getCsvLimit();

  // If we already have enough data, export directly
  if (_exportData.length >= maxRows) {
    _buildCsv(_exportData.slice(0, maxRows));
    return;
  }

  // Need more data -- fetch from API with the correct limit
  const searchParams = searchPager.getParams();
  if (!searchParams) {
    _buildCsv(_exportData.slice(0, maxRows));
    return;
  }

  const btn = document.getElementById('exportCsvBtn');
  if (btn) _setBtnLoading(btn, 'CSV');

  try {
    const params = new URLSearchParams(searchParams);
    params.set('limit', String(maxRows));
    params.set('offset', '0');
    const response = await getAppApi().apiFetch('/api/search?' + params);
    if (response.ok) {
      const data = await response.json();
      if (data.results && data.results.length > 0) {
        _buildCsv(data.results.slice(0, maxRows));
        if (btn) _updateBtnLabel(btn, 'CSV');
        return;
      }
    }
  } catch (err) {
    console.error('CSV fetch failed:', err);
  }

  if (btn) _updateBtnLabel(btn, 'CSV');
  _buildCsv(_exportData.slice(0, maxRows));
}

export async function exportResultsRecipeJson(): Promise<void> {
  if (_exportData.length === 0) return;
  if (_isGroupedMode()) return;

  const maxRows = Math.min(_getCsvLimit(), EXPORT_MAX);

  // Collect IDs — fetch full result set if not yet loaded
  const total = _getTotalCount();
  let ids: number[] = _exportData.slice(0, maxRows).map((r: ResultRecord) => r.id as number).filter(Boolean);

  const searchParams = searchPager.getParams();
  if (searchParams && _exportData.length < Math.min(total, maxRows)) {
    const recipeBtn = document.getElementById('exportRecipeJsonBtn');
    if (recipeBtn) _setBtnLoading(recipeBtn, 'Recipe JSON');
    try {
      const params = new URLSearchParams(searchParams);
      params.set('limit', String(maxRows));
      params.set('offset', '0');
      const response = await getAppApi().apiFetch('/api/search?' + params);
      if (response.ok) {
        const data = await response.json();
        if (data.results && data.results.length > 0) {
          ids = (data.results as ResultRecord[]).slice(0, maxRows).map((r) => r.id as number).filter(Boolean);
        }
      }
    } catch (err) {
      console.error('recipe JSON pre-fetch failed:', err);
    }
    _applyRecipeJsonBtnState();
  }

  if (ids.length === 0) return;

  try {
    const response = await getAppApi().apiFetch('/api/recipe/export/batch', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ file_ids: ids }),
    });
    if (!response.ok) {
      console.error('recipe export batch failed:', response.status);
      return;
    }
    const result = await response.json();
    const recipes: unknown[] = result.data?.recipes ?? [];
    const blob = new Blob(
      [JSON.stringify({ schema: 'yu://recipe-batch/1', recipes }, null, 2)],
      { type: 'application/json' },
    );
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'recipes_' + new Date().toISOString().slice(0, 10) + '.json';
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  } catch (err) {
    console.error('recipe JSON export failed:', err);
  }
}
