/**
 * tools-page/mcp-connections.ts — MCP server connection management UI.
 */

import { apiFetch } from './api';
import { customConfirm } from '../shared/dialog';
import { getEnhanceHandle } from '../shared/json-editor-enhance';

interface McpConnection {
  id: string;
  name: string;
  transport: string;
  status: string;
  tool_count?: number;
  command?: string;
}

async function loadMcpConnections(): Promise<void> {
  const list = document.getElementById('mcpConnectionList');
  if (!list) return;
  try {
    const res = await apiFetch('/ext/mcp-client/api/connections');
    const json = await res.json();
    const data = json.data ?? json;
    const conns: McpConnection[] = data.connections ?? [];
    if (conns.length === 0) {
      list.textContent = 'No MCP connections configured';
      list.style.color = 'var(--muted)';
      return;
    }
    list.textContent = '';
    list.style.color = '';
    conns.forEach(c => {
      const row = document.createElement('div');
      row.style.cssText = 'display:flex;align-items:center;gap:8px;padding:4px 0;border-bottom:1px solid var(--border,#333);';

      const statusDot = document.createElement('span');
      const isConnected = c.status === 'connected';
      statusDot.style.cssText = `width:8px;height:8px;border-radius:50%;background:${isConnected ? '#22c55e' : '#666'};flex-shrink:0;`;
      statusDot.title = c.status;

      const name = document.createElement('span');
      name.style.cssText = 'flex:1;font-size:13px;font-weight:600;';
      name.textContent = c.name || c.id;

      const transport = document.createElement('span');
      transport.style.cssText = 'font-size:10px;color:var(--muted);';
      transport.textContent = c.transport || '';

      const tools = document.createElement('span');
      tools.style.cssText = 'font-size:11px;color:var(--accent);';
      tools.textContent = (c.tool_count ?? 0) + ' tools';

      const connectBtn = document.createElement('button');
      connectBtn.className = 'btn btn-sm';
      connectBtn.textContent = isConnected ? 'Disconnect' : 'Connect';
      connectBtn.style.cssText = 'font-size:10px;padding:2px 6px;';
      connectBtn.addEventListener('click', async () => {
        const action = isConnected ? 'disconnect' : 'connect';
        await apiFetch(`/ext/mcp-client/api/connections/${c.id}/${action}`, { method: 'POST' });
        loadMcpConnections();
      });

      const delBtn = document.createElement('button');
      delBtn.className = 'btn btn-sm';
      delBtn.textContent = '\u00d7';
      delBtn.style.cssText = 'font-size:12px;padding:2px 6px;color:#e74c3c;';
      delBtn.addEventListener('click', async () => {
        await apiFetch(`/ext/mcp-client/api/connections/${c.id}`, { method: 'DELETE' });
        loadMcpConnections();
      });

      row.appendChild(statusDot);
      row.appendChild(name);
      row.appendChild(transport);
      row.appendChild(tools);
      row.appendChild(connectBtn);
      row.appendChild(delBtn);
      list.appendChild(row);
    });
  } catch {
    list.textContent = 'MCP Client extension not available';
    list.style.color = 'var(--muted)';
  }
}

function initMcpAdd(): void {
  const btn = document.getElementById('mcpConnAddBtn');
  const nameInput = document.getElementById('mcpConnName') as HTMLInputElement | null;
  const cmdInput = document.getElementById('mcpConnCmd') as HTMLInputElement | null;
  if (!btn || !nameInput || !cmdInput) return;
  btn.addEventListener('click', async () => {
    const name = nameInput.value.trim();
    const command = cmdInput.value.trim();
    if (!name || !command) return;
    try {
      await apiFetch('/ext/mcp-client/api/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ name, transport: 'stdio', command }),
      });
      nameInput.value = '';
      cmdInput.value = '';
      loadMcpConnections();
    } catch (e) {
      console.error('Failed to add MCP connection:', e);
    }
  });
}

