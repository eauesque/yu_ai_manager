/**
 * scan-panel.ts -- port scan UI using fetch() + ReadableStream SSE.
 * IMPORTANT: use fetch streams for SSE because the native browser SSE API is proxied.
 * All API response strings rendered via innerHTML are sanitized with escapeHtml().
 */
import { apiFetch, escapeHtml } from '../main/api-utils';
import { mutationHeaders } from '../shared/gateway-auth';
import { refreshBackends, getRegisteredPorts } from './backends-panel';

interface ScanFoundEntry {
  type: string;
  port: number;
  base_url?: string;
  registered?: boolean;
  already_existed?: boolean;
}

interface ScanProgressEvent {
  type: 'progress';
  scanned?: number;
  total?: number;
}

interface ScanFoundEvent {
  type: 'found';
  entry?: ScanFoundEntry;
}

interface ScanTerminalEvent {
  type: 'done' | 'cancelled';
}

type ScanEvent = ScanProgressEvent | ScanFoundEvent | ScanTerminalEvent;

const seenPorts = new Set<number>();
let activeReader: ReadableStreamDefaultReader<Uint8Array> | null = null;
let activeScanId = '';
let finishing = false;

export function initScanPanel(): void {
  const rangeChk = getInput('gw-scan-range');
  const fullChk = getInput('gw-scan-full');
  if (!rangeChk || !fullChk) return;

  rangeChk.addEventListener('change', updateRangeInputs);
  fullChk.addEventListener('change', handleFullScanChange);
  getButton('gw-scan-start')?.addEventListener('click', () => { void startScan(); });
  getButton('gw-scan-cancel')?.addEventListener('click', () => { void cancelScan(); });

  updateRangeInputs();
}

async function startScan(): Promise<void> {
  if (activeScanId) return;

  const body = buildScanRequest();
  if (!body) return;

  try {
    const postResp = await apiFetch('/api/gateway/backends/scan', {
      method: 'POST',
      headers: await mutationHeaders(),
      body: JSON.stringify(body),
    });
    const { scanId } = (await postResp.json()) as { scanId?: string };
    if (!scanId) {
      alert('スキャン開始に失敗しました');
      return;
    }

    beginScan(scanId);
    await readScanStream(scanId);
  } catch (err) {
    if (!finishing) {
      alert(err instanceof Error ? err.message : 'スキャン開始に失敗しました');
    }
    await finishScan();
  }
}

function buildScanRequest(): Record<string, unknown> | null {
  const defaults = getInput('gw-scan-defaults')?.checked ?? false;
  const rangeEnabled = getInput('gw-scan-range')?.checked ?? false;
  const fullScan = getInput('gw-scan-full')?.checked ?? false;
  const autoRegister = getInput('gw-scan-auto-register')?.checked ?? false;

  if (fullScan) {
    return {
      include_defaults: defaults,
      full_scan: true,
      auto_register: autoRegister,
    };
  }

  const body: Record<string, unknown> = {
    include_defaults: defaults,
    full_scan: false,
    auto_register: autoRegister,
  };

  if (rangeEnabled) {
    const min = readPort('gw-scan-range-min');
    const max = readPort('gw-scan-range-max');
    if (min === null || max === null || min > max) {
      alert('ポート範囲は 1〜65535 の範囲で、最小値が最大値以下になるように入力してください');
      return null;
    }
    body.range = { min, max };
  }

  if (!defaults && !rangeEnabled) {
    alert('スキャン対象を選択してください');
    return null;
  }

  return body;
}

function beginScan(scanId: string): void {
  activeScanId = scanId;
  finishing = false;
  seenPorts.clear();
  document.getElementById('gw-scan-results')?.replaceChildren();
  setProgress(0, 0);
  setScanningUi(true);
}

async function readScanStream(scanId: string): Promise<void> {
  const resp = await fetch(`/api/gateway/backends/scan/${encodeURIComponent(scanId)}/stream`);
  if (!resp.ok || !resp.body) {
    throw new Error('スキャンストリームに接続できませんでした');
  }

  activeReader = resp.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (activeReader) {
      const { done, value } = await activeReader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const terminal = processSseBuffer(buffer);
      buffer = terminal.remainder;
      if (terminal.finished) break;
    }
  } finally {
    await finishScan();
  }
}

function processSseBuffer(buffer: string): { remainder: string; finished: boolean } {
  const normalized = buffer.replace(/\r\n/g, '\n');
  const chunks = normalized.split('\n\n');
  const remainder = chunks.pop() ?? '';
  let finished = false;

  for (const chunk of chunks) {
    const data = chunk
      .split('\n')
      .filter(line => line.startsWith('data:'))
      .map(line => line.slice(5).trimStart())
      .join('\n');
    if (!data) continue;

    const event = JSON.parse(data) as unknown;
    if (handleScanEvent(event)) {
      finished = true;
      void closeReader();
      break;
    }
  }

  return { remainder, finished };
}

function handleScanEvent(event: unknown): boolean {
  if (!isScanEvent(event)) return false;

  switch (event.type) {
    case 'progress':
      setProgress(toNumber(event.scanned), toNumber(event.total));
      return false;
    case 'found':
      if (event.entry) addCandidate(event.entry);
      return false;
    case 'done':
    case 'cancelled':
      return true;
    default:
      return false;
  }
}

function isScanEvent(event: unknown): event is ScanEvent {
  return typeof event === 'object' && event !== null && 'type' in event;
}

