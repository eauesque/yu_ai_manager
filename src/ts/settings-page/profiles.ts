/**
 * Settings page — Profile Manager UI.
 *
 * Provides full CRUD for profiles, QR export/import, and favorite toggling.
 * Replaces the simple renderProfileSection() in server-status.ts.
 *
 * Theme-related QR export/import logic lives in profiles-theme.ts.
 */

import {
  deleteProfile,
  duplicateProfile,
  exportProfileQR,
  refreshProfiles,
  renameProfile,
  showCreateProfileDialog,
  showImportProfileDialog,
  toggleProfileFavorite,
} from './profiles-actions';
import { getAppApi } from '../shared/browser-apis';
import { formatRelativeTime } from './profiles-time';
import { switchProfileFromSettings } from './security-actions';
import { icon } from '../shared/icon';

export {
  deleteProfile,
  duplicateProfile,
  exportProfileQR,
  renameProfile,
  showCreateProfileDialog,
  showImportProfileDialog,
  toggleProfileFavorite,
};

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

function esc(s: string): string {
  const el = document.createElement('span');
  el.textContent = s;
  return el.innerHTML;
}

interface ProfileData {
  name: string;
  label: string;
  description?: string;
  favorite?: boolean;
  last_used_at?: string | null;
  created_at?: string | null;
  is_active?: boolean;
  db?: string;
}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

export function renderProfileManager(
  profiles: ProfileData[],
  activeProfile: string,
  hasPinActive: boolean,
): void {
  const section = document.getElementById('profileSection');
  const content = document.getElementById('profileContent');
  if (!section || !content) return;

  section.style.display = '';

  if (profiles.length === 0) {
    content.innerHTML =
      '<div style="padding:16px;border-radius:8px;border:1px solid rgba(128,128,128,0.15);background:rgba(128,128,128,0.04);margin-bottom:12px;">' +
      '<p style="font-weight:600;margin:0 0 6px 0;font-size:13px;" data-i18n="settings.profile_what_is">プロファイルとは</p>' +
      '<p style="color:var(--muted);margin:0 0 10px 0;font-size:12px;line-height:1.5;" data-i18n="settings.profile_guide">' +
      'プロファイルは DB・設定セットのスナップショットです。用途別に切り替えることで、異なるライブラリや生成設定を素早く切り替えられます。' +
      '</p>' +
      '<button type="button" class="profile-action-btn" data-profile-action="create" style="padding:6px 16px;border:1px solid rgba(128,128,128,0.3);border-radius:6px;background:none;color:var(--text);cursor:pointer;">' +
      '+ ' + esc(_t('settings.profile_create', 'Create Profile')) + '</button></div>';
    _bindProfileActions(content);
    return;
  }

  let html = '';
  if (!hasPinActive) {
    html += '<p style="color:#d32f2f;font-size:12px;margin-bottom:10px;">' +
      esc(_t('settings.profile_no_pin', 'Profile management requires PIN auth. Set a PIN and restart.')) + '</p>';
  }

  // Toolbar
  html += '<div style="display:flex;gap:8px;margin-bottom:12px;flex-wrap:wrap;">';
  html += '<button type="button" class="profile-action-btn" data-profile-action="create"' + (hasPinActive ? '' : ' disabled') +
    ' style="padding:4px 14px;border:1px solid rgba(128,128,128,0.3);border-radius:6px;background:none;color:var(--text);cursor:pointer;font-size:13px;">' +
    '+ ' + esc(_t('settings.profile_create', 'Create Profile')) + '</button>';
  html += '<button type="button" class="profile-action-btn" data-profile-action="import"' + (hasPinActive ? '' : ' disabled') +
    ' style="padding:4px 14px;border:1px solid rgba(128,128,128,0.3);border-radius:6px;background:none;color:var(--text);cursor:pointer;font-size:13px;">' +
    esc(_t('settings.profile_qr_import', 'QR Import')) + '</button>';
  html += '</div>';

  // Profile cards
  html += '<div style="display:flex;flex-direction:column;gap:8px;">';
  for (const p of profiles) {
    const isActive = p.name === activeProfile;
    const safeName = esc(p.name);
    const safeLabel = esc(p.label);
    const favStar = p.favorite ? icon('star-filled') : icon('star');
    const favColor = p.favorite ? '#f1c40f' : '#888';

    const lastUsed = p.last_used_at
      ? _t('settings.profile_last_used', 'Last used') + ': ' + formatRelativeTime(p.last_used_at)
      : _t('settings.profile_never_used', 'Never used');

    const descText = p.description ? esc(p.description) : _t('settings.profile_no_desc', 'No description');

    html += '<div style="padding:10px 14px;border:' + (isActive ? '2px solid #2ecc71' : '1px solid rgba(128,128,128,0.3)') +
      ';border-radius:8px;' + (isActive ? 'background:rgba(46,204,113,0.08);' : '') +
      'display:flex;align-items:center;gap:10px;flex-wrap:wrap;">';

    // Favorite star
    html += '<button type="button" class="profile-action-btn" data-profile-action="favorite" data-profile-name="' + safeName + '" style="background:none;border:none;cursor:pointer;font-size:16px;color:' + favColor + ';padding:0;" title="' +
      esc(_t('settings.profile_toggle_fav', 'Toggle favorite')) + '">' + favStar + '</button>';

    // Label + meta
    html += '<div style="flex:1;min-width:150px;">';
    html += '<span style="font-weight:600;">' + safeLabel + '</span>';
    if (isActive) {
      html += ' <span style="background:#2ecc71;color:#fff;padding:2px 8px;border-radius:4px;font-size:11px;font-weight:600;">' +
        esc(_t('settings.profile_active_badge', 'Active')) + '</span>';
    }
    html += '<div style="font-size:11px;color:var(--muted,#666);margin-top:2px;">' + descText + ' &middot; ' + lastUsed + '</div>';
    if (p.db) {
      html += '<div style="font-size:11px;color:#6aafff;margin-top:2px;" title="' + esc(p.db) + '">DB: ' + esc(p.db) + '</div>';
    }
    html += '</div>';

    // Action buttons
    html += '<div style="display:flex;gap:6px;flex-wrap:wrap;">';
    if (!isActive) {
      html += '<button type="button" class="profile-action-btn" data-profile-action="switch" data-profile-name="' + safeName + '" data-profile-label="' + safeLabel + '"' +
        (hasPinActive ? '' : ' disabled') +
        ' style="padding:4px 12px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:12px;">' +
        esc(_t('settings.profile_switch_btn', 'Switch')) + '</button>';
    }
    html += '<button type="button" class="profile-action-btn" data-profile-action="export-qr" data-profile-name="' + safeName + '"' + (hasPinActive ? '' : ' disabled') +
      ' style="padding:4px 8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:12px;" title="QR Export">QR</button>';

    // Overflow menu
    html += '<div style="position:relative;display:inline-block;">';
    html += '<button type="button" class="profile-menu-toggle" ' +
      'style="padding:4px 8px;border:1px solid rgba(128,128,128,0.3);border-radius:4px;background:none;color:var(--text);cursor:pointer;font-size:12px;">...</button>';
    html += '<div class="profile-menu" style="display:none;position:absolute;right:0;top:100%;background:var(--bg,#1a1a2e);border:1px solid rgba(128,128,128,0.3);border-radius:6px;min-width:140px;z-index:100;box-shadow:0 4px 12px rgba(0,0,0,0.3);">';
    html += '<button type="button" class="profile-action-btn" data-profile-action="duplicate" data-profile-name="' + safeName + '" style="display:block;width:100%;text-align:left;padding:8px 12px;border:none;background:none;color:var(--text);cursor:pointer;font-size:12px;">' +
      esc(_t('settings.profile_duplicate', 'Duplicate')) + '</button>';
    html += '<button type="button" class="profile-action-btn" data-profile-action="rename" data-profile-name="' + safeName + '" style="display:block;width:100%;text-align:left;padding:8px 12px;border:none;background:none;color:var(--text);cursor:pointer;font-size:12px;">' +
      esc(_t('settings.profile_rename', 'Rename')) + '</button>';
    if (!isActive) {
      html += '<button type="button" class="profile-action-btn" data-profile-action="delete" data-profile-name="' + safeName + '" data-profile-label="' + safeLabel + '" style="display:block;width:100%;text-align:left;padding:8px 12px;border:none;background:none;color:#d32f2f;cursor:pointer;font-size:12px;">' +
        esc(_t('settings.profile_delete', 'Delete')) + '</button>';
    }
    html += '</div></div>';

    html += '</div>';  // action buttons
    html += '</div>';  // card
  }
  html += '</div>';

  content.innerHTML = html;
  _bindProfileActions(content);

  // Close overflow menus on outside click
  document.addEventListener('click', _closeOverflowMenus, { once: true });
}

