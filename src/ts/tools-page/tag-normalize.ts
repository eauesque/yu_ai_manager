/**
 * tag-normalize.ts -- Tag normalization preview and execution.
 * Converted from tools-tag-normalize.js
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch } from './api';
import { loadDbInfo, loadTagCount } from './db-info';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface NormalizeResult {
  changes: number;
  normalized?: number;
  examples: Array<{ before: string; after: string }>;
}

export async function previewNormalize(): Promise<void> {
  const resultBox = document.getElementById('normalizeResult');
  if (!resultBox) return;
  resultBox.innerHTML =
    '<div class="spinner-overlay"><div class="spinner"></div><span class="spinner-text">' +
    _t('tools.analyzing', 'Analyzing...') +
    '</span></div>';
  resultBox.classList.add('show');

  try {
    const response = await apiFetch('/api/tools/normalize-tags?dry_run=true');
    const data: NormalizeResult = await response.json();

    if (data.changes === 0) {
      resultBox.innerHTML =
        '<p>\u2713 ' +
        _t('tools.no_normalize_needed', 'No tags need normalization') +
        '</p>';
      return;
    }

    let html =
      '<p>' +
      _t('tools.normalize_items', 'Items to normalize') +
      ': ' +
      data.changes +
      '</p>';
    html += '<div style="margin-top: 10px; max-height: 300px; overflow-y: auto;">';

    data.examples.forEach((ex) => {
      html += '<div style="margin: 5px 0; padding: 5px; background: rgba(0,0,0,0.2); border-radius: 3px;">';
      html += `<span style="color: #e74c3c;">${ex.before}</span> \u2192 `;
      html += `<span style="color: #2ecc71;">${ex.after}</span>`;
      html += '</div>';
    });

    html += '</div>';
    resultBox.innerHTML = html;
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color: #e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      msg +
      '</p>';
  }
}

export async function executeNormalize(): Promise<void> {
  if (
    !confirm(
      _t('tools.normalize_confirm', 'Normalize tags? This cannot be undone.'),
    )
  )
    return;

  const resultBox = document.getElementById('normalizeResult');
  if (!resultBox) return;
  resultBox.innerHTML =
    '<div class="spinner-overlay"><div class="spinner"></div><span class="spinner-text">' +
    _t('tools.normalizing', 'Normalizing...') +
    '</span></div>';
  resultBox.classList.add('show');

  try {
    const response = await apiFetch('/api/tools/normalize-tags');
    const data: NormalizeResult = await response.json();

    resultBox.innerHTML =
      '<p style="color: #2ecc71;">\u2713 ' +
      _t('tools.normalized_count', 'Normalized') +
      ': ' +
      data.normalized +
      '</p>';

    loadTagCount();
    loadDbInfo();
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : String(err);
    resultBox.innerHTML =
      '<p style="color: #e74c3c;">' +
      _t('tools.error', 'Error') +
      ': ' +
      msg +
      '</p>';
  }
}
