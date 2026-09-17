/**
 * wd-tagger/profile-list.ts -- Profile manager list view.
 *
 * DOM construction policy: createElement + textContent/value + appendChild only.
 * Avoid HTML string insertion and inline event handlers.
 */

import { fetchWdTaggerProfiles, type WdTaggerProfile } from './profiles';
import { customConfirm } from '../../shared/dialog';

export type ProfileOrigin = 'builtin' | 'user' | 'unknown';

export type ProfileListItem = WdTaggerProfile & {
  origin?: ProfileOrigin;
  overrides_builtin?: boolean;
};

export type ProfileListFilter = 'all' | 'user' | 'builtin';

export interface ProfileListCallbacks {
  onClose: () => void;
  onCreate: () => void;
  onEdit: (profile: ProfileListItem) => void;
  onDuplicate: (profile: ProfileListItem) => void;
  onImport: (profile: unknown) => void;
}

export interface ProfileListApi {
  refresh: () => Promise<void>;
}

type ImportTab = 'upload' | 'paste';

function _t(key: string, fallback: string): string {
  try {
    if (typeof window.tr === 'function') {
      const v = String((window.tr as (k: string, f?: string) => unknown)(key, fallback));
      return v || fallback;
    }
  } catch { /* ignore */ }
  return fallback;
}

