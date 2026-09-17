/**
 * duplicates/render.ts -- Rendering helpers for duplicate groups.
 *
 * Builds DOM via createElement and chunks insertion through requestIdleCallback
 * to keep the browser responsive when there are many groups. Thumbnails are
 * fetched lazily via a single IntersectionObserver instead of <img loading=lazy>
 * + onerror inline handlers (which DOMPurify strips and which still incur DOM
 * cost up front).
 */

import { escapeHtml } from '../../main/api-utils';
import { buildIcon, getThumbObserver, onThumbError, scheduleIdle, t as _t } from './render-helpers';

interface HashStats {
  with_hash?: number;
  with_phash?: number;
}

export interface DuplicateGroup {
  count: number;
  ids?: number[];
  files: string[];
}

export interface DuplicateData {
  groups: DuplicateGroup[];
  total_duplicates: number;
  hash_stats?: HashStats;
  truncated?: boolean;
  group_limit?: number;
  total_groups?: number;
}

const CHUNK_SIZE = 20;

export function renderLoading(): string {
  return (
    '<div class="spinner-overlay"><div class="spinner"></div><span class="spinner-text">' +
    _t('tools.searching', 'Searching...') +
    '</span></div>'
  );
}

export function renderProgress(elapsed: number): string {
  return (
    '<div class="spinner-overlay"><div class="spinner"></div><span class="spinner-text">' +
    _t('tools.searching', 'Searching...') +
    ' (' +
    elapsed.toFixed(0) +
    's)</span></div>'
  );
}

export function renderNoDuplicates(method: string, hashStats?: HashStats): string {
  let msg = '✓ ' + _t('tools.no_duplicates', 'No duplicates found');
  if (method === 'hash' && hashStats?.with_hash === 0) {
    msg +=
      '<br><span style="color:#e67e22;">⚠ ' +
      _t(
        'tools.hash_not_computed',
        'Hashes not computed. Run "Compute Hashes" first.',
      ) +
      '</span>';
  }
  if (method === 'phash' && hashStats?.with_phash === 0) {
    msg +=
      '<br><span style="color:#e67e22;">⚠ ' +
      _t(
        'tools.phash_not_computed',
        'Perceptual hashes not computed. Run "Compute Hashes" first.',
      ) +
      '</span>';
  }
  return `<p>${msg}</p>`;
}

function methodLabel(method: string): string {
  return method === 'phash'
    ? _t('tools.similar_images', 'Similar images')
    : method === 'size'
      ? _t('tools.same_size', 'Same size')
      : _t('tools.exact_match', 'Exact match');
}

function buildHeader(data: DuplicateData, method: string): DocumentFragment {
  const frag = document.createDocumentFragment();

  const summary = document.createElement('p');
  summary.append(`${_t('tools.dup_groups_found', 'Duplicate groups found')}: `);
  const sB = document.createElement('b');
  sB.textContent = String(data.groups.length);
  summary.append(sB, ` (${_t('tools.duplicate', 'Duplicate')} ${_t('tools.files', 'files')}: `);
  const dB = document.createElement('b');
  dB.textContent = String(data.total_duplicates);
  summary.append(dB, `) — ${methodLabel(method)}`);
  frag.append(summary);

  if (data.truncated) {
    const limit = data.group_limit ?? data.groups.length;
    const total = data.total_groups ?? data.groups.length;
    const warn = document.createElement('div');
    warn.style.cssText =
      'margin:6px 0 10px;padding:8px 10px;background:rgba(231,76,60,0.12);border:1px solid rgba(231,76,60,0.4);border-radius:6px;font-size:13px;';
    const tmpl = _t(
      'tools.results_truncated',
      'Too many duplicate groups; showing the first {limit} of {total}. Narrow the search and try again.',
    );
    warn.textContent = tmpl
      .replace('{limit}', String(limit))
      .replace('{total}', String(total));
    frag.append(warn);
  }

  const counter = document.createElement('div');
  counter.id = 'dupeDeleteCount';
  counter.style.cssText =
    'margin:6px 0 10px;padding:6px 10px;background:rgba(231,76,60,0.12);border:1px solid rgba(231,76,60,0.3);border-radius:6px;font-size:13px;display:none;';
  frag.append(counter);

  return frag;
}

