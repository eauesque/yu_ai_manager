import { getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import type {
  ActiveModelEntry,
  ActiveModelPayload,
  ActiveModelResponse,
  RetagActiveState,
  WdTagsResponse,
} from './retag-modal-types';
import { showError, t } from './retag-modal-ui';

export function formatActiveModel(modelId: string | null): string {
  return modelId || t('tools.wt_retag_active_model_none', '(none)');
}

export function renderActiveModelState(
  state: RetagActiveState,
  valueEl: HTMLElement,
  menuEl: HTMLElement,
): void {
  valueEl.textContent = formatActiveModel(state.activeModelId);
  menuEl.textContent = '';
  menuEl.appendChild(createActiveModelMenuButton('', t('tools.wt_retag_active_reset_option', '(none / reset)')));
  for (const model of state.availableModels) {
    menuEl.appendChild(createActiveModelMenuButton(model.model_id, `${model.model_id} (${model.file_count})`));
  }
}

export async function loadActiveModelState(
  state: RetagActiveState,
  valueEl: HTMLElement,
  menuEl: HTMLElement,
  modelInput: HTMLInputElement,
  resultEl: HTMLElement,
): Promise<void> {
  try {
    const payload = await fetchActiveModelState();
    state.activeModelId = payload.active_model_id ?? null;
    state.availableModels = payload.available_models || [];
    renderActiveModelState(state, valueEl, menuEl);
    if (!modelInput.value && state.activeModelId) modelInput.value = state.activeModelId;
  } catch (err) {
    showError(resultEl, activeChangeFailedMessage(err));
  }
}

export async function fetchActiveModelState(): Promise<ActiveModelPayload> {
  const res = await apiFetch('/api/wd-tagger/active-model');
  const data: ActiveModelResponse = await res.json();
  return {
    active_model_id: data.data?.active_model_id ?? data.active_model_id ?? null,
    available_models: data.data?.available_models ?? data.available_models ?? [],
  };
}

export async function changeActiveModel(
  modelId: string | null,
  state: RetagActiveState,
  valueEl: HTMLElement,
  menuEl: HTMLElement,
  resultEl: HTMLElement,
): Promise<void> {
  try {
    const res = await apiFetch('/api/wd-tagger/active-model', {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ model_id: modelId }),
    });
    const data: ActiveModelResponse = await res.json();
    state.activeModelId = data.data?.active_model_id ?? data.active_model_id ?? modelId;
    renderActiveModelState(state, valueEl, menuEl);
  } catch (err) {
    const msg = activeChangeFailedMessage(err);
    showError(resultEl, msg);
    getNavApi().showToast(msg, true);
  }
}

export async function collectOldModelIds(
  fileId: number,
  nextModelId: string,
  availableModels: ActiveModelEntry[],
): Promise<string[]> {
  const oldModelIds: string[] = [];
  for (const model of availableModels) {
    const modelId = model.model_id;
    if (!modelId || modelId === nextModelId) continue;
    const res = await apiFetch(`/api/wd-tagger/tags/${fileId}?model=${encodeURIComponent(modelId)}`, { silent: true });
    const data: WdTagsResponse = await res.json();
    const tags = data.data?.tags ?? data.tags ?? [];
    if (tags.length > 0) oldModelIds.push(modelId);
  }
  return oldModelIds;
}

export async function deleteOldModelTags(fileId: number, modelIds: string[]): Promise<void> {
  for (const modelId of modelIds) {
    await apiFetch(`/api/wd-tagger/tags/${fileId}?model=${encodeURIComponent(modelId)}`, { method: 'DELETE' });
  }
}

function createActiveModelMenuButton(modelId: string, label: string): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.dataset.action = 'select-active-model';
  btn.dataset.modelId = modelId;
  btn.textContent = label;
  btn.style.cssText = [
    'display:block', 'width:100%', 'text-align:left',
    'padding:6px 8px',
    'border:0', 'border-radius:4px',
    'background:transparent', 'color:inherit',
    'font-size:13px',
    'cursor:pointer',
  ].join(';');
  return btn;
}

function activeChangeFailedMessage(err: unknown): string {
  return t('tools.wt_retag_active_change_failed', 'Failed to change active model: {error}')
    .replace('{error}', err instanceof Error ? err.message : String(err || 'unknown error'));
}
