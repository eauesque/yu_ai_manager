/**
 * archive-cleanup/render.ts -- HTML rendering for archive cleanup UI.
 */

import { getAppApi } from '../../shared/browser-apis';
import { renderPagination, renderSortFilterBar } from './render-toolbar';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export interface ArchivePair {
  archive_path: string;
  archive_name: string;
  archive_ext: string;
  archive_size: number;
  archive_file_count: number;
  archive_content_size: number;
  folder_path: string;
  folder_name: string;
  folder_file_count: number;
  folder_size: number;
  match_count: number;
  match_rate: number;
  diagnosis?: string | null;
  adjusted_match_rate?: number | null;
  adjustment_reason?: string | null;
}

export interface ExecuteResult {
  deleted_archives: number;
  deleted_folders: number;
  skipped: number;
  errors: string[];
  deleted_paths?: string[];
}

export interface LlmResult {
  is_duplicate: boolean;
  confidence: number;
  reasoning: string;
  recommendation: string;
  warnings?: string[];
}

export const PAGE_SIZE = 20;

function formatSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function matchColor(rate: number): string {
  if (rate >= 95) return '#27ae60';
  if (rate >= 70) return '#f39c12';
  return '#e74c3c';
}

/** Display match rate (prefers adjusted_match_rate if available) */
function displayRate(p: ArchivePair): number {
  return p.adjusted_match_rate != null ? p.adjusted_match_rate : p.match_rate;
}

export function renderScanning(): string {
  return `<div style="color:#888;font-size:13px;padding:12px;">
    <span class="spinner" style="display:inline-block;width:14px;height:14px;border:2px solid rgba(128,128,128,0.3);border-top-color:#888;border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:6px;"></span>
    ${_t('tools.ac_scanning', 'Scanning for archive pairs...')}
  </div>`;
}

export function renderNoPairs(): string {
  return `<div style="color:#888;font-size:13px;padding:12px;">
    ${_t('tools.ac_no_pairs', 'No archive + folder pairs found.')}
  </div>`;
}

export function renderError(msg: string): string {
  return `<div style="color:#e74c3c;font-size:13px;padding:12px;">${_esc(msg)}</div>`;
}

