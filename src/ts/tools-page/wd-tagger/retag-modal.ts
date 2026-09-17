import { getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import {
  changeActiveModel,
  collectOldModelIds,
  deleteOldModelTags,
  fetchActiveModelState,
  formatActiveModel,
  loadActiveModelState,
  renderActiveModelState,
} from './retag-modal-active';
import { renderResult } from './retag-modal-result';
import type { RetagActiveState, RetagSinglePayload, RetagSingleResponse } from './retag-modal-types';
import { addLabeledInput, showError, t } from './retag-modal-ui';
import { customConfirm } from '../../shared/dialog';

export function openRetagModal(fileId: number, defaultModelId: string = ''): void {
  const activeState: RetagActiveState = { activeModelId: null, availableModels: [] };
  const overlay = document.createElement('div');
  overlay.className = 'wt-retag-modal-overlay';
  overlay.style.cssText = [
    'position:fixed', 'inset:0',
    'background:rgba(0,0,0,0.5)',
    'z-index:10000',
    'display:flex', 'align-items:center', 'justify-content:center',
  ].join(';');
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });

  const modal = document.createElement('div');
  modal.className = 'wt-retag-modal';
  modal.style.cssText = [
    'background:var(--bg, #fff)', 'color:var(--fg, #222)',
    'max-width:560px', 'width:92%', 'max-height:90vh', 'overflow:auto',
    'border-radius:8px', 'padding:20px',
    'box-shadow:0 10px 40px rgba(0,0,0,0.25)',
    'border:1px solid var(--border, #ddd)',
  ].join(';');
  modal.setAttribute('role', 'dialog');

  const title = document.createElement('h3');
  title.textContent = t('tools.wt_retag_title', 'Retag image');
  title.style.cssText = 'margin:0 0 14px;font-size:16px;';
  title.id = `wt-retag-title-${fileId}`;
  modal.setAttribute('aria-labelledby', title.id);
  modal.appendChild(title);

  const meta = document.createElement('div');
  meta.style.cssText = 'font-size:12px;opacity:0.7;margin-bottom:12px;';
  meta.textContent = `file_id: ${fileId}`;
  modal.appendChild(meta);

  const { activeValue, activeMenu } = appendActiveModelPanel(modal, activeState, fileId);
  const modelInput = addLabeledInput(modal, `wt-retag-model-${fileId}`, t('tools.wt_retag_model', 'Model'), {
    type: 'text',
    name: 'wt-retag-model',
    value: defaultModelId,
    placeholder: 'SmilingWolf/wd-swinv2-tagger-v3',
  });
  if (modelInput.parentElement) modelInput.parentElement.style.marginBottom = '12px';

  const thresholdRow = document.createElement('div');
  thresholdRow.style.cssText = 'display:grid;grid-template-columns:1fr 1fr;gap:12px;margin-bottom:12px;';
  modal.appendChild(thresholdRow);
  const genInput = addLabeledInput(
    thresholdRow,
    `wt-retag-gen-${fileId}`,
    t('tools.wt_general_threshold', 'General threshold'),
    { type: 'number', name: 'wt-retag-gen', min: '0', max: '1', step: '0.05', value: '0.35' },
  );
  const charInput = addLabeledInput(
    thresholdRow,
    `wt-retag-char-${fileId}`,
    t('tools.wt_char_threshold', 'Character threshold'),
    { type: 'number', name: 'wt-retag-char', min: '0', max: '1', step: '0.05', value: '0.85' },
  );

  const overwriteInput = appendCheckbox(modal, fileId, 'overwrite', t('tools.wt_retag_overwrite', 'Overwrite same model tags'), true);
  const setActiveInput = appendCheckbox(
    modal,
    fileId,
    'set-active',
    t('tools.wt_retag_set_active_label', 'Set as active model after retag'),
    true,
    t('tools.wt_retag_set_active_tooltip', 'If checked, this model becomes the active one used by tag display and search after retag completes.'),
  );
  const deleteOldInput = appendCheckbox(
    modal,
    fileId,
    'delete-old',
    t('tools.wt_retag_delete_old_label', 'Also delete tags from other models'),
    false,
    t('tools.wt_retag_delete_old_tooltip', 'Permanently remove tags from previously used models for this file.'),
  );

  const resultEl = document.createElement('div');
  resultEl.id = `wt-retag-result-${fileId}`;
  resultEl.style.cssText = 'font-size:13px;margin-bottom:12px;';
  modal.appendChild(resultEl);
  appendActions(modal, overlay, () => {
    void runRetag(
      fileId,
      { modelInput, genInput, charInput, overwriteInput, setActiveInput, deleteOldInput },
      { activeState, activeValue, activeMenu, resultEl },
    );
  });

  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  modelInput.focus();
  void loadActiveModelState(activeState, activeValue, activeMenu, modelInput, resultEl);
}

