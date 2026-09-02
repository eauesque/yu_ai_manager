import { exportProfileQR, showImportProfileDialog as showImportProfileDialogLeaf } from './profiles-theme';
import { getAppApi } from '../shared/browser-apis';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

function t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export { exportProfileQR };

export async function refreshProfiles<T>(render: (profiles: T[], activeProfile: string, hasPin: boolean) => void): Promise<void> {
  try {
    const res = await fetch('/api/server-info');
    if (!res.ok) return;
    const d = await res.json();
    render((d.profiles || []) as T[], d.active_profile || '', !!d.has_pin);
  } catch {
    // ignore
  }
}

async function handleJsonAction(url: string, options: RequestInit, errorMessage: string, onSuccess: () => Promise<void>): Promise<void> {
  try {
    const res = await fetch(url, options);
    const data = await res.json();
    if (!res.ok) {
      alert(data.error || 'Failed');
      return;
    }
    await onSuccess();
  } catch (e) {
    alert(errorMessage + ': ' + (e instanceof Error ? e.message : String(e)));
  }
}

export async function showCreateProfileDialog(onSuccess: () => Promise<void>): Promise<void> {
  const name = prompt(t('settings.profile_name_prompt', 'Profile name (alphanumeric, hyphens, underscores):'));
  if (!name) return;
  const label = prompt(t('settings.profile_label_prompt', 'Display label:'), name);
  if (!label) return;
  const description = prompt(t('settings.profile_desc_prompt', 'Description (optional):'), '') || '';
  await handleJsonAction('/api/profiles', {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ name: name.trim(), label: label.trim(), description }),
  }, t('settings.profile_create_failed', 'Create failed'), onSuccess);
}

export async function duplicateProfile(name: string, onSuccess: () => Promise<void>): Promise<void> {
  const newName = prompt(t('settings.profile_dup_name_prompt', 'New profile name:'));
  if (!newName) return;
  const newLabel = prompt(t('settings.profile_dup_label_prompt', 'New display label:'), newName);
  if (!newLabel) return;
  await handleJsonAction(`/api/profiles/${encodeURIComponent(name)}/duplicate`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ new_name: newName.trim(), new_label: newLabel.trim() }),
  }, t('settings.profile_dup_failed', 'Duplicate failed'), onSuccess);
}

export async function renameProfile(name: string, onSuccess: () => Promise<void>): Promise<void> {
  const newName = prompt(t('settings.profile_rename_prompt', 'New name:'), name);
  if (!newName || newName.trim() === name) return;
  await handleJsonAction(`/api/profiles/${encodeURIComponent(name)}/rename`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      'X-Requested-With': 'XMLHttpRequest',
    },
    body: JSON.stringify({ new_name: newName.trim() }),
  }, t('settings.profile_rename_failed', 'Rename failed'), onSuccess);
}

export async function deleteProfile(name: string, label: string, onSuccess: () => Promise<void>): Promise<void> {
  const msg = t('settings.profile_delete_confirm', 'Delete profile "{label}"? This cannot be undone.').replace('{label}', label);
  if (!confirm(msg)) return;
  await handleJsonAction(`/api/profiles/${encodeURIComponent(name)}`, {
    method: 'DELETE',
    headers: XHR_HEADERS,
  }, t('settings.profile_delete_failed', 'Delete failed'), onSuccess);
}

export async function toggleProfileFavorite(name: string, onSuccess: () => Promise<void>): Promise<void> {
  try {
    const res = await fetch(`/api/profiles/${encodeURIComponent(name)}/favorite`, {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    if (!res.ok) return;
    await onSuccess();
  } catch {
    // ignore
  }
}

export async function showImportProfileDialog(onSuccess: () => Promise<void>): Promise<void> {
  return showImportProfileDialogLeaf(onSuccess);
}
