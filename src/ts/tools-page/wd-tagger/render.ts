/**
 * wd-tagger/render.ts -- DOM rendering helpers for WD-Tagger UI.
 */

import { getAppApi } from '../../shared/browser-apis';
import { formatElapsedHms } from '../../shared/date-format';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function _esc(text: string): string {
  const d = document.createElement('div');
  d.textContent = text;
  return d.innerHTML;
}

// Category -> CSS class mapping
const CATEGORY_CLASS: Record<string, string> = {
  general: 'wt-tag-general',
  character: 'wt-tag-character',
  copyright: 'wt-tag-copyright',
  rating: 'wt-tag-rating',
};

export function renderWtModelStatus(data: Record<string, unknown>): string {
  const d = (data.data || data) as Record<string, unknown>;
  const ready = d.ready as boolean;
  const files = (d.files || {}) as Record<string, { exists: boolean; size_mb: number }>;

  if (ready) {
    const onnxSize = files['model.onnx']?.size_mb || 0;
    return `<span style="color:#4caf50;">&#x2714;</span> ${_t('tools.wt_model_ready', 'Model ready')} (${onnxSize} MB)`;
  }

  let html = `<span style="color:#ff9800;">&#x26A0;</span> ${_t('tools.wt_model_not_downloaded', 'Model not downloaded')}`;
  for (const [name, info] of Object.entries(files)) {
    const icon = info.exists ? '&#x2714;' : '&#x2716;';
    const color = info.exists ? '#4caf50' : '#f44336';
    html += ` <span style="color:${color};font-size:11px;">${icon} ${_esc(name)}</span>`;
  }
  return html;
}

export function renderWtStats(data: Record<string, unknown>): string {
  const d = (data.data || data) as Record<string, unknown>;
  const tagged = d.tagged_files as number || 0;
  const total = d.total_tags as number || 0;
  const unique = d.unique_tags as number || 0;
  const untagged = d.untagged_unknown as number || 0;

  let html = `&#x1F4CA; ${_t('tools.wt_tagged_files', 'Tagged files')}: <strong>${tagged.toLocaleString()}</strong>`;
  html += ` &mdash; ${_t('tools.wt_total_tags', 'Total tags')}: ${total.toLocaleString()}`;
  html += ` &mdash; ${_t('tools.wt_unique', 'Unique')}: ${unique.toLocaleString()}`;
  if (untagged > 0) {
    html += ` &mdash; <span style="color:#ff9800;">${_t('tools.wt_untagged', 'Untagged unknown')}: ${untagged.toLocaleString()}</span>`;
  }

  const cats = d.by_category as Record<string, number> | undefined;
  if (cats && Object.keys(cats).length > 0) {
    html += '<div style="margin-top:4px;font-size:11px;">';
    for (const [cat, cnt] of Object.entries(cats)) {
      const cls = CATEGORY_CLASS[cat] || 'wt-tag-general';
      html += `<span class="wt-tag ${cls}" style="font-size:10px;">${_esc(cat)}: ${cnt.toLocaleString()}</span> `;
    }
    html += '</div>';
  }

  return html;
}

export function renderWtResult(job: Record<string, unknown>): string {
  const phase = job.phase as string || '';
  const message = job.message as string || '';
  const elapsed = job.elapsed_seconds as number || 0;

  let icon = '&#x2714;';
  let color = '#4caf50';
  if (phase === 'error') { icon = '&#x2716;'; color = '#f44336'; }
  else if (phase === 'cancelled') { icon = '&#x26A0;'; color = '#ff9800'; }

  return `<div style="display:flex;align-items:center;gap:8px;">
    <span style="color:${color};font-size:18px;">${icon}</span>
    <div>
      <div style="font-weight:600;">${_esc(message)}</div>
      <div style="font-size:11px;color:#888;">${formatElapsedHms(elapsed)}</div>
    </div>
  </div>`;
}

export function renderWtTags(
  tags: Array<{ tag: string; confidence: number; category: string }>,
): string {
  if (!tags || tags.length === 0) return `<span style="color:#888;">${_esc(_t('tools.wt_no_tags', 'No tags'))}</span>`;

  let html = '<div class="wt-tag-list">';
  for (const t of tags) {
    const cls = CATEGORY_CLASS[t.category] || 'wt-tag-general';
    const pct = (t.confidence * 100).toFixed(1);
    html += `<span class="wt-tag ${cls}" title="${_esc(t.category)} ${pct}%">${_esc(t.tag)}</span>`;
  }
  html += '</div>';
  return html;
}