function addCandidate(entry: ScanFoundEntry): void {
  const port = Number(entry.port);
  if (!Number.isInteger(port) || seenPorts.has(port)) return;
  seenPorts.add(port);

  const container = document.getElementById('gw-scan-results');
  if (!container) return;

  const row = document.createElement('div');
  row.className = 'scan-candidate row gap-2';

  const typeHtml = escapeHtml(entry.type);
  const urlHtml = escapeHtml(entry.base_url ?? '');
  const urlPart = urlHtml ? `<span class="muted">${urlHtml}</span>` : '';

  // Proactively show "登録済み" if already in the registered backends list,
  // even when the server-side scan ran before the backend was added.
  if (entry.already_existed || entry.registered || getRegisteredPorts().has(port)) {
    const typeSpan = document.createElement('span');
    typeSpan.textContent = `${entry.type} :${port}`;
    row.appendChild(typeSpan);
    if (entry.base_url) {
      const urlSpan = document.createElement('span');
      urlSpan.className = 'muted';
      urlSpan.textContent = entry.base_url;
      row.appendChild(urlSpan);
    }
    const badge = document.createElement('span');
    badge.className = 'badge badge-ok';
    badge.textContent = '登録済み';
    row.appendChild(badge);
    container.appendChild(row);
    return;
  }

  row.innerHTML = `<span>${typeHtml} :${port}</span>${urlPart}<button class="btn-sm" type="button" data-action="add-candidate">追加</button>`;
  row.querySelector('[data-action="add-candidate"]')?.addEventListener('click', () => {
    void addBackendCandidate(entry, row);
  });

  container.appendChild(row);
}

async function addBackendCandidate(entry: ScanFoundEntry, row: HTMLElement): Promise<void> {
  try {
    await apiFetch('/api/gateway/backends', {
      method: 'POST',
      headers: await mutationHeaders(),
      body: JSON.stringify({ type: entry.type, port: entry.port }),
      silent: true,
    });
  } catch {
    // Likely a conflict (port registered concurrently) — show as registered.
    const badge = document.createElement('span');
    badge.className = 'badge badge-ok';
    badge.textContent = '登録済み';
    row.querySelector('button')?.replaceWith(badge);
    await refreshBackends();
    return;
  }

  const badge = document.createElement('span');
  badge.className = 'badge badge-ok';
  badge.textContent = '登録済み';
  row.querySelector('button')?.replaceWith(badge);
  await refreshBackends();
}

async function cancelScan(): Promise<void> {
  const scanId = activeScanId;
  try {
    if (scanId) {
      await apiFetch(`/api/gateway/backends/scan/${encodeURIComponent(scanId)}`, {
        method: 'DELETE',
        headers: await mutationHeaders(),
      });
    }
  } finally {
    await closeReader();
    await finishScan();
  }
}

async function finishScan(): Promise<void> {
  if (finishing) return;
  finishing = true;

  await closeReader();
  activeScanId = '';
  setScanningUi(false);
  await refreshBackends();
  finishing = false;
}

async function closeReader(): Promise<void> {
  const reader = activeReader;
  activeReader = null;
  if (!reader) return;
  try {
    await reader.cancel();
  } catch {
    // Stream may already be closed by the server.
  } finally {
    try {
      reader.releaseLock();
    } catch {
      // Lock may already be released after cancellation.
    }
  }
}

async function handleFullScanChange(): Promise<void> {
  const fullChk = getInput('gw-scan-full');
  const rangeChk = getInput('gw-scan-range');
  if (!fullChk || !rangeChk) return;

  if (fullChk.checked) {
    const ok = await window.customConfirm('全ポートスキャンは時間がかかる場合があります。続行しますか？');
    if (!ok) {
      fullChk.checked = false;
      rangeChk.disabled = false;
      updateRangeInputs();
      return;
    }
    rangeChk.checked = false;
    rangeChk.disabled = true;
  } else {
    rangeChk.disabled = false;
  }
  updateRangeInputs();
}

function updateRangeInputs(): void {
  const rangeChk = getInput('gw-scan-range');
  const rangeDiv = document.getElementById('gw-scan-range-inputs');
  const enabled = Boolean(rangeChk?.checked && !rangeChk.disabled);
  rangeDiv?.classList.toggle('hidden', !enabled);
  getInput('gw-scan-range-min')?.toggleAttribute('disabled', !enabled);
  getInput('gw-scan-range-max')?.toggleAttribute('disabled', !enabled);
}

function setProgress(scanned: number, total: number): void {
  const progress = document.getElementById('gw-scan-progress');
  const bar = document.getElementById('gw-scan-bar') as HTMLProgressElement | null;
  const counter = document.getElementById('gw-scan-counter');

  progress?.classList.remove('hidden');
  if (bar) {
    bar.max = total || 1;
    bar.value = scanned;
  }
  if (counter) {
    counter.textContent = `${scanned} / ${total}`;
  }
}

function setScanningUi(scanning: boolean): void {
  const startBtn = getButton('gw-scan-start');
  const cancelBtn = getButton('gw-scan-cancel');

  if (startBtn) {
    startBtn.disabled = scanning;
    startBtn.textContent = 'スキャン開始';
    startBtn.classList.toggle('hidden', scanning);
  }
  cancelBtn?.classList.toggle('hidden', !scanning);
}

function readPort(id: string): number | null {
  const raw = getInput(id)?.value ?? '';
  const port = Number.parseInt(raw, 10);
  if (!Number.isInteger(port) || port < 1 || port > 65535) return null;
  return port;
}

function toNumber(value: unknown): number {
  return typeof value === 'number' && Number.isFinite(value) ? value : 0;
}

function getInput(id: string): HTMLInputElement | null {
  return document.getElementById(id) as HTMLInputElement | null;
}

function getButton(id: string): HTMLButtonElement | null {
  return document.getElementById(id) as HTMLButtonElement | null;
}
