/** Bridge Quality Presets — UI components (toast, style injection, menu, modal) */
import {
  QualityPreset, AttachConfig,
  BUILTIN_PRESETS, loadCustomPresets, saveCustomPresets,
} from './quality-presets-data';

/* ------------------------------------------------------------------ */
/*  Toast                                                              */
/* ------------------------------------------------------------------ */

export function showToast(msg: string): void {
  const prev = document.querySelector('.bqp-toast');
  if (prev) prev.remove();
  const el = document.createElement('div');
  el.className = 'bqp-toast';
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => { if (el.parentNode) el.remove(); }, 3000);
}

/* ------------------------------------------------------------------ */
/*  Style injection (once)                                             */
/* ------------------------------------------------------------------ */

let _styleInjected = false;
export function injectStyle(): void {
  if (_styleInjected) return;
  _styleInjected = true;
  const s = document.createElement('style');
  s.textContent = `
.bqp-menu{position:absolute;z-index:9999;min-width:240px;max-width:340px;
  background:var(--bg-secondary,#fff);border:1px solid var(--border-color,#ccc);
  border-radius:6px;box-shadow:0 4px 16px rgba(0,0,0,.18);padding:4px 0;
  font-size:13px;max-height:400px;overflow-y:auto}
.bqp-item{display:block;width:100%;padding:6px 12px;border:none;background:none;
  text-align:left;cursor:pointer;color:var(--text-primary,#222);line-height:1.3}
.bqp-item:hover{background:var(--hover-bg,#f0f0f0)}
.bqp-item-desc{display:block;font-size:11px;color:var(--text-secondary,#888);
  white-space:nowrap;overflow:hidden;text-overflow:ellipsis;margin-top:1px}
.bqp-separator{height:1px;margin:4px 8px;background:var(--border-color,#ddd)}
.bqp-section-label{padding:4px 12px;font-size:11px;font-weight:600;
  color:var(--text-secondary,#888);pointer-events:none}
.bqp-item-delete{float:right;color:var(--text-secondary,#888);font-size:11px;
  cursor:pointer;padding:0 4px}
.bqp-item-delete:hover{color:var(--danger-color,#e44)}
.bqp-toast{position:fixed;bottom:20px;left:50%;transform:translateX(-50%);
  background:var(--bg-secondary,#333);color:var(--text-primary,#fff);
  padding:8px 20px;border-radius:6px;z-index:10000;font-size:13px;
  box-shadow:0 2px 8px rgba(0,0,0,.2);pointer-events:none;
  animation:bqp-fade .3s ease}
@keyframes bqp-fade{from{opacity:0;transform:translateX(-50%) translateY(8px)}
  to{opacity:1;transform:translateX(-50%) translateY(0)}}
.bqp-modal-overlay{position:fixed;inset:0;background:rgba(0,0,0,.4);
  z-index:10000;display:flex;align-items:center;justify-content:center}
.bqp-modal{background:var(--bg-primary,#fff);border-radius:8px;padding:20px;
  width:420px;max-width:90vw;box-shadow:0 8px 32px rgba(0,0,0,.25)}
.bqp-modal h3{margin:0 0 12px;font-size:15px;color:var(--text-primary,#222)}
.bqp-modal label{display:block;font-size:12px;font-weight:600;margin:8px 0 4px;
  color:var(--text-secondary,#666)}
.bqp-modal input,.bqp-modal textarea{width:100%;box-sizing:border-box;
  padding:6px 8px;border:1px solid var(--border-color,#ccc);border-radius:4px;
  font-size:13px;background:var(--bg-secondary,#fafafa);
  color:var(--text-primary,#222);font-family:inherit}
.bqp-modal textarea{height:60px;resize:vertical}
.bqp-modal-actions{display:flex;gap:8px;justify-content:flex-end;margin-top:14px}
.bqp-modal-actions button{padding:6px 16px;border:none;border-radius:4px;
  cursor:pointer;font-size:13px}
.bqp-modal-actions .bqp-save{background:var(--accent-color,#4a9eff);color:#fff}
.bqp-modal-actions .bqp-save:hover{opacity:.85}
.bqp-modal-actions .bqp-cancel{background:var(--bg-secondary,#eee);
  color:var(--text-primary,#333)}
`;
  document.head.appendChild(s);
}

