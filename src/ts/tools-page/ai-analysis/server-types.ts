/**
 * ai-analysis/server-types.ts -- Shared types, constants, state
 * and utility functions for the AI Server Registry.
 */

import { _t, _esc } from './helpers';
import { showToast as showSharedToast } from '../../shared/toast';

/* ------------------------------------------------------------------ */
/* Types                                                               */
/* ------------------------------------------------------------------ */

export interface ServerEntry {
  id: string;
  name: string;
  type: string;
  priority: number;
  enabled: boolean;
  config: Record<string, string>;
  is_active?: boolean;
  status?: string;
}

export interface DiscoveredCandidate {
  provider: string;
  base_url: string;
  display_preferred_url: string;
  scope: string;
  source: string;
  reachable: boolean;
  advertisable: boolean;
  already_registered: boolean;
  ignored?: boolean;
  model?: string;
  model_name?: string;
  matched_existing_server_id?: string | null;
  matched_existing_server_name?: string | null;
  matchable_servers?: Array<{ id: string; name: string }>;
  duplicate_of_canonical_url?: string | null;
  suppressed_reason?: string | null;
}

export const ENGINE_LABELS: Record<string, string> = {
  claude_api: 'Claude API',
  openai: 'OpenAI API',
  openai_compat: 'OpenAI Compatible',
  ollama: 'Ollama',
  hailo_vlm: 'Hailo VLM',
};

export const ENGINE_ICONS: Record<string, string> = {
  claude_api: '\u2601',    // cloud
  openai: '\u2601',
  openai_compat: '\uD83D\uDD17', // link
  ollama: '\uD83E\uDDE0', // brain
  hailo_vlm: '\uD83D\uDCBB',     // laptop
};

/* ------------------------------------------------------------------ */
/* Shared mutable state                                                */
/* ------------------------------------------------------------------ */

let _servers: ServerEntry[] = [];
let _hasServers = false;
let _discoveredCandidates: DiscoveredCandidate[] = [];

export function getServers(): ServerEntry[] {
  return _servers;
}

export function setServers(list: ServerEntry[]): void {
  _servers = list;
  _hasServers = list.length > 0;
}

export function getHasServers(): boolean {
  return _hasServers;
}

export function getDiscoveredCandidates(): DiscoveredCandidate[] {
  return _discoveredCandidates;
}

export function setDiscoveredCandidates(list: DiscoveredCandidate[]): void {
  _discoveredCandidates = list;
}

/* ------------------------------------------------------------------ */
/* Toast helper                                                        */
/* ------------------------------------------------------------------ */

export function showToast(msg: string, type: 'success' | 'error'): void {
  showSharedToast(msg, type === 'error');
}

export function errMsg(e: unknown): string {
  return e instanceof Error ? e.message : String(e);
}

/* ------------------------------------------------------------------ */
/* Batch server checkboxes                                             */
/* ------------------------------------------------------------------ */

/** Render server checkboxes for batch analysis. */
export function renderBatchServerCheckboxes(container: HTMLElement): void {
  if (!_servers.length || _servers.length < 2) {
    container.innerHTML = '';
    container.style.display = 'none';
    return;
  }

  const enabled = _servers.filter(s => s.enabled);
  if (enabled.length < 2) {
    container.innerHTML = '';
    container.style.display = 'none';
    return;
  }

  container.style.display = '';
  let html = `<p style="font-weight:600;font-size:12px;margin:0 0 6px;">
    ${_t('tools.batch_servers', 'Parallel servers')}:
    <span style="font-weight:normal;color:var(--muted);">${_t('tools.batch_servers_hint', '(select multiple for parallel processing)')}</span>
  </p>`;
  html += '<div style="display:flex;flex-wrap:wrap;gap:6px 14px;">';
  for (const s of enabled) {
    const icon = ENGINE_ICONS[s.type] || '\u2699';
    const checked = s.is_active ? ' checked' : '';
    html += `
      <label style="display:flex;align-items:center;gap:5px;cursor:pointer;font-size:12px;">
        <input type="checkbox" class="ais-batch-cb" value="${s.id}"${checked}
               style="min-width:18px;min-height:18px;">
        <span>${icon} ${_esc(s.name)}</span>
      </label>`;
  }
  html += '</div>';
  container.innerHTML = html;
}

/** Get selected server IDs from batch checkboxes. */
export function getSelectedBatchServerIds(): string[] {
  const cbs = document.querySelectorAll<HTMLInputElement>('.ais-batch-cb:checked');
  return Array.from(cbs).map(cb => cb.value);
}