function initMcpJsonImport(): void {
  const btn = document.getElementById('mcpConnJsonAddBtn');
  const textarea = document.getElementById('mcpConnJsonInput') as HTMLTextAreaElement | null;
  const errorEl = document.getElementById('mcpConnJsonError');
  if (!btn || !textarea) return;

  btn.addEventListener('click', async () => {
    const raw = textarea.value.trim();
    if (!raw) return;
    if (errorEl) errorEl.textContent = '';

    let cfg: Record<string, unknown>;
    try {
      cfg = JSON.parse(raw);
    } catch {
      if (errorEl) errorEl.textContent = 'Invalid JSON';
      return;
    }

    // Support both bare config and Claude Desktop / Cursor style wrappers:
    // {"mcpServers": {"name": {...}}} or {"name": {...transport...}}
    const unwrapped = unwrapMcpJson(cfg);
    if (!unwrapped) {
      if (errorEl) errorEl.textContent = 'Could not detect MCP server config. Paste the full JSON snippet.';
      return;
    }

    // Check validation issues before submitting
    const handle = textarea ? getEnhanceHandle(textarea) : undefined;
    const issues = handle?.getValidationIssues() ?? [];
    if (issues.length > 0) {
      const lines = issues.map(i => `• ${i.path ? i.path + ': ' : ''}${i.message}`).join('\n');
      const ok = await customConfirm(
        `${issues.length} issue(s) found:\n${lines}\n\nAdd anyway?`,
      );
      if (!ok) return;
    }

    try {
      const res = await apiFetch('/ext/mcp-client/api/connections', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(unwrapped),
      });
      const json = await res.json();
      if (!res.ok || json.error) {
        if (errorEl) errorEl.textContent = json.error || `HTTP ${res.status}`;
        return;
      }
      textarea.value = '';
      if (errorEl) errorEl.textContent = '';
      // Close the details panel
      const details = textarea.closest('details');
      if (details) (details as HTMLDetailsElement).open = false;
      loadMcpConnections();
    } catch (e) {
      if (errorEl) errorEl.textContent = String(e);
    }
  });
}

/** Unwrap various MCP JSON config formats into our connection schema. */
function unwrapMcpJson(raw: Record<string, unknown>): Record<string, unknown> | null {
  // Format 1: Direct config with transport field
  // {"name":"x","transport":"stdio","stdio":{"command":"npx","args":[...]}}
  if (raw.transport && raw.name) {
    return raw;
  }

  // Format 2: Claude Desktop / Cursor style: {"mcpServers": {"server-name": {config}}}
  const servers = (raw.mcpServers ?? raw.mcp_servers ?? raw.servers) as Record<string, unknown> | undefined;
  if (servers && typeof servers === 'object') {
    const entries = Object.entries(servers);
    if (entries.length === 0) return null;
    // Import first server (or all? For now, first)
    const [serverName, serverCfg] = entries[0];
    if (typeof serverCfg !== 'object' || !serverCfg) return null;
    return normalizeServerEntry(serverName, serverCfg as Record<string, unknown>);
  }

  // Format 3: Bare command object: {"command":"npx","args":["-y","@mcp/server"]}
  if (raw.command && typeof raw.command === 'string') {
    const name = guessName(raw.command as string, (raw.args as string[]) ?? []);
    return {
      name,
      transport: 'stdio',
      stdio: { command: raw.command, args: raw.args ?? [] },
      env: raw.env ?? {},
    };
  }

  // Format 4: URL-based: {"url":"http://..."}
  if (raw.url && typeof raw.url === 'string') {
    const url = raw.url as string;
    return {
      name: new URL(url).hostname,
      transport: 'streamable_http',
      streamable_http: { url },
    };
  }

  return null;
}

function normalizeServerEntry(name: string, cfg: Record<string, unknown>): Record<string, unknown> {
  // Claude Desktop format: {"command":"npx","args":[...],"env":{}}
  if (cfg.command && typeof cfg.command === 'string') {
    return {
      name,
      transport: 'stdio',
      stdio: { command: cfg.command, args: cfg.args ?? [] },
      env: cfg.env ?? {},
    };
  }
  // SSE format: {"url":"http://..."}
  if (cfg.url && typeof cfg.url === 'string') {
    return {
      name,
      transport: 'streamable_http',
      streamable_http: { url: cfg.url },
    };
  }
  // Already in our format
  return { name, ...cfg };
}

function guessName(command: string, args: string[]): string {
  // Try to extract a meaningful name from command/args
  // e.g. "npx -y @modelcontextprotocol/server-filesystem" → "server-filesystem"
  for (const arg of args) {
    if (arg.startsWith('@') || arg.startsWith('mcp-') || arg.includes('server')) {
      const parts = arg.split('/');
      return parts[parts.length - 1];
    }
  }
  return command.split(/[\\/]/).pop() || 'mcp-server';
}

if (document.getElementById('mcpConnectionCard')) {
  loadMcpConnections();
  initMcpAdd();
  initMcpJsonImport();
}
