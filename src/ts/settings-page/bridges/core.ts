import { loadConfig, loadTomlConfig, loadLegacyMigrationStatus, runLegacyMigration, populateForm, collectForm } from '../config-form';
import { saveSettings, saveJsonDirect, saveTomlDirect } from '../save';
import {
  onLanToggle,
  updateLanBadge,
  togglePinVisibilitySetting,
  toggleRestartTokenVisibilitySetting,
  updatePinSourceNotice,
} from '../security-ui';
import {
  quickLockFromSettings,
  waitForServerBack,
  restartServerFromSettings,
  switchProfileFromSettings,
  calcRfsWait,
} from '../security-actions';
import { loadServerStatus, showDbPathChanger, browseDbPath, applyDbPathChange } from '../server-status';
import { loadMcpToolsPanel } from '../mcp-tools-panel';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

interface ApiEnvelope {
  ok?: boolean;
  error?: string;
  data?: unknown;
}

/** POST a maintenance endpoint, treating an HTTP error or `ok: false` body as a failure. */
async function postMaintenance<T>(path: string): Promise<T | undefined> {
  const resp = await fetch(path, { method: 'POST', headers: XHR_HEADERS });
  const json = (await resp.json().catch(() => null)) as ApiEnvelope | null;
  if (!resp.ok || json?.ok === false) {
    throw new Error(json?.error ?? `HTTP ${resp.status}`);
  }
  return json?.data as T | undefined;
}

interface VacuumResult {
  size_before_mb: number;
  size_after_mb: number;
  saved_mb: number;
}

function errorText(e: unknown): string {
  const raw = e instanceof Error ? e.message : String(e);
  if (raw === 'database_locked') return 'DB がロックされています。時間をおいて再試行してください';
  return raw;
}

export function createSettingsCoreBridgeSection() {
  return {
    loadConfig,
    populateForm,
    collectForm,
    saveSettings,
    saveJsonDirect,
    saveTomlDirect,
    loadTomlConfig,
    loadLegacyMigrationStatus,
    runLegacyMigration,
    onLanToggle,
    updateLanBadge,
    togglePinVisibilitySetting,
    toggleRestartTokenVisibilitySetting,
    updatePinSourceNotice,
    quickLockFromSettings,
    waitForServerBack,
    restartServerFromSettings,
    switchProfileFromSettings,
    calcRfsWait,
    loadServerStatus,
    showDbPathChanger,
    browseDbPath,
    applyDbPathChange,
    loadMcpTools() {
      const container = document.getElementById('mcpToolsPanel');
      if (container) void loadMcpToolsPanel(container);
    },

    async loadDbStats() {
      const panel = document.getElementById('dbStatsPanel');
      if (!panel) return;
      try {
        const resp = await fetch('/api/maintenance/db-stats');
        const json = await resp.json();
        const d = json.data || json;
        // Build stats display using safe DOM methods (no innerHTML)
        panel.textContent = '';
        const line1 = document.createElement('div');
        line1.textContent = `サイズ: `;
        const strong = document.createElement('strong');
        strong.textContent = `${d.size_mb} MB`;
        line1.appendChild(strong);
        const line2 = document.createElement('div');
        line2.textContent = `ページ数: ${d.page_count.toLocaleString()} / 空きページ: ${d.freelist_count.toLocaleString()} (${Math.round(d.free_ratio * 100)}%)`;
        panel.appendChild(line1);
        panel.appendChild(line2);
      } catch {
        if (panel) panel.textContent = '取得失敗';
      }
    },

    async runVacuum() {
      const btn = document.getElementById('vacuumBtn') as HTMLButtonElement | null;
      const result = document.getElementById('vacuumResult');
      if (btn) { btn.disabled = true; btn.textContent = '実行中...'; }
      try {
        const d = await postMaintenance<VacuumResult>('/api/maintenance/vacuum');
        if (result && d) {
          const saved = d.saved_mb > 0 ? `-${d.saved_mb} MB` : '変化なし';
          result.textContent = `完了: ${d.size_before_mb} MB → ${d.size_after_mb} MB (${saved})`;
          result.style.color = '#16a34a';
        }
      } catch (e) {
        if (result) { result.textContent = `失敗: ${errorText(e)}`; result.style.color = '#b91c1c'; }
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'VACUUM 実行'; }
      }
    },

    async runAnalyze() {
      const btn = document.getElementById('analyzeBtn') as HTMLButtonElement | null;
      const result = document.getElementById('analyzeResult');
      if (btn) { btn.disabled = true; btn.textContent = '実行中...'; }
      try {
        await postMaintenance('/api/maintenance/analyze');
        if (result) { result.textContent = '完了'; result.style.color = '#16a34a'; }
      } catch (e) {
        if (result) { result.textContent = `失敗: ${errorText(e)}`; result.style.color = '#b91c1c'; }
      } finally {
        if (btn) { btn.disabled = false; btn.textContent = 'ANALYZE 実行'; }
      }
    },
  };
}
