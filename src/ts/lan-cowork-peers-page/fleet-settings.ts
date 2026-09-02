/**
 * lan-cowork-peers-page/fleet-settings.ts
 * Fleet 設定パネル — chief トグルの読み込み・保存。
 */
import { getFleetSettings, saveFleetSettings, showToast, tr } from './api';

export function initFleetSettingsPanel(): void {
  const toggle = document.getElementById('lcFleetChiefToggle') as HTMLInputElement | null;
  const status = document.getElementById('lcFleetSaveStatus') as HTMLElement | null;
  const linkRow = document.getElementById('lcFleetAdminLinkRow') as HTMLElement | null;
  if (!toggle) return;

  const updateLinkVisibility = (chief: boolean) => {
    if (linkRow) linkRow.hidden = !chief;
  };

  getFleetSettings().then((res) => {
    if (res.ok) {
      toggle.checked = !!res.chief;
      updateLinkVisibility(!!res.chief);
    }
  }).catch(() => {/* silent */});

  toggle.addEventListener('change', async () => {
    const chief = toggle.checked;
    if (status) { status.hidden = false; status.textContent = tr('lc_peers.fleet.saving', '保存中...'); }
    try {
      const res = await saveFleetSettings(chief);
      if (res.ok) {
        if (status) { status.textContent = tr('lc_peers.fleet.saved', '保存しました'); }
        updateLinkVisibility(chief);
        showToast(chief
          ? tr('lc_peers.fleet.chief_enabled', 'Fleet Chief を有効にしました。Fleet Admin リンクが表示されます')
          : tr('lc_peers.fleet.chief_disabled', 'Fleet Chief を無効にしました'));
      } else {
        toggle.checked = !chief;
        showToast(tr('lc_peers.fleet.save_error', '設定の保存に失敗しました') + ': ' + (res.error ?? ''));
        if (status) { status.hidden = true; }
      }
    } catch {
      toggle.checked = !chief;
      showToast(tr('lc_peers.fleet.save_error', '設定の保存に失敗しました'));
      if (status) { status.hidden = true; }
    }
  });
}
