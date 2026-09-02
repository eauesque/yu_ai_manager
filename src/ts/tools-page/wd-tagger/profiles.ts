/**
 * wd-tagger/profiles.ts -- Builtin profile list helpers.
 */

export interface WdTaggerProfile {
  id: string;
  display_name: string;
  model_id: string;
  adapter_family?: string;
  backend?: string;
  builtin?: boolean;
  has_tags?: boolean;
}

export interface WdTaggerProfilesPayload {
  profiles: WdTaggerProfile[];
  active_model_id: string | null;
}

interface WdTaggerProfilesResponse {
  ok?: boolean;
  data?: Partial<WdTaggerProfilesPayload>;
  profiles?: WdTaggerProfile[];
  active_model_id?: string | null;
}

let _manageBtnAttached = false;
let _profileChangedListenerAttached = false;

function _t(key: string, fallback: string): string {
  try {
    if (typeof window.tr === 'function') {
      const v = String((window.tr as (k: string, f?: string) => unknown)(key, fallback));
      return v || fallback;
    }
  } catch { /* ignore */ }
  return fallback;
}

function _attachManageProfilesButton(): void {
  if (_manageBtnAttached) return;
  const sel = document.getElementById('wtModel') as HTMLSelectElement | null;
  if (!sel) return;
  const parent = sel.parentElement;
  if (!parent) return;

  // Avoid duplicates if hot-reloaded or called multiple times.
  if (parent.querySelector('#wtManageProfilesBtn')) {
    _manageBtnAttached = true;
    return;
  }

  const btn = document.createElement('button');
  btn.type = 'button';
  btn.id = 'wtManageProfilesBtn';
  btn.className = 'btn btn-secondary';
  btn.textContent = _t('tools.wt_profile_manage', 'Manage profiles...');
  btn.addEventListener('click', () => {
    void import('./profile-manager-modal').then((m) => m.openProfileManagerModal());
  });

  // Insert right after the select (best-effort; HTML layout is fixed).
  if (sel.nextSibling) parent.insertBefore(btn, sel.nextSibling);
  else parent.appendChild(btn);

  _manageBtnAttached = true;
}

function _attachProfileChangedListener(): void {
  if (_profileChangedListenerAttached) return;
  window.addEventListener('wd-tagger-profile-changed', async () => {
    // Rebuild the dropdown options without changing selection behavior.
    const sel = document.getElementById('wtModel') as HTMLSelectElement | null;
    if (!sel) return;
    const selected = sel.value || '';
    try {
      const payload = await fetchWdTaggerProfiles();
      sel.textContent = '';
      for (const profile of payload.profiles) {
        if (!profile.model_id) continue;
        const opt = document.createElement('option');
        opt.value = profile.model_id;
        opt.textContent = profile.display_name || profile.model_id || profile.id;
        sel.appendChild(opt);
      }
      // Preserve selection if possible.
      if (selected) {
        let found = false;
        for (const opt of Array.from(sel.options)) {
          if (opt.value === selected) { found = true; break; }
        }
        if (!found) {
          const opt = document.createElement('option');
          opt.value = selected;
          opt.textContent = selected;
          sel.appendChild(opt);
        }
        sel.value = selected;
      }
    } catch {
      // ignore
    }
  });
  _profileChangedListenerAttached = true;
}

export async function fetchWdTaggerProfiles(): Promise<WdTaggerProfilesPayload> {
  // Best-effort UI hook: called by config.ts during page init.
  _attachManageProfilesButton();
  _attachProfileChangedListener();

  const res = await fetch('/api/wd-tagger/profiles');
  const data: WdTaggerProfilesResponse = await res.json();
  const payload = data.data || data;
  return {
    profiles: Array.isArray(payload.profiles) ? payload.profiles : [],
    active_model_id: payload.active_model_id ?? null,
  };
}
