/**
 * extensions-summary.ts -- Extension manager summary display.
 * Converted from tools-extensions-summary.js
 */

import { getAppApi } from '../shared/browser-apis';
import { apiFetch } from './api';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

interface Extension {
  enabled: boolean;
  name: string;
}

export async function loadExtensions(): Promise<void> {
  const el = document.getElementById('extensionsSummary');
  if (!el) return;
  try {
    const res = await apiFetch('/api/extensions');
    const data: { extensions?: Extension[] } = await res.json();
    const exts = data.extensions || [];
    const enabled = exts.filter((e) => e.enabled).length;
    el.textContent =
      exts.length > 0
        ? exts.length +
          ' extensions (' +
          enabled +
          ' ' +
          _t('tools.ext_enabled', 'enabled') +
          ')'
        : _t('tools.no_extensions', 'No extensions');
  } catch {
    el.textContent = '';
  }
}