/* ------------------------------------------------------------------ */
/*  Apply preset                                                       */
/* ------------------------------------------------------------------ */

export function applyPreset(preset: QualityPreset, config: AttachConfig): void {
  const curP = config.getPrompt().trim();
  const curN = config.getNegative().trim();
  config.setPrompt(curP ? preset.positive + ', ' + curP : preset.positive);
  config.setNegative(curN ? preset.negative + ', ' + curN : preset.negative);
  showToast(window.tr('preset.applied', '{name} applied').replace('{name}', preset.name));
}

/* ------------------------------------------------------------------ */
/*  Add custom preset modal                                            */
/* ------------------------------------------------------------------ */

export function openAddModal(onAdded: () => void): void {
  const overlay = document.createElement('div');
  overlay.className = 'bqp-modal-overlay';
  const modal = document.createElement('div');
  modal.className = 'bqp-modal';
  const h3 = document.createElement('h3');
  h3.textContent = window.tr('preset.add_custom_title', 'Add Custom Preset');
  modal.appendChild(h3);

  const fields: Array<{ key: string; label: string; tag: 'input' | 'textarea' }> = [
    { key: 'name', label: window.tr('preset.field_name', 'Name'), tag: 'input' },
    { key: 'positive', label: 'Positive', tag: 'textarea' },
    { key: 'negative', label: 'Negative', tag: 'textarea' },
  ];

  const inputs: Record<string, HTMLInputElement | HTMLTextAreaElement> = {};
  for (const f of fields) {
    const lbl = document.createElement('label');
    lbl.textContent = f.label;
    modal.appendChild(lbl);
    const el = document.createElement(f.tag);
    if (f.key === 'name') (el as HTMLInputElement).placeholder = 'My Preset';
    inputs[f.key] = el;
    modal.appendChild(el);
  }

  const actions = document.createElement('div');
  actions.className = 'bqp-modal-actions';
  const cancelBtn = document.createElement('button');
  cancelBtn.className = 'bqp-cancel';
  cancelBtn.textContent = window.tr('common.cancel', 'Cancel');
  cancelBtn.addEventListener('click', () => overlay.remove());
  const saveBtn = document.createElement('button');
  saveBtn.className = 'bqp-save';
  saveBtn.textContent = window.tr('common.save', 'Save');
  saveBtn.addEventListener('click', () => {
    const name = inputs.name.value.trim();
    if (!name) { inputs.name.focus(); return; }
    const custom = loadCustomPresets();
    custom.push({
      name,
      positive: inputs.positive.value.trim(),
      negative: inputs.negative.value.trim(),
      compat: ['sd', 'nai', 'comfy'],
    });
    saveCustomPresets(custom);
    overlay.remove();
    showToast(window.tr('preset.saved', '{name} saved').replace('{name}', name));
    onAdded();
  });
  actions.appendChild(cancelBtn);
  actions.appendChild(saveBtn);
  modal.appendChild(actions);

  overlay.appendChild(modal);
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) overlay.remove();
  });
  document.body.appendChild(overlay);

  // Close on Esc
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', onKey); }
  };
  document.addEventListener('keydown', onKey);
}

/* ------------------------------------------------------------------ */
/*  Dropdown menu                                                      */
/* ------------------------------------------------------------------ */

let _activeMenu: HTMLElement | null = null;

export function closeMenu(): void {
  if (_activeMenu) { _activeMenu.remove(); _activeMenu = null; }
}

