/**
 * secrets-tab-bw-wizard.ts -- Push-to-Bitwarden bulk migration wizard (Steps 1-3).
 */

import { apiFetch } from '../main/api-utils';
import { getNavApi } from '../shared/browser-apis';
import { _t, _esc, _sourceBadge, fetchSecretSettingsAndSchema } from './secrets-tab-utils';

// Lazy-bound reference; set by the main barrel file to avoid circular deps.
let _refreshOverview: (() => void) | null = null;
export function _setRefreshOverview(fn: () => void): void {
  _refreshOverview = fn;
}

const { showToast } = getNavApi();

let _bwPushWizardOpen = false;

/* -- Push to Bitwarden wizard: Step 1 (folder selection) -- */

export async function showPushToBwWizard(): Promise<void> {
  const area = document.getElementById('bwPushWizardArea');
  if (!area) return;

  // Toggle: close if already open
  if (_bwPushWizardOpen) {
    area.innerHTML = '';
    _bwPushWizardOpen = false;
    return;
  }
  _bwPushWizardOpen = true;

  // Step 1: Folder selection + item name
  area.innerHTML = `<div style="padding:12px;border:1px solid var(--border,#333);border-radius:6px;background:rgba(128,128,128,.05)">
    <div style="font-weight:600;margin-bottom:8px">ステップ 1: フォルダ・アイテム名</div>
    <div id="bwPushFolderLoading" style="color:var(--muted,#888);font-size:12px">フォルダ一覧を取得中...</div>
  </div>`;

  try {
    const res = await apiFetch('/api/settings/secrets/bw-folders');
    const d = await res.json();
    const data = d.data ?? d;
    const folders: Array<{ id: string; name: string }> = data.folders ?? [];

    if (!_bwPushWizardOpen) return; // Closed while fetching

    let optionsHtml = `<option value="">${_t('secrets.no_folder', '(No folder)')}</option>`;
    for (const f of folders) {
      optionsHtml += `<option value="${_esc(f.id)}">${_esc(f.name)}</option>`;
    }

    area.innerHTML = `<div style="padding:12px;border:1px solid var(--border,#333);border-radius:6px;background:rgba(128,128,128,.05)">
      <div style="font-weight:600;margin-bottom:8px">ステップ 1: フォルダ・アイテム名</div>
      <div style="margin-bottom:8px">
        <label style="font-size:12px;display:block;margin-bottom:4px">フォルダ (任意)</label>
        <select id="bwPushFolderSelect" style="padding:4px 8px;border-radius:4px;border:1px solid var(--border,#444);background:var(--bg-input,#1a1a2e);color:inherit;font-size:13px;min-width:200px">
          ${optionsHtml}
        </select>
      </div>
      <div style="margin-bottom:8px">
        <label style="font-size:12px;display:block;margin-bottom:4px">アイテム名</label>
        <input type="text" id="bwPushItemName" value="YU AI Manager" style="padding:4px 8px;border-radius:4px;border:1px solid var(--border,#444);background:var(--bg-input,#1a1a2e);color:inherit;font-size:13px;min-width:200px" />
      </div>
      <div style="display:flex;gap:8px">
        <button class="btn btn-primary" id="bwPushNextBtn" style="font-size:12px;padding:4px 12px">次へ</button>
        <button class="btn btn-secondary" id="bwPushCancelBtn" style="font-size:12px;padding:4px 12px">キャンセル</button>
      </div>
    </div>`;

    document.getElementById('bwPushCancelBtn')?.addEventListener('click', () => {
      area.innerHTML = '';
      _bwPushWizardOpen = false;
    });
    document.getElementById('bwPushNextBtn')?.addEventListener('click', () => {
      const folderSelect = document.getElementById('bwPushFolderSelect') as HTMLSelectElement | null;
      const nameInput = document.getElementById('bwPushItemName') as HTMLInputElement | null;
      const folderId = folderSelect?.value ?? '';
      const itemName = nameInput?.value.trim() || 'YU AI Manager';
      _showBwPushStep2(area, folderId, itemName);
    });
  } catch (err) {
    if (!_bwPushWizardOpen) return;
    area.innerHTML = `<div style="padding:12px;border:1px solid var(--border,#333);border-radius:6px">
      <span style="color:#ef4444">フォルダ一覧の取得に失敗しました: ${_esc(err instanceof Error ? err.message : String(err))}</span>
      <div style="margin-top:8px"><button class="btn btn-secondary" id="bwPushCancelBtn" style="font-size:12px;padding:4px 12px">閉じる</button></div>
    </div>`;
    document.getElementById('bwPushCancelBtn')?.addEventListener('click', () => {
      area.innerHTML = '';
      _bwPushWizardOpen = false;
    });
  }
}

