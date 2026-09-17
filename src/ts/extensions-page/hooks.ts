/**
 * Extension hooks viewer — loads and renders hook registrations.
 * Converted from static/js/extensions/extensions-hooks.js
 */

import { getAppApi } from '../shared/browser-apis';
import { extensionApiFetch, extensionEsc } from './api';

/** i18n helper: use window.tr if available, otherwise return fallback. */
function _t(key: string, fallback: string = ''): string {
  return getAppApi().tr(key, fallback);
}

interface HookHandler {
  priority: number;
  extension: string;
  enabled: boolean;
}

interface HookInfo {
  handlers?: HookHandler[];
  mode?: string;
}

interface HookDefinitions {
  [hookName: string]: { mode?: string };
}

interface HooksApiResponse {
  definitions?: HookDefinitions;
  hooks?: Record<string, HookInfo>;
}

/**
 * Load extension hook registrations and render them into #extensionHooks.
 */
export async function loadExtensionHooks(): Promise<void> {
  const container = document.getElementById('extensionHooks');
  if (!container) return;

  try {
    const res = await extensionApiFetch('/api/extensions/hooks');
    const data: HooksApiResponse = await res.json();

    const hookDefs = data.definitions || {};
    const hooks = data.hooks || {};

    let html = '';
    for (const [hookName, info] of Object.entries(hooks)) {
      const handlers = info.handlers || [];
      const mode = hookDefs[hookName]?.mode || info.mode || '?';
      const modeColor = mode === 'exclusive' ? '#9a3412' : '#1e40af';
      const safeHookName = extensionEsc(hookName);
      const safeMode = extensionEsc(mode);

      html += `<div style="margin-bottom:12px;padding:10px 14px;border-radius:8px;background:rgba(0,0,0,0.1);border:1px solid rgba(255,255,255,0.05);">
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;">
          <code style="background:rgba(100,100,100,0.25);padding:2px 8px;border-radius:4px;font-size:13px;color:var(--text,#333);">${safeHookName}</code>
          <span style="font-size:11px;color:${modeColor};border:1px solid ${modeColor};padding:1px 6px;border-radius:10px;">${safeMode}</span>
        </div>`;

      if (handlers.length > 0) {
        for (const h of handlers) {
          const color = h.enabled ? '#166534' : '#666';
          const strike = h.enabled ? '' : 'text-decoration:line-through;';
          const safePriority = extensionEsc(String(h.priority));
          const safeExtension = extensionEsc(h.extension);
          html += `<div style="margin-left:20px;font-size:12px;color:${color};${strike}padding:2px 0;">
            <span style="display:inline-block;width:36px;text-align:right;color:#666;font-size:11px;margin-right:8px;">${safePriority}</span>
            \u2192 ${safeExtension}
          </div>`;
        }
      } else {
        html += '<div style="margin-left:20px;font-size:12px;color:#555;font-style:italic;">'
          + (_t('ext.no_handlers') || 'No handlers registered')
          + '</div>';
      }
      html += '</div>';
    }

    container.innerHTML = html
      || '<span style="color:#666;">' + (_t('ext.no_hook_info') || 'No hook info') + '</span>';
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : String(err);
    container.innerHTML = `<span style="color:#e74c3c;">${_t('ext.fetch_failed') || 'Fetch failed'}: ${extensionEsc(message)}</span>`;
  }
}
