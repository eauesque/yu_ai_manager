// agent-memory-page — Agent Memory dashboard (TypeScript port of agent_memory.js)

import { amFetch, makeCell, makeRow, makeTable, setText } from './dom';

// vis.js is loaded via vendor <script> tag before this module
interface VisNetwork {
  destroy(): void;
}
interface VisLibrary {
  Network: new (container: HTMLElement, data: object, options: object) => VisNetwork;
  DataSet: new <T>(items: T[]) => object;
}

// ---- Offline banner ----
const offlineBanner = document.getElementById('amOfflineBanner') as HTMLElement;

function setOffline(errOrFalse: false | { status?: number; message?: string } | Error): void {
  if (errOrFalse === false) {
    offlineBanner.hidden = true;
    offlineBanner.textContent = '';
    return;
  }
  const status = typeof errOrFalse === 'object' && 'status' in errOrFalse ? errOrFalse.status : null;
  let msg: string;
  if (status === 401 || status === 403) {
    msg = '⚠ agentmemory API 認証エラー（API キーを確認してください）';
  } else if (status === 404) {
    msg = '⚠ agentmemory エンドポイントが見つかりません（バージョン不一致?）';
  } else {
    msg = '⚠ agentmemory サーバーに接続できません（localhost:3111 停止中?）';
  }
  offlineBanner.textContent = msg;
  offlineBanner.hidden = false;
}

// ---- Polling (generation-counter pattern) ----
let pollActive = false;
let pollTimerId: ReturnType<typeof setTimeout> | null = null;
let pollGen = 0;

function startPolling(fn: () => Promise<void>, delayMs: number): void {
  stopPolling();
  pollActive = true;
  const myGen = ++pollGen;
  (function arm() {
    pollTimerId = setTimeout(async () => {
      if (!pollActive || pollGen !== myGen) return;
      try { await fn(); } catch { /* network error — keep looping */ }
      finally { if (pollActive && pollGen === myGen) arm(); }
    }, delayMs);
  })();
}

function stopPolling(): void {
  pollActive = false;
  if (pollTimerId !== null) { clearTimeout(pollTimerId); pollTimerId = null; }
}

// ---- Tab switching ----
let currentAbort: AbortController | null = null;

function initTabs(): void {
  const btns = document.querySelectorAll<HTMLButtonElement>('.am-tab-btn');
  const panels = document.querySelectorAll<HTMLElement>('.am-tab-panel');

  btns.forEach(btn => {
    btn.addEventListener('click', () => {
      if (btn.classList.contains('active')) return;
      if (currentAbort) { currentAbort.abort(); currentAbort = null; }
      btns.forEach(b => { b.classList.remove('active'); b.setAttribute('aria-selected', 'false'); });
      panels.forEach(p => { p.hidden = true; });
      btn.classList.add('active');
      btn.setAttribute('aria-selected', 'true');
      const panel = document.getElementById(btn.dataset['tab'] ?? '');
      if (panel) panel.hidden = false;
      loadTab(btn.dataset['tab'] ?? '');
    });
  });
}

function loadTab(tabId: string): void {
  currentAbort = new AbortController();
  switch (tabId) {
    case 'amTabHealth':   void loadHealth(currentAbort.signal); break;
    case 'amTabSessions': void loadSessions(currentAbort.signal); break;
    case 'amTabMemories': void loadMemories(currentAbort.signal); break;
    case 'amTabGraph':    void loadGraph(currentAbort.signal); break;
    case 'amTabAudit':    void loadAudit(currentAbort.signal); break;
  }
}

// ---- Visibility change ----
document.addEventListener('visibilitychange', () => {
  if (document.hidden) {
    stopPolling();
    if (currentAbort) { currentAbort.abort(); currentAbort = null; }
  } else {
    startLivezPoll();
  }
});

// ---- /livez 30s poll ----
async function checkLivez(): Promise<void> {
  try {
    const res = await amFetch('/api/agentmemory-dash/livez');
    if (!res.ok) {
      const err = Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
      throw err;
    }
    setOffline(false);
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    setOffline(err as Error & { status?: number });
  }
}

function startLivezPoll(): void {
  startPolling(checkLivez, 30_000);
}