/* -- Push wizard Step 2: confirmation -- */

async function _showBwPushStep2(area: HTMLElement, folderId: string, itemName: string): Promise<void> {
  let secretRows = '';
  try {
    const { settings, schema } = await fetchSecretSettingsAndSchema();
    const opEligibleKeys = new Set(schema.filter(s => s.op_eligible).map(s => s.key));
    const targets = settings.filter(s => s.secret && opEligibleKeys.has(s.key));

    if (targets.length === 0) {
      area.innerHTML = `<div style="padding:12px;border:1px solid var(--border,#333);border-radius:6px">
        <span style="color:var(--muted,#888)">移行対象の secret 設定がありません。</span>
        <div style="margin-top:8px"><button class="btn btn-secondary" id="bwPushCancelBtn" style="font-size:12px;padding:4px 12px">閉じる</button></div>
      </div>`;
      document.getElementById('bwPushCancelBtn')?.addEventListener('click', () => {
        area.innerHTML = '';
        _bwPushWizardOpen = false;
      });
      return;
    }

    for (const t of targets) {
      secretRows += `<tr style="border-bottom:1px solid rgba(128,128,128,.15)">
        <td style="padding:4px 8px;font-size:12px"><code>${_esc(t.key)}</code></td>
        <td style="padding:4px 8px">${_sourceBadge(t.source)}</td>
      </tr>`;
    }
  } catch {
    secretRows = `<tr><td colspan="2" style="color:#ef4444;padding:4px 8px">${_t('secrets.fetch_failed', 'Failed to fetch settings')}</td></tr>`;
  }

  const folderLabel = folderId ? folderId : _t('secrets.no_folder', '(No folder)');

  area.innerHTML = `<div style="padding:12px;border:1px solid var(--border,#333);border-radius:6px;background:rgba(128,128,128,.05)">
    <div style="font-weight:600;margin-bottom:8px">ステップ 2: 確認</div>
    <div style="font-size:12px;margin-bottom:8px">
      <div>フォルダ: <strong>${_esc(folderLabel)}</strong></div>
      <div>アイテム名: <strong>${_esc(itemName)}</strong></div>
    </div>
    <div style="margin-bottom:8px">
      <div style="font-size:12px;font-weight:600;margin-bottom:4px">移行される設定:</div>
      <table style="width:100%;border-collapse:collapse;font-size:12px">
        <thead><tr style="border-bottom:1px solid var(--border,#333)">
          <th style="padding:4px 8px;text-align:left">Key</th>
          <th style="padding:4px 8px;text-align:left">Source</th>
        </tr></thead>
        <tbody>${secretRows}</tbody>
      </table>
    </div>
    <div style="padding:8px;background:rgba(234,179,8,.1);border-radius:4px;border:1px solid rgba(234,179,8,.3);font-size:12px;color:#eab308;margin-bottom:8px">
      Bitwarden に書き込まれ、マッピングが自動設定されます。
    </div>
    <div style="display:flex;gap:8px">
      <button class="btn btn-primary" id="bwPushExecBtn" style="font-size:12px;padding:4px 12px">実行</button>
      <button class="btn btn-secondary" id="bwPushCancelBtn" style="font-size:12px;padding:4px 12px">キャンセル</button>
    </div>
  </div>`;

  document.getElementById('bwPushCancelBtn')?.addEventListener('click', () => {
    area.innerHTML = '';
    _bwPushWizardOpen = false;
  });
  document.getElementById('bwPushExecBtn')?.addEventListener('click', () => {
    _showBwPushStep3(area, folderId, itemName);
  });
}