function buildGroup(group: DuplicateGroup, idx: number): HTMLElement {
  const wrap = document.createElement('div');
  wrap.className = 'duplicate-group';
  wrap.dataset.group = String(idx);

  const h4 = document.createElement('h4');
  h4.append(
    `${_t('tools.group', 'Group')} ${idx + 1} (${group.count} ${_t('tools.files', 'files')})`,
  );
  const selectAllBtn = document.createElement('button');
  selectAllBtn.type = 'button';
  selectAllBtn.style.cssText =
    'font-size:11px;background:rgba(0,0,0,0.15);border:1px solid rgba(0,0,0,0.3);color:inherit;border-radius:3px;padding:3px 8px;cursor:pointer;margin-left:8px;';
  selectAllBtn.dataset.action = 'toolsPageApi.selectAllDupes';
  selectAllBtn.dataset.actionArg = String(idx);
  selectAllBtn.textContent = _t('tools.select_all_dupes', 'Select all duplicates');
  h4.append(' ', selectAllBtn);
  wrap.append(h4);

  const thumbRow = document.createElement('div');
  thumbRow.style.cssText = 'display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px;';
  const ids = group.ids || [];
  const observer = ids.length ? getThumbObserver() : null;
  ids.forEach((id, fileIdx) => {
    const isKeep = fileIdx === 0;
    const cell = document.createElement('div');
    cell.className = 'dupe-thumb-cell';
    cell.dataset.group = String(idx);
    cell.dataset.fileIdx = String(fileIdx);
    cell.style.cssText = 'text-align:center;position:relative;';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'dupe-check';
    cb.dataset.group = String(idx);
    cb.dataset.fileIdx = String(fileIdx);
    cb.dataset.id = String(id);
    cb.checked = !isKeep;
    const label = isKeep ? _t('tools.keep', 'Keep') : _t('tools.duplicate', 'Duplicate');
    cb.setAttribute('aria-label', label);
    cb.style.cssText =
      'position:absolute;top:4px;left:4px;z-index:2;width:16px;height:16px;cursor:pointer;';
    cell.append(cb);

    const img = document.createElement('img');
    img.className = 'dupe-thumb-img';
    img.dataset.group = String(idx);
    img.dataset.fileIdx = String(fileIdx);
    img.dataset.thumbId = String(id);
    img.alt = '';
    img.style.cssText = `width:100px;height:100px;object-fit:cover;border-radius:4px;border:2px solid ${isKeep ? '#2ecc71' : '#e74c3c'};cursor:pointer;background:rgba(255,255,255,0.04);`;
    img.title = _t('tools.click_preview', 'Click to preview');
    img.dataset.action = 'toolsPageApi.previewDuplicateImage';
    img.dataset.actionArg = String(id);
    img.addEventListener('error', onThumbError);
    if (observer) observer.observe(img);
    cell.append(img);

    const labelDiv = document.createElement('div');
    labelDiv.className = 'dupe-label';
    labelDiv.dataset.group = String(idx);
    labelDiv.dataset.fileIdx = String(fileIdx);
    labelDiv.style.cssText = `font-size:10px;color:${isKeep ? '#2ecc71' : '#e74c3c'};margin-top:2px;`;
    labelDiv.textContent = label;
    cell.append(labelDiv);

    const keepBtn = document.createElement('button');
    keepBtn.type = 'button';
    keepBtn.className = 'dupe-keep-btn';
    keepBtn.dataset.group = String(idx);
    keepBtn.dataset.fileIdx = String(fileIdx);
    keepBtn.dataset.action = 'toolsPageApi.setKeepImageArg';
    keepBtn.dataset.actionArg = `${idx}:${fileIdx}`;
    keepBtn.title = _t('tools.keep_this_title', 'Keep this file, mark all others as duplicates');
    keepBtn.style.cssText = isKeep
      ? 'font-size:10px;padding:2px 6px;border-radius:3px;border:none;cursor:pointer;background:#2ecc71;color:#000;font-weight:600;margin-top:4px;'
      : 'font-size:10px;padding:2px 6px;border-radius:3px;border:1px solid rgba(255,255,255,0.3);cursor:pointer;background:rgba(255,255,255,0.1);color:inherit;margin-top:4px;';
    if (isKeep) {
      keepBtn.append(buildIcon('pin'), ' ', _t('tools.keeping', 'Keeping'));
    } else {
      keepBtn.textContent = _t('tools.keep_this', 'Keep this');
    }
    cell.append(keepBtn);

    thumbRow.append(cell);
  });
  wrap.append(thumbRow);

  group.files.forEach((file, fileIdx) => {
    const isKeep = fileIdx === 0;
    const itemLabel = isKeep
      ? `[${_t('tools.keep', 'Keep')}]`
      : `[${_t('tools.duplicate', 'Duplicate')}]`;
    const row = document.createElement('div');
    row.className = `duplicate-item ${isKeep ? 'keep' : 'dupe'}`;
    row.style.cssText = 'font-size:12px;display:flex;align-items:center;gap:6px;';

    const cb = document.createElement('input');
    cb.type = 'checkbox';
    cb.className = 'dupe-check-path';
    cb.dataset.group = String(idx);
    cb.dataset.fileIdx = String(fileIdx);
    cb.dataset.path = file;
    cb.checked = !isKeep;
    cb.setAttribute('aria-label', itemLabel);
    cb.style.cssText = 'width:14px;height:14px;cursor:pointer;';
    cb.dataset.action = 'toolsPageApi.syncDupeCheckArg';
    cb.dataset.actionArg = `${idx}:${fileIdx}`;
    cb.dataset.actionEvent = 'change';
    cb.dataset.actionThis = '1';
    row.append(cb);

    const span = document.createElement('span');
    span.textContent = `${itemLabel} ${file}`;
    row.append(span);

    wrap.append(row);
  });

  return wrap;
}

