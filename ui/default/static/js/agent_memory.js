// agent_memory.js — Agent Memory dashboard

"use strict";

// ---- Fetch utility ----
async function amFetch(path, opts = {}) {
    const headers = { Accept: 'application/json', ...opts.headers };
    const res = await fetch(path, { ...opts, headers });
    return res;
}

// ---- XSS-safe helpers ----
function escapeHtml(str) {
    const d = document.createElement('div');
    d.textContent = String(str ?? '');
    return d.innerHTML;
}

function setText(id, value) {
    const el = document.getElementById(id);
    if (el) el.textContent = String(value ?? '');
}

function makeCell(text) {
    const td = document.createElement('td');
    td.textContent = String(text ?? '—');
    return td;
}

function makeRow(...cells) {
    const tr = document.createElement('tr');
    for (const text of cells) tr.appendChild(makeCell(text));
    return tr;
}

function makeTable(headers, rows) {
    const table = document.createElement('table');
    table.className = 'am-table';

    const thead = table.createTHead();
    const hr = thead.insertRow();
    for (const h of headers) {
        const th = document.createElement('th');
        th.textContent = h;
        hr.appendChild(th);
    }

    const tbody = table.createTBody();
    for (const row of rows) tbody.appendChild(row);
    return table;
}

// ---- Offline banner ----
const offlineBanner = document.getElementById('amOfflineBanner');

