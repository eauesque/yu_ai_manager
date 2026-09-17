/**
 * apikeys-mcp.ts -- MCP snippet generation and mode switching.
 */

import { getKeys, getCreatedRawKey, showToast, _t, setOnKeysLoaded } from './apikeys-keys';
import { copyToClipboard } from '../shared/clipboard';

/* -- MCP Snippet State -- */

let _mcpMode: 'stdio' | 'http' = 'stdio';

export function switchMcpMode(mode: 'stdio' | 'http'): void {
  _mcpMode = mode;
  // Update tab styles
  document.querySelectorAll('.mcp-mode-tab').forEach(btn => {
    const el = btn as HTMLElement;
    const isActive = el.dataset.mode === mode;
    el.style.borderBottomColor = isActive ? 'var(--accent)' : 'transparent';
    el.style.color = isActive ? 'var(--accent)' : 'var(--muted)';
    el.classList.toggle('active', isActive);
  });
  // LAN notice display
  const notice = document.getElementById('mcp-lan-notice');
  if (notice) notice.style.display = mode === 'http' ? '' : 'none';
  updateMcpSnippet();
}

export function populateMcpKeySelect(): void {
  const sel = document.getElementById('mcp-key-select') as HTMLSelectElement | null;
  if (!sel) return;
  // Keep first option (no key)
  while (sel.options.length > 1) sel.remove(1);
  for (const k of getKeys()) {
    const opt = document.createElement('option');
    opt.value = k.key_prefix;
    opt.textContent = `${k.label} (${k.key_prefix}...)`;
    sel.appendChild(opt);
  }
  // Auto-select newly created key so the snippet is immediately populated
  const rawKey = getCreatedRawKey();
  if (rawKey) {
    for (let i = 1; i < sel.options.length; i++) {
      if (rawKey.startsWith(sel.options[i].value)) {
        sel.selectedIndex = i;
        break;
      }
    }
  }
}

export function updateMcpSnippet(): void {
  const pre = document.getElementById('mcp-snippet');
  if (!pre) return;

  const sel = document.getElementById('mcp-key-select') as HTMLSelectElement | null;
  const selectedPrefix = sel?.value || '';

  // Determine base URL from current page
  const baseUrl = `${location.protocol}//${location.host}`;

  // Resolve API key value
  let apiKeyValue = '';
  const rawKey = getCreatedRawKey();
  if (selectedPrefix) {
    if (rawKey && rawKey.startsWith(selectedPrefix)) {
      apiKeyValue = rawKey;
    } else {
      apiKeyValue = `sk_... (paste the full key for ${selectedPrefix}...)`;
    }
  }

  let snippet: Record<string, unknown>;

  if (_mcpMode === 'http') {
    // HTTP/SSE mode (for LAN connections)
    const mcpUrl = `${baseUrl}/mcp`;
    const headers: Record<string, string> = {};
    if (apiKeyValue) {
      headers['Authorization'] = `Bearer ${apiKeyValue}`;
    }
    const entry: Record<string, unknown> = {
      type: 'http',
      url: mcpUrl,
    };
    if (Object.keys(headers).length > 0) {
      entry.headers = headers;
    }
    snippet = {
      mcpServers: {
        'yu-ai-manager': entry,
      },
    };
  } else {
    // stdio mode (for local connections)
    const tab = document.getElementById('tab-apikeys');
    const projectRoot = tab?.dataset.projectRoot || '<path-to-yu_ai_manager>';
    const isWin = navigator.platform.indexOf('Win') >= 0;

    const env: Record<string, string> = {
      PYTHONPATH: projectRoot,
      YU_BASE_URL: baseUrl,
    };
    if (apiKeyValue) {
      env.YU_API_KEY = apiKeyValue;
    }

    // Server-detected interpreter path (uv-managed .venv preferred, legacy venv fallback).
    // Falls back to a plausible default if detection failed (no venv on disk yet).
    const detected = tab?.dataset.pythonExe || '';
    const venvPython = detected || (isWin
      ? `${projectRoot}\\.venv\\Scripts\\python.exe`
      : `${projectRoot}/.venv/bin/python3`);

    snippet = {
      mcpServers: {
        'yu-ai-manager': {
          command: venvPython,
          args: ['-m', 'mcp_server'],
          cwd: projectRoot,
          env,
        },
      },
    };
  }

  pre.textContent = JSON.stringify(snippet, null, 2);
}

export function scrollToMcpSnippet(): void {
  const section = document.getElementById('mcp-snippet-section');
  if (section) section.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

export function copyMcpSnippet(): void {
  const pre = document.getElementById('mcp-snippet');
  if (!pre) return;
  void copyToClipboard(pre.textContent || '').then(() => {
    showToast(_t('settings.apikeys_toast_mcp_copied', 'MCP snippet copied'));
  });
}

// Register callback so key list changes refresh MCP UI
setOnKeysLoaded(() => {
  populateMcpKeySelect();
  updateMcpSnippet();
});
