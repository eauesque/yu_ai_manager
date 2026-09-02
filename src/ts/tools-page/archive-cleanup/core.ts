/**
 * archive-cleanup/core.ts -- entry point, scan, sort/filter/rerender.
 *
 * Re-exports all public functions so that the existing import in
 * tools-page/index.ts (`from './archive-cleanup/core'`) keeps working.
 *
 * Session persistence: scan results and selections are stored in
 * sessionStorage so they survive accidental page navigation.
 * A beforeunload warning fires when there are unsaved selections.
 */

import { apiFetch } from '../api';
import {
  renderScanning,
  renderNoPairs,
  renderError,
  renderPairs,
  renderLlmResult,
  PAGE_SIZE,
  type ArchivePair,
} from './render';
import {
  _currentPairs,
  _pairActions,
  _llmResults,
  _sortKey,
  _filterKey,
  _page,
  _t,
  _getDisplayRate,
  setCurrentPairs,
  setPairActions,
  setLlmResults,
  setSortKey,
  setFilterKey,
  setPage,
} from './state';
import {
  _saveSession,
  _clearSession,
  _restoreSession,
  _installGuard,
  _removeGuard,
} from './session';

// ── Re-exports (actions.ts) ─────────────────────────────────────
export { acActionChange, acSelectAll, acSelectAllPerfect, acExecute } from './actions';

// ── Re-exports (llm.ts) ─────────────────────────────────────────
export {
  acLlmVerify,
  acLlmVerifyAll,
  acLoadLlmConfig,
  acSaveLlmConfig,
  acOnLlmEngineChange,
  acRefreshModels,
} from './llm';

// ── Rerender (exported for sibling modules) ─────────────────────

export function _rerender(): void {
  const resultBox = document.getElementById('acResult');
  if (!resultBox || _currentPairs.length === 0) return;

  const sorted = _sortedFiltered();
  const perfectCountAll = _currentPairs.filter((p) => _getDisplayRate(p) >= 99.9).length;

  resultBox.innerHTML = renderPairs(
    sorted, _pairActions, _page, _currentPairs.length, perfectCountAll,
  );

  // Restore sort/filter select values
  const sortSel = document.getElementById('acSort') as HTMLSelectElement | null;
  if (sortSel) sortSel.value = _sortKey;
  const filterSel = document.getElementById('acFilter') as HTMLSelectElement | null;
  if (filterSel) filterSel.value = _filterKey;

  // Restore LLM results
  _llmResults.forEach((result, idx) => {
    const el = document.getElementById(`acLlmResult_${idx}`);
    if (el) el.innerHTML = renderLlmResult(result);
  });
}

// ── Sort helpers (internal) ─────────────────────────────────────

function _sortedFiltered(): ArchivePair[] {
  type Tagged = ArchivePair & { _originalIdx: number };
  let list: Tagged[] = _currentPairs.map((p, i) => ({ ...p, _originalIdx: i }));

  if (_filterKey === 'perfect') {
    list = list.filter((p) => _getDisplayRate(p) >= 99.9);
  } else if (_filterKey === 'imperfect') {
    list = list.filter((p) => _getDisplayRate(p) < 99.9);
  }

  switch (_sortKey) {
    case 'rate_desc':
      list.sort((a, b) => _getDisplayRate(b) - _getDisplayRate(a));
      break;
    case 'rate_asc':
      list.sort((a, b) => _getDisplayRate(a) - _getDisplayRate(b));
      break;
    case 'name':
      list.sort((a, b) => a.archive_name.localeCompare(b.archive_name));
      break;
    case 'size':
      list.sort((a, b) => b.archive_size - a.archive_size);
      break;
  }
  return list;
}

// ── Auto-restore on tools page load ──────────────────────────────

export function acTryRestore(): void {
  if (_restoreSession()) {
    const resultBox = document.getElementById('acResult');
    const execBtn = document.getElementById('acExecuteBtn') as HTMLButtonElement | null;
    if (resultBox) {
      _rerender();
      if (execBtn) execBtn.disabled = false;
      _installGuard();
    }
  }
}

// ── Scan ─────────────────────────────────────────────────────────

export async function acScan(): Promise<void> {
  const resultBox = document.getElementById('acResult');
  const execBtn = document.getElementById('acExecuteBtn') as HTMLButtonElement | null;
  if (!resultBox) return;

  const pathEl = document.getElementById('acPath') as HTMLInputElement | null;
  const recurEl = document.getElementById('acRecursive') as HTMLInputElement | null;
  const path = pathEl?.value.trim() || '';
  const recursive = recurEl?.checked || false;

  if (!path) {
    resultBox.innerHTML = renderError(_t('tools.ac_path_required', 'Please enter a directory path.'));
    return;
  }

  resultBox.innerHTML = renderScanning();
  if (execBtn) execBtn.disabled = true;
  setCurrentPairs([]);
  setPairActions(new Map());
  setLlmResults(new Map());
  setSortKey('rate_desc');
  setFilterKey('all');
  setPage(1);
  _clearSession();
  _removeGuard();

  try {
    const res = await apiFetch('/api/tools/archive-cleanup/scan', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ path, recursive }),
    });
    const data = await res.json();

    if (data.error) {
      resultBox.innerHTML = renderError(data.error);
      return;
    }

    const pairs: ArchivePair[] = data.pairs || [];
    setCurrentPairs(pairs);

    if (pairs.length === 0) {
      resultBox.innerHTML = renderNoPairs();
      return;
    }

    _saveSession();
    _installGuard();
    _rerender();
    if (execBtn) execBtn.disabled = false;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML = renderError(msg);
  }
}

// ── Sort / Filter / Page ─────────────────────────────────────────

export function acSort(): void {
  const sel = document.getElementById('acSort') as HTMLSelectElement | null;
  if (sel) setSortKey(sel.value);
  setPage(1);
  _saveSession();
  _rerender();
}

export function acFilter(): void {
  const sel = document.getElementById('acFilter') as HTMLSelectElement | null;
  if (sel) setFilterKey(sel.value);
  setPage(1);
  _saveSession();
  _rerender();
}

export function acPage(p: number): void {
  setPage(p);
  _saveSession();
  _rerender();
  // Scroll to the top of the page
  document.getElementById('acResult')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

// ── Folder Picker ────────────────────────────────────────────────

export async function acPickFolder(): Promise<void> {
  const targetEl = document.getElementById('acPath') as HTMLInputElement | null;
  if (!targetEl) return;

  const current = targetEl.value.trim();
  try {
    const res = await fetch(
      '/api/tools/select-folder' + (current ? '?initial=' + encodeURIComponent(current) : ''),
    );
    const data: { path?: string; cancelled?: boolean; error?: string; message?: string } =
      await res.json();
    if (data.path) {
      targetEl.value = data.path;
      return;
    }
    if (data.cancelled) return;
    if (data.message) {
      alert(data.message);
      return;
    }
    if (data.error) {
      alert(
        _t(
          'tools.folder_dialog_failed',
          'Could not open folder picker dialog.\nPlease enter the path manually.',
        ),
      );
    }
  } catch {
    alert(
      _t(
        'tools.folder_dialog_failed',
        'Could not open folder picker dialog.\nPlease enter the path manually.',
      ),
    );
  }
}
