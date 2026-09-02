/**
 * archive-cleanup/llm.ts -- LLM verification (single + batch).
 *
 * LLM engine configuration UI is in llm-config.ts.
 * This module handles single/batch LLM verification of archive-folder pairs.
 */

import { apiFetch } from '../api';
import {
  renderError,
  renderLlmResult,
  renderLlmVerifying,
  type LlmResult,
} from './render';
import {
  _currentPairs,
  _llmResults,
  _t,
  _getDisplayRate,
} from './state';
import { _saveSession } from './session';

// Re-export config functions for backward compatibility
export {
  acLoadLlmConfig,
  acSaveLlmConfig,
  acOnLlmEngineChange,
  acRefreshModels,
} from './llm-config';

// -- LLM Verify (single) --

export async function acLlmVerify(index: number): Promise<void> {
  const resultEl = document.getElementById(`acLlmResult_${index}`);
  if (!resultEl) return;

  const pair = _currentPairs[index];
  if (!pair) return;

  resultEl.innerHTML = renderLlmVerifying();

  try {
    const res = await apiFetch('/api/tools/archive-cleanup/llm-verify', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        archive_path: pair.archive_path,
        folder_path: pair.folder_path,
        pair_info: pair,
      }),
    });
    const data = await res.json();

    if (data.error) {
      resultEl.innerHTML = renderError(data.error);
      return;
    }

    _showLlmResult(index, data);
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultEl.innerHTML = renderError(msg);
  }
}

// -- LLM Verify (batch) --

export async function acLlmVerifyAll(): Promise<void> {
  const imperfect = _currentPairs
    .map((p, i) => ({ pair: p, idx: i }))
    .filter((x) => _getDisplayRate(x.pair) < 99.9);

  if (imperfect.length === 0) return;

  const msg = _t(
    'tools.ac_llm_verify_all_confirm',
    `LLM verify ${imperfect.length} pair(s) with < 100% match? This may take a while.`,
  ).replace('${count}', String(imperfect.length));
  if (!confirm(msg)) return;

  for (const { idx } of imperfect) {
    const el = document.getElementById(`acLlmResult_${idx}`);
    if (el) el.innerHTML = renderLlmVerifying();
  }

  // Split into chunks of 50 and send (API limit: 50 pairs/batch)
  const BATCH_SIZE = 50;
  for (let offset = 0; offset < imperfect.length; offset += BATCH_SIZE) {
    const chunk = imperfect.slice(offset, offset + BATCH_SIZE);
    try {
      const pairsPayload = chunk.map(({ pair }) => ({
        archive_path: pair.archive_path,
        folder_path: pair.folder_path,
        pair_info: pair,
      }));

      const res = await apiFetch('/api/tools/archive-cleanup/llm-verify-batch', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pairs: pairsPayload }),
      });
      const data = await res.json();

      if (data.error) {
        for (const { idx } of chunk) {
          const el = document.getElementById(`acLlmResult_${idx}`);
          if (el) el.innerHTML = renderError(data.error);
        }
        continue;
      }

      const results: { index: number; result?: LlmResult; error?: string }[] = data.results || [];
      results.forEach((r, i) => {
        const idx = chunk[i]?.idx;
        if (idx == null) return;
        if (r.error) {
          const el = document.getElementById(`acLlmResult_${idx}`);
          if (el) el.innerHTML = renderError(r.error);
        } else if (r.result) {
          _showLlmResult(idx, r.result);
        }
      });
    } catch (err: unknown) {
      const errMsg = err instanceof Error ? err.message : String(err);
      for (const { idx } of chunk) {
        const el = document.getElementById(`acLlmResult_${idx}`);
        if (el) el.innerHTML = renderError(errMsg);
      }
    }
  }
}

function _showLlmResult(index: number, result: LlmResult): void {
  _llmResults.set(index, result);
  _saveSession();
  const el = document.getElementById(`acLlmResult_${index}`);
  if (!el) return;
  el.innerHTML = renderLlmResult(result);
}
