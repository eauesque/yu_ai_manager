/**
 * duplicates/ui.ts -- Duplicate image preview, checkbox sync, and group selection.
 * Converted from tools-duplicates-ui.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';
import { icon } from '../../shared/icon';
import { copyToClipboard } from '../../shared/clipboard';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function syncDupeCheck(
  el: HTMLInputElement,
  groupIdx: number,
  fileIdx: number,
): void {
  const thumbCheck = document.querySelector<HTMLInputElement>(
    `.dupe-check[data-group="${groupIdx}"][data-file-idx="${fileIdx}"]`,
  );
  if (thumbCheck) thumbCheck.checked = el.checked;
}

export function initDupeCheckSync(): void {
  document.addEventListener('change', (e: Event) => {
    const target = e.target as HTMLElement;
    if (target.classList.contains('dupe-check')) {
      const g = (target as HTMLInputElement).dataset.group;
      const f = (target as HTMLInputElement).dataset.fileIdx;
      const pathCheck = document.querySelector<HTMLInputElement>(
        `.dupe-check-path[data-group="${g}"][data-file-idx="${f}"]`,
      );
      if (pathCheck) pathCheck.checked = (target as HTMLInputElement).checked;
    }
  });
}

export function previewDuplicateImage(fileId: number): void {
  let modal = document.getElementById('dupePreviewModal');
  if (!modal) {
    modal = document.createElement('div');
    modal.id = 'dupePreviewModal';
    modal.style.cssText =
      'position:fixed;top:0;left:0;width:100%;height:100%;background:rgba(0,0,0,0.85);z-index:10000;display:flex;align-items:center;justify-content:center;cursor:pointer;';
    const modalRef = modal;
    modal.addEventListener('click', (e: MouseEvent) => {
      if (e.target === modalRef) modalRef.style.display = 'none';
    });
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Escape' && modalRef.style.display !== 'none')
        modalRef.style.display = 'none';
    });
    document.body.appendChild(modal);
  }
  const modalEl = modal;
  const dismiss = () => {
    modalEl.style.display = 'none';
  };

  modalEl.replaceChildren();

  const inner = document.createElement('div');
  inner.style.cssText =
    'position:relative;max-width:90vw;max-height:90vh;display:flex;flex-direction:column;align-items:center;';
  inner.addEventListener('click', (e) => e.stopPropagation());

  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.textContent = '\u2715';
  closeBtn.setAttribute('aria-label', _t('common.close', 'Close'));
  closeBtn.style.cssText =
    'position:absolute;top:6px;right:6px;background:rgba(0,0,0,0.6);color:white;border:none;border-radius:50%;width:32px;height:32px;cursor:pointer;font-size:16px;z-index:10;backdrop-filter:blur(4px);';
  closeBtn.addEventListener('click', dismiss);
  inner.append(closeBtn);

  const img = document.createElement('img');
  img.src = `/api/original/${fileId}`;
  img.alt = '';
  img.style.cssText =
    'max-width:90vw;max-height:75vh;object-fit:contain;border-radius:6px;cursor:pointer;';
  img.addEventListener('click', dismiss);
  inner.append(img);

  const meta = document.createElement('div');
  meta.style.cssText =
    'display:flex;align-items:center;gap:12px;margin-top:8px;flex-wrap:wrap;';

  const info = document.createElement('span');
  info.id = 'dupePreviewInfo';
  info.style.cssText = 'color:#ccc;font-size:13px;cursor:pointer;';
  info.textContent = _t('tools.loading', 'Loading...');
  info.addEventListener('click', () => {
    const p = info.dataset.path;
    if (!p) return;
    void copyToClipboard(p).catch(() => {});
    info.style.color = '#2ecc71';
    setTimeout(() => {
      info.style.color = '#ccc';
    }, 1200);
  });
  meta.append(info);

  const link = document.createElement('a');
  link.href = `/?open=${fileId}`;
  link.className = 'nav-link';
  const linkIcon = document.createElement('span');
  linkIcon.className = 'icon';
  linkIcon.setAttribute('aria-hidden', 'true');
  linkIcon.textContent = '\u{1F50D}';
  const linkLabel = document.createElement('span');
  linkLabel.className = 'label';
  linkLabel.textContent = _t('tools.open_detail_tab', 'Open detail in new tab');
  link.append(linkIcon, linkLabel);
  meta.append(link);

  inner.append(meta);
  modalEl.append(inner);
  modalEl.style.display = 'flex';

  apiFetch('/api/file/' + fileId)
    .then((r) => r.json())
    .then(
      (data: { path?: string; resolution?: string; size?: number }) => {
        let text = data.path || '';
        if (data.resolution) text += ` | ${data.resolution}`;
        if (data.size) text += ` | ${(data.size / 1024).toFixed(1)} KB`;
        info.textContent = text;
        info.dataset.path = data.path || '';
        info.title = _t('tools.click_copy_path', 'Click to copy path');
      },
    )
    .catch(() => {});
}

export function selectAllDupes(groupIdx: number): void {
  document
    .querySelectorAll<HTMLInputElement>(`.dupe-check[data-group="${groupIdx}"]`)
    .forEach((cb) => {
      if (cb.dataset.fileIdx !== '0') cb.checked = true;
    });
  document
    .querySelectorAll<HTMLInputElement>(`.dupe-check-path[data-group="${groupIdx}"]`)
    .forEach((cb) => {
      if (cb.dataset.fileIdx !== '0') cb.checked = true;
    });
}

/** Set a specific item as the keeper for a group. All others in the group get marked for deletion. */
export function setKeepImage(groupIdx: number, keepFileIdx: number): void {
  // Update thumb checkboxes and visual state
  document
    .querySelectorAll<HTMLInputElement>(`.dupe-check[data-group="${groupIdx}"]`)
    .forEach((cb) => {
      const fi = parseInt(cb.dataset.fileIdx || '0', 10);
      cb.checked = fi !== keepFileIdx;
    });

  // Update path checkboxes
  document
    .querySelectorAll<HTMLInputElement>(`.dupe-check-path[data-group="${groupIdx}"]`)
    .forEach((cb) => {
      const fi = parseInt(cb.dataset.fileIdx || '0', 10);
      cb.checked = fi !== keepFileIdx;
    });

  // Update borders, label text, and keep button styles
  document.querySelectorAll<HTMLElement>(`.dupe-thumb-cell[data-group="${groupIdx}"]`).forEach((cell) => {
    const fi = parseInt(cell.dataset.fileIdx || '0', 10);
    const isNowKeep = fi === keepFileIdx;
    const img = cell.querySelector<HTMLImageElement>('.dupe-thumb-img');
    const label = cell.querySelector<HTMLElement>('.dupe-label');
    const keepBtn = cell.querySelector<HTMLButtonElement>('.dupe-keep-btn');
    const keepText = _t('tools.keep', 'Keep');
    const dupText = _t('tools.duplicate', 'Duplicate');
    const keepingLabel = _t('tools.keeping', 'Keeping');
    const keepThisText = _t('tools.keep_this', 'Keep this');
    if (img) img.style.border = isNowKeep ? '2px solid #2ecc71' : '2px solid #e74c3c';
    if (label) {
      label.textContent = isNowKeep ? keepText : dupText;
      label.style.color = isNowKeep ? '#2ecc71' : '#e74c3c';
    }
    if (keepBtn) {
      if (isNowKeep) {
        // Rebuild with SVG icon + label. Both are trusted (static sprite + i18n).
        keepBtn.replaceChildren();
        keepBtn.insertAdjacentHTML('beforeend', icon('pin'));
        keepBtn.append(' ' + keepingLabel);
        keepBtn.style.background = '#2ecc71';
        keepBtn.style.color = '#000';
        keepBtn.style.fontWeight = '600';
        keepBtn.style.border = 'none';
      } else {
        keepBtn.textContent = keepThisText;
        keepBtn.style.background = 'rgba(255,255,255,0.1)';
        keepBtn.style.color = '';
        keepBtn.style.fontWeight = '';
        keepBtn.style.border = '1px solid rgba(255,255,255,0.3)';
      }
    }
  });

  updateDupeDeleteCount();
}

/** Update the live delete counter display. */
export function updateDupeDeleteCount(): void {
  const countEl = document.getElementById('dupeDeleteCount');
  if (!countEl) return;
  const checked = document.querySelectorAll<HTMLInputElement>('.dupe-check-path:checked');
  const total = checked.length;
  if (total === 0) {
    countEl.style.display = 'none';
    return;
  }
  const _tr = typeof window !== 'undefined'
    ? (window as unknown as Record<string, unknown>).tr as ((k: string, f: string) => string) | undefined
    : undefined;
  const msg = (_tr ? _tr('tools.dupe_delete_summary', '{count}件を削除対象にマーク済み') : '{count}件を削除対象にマーク済み').replace('{count}', String(total));
  // Trusted SVG markup + i18n message. innerHTML-equivalent via DOM API.
  countEl.replaceChildren();
  countEl.insertAdjacentHTML('beforeend', icon('trash'));
  countEl.append(' ' + msg);
  countEl.style.display = 'block';
}