// ---- Health tab ----
async function loadHealth(signal: AbortSignal): Promise<void> {
  try {
    const [healthRes, profileRes] = await Promise.all([
      amFetch('/api/agentmemory-dash/health', { signal }),
      amFetch('/api/agentmemory-dash/profile', { signal }),
    ]);
    if (!healthRes.ok) {
      throw Object.assign(new Error(`HTTP ${healthRes.status}`), { status: healthRes.status });
    }
    const health = await healthRes.json() as Record<string, unknown>;
    renderHealthCard(health);
    setOffline(false);
    if (profileRes.ok) {
      const profile = await profileRes.json() as Record<string, unknown>;
      renderProfileCard(profile);
    }
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    setOffline(err as Error & { status?: number });
  }
}

function formatUptimeSecs(s: number): string {
  s = Math.floor(s);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  return `${h}h ${m}m ${sec}s`;
}

function renderHealthCard(h: Record<string, unknown>): void {
  const statusEl = document.getElementById('amHealthStatus')!;
  const isUp = h['status'] === 'ok' || h['status'] === 'healthy' || h['healthy'] === true;
  statusEl.textContent = isUp ? '✅ 稼働中' : '❌ 停止';
  statusEl.className = 'am-status-row ' + (isUp ? 'ok' : 'error');

  const version = (h['version'] ?? h['agentmemory_version'] ?? '') as string;
  const healthObj = h['health'] as Record<string, unknown> | undefined;
  const workers = healthObj?.['workers'] as unknown[] | undefined;
  const uptimeSecs = (healthObj?.['uptimeSeconds'] ?? (typeof h['uptime'] === 'number' ? h['uptime'] : null)) as number | null;
  const workerInfo = (workers?.[0] ?? {}) as Record<string, unknown>;

  if (version) setText('amHealthVersion', `バージョン: ${version}`);
  if (uptimeSecs != null) setText('amHealthUptime', `稼働時間: ${formatUptimeSecs(uptimeSecs)}`);

  const statsEl = document.getElementById('amHealthStats')!;
  statsEl.textContent = '';
  const entries: [string, unknown][] = [
    ['Workers',         workers?.length ?? '—'],
    ['Function 数',     workerInfo['function_count'] ?? '—'],
    ['Circuit Breaker', (h['circuitBreaker'] as Record<string, unknown> | undefined)?.['state'] ?? '—'],
  ];
  statsEl.appendChild(makeTable(['種別', '値'], entries.map(([k, v]) => makeRow(k, v))));
}

function renderProfileCard(p: Record<string, unknown>): void {
  const el = document.getElementById('amHealthProfile')!;
  el.textContent = '';
  const name = String(p['project_name'] ?? p['name'] ?? '');
  const desc = String(p['description'] ?? '');
  if (name) {
    const strong = document.createElement('strong');
    strong.textContent = name;
    el.appendChild(strong);
    el.appendChild(document.createElement('br'));
  }
  if (desc) {
    const span = document.createElement('span');
    span.textContent = desc;
    el.appendChild(span);
  }
  if (!name && !desc) el.textContent = '—';
}

// ---- Sessions tab ----
async function loadSessions(signal: AbortSignal): Promise<void> {
  const el = document.getElementById('amSessionsContent')!;
  el.textContent = '';
  try {
    const res = await amFetch('/api/agentmemory-dash/sessions', { signal });
    if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
    const data = await res.json() as unknown[] | { sessions?: unknown[] };
    const sessions = (Array.isArray(data) ? data : ((data as { sessions?: unknown[] }).sessions ?? [])) as Record<string, unknown>[];
    renderSessions(el, sessions.slice(0, 50), sessions.length);
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = `読み込みエラー: ${(err as Error).message}`;
    el.appendChild(p);
  }
}

function renderSessions(container: HTMLElement, sessions: Record<string, unknown>[], total: number): void {
  if (!sessions.length) {
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = 'セッションがありません';
    container.appendChild(p);
    return;
  }
  if (total > 50) {
    const note = document.createElement('p');
    note.className = 'am-note';
    note.textContent = `上位 50 件を表示（全 ${total} 件）`;
    container.appendChild(note);
  }
  const rows = sessions.map(s => makeRow(
    s['session_id'] ?? s['id'] ?? '—',
    s['startedAt'] ?? s['created_at'] ?? s['timestamp'] ?? '—',
    String(s['observationCount'] ?? s['observation_count'] ?? s['observations'] ?? '—'),
  ));
  container.appendChild(makeTable(['Session ID', '日時', '観察件数'], rows));
}

// ---- Memories tab ----
let _memoriesCache: Record<string, unknown>[] = [];

