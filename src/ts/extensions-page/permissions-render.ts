/**
 * permissions-render.ts -- Types and render helpers for the extension
 * permissions modal.
 *
 * Extracted from permissions-modal.ts to keep each module under 300 lines.
 */

import { extensionEsc } from './api';

/* ------------------------------------------------------------------ */
/*  Types                                                              */
/* ------------------------------------------------------------------ */

export interface PermissionDecl {
  name: string;
  reason: string;
}

export interface PermissionsData {
  name: string;
  trust_level: string;
  approved: boolean;
  permissions: {
    required: PermissionDecl[];
    optional: PermissionDecl[];
  };
  granted: {
    granted: string[];
    denied: string[];
    granted_at: string;
    auto_approved: boolean;
  } | null;
}

export interface TokenInfo {
  permission: string;
  issued_at: number;
  expires_at: number;
  expired: boolean;
}

export interface TokensData {
  name: string;
  token_count: number;
  tokens: TokenInfo[];
}

export interface IntegrityData {
  name: string;
  integrity: {
    monitored: boolean;
    file_count: number;
    tampered: boolean;
    tampered_files: string[];
  };
  revocation: {
    denial_count: number;
    last_access: number | null;
  };
  import_guard: {
    import_denial_count: number;
  };
}

export interface ScanFinding {
  file: string;
  line: number;
  severity: string;
  message: string;
}

export interface ScanData {
  name: string;
  trust_level: string;
  manifest_review: {
    approved: boolean;
    issues: { severity: string; message: string }[];
  };
  code_scan: {
    approved: boolean;
    findings: ScanFinding[];
  } | null;
}

/* ------------------------------------------------------------------ */
/*  Render helpers                                                     */
/* ------------------------------------------------------------------ */

export function severityColor(sev: string): string {
  if (sev === 'block') return '#e74c3c';
  if (sev === 'warn') return '#f39c12';
  return '#888';
}

export function trustColor(tl: string): string {
  if (tl === 'trusted') return '#2ecc71';
  if (tl === 'verified') return '#3498db';
  return '#e74c3c';
}

export function renderPermList(perms: PermissionDecl[], label: string): string {
  if (perms.length === 0) return '';
  return `
    <div style="margin-bottom:12px;">
      <div style="font-size:12px;font-weight:600;color:#aaa;margin-bottom:6px;">${extensionEsc(label)}</div>
      ${perms.map(p => `
        <div style="display:flex;align-items:center;gap:8px;padding:4px 0;font-size:13px;">
          <code style="background:rgba(100,100,100,0.2);padding:2px 8px;border-radius:4px;">${extensionEsc(p.name)}</code>
          ${p.reason ? `<span style="color:#999;font-size:11px;">${extensionEsc(p.reason)}</span>` : ''}
        </div>
      `).join('')}
    </div>`;
}