function _bindProfileActions(content: HTMLElement): void {
  content.querySelectorAll<HTMLButtonElement>('.profile-menu-toggle').forEach((btn) => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const menu = btn.nextElementSibling as HTMLElement | null;
      if (!menu) return;
      menu.style.display = menu.style.display === 'block' ? 'none' : 'block';
    });
  });

  content.querySelectorAll<HTMLButtonElement>('.profile-action-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      const action = btn.dataset.profileAction;
      const name = btn.dataset.profileName || '';
      const label = btn.dataset.profileLabel || '';
      if (action === 'create') {
        void showCreateProfileDialog(() => refreshProfiles(renderProfileManager));
      } else if (action === 'import') {
        void showImportProfileDialog(() => refreshProfiles(renderProfileManager));
      } else if (action === 'favorite' && name) {
        void toggleProfileFavorite(name, () => refreshProfiles(renderProfileManager));
      } else if (action === 'switch' && name) {
        void switchProfileFromSettings(name, label);
      } else if (action === 'export-qr' && name) {
        void exportProfileQR(name);
      } else if (action === 'duplicate' && name) {
        void duplicateProfile(name, () => refreshProfiles(renderProfileManager));
      } else if (action === 'rename' && name) {
        void renameProfile(name, () => refreshProfiles(renderProfileManager));
      } else if (action === 'delete' && name) {
        void deleteProfile(name, label, () => refreshProfiles(renderProfileManager));
      }
    });
  });
}

function _closeOverflowMenus(e: Event): void {
  const menus = document.querySelectorAll('#profileContent div[style*="position:absolute"]');
  for (const m of menus) {
    const el = m as HTMLElement;
    if (!el.contains(e.target as Node)) {
      el.style.display = 'none';
    }
  }
}
