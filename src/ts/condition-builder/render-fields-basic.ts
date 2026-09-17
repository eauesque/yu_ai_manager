import type { ConditionDef } from './config';
import { getAppApi, getConditionBuilderApi, getRuntimeInitApi } from '../shared/browser-apis';

function esc(value: unknown): string {
  return getAppApi().escapeHtml(value);
}

function escAttr(value: string | undefined): string {
  return String(value || '').replace(/"/g, '&quot;');
}

export function renderTextField(cond: ConditionDef, conditionPlaceholder: (c: ConditionDef) => string): string {
  const { tr } = getAppApi();
  const val = (document.getElementById(cond.target!) as HTMLInputElement | null)?.value || '';
  return `<div class="input-with-clear" style="flex:1;min-width:150px;position:relative;display:flex;align-items:center;">
    <input type="text" value="${escAttr(val)}" placeholder="${esc(conditionPlaceholder(cond))}" data-condition-text-target="${escAttr(cond.target || '')}"
    style="flex:1;padding:5px 30px 5px 8px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:13px;">
    <button type="button" class="clear-btn" data-condition-clear-target="${escAttr(cond.target || '')}" title="${esc(tr('common.clear'))}" style="position:absolute;right:2px;background:transparent;border:none;cursor:pointer;font-size:14px;padding:2px 6px;opacity:0.5;color:inherit;">×</button>
  </div>`;
}

export function renderSelectField(cond: ConditionDef, conditionLabel: ((c: ConditionDef) => string) | string): string {
  const { tr } = getAppApi();
  const sel = document.getElementById(cond.target!) as HTMLSelectElement | null;
  if (!sel) return '';

  const labelText = typeof conditionLabel === 'function'
    ? conditionLabel(cond)
    : String(conditionLabel || '');
  const ariaAttr = labelText ? ` aria-label="${escAttr(labelText)}"` : '';
  const needsChipSync = cond.target === 'sortBy';
  let html = `<div style="display:flex;align-items:center;gap:4px;">`;
  html += `<select${ariaAttr} name="cb-${escAttr(cond.target || '')}" data-condition-select-target="${escAttr(cond.target || '')}"${needsChipSync ? ' data-condition-sync-chip="1"' : ''}
    style="padding:5px 8px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:13px;">`;
  for (const opt of Array.from(sel.options)) {
    const selected = opt.value === sel.value ? 'selected' : '';
    html += `<option value="${opt.value}" ${selected}>${opt.textContent}</option>`;
  }
  html += '</select>';
  if (cond.target !== 'sortBy') {
    html += `<button type="button" data-condition-reset-target="${escAttr(cond.target || '')}"${cond.target === 'fileFormat' ? ' data-condition-reset-format-exts="1"' : ''} title="${esc(tr('common.reset'))}" style="background:none;border:1px solid rgba(255,255,255,0.15);border-radius:4px;cursor:pointer;font-size:12px;padding:2px 6px;color:#888;">×</button>`;
  }
  html += `</div>`;
  if (cond.target === 'fileFormat') {
    html += renderFormatExtField();
  }
  return html;
}

const FORMAT_EXT_GROUPS = [
  { labelKey: 'conditions.format.ext_group_image', label: 'Image', exts: ['png', 'jpg', 'jpeg', 'webp', 'gif', 'avif', 'jxl', 'heif', 'heic', 'bmp', 'tif', 'tiff'] },
  { labelKey: 'conditions.format.ext_group_video', label: 'Video', exts: ['webm', 'mp4', 'mov', 'mkv', 'avi', 'm4v', 'ogv'] },
  { labelKey: 'conditions.format.ext_group_audio', label: 'Audio', exts: ['mp3', 'wav', 'ogg', 'opus', 'm4a', 'aac', 'flac'] },
  { labelKey: 'conditions.format.ext_group_document', label: 'Document', exts: ['pdf'] },
  { labelKey: 'conditions.format.ext_group_container', label: 'Container', exts: ['zip', '7z'] },
];

function ensureFormatExtInput(): HTMLInputElement {
  let input = document.getElementById('formatExts') as HTMLInputElement | null;
  if (input) return input;
  input = document.createElement('input');
  input.type = 'text';
  input.id = 'formatExts';
  input.value = '';
  input.style.display = 'none';
  (document.getElementById('fileFormat')?.parentElement || document.body).appendChild(input);
  return input;
}

function getSelectedFormatExts(): string[] {
  const raw = String(ensureFormatExtInput()?.value || '');
  return raw
    .split(',')
    .map((s) => s.trim().toLowerCase())
    .filter((s) => /^[a-z0-9]{1,8}$/.test(s));
}

function renderFormatExtField(): string {
  const { tr } = getAppApi();
  const selected = new Set(getSelectedFormatExts());
  let html = `<div style="display:flex;flex-direction:column;gap:4px;margin-top:6px;padding:6px 8px;border:1px dashed rgba(102,126,234,0.35);border-radius:8px;">`;
  html += `<div style="font-size:11px;color:#888;">${esc(tr('conditions.format.ext_filter_hint', 'Filter by extension (optional)'))}</div>`;
  for (const group of FORMAT_EXT_GROUPS) {
    html += `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">`;
    html += `<span style="font-size:11px;color:#777;min-width:44px;">${esc(tr(group.labelKey, group.label))}</span>`;
    for (const ext of group.exts) {
      const checked = selected.has(ext) ? 'checked' : '';
      html += `<label style="display:inline-flex;align-items:center;gap:4px;font-size:12px;cursor:pointer;">
        <input type="checkbox" data-format-ext="${ext}" ${checked} aria-label="Filter .${ext}">
        .${ext}
      </label>`;
    }
    html += `</div>`;
  }
  html += `<div style="display:flex;justify-content:flex-end;">
    <button type="button" data-condition-clear-format-exts="1" title="${esc(tr('common.clear'))}" style="background:none;border:1px solid rgba(255,255,255,0.15);border-radius:4px;cursor:pointer;font-size:11px;padding:2px 6px;color:#888;">${esc(tr('common.clear'))}</button>
  </div>`;
  html += `</div>`;
  return html;
}

export function toggleFormatExt(ext: string, enabled: boolean): void {
  const runtimeInitApi = getRuntimeInitApi();
  const conditionBuilderApi = getConditionBuilderApi();
  if (!/^[a-z0-9]{1,8}$/.test(String(ext || '').toLowerCase())) return;
  const set = new Set(getSelectedFormatExts());
  if (enabled) set.add(ext);
  else set.delete(ext);
  const input = ensureFormatExtInput();
  if (input) input.value = Array.from(set).sort().join(',');
  runtimeInitApi.saveSearchState();
  conditionBuilderApi.renderActiveConditions();
}

export function clearFormatExts(): void {
  const runtimeInitApi = getRuntimeInitApi();
  const conditionBuilderApi = getConditionBuilderApi();
  const input = ensureFormatExtInput();
  if (input) input.value = '';
  document.querySelectorAll<HTMLInputElement>('input[data-format-ext]').forEach((el) => {
    el.checked = false;
  });
  runtimeInitApi.saveSearchState();
  conditionBuilderApi.renderActiveConditions();
}

export function renderToggleField(cond: ConditionDef): string {
  const { tr } = getAppApi();
  const cb = document.getElementById(cond.target!) as HTMLInputElement | null;
  const checked = cb?.checked ? 'checked' : '';
  return `<label style="display:inline-flex;align-items:center;gap:4px;cursor:pointer;font-size:13px;">
    <input type="checkbox" ${checked} data-condition-toggle-target="${escAttr(cond.target || '')}" aria-label="${esc(tr('common.enabled'))}">
    ${esc(tr('common.enabled'))}
  </label>`;
}