function _esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function _renderDiagnosisBadge(p: ArchivePair): string {
  if (!p.diagnosis) return '';

  const labels: Record<string, { label: string; color: string }> = {
    double_extraction: { label: _t('tools.ac_diag_double', 'Double Extraction'), color: '#e67e22' },
    prefix_stripped: { label: _t('tools.ac_diag_prefix', 'Prefix Stripped'), color: '#3498db' },
    unicode_normalized: { label: _t('tools.ac_diag_unicode', 'Unicode Normalized'), color: '#9b59b6' },
    size_profile_match: { label: _t('tools.ac_diag_size_profile', 'Size Match'), color: '#2ecc71' },
  };
  const info = labels[p.diagnosis] || { label: p.diagnosis, color: '#888' };
  const adj = p.adjusted_match_rate != null ? ` -> ${p.adjusted_match_rate}%` : '';
  const title = p.adjustment_reason
    ? p.adjustment_reason.replace(/"/g, '&quot;')
    : '';

  return `<span title="${title}" style="font-size:10px;padding:2px 6px;border-radius:10px;background:${info.color};color:#fff;margin-left:6px;cursor:help;">${info.label}${adj}</span>`;
}

export function renderPairs(
  allFiltered: ArchivePair[],
  pairActions: Map<number, string>,
  page: number,
  totalAll: number,
  perfectCountAll: number,
): string {
  const totalPages = Math.max(1, Math.ceil(allFiltered.length / PAGE_SIZE));
  const safePage = Math.max(1, Math.min(page, totalPages));
  const startIdx = (safePage - 1) * PAGE_SIZE;
  const pageItems = allFiltered.slice(startIdx, startIdx + PAGE_SIZE);

  let html = renderSortFilterBar(
    allFiltered.length, totalAll, perfectCountAll, safePage, totalPages, _t,
  );

  pageItems.forEach((p) => {
    const origIdx = (p as ArchivePair & { _originalIdx?: number })._originalIdx ?? 0;
    const rate = displayRate(p);
    const mc = matchColor(rate);
    const escArc = p.archive_path.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    const escFld = p.folder_path.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/"/g, '&quot;');
    const selectedAction = pairActions.get(origIdx) || 'skip';

    html += `<div class="ac-pair-card" data-idx="${origIdx}" data-match-rate="${rate}" data-archive="${escArc}" data-folder="${escFld}"
      style="border:1px solid rgba(128,128,128,0.25);border-radius:8px;padding:12px;margin-bottom:10px;background:var(--card,#2a2a2a);">
      <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;flex-wrap:wrap;gap:4px;">
        <strong style="font-size:14px;">${p.archive_name}</strong>
        <div style="display:flex;align-items:center;">
          <span style="font-size:12px;font-weight:600;color:${mc};border:1px solid ${mc};border-radius:12px;padding:2px 8px;">
            ${_t('tools.ac_match', 'Match')}: ${p.match_rate}%
          </span>
          ${_renderDiagnosisBadge(p)}
        </div>
      </div>
      <div style="display:grid;grid-template-columns:1fr 1fr;gap:10px;font-size:12px;margin-bottom:10px;">
        <div style="padding:8px;border-radius:6px;background:rgba(128,128,128,0.08);">
          <div style="font-weight:600;margin-bottom:4px;">${_t('tools.ac_archive', 'Archive')} (${p.archive_ext})</div>
          <div>${_t('tools.ac_files', 'Files')}: ${p.archive_file_count}</div>
          <div>${_t('tools.ac_archive_size', 'Archive size')}: ${formatSize(p.archive_size)}</div>
          <div>${_t('tools.ac_content_size', 'Content size')}: ${formatSize(p.archive_content_size)}</div>
        </div>
        <div style="padding:8px;border-radius:6px;background:rgba(128,128,128,0.08);">
          <div style="font-weight:600;margin-bottom:4px;">${_t('tools.ac_folder', 'Folder')}</div>
          <div>${_t('tools.ac_files', 'Files')}: ${p.folder_file_count}</div>
          <div>${_t('tools.ac_size', 'Size')}: ${formatSize(p.folder_size)}</div>
        </div>
      </div>
      ${p.adjustment_reason ? `<div style="font-size:11px;color:#f39c12;margin-bottom:8px;padding:4px 8px;background:rgba(243,156,18,0.1);border-radius:4px;">${_esc(p.adjustment_reason)}</div>` : ''}
      <div style="display:flex;gap:12px;font-size:12px;align-items:center;flex-wrap:wrap;">
        <label style="cursor:pointer;"><input type="radio" name="ac_action_${origIdx}" value="skip" ${selectedAction === 'skip' ? 'checked' : ''} data-action="toolsPageApi.acActionChangeArg" data-action-arg="${origIdx}:skip" data-action-event="change"> ${_t('tools.ac_skip', 'Skip')}</label>
        <label style="cursor:pointer;color:#e74c3c;"><input type="radio" name="ac_action_${origIdx}" value="delete_archive" ${selectedAction === 'delete_archive' ? 'checked' : ''} data-action="toolsPageApi.acActionChangeArg" data-action-arg="${origIdx}:delete_archive" data-action-event="change"> ${_t('tools.ac_del_archive', 'Delete Archive')}</label>
        <label style="cursor:pointer;color:#e67e22;"><input type="radio" name="ac_action_${origIdx}" value="delete_folder" ${selectedAction === 'delete_folder' ? 'checked' : ''} data-action="toolsPageApi.acActionChangeArg" data-action-arg="${origIdx}:delete_folder" data-action-event="change"> ${_t('tools.ac_del_folder', 'Delete Folder')}</label>
        ${rate < 99.9 ? `<button type="button" class="btn btn-secondary" data-action="toolsPageApi.acLlmVerify" data-action-arg="${origIdx}" style="font-size:10px;padding:2px 8px;margin-left:auto;">${_t('tools.ac_llm_verify', 'LLM Verify')}</button>` : ''}
      </div>
      <div id="acLlmResult_${origIdx}" style="margin-top:6px;"></div>
    </div>`;
  });

  // Bottom pagination
  if (totalPages > 1) {
    html += renderPagination(safePage, totalPages);
  }

  return html;
}

export function renderLlmResult(result: LlmResult): string {
  const dupColor = result.is_duplicate ? '#27ae60' : '#e74c3c';
  const dupLabel = result.is_duplicate
    ? _t('tools.ac_llm_dup', 'Duplicate')
    : _t('tools.ac_llm_not_dup', 'Not Duplicate');
  const conf = Math.round(result.confidence * 100);

  let html = `<div style="font-size:11px;padding:8px;border-radius:6px;background:rgba(128,128,128,0.08);margin-top:4px;">
    <div style="display:flex;gap:8px;align-items:center;margin-bottom:4px;">
      <span style="font-weight:600;color:${dupColor};">${dupLabel}</span>
      <span style="color:#888;">${_t('tools.ac_llm_confidence', 'Confidence')}: ${conf}%</span>
    </div>
    <div style="color:#ccc;margin-bottom:4px;">${_esc(result.reasoning)}</div>
    <div style="color:#f39c12;">${_t('tools.ac_llm_recommend', 'Recommendation')}: ${_esc(result.recommendation)}</div>`;

  if (result.warnings && result.warnings.length > 0) {
    html += `<div style="color:#e74c3c;margin-top:4px;">${result.warnings.map(w => _esc(w)).join('<br>')}</div>`;
  }
  html += '</div>';
  return html;
}

export function renderLlmVerifying(): string {
  return `<div style="font-size:11px;color:#888;padding:4px;">
    <span class="spinner" style="display:inline-block;width:10px;height:10px;border:2px solid rgba(128,128,128,0.3);border-top-color:#888;border-radius:50%;animation:spin .6s linear infinite;vertical-align:middle;margin-right:4px;"></span>
    ${_t('tools.ac_llm_verifying', 'LLM verifying...')}
  </div>`;
}

/** Execution result summary banner (displayed above the pair list) */
export function renderExecuteBanner(data: ExecuteResult): string {
  const parts: string[] = [];
  if (data.deleted_archives > 0) {
    parts.push(`<span style="color:#27ae60;">${_t('tools.ac_archives_deleted', 'Archives deleted')}: ${data.deleted_archives}</span>`);
  }
  if (data.deleted_folders > 0) {
    parts.push(`<span style="color:#27ae60;">${_t('tools.ac_folders_deleted', 'Folders deleted')}: ${data.deleted_folders}</span>`);
  }
  if (data.errors.length > 0) {
    parts.push(`<span style="color:#e74c3c;">${_t('tools.ac_errors', 'Errors')}: ${data.errors.length}</span>`);
  }
  let html = `<div id="acExecBanner" style="padding:10px 12px;font-size:13px;border-radius:8px;background:rgba(39,174,96,0.1);border:1px solid rgba(39,174,96,0.3);margin-bottom:12px;">
    <div style="display:flex;gap:16px;align-items:center;flex-wrap:wrap;">
      ${parts.join('')}
      <button type="button" data-action="toolsPageApi.acCloseExecBanner" style="margin-left:auto;background:none;border:none;color:#888;cursor:pointer;font-size:16px;padding:0 4px;" title="Close">&times;</button>
    </div>`;
  if (data.errors.length > 0) {
    html += `<details style="margin-top:6px;"><summary style="font-size:11px;color:#e74c3c;cursor:pointer;">${_t('tools.ac_show_errors', 'Show errors')}</summary>`;
    data.errors.forEach((e) => {
      html += `<div style="color:#e74c3c;font-size:11px;margin-left:12px;margin-top:2px;">${_esc(e)}</div>`;
    });
    html += `</details>`;
  }
  html += `</div>`;
  return html;
}
