import {
  COUNT_ID,
  HISTORY_COUNT_ID,
  HISTORY_LIST_ID,
  HISTORY_PANEL_ID,
  HISTORY_TAB_BTN_ID,
  HISTORY_ROW_CLASS,
  HISTORY_ROW_COPY_CLASS,
  LATEST_PANEL_ID,
  LATEST_TAB_BTN_ID,
  LAUNCHER_ID,
  MODAL_ID,
  REPORTER_STYLE_ID,
  STATUS_ID,
  SUMMARY_ID,
  TEXT_ID,
  COPY_ALL_BTN_ID,
  CLEAR_HISTORY_BTN_ID,
  buildCaughtBundle,
  copyText,
  reporterState,
  t,
} from './error-reporter-shared';

export function setStatus(message: string): void {
  const el = document.getElementById(STATUS_ID);
  if (el) el.textContent = message;
}

export function renderModalBundle(): void {
  const bundle = reporterState.latestBundle;
  const textEl = document.getElementById(TEXT_ID) as HTMLTextAreaElement | null;
  const summaryEl = document.getElementById(SUMMARY_ID);
  if (!textEl || !summaryEl) return;
  if (!bundle) {
    textEl.value = '';
    summaryEl.textContent = t('error_report.empty', 'まだエラーレポートはありません。');
    return;
  }
  const err = (bundle.error || {}) as Record<string, unknown>;
  const req = (bundle.request || {}) as Record<string, unknown>;
  summaryEl.textContent = [
    String(err.kind || ''),
    String(req.method || ''),
    String(req.url || req.path || ''),
    String(err.message || ''),
  ].filter(Boolean).join(' | ');
  textEl.value = JSON.stringify(bundle, null, 2);
}

/** Update launcher badge and history count. Call after any state mutation. */
export function updateHistoryBadge(): void {
  ensureLauncher(); // safe to call even if DOM is not yet initialized
  // captureBundle() always pushes to caughtErrors before setting latestBundle, so in
  // steady state the two are never disjoint. But "クリア" (clear history) empties
  // caughtErrors while leaving latestBundle intact — use max() so the launcher stays
  // visible (and the latest error still reachable) instead of hiding at count 0.
  const count = Math.max(reporterState.caughtErrors.length, reporterState.latestBundle ? 1 : 0);
  const launcher = document.getElementById(LAUNCHER_ID);
  if (launcher) {
    if (count > 0) launcher.removeAttribute('hidden');
    else launcher.setAttribute('hidden', '');
  }
  const badge = document.getElementById(COUNT_ID);
  if (badge) badge.textContent = String(count);
  const histCount = document.getElementById(HISTORY_COUNT_ID);
  if (histCount) histCount.textContent = String(reporterState.caughtErrors.length);
}

export function setLatestBundle(bundle: Record<string, unknown>): void {
  reporterState.latestBundle = bundle;
  renderModalBundle();
  updateHistoryBadge(); // recompute full count (replaces hardcoded '1')
}