async function loadMemories(signal: AbortSignal): Promise<void> {
  const el = document.getElementById('amMemoriesContent')!;
  el.textContent = '';
  try {
    const res = await amFetch('/api/agentmemory-dash/memories', { signal });
    if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
    const data = await res.json() as unknown[] | { memories?: unknown[] };
    _memoriesCache = (Array.isArray(data) ? data : ((data as { memories?: unknown[] }).memories ?? [])) as Record<string, unknown>[];
    applyMemoriesFilter();
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = `読み込みエラー: ${(err as Error).message}`;
    el.appendChild(p);
  }
}

function applyMemoriesFilter(): void {
  const el = document.getElementById('amMemoriesContent')!;
  el.textContent = '';
  const typeFilter = (document.getElementById('amMemoriesFilter') as HTMLSelectElement | null)?.value ?? '';
  const textFilter = ((document.getElementById('amMemoriesSearch') as HTMLInputElement | null)?.value ?? '').toLowerCase();

  let items = _memoriesCache;
  if (typeFilter) items = items.filter(m => (m['memory_type'] ?? m['type'] ?? '') === typeFilter);
  if (textFilter) items = items.filter(m => String(m['content'] ?? m['text'] ?? '').toLowerCase().includes(textFilter));

  const shown = items.slice(0, 200);
  if (items.length > 200) {
    const note = document.createElement('p');
    note.className = 'am-note';
    note.textContent = `上位 200 件を表示（フィルター後 ${items.length} 件）`;
    el.appendChild(note);
  }
  if (!shown.length) {
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = 'メモリがありません';
    el.appendChild(p);
    return;
  }
  const rows = shown.map(m => makeRow(
    m['memory_type'] ?? m['type'] ?? '—',
    m['content'] ?? m['text'] ?? '—',
    m['created_at'] ?? m['timestamp'] ?? '—',
  ));
  el.appendChild(makeTable(['Type', 'Content', '日時'], rows));
}

function wireMemoriesFilter(): void {
  document.getElementById('amMemoriesFilter')?.addEventListener('change', applyMemoriesFilter);
  document.getElementById('amMemoriesSearch')?.addEventListener('input', applyMemoriesFilter);
}

// ---- Audit tab ----
async function loadAudit(signal: AbortSignal): Promise<void> {
  const el = document.getElementById('amAuditContent')!;
  el.textContent = '';
  try {
    const res = await amFetch('/api/agentmemory-dash/audit', { signal });
    if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
    const data = await res.json() as unknown[] | { audit?: unknown[]; records?: unknown[] };
    const entries = (Array.isArray(data) ? data : ((data as { audit?: unknown[]; records?: unknown[] }).audit ?? (data as { records?: unknown[] }).records ?? [])) as Record<string, unknown>[];
    renderAudit(el, entries.slice(0, 100));
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = `読み込みエラー: ${(err as Error).message}`;
    el.appendChild(p);
  }
}

function renderAudit(container: HTMLElement, entries: Record<string, unknown>[]): void {
  if (!entries.length) {
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = '監査ログがありません';
    container.appendChild(p);
    return;
  }
  const rows = entries.map(e => makeRow(
    e['timestamp'] ?? e['created_at'] ?? '—',
    e['operation'] ?? e['op'] ?? '—',
    e['target'] ?? '—',
    e['status'] ?? '—',
  ));
  container.appendChild(makeTable(['日時', 'Operation', 'Target', 'Status'], rows));
}

// ---- Graph tab ----
// vis-network uses innerHTML internally; yu CSP has trusted-types but NOT
// require-trusted-types-for 'script', so vis.js innerHTML calls are permitted.
let _visNetwork: VisNetwork | null = null;

