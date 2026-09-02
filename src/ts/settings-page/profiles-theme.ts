/**
 * Settings page — Profile QR export/import with theme integration.
 *
 * Leaf module: no imports from profiles.ts to avoid circular dependencies.
 * The refreshFn callback is injected by the caller (profiles.ts).
 */

import { getAppApi } from '../shared/browser-apis';
import { getActiveThemeId, loadCustomThemes, setActiveThemeId, saveCustomThemes } from '../theme-system/storage';
import { getActiveTheme } from '../theme-system/apply';
import { applyTheme } from '../theme-system/apply';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function esc(s: string): string {
  const el = document.createElement('span');
  el.textContent = s;
  return el.innerHTML;
}

export async function exportProfileQR(name: string): Promise<void> {
  try {
    const res = await fetch('/api/profiles/' + encodeURIComponent(name) + '/export');
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Export failed');
      return;
    }

    // Show QR data in a modal
    // Inject client-side theme data into profile export
    let qrData = data.qr_data || '';
    try {
      const parsed = JSON.parse(qrData);
      if (parsed && parsed.profile) {
        const themeId = getActiveThemeId();
        if (themeId) {
          parsed.profile._theme = {
            activeThemeId: themeId,
            customThemes: loadCustomThemes(),
          };
          qrData = JSON.stringify(parsed);
        }
      }
    } catch { /* ignore parse errors */ }
    const modal = document.createElement('div');
    modal.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.7);z-index:9999;display:flex;align-items:center;justify-content:center;';
    modal.onclick = (e) => { if (e.target === modal) modal.remove(); };

    const box = document.createElement('div');
    box.style.cssText = 'background:var(--bg,#1a1a2e);border:1px solid rgba(128,128,128,0.3);border-radius:12px;padding:24px;max-width:500px;width:90%;max-height:80vh;overflow:auto;';

    box.innerHTML =
      '<h3 style="margin-top:0;">' + esc(_t('settings.profile_qr_title', 'Profile Export')) + ' — ' + esc(name) + '</h3>' +
      '<p style="font-size:12px;color:#888;">' + esc(_t('settings.profile_qr_hint', 'Copy the data below or scan the QR code to import on another instance.')) + '</p>' +
      '<textarea readonly style="width:100%;height:120px;font-family:monospace;font-size:11px;background:rgba(128,128,128,0.1);border:1px solid rgba(128,128,128,0.3);border-radius:6px;padding:8px;color:var(--text);resize:vertical;">' + esc(qrData) + '</textarea>' +
      '<div style="margin-top:12px;text-align:right;">' +
      '<button onclick="this.closest(\'div[style*=position\\\\:fixed]\').remove()" style="padding:6px 16px;border:1px solid rgba(128,128,128,0.3);border-radius:6px;background:none;color:var(--text);cursor:pointer;">' +
      esc(_t('common.close', 'Close')) + '</button></div>';

    modal.appendChild(box);
    document.body.appendChild(modal);
  } catch (e) {
    alert(_t('settings.profile_export_failed', 'Export failed') + ': ' + (e instanceof Error ? e.message : String(e)));
  }
}

export async function showImportProfileDialog(refreshFn: () => Promise<void>): Promise<void> {
  const raw = prompt(_t('settings.profile_import_prompt', 'Paste QR profile data (JSON):'));
  if (!raw) return;

  try {
    // Preview
    const preRes = await fetch('/api/profiles/import-preview', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ qr_data: raw }),
    });
    const preData = await preRes.json();
    if (!preRes.ok) {
      alert(preData.error || 'Preview failed');
      return;
    }

    let mode = 'new';
    if (preData.mode === 'existing') {
      const diffKeys = Object.keys(preData.diff || {});
      const msg = _t('settings.profile_import_exists', 'Profile "{name}" already exists. {count} field(s) differ.\nImport mode: full (overwrite) or diff (merge changes)?')
        .replace('{name}', preData.name)
        .replace('{count}', String(diffKeys.length));
      const choice = prompt(msg + '\n\nType "full" or "diff":', 'diff');
      if (!choice) return;
      mode = choice.trim().toLowerCase() === 'full' ? 'full' : 'diff';
    }

    const impRes = await fetch('/api/profiles/import', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ qr_data: raw, mode }),
    });
    const impData = await impRes.json();
    if (!impRes.ok) {
      alert(impData.error || 'Import failed');
      return;
    }

    // Restore theme data if present in import
    try {
      const parsedImport = JSON.parse(raw);
      const themeData = parsedImport?.profile?._theme;
      if (themeData) {
        if (Array.isArray(themeData.customThemes) && themeData.customThemes.length > 0) {
          // Merge custom themes (don't overwrite existing ones)
          const existing = loadCustomThemes();
          const existingIds = new Set(existing.map((t: { id: string }) => t.id));
          for (const t of themeData.customThemes) {
            if (!existingIds.has(t.id)) {
              existing.push(t);
            }
          }
          saveCustomThemes(existing);
        }
        if (themeData.activeThemeId) {
          setActiveThemeId(themeData.activeThemeId);
          const theme = getActiveTheme();
          if (theme) applyTheme(theme);
        }
      }
    } catch { /* ignore theme restore errors */ }

    alert(_t('settings.profile_import_success', 'Profile imported successfully.'));
    await refreshFn();
  } catch (e) {
    alert(_t('settings.profile_import_failed', 'Import failed') + ': ' + (e instanceof Error ? e.message : String(e)));
  }
}
