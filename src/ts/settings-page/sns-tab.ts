/**
 * settings-page/sns-tab.ts — Settings SNS tab initialization and save logic.
 */

import { getAppApi, getNavApi } from '../shared/browser-apis';
import { loadSnsConfig, saveSnsConfig, testBlueskyConnection } from '../sns-share/sns-share-api';

const XHR_HEADERS = { 'X-Requested-With': 'XMLHttpRequest' } as const;

const { tr } = getAppApi();
const { showToast } = getNavApi();

function _tr(key: string, fb: string): string {
  return tr(key, fb);
}

function _el<T extends HTMLElement>(id: string): T | null {
  return document.getElementById(id) as T | null;
}

export async function initSnsTab(): Promise<void> {
  try {
    const cfg = await loadSnsConfig();
    const bsky = (cfg.bluesky || {}) as Record<string, string>;

    const handleInput = _el<HTMLInputElement>('cfg-sns-bsky-handle');
    const pwInput = _el<HTMLInputElement>('cfg-sns-bsky-password');
    const templateInput = _el<HTMLTextAreaElement>('cfg-sns-template');

    if (handleInput) handleInput.value = bsky.handle || '';
    if (pwInput) pwInput.value = bsky.app_password || '';
    if (templateInput) templateInput.value = (cfg.post_template as string) || '';
  } catch {
    // Ignore initial load failure (keep default values)
  }
}

export async function saveSnsSettings(): Promise<void> {
  const handle = _el<HTMLInputElement>('cfg-sns-bsky-handle')?.value || '';
  const pw = _el<HTMLInputElement>('cfg-sns-bsky-password')?.value || '';
  const template = _el<HTMLTextAreaElement>('cfg-sns-template')?.value || '';

  const ok = await saveSnsConfig({
    bluesky_handle: handle,
    bluesky_app_password: pw,
    post_template: template,
  });

  if (ok) {
    showToast(_tr('settings.sns_saved', 'SNS settings saved'));
  } else {
    showToast(_tr('settings.sns_save_failed', 'Failed to save SNS settings'), true);
  }
}

// ── Bluesky Monitor ──────────────────────────────────────────

export async function initBskyMonitor(): Promise<void> {
  try {
    const cfgRes = await fetch('/api/sns/bsky/monitor/config');
    const cfgJson = await cfgRes.json();
    const cfg = cfgJson.data || cfgJson;

    const interval = _el<HTMLSelectElement>('cfg-bsky-poll-interval');
    if (interval) interval.value = String(cfg.poll_interval_minutes || 30);
    const af = _el<HTMLInputElement>('cfg-bsky-auto-dismiss-follow');
    if (af) af.checked = cfg.auto_dismiss_follow !== false;
    const al = _el<HTMLInputElement>('cfg-bsky-auto-dismiss-like');
    if (al) al.checked = cfg.auto_dismiss_like !== false;
    const ar = _el<HTMLInputElement>('cfg-bsky-auto-dismiss-repost');
    if (ar) ar.checked = cfg.auto_dismiss_repost !== false;
    const ae = _el<HTMLInputElement>('cfg-bsky-auto-respond');
    if (ae) ae.checked = !!cfg.auto_respond_enabled;
    const nc = _el<HTMLInputElement>('cfg-bsky-notify-connect');
    if (nc) nc.checked = cfg.notify_on_connect !== false;
  } catch { /* ignore */ }

  // Load triage prompts + auto-response templates
  try {
    const res = await fetch('/api/sns/bsky/monitor/triage-prompts');
    const json = await res.json();
    const d = json.data || json;
    const tp = d.triage_prompts || {};
    const resp = d.auto_responses || {};

    const tm = _el<HTMLTextAreaElement>('cfg-bsky-triage-mention');
    if (tm) tm.value = tp.mention || '';
    const tr2 = _el<HTMLTextAreaElement>('cfg-bsky-triage-reply');
    if (tr2) tr2.value = tp.reply || '';
    const tq = _el<HTMLTextAreaElement>('cfg-bsky-triage-quote');
    if (tq) tq.value = tp.quote || '';

    const rm = _el<HTMLTextAreaElement>('cfg-bsky-response-mention');
    if (rm) rm.value = resp.mention || '';
    const rr = _el<HTMLTextAreaElement>('cfg-bsky-response-reply');
    if (rr) rr.value = resp.reply || '';
  } catch { /* ignore */ }
}

