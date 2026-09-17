/**
 * wd-tagger/profile-manager-modal.ts -- Profile manager modal (list/form switch).
 *
 * DOM construction policy: createElement + textContent/value + appendChild only.
 * Avoid HTML string insertion and inline event handlers.
 */

import { renderProfileList, type ProfileListApi } from './profile-list';
import { renderProfileForm, type ProfileFormApi, type ProfileFormMode, type ProfileV2 } from './profile-form';

type ViewMode = 'list' | 'form';

let _overlay: HTMLDivElement | null = null;
let _modal: HTMLDivElement | null = null;
let _body: HTMLDivElement | null = null;
let _view: ViewMode = 'list';

let _listApi: ProfileListApi | null = null;
let _formApi: ProfileFormApi | null = null;

function _t(key: string, fallback: string): string {
  try {
    if (typeof window.tr === 'function') {
      const v = String((window.tr as (k: string, f?: string) => unknown)(key, fallback));
      return v || fallback;
    }
  } catch { /* ignore */ }
  return fallback;
}

function _removeModal(): void {
  if (_overlay) _overlay.remove();
  _overlay = null;
  _modal = null;
  _body = null;
  _listApi = null;
  _formApi = null;
  _view = 'list';
}

function _clear(el: HTMLElement): void {
  while (el.firstChild) el.removeChild(el.firstChild);
}

function _ensureBody(): HTMLDivElement {
  if (!_body) throw new Error('profile manager modal not initialized');
  return _body;
}

function _showList(): void {
  const body = _ensureBody();
  _clear(body);
  _view = 'list';
  _listApi = renderProfileList(body, {
    onClose: _removeModal,
    onCreate: () => _showForm('create'),
    onEdit: (p) => _showForm('edit', p as unknown as ProfileV2),
    onDuplicate: (p) => _showForm('duplicate', p as unknown as ProfileV2),
    onImport: (p) => _showForm('create', p as unknown as ProfileV2),
  });
  void _listApi.refresh();
}

function _showForm(mode: ProfileFormMode, profile?: ProfileV2): void {
  const body = _ensureBody();
  _clear(body);
  _view = 'form';
  _formApi = renderProfileForm(body, {
    mode,
    profile,
    onCancel: _showList,
    onSaved: () => {
      // Save success → list refresh + notify dropdown rebuild (profiles.ts listens)
      try {
        window.dispatchEvent(new CustomEvent('wd-tagger-profile-changed'));
      } catch { /* ignore */ }
      _showList();
    },
  });
}

export function openProfileManagerModal(): void {
  // Prevent double-open
  if (_overlay) return;

  const overlay = document.createElement('div');
  overlay.className = 'wt-profile-modal-overlay';
  overlay.style.cssText = [
    'position:fixed', 'inset:0',
    'background:rgba(0,0,0,0.5)',
    'z-index:10000',
    'display:flex', 'align-items:center', 'justify-content:center',
  ].join(';');
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) _removeModal();
  });

  const modal = document.createElement('div');
  modal.className = 'wt-profile-modal';
  modal.style.cssText = [
    'background:var(--bg, #fff)', 'color:var(--fg, #222)',
    'max-width:900px', 'width:94%', 'max-height:90vh', 'overflow:auto',
    'border-radius:8px', 'padding:16px 16px 14px',
    'box-shadow:0 10px 40px rgba(0,0,0,0.25)',
    'border:1px solid var(--border, #ddd)',
  ].join(';');
  modal.setAttribute('role', 'dialog');

  const header = document.createElement('div');
  header.style.cssText = 'display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:10px;';
  modal.appendChild(header);

  const title = document.createElement('h3');
  title.textContent = _t('tools.wt_profile_modal_title', 'Tagger profiles');
  title.style.cssText = 'margin:0;font-size:16px;';
  title.id = 'wt-profile-manager-title';
  modal.setAttribute('aria-labelledby', title.id);
  header.appendChild(title);

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'btn btn-secondary';
  closeBtn.textContent = _t('tools.wt_close', 'Close');
  closeBtn.addEventListener('click', _removeModal);
  header.appendChild(closeBtn);

  const body = document.createElement('div');
  body.className = 'wt-profile-modal-body';
  modal.appendChild(body);

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  _overlay = overlay;
  _modal = modal;
  _body = body;
  _view = 'list';

  _showList();
}

export function closeProfileManagerModal(): void {
  _removeModal();
}

export function getProfileManagerModalView(): ViewMode {
  return _view;
}
