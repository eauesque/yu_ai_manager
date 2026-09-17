import { getAppApi } from '../shared/browser-apis';

function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export function renderMetaStats(metaStats: Record<string, number>): string {
  const total = Object.values(metaStats).reduce((a, b) => a + b, 0);
  if (total === 0) return '';
  const sorted = Object.entries(metaStats).sort((a, b) => b[1] - a[1]);
  const unknownCount = metaStats.unknown || 0;
  const unknownPct = total > 0 ? Math.round((unknownCount / total) * 100) : 0;
  const metaDesc: Record<string, string> = {
    unknown: 'メタデータ未検出（解析対象外形式・スキャンエラーの可能性）',
    png_chunk: 'PNG チャンクからメタデータを取得',
    exif: 'EXIF データからメタデータを取得',
    a1111_png: 'Stable Diffusion (A1111) PNG 形式',
    a1111_jpg: 'Stable Diffusion (A1111) JPEG 形式',
    novelai_png: 'NovelAI PNG 形式',
    novelai_v4_png: 'NovelAI v4 PNG 形式',
    novelai_webp: 'NovelAI WebP 形式',
    novelai_v4_webp: 'NovelAI v4 WebP 形式',
    comfyui: 'ComfyUI 形式',
  };

  let html = '';
  if (unknownPct > 20) {
    html += `<div style="margin-bottom:8px;padding:8px 12px;border-radius:6px;background:rgba(185,28,28,0.1);border:1px solid rgba(185,28,28,0.3);font-size:12px;color:var(--text);">⚠️ 全ファイルの <strong>${unknownPct}%</strong> がメタデータ未取得です。<a href="/settings" data-action="settingsPageApi.switchTab" data-action-arg="scan" style="color:inherit;text-decoration:underline;">スキャン設定</a>を確認してください。</div>`;
  }
  html += '<div style="margin-top:4px;">';
  for (const [key, count] of sorted) {
    const pct = Math.round((count / total) * 100);
    const isUnknown = key === 'unknown';
    const barColor = isUnknown ? '#b91c1c' : '#166534';
    html += `<div style="margin-bottom:6px;" title="${esc(metaDesc[key] || key)}"><div style="display:flex;justify-content:space-between;font-size:11px;margin-bottom:2px;"><span style="color:${isUnknown ? '#b91c1c' : 'var(--text)'};font-weight:${isUnknown ? '600' : '400'};">${esc(key)}</span><span style="color:var(--muted);">${count.toLocaleString()} (${pct}%)</span></div><div style="height:6px;border-radius:3px;background:rgba(128,128,128,0.15);overflow:hidden;"><div style="height:100%;width:${pct}%;background:${barColor};border-radius:3px;transition:width 0.3s;"></div></div></div>`;
  }
  html += '</div>';
  return html;
}

export async function loadScanErrorStats(): Promise<Array<{ error_type: string; count: number }>> {
  try {
    const resp = await fetch('/api/maintenance/scan-error-stats');
    const json = await resp.json();
    return (json.data || json).errors || [];
  } catch {
    return [];
  }
}

export async function loadOsIsolationStatus(): Promise<void> {
  const grid = document.getElementById('serverStatusGrid');
  if (!grid) return;
  const gridInner = grid.querySelector('div');
  if (!gridInner) return;
  try {
    const res = await fetch('/api/extensions/os-isolation');
    if (!res.ok) return;
    const data = await res.json();
    const iso = data.os_isolation || {};
    const cfg = data.config || {};
    const details = iso.details || {};
    const processes: Array<{ extension?: string; apparmor_profile?: string; pid?: number }> = data.processes || [];
    const available = !!iso.available;
    const enabled = !!cfg.enabled;
    const method = (iso.method as string) || 'none';
    const t = (key: string, fallback: string) => getAppApi().tr(key, fallback);
    let statusBadge = `<span style="color:#166534;font-weight:600;">${t('settings.os_iso_active', 'Active')}</span>`;
    if (!available) statusBadge = `<span style="color:#d32f2f;font-weight:600;">${t('settings.os_iso_unavailable', 'Unavailable')}</span>`;
    else if (!enabled) statusBadge = `<span style="color:#b45309;font-weight:600;">${t('settings.os_iso_inactive', 'Inactive')}</span>`;
    const subLines: string[] = [`${t('settings.os_iso_method', 'Method')}: ${method.toUpperCase()}`];
    if (method === 'apparmor') subLines.push(`Kernel: ${details.apparmor_kernel || 'unknown'} / Tools: ${details.apparmor_tools ? 'OK' : 'Missing'} / Sudoers: ${details.apparmor_sudoers ? 'OK' : 'Missing'}`);
    if (processes.length > 0) subLines.push(`${t('settings.os_iso_processes', 'Isolated processes')}: ${processes.length}`);
    const card = document.createElement('div');
    card.className = 'status-card';
    card.innerHTML = `<div class="status-label">${t('settings.os_isolation', 'OS Isolation')}</div><div class="status-value">${statusBadge}</div><div class="status-sub">${subLines.join('<br>')}</div>`;
    gridInner.appendChild(card);
  } catch {
    // ignore unsupported API
  }
}