function ensureStyle(): void {
  if (document.getElementById(REPORTER_STYLE_ID)) return;
  const style = document.createElement('style');
  style.id = REPORTER_STYLE_ID;
  style.textContent = `
    #${LAUNCHER_ID}{position:fixed;right:16px;bottom:16px;z-index:9998;border:1px solid rgba(255,255,255,.2);background:#8b1e1e;color:#fff;border-radius:999px;padding:10px 14px;font-size:12px;box-shadow:0 8px 24px rgba(0,0,0,.35)}
    #${LAUNCHER_ID}[hidden]{display:none}
    #${LAUNCHER_ID} .count{display:inline-block;min-width:18px;height:18px;line-height:18px;text-align:center;background:#fff;color:#8b1e1e;border-radius:999px;margin-left:8px;font-weight:700}
    #${MODAL_ID}{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.58);display:none;align-items:center;justify-content:center;padding:24px}
    #${MODAL_ID}.open{display:flex}
    #${MODAL_ID} .panel{width:min(920px,100%);max-height:85vh;overflow:auto;background:#16181d;color:#e7e7e7;border:1px solid rgba(255,255,255,.12);border-radius:16px;padding:18px 18px 16px;box-shadow:0 24px 80px rgba(0,0,0,.45)}
    #${MODAL_ID} .title{font-size:18px;font-weight:700;margin:0 0 10px}
    #${MODAL_ID} .tab-bar{display:flex;gap:4px;margin-bottom:12px;border-bottom:1px solid rgba(255,255,255,.1);padding-bottom:4px}
    #${MODAL_ID} .tab-bar button{border:none;background:transparent;color:#9aa3b2;border-radius:8px 8px 0 0;padding:6px 12px;font-size:12px;cursor:pointer}
    #${MODAL_ID} .tab-bar button[aria-selected="true"]{background:#242932;color:#fff;font-weight:600}
    #${MODAL_ID} .summary{font-size:12px;color:#aeb4bf;margin-bottom:10px;word-break:break-all}
    #${MODAL_ID} textarea{width:100%;min-height:320px;background:#0f1115;color:#dfe6ef;border:1px solid rgba(255,255,255,.12);border-radius:10px;padding:12px;font:12px/1.45 ui-monospace,SFMono-Regular,Consolas,monospace}
    #${MODAL_ID} .actions{display:flex;gap:10px;flex-wrap:wrap;margin-top:12px}
    #${MODAL_ID} button,#${MODAL_ID} a.action{border:1px solid rgba(255,255,255,.18);background:#242932;color:#fff;border-radius:10px;padding:9px 12px;font-size:12px;text-decoration:none;cursor:pointer}
    #${MODAL_ID} button:disabled{opacity:.4;cursor:not-allowed}
    #${MODAL_ID} .status{font-size:11px;color:#9aa3b2;margin-top:8px;min-height:16px}
    #${MODAL_ID} .history-actions{display:flex;gap:8px;margin-bottom:10px}
    #${MODAL_ID} .${HISTORY_ROW_CLASS}{display:flex;align-items:baseline;gap:8px;padding:6px 0;border-bottom:1px solid rgba(255,255,255,.06);font-size:11px}
    #${MODAL_ID} .${HISTORY_ROW_CLASS} .ts{color:#9aa3b2;white-space:nowrap;flex-shrink:0}
    #${MODAL_ID} .${HISTORY_ROW_CLASS} .comp{color:#e67e22;white-space:nowrap;flex-shrink:0;font-family:ui-monospace,monospace}
    #${MODAL_ID} .${HISTORY_ROW_CLASS} .msg{flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:#dfe6ef}
    #${MODAL_ID} .${HISTORY_ROW_COPY_CLASS}{flex-shrink:0;border:1px solid rgba(255,255,255,.18);background:#242932;color:#fff;border-radius:6px;padding:3px 8px;font-size:10px;cursor:pointer}
    #${HISTORY_PANEL_ID}[hidden]{display:none}
    #${LATEST_PANEL_ID}[hidden]{display:none}
  `;
  document.head.appendChild(style);
}

/** Render the history list in reverse-chronological order (non-destructive). */
export function renderHistoryList(): void {
  const listEl = document.getElementById(HISTORY_LIST_ID);
  if (!listEl) return;
  const items = [...reporterState.caughtErrors].reverse();
  if (items.length === 0) {
    listEl.textContent = t('error_report.history_empty', 'このセッションでエラーは記録されていません。');
    return;
  }
  listEl.innerHTML = '';
  for (const item of items) {
    const timeStr = new Date(item.ts).toLocaleTimeString('ja-JP', { hour: '2-digit', minute: '2-digit', second: '2-digit' });
    const row = document.createElement('div');
    row.className = HISTORY_ROW_CLASS;

    const tsEl = document.createElement('span');
    tsEl.className = 'ts';
    tsEl.textContent = timeStr;

    const compEl = document.createElement('span');
    compEl.className = 'comp';
    compEl.textContent = item.component;

    const msgEl = document.createElement('span');
    msgEl.className = 'msg';
    msgEl.textContent = item.message.slice(0, 80);

    const copyBtn = document.createElement('button');
    copyBtn.type = 'button';
    copyBtn.className = HISTORY_ROW_COPY_CLASS;
    copyBtn.textContent = 'JSON';
    copyBtn.addEventListener('click', () => {
      void copyText(JSON.stringify(buildCaughtBundle(item), null, 2))
        .then(() => setStatus(t('error_report.copied', 'Bundle JSONをコピーしました。')))
        .catch(() => setStatus(t('error_report.copy_failed', 'コピーに失敗しました。')));
    });

    row.appendChild(tsEl);
    row.appendChild(compEl);
    row.appendChild(msgEl);
    row.appendChild(copyBtn);
    listEl.appendChild(row);
  }
}