export function toggleMenu(btn: HTMLElement, config: AttachConfig): void {
  if (_activeMenu) { closeMenu(); return; }

  const menu = document.createElement('div');
  menu.className = 'bqp-menu';
  _activeMenu = menu;

  const buildItems = () => {
    menu.innerHTML = '';

    // Built-in presets filtered by bridge type
    const builtins = BUILTIN_PRESETS.filter(p => p.compat.includes(config.bridgeType));
    if (builtins.length) {
      const lbl = document.createElement('div');
      lbl.className = 'bqp-section-label';
      lbl.textContent = window.tr('preset.section_builtin', 'Built-in');
      menu.appendChild(lbl);
      for (const p of builtins) {
        menu.appendChild(createItem(p, config, false));
      }
    }

    // Custom presets
    const customs = loadCustomPresets();
    if (customs.length) {
      const sep = document.createElement('div');
      sep.className = 'bqp-separator';
      menu.appendChild(sep);
      const lbl2 = document.createElement('div');
      lbl2.className = 'bqp-section-label';
      lbl2.textContent = window.tr('preset.section_custom', 'Custom');
      menu.appendChild(lbl2);
      customs.forEach((p, idx) => {
        menu.appendChild(createItem(p, config, true, idx, buildItems));
      });
    }

    // Add custom button
    const sep2 = document.createElement('div');
    sep2.className = 'bqp-separator';
    menu.appendChild(sep2);
    const addBtn = document.createElement('button');
    addBtn.className = 'bqp-item';
    addBtn.textContent = window.tr('preset.add_custom', '+ Add Custom...');
    addBtn.addEventListener('click', () => {
      closeMenu();
      openAddModal(() => { /* reflected next time menu is opened */ });
    });
    menu.appendChild(addBtn);
  };

  buildItems();

  // Positioning relative to trigger button
  const rect = btn.getBoundingClientRect();
  menu.style.position = 'fixed';
  menu.style.top = (rect.bottom + 4) + 'px';
  menu.style.left = rect.left + 'px';
  document.body.appendChild(menu);

  // Adjust if overflowing right edge
  const menuRect = menu.getBoundingClientRect();
  if (menuRect.right > window.innerWidth - 8) {
    menu.style.left = Math.max(8, window.innerWidth - menuRect.width - 8) + 'px';
  }

  // Close on outside click
  const onClickOutside = (e: MouseEvent) => {
    if (!menu.contains(e.target as Node) && e.target !== btn) {
      closeMenu();
      document.removeEventListener('click', onClickOutside, true);
    }
  };
  // Close on Esc
  const onEsc = (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      closeMenu();
      document.removeEventListener('keydown', onEsc);
    }
  };
  setTimeout(() => {
    document.addEventListener('click', onClickOutside, true);
    document.addEventListener('keydown', onEsc);
  }, 0);
}

/* ------------------------------------------------------------------ */
/*  Create a single menu item element                                  */
/* ------------------------------------------------------------------ */

function createItem(
  preset: QualityPreset, config: AttachConfig,
  isCustom: boolean, idx?: number, rebuild?: () => void,
): HTMLElement {
  const item = document.createElement('button');
  item.className = 'bqp-item';
  const nameSpan = document.createElement('span');
  nameSpan.textContent = preset.name;
  item.appendChild(nameSpan);

  if (isCustom && idx !== undefined) {
    const del = document.createElement('span');
    del.className = 'bqp-item-delete';
    del.textContent = '\u2715';
    del.title = window.tr('common.delete', 'Delete');
    del.addEventListener('click', (e) => {
      e.stopPropagation();
      const customs = loadCustomPresets();
      customs.splice(idx, 1);
      saveCustomPresets(customs);
      showToast(window.tr('preset.deleted', 'Deleted'));
      if (rebuild) rebuild();
    });
    item.appendChild(del);
  }

  const desc = document.createElement('span');
  desc.className = 'bqp-item-desc';
  const preview = preset.positive.length > 40
    ? preset.positive.substring(0, 40) + '...'
    : preset.positive;
  desc.textContent = preview;
  item.appendChild(desc);

  item.addEventListener('click', () => {
    applyPreset(preset, config);
    closeMenu();
  });
  return item;
}