async function loadGraph(signal: AbortSignal): Promise<void> {
  const statsEl = document.getElementById('amGraphStats')!;
  statsEl.textContent = '';
  const container = document.getElementById('amGraphContainer') as HTMLElement;
  container.style.display = 'none';
  const placeholder = document.getElementById('amGraphPlaceholder')!;
  const truncNote = document.getElementById('amGraphTruncNote')!;
  placeholder.hidden = true;
  truncNote.hidden = true;

  try {
    const statsRes = await amFetch('/api/agentmemory-dash/graph/stats', { signal });
    if (statsRes.ok) {
      const stats = await statsRes.json() as Record<string, unknown>;
      renderGraphStats(statsEl, stats);
    }

    const queryRes = await amFetch('/api/agentmemory-dash/graph/query', {
      method: 'POST',
      signal,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ query: '*', limit: 151 }),
    });
    if (!queryRes.ok) throw Object.assign(new Error(`HTTP ${queryRes.status}`), { status: queryRes.status });
    const data = await queryRes.json() as { nodes?: Record<string, unknown>[]; edges?: Record<string, unknown>[] };

    const rawNodes = data['nodes'] ?? [];
    const rawEdges = data['edges'] ?? [];

    if (!rawNodes.length) { placeholder.hidden = false; return; }
    if (rawNodes.length > 150) truncNote.hidden = false;

    const nodes = rawNodes.slice(0, 150).map(n => ({
      id: n['id'],
      label: String(n['name'] ?? n['label'] ?? String(n['id'])),
      title: makeNodeTooltip(n),
    }));
    const edges = rawEdges.map((e, i) => ({
      id: i,
      from: e['source'] ?? e['from'],
      to: e['target'] ?? e['to'],
      label: String(e['type'] ?? e['label'] ?? ''),
    }));

    if (_visNetwork) { _visNetwork.destroy(); _visNetwork = null; }
    container.style.display = '';

    const visLib = (globalThis as Record<string, unknown>)['vis'] as VisLibrary | undefined;
    if (!visLib) {
      const p = document.createElement('p');
      p.className = 'am-placeholder';
      p.textContent = 'vis.js が読み込まれていません';
      statsEl.after(p);
      return;
    }
    _visNetwork = new visLib.Network(
      container,
      { nodes: new visLib.DataSet(nodes), edges: new visLib.DataSet(edges) },
      {
        layout: { improvedLayout: true },
        physics: { stabilization: { iterations: 80 } },
        interaction: { hover: true, tooltipDelay: 200 },
      },
    );
  } catch (err) {
    if ((err as Error).name === 'AbortError') return;
    const p = document.createElement('p');
    p.className = 'am-placeholder';
    p.textContent = `読み込みエラー: ${(err as Error).message}`;
    statsEl.appendChild(p);
  }
}

function renderGraphStats(container: HTMLElement, stats: Record<string, unknown>): void {
  const rows: [string, unknown][] = [
    ['ノード数', stats['totalNodes'] ?? stats['node_count'] ?? stats['nodes'] ?? '—'],
    ['エッジ数', stats['totalEdges'] ?? stats['edge_count'] ?? stats['edges'] ?? '—'],
  ];
  container.appendChild(makeTable(['項目', '件数'], rows.map(([k, v]) => makeRow(k, v))));
}

// vis.js node tooltip — DOM element (textContent only, no innerHTML)
function makeNodeTooltip(node: Record<string, unknown>): HTMLElement {
  const div = document.createElement('div');
  div.style.cssText = 'max-width:280px;padding:6px 8px;font-size:13px;';
  const label = node['name'] ?? node['label'];
  if (label) {
    const strong = document.createElement('strong');
    strong.textContent = String(label);
    div.appendChild(strong);
    div.appendChild(document.createElement('br'));
  }
  if (node['type']) {
    const span = document.createElement('span');
    span.textContent = `Type: ${String(node['type'])}`;
    div.appendChild(span);
    div.appendChild(document.createElement('br'));
  }
  if (node['id'] !== undefined) {
    const span = document.createElement('span');
    span.textContent = `ID: ${String(node['id'])}`;
    div.appendChild(span);
  }
  return div;
}

// ---- Refresh button wiring ----
function wireRefreshButtons(): void {
  document.getElementById('amHealthRefresh')?.addEventListener('click', () => {
    currentAbort = new AbortController();
    void loadHealth(currentAbort.signal);
  });
  document.getElementById('amSessionsRefresh')?.addEventListener('click', () => {
    currentAbort = new AbortController();
    void loadSessions(currentAbort.signal);
  });
  document.getElementById('amMemoriesRefresh')?.addEventListener('click', () => {
    _memoriesCache = [];
    currentAbort = new AbortController();
    void loadMemories(currentAbort.signal);
  });
  document.getElementById('amGraphRefresh')?.addEventListener('click', () => {
    currentAbort = new AbortController();
    void loadGraph(currentAbort.signal);
  });
  document.getElementById('amAuditRefresh')?.addEventListener('click', () => {
    currentAbort = new AbortController();
    void loadAudit(currentAbort.signal);
  });
}

// ---- Entry point ----
document.addEventListener('DOMContentLoaded', () => {
  initTabs();
  wireRefreshButtons();
  wireMemoriesFilter();
  loadTab('amTabHealth');
  startLivezPoll();
});
