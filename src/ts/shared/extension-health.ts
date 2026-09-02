/**
 * Shared rendering for extension runtime health.
 *
 * Backend contract (core/extensions_core/lifecycle/extensions_health.py):
 *   health = {
 *     available: boolean,
 *     checks: Record<string, boolean>,
 *     reason: string,            // English fallback
 *     reason_i18n_key: string,   // optional i18n key
 *   } | null  // null when extension does not expose get_health()
 *
 * Both the Extensions page and the Tools page (Hailo partials) call this
 * module so the badge text, color, and tooltip stay consistent.
 */

import { getAppApi } from './browser-apis';

export interface HealthInfo {
  available: boolean;
  checks?: Record<string, boolean>;
  reason?: string;
  reason_i18n_key?: string;
}

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/** Resolve the localized reason string for a health entry. */
export function healthReasonText(health: HealthInfo): string {
  const key = (health.reason_i18n_key || '').trim();
  const fallback = health.reason || '';
  if (key) {
    const translated = _t(key, '');
    if (translated && translated !== key) return translated;
  }
  return fallback;
}

/** Lookup color/icon/label for a given health verdict. */
export function healthVerdict(health: HealthInfo | null | undefined): {
  icon: string;
  color: string;
  label: string;
} {
  if (health == null) {
    // Extension did not expose get_health() — caller should fall back to manifest status.
    return { icon: '', color: '', label: '' };
  }
  if (health.available) {
    return {
      icon: '✅',
      color: 'var(--status-ok,#166534)',
      label: _t('ext.health.available', 'Available'),
    };
  }
  return {
    icon: '⚠️',
    color: '#9a3412',
    label: _t('ext.health.unavailable', 'Unavailable'),
  };
}

function _esc(value: string): string {
  return value
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

/**
 * Render a compact inline badge (icon + label + optional reason tooltip).
 * Returns empty string when health is null so the caller can fall back to the
 * generic manifest-status badge.
 */
export function renderHealthBadge(health: HealthInfo | null | undefined): string {
  if (health == null) return '';
  const v = healthVerdict(health);
  const reason = healthReasonText(health);
  const tooltip = reason ? _esc(reason) : _esc(v.label);
  const bg = health.available ? 'rgba(46,204,113,0.15)' : 'rgba(230,126,34,0.15)';
  return `<span style="font-size:11px;padding:1px 7px;border-radius:9px;background:${bg};color:${v.color};" title="${tooltip}">${v.icon} ${_esc(v.label)}</span>`;
}

/**
 * Render a multi-line detail block for the Tools page (shows per-check rows
 * + the localized reason). Returns empty string when health is null.
 */
export function renderHealthDetails(health: HealthInfo | null | undefined): string {
  if (health == null) return '';
  const v = healthVerdict(health);
  const reason = healthReasonText(health);
  const rows: string[] = [];
  rows.push(
    `<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
      <span style="font-size:14px;color:${v.color};">${v.icon} <strong>${_esc(v.label)}</strong></span>
    </div>`,
  );
  if (health.checks) {
    const checkLabels: Record<string, string> = {
      runtime_ok: _t('ext.health.check.runtime', 'Runtime library'),
      hardware_ok: _t('ext.health.check.hardware', 'Hardware device'),
      hef_ok: _t('ext.health.check.hef', 'Model file (HEF)'),
      onnx_ok: _t('ext.health.check.onnx', 'ONNX Runtime'),
      hailo_npu: _t('ext.health.check.hailo_npu', 'Hailo NPU'),
    };
    const items: string[] = [];
    for (const [key, ok] of Object.entries(health.checks)) {
      const label = checkLabels[key] || key;
      const icon = ok ? '✅' : '❌';
      items.push(`<li style="font-size:12px;color:var(--muted,#aab2c0);">${icon} ${_esc(label)}</li>`);
    }
    if (items.length > 0) {
      rows.push(`<ul style="list-style:none;padding:0;margin:0 0 6px 0;">${items.join('')}</ul>`);
    }
  }
  if (reason) {
    const rc = health.available ? 'var(--muted,#6b7280)' : '#9a3412';
    const rb = health.available ? 'rgba(100,100,100,0.08)' : 'rgba(231,76,60,0.08)';
    rows.push(
      `<div style="font-size:12px;color:${rc};padding:4px 8px;background:${rb};border-radius:4px;">${_esc(reason)}</div>`,
    );
  }
  return rows.join('');
}
