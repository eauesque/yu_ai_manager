import { getAppApi } from '../shared/browser-apis';
import type { PeriodPreset } from './config';

function esc(value: unknown): string {
  return getAppApi().escapeHtml(value);
}

export function renderPeriodField(PERIOD_PRESETS: PeriodPreset[]): string {
  const { tr } = getAppApi();
  let html = `<div style="display:flex;gap:4px;flex-wrap:wrap;">`;
  for (const preset of PERIOD_PRESETS) {
    if (preset.type === 'custom') {
      html += `<button type="button" data-condition-period-custom="1" style="padding:3px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.1);color:inherit;font-size:11px;cursor:pointer;">📅 ${esc(tr('period.custom'))}</button>`;
    } else {
      html += `<button type="button" data-condition-period-days="${String(preset.days || 0)}" data-condition-period-type="${String(preset.type || '')}" data-condition-period-hours="${String(preset.hours || 0)}" style="padding:3px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.1);color:inherit;font-size:11px;cursor:pointer;">${esc(tr(preset.labelKey, preset.label))}</button>`;
    }
  }
  html += `</div>`;

  const fromVal = (document.getElementById('fromDate') as HTMLInputElement | null)?.value || '';
  const toVal = (document.getElementById('toDate') as HTMLInputElement | null)?.value || '';
  html += `<div id="customPeriodFields" style="display:${fromVal || toVal ? 'flex' : 'none'};gap:6px;margin-top:4px;align-items:center;">
    <input type="date" value="${fromVal}" data-condition-period-target="fromDate" style="padding:4px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:12px;">
    <span style="font-size:12px;">${esc(tr('common.range_sep', '–'))}</span>
    <input type="date" value="${toVal}" data-condition-period-target="toDate" style="padding:4px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:12px;">
  </div>`;

  return html;
}

export function renderResolutionField(): string {
  const { tr } = getAppApi();
  const presets = [
    { label: '', labelKey: 'resolution.w512', minW: 512 },
    { label: '', labelKey: 'resolution.w768', minW: 768 },
    { label: '', labelKey: 'resolution.w1024', minW: 1024 },
    { label: '', labelKey: 'resolution.square_1024', minW: 1024, maxW: 1024, minH: 1024, maxH: 1024 },
    { label: '', labelKey: 'resolution.landscape', minW: 1024, maxH: 768 },
    { label: '', labelKey: 'resolution.portrait', maxW: 768, minH: 1024 },
    { label: '', labelKey: 'resolution.square', minW: 512, maxW: 1024, minH: 512, maxH: 1024 },
    { label: '', labelKey: 'common.reset' },
  ];

  let html = `<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:4px;">`;
  for (const p of presets) {
    html += `<button type="button" data-condition-resolution-min-w="${String(p.minW || 0)}" data-condition-resolution-max-w="${String(p.maxW || 0)}" data-condition-resolution-min-h="${String(p.minH || 0)}" data-condition-resolution-max-h="${String(p.maxH || 0)}" style="padding:3px 8px;border-radius:10px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.1);color:inherit;font-size:11px;cursor:pointer;">${esc(tr(p.labelKey, p.label))}</button>`;
  }
  html += `</div>`;

  const mw = (document.getElementById('minWidth') as HTMLInputElement | null)?.value || '';
  const xw = (document.getElementById('maxWidth') as HTMLInputElement | null)?.value || '';
  const mh = (document.getElementById('minHeight') as HTMLInputElement | null)?.value || '';
  const xh = (document.getElementById('maxHeight') as HTMLInputElement | null)?.value || '';
  html += `<div style="display:flex;gap:6px;align-items:center;flex-wrap:wrap;">
    <span style="font-size:11px;color:#888;">W:</span>
    <input type="number" value="${mw}" placeholder="≥min" min="0" step="64" data-condition-resolution-target="minWidth"
      style="width:70px;padding:4px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:12px;">
    <span style="font-size:11px;">${esc(tr('common.range_sep', '–'))}</span>
    <input type="number" value="${xw}" placeholder="≤max" min="0" step="64" data-condition-resolution-target="maxWidth"
      style="width:70px;padding:4px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:12px;">
    <span style="font-size:11px;color:#888;margin-left:8px;">H:</span>
    <input type="number" value="${mh}" placeholder="≥min" min="0" step="64" data-condition-resolution-target="minHeight"
      style="width:70px;padding:4px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:12px;">
    <span style="font-size:11px;">${esc(tr('common.range_sep', '–'))}</span>
    <input type="number" value="${xh}" placeholder="≤max" min="0" step="64" data-condition-resolution-target="maxHeight"
      style="width:70px;padding:4px;border-radius:4px;border:1px solid rgba(255,255,255,0.2);background:rgba(0,0,0,0.15);color:inherit;font-size:12px;">
  </div>`;

  return html;
}