function switchTab(tab: 'latest' | 'history'): void {
  const latestBtn = document.getElementById(LATEST_TAB_BTN_ID);
  const histBtn = document.getElementById(HISTORY_TAB_BTN_ID);
  const latestPanel = document.getElementById(LATEST_PANEL_ID);
  const histPanel = document.getElementById(HISTORY_PANEL_ID);
  if (!latestBtn || !histBtn || !latestPanel || !histPanel) return;

  if (tab === 'latest') {
    latestBtn.setAttribute('aria-selected', 'true');
    histBtn.setAttribute('aria-selected', 'false');
    latestPanel.removeAttribute('hidden');
    histPanel.setAttribute('hidden', '');
  } else {
    latestBtn.setAttribute('aria-selected', 'false');
    histBtn.setAttribute('aria-selected', 'true');
    latestPanel.setAttribute('hidden', '');
    histPanel.removeAttribute('hidden');
    renderHistoryList();
  }
}

export function ensureLauncher(): void {
  if (reporterState.launcherReady) return;
  ensureStyle();
  const launcher = document.createElement('button');
  launcher.id = LAUNCHER_ID;
  launcher.hidden = true;
  launcher.type = 'button';
  launcher.innerHTML = `${t('error_report.launcher', 'エラー報告')} <span class="count" id="${COUNT_ID}">0</span>`;
  launcher.addEventListener('click', () => openErrorReportModal());
  document.body.appendChild(launcher);

  const modal = document.createElement('div');
  modal.id = MODAL_ID;
  modal.innerHTML = `
    <div class="panel" role="dialog" aria-modal="true" aria-labelledby="${MODAL_ID}Title">
      <div class="title" id="${MODAL_ID}Title">${t('error_report.title', 'エラーレポート')}</div>

      <div class="tab-bar" role="tablist">
        <button id="${LATEST_TAB_BTN_ID}" role="tab" aria-selected="true" type="button">
          ${t('error_report.latest_tab', '最新エラー')}
        </button>
        <button id="${HISTORY_TAB_BTN_ID}" role="tab" aria-selected="false" type="button" disabled>
          ${t('error_report.history_tab', 'セッション履歴')} (<span id="${HISTORY_COUNT_ID}">0</span>)
        </button>
      </div>

      <div id="${LATEST_PANEL_ID}" role="tabpanel">
        <div class="summary" id="${SUMMARY_ID}"></div>
        <textarea id="${TEXT_ID}" readonly spellcheck="false"></textarea>
        <div class="actions">
          <button type="button" id="${MODAL_ID}Copy" disabled>${t('error_report.copy', 'Bundle JSONをコピー')}</button>
          <button type="button" id="${MODAL_ID}Download" disabled>${t('error_report.download', 'Bundleをダウンロード')}</button>
          <a class="action" id="${MODAL_ID}Github" target="_blank" rel="noopener noreferrer">${t('error_report.github', 'GitHub Issueを開く')}</a>
          <button type="button" id="${MODAL_ID}Close" disabled>${t('common.close', '閉じる')}</button>
        </div>
        <div class="status" id="${STATUS_ID}"></div>
      </div>

      <div id="${HISTORY_PANEL_ID}" role="tabpanel" hidden>
        <div class="history-actions">
          <button type="button" id="${COPY_ALL_BTN_ID}" disabled>${t('error_report.copy_all', '全件コピー')}</button>
          <button type="button" id="${CLEAR_HISTORY_BTN_ID}" disabled>${t('error_report.clear_history', 'クリア')}</button>
        </div>
        <div id="${HISTORY_LIST_ID}"></div>
      </div>
    </div>
  `;
  modal.addEventListener('click', (e) => {
    if (e.target === modal) closeErrorReportModal();
  });

  // Tab switching (history tab is disabled until actionsReady; click still allowed for latest)
  document.body.appendChild(modal);

  const latestTabBtn = document.getElementById(LATEST_TAB_BTN_ID);
  const histTabBtn = document.getElementById(HISTORY_TAB_BTN_ID);
  latestTabBtn?.addEventListener('click', () => switchTab('latest'));
  histTabBtn?.addEventListener('click', () => {
    if (!reporterState.actionsReady) return;
    switchTab('history');
  });

  reporterState.launcherReady = true;
  renderModalBundle();
}