export async function saveBskyMonitorSettings(): Promise<void> {
  const interval = parseInt(_el<HTMLSelectElement>('cfg-bsky-poll-interval')?.value || '30');
  const body: Record<string, unknown> = {
    poll_interval_minutes: interval,
    auto_dismiss_follow: _el<HTMLInputElement>('cfg-bsky-auto-dismiss-follow')?.checked ?? true,
    auto_dismiss_like: _el<HTMLInputElement>('cfg-bsky-auto-dismiss-like')?.checked ?? true,
    auto_dismiss_repost: _el<HTMLInputElement>('cfg-bsky-auto-dismiss-repost')?.checked ?? true,
    auto_respond_enabled: _el<HTMLInputElement>('cfg-bsky-auto-respond')?.checked ?? false,
    notify_on_connect: _el<HTMLInputElement>('cfg-bsky-notify-connect')?.checked ?? true,
  };

  // Save config
  try {
    await fetch('/api/sns/bsky/monitor/config', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify(body),
    });
  } catch {
    showToast(_tr('settings.bsky_save_failed', 'Failed to save monitor settings'), true);
    return;
  }

  // Save triage prompts + auto-responses
  const triageBody: Record<string, unknown> = {
    triage_prompts: {
      mention: _el<HTMLTextAreaElement>('cfg-bsky-triage-mention')?.value || '',
      reply: _el<HTMLTextAreaElement>('cfg-bsky-triage-reply')?.value || '',
      quote: _el<HTMLTextAreaElement>('cfg-bsky-triage-quote')?.value || '',
    },
    auto_responses: {
      mention: _el<HTMLTextAreaElement>('cfg-bsky-response-mention')?.value || '',
      reply: _el<HTMLTextAreaElement>('cfg-bsky-response-reply')?.value || '',
    },
  };

  try {
    await fetch('/api/sns/bsky/monitor/triage-prompts', {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify(triageBody),
    });
    showToast(_tr('settings.bsky_saved', 'Monitor settings saved'));
  } catch {
    showToast(_tr('settings.bsky_save_failed', 'Failed to save'), true);
  }
}

export async function bskyPollNow(): Promise<void> {
  const statusEl = _el<HTMLElement>('bsky-monitor-status');
  if (statusEl) statusEl.textContent = _tr('settings.bsky_polling', 'Polling...');
  try {
    const res = await fetch('/api/sns/bsky/queue/poll', {
      method: 'POST',
      headers: XHR_HEADERS,
    });
    const json = await res.json();
    const msg = (json.data || json).message || 'Done';
    if (statusEl) statusEl.textContent = msg;
    showToast(msg);
  } catch (e) {
    if (statusEl) statusEl.textContent = 'Error';
    showToast('Poll error', true);
  }
}

export async function testBskyConnection(): Promise<void> {
  const statusEl = _el<HTMLElement>('sns-bsky-test-status');
  if (statusEl) {
    statusEl.textContent = _tr('settings.sns_testing', 'Testing...');
    statusEl.style.color = 'var(--muted)';
  }

  const result = await testBlueskyConnection();

  if (statusEl) {
    if (result.ok) {
      statusEl.textContent = `\u2705 ${result.handle} (${result.display_name || ''})`;
      statusEl.style.color = '#2ecc71';
    } else {
      statusEl.textContent = `\u274C ${result.error || 'Connection failed'}`;
      statusEl.style.color = '#d32f2f';
    }
  }
}