function setOffline(errOrFalse) {
    if (!errOrFalse) {
        offlineBanner.hidden = true;
        offlineBanner.textContent = '';
        return;
    }
    const status = typeof errOrFalse === 'object' && errOrFalse.status
        ? errOrFalse.status : null;
    let msg;
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
let pollTimerId = null;
let pollGen = 0;

function startPolling(fn, delayMs) {
    stopPolling();
    pollActive = true;
    const myGen = ++pollGen;
    (function arm() {
        pollTimerId = setTimeout(async () => {
            if (!pollActive || pollGen !== myGen) return;
            try { await fn(); }
            catch (_) { /* network error → keep looping */ }
            finally { if (pollActive && pollGen === myGen) arm(); }
        }, delayMs);
    })();
}

function stopPolling() {
    pollActive = false;
    clearTimeout(pollTimerId);
    pollTimerId = null;
}

// ---- Tab switching ----
let currentAbort = null;

function initTabs() {
    const btns = document.querySelectorAll('.am-tab-btn');
    const panels = document.querySelectorAll('.am-tab-panel');

    btns.forEach(btn => {
        btn.addEventListener('click', () => {
            if (btn.classList.contains('active')) return;

            if (currentAbort) { currentAbort.abort(); currentAbort = null; }

            btns.forEach(b => {
                b.classList.remove('active');
                b.setAttribute('aria-selected', 'false');
            });
            panels.forEach(p => { p.hidden = true; });

            btn.classList.add('active');
            btn.setAttribute('aria-selected', 'true');
            const panel = document.getElementById(btn.dataset.tab);
            if (panel) panel.hidden = false;

            loadTab(btn.dataset.tab);
        });
    });
}

function loadTab(tabId) {
    currentAbort = new AbortController();
    switch (tabId) {
        case 'amTabHealth':   loadHealth(currentAbort.signal); break;
        case 'amTabSessions': loadSessions(currentAbort.signal); break;
        case 'amTabMemories': loadMemories(currentAbort.signal); break;
        case 'amTabGraph':    loadGraph(currentAbort.signal); break;
        case 'amTabAudit':    loadAudit(currentAbort.signal); break;
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
async function checkLivez() {
    try {
        const res = await amFetch('/api/agentmemory-dash/livez');
        if (!res.ok) {
            const err = new Error(`HTTP ${res.status}`);
            err.status = res.status;
            throw err;
        }
        setOffline(false);
    } catch (err) {
        if (err.name === 'AbortError') return;
        setOffline(err);
    }
}

function startLivezPoll() {
    startPolling(checkLivez, 30_000);
}

// ---- Health tab ----
async function loadHealth(signal) {
    try {
        const [healthRes, profileRes] = await Promise.all([
            amFetch('/api/agentmemory-dash/health', { signal }),
            amFetch('/api/agentmemory-dash/profile', { signal }),
        ]);
        if (!healthRes.ok) {
            const err = new Error(`HTTP ${healthRes.status}`);
            err.status = healthRes.status;
            throw err;
        }
        const health = await healthRes.json();
        renderHealthCard(health);
        setOffline(false);

        if (profileRes.ok) {
            const profile = await profileRes.json();
            renderProfileCard(profile);
        }
    } catch (err) {
        if (err.name === 'AbortError') return;
        setOffline(err);
    }
}

function formatUptimeSecs(s) {
    s = Math.floor(s);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${h}h ${m}m ${sec}s`;
}

function renderHealthCard(h) {
    const statusEl = document.getElementById('amHealthStatus');
    const isUp = h.status === 'ok' || h.status === 'healthy' || h.healthy === true;
    statusEl.textContent = isUp ? '✅ 稼働中' : '❌ 停止';
    statusEl.className = 'am-status-row ' + (isUp ? 'ok' : 'error');

    const version = h.version ?? h.agentmemory_version ?? '';
    const uptimeSecs = h.health?.uptimeSeconds ?? (typeof h.uptime === 'number' ? h.uptime : null);
    if (version)    setText('amHealthVersion', `バージョン: ${version}`);
    if (uptimeSecs != null) setText('amHealthUptime', `稼働時間: ${formatUptimeSecs(uptimeSecs)}`);

    const workerInfo = h.health?.workers?.[0] ?? {};
    const statsEl = document.getElementById('amHealthStats');
    statsEl.textContent = '';
    const entries = [
        ['Workers',          h.health?.workers?.length ?? '—'],
        ['Function 数',      workerInfo.function_count ?? '—'],
        ['Circuit Breaker',  h.circuitBreaker?.state   ?? '—'],
    ];
    statsEl.appendChild(makeTable(['種別', '値'],
        entries.map(([k, v]) => makeRow(k, v))));
}

function renderProfileCard(p) {
    const el = document.getElementById('amHealthProfile');
    el.textContent = '';
    const name = p.project_name ?? p.name ?? '';
    const desc = p.description ?? '';
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
async function loadSessions(signal) {
    const el = document.getElementById('amSessionsContent');
    el.textContent = '';
    try {
        const res = await amFetch('/api/agentmemory-dash/sessions', { signal });
        if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
        const data = await res.json();
        const sessions = Array.isArray(data) ? data : (data.sessions ?? []);
        renderSessions(el, sessions.slice(0, 50), sessions.length);
    } catch (err) {
        if (err.name === 'AbortError') return;
        const p = document.createElement('p');
        p.className = 'am-placeholder';
        p.textContent = `読み込みエラー: ${err.message}`;
        el.appendChild(p);
    }
}

function renderSessions(container, sessions, total) {
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
        s.session_id ?? s.id ?? '—',
        s.startedAt ?? s.created_at ?? s.timestamp ?? '—',
        String(s.observationCount ?? s.observation_count ?? s.observations ?? '—'),
    ));
    container.appendChild(makeTable(['Session ID', '日時', '観察件数'], rows));
}

// ---- Memories tab ----
let _memoriesCache = [];

async function loadMemories(signal) {
    const el = document.getElementById('amMemoriesContent');
    el.textContent = '';
    try {
        const res = await amFetch('/api/agentmemory-dash/memories', { signal });
        if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
        const data = await res.json();
        _memoriesCache = Array.isArray(data) ? data : (data.memories ?? []);
        applyMemoriesFilter();
    } catch (err) {
        if (err.name === 'AbortError') return;
        const p = document.createElement('p');
        p.className = 'am-placeholder';
        p.textContent = `読み込みエラー: ${err.message}`;
        el.appendChild(p);
    }
}

function applyMemoriesFilter() {
    const el = document.getElementById('amMemoriesContent');
    el.textContent = '';

    const typeFilter = document.getElementById('amMemoriesFilter')?.value ?? '';
    const textFilter = (document.getElementById('amMemoriesSearch')?.value ?? '').toLowerCase();

    let items = _memoriesCache;
    if (typeFilter) items = items.filter(m => (m.memory_type ?? m.type ?? '') === typeFilter);
    if (textFilter) items = items.filter(m =>
        (m.content ?? m.text ?? '').toLowerCase().includes(textFilter));

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
        m.memory_type ?? m.type ?? '—',
        m.content ?? m.text ?? '—',
        m.created_at ?? m.timestamp ?? '—',
    ));
    el.appendChild(makeTable(['Type', 'Content', '日時'], rows));
}

function wireMemoriesFilter() {
    document.getElementById('amMemoriesFilter')?.addEventListener('change', applyMemoriesFilter);
    document.getElementById('amMemoriesSearch')?.addEventListener('input', applyMemoriesFilter);
}

// ---- Audit tab ----
// Note: GET /audit writes an AuditRecord; auto-refresh disabled by design.
async function loadAudit(signal) {
    const el = document.getElementById('amAuditContent');
    el.textContent = '';
    try {
        const res = await amFetch('/api/agentmemory-dash/audit', { signal });
        if (!res.ok) throw Object.assign(new Error(`HTTP ${res.status}`), { status: res.status });
        const data = await res.json();
        const entries = Array.isArray(data) ? data : (data.audit ?? data.records ?? []);
        renderAudit(el, entries.slice(0, 100));
    } catch (err) {
        if (err.name === 'AbortError') return;
        const p = document.createElement('p');
        p.className = 'am-placeholder';
        p.textContent = `読み込みエラー: ${err.message}`;
        el.appendChild(p);
    }
}

function renderAudit(container, entries) {
    if (!entries.length) {
        const p = document.createElement('p');
        p.className = 'am-placeholder';
        p.textContent = '監査ログがありません';
        container.appendChild(p);
        return;
    }
    const rows = entries.map(e => makeRow(
        e.timestamp ?? e.created_at ?? '—',
        e.operation ?? e.op ?? '—',
        e.target ?? '—',
        e.status ?? '—',
    ));
    container.appendChild(makeTable(['日時', 'Operation', 'Target', 'Status'], rows));
}

// ---- Graph tab ----
// vis-network uses innerHTML internally; yu CSP has trusted-types but NOT
// require-trusted-types-for 'script', so vis.js innerHTML calls are permitted.
let _visNetwork = null;

async function loadGraph(signal) {
    const statsEl = document.getElementById('amGraphStats');
    statsEl.textContent = '';
    const container = document.getElementById('amGraphContainer');
    container.style.display = 'none';
    document.getElementById('amGraphPlaceholder').hidden = true;
    document.getElementById('amGraphTruncNote').hidden = true;

    try {
        const statsRes = await amFetch('/api/agentmemory-dash/graph/stats', { signal });
        if (statsRes.ok) {
            const stats = await statsRes.json();
            renderGraphStats(statsEl, stats);
        }

        const queryRes = await amFetch('/api/agentmemory-dash/graph/query', {
            method: 'POST',
            signal,
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ query: '*', limit: 151 }),
        });
        if (!queryRes.ok) throw Object.assign(new Error(`HTTP ${queryRes.status}`), { status: queryRes.status });
        const data = await queryRes.json();

        const rawNodes = data.nodes ?? [];
        const rawEdges = data.edges ?? [];

        if (!rawNodes.length) {
            document.getElementById('amGraphPlaceholder').hidden = false;
            return;
        }

        if (rawNodes.length > 150) {
            document.getElementById('amGraphTruncNote').hidden = false;
        }

        const nodes = rawNodes.slice(0, 150).map(n => ({
            id: n.id,
            label: n.name ?? n.label ?? String(n.id),
            title: makeNodeTooltip(n),
        }));

        const edges = rawEdges.map((e, i) => ({
            id: i,
            from: e.source ?? e.from,
            to: e.target ?? e.to,
            label: e.type ?? e.label ?? '',
        }));

        if (_visNetwork) { _visNetwork.destroy(); _visNetwork = null; }
        container.style.display = '';
        /* global vis */
        if (typeof vis === 'undefined') {
            const p = document.createElement('p');
            p.className = 'am-placeholder';
            p.textContent = 'vis.js が読み込まれていません';
            statsEl.after(p);
            return;
        }
        _visNetwork = new vis.Network(
            container,
            { nodes: new vis.DataSet(nodes), edges: new vis.DataSet(edges) },
            {
                layout: { improvedLayout: true },
                physics: { stabilization: { iterations: 80 } },
                interaction: { hover: true, tooltipDelay: 200 },
            },
        );
    } catch (err) {
        if (err.name === 'AbortError') return;
        const p = document.createElement('p');
        p.className = 'am-placeholder';
        p.textContent = `読み込みエラー: ${err.message}`;
        statsEl.appendChild(p);
    }
}

function renderGraphStats(container, stats) {
    const rows = [
        ['ノード数', stats.totalNodes ?? stats.node_count ?? stats.nodes ?? '—'],
        ['エッジ数', stats.totalEdges ?? stats.edge_count ?? stats.edges ?? '—'],
    ];
    container.appendChild(makeTable(['項目', '件数'], rows.map(([k, v]) => makeRow(k, v))));
}

// vis.js node tooltip — DOM element (textContent only, no innerHTML)
function makeNodeTooltip(node) {
    const div = document.createElement('div');
    div.style.cssText = 'max-width:280px;padding:6px 8px;font-size:13px;';
    if (node.name ?? node.label) {
        const strong = document.createElement('strong');
        strong.textContent = node.name ?? node.label;
        div.appendChild(strong);
        div.appendChild(document.createElement('br'));
    }
    if (node.type) {
        const span = document.createElement('span');
        span.textContent = `Type: ${node.type}`;
        div.appendChild(span);
        div.appendChild(document.createElement('br'));
    }
    if (node.id !== undefined) {
        const span = document.createElement('span');
        span.textContent = `ID: ${node.id}`;
        div.appendChild(span);
    }
    return div;
}

// ---- Refresh button wiring ----
function wireRefreshButtons() {
    document.getElementById('amHealthRefresh')?.addEventListener('click', () => {
        currentAbort = new AbortController();
        loadHealth(currentAbort.signal);
    });
    document.getElementById('amSessionsRefresh')?.addEventListener('click', () => {
        currentAbort = new AbortController();
        loadSessions(currentAbort.signal);
    });
    document.getElementById('amMemoriesRefresh')?.addEventListener('click', () => {
        _memoriesCache = [];
        currentAbort = new AbortController();
        loadMemories(currentAbort.signal);
    });
    document.getElementById('amGraphRefresh')?.addEventListener('click', () => {
        currentAbort = new AbortController();
        loadGraph(currentAbort.signal);
    });
    document.getElementById('amAuditRefresh')?.addEventListener('click', () => {
        currentAbort = new AbortController();
        loadAudit(currentAbort.signal);
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
