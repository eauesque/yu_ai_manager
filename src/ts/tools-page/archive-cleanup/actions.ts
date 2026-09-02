/**
 * archive-cleanup/actions.ts -- action management + execution.
 *
 * Handles per-pair action selection (skip/delete_archive/delete_folder),
 * bulk selection helpers, and the execute API call.
 */

import { apiFetch } from '../api';
import {
  renderError,
  renderExecuteBanner,
  type ArchivePair,
  type ExecuteResult,
  type LlmResult,
} from './render';
import {
  _currentPairs,
  _pairActions,
  _llmResults,
  _t,
  _getDisplayRate,
  setCurrentPairs,
  setPairActions,
  setLlmResults,
  setPage,
} from './state';
import { _saveSession, _clearSession, _removeGuard } from './session';
import { _rerender } from './core';

// ── Action Management ────────────────────────────────────────────

export function acActionChange(idx: number, action: string): void {
  _pairActions.set(idx, action);
  _saveSession();
}

export function acSelectAll(action: string): void {
  _currentPairs.forEach((_, i) => {
    _pairActions.set(i, action);
  });
  _saveSession();
  _rerender();
}

export function acSelectAllPerfect(action: string): void {
  _currentPairs.forEach((p, i) => {
    if (_getDisplayRate(p) >= 99.9) {
      _pairActions.set(i, action);
    }
  });
  _saveSession();
  _rerender();
}

// ── Execute ──────────────────────────────────────────────────────

export async function acExecute(): Promise<void> {
  const resultBox = document.getElementById('acResult');
  const execBtn = document.getElementById('acExecuteBtn') as HTMLButtonElement | null;
  if (!resultBox || _currentPairs.length === 0) return;

  // Only send non-skip actions (reduce payload size)
  const actions: { archive_path: string; folder_path: string; action: string }[] = [];
  _currentPairs.forEach((p, i) => {
    const action = _pairActions.get(i) || 'skip';
    if (action !== 'skip') {
      actions.push({
        archive_path: p.archive_path,
        folder_path: p.folder_path,
        action,
      });
    }
  });

  const deleteCount = actions.length;
  if (deleteCount === 0) {
    resultBox.innerHTML = renderError(_t('tools.ac_nothing_selected', 'No actions selected (all skipped).'));
    return;
  }

  const confirmMsg = _t(
    'tools.ac_confirm',
    `Are you sure you want to execute ${deleteCount} deletion(s)? This cannot be undone.`,
  ).replace('${deleteCount}', String(deleteCount));

  if (!confirm(confirmMsg)) return;

  if (execBtn) execBtn.disabled = true;

  try {
    const res = await apiFetch('/api/tools/archive-cleanup/execute', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ actions }),
    });
    const data: ExecuteResult & { error?: string } = await res.json();

    if (data.error) {
      resultBox.innerHTML = renderError(data.error);
      return;
    }

    // Build a Set of successfully deleted paths
    const deletedSet = new Set<string>(data.deleted_paths || []);

    // Remove successfully deleted pairs, remap corresponding actions and LLM results
    const newPairs: ArchivePair[] = [];
    const newActions = new Map<number, string>();
    const newLlm = new Map<number, LlmResult>();
    _currentPairs.forEach((p, oldIdx) => {
      const act = _pairActions.get(oldIdx) || 'skip';
      const targetPath = act === 'delete_archive' ? p.archive_path : p.folder_path;
      if (act !== 'skip' && deletedSet.has(targetPath)) {
        return; // Successfully deleted -> remove from list
      }
      const newIdx = newPairs.length;
      newPairs.push(p);
      // Revert failed deletions back to skip
      if (act !== 'skip' && !deletedSet.has(targetPath)) {
        newActions.set(newIdx, 'skip');
      } else {
        newActions.set(newIdx, act);
      }
      // Carry over LLM results
      const llm = _llmResults.get(oldIdx);
      if (llm) newLlm.set(newIdx, llm);
    });

    setCurrentPairs(newPairs);
    setPairActions(newActions);
    setLlmResults(newLlm);

    if (_currentPairs.length === 0) {
      // All pairs deleted
      resultBox.innerHTML = renderExecuteBanner(data);
      _clearSession();
      _removeGuard();
    } else {
      // Re-render remaining pairs (banner + list)
      _saveSession();
      setPage(1);
      _rerender();
      // Insert banner at the top
      resultBox.insertAdjacentHTML('afterbegin', renderExecuteBanner(data));
      if (execBtn) execBtn.disabled = false;
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML = renderError(msg);
    if (execBtn) execBtn.disabled = false;
  }
}
