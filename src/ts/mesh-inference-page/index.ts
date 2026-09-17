/**
 * Entry. Loads state, renders, wires events, repaints on i18n-ready.
 */
import {
  fetchState,
  refresh,
  toggle,
  bulk,
  tr,
  showToast,
  InferenceType,
  StateResponse,
} from './api';
import { renderMatrix } from './render';

let _last: StateResponse | null = null;

async function loadAll(): Promise<void> {
  try {
    const data = await fetchState();
    if (!data || data.ok === false) {
      showToast(tr('mesh_inference.toast.load_failed', 'Load failed'));
      return;
    }
    _last = data;
    renderMatrix(data);
  } catch (e) {
    console.error('[mesh_inference] load failed:', e);
    showToast(tr('mesh_inference.toast.load_failed', 'Load failed'));
  }
}

function repaintFromCache(): void {
  if (_last) renderMatrix(_last);
}

async function handleRefreshClick(): Promise<void> {
  const btn = document.getElementById('miRefreshBtn') as HTMLButtonElement | null;
  if (btn) btn.disabled = true;
  try {
    const data = await refresh();
    _last = data;
    renderMatrix(data);
    showToast(tr('mesh_inference.toast.refreshed', 'Refreshed'));
  } catch {
    showToast(tr('mesh_inference.toast.load_failed', 'Load failed'));
  } finally {
    if (btn) btn.disabled = false;
  }
}

async function handleLocalOnlyClick(): Promise<void> {
  const btn = document.getElementById('miLocalOnlyBtn') as HTMLButtonElement | null;
  if (btn) btn.disabled = true;
  try {
    const resp = await bulk('local_only');
    if (resp?.ok === false) {
      showToast(resp.error ?? tr('mesh_inference.toast.save_failed', 'Save failed'));
    } else {
      showToast(tr('mesh_inference.toast.saved', 'Saved'));
    }
    await loadAll();
  } catch {
    showToast(tr('mesh_inference.toast.save_failed', 'Save failed'));
  } finally {
    // loadAll() will re-evaluate disabled via renderMatrix, so we don't
    // forcibly re-enable here — the button stays disabled if appropriate.
  }
}

async function handleMatrixClick(e: Event): Promise<void> {
  const input = (e.target as HTMLElement).closest<HTMLInputElement>('input.mi-toggle');
  if (!input) return;
  const peer_id = input.dataset.peerId;
  const inference_type = input.dataset.inferenceType as InferenceType | undefined;
  if (!peer_id || !inference_type) return;

  // Checkbox UX: "checked = enabled", so sending disabled = !checked AFTER the
  // browser has toggled it is correct.
  const disabled = !input.checked;
  input.disabled = true;
  try {
    const resp = await toggle(peer_id, inference_type, disabled);
    if (resp?.ok === false) {
      showToast(resp.error ?? tr('mesh_inference.toast.save_failed', 'Save failed'));
      // Roll back checkbox state
      input.checked = !input.checked;
    } else {
      showToast(tr('mesh_inference.toast.saved', 'Saved'));
    }
    await loadAll();
  } catch {
    input.checked = !input.checked;
    showToast(tr('mesh_inference.toast.save_failed', 'Save failed'));
  } finally {
    input.disabled = false;
  }
}

function init(): void {
  loadAll();
  document.getElementById('miRefreshBtn')?.addEventListener('click', handleRefreshClick);
  document.getElementById('miLocalOnlyBtn')?.addEventListener('click', handleLocalOnlyClick);
  document.getElementById('miMatrix')?.addEventListener('change', handleMatrixClick);
  document.addEventListener('i18n:changed', repaintFromCache);
  document.addEventListener('tr-runtime:ready', repaintFromCache);
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', init);
} else {
  init();
}
