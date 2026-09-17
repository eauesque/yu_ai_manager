/**
 * ai-analysis/render.ts -- AI analysis rendering helpers.
 * Converted from tools-ai-analysis-render.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { _esc } from './helpers';
import type { TrendHistoryItem } from './types';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface AiStats {
  total_analyzed: number;
  total_files: number;
  styles: Array<{ style: string; count: number }>;
}

interface TrendsResult {
  style_tendency?: string;
  strengths?: string;
  weaknesses?: string;
  frequent_tags?: string[];
  recommendations?: string[];
  unexplored?: string[];
  raw?: string;
}

export function renderAiStats(
  el: HTMLElement | null,
  stats: AiStats,
): void {
  if (!el) return;
  if (stats.total_analyzed > 0) {
    let html =
      '\uD83D\uDCCA ' +
      _t('tools.analyzed', 'Analyzed') +
      ': ' +
      `<b>${stats.total_analyzed}</b> / ${stats.total_files} ` +
      _t('tools.files', 'files');
    if (stats.styles.length > 0) {
      html +=
        ' \uFF5C ' +
        _t('tools.style', 'Style') +
        ': ' +
        stats.styles.map((s) => `${_esc(s.style)}(${s.count})`).join(', ');
    }
    el.innerHTML = html;
    return;
  }
  el.innerHTML =
    '\uD83D\uDCCA ' + _t('tools.no_analysis_yet', 'No files analyzed yet');
}

export function renderBatchProgress(resultBox: HTMLElement): void {
  resultBox.classList.add('show');
  resultBox.innerHTML = `
    <div style="padding:10px;">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">
        <span>\uD83E\uDDE0 <strong>${_t('tools.ai_analyzing', 'AI analyzing...')}</strong></span>
        <button id="aiCancelBtn" data-action="toolsPageApi.cancelAiBatch"
                style="padding:2px 10px;font-size:11px;border:1px solid rgba(239,68,68,0.5);color:var(--text);background:transparent;border-radius:4px;cursor:pointer;"
                data-i18n="tools.cancel">Cancel</button>
      </div>
      <div style="background:rgba(0,0,0,0.3);border-radius:4px;height:24px;overflow:hidden;margin:8px 0;">
        <div id="aiProgressBar" style="height:100%;background:linear-gradient(90deg,#e667ea,#764ba2);width:0%;transition:width 0.3s;border-radius:4px;"></div>
      </div>
      <div id="aiProgressText" style="font-size:12px;color:#888;">${_t('tools.starting', 'Starting...')}</div>
    </div>
  `;
}

export function renderTrendsLoading(resultBox: HTMLElement): void {
  resultBox.classList.add('show');
  resultBox.innerHTML =
    '<div class="spinner-overlay"><div class="spinner"></div><span class="spinner-text">' +
    _t('tools.analyzing_trends', 'Analyzing prompt trends...') +
    '</span></div>';
}

export function renderTrendsResult(
  resultBox: HTMLElement,
  r: TrendsResult,
): void {
  let html =
    '<h3 style="margin-bottom:10px;">\uD83D\uDCCA ' +
    _t('tools.prompt_trends', 'Prompt Trend Analysis') +
    '</h3>';

  if (r.style_tendency)
    html +=
      '<p><b>\uD83C\uDFA8 ' +
      _t('tools.style_tendency', 'Style tendency:') +
      '</b> ' +
      _esc(r.style_tendency) +
      '</p>';
  if (r.strengths)
    html +=
      '<p><b>\uD83D\uDCAA ' +
      _t('tools.strengths', 'Strengths:') +
      '</b> ' +
      _esc(r.strengths) +
      '</p>';
  if (r.weaknesses)
    html +=
      '<p><b>\uD83D\uDCDD ' +
      _t('tools.weaknesses', 'Areas for improvement:') +
      '</b> ' +
      _esc(r.weaknesses) +
      '</p>';

  if (r.frequent_tags?.length) {
    html +=
      '<p><b>\uD83C\uDFF7\uFE0F ' +
      _t('tools.frequent_tags', 'Frequent tags:') +
      '</b> ' +
      r.frequent_tags.map(_esc).join(', ') +
      '</p>';
  }

  if (r.recommendations?.length) {
    html +=
      '<p><b>\uD83D\uDCA1 ' +
      _t('tools.recommendations', 'Recommendations:') +
      '</b></p><ul style="margin:5px 0 10px 20px;">';
    r.recommendations.forEach((rec) => (html += `<li>${_esc(rec)}</li>`));
    html += '</ul>';
  }

  if (r.unexplored?.length) {
    html +=
      '<p><b>\uD83D\uDD2E ' +
      _t('tools.unexplored_themes', 'Unexplored themes:') +
      '</b> ' +
      r.unexplored.map(_esc).join(', ') +
      '</p>';
  }

  if (r.raw)
    html += `<pre style="font-size:11px;max-height:200px;overflow:auto;">${_esc(r.raw)}</pre>`;

  resultBox.innerHTML = html;
}

function _formatDate(epoch: number): string {
  const d = new Date(epoch * 1000);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function _renderHistoryItem(item: TrendHistoryItem): string {
  const r = item.result;
  let body = '';
  if (r.style_tendency)
    body += `<p><b>\uD83C\uDFA8 ${_t('tools.style_tendency', 'Style tendency:')}</b> ${_esc(r.style_tendency)}</p>`;
  if (r.strengths)
    body += `<p><b>\uD83D\uDCAA ${_t('tools.strengths', 'Strengths:')}</b> ${_esc(r.strengths)}</p>`;
  if (r.weaknesses)
    body += `<p><b>\uD83D\uDCDD ${_t('tools.weaknesses', 'Areas for improvement:')}</b> ${_esc(r.weaknesses)}</p>`;
  if (r.frequent_tags?.length)
    body += `<p><b>\uD83C\uDFF7\uFE0F ${_t('tools.frequent_tags', 'Frequent tags:')}</b> ${r.frequent_tags.map(_esc).join(', ')}</p>`;
  if (r.recommendations?.length) {
    body += `<p><b>\uD83D\uDCA1 ${_t('tools.recommendations', 'Recommendations:')}</b></p><ul style="margin:5px 0 10px 20px;">`;
    r.recommendations.forEach((rec) => (body += `<li>${_esc(rec)}</li>`));
    body += '</ul>';
  }
  if (r.unexplored?.length)
    body += `<p><b>\uD83D\uDD2E ${_t('tools.unexplored_themes', 'Unexplored themes:')}</b> ${r.unexplored.map(_esc).join(', ')}</p>`;

  return `<details class="trend-history-item" style="margin:6px 0;border:1px solid rgba(255,255,255,0.1);border-radius:6px;padding:0;">
    <summary style="padding:8px 12px;cursor:pointer;display:flex;align-items:center;gap:8px;font-size:13px;">
      <span style="flex:1;">\uD83D\uDCC5 ${_formatDate(item.analyzed_at)} \u2014 ${_esc(item.engine)} (${item.prompt_count} prompts)</span>
      <button class="btn btn-danger btn-sm" data-action="toolsPageApi.deleteTrendHistoryEntry" data-action-arg="${item.id}"
        style="font-size:11px;padding:2px 8px;" title="${_t('tools.delete', 'Delete')}">\u2715</button>
    </summary>
    <div style="padding:8px 12px;border-top:1px solid rgba(255,255,255,0.05);font-size:13px;">
      ${body}
    </div>
  </details>`;
}

export function renderTrendHistory(
  container: HTMLElement,
  items: TrendHistoryItem[],
): void {
  if (!items.length) {
    container.innerHTML = '';
    return;
  }
  let html = `<details style="margin-top:16px;" open>
    <summary style="cursor:pointer;font-weight:600;font-size:14px;padding:6px 0;">
      \uD83D\uDCDC ${_t('tools.trend_history', 'Trend Analysis History')} (${items.length})
    </summary>
    <div style="margin-top:8px;">`;
  for (const item of items) {
    html += _renderHistoryItem(item);
  }
  html += '</div></details>';
  container.innerHTML = html;
}