function _clear(el: HTMLElement): void {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function _mkBadge(text: string, kind: 'builtin' | 'user' | 'unknown'): HTMLElement {
  const badge = document.createElement('span');
  badge.textContent = text;
  badge.style.cssText = [
    'display:inline-flex', 'align-items:center',
    'font-size:11px', 'padding:2px 6px',
    'border-radius:999px',
    kind === 'builtin' ? 'background:rgba(0,128,255,0.12);color:var(--fg,#222);border:1px solid rgba(0,128,255,0.3)'
      : kind === 'user' ? 'background:rgba(0,160,80,0.12);color:var(--fg,#222);border:1px solid rgba(0,160,80,0.3)'
        : 'background:rgba(120,120,120,0.10);color:var(--fg,#222);border:1px solid rgba(120,120,120,0.25)',
  ].join(';');
  return badge;
}

function _profileLabel(p: ProfileListItem): string {
  return (p.display_name || p.model_id || p.id || '').trim();
}

function _isBuiltin(p: ProfileListItem): boolean {
  if (p.origin === 'builtin') return true;
  if (p.builtin === true) return true;
  return false;
}

function _matchesFilter(p: ProfileListItem, filter: ProfileListFilter): boolean {
  if (filter === 'all') return true;
  if (filter === 'builtin') return _isBuiltin(p);
  if (filter === 'user') return !_isBuiltin(p);
  return true;
}

function _downloadJson(filename: string, obj: unknown): void {
  try {
    const text = JSON.stringify(obj, null, 2);
    const blob = new Blob([text], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 0);
  } catch {
    // ignore
  }
}

function _csrfHeadersForUnsafe(): HeadersInit {
  const headers: Record<string, string> = { 'Content-Type': 'application/json' };
  try {
    const anyWin = window as unknown as { csrfHeader?: () => unknown };
    const h = typeof anyWin.csrfHeader === 'function' ? anyWin.csrfHeader() : null;
    if (h && typeof h === 'object') return { ...headers, ...(h as Record<string, string>) };
  } catch { /* ignore */ }
  return headers;
}

async function _apiJson(path: string, init?: RequestInit): Promise<{ res: Response; json: any }> {
  const res = await fetch(path, init);
  let json: any = null;
  try {
    json = await res.json();
  } catch {
    json = null;
  }
  return { res, json };
}

async function _fetchFullProfile(profileId: string): Promise<ProfileListItem | null> {
  const { json } = await _apiJson(`/api/wd-tagger/profiles/${encodeURIComponent(profileId)}`);
  if (!json || json.ok === false) return null;
  const profile = json.profile;
  if (!profile || typeof profile !== 'object') return null;
  const out = profile as ProfileListItem;
  if (json.origin) out.origin = String(json.origin) as ProfileOrigin;
  if (typeof json.overrides_builtin === 'boolean') out.overrides_builtin = json.overrides_builtin;
  return out;
}

function _openImportModal(onImport: (profile: unknown) => void): void {
  let tab: ImportTab = 'upload';
  let overlay: HTMLDivElement | null = null;

  function close(): void {
    if (overlay) overlay.remove();
    overlay = null;
  }

  const ov = document.createElement('div');
  ov.className = 'wt-profile-import-overlay';
  ov.style.cssText = [
    'position:fixed', 'inset:0',
    'background:rgba(0,0,0,0.5)',
    'z-index:10001',
    'display:flex', 'align-items:center', 'justify-content:center',
  ].join(';');
  ov.addEventListener('click', (e) => {
    if (e.target === ov) close();
  });

  const modal = document.createElement('div');
  modal.className = 'wt-profile-import-modal';
  modal.style.cssText = [
    'background:var(--bg, #fff)', 'color:var(--fg, #222)',
    'max-width:720px', 'width:92%', 'max-height:86vh', 'overflow:auto',
    'border-radius:8px', 'padding:16px',
    'box-shadow:0 10px 40px rgba(0,0,0,0.25)',
    'border:1px solid var(--border, #ddd)',
  ].join(';');
  modal.setAttribute('role', 'dialog');

  const title = document.createElement('h4');
  title.textContent = _t('tools.wt_profile_import', 'Import');
  title.style.cssText = 'margin:0 0 10px;font-size:14px;';
  modal.appendChild(title);

  const tabs = document.createElement('div');
  tabs.style.cssText = 'display:flex;gap:8px;margin-bottom:12px;';
  modal.appendChild(tabs);

  const uploadTab = document.createElement('button');
  uploadTab.type = 'button';
  uploadTab.className = 'btn btn-secondary';
  uploadTab.textContent = _t('tools.wt_profile_import_upload', 'Upload JSON');
  uploadTab.dataset.action = 'tab-upload';
  tabs.appendChild(uploadTab);

  const pasteTab = document.createElement('button');
  pasteTab.type = 'button';
  pasteTab.className = 'btn btn-secondary';
  pasteTab.textContent = _t('tools.wt_profile_import_paste', 'Paste JSON');
  pasteTab.dataset.action = 'tab-paste';
  tabs.appendChild(pasteTab);

  const content = document.createElement('div');
  modal.appendChild(content);

  const errorBox = document.createElement('div');
  errorBox.style.cssText = 'margin-top:10px;font-size:12px;color:#b00020;';
  modal.appendChild(errorBox);

  function setError(msg: string): void {
    errorBox.textContent = msg;
  }

  function setActiveTab(): void {
    uploadTab.disabled = tab === 'upload';
    pasteTab.disabled = tab === 'paste';
    renderTab();
  }

  function preflight(obj: any): { ok: true; profile: any } | { ok: false; error: string } {
    if (!obj || typeof obj !== 'object') return { ok: false, error: _t('tools.wt_profile_import_invalid', 'Invalid JSON') };
    const id = String(obj.id || '').trim();
    const displayName = String(obj.display_name || '').trim();
    const modelId = String(obj.model_id || '').trim();
    const idRe = /^[a-z0-9][a-z0-9_-]{0,63}$/;
    if (!idRe.test(id)) return { ok: false, error: _t('tools.wt_profile_id_invalid', 'Invalid id') };
    if (displayName.length < 1 || displayName.length > 200) return { ok: false, error: _t('tools.wt_profile_display_name_invalid', 'Invalid display name') };
    if (!modelId) return { ok: false, error: _t('tools.wt_profile_model_id_required', 'model_id is required') };
    return { ok: true, profile: obj };
  }

  function renderTab(): void {
    _clear(content);
    setError('');
    if (tab === 'upload') {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;gap:10px;align-items:center;flex-wrap:wrap;';
      content.appendChild(row);

      const input = document.createElement('input');
      input.type = 'file';
      input.accept = 'application/json';
      input.id = 'wt-profile-import-file';
      input.name = 'wt-profile-import-file';
      row.appendChild(input);

      const importBtn = document.createElement('button');
      importBtn.type = 'button';
      importBtn.className = 'btn btn-primary';
      importBtn.textContent = _t('tools.wt_profile_import_apply', 'Import');
      row.appendChild(importBtn);

      importBtn.addEventListener('click', () => {
        const f = input.files?.[0] || null;
        if (!f) {
          setError(_t('tools.wt_profile_import_select_file', 'Select a JSON file'));
          return;
        }
        if (f.size > 1024 * 1024) {
          setError(_t('tools.wt_profile_too_large', 'Profile too large'));
          return;
        }
        const fr = new FileReader();
        fr.onload = () => {
          try {
            const txt = String(fr.result || '');
            const obj = JSON.parse(txt);
            const pf = preflight(obj);
            if (!pf.ok) {
              setError(pf.error);
              return;
            }
            onImport(pf.profile);
            close();
          } catch {
            setError(_t('tools.wt_profile_import_invalid', 'Invalid JSON'));
          }
        };
        fr.onerror = () => setError(_t('tools.wt_profile_import_read_failed', 'Failed to read file'));
        fr.readAsText(f);
      });
    } else {
      const ta = document.createElement('textarea');
      ta.id = 'wt-profile-import-paste';
      ta.name = 'wt-profile-import-paste';
      ta.rows = 12;
      ta.style.cssText = 'width:100%;font-family:ui-monospace, SFMono-Regular, Menlo, monospace;font-size:12px;';
      content.appendChild(ta);

      const row = document.createElement('div');
      row.style.cssText = 'display:flex;justify-content:flex-end;gap:8px;margin-top:10px;';
      content.appendChild(row);

      const importBtn = document.createElement('button');
      importBtn.type = 'button';
      importBtn.className = 'btn btn-primary';
      importBtn.textContent = _t('tools.wt_profile_import_apply', 'Import');
      row.appendChild(importBtn);
      importBtn.addEventListener('click', () => {
        const txt = (ta.value || '').trim();
        if (!txt) {
          setError(_t('tools.wt_profile_import_empty', 'Paste JSON'));
          return;
        }
        if (txt.length > 1024 * 1024) {
          setError(_t('tools.wt_profile_too_large', 'Profile too large'));
          return;
        }
        try {
          const obj = JSON.parse(txt);
          const pf = preflight(obj);
          if (!pf.ok) {
            setError(pf.error);
            return;
          }
          onImport(pf.profile);
          close();
        } catch {
          setError(_t('tools.wt_profile_import_invalid', 'Invalid JSON'));
        }
      });
    }
  }

  modal.addEventListener('click', (e) => {
    const btn = (e.target as HTMLElement | null)?.closest('button[data-action]') as HTMLButtonElement | null;
    if (!btn) return;
    if (btn.dataset.action === 'tab-upload') {
      tab = 'upload';
      setActiveTab();
    }
    if (btn.dataset.action === 'tab-paste') {
      tab = 'paste';
      setActiveTab();
    }
  });

  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;justify-content:flex-end;gap:8px;margin-top:12px;';
  modal.appendChild(actions);

  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = _t('tools.wt_profile_cancel', 'Cancel');
  cancelBtn.addEventListener('click', close);
  actions.appendChild(cancelBtn);

  ov.appendChild(modal);
  document.body.appendChild(ov);
  overlay = ov;

  setActiveTab();
}

export function renderProfileList(container: HTMLElement, cb: ProfileListCallbacks): ProfileListApi {
  const state: { filter: ProfileListFilter; profiles: ProfileListItem[]; activeModelId: string | null } = {
    filter: 'all',
    profiles: [],
    activeModelId: null,
  };

  const header = document.createElement('div');
  header.style.cssText = 'display:flex;justify-content:space-between;align-items:center;gap:12px;flex-wrap:wrap;margin-bottom:10px;';
  container.appendChild(header);

  const left = document.createElement('div');
  left.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;';
  header.appendChild(left);

  const filterAll = document.createElement('button');
  filterAll.type = 'button';
  filterAll.className = 'btn btn-secondary';
  filterAll.textContent = _t('tools.wt_profile_filter_all', 'All');
  filterAll.dataset.action = 'filter-all';
  left.appendChild(filterAll);

  const filterUser = document.createElement('button');
  filterUser.type = 'button';
  filterUser.className = 'btn btn-secondary';
  filterUser.textContent = _t('tools.wt_profile_filter_user', 'User');
  filterUser.dataset.action = 'filter-user';
  left.appendChild(filterUser);

  const filterBuiltin = document.createElement('button');
  filterBuiltin.type = 'button';
  filterBuiltin.className = 'btn btn-secondary';
  filterBuiltin.textContent = _t('tools.wt_profile_filter_builtin', 'Builtin');
  filterBuiltin.dataset.action = 'filter-builtin';
  left.appendChild(filterBuiltin);

  const right = document.createElement('div');
  right.style.cssText = 'display:flex;gap:8px;align-items:center;flex-wrap:wrap;';
  header.appendChild(right);

  const importBtn = document.createElement('button');
  importBtn.type = 'button';
  importBtn.className = 'btn btn-secondary';
  importBtn.textContent = _t('tools.wt_profile_import', 'Import');
  importBtn.dataset.action = 'import';
  right.appendChild(importBtn);

  const newBtn = document.createElement('button');
  newBtn.type = 'button';
  newBtn.className = 'btn btn-primary';
  newBtn.textContent = _t('tools.wt_profile_new', '+ New');
  newBtn.dataset.action = 'new';
  right.appendChild(newBtn);

  const hint = document.createElement('div');
  hint.style.cssText = 'font-size:12px;opacity:0.75;margin:2px 0 10px;';
  container.appendChild(hint);

  const list = document.createElement('div');
  list.className = 'wt-profile-list';
  container.appendChild(list);

  const banner = document.createElement('div');
  banner.style.cssText = 'margin-top:10px;font-size:12px;';
  container.appendChild(banner);

  function setBanner(text: string, kind: 'ok' | 'error' | 'info'): void {
    banner.textContent = '';
    if (!text) return;
    const el = document.createElement('div');
    el.textContent = text;
    el.style.cssText = [
      'padding:8px 10px', 'border-radius:6px',
      kind === 'ok' ? 'background:rgba(0,160,80,0.12);border:1px solid rgba(0,160,80,0.25)'
        : kind === 'error' ? 'background:rgba(176,0,32,0.10);border:1px solid rgba(176,0,32,0.20)'
          : 'background:rgba(0,128,255,0.10);border:1px solid rgba(0,128,255,0.20)',
    ].join(';');
    banner.appendChild(el);
    setTimeout(() => { if (banner.contains(el)) el.remove(); }, 5000);
  }

  function updateFilterButtons(): void {
    filterAll.disabled = state.filter === 'all';
    filterUser.disabled = state.filter === 'user';
    filterBuiltin.disabled = state.filter === 'builtin';
  }

  function renderRows(): void {
    _clear(list);
    updateFilterButtons();

    const items = state.profiles.filter((p) => _matchesFilter(p, state.filter));
    hint.textContent = items.length ? '' : _t('tools.wt_profile_list_empty', 'No profiles');

    for (const p of items) {
      const row = document.createElement('div');
      row.className = 'wt-profile-row';
      row.style.cssText = [
        'display:flex', 'align-items:center', 'justify-content:space-between',
        'gap:12px', 'padding:10px 8px',
        'border-top:1px solid var(--border,#ddd)',
      ].join(';');
      list.appendChild(row);

      const leftCol = document.createElement('div');
      leftCol.style.cssText = 'display:flex;align-items:center;gap:8px;min-width:0;flex:1;';
      row.appendChild(leftCol);

      const origin = _isBuiltin(p) ? 'builtin' : 'user';
      leftCol.appendChild(_mkBadge(origin === 'builtin' ? 'builtin' : 'user', origin));

      if (p.overrides_builtin) {
        const ov = document.createElement('span');
        ov.textContent = '↻';
        ov.title = _t('tools.wt_profile_overrides', 'Overrides builtin');
        ov.style.cssText = 'font-size:12px;opacity:0.85;';
        leftCol.appendChild(ov);
      }

      const name = document.createElement('div');
      name.style.cssText = 'min-width:0;';
      leftCol.appendChild(name);

      const dn = document.createElement('div');
      dn.textContent = _profileLabel(p);
      dn.style.cssText = 'font-weight:600;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      name.appendChild(dn);

      const meta = document.createElement('div');
      meta.textContent = `(${p.id})`;
      meta.style.cssText = 'font-size:12px;opacity:0.75;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;';
      name.appendChild(meta);

      const actions = document.createElement('div');
      actions.style.cssText = 'display:flex;gap:6px;align-items:center;flex-wrap:wrap;justify-content:flex-end;';
      row.appendChild(actions);

      const mkBtn = (action: string, label: string, primary?: boolean): HTMLButtonElement => {
        const b = document.createElement('button');
        b.type = 'button';
        b.className = primary ? 'btn btn-primary' : 'btn btn-secondary';
        b.textContent = label;
        b.dataset.action = action;
        b.dataset.profileId = p.id;
        return b;
      };

      actions.appendChild(mkBtn('duplicate', _t('tools.wt_profile_duplicate', 'Duplicate')));

      const editBtn = mkBtn('edit', _t('tools.wt_profile_edit', 'Edit'));
      if (_isBuiltin(p)) {
        editBtn.disabled = true;
        editBtn.title = _t('tools.wt_profile_builtin_ro', 'Built-in profile (read-only)');
      }
      actions.appendChild(editBtn);

      const delBtn = mkBtn('delete', _t('tools.wt_profile_delete', 'Delete'));
      if (_isBuiltin(p)) {
        delBtn.disabled = true;
        delBtn.title = _t('tools.wt_profile_builtin_ro', 'Built-in profile (read-only)');
      }
      actions.appendChild(delBtn);

      actions.appendChild(mkBtn('export', _t('tools.wt_profile_export', 'Export')));
      actions.appendChild(mkBtn('test', _t('tools.wt_profile_test', 'Test')));
    }
  }

  async function refresh(): Promise<void> {
    try {
      const payload = await fetchWdTaggerProfiles();
      const raw = payload.profiles as unknown as ProfileListItem[];
      state.profiles = Array.isArray(raw) ? raw : [];
      state.activeModelId = payload.active_model_id ?? null;
      renderRows();
    } catch {
      state.profiles = [];
      renderRows();
    }
  }

  async function doDelete(profileId: string): Promise<void> {
    const p = state.profiles.find((x) => x.id === profileId);
    if (!p) return;
    const name = _profileLabel(p);
    const msg = _t('tools.wt_profile_delete_confirm', `Delete ${name}? This cannot be undone.`);
    if (!(await customConfirm(msg, { danger: true }))) return;

    const { json } = await _apiJson(`/api/wd-tagger/profiles/${encodeURIComponent(profileId)}`, {
      method: 'DELETE',
      headers: _csrfHeadersForUnsafe(),
    });
    if (json && json.ok === false) {
      const code = String(json.code || '');
      if (code === 'in_use') {
        setBanner(_t('tools.wt_profile_in_use', 'Cannot delete: profile is the active model'), 'error');
        return;
      }
      if (code === 'not_found') {
        await refresh();
        return;
      }
      if (code === 'builtin_read_only') {
        setBanner(_t('tools.wt_profile_builtin_ro', 'Built-in profile (read-only)'), 'error');
        return;
      }
      setBanner(String(json.error || _t('tools.wt_profile_delete_failed', 'Delete failed')), 'error');
      return;
    }
    setBanner(_t('tools.wt_profile_delete_ok', 'Deleted'), 'ok');
    try {
      window.dispatchEvent(new CustomEvent('wd-tagger-profile-changed'));
    } catch { /* ignore */ }
    await refresh();
  }

  async function doTest(profileId: string): Promise<void> {
    const { json } = await _apiJson(`/api/wd-tagger/profiles/${encodeURIComponent(profileId)}/test`, {
      method: 'POST',
      headers: _csrfHeadersForUnsafe(),
    });
    if (json && json.ok === false) {
      const code = String(json.code || '');
      if (code === 'ssrf_blocked') setBanner(_t('tools.wt_profile_test_ssrf', 'Blocked redirect (SSRF prevention)'), 'error');
      else if (code === 'hf_unavailable') setBanner(_t('tools.wt_profile_test_hf_unavailable', 'HuggingFace unavailable'), 'error');
      else if (code === 'timeout') setBanner(_t('tools.wt_profile_test_timeout', 'Timeout'), 'error');
      else if (code === 'required_missing') setBanner(_t('tools.wt_profile_test_required_missing', 'Required file missing'), 'error');
      else setBanner(String(json.error || _t('tools.wt_profile_test_failed', 'Test failed')), 'error');
      return;
    }
    setBanner(_t('tools.wt_profile_test_ok', 'OK'), 'ok');
  }

  container.addEventListener('click', (e) => {
    const el = (e.target as HTMLElement | null)?.closest('[data-action]') as HTMLElement | null;
    if (!el) return;
    const action = el.dataset.action || '';
    if (action === 'filter-all') {
      state.filter = 'all';
      renderRows();
    } else if (action === 'filter-user') {
      state.filter = 'user';
      renderRows();
    } else if (action === 'filter-builtin') {
      state.filter = 'builtin';
      renderRows();
    } else if (action === 'import') {
      _openImportModal((profile) => {
        cb.onImport(profile);
      });
    } else if (action === 'new') {
      cb.onCreate();
    } else if (action === 'duplicate' || action === 'edit' || action === 'delete' || action === 'export' || action === 'test') {
      const id = el.dataset.profileId || '';
      const p = state.profiles.find((x) => x.id === id);
      if (!p) return;
      if (action === 'duplicate' || action === 'edit' || action === 'export') {
        void (async () => {
          const full = await _fetchFullProfile(id);
          if (!full) {
            setBanner(_t('tools.wt_profile_fetch_failed', 'Failed to fetch profile'), 'error');
            return;
          }
          if (action === 'duplicate') cb.onDuplicate(full);
          if (action === 'edit') cb.onEdit(full);
          if (action === 'export') _downloadJson(`${full.id || 'profile'}.json`, full);
        })();
      }
      if (action === 'delete') void doDelete(id);
      if (action === 'test') void doTest(id);
    }
  });

  return { refresh };
}
