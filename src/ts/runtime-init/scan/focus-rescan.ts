/**
 * focus-rescan.ts — Tauri-only: trigger an incremental scan-all when the
 * desktop window regains focus after being away for a while.
 *
 * Web mode has no equivalent because users typically rescan via the Tools
 * page button; the Tauri app is meant to feel "always live" against the
 * filesystem, but we don't yet have a native filesystem watcher (see
 * TODO.md — notify-rs based watcher is the planned upgrade if this proves
 * insufficient).
 *
 * Strategy:
 *   - Only fires inside the Tauri webview (no-op in browser mode).
 *   - Hooks `window.focus` and `document.visibilitychange`.
 *   - Skips fire if the window was only away briefly (debounce on blur
 *     duration) — avoids firing on every alt-tab.
 *   - Rate-limited globally (cooldown) so rapid focus toggles don't queue
 *     repeated /api/scan-all calls.
 *   - Posts to /api/scan-all with force=false; the existing scan worker
 *     does an mtime-based diff scan and the existing scan-banner SSE
 *     surfaces progress, so this is silent on the UI side.
 */

const _AWAY_THRESHOLD_MS = 30_000;     // ignore blur shorter than this
const _COOLDOWN_MS = 5 * 60_000;       // at most one fire per 5 min

let _installed = false;
let _lastBlurAt = 0;
let _lastFireAt = 0;
let _hiddenAt = 0;

function _isTauri(): boolean {
  return typeof (window as unknown as { __TAURI_INTERNALS__?: unknown })
    .__TAURI_INTERNALS__ !== 'undefined';
}

async function _maybeFire(awayMs: number): Promise<void> {
  if (awayMs < _AWAY_THRESHOLD_MS) return;
  const now = Date.now();
  if (now - _lastFireAt < _COOLDOWN_MS) return;
  _lastFireAt = now;
  try {
    await fetch('/api/scan-all', {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'X-Requested-With': 'XMLHttpRequest',
      },
      body: JSON.stringify({ force: false }),
    });
    // Response is intentionally not inspected: scan-banner SSE surfaces
    // progress, and 200/202 are both fine ("started" vs "queued behind a
    // running scan"). Errors are silent — user can still hit the Tools page.
  } catch {
    // Network failure (e.g. server restarting) — silent.
  }
}

export function installFocusRescan(): void {
  if (_installed) return;
  if (!_isTauri()) return;
  _installed = true;

  const now = Date.now();
  _lastBlurAt = now;
  _hiddenAt = document.hidden ? now : 0;

  window.addEventListener('blur', () => {
    _lastBlurAt = Date.now();
  });

  window.addEventListener('focus', () => {
    const away = Date.now() - _lastBlurAt;
    void _maybeFire(away);
  });

  document.addEventListener('visibilitychange', () => {
    if (document.hidden) {
      _hiddenAt = Date.now();
      return;
    }
    if (_hiddenAt === 0) return;
    const away = Date.now() - _hiddenAt;
    _hiddenAt = 0;
    void _maybeFire(away);
  });
}
