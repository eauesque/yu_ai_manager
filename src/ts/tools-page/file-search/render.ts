/**
 * file-search/render.ts -- File search results rendering.
 * Converted from tools-ui-file-search-render.js
 */

import { getAppApi } from '../../shared/browser-apis';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function escapeHtml(value: unknown): string {
  return String(value || '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export interface FileSearchResult {
  path?: string;
  meta_source?: string;
  format?: string;
  has_prompt?: boolean;
  size?: number;
  is_deleted?: boolean;
}

export interface FileSearchData {
  results?: FileSearchResult[];
  total: number;
}

export function renderSearchPrompt(): string {
  return (
    '<div style="color:#888;font-size:13px;">' +
    _t('tools.enter_search_query', 'Enter search query') +
    '</div>'
  );
}

export function renderSearching(): string {
  return (
    '<div style="color:#888;font-size:13px;">' +
    _t('tools.searching', 'Searching...') +
    '</div>'
  );
}

export function renderSearchError(message: string): string {
  return (
    '<div style="color:#e74c3c;font-size:13px;">' +
    _t('tools.error', 'Error') +
    ': ' +
    escapeHtml(message) +
    '</div>'
  );
}

export function renderSearchResults(data: FileSearchData): string {
  if (!data.results || data.results.length === 0) {
    return (
      '<div style="color:#888;font-size:13px;">' +
      _t('tools.no_results', 'No results') +
      (data.total > 0
        ? ' (' + data.total + ' ' + _t('tools.items', 'items') + ' 0)'
        : '') +
      '</div>'
    );
  }

  let html =
    '<div style="font-size:13px;color:#888;margin-bottom:8px;">' +
    data.total +
    ' ' +
    _t('tools.items', 'items') +
    (data.total > data.results.length
      ? ' (' +
        _t('tools.showing_first', 'showing first') +
        ' ' +
        data.results.length +
        ')'
      : '') +
    '</div>';
  html +=
    '<div style="overflow-x:auto;"><table style="width:100%;border-collapse:collapse;font-size:12px;">';
  html +=
    '<tr style="border-bottom:1px solid rgba(128,128,128,0.3);text-align:left;">' +
    '<th style="padding:6px 8px;">' +
    _t('tools.th_path', 'Path') +
    '</th>' +
    '<th style="padding:6px 8px;">' +
    _t('tools.th_source', 'Source') +
    '</th>' +
    '<th style="padding:6px 8px;">' +
    _t('tools.th_format', 'Format') +
    '</th>' +
    '<th style="padding:6px 8px;">' +
    _t('tools.th_prompt', 'Prompt') +
    '</th>' +
    '<th style="padding:6px 8px;">' +
    _t('tools.th_size', 'Size') +
    '</th>' +
    '<th style="padding:6px 8px;">' +
    _t('tools.th_deleted', 'Deleted') +
    '</th>' +
    '</tr>';

  for (let i = 0; i < data.results.length; i += 1) {
    const r = data.results[i];
    const pathParts = (r.path || '').replace(/\\/g, '/').split('/');
    const fileName = pathParts[pathParts.length - 1] || r.path || '';
    const dirPath = pathParts.slice(0, -1).join('/');
    const sizeKB = r.size ? (r.size / 1024).toFixed(0) + ' KB' : '-';
    const metaColor = r.meta_source === 'unknown' ? '#e74c3c' : '#2ecc71';
    const promptIcon = r.has_prompt ? '\u2705' : '\u274C';
    const delIcon = r.is_deleted ? '\uD83D\uDDD1\uFE0F' : '';

    html +=
      '<tr style="border-bottom:1px solid rgba(128,128,128,0.15);">' +
      '<td style="padding:6px 8px;max-width:400px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;" title="' +
      escapeHtml(r.path) +
      '">' +
      '<span style="color:#888;font-size:11px;">' +
      escapeHtml(dirPath) +
      '/</span><br>' +
      '<b>' +
      escapeHtml(fileName) +
      '</b>' +
      '</td>' +
      '<td style="padding:6px 8px;"><span style="color:' +
      metaColor +
      ';font-weight:600;">' +
      escapeHtml(r.meta_source) +
      '</span></td>' +
      '<td style="padding:6px 8px;">' +
      escapeHtml(r.format || '-') +
      '</td>' +
      '<td style="padding:6px 8px;text-align:center;">' +
      promptIcon +
      '</td>' +
      '<td style="padding:6px 8px;white-space:nowrap;">' +
      sizeKB +
      '</td>' +
      '<td style="padding:6px 8px;">' +
      delIcon +
      '</td>' +
      '</tr>';
  }

  html += '</table></div>';
  return html;
}