/**
 * Render duplicate groups into the container. Replaces existing content.
 *
 * Splits work across idle frames so the browser stays responsive even with
 * hundreds of groups. Thumbnails load lazily via IntersectionObserver.
 */
export function renderGroups(
  container: HTMLElement,
  data: DuplicateData,
  method: string,
): void {
  container.replaceChildren();
  container.append(buildHeader(data, method));

  const groups = data.groups;
  let i = 0;
  const renderChunk = () => {
    if (i >= groups.length) return;
    const frag = document.createDocumentFragment();
    const end = Math.min(i + CHUNK_SIZE, groups.length);
    for (let j = i; j < end; j++) {
      frag.append(buildGroup(groups[j], j));
    }
    container.append(frag);
    i = end;
    if (i < groups.length) scheduleIdle(renderChunk);
  };
  scheduleIdle(renderChunk);
}

export function renderError(message: string): string {
  return (
    '<p style="color: #e74c3c;">' +
    _t('tools.error', 'Error') +
    ': ' +
    escapeHtml(message) +
    '</p>'
  );
}

export function renderHashProgress(): string {
  return `
    <div style="padding:10px;">
      <div style="margin-bottom:8px;">#️⃣ <strong>${_t('tools.computing_hashes', 'Computing hashes...')}</strong></div>
      <div style="background:rgba(0,0,0,0.3);border-radius:4px;height:24px;overflow:hidden;margin:8px 0;">
        <div id="hashProgressBar" style="height:100%;background:linear-gradient(90deg,#667eea,#764ba2);width:0%;transition:width 0.3s;border-radius:4px;"></div>
      </div>
      <div id="hashProgressText" style="font-size:12px;color:#888;">${_t('tools.preparing', 'Preparing...')}</div>
    </div>
  `;
}

export function renderHashDone(message: string): string {
  return `<p style="color:#2ecc71;">✓ ${escapeHtml(message)}</p>`;
}