function appendActiveModelPanel(
  modal: HTMLElement,
  activeState: RetagActiveState,
  fileId: number,
): { activeValue: HTMLElement; activeMenu: HTMLElement } {
  const activePanel = document.createElement('div');
  activePanel.style.cssText = [
    'position:relative', 'display:flex', 'align-items:center', 'gap:8px', 'flex-wrap:wrap',
    'font-size:13px', 'padding:8px 10px',
    'border:1px solid var(--border,#ddd)', 'border-radius:6px',
    'background:var(--panel-bg,rgba(0,0,0,0.03))', 'margin-bottom:12px',
  ].join(';');
  const activeLabel = document.createElement('span');
  activeLabel.style.fontWeight = '600';
  activeLabel.textContent = t('tools.wt_retag_active_model_label', 'Active model') + ':';
  activePanel.appendChild(activeLabel);

  const activeValue = document.createElement('span');
  activeValue.dataset.role = 'active-model-value';
  activeValue.textContent = formatActiveModel(activeState.activeModelId);
  activePanel.appendChild(activeValue);

  const changeBtn = document.createElement('button');
  changeBtn.type = 'button';
  changeBtn.className = 'btn btn-secondary btn-sm';
  changeBtn.dataset.action = 'toggle-active-model-menu';
  changeBtn.textContent = t('tools.wt_retag_active_change_btn', 'Change ▾');
  activePanel.appendChild(changeBtn);

  const activeMenu = document.createElement('div');
  activeMenu.hidden = true;
  activeMenu.style.cssText = [
    'position:absolute', 'left:10px', 'top:100%', 'z-index:1',
    'min-width:260px', 'max-width:100%', 'max-height:220px', 'overflow:auto',
    'background:var(--bg,#fff)', 'color:var(--fg,#222)',
    'border:1px solid var(--border,#ddd)', 'border-radius:6px',
    'box-shadow:0 8px 20px rgba(0,0,0,0.18)', 'padding:4px',
  ].join(';');
  activePanel.appendChild(activeMenu);
  activePanel.addEventListener('click', (event) => {
    const actionEl = (event.target as HTMLElement | null)?.closest('[data-action]') as HTMLElement | null;
    if (!actionEl) return;
    if (actionEl.dataset.action === 'toggle-active-model-menu') activeMenu.hidden = !activeMenu.hidden;
    if (actionEl.dataset.action === 'select-active-model') {
      activeMenu.hidden = true;
      void changeActiveModel(actionEl.dataset.modelId || null, activeState, activeValue, activeMenu, document.getElementById(`wt-retag-result-${fileId}`) as HTMLElement);
    }
  });
  modal.appendChild(activePanel);
  return { activeValue, activeMenu };
}

function appendCheckbox(parent: HTMLElement, fileId: number, name: string, labelText: string, checked: boolean, title?: string): HTMLInputElement {
  const label = document.createElement('label');
  if (title) label.title = title;
  label.style.cssText = 'display:flex;align-items:center;gap:8px;font-size:13px;margin-bottom:14px;';
  const input = document.createElement('input');
  input.type = 'checkbox';
  input.name = `wt-retag-${name}`;
  input.id = `wt-retag-${name}-${fileId}`;
  input.checked = checked;
  label.appendChild(input);
  label.appendChild(document.createTextNode(' ' + labelText));
  parent.appendChild(label);
  return input;
}

