/**
 * Tools page — Hash Backfill panel.
 * POST /api/hash-backfill/start  — begin
 * POST /api/hash-backfill/cancel — cancel
 * GET  /api/hash-backfill/status — status (5s polling fallback)
 * SSE  hash_backfill.progress    — primary progress source
 * SSE  hash_backfill.complete    — completion
 */

const POLL_INTERVAL_MS = 5_000;
let pollTimer: ReturnType<typeof setInterval> | null = null;

interface BackfillStatus {
  running: boolean;
  processed: number;
  total: number;
  percent: number;
}

function setRunning(state: boolean): void {
  const startBtn = document.getElementById('hashBackfillStartBtn');
  const cancelBtn = document.getElementById('hashBackfillCancelBtn');
  const progressEl = document.getElementById('hashBackfillProgress');
  if (startBtn) startBtn.style.display = state ? 'none' : '';
  if (cancelBtn) cancelBtn.style.display = state ? '' : 'none';
  if (progressEl) progressEl.style.display = state ? '' : 'none';
}

function updateProgress(percent: number, label: string): void {
  const bar = document.getElementById('hashBackfillBar');
  const status = document.getElementById('hashBackfillStatus');
  if (bar) bar.style.width = `${Math.min(100, percent)}%`;
  if (status) status.textContent = label;
}

async function fetchStatus(): Promise<void> {
  try {
    const res = await fetch('/api/hash-backfill/status');
    if (!res.ok) return;
    const data = (await res.json()) as BackfillStatus;
    if (data.running) {
      setRunning(true);
      updateProgress(data.percent, `${data.processed} / ${data.total}`);
    } else {
      setRunning(false);
      stopPolling();
    }
  } catch {
    /* ignore */
  }
}

function startPolling(): void {
  if (pollTimer !== null) return;
  pollTimer = setInterval(() => void fetchStatus(), POLL_INTERVAL_MS);
}

function stopPolling(): void {
  if (pollTimer !== null) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

type SseCallback = (data: unknown) => void;
type SseSubscribeFn = (event: string, cb: SseCallback) => void;

export function initHashBackfill(sseSubscribe: SseSubscribeFn): void {
  document.getElementById('hashBackfillStartBtn')?.addEventListener('click', () => {
    void fetch('/api/hash-backfill/start', { method: 'POST' }).then(() => {
      setRunning(true);
      startPolling();
    });
  });

  document.getElementById('hashBackfillCancelBtn')?.addEventListener('click', () => {
    void fetch('/api/hash-backfill/cancel', { method: 'POST' }).then(() => {
      setRunning(false);
      stopPolling();
      updateProgress(0, '');
    });
  });

  sseSubscribe('hash_backfill.progress', (data: unknown) => {
    const d = data as { percent?: number; processed?: number; total?: number };
    setRunning(true);
    updateProgress(d.percent ?? 0, `${d.processed ?? 0} / ${d.total ?? 0}`);
    stopPolling();
  });

  sseSubscribe('hash_backfill.complete', () => {
    setRunning(false);
    stopPolling();
    updateProgress(100, 'Complete');
  });

  void fetchStatus();
}