/** Render scan analysis section (manifest review + code scan). */
export function renderScanHtml(scanData: ScanData): string {
  let scanHtml = '';
  // Manifest review issues
  if (scanData.manifest_review?.issues.length > 0) {
    scanHtml += `<div style="margin-bottom:12px;">
      <div style="font-size:12px;font-weight:600;color:#aaa;margin-bottom:6px;">Manifest Review</div>
      ${scanData.manifest_review.issues.map(i => `
        <div style="font-size:12px;padding:4px 8px;margin-bottom:4px;border-radius:4px;background:rgba(${i.severity === 'block' ? '231,76,60' : '243,156,18'},0.1);color:${severityColor(i.severity)};">
          [${i.severity}] ${extensionEsc(i.message)}
        </div>
      `).join('')}
    </div>`;
  }
  // Code scan findings
  if (scanData.code_scan && scanData.code_scan.findings.length > 0) {
    scanHtml += `<div style="margin-bottom:12px;">
      <div style="font-size:12px;font-weight:600;color:#aaa;margin-bottom:6px;">Code Analysis</div>
      ${scanData.code_scan.findings.map(f => `
        <div style="font-size:12px;padding:4px 8px;margin-bottom:4px;border-radius:4px;background:rgba(${f.severity === 'block' ? '231,76,60' : '243,156,18'},0.1);color:${severityColor(f.severity)};">
          [${f.severity}] ${extensionEsc(f.file)}:${f.line} - ${extensionEsc(f.message)}
        </div>
      `).join('')}
    </div>`;
  }
  // A null code_scan means no scanner ran — the server says so when it has no
  // directory to read (Python) or no Python AST parser at all (Rust
  // standalone). That is NOT the same as a scan that came back clean, so it
  // must never fall through to "No issues found."; saying so would be a
  // positive claim about code nobody read.
  if (!scanData.code_scan) {
    scanHtml += `<div style="font-size:12px;color:#f39c12;margin-bottom:12px;">
      Code analysis not run — findings unknown.
    </div>`;
  } else if (!scanHtml) {
    scanHtml = '<div style="font-size:12px;color:#888;margin-bottom:12px;">No issues found.</div>';
  }
  return scanHtml;
}

/** Render capability tokens section. */
export function renderTokenHtml(tokensData: TokensData): string {
  if (tokensData.token_count === 0) return '';

  const tokenRows = tokensData.tokens.map(t => {
    const expiresDate = new Date(t.expires_at * 1000);
    const statusColor = t.expired ? '#e74c3c' : '#2ecc71';
    const statusLabel = t.expired ? 'Expired' : 'Active';
    return `
      <div style="display:flex;align-items:center;gap:8px;padding:3px 0;font-size:12px;">
        <code style="background:rgba(100,100,100,0.2);padding:1px 6px;border-radius:4px;">${extensionEsc(t.permission)}</code>
        <span style="color:${statusColor};font-size:11px;">${statusLabel}</span>
        <span style="color:#666;font-size:10px;">expires ${expiresDate.toLocaleString()}</span>
      </div>`;
  }).join('');
  return `
    <div style="margin-bottom:12px;">
      <div style="font-size:12px;font-weight:600;color:#aaa;margin-bottom:6px;">Capability Tokens (${tokensData.token_count})</div>
      ${tokenRows}
    </div>`;
}

/** Render runtime monitoring section. */
export function renderRuntimeHtml(integrityData: IntegrityData): string {
  if (!integrityData.integrity?.monitored) return '';

  const tamperedColor = integrityData.integrity.tampered ? '#e74c3c' : '#2ecc71';
  const tamperedLabel = integrityData.integrity.tampered ? 'TAMPERED' : 'OK';
  const denialCount = integrityData.import_guard?.import_denial_count || 0;
  const revDenials = integrityData.revocation?.denial_count || 0;

  let html = `
    <div style="margin-bottom:12px;">
      <div style="font-size:12px;font-weight:600;color:#aaa;margin-bottom:6px;">Runtime Monitoring</div>
      <div style="display:flex;gap:16px;flex-wrap:wrap;font-size:12px;">
        <span>Integrity: <span style="color:${tamperedColor};font-weight:600;">${tamperedLabel}</span> (${integrityData.integrity.file_count} files)</span>
        ${denialCount > 0 ? `<span>Import denials: <span style="color:#f39c12;">${denialCount}</span></span>` : ''}
        ${revDenials > 0 ? `<span>Service denials: <span style="color:#f39c12;">${revDenials}</span></span>` : ''}
      </div>`;
  if (integrityData.integrity.tampered_files.length > 0) {
    html += `
      <div style="margin-top:6px;">
        ${integrityData.integrity.tampered_files.slice(0, 5).map(f => `
          <div style="font-size:11px;color:#e74c3c;padding:2px 0;">${extensionEsc(f)}</div>
        `).join('')}
      </div>`;
  }
  html += '</div>';
  return html;
}