function appendActions(modal: HTMLElement, overlay: HTMLElement, onSubmit: () => void): void {
  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;gap:8px;justify-content:flex-end;';
  const cancelBtn = document.createElement('button');
  cancelBtn.type = 'button';
  cancelBtn.className = 'btn btn-secondary';
  cancelBtn.textContent = t('tools.wt_close', 'Close');
  cancelBtn.addEventListener('click', () => overlay.remove());
  actions.appendChild(cancelBtn);
  const submitBtn = document.createElement('button');
  submitBtn.type = 'button';
  submitBtn.className = 'btn btn-primary';
  submitBtn.textContent = t('tools.wt_retag_submit', 'Run retag');
  submitBtn.addEventListener('click', onSubmit);
  actions.appendChild(submitBtn);
  modal.appendChild(actions);
}

async function runRetag(
  fileId: number,
  inputs: {
    modelInput: HTMLInputElement;
    genInput: HTMLInputElement;
    charInput: HTMLInputElement;
    overwriteInput: HTMLInputElement;
    setActiveInput: HTMLInputElement;
    deleteOldInput: HTMLInputElement;
  },
  ctx: {
    activeState: RetagActiveState;
    activeValue: HTMLElement;
    activeMenu: HTMLElement;
    resultEl: HTMLElement;
  },
): Promise<void> {
  const modelId = (inputs.modelInput.value || '').trim();
  if (!modelId) {
    showError(ctx.resultEl, t('tools.wt_retag_model_required', 'Model is required'));
    return;
  }
  const submitBtn = ctx.resultEl.parentElement?.querySelector<HTMLButtonElement>('.btn.btn-primary');
  const origLabel = submitBtn?.textContent;
  if (submitBtn) {
    submitBtn.disabled = true;
    submitBtn.textContent = t('tools.wt_retag_running', 'Running...');
  }
  ctx.resultEl.textContent = '';

  try {
    if (inputs.deleteOldInput.checked && ctx.activeState.availableModels.length === 0) {
      const payload = await fetchActiveModelState();
      ctx.activeState.activeModelId = payload.active_model_id ?? null;
      ctx.activeState.availableModels = payload.available_models || [];
      renderActiveModelState(ctx.activeState, ctx.activeValue, ctx.activeMenu);
    }
    const oldModelIds = inputs.deleteOldInput.checked
      ? await collectOldModelIds(fileId, modelId, ctx.activeState.availableModels)
      : [];
    const payload = await postRetag(fileId, modelId, inputs);
    renderResult(ctx.resultEl, payload);
    if (inputs.setActiveInput.checked) {
      ctx.activeState.activeModelId = payload.model_id;
      renderActiveModelState(ctx.activeState, ctx.activeValue, ctx.activeMenu);
    }
    if (inputs.deleteOldInput.checked && oldModelIds.length > 0 && await customConfirm(t(
      'tools.wt_retag_delete_old_confirm',
      'Permanently delete tags from other models for this file? This cannot be undone.',
    ), { danger: true })) {
      await deleteOldModelTags(fileId, oldModelIds);
    }
    getNavApi().showToast(t('tools.wt_retag_success', 'Retag complete'), false);
  } catch (err) {
    const msg = err instanceof Error ? err.message : t('tools.wt_retag_failed', 'Retag failed');
    showError(ctx.resultEl, msg);
    getNavApi().showToast(msg, true);
  } finally {
    if (submitBtn) {
      submitBtn.disabled = false;
      if (origLabel != null) submitBtn.textContent = origLabel;
    }
  }
}

async function postRetag(
  fileId: number,
  modelId: string,
  inputs: { genInput: HTMLInputElement; charInput: HTMLInputElement; overwriteInput: HTMLInputElement; setActiveInput: HTMLInputElement },
): Promise<RetagSinglePayload> {
  const res = await apiFetch('/api/wd-tagger/retag/single', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      file_id: fileId,
      model_id: modelId,
      thresholds: {
        general: parseFloat(inputs.genInput.value || '0.35'),
        character: parseFloat(inputs.charInput.value || '0.85'),
      },
      overwrite_same_model: !!inputs.overwriteInput.checked,
      set_active: !!inputs.setActiveInput.checked,
    }),
  });
  const data: RetagSingleResponse = await res.json();
  if (data.ok === false || !res.ok) {
    throw new Error(data.error || t('tools.wt_retag_failed', 'Retag failed'));
  }
  return data.data ?? {
    file_id: data.file_id ?? fileId,
    model_id: data.model_id ?? modelId,
    tags: data.tags || [],
    rating: data.rating ?? '',
    elapsed_ms: data.elapsed_ms ?? 0,
    inserted: data.inserted ?? 0,
  };
}
