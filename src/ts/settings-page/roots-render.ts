/**
 * Settings page — roots list rendering.
 * Converted from static/js/settings/settings-roots-render.js
 */

import { getAppApi } from '../shared/browser-apis';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export interface ScanRoot {
  path: string;
  enabled: boolean;
  recursive?: boolean;
  comment?: string;
}

export function emptyHtml(): string {
  return '<div style="color:#888;">' + _t('settings.no_roots', 'No registered folders.') + '</div>';
}

export function errorHtml(): string {
  return '<span style="color:#d32f2f;">' + _t('settings.load_failed', 'Load failed') + '</span>';
}

export function buildRootsHtml(roots: ScanRoot[]): string {
  let html = '';
  roots.forEach((r, i) => {
    const icon = r.enabled ? '\u2705' : '\u2B1C';
    const pathStyle = r.path.length < 5 || r.path.endsWith('\\') || r.path.endsWith('/')
      ? 'color:#d32f2f;' : '';
    const commentVal = (r.comment || '').replace(/"/g, '&quot;');
    html += '<div style="background:rgba(128,128,128,0.08);border-radius:8px;margin-bottom:6px;padding:8px 12px;">' +
      '<div style="display:flex;align-items:center;gap:8px;">' +
        '<span style="cursor:pointer;" data-action="settingsPageApi.toggleScanRoot" data-action-arg="' + i + '" title="' + _t('settings.toggle_root', 'Enable/Disable') + '">' + icon + '</span>' +
        '<input type="text" id="rootPath' + i + '" value="' + r.path.replace(/"/g, '&quot;') + '" ' +
          'aria-label="Scan root path ' + (i + 1) + '" ' +
          'style="flex:1;padding:4px 8px;border-radius:4px;border:1px solid rgba(128,128,128,0.3);background:var(--bg);color:var(--text);font-size:13px;' + pathStyle + '">' +
        '<button data-action="settingsPageApi.saveRootPath" data-action-arg="' + i + '" style="background:none;border:1px solid rgba(128,128,128,0.3);border-radius:4px;cursor:pointer;padding:4px 8px;font-size:11px;color:var(--text);" title="' + _t('settings.save_path', 'Save path') + '">\uD83D\uDCBE</button>' +
        (r.recursive ? ' <span style="color:#888;font-size:11px;" title="' + _t('settings.recursive_scan', 'Recursive scan') + '">\uD83D\uDCC2</span>' : '') +
        '<button data-action="settingsPageApi.removeScanRoot" data-action-arg="' + i + '" style="background:none;border:none;cursor:pointer;font-size:16px;" title="' + _t('settings.delete', 'Delete') + '">\uD83D\uDDD1\uFE0F</button>' +
      '</div>' +
      '<div style="margin-top:5px;">' +
        '<input type="text" id="rootComment' + i + '" value="' + commentVal + '" ' +
          'placeholder="' + _t('settings.root_comment_placeholder', 'Memo (optional)') + '" ' +
          'aria-label="' + _t('settings.root_comment_label', 'Folder memo') + '" ' +
          'data-action="settingsPageApi.saveRootComment" data-action-arg="' + i + '" data-action-event="change" ' +
          'style="width:100%;padding:3px 8px;border-radius:4px;border:1px solid rgba(128,128,128,0.2);background:var(--bg);color:var(--muted,#aab2c0);font-size:11px;">' +
      '</div>' +
    '</div>';
  });
  return html;
}
