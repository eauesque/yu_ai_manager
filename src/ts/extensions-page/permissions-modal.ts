/**
 * Extension permissions modal -- shows permission details,
 * static analysis results, and approve/deny controls.
 *
 * Types and render helpers are in permissions-render.ts.
 */

import { extensionApiFetch, extensionEsc } from './api';
import {
  type PermissionsData,
  type ScanData,
  type TokensData,
  type IntegrityData,
  trustColor,
  renderPermList,
  renderScanHtml,
  renderTokenHtml,
  renderRuntimeHtml,
} from './permissions-render';

let _modalEl: HTMLDivElement | null = null;

function _getOrCreateModal(): HTMLDivElement {
  if (_modalEl) return _modalEl;
  _modalEl = document.createElement('div');
  _modalEl.id = 'ext-permissions-modal';
  _modalEl.setAttribute('role', 'dialog');
  _modalEl.setAttribute('aria-modal', 'true');
  _modalEl.setAttribute('aria-label', 'Extension Permissions');
  _modalEl.style.cssText = 'display:none;position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,0.6);align-items:center;justify-content:center;';
  _modalEl.addEventListener('click', (e) => {
    if (e.target === _modalEl) _closeModal();
  });
  document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape' && _modalEl?.style.display === 'flex') _closeModal();
  });
  document.body.appendChild(_modalEl);
  return _modalEl;
}

function _closeModal(): void {
  if (_modalEl) _modalEl.style.display = 'none';
}

function _bindModalActions(modal: HTMLDivElement, name: string, approved: boolean): void {
  const closeButtons = modal.querySelectorAll<HTMLElement>('[data-ext-modal-close]');
  closeButtons.forEach((btn) => {
    btn.addEventListener('click', _closeModal);
  });

  const approveButton = modal.querySelector<HTMLElement>('[data-ext-modal-approve]');
  if (approveButton && !approved) {
    approveButton.addEventListener('click', () => {
      void approveExtPermissions(name);
    });
  }

  const revokeButton = modal.querySelector<HTMLElement>('[data-ext-modal-revoke]');
  if (revokeButton && approved) {
    revokeButton.addEventListener('click', () => {
      void revokeExtPermissions(name);
    });
  }
}

export async function showPermissionsModal(name: string): Promise<void> {
  const modal = _getOrCreateModal();
  modal.style.display = 'flex';
  modal.innerHTML = `
    <div style="background:#1e1e2e;border-radius:12px;padding:24px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;color:#ccc;">
      <div style="text-align:center;padding:20px;color:#888;">Loading...</div>
    </div>`;

  try {
    const [permRes, scanRes, tokensRes, integrityRes] = await Promise.all([
      extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/permissions`),
      extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/scan-results`),
      extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/tokens`),
      extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/integrity`),
    ]);
    const permData: PermissionsData = await permRes.json();
    const scanData: ScanData = await scanRes.json();
    const tokensData: TokensData = await tokensRes.json();
    const integrityData: IntegrityData = await integrityRes.json();

    const tl = permData.trust_level || 'untrusted';
    const tlColor = trustColor(tl);

    const scanHtml = renderScanHtml(scanData);
    const tokenHtml = renderTokenHtml(tokensData);
    const runtimeHtml = renderRuntimeHtml(integrityData);

    const approvedBadge = permData.approved
      ? '<span style="color:#2ecc71;font-size:12px;">Approved</span>'
      : '<span style="color:#f39c12;font-size:12px;">Not approved</span>';

    const grantedInfo = permData.granted
      ? `<div style="font-size:11px;color:#888;margin-top:8px;">
          Approved at: ${extensionEsc(permData.granted.granted_at || 'N/A')}
          ${permData.granted.auto_approved ? '(auto)' : ''}
         </div>`
      : '';

    modal.innerHTML = `
      <div style="background:#1e1e2e;border-radius:12px;padding:24px;max-width:600px;width:90%;max-height:80vh;overflow-y:auto;color:#ccc;" role="document">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;">
          <h3 style="margin:0;font-size:16px;">${extensionEsc(name)}</h3>
          <button type="button" data-ext-modal-close="1" style="background:none;border:none;color:#888;font-size:20px;cursor:pointer;" aria-label="Close">&times;</button>
        </div>
        <div style="display:flex;gap:8px;align-items:center;margin-bottom:16px;">
          <span style="font-size:11px;padding:2px 8px;border-radius:8px;background:rgba(${tl === 'trusted' ? '46,204,113' : tl === 'verified' ? '52,152,219' : '231,76,60'},0.15);color:${tlColor};">Trust: ${tl.toUpperCase()}</span>
          ${approvedBadge}
        </div>
        ${renderPermList(permData.permissions?.required || [], 'Required Permissions')}
        ${renderPermList(permData.permissions?.optional || [], 'Optional Permissions')}
        ${tokenHtml}
        ${runtimeHtml}
        <hr style="border:none;border-top:1px solid rgba(255,255,255,0.08);margin:16px 0;">
        <div style="font-size:13px;font-weight:600;margin-bottom:8px;">Security Analysis</div>
        ${scanHtml}
        ${grantedInfo}
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:16px;">
          ${!permData.approved ? '<button class="btn" type="button" data-ext-modal-approve="1" style="padding:6px 16px;font-size:13px;background:#2ecc71;color:#fff;border:none;border-radius:6px;cursor:pointer;">Approve</button>' : ''}
          ${permData.approved ? '<button class="btn" type="button" data-ext-modal-revoke="1" style="padding:6px 16px;font-size:13px;background:#e74c3c;color:#fff;border:none;border-radius:6px;cursor:pointer;">Revoke</button>' : ''}
          <button class="btn btn-secondary" type="button" data-ext-modal-close="1" style="padding:6px 16px;font-size:13px;">Close</button>
        </div>
      </div>`;
    _bindModalActions(modal, name, !!permData.approved);
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    modal.innerHTML = `
      <div style="background:#1e1e2e;border-radius:12px;padding:24px;max-width:500px;width:90%;color:#e74c3c;">
        Failed to load permissions: ${extensionEsc(message)}
        <div style="margin-top:12px;text-align:right;">
          <button class="btn btn-secondary" type="button" data-ext-modal-close="1" style="padding:6px 16px;font-size:13px;">Close</button>
        </div>
      </div>`;
    _bindModalActions(modal, name, false);
  }
}

export async function approveExtPermissions(name: string): Promise<void> {
  try {
    const permRes = await extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/permissions`);
    const permData: PermissionsData = await permRes.json();

    const allPerms = [
      ...(permData.permissions?.required || []).map(p => p.name),
      ...(permData.permissions?.optional || []).map(p => p.name),
    ];

    await extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'approve', granted: allPerms, denied: [] }),
    });

    // Refresh modal
    await showPermissionsModal(name);
  } catch (err) {
    alert('Failed to approve: ' + (err instanceof Error ? err.message : String(err)));
  }
}

export async function revokeExtPermissions(name: string): Promise<void> {
  try {
    await extensionApiFetch(`/api/extensions/${encodeURIComponent(name)}/permissions`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ action: 'revoke' }),
    });
    await showPermissionsModal(name);
  } catch (err) {
    alert('Failed to revoke: ' + (err instanceof Error ? err.message : String(err)));
  }
}