export function bindLauncherActions(
  copyBundle: () => Promise<void>,
  downloadBundle: () => Promise<void>,
  buildGithubUrl: () => string,
): void {
  // Idempotent: skip if already bound
  if (reporterState.actionsReady) return;

  document.getElementById(`${MODAL_ID}Close`)?.addEventListener('click', () => closeErrorReportModal());
  document.getElementById(`${MODAL_ID}Copy`)?.addEventListener('click', () => {
    void copyBundle()
      .then(() => setStatus(t('error_report.copied', 'Bundle JSONをコピーしました。')))
      .catch(() => setStatus(t('error_report.copy_failed', 'Bundle JSONのコピーに失敗しました。')));
  });
  document.getElementById(`${MODAL_ID}Download`)?.addEventListener('click', () => {
    void downloadBundle()
      .then(() => setStatus(t('error_report.download_started', 'Bundle のダウンロードを開始しました。')))
      .catch(() => setStatus(t('error_report.download_failed', 'Bundle のダウンロードに失敗しました。')));
  });
  // Compute the GitHub URL lazily on click so it always reflects the current latestBundle.
  const github = document.getElementById(`${MODAL_ID}Github`) as HTMLAnchorElement | null;
  if (github) {
    github.addEventListener('click', () => { github.href = buildGithubUrl(); });
  }

  // History panel buttons
  document.getElementById(COPY_ALL_BTN_ID)?.addEventListener('click', () => {
    const all = [...reporterState.caughtErrors].reverse().map(buildCaughtBundle);
    void copyText(JSON.stringify(all, null, 2))
      .then(() => setStatus(t('error_report.copy_all_done', '全件 JSON をコピーしました。')))
      .catch(() => setStatus(t('error_report.copy_failed', 'コピーに失敗しました。')));
  });
  document.getElementById(CLEAR_HISTORY_BTN_ID)?.addEventListener('click', () => {
    reporterState.caughtErrors = [];
    renderHistoryList();
    updateHistoryBadge();
    setStatus(t('error_report.cleared', '履歴をクリアしました。'));
  });

  // Enable all buttons now that binding is complete
  const disabledBtns = document.querySelectorAll<HTMLButtonElement>(`#${MODAL_ID} button[disabled], #${MODAL_ID} button:disabled`);
  disabledBtns.forEach(btn => btn.removeAttribute('disabled'));

  reporterState.actionsReady = true;
}

export function openErrorReportModal(tab?: 'latest' | 'history'): void {
  ensureLauncher();
  // Auto-select tab if not specified
  const resolvedTab: 'latest' | 'history' = tab ?? (
    reporterState.latestBundle !== null
      ? 'latest'
      : reporterState.caughtErrors.length > 0
        ? 'history'
        : 'latest'
  );
  switchTab(resolvedTab);
  document.getElementById(MODAL_ID)?.classList.add('open');
}

export function closeErrorReportModal(): void {
  document.getElementById(MODAL_ID)?.classList.remove('open');
}
