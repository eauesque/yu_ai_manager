/**
 * secrets-tab-utils.ts -- Shared utility functions for the secrets tab.
 * Translation helper, HTML escaping, source badge rendering.
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch } from '../main/api-utils';

/* ── Translation helper ──────────────────────────────── */

export function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

/* ── HTML escape ─────────────────────────────────────── */

export function _esc(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/* ── Source badge ─────────────────────────────────────── */

export function _sourceBadge(source: string): string {
  const colors: Record<string, { bg: string; fg: string }> = {
    '1password': { bg: 'rgba(59,130,246,.15)', fg: '#3b82f6' },
    bitwarden: { bg: 'rgba(23,93,220,.15)', fg: '#175ddc' },
    encrypted: { bg: 'rgba(34,197,94,.15)', fg: '#22c55e' },
    config: { bg: 'rgba(234,179,8,.15)', fg: '#eab308' },
    default: { bg: 'rgba(128,128,128,.15)', fg: 'var(--muted,#888)' },
  };
  const c = colors[source] || colors.default;
  return `<span style="display:inline-block;padding:1px 6px;border-radius:4px;font-size:11px;font-weight:600;background:${c.bg};color:${c.fg}">${_esc(source)}</span>`;
}

/* ── Fetch secret settings and schema (shared by overview + wizards) ── */

export interface SecretSetting {
  key: string;
  value: unknown;
  source: string;
  secret: boolean;
}

export interface SecretSchema {
  key: string;
  op_eligible: boolean;
  description: string;
  secret: boolean;
}

export async function fetchSecretSettingsAndSchema(): Promise<{
  settings: SecretSetting[];
  schema: SecretSchema[];
}> {
  const [settingsRes, schemaRes] = await Promise.all([
    apiFetch('/api/settings/all'),
    apiFetch('/api/settings/schema'),
  ]);
  const settingsData = await settingsRes.json();
  const schemaData = await schemaRes.json();
  const settings = (settingsData.data?.settings ?? settingsData.settings ?? []) as SecretSetting[];
  const schema = (schemaData.data?.schema ?? schemaData.schema ?? []) as SecretSchema[];
  return { settings, schema };
}