/* -- Push wizard Step 3: execution -- */

async function _showBwPushStep3(area: HTMLElement, folderId: string, itemName: string): Promise<void> {
  area.innerHTML = `<div style="padding:12px;border:1px solid var(--border,#333);border-radius:6px;background:rgba(128,128,128,.05)">
    <div style="font-weight:600;margin-bottom:8px">ステップ 3: 実行中</div>
    <div style="display:flex;align-items:center;gap:8px">
      <span class="spinner" style="display:inline-block;width:16px;height:16px;border:2px solid var(--muted,#888);border-top-color:var(--link,#3b82f6);border-radius:50%;animation:spin 1s linear infinite"></span>
      <span style="font-size:12px;color:var(--muted,#888)">Bitwarden へ書き込み中...</span>
    </div>
    <style>@keyframes spin{to{transform:rotate(360deg)}}</style>
  </div>`;

  try {
    const body: Record<string, string> = { item_name: itemName };
    if (folderId) {
      body.folder_id = folderId;
    }
    const res = await apiFetch('/api/settings/secrets/push-to-bw', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    });
    const d = await res.json();
    const data = d.data ?? d;

    if (data.message && !data.error) {
      const pushedKeys: string[] = data.pushed_keys ?? [];
      let keyList = '';
      for (const key of pushedKeys) {
        keyList += `<div style="padding:2px 0;font-size:11px"><code>${_esc(key)}</code></div>`;
      }

      area.innerHTML = `<div style="padding:12px;border:1px solid rgba(34,197,94,.3);border-radius:6px;background:rgba(34,197,94,.05)">
        <div style="font-weight:600;color:#22c55e;margin-bottom:8px">移行が完了しました</div>
        ${keyList ? `<div style="margin-bottom:8px">${keyList}</div>` : ''}
        <div style="font-size:12px;color:var(--muted,#888)">${_esc(data.message)}</div>
        <div style="margin-top:8px"><button class="btn btn-secondary" id="bwPushCloseBtn" style="font-size:12px;padding:4px 12px">閉じる</button></div>
      </div>`;

      showToast(_t('secrets.bw_migrated', '{count} secrets migrated to Bitwarden').replace('{count}', String(pushedKeys.length)));
      _refreshOverview?.();
    } else {
      area.innerHTML = `<div style="padding:12px;border:1px solid rgba(239,68,68,.3);border-radius:6px;background:rgba(239,68,68,.05)">
        <div style="font-weight:600;color:#ef4444;margin-bottom:8px">移行に失敗しました</div>
        <div style="font-size:12px;color:#ef4444">${_esc(data.error || _t('secrets.unknown_error', 'An unknown error occurred'))}</div>
        <div style="margin-top:8px"><button class="btn btn-secondary" id="bwPushCloseBtn" style="font-size:12px;padding:4px 12px">閉じる</button></div>
      </div>`;
    }
  } catch (err) {
    area.innerHTML = `<div style="padding:12px;border:1px solid rgba(239,68,68,.3);border-radius:6px;background:rgba(239,68,68,.05)">
      <div style="font-weight:600;color:#ef4444;margin-bottom:8px">移行に失敗しました</div>
      <div style="font-size:12px;color:#ef4444">${_esc(err instanceof Error ? err.message : String(err))}</div>
      <div style="margin-top:8px"><button class="btn btn-secondary" id="bwPushCloseBtn" style="font-size:12px;padding:4px 12px">閉じる</button></div>
    </div>`;
  }

  document.getElementById('bwPushCloseBtn')?.addEventListener('click', () => {
    area.innerHTML = '';
    _bwPushWizardOpen = false;
  });
}
