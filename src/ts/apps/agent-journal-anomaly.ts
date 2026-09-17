/**
 * Agent Journal — Anomaly Detection section.
 * Polls GET /api/agent/anomaly and GET /api/agent/anomaly/alerts every 30s.
 */

interface AnomalyStatus {
  anomaly_detected: boolean;
  alert_count: number;
}

interface AnomalyAlert {
  id: string;
  type: string;
  description: string;
  severity: string;
  timestamp: string;
}

const ANOMALY_POLL_INTERVAL_MS = 30_000;
let anomalyTimer: ReturnType<typeof setInterval> | null = null;

function escHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function tStr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

function renderAnomalyAlerts(content: HTMLElement, alerts: AnomalyAlert[]): void {
  if (alerts.length === 0) {
    content.innerHTML = `<div class="aj-empty" data-i18n="agent_journal.anomaly_no_alerts">${tStr('agent_journal.anomaly_no_alerts', 'No anomalies detected')}</div>`;
    return;
  }
  content.innerHTML = alerts
    .map(
      (a) =>
        `<div class="aj-anomaly-item">
          <span class="aj-tool-name">[${escHtml(a.severity)}] ${escHtml(a.type)}</span>
          <span>${escHtml(a.description)}</span>
          <span class="aj-time">${new Date(a.timestamp).toLocaleTimeString()}</span>
        </div>`,
    )
    .join('');
}

export async function loadAnomaly(): Promise<void> {
  const section = document.getElementById('ajAnomalySection');
  const content = document.getElementById('ajAnomalyContent');
  if (!section || !content) return;
  try {
    const [statusRes, alertsRes] = await Promise.all([
      fetch('/api/agent/anomaly'),
      fetch('/api/agent/anomaly/alerts'),
    ]);
    if (!statusRes.ok || !alertsRes.ok) return;
    const status = (await statusRes.json()) as AnomalyStatus;
    const alerts = (await alertsRes.json()) as AnomalyAlert[];
    section.style.display = status.anomaly_detected || alerts.length > 0 ? '' : 'none';
    renderAnomalyAlerts(content, alerts);
  } catch { /* ignore */ }
}

export function initAnomaly(): void {
  document.getElementById('ajAnomalyResetBtn')?.addEventListener('click', () => {
    void fetch('/api/agent/anomaly/reset', { method: 'POST' }).then(() => loadAnomaly());
  });
  void loadAnomaly();
  anomalyTimer = setInterval(() => void loadAnomaly(), ANOMALY_POLL_INTERVAL_MS);
}
