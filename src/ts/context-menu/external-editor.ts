/**
 * context-menu/external-editor.ts — Tauri external editor integration (L268).
 *
 * Implements the "Open in external editor" context menu action using the
 * low-level Tauri IPC API (`window.__TAURI_INTERNALS__`). Avoids depending on
 * `withGlobalTauri` so we don't pay the full `@tauri-apps/api` bundle cost on
 * every page load — only the two commands and one event we actually need.
 *
 * Flow:
 *   1. User right-clicks an image card → "外部エディタで開く"
 *   2. This module invokes `open_in_external_editor` on the Rust side, which
 *      spawns the editor and a background mtime-polling thread
 *   3. The Rust thread emits `editor-closed` with `{path, changed: bool}` on
 *      mtime change or after its 5-minute timeout
 *   4. The event handler (registered ONCE at page init) calls
 *      `/api/files/register-path` on mtime change to trigger a rescan, which
 *      fires `scan.complete` SSE — the existing SSE pipeline refreshes the card
 */

import { getAppApi, getNavApi } from '../shared/browser-apis';

interface CardData {
  id: number;
  path: string;
  positive: string;
  negative: string;
}

interface TauriInternals {
  invoke: (cmd: string, payload?: Record<string, unknown>) => Promise<unknown>;
  transformCallback: (fn: (data: unknown) => void, once?: boolean) => number;
  unregisterCallback: (id: number) => void;
}

interface EditorClosedPayload {
  path: string;
  changed: boolean;
}

function _tr(key: string, fb: string): string {
  return getAppApi().tr(key, fb);
}

function _toast(msg: string): void {
  getNavApi().showToast(msg);
}

/**
 * Return the Tauri IPC internals object if we're running inside the desktop
 * app, or `null` for plain web mode. Callers must gate all IPC on this.
 */
function _tauriInternals(): TauriInternals | null {
  const w = window as unknown as { __TAURI_INTERNALS__?: TauriInternals };
  return w.__TAURI_INTERNALS__ || null;
}

/**
 * Return true if the Tauri session IPC token (injected by main.rs setup) is
 * present. Without this token, `open_in_external_editor` will reject.
 */
function _restartToken(): string {
  const w = window as unknown as { __TAURI_RESTART_TOKEN__?: string };
  return w.__TAURI_RESTART_TOKEN__ || '';
}

/**
 * True if we're running inside the Tauri desktop app.
 * Gates the context menu item so web mode users don't see a non-functional entry.
 */
export function isExternalEditorAvailable(): boolean {
  return _tauriInternals() !== null;
}

/**
 * True if the given file path looks like an archive member (`foo.zip!bar.png`).
 * These cannot be opened in an external editor because they don't exist as
 * standalone files on disk — the caller must extract first.
 */
export function isArchiveMemberPath(path: string): boolean {
  return /\.(zip|7z|rar)!/i.test(path);
}

/**
 * Context menu action: open the file in the configured external editor.
 * On first use, the Rust side pops up a file picker so the user can select
 * their editor executable; the selection is persisted in editor_config.json
 * under the Tauri config directory.
 */
export async function actionOpenInExternalEditor(data: CardData): Promise<void> {
  const internals = _tauriInternals();
  if (!internals) {
    _toast(_tr('ctx.editor_desktop_only', '外部エディタはデスクトップ版でのみ利用できます'));
    return;
  }
  if (!data.path) {
    _toast(_tr('ctx.editor_no_path', 'ファイルパスが取得できません'));
    return;
  }
  if (isArchiveMemberPath(data.path)) {
    _toast(_tr('ctx.editor_archive_unsupported', 'アーカイブ内のファイルは直接編集できません'));
    return;
  }
  const token = _restartToken();
  if (!token) {
    _toast(_tr('ctx.editor_no_token', 'IPC トークンが見つかりません'));
    return;
  }

  try {
    await internals.invoke('open_in_external_editor', {
      token,
      filePath: data.path,
    });
    _toast(_tr('ctx.editor_launched', 'エディタを起動しました'));
  } catch (err) {
    const msg = err instanceof Error ? err.message : String(err);
    // "No editor selected" just means the user cancelled the picker — not worth
    // a red toast, but a gentle info-level notice is fine.
    _toast(_tr('ctx.editor_launch_failed', 'エディタ起動失敗') + ': ' + msg);
  }
}

/**
 * Low-level Tauri event subscription using `plugin:event|listen`.
 *
 * Tauri 2.x normally exposes this via `@tauri-apps/api/event.listen()` when
 * `withGlobalTauri: true`, but we intentionally skip the global bundle to keep
 * page-load cost minimal. This helper replicates the minimum-viable subset.
 *
 * Returns an unlisten function.
 */
function _tauriListen(
  event: string,
  handler: (payload: unknown) => void,
): () => void {
  const internals = _tauriInternals();
  if (!internals) return () => {};

  const callbackId = internals.transformCallback((raw: unknown) => {
    // Tauri wraps payloads as `{event, id, payload}` — we only care about payload
    try {
      const envelope = raw as { payload?: unknown };
      handler(envelope && 'payload' in envelope ? envelope.payload : raw);
    } catch {
      handler(raw);
    }
  }, false);

  let eventIdPromise: Promise<number> | null = internals
    .invoke('plugin:event|listen', {
      event,
      target: { kind: 'Any' },
      handler: callbackId,
    })
    .then((id) => id as number)
    .catch(() => {
      internals.unregisterCallback(callbackId);
      return -1;
    });

  return () => {
    if (!eventIdPromise) return;
    eventIdPromise
      .then((eventId) => {
        if (eventId >= 0) {
          internals.invoke('plugin:event|unlisten', { event, eventId }).catch(() => {});
        }
      })
      .finally(() => {
        internals.unregisterCallback(callbackId);
      });
    eventIdPromise = null;
  };
}

let _editorClosedInstalled = false;

/**
 * Install the `editor-closed` event listener once per page load. On mtime
 * change, fires a rescan via `/api/files/register-path` so the existing SSE
 * `scan.complete` pipeline can refresh the card. Idempotent — repeated calls
 * are no-ops.
 */
export function installEditorClosedListener(): void {
  if (_editorClosedInstalled) return;
  if (!isExternalEditorAvailable()) return;
  _editorClosedInstalled = true;

  _tauriListen('editor-closed', async (payload: unknown) => {
    const p = payload as EditorClosedPayload | null;
    if (!p || typeof p.path !== 'string') return;
    if (!p.changed) {
      // Editor session ended without a save — no-op. Don't toast to avoid
      // noise for the "user opened but decided not to edit" case.
      return;
    }
    try {
      const res = await fetch('/api/files/register-path', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: p.path }),
      });
      if (res.ok) {
        _toast(_tr('ctx.editor_rescanned', '編集後の再スキャンが完了しました'));
      } else {
        const data: unknown = await res.json().catch(() => null);
        const errMsg = (data && typeof data === 'object' && 'error' in data
          ? String((data as { error: unknown }).error)
          : 'HTTP ' + res.status);
        _toast(_tr('ctx.editor_rescan_failed', '再スキャンに失敗しました') + ': ' + errMsg);
      }
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err);
      _toast(_tr('ctx.editor_rescan_failed', '再スキャンに失敗しました') + ': ' + msg);
    }
  });
}
