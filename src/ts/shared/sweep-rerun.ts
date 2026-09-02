/**
 * shared/sweep-rerun.ts
 *
 * Same-bridge "Re-run sweep" handler shared by:
 *   • src/ts/detail-modal/runtime/sweep-card.ts   (image modal Sweep card)
 *   • src/ts/apps/sweep-view-app.ts               (dedicated /sweep/<id> page)
 *
 * Both surfaces present "Re-run (same seed)" and "Re-run (new seed)"
 * buttons. A naïve anchor with `?resume_sweep=<id>` only restores the
 * sweep axes — the destination bridge falls back to whatever happens to
 * be in `XX_last_params`, which is typically a later single-image
 * generate, not the original sweep prompt. To get a faithful re-run we
 * fetch the source file's metadata and push the full prompt /
 * negative / characters via the `bridge_send_prompt` localStorage
 * protocol before navigating.
 *
 * Plain left-click is intercepted; middle/Ctrl/Shift/Alt-click still
 * falls through to the anchor's href as a graceful fallback.
 */

import { buildPromptPayload, type BridgeTarget, type PromptSource } from './bridge-payload';
import { bridgeStorage } from './bridge-storage';

export const BRIDGE_URL: Record<BridgeTarget, string> = {
  nai: '/ext/nai-bridge/',
  sd: '/ext/sd-webui/',
  comfyui: '/ext/comfyui-bridge/',
};

export const BRIDGE_LABEL: Record<BridgeTarget, string> = {
  nai: 'NAI Bridge',
  sd: 'SD WebUI',
  comfyui: 'ComfyUI',
};

export function toBridgeTarget(bridge: string): BridgeTarget | null {
  if (bridge === 'nai' || bridge === 'sd' || bridge === 'comfyui') return bridge;
  if (bridge === 'sd-webui') return 'sd';
  return null;
}

export function bridgePath(bridge: string): string | null {
  const t = toBridgeTarget(bridge);
  return t ? BRIDGE_URL[t] : null;
}

function _tr(key: string, fallback: string): string {
  const w = window as unknown as { tr?: (k: string, f?: string) => string };
  return typeof w.tr === 'function' ? w.tr(key, fallback) : fallback;
}

export function attachSameBridgeRerunHandler(
  anchor: HTMLAnchorElement,
  fileId: number,
  target: BridgeTarget,
  omitSeed: boolean,
): void {
  anchor.addEventListener('click', (ev) => {
    const me = ev as MouseEvent;
    if (me.button !== 0 || me.metaKey || me.ctrlKey || me.shiftKey || me.altKey) return;
    ev.preventDefault();
    void sendSameBridgeRerun(fileId, target, omitSeed);
  });
}

interface SweepInfoPayload {
  ok?: boolean;
  meta?: {
    prompt_template?: string;
    negative_template?: string;
  };
}

export async function sendSameBridgeRerun(
  fileId: number,
  target: BridgeTarget,
  omitSeed: boolean,
): Promise<void> {
  try {
    // Fetch file metadata + sweep XMP info in parallel. The file's
    // prompt is the *substituted* one (macros / S-R already applied);
    // the sweep XMP carries the original templates so we can restore
    // `$x1` / `$y1` etc. for the re-run.
    const headers = { 'X-Requested-With': 'XMLHttpRequest' };
    const [r, sweepRes] = await Promise.all([
      fetch(`/api/file/${fileId}`, { headers }),
      fetch(`/api/sweep/info/${fileId}`, { headers }).catch(() => null),
    ]);
    if (!r.ok) {
      window.showToast?.(_tr('sweep_view.rerun_other_failed',
        'Failed to load source metadata: ') + r.status, true);
      return;
    }
    const data = (await r.json()) as PromptSource;
    // Same target as source bridge → buildPromptPayload short-circuits the
    // NAI↔SD conversion and we get prompt/negative/characters/seed verbatim.
    const payload = await buildPromptPayload(data, target, { source: 'sweep-rerun' });
    if (omitSeed && 'seed' in payload) delete (payload as { seed?: number }).seed;

    // Override with the sweep's original prompt/negative templates if
    // available, so $x1 / $y1 / S-R tokens are preserved instead of the
    // baked-in substituted values from this single image's metadata.
    let templateApplied = false;
    if (sweepRes && sweepRes.ok) {
      try {
        const sweepData = (await sweepRes.json()) as SweepInfoPayload;
        const meta = sweepData?.meta;
        if (meta) {
          if (typeof meta.prompt_template === 'string') {
            (payload as { prompt?: string }).prompt = meta.prompt_template;
            templateApplied = true;
          }
          if (typeof meta.negative_template === 'string') {
            (payload as { negative?: string }).negative = meta.negative_template;
          }
        }
      } catch (_e) { /* templates absent → fall back to substituted prompt */ }
    }
    // Diagnostic: when the XMP did not carry prompt_template (older sweeps
    // generated before v4.164.1), the payload.prompt is the SUBSTITUTED text
    // — `$1` / `$x1` markers are already baked. Gated behind window.__YU_DEBUG__
    // so the log doesn't follow regular users into devtools.
    const dbg = (window as unknown as { __YU_DEBUG__?: boolean }).__YU_DEBUG__;
    if (dbg) {
      console.debug('[sweep-rerun] template_applied=', templateApplied,
        'final payload.prompt=', JSON.stringify((payload as { prompt?: string }).prompt));
    }

    const ok = await bridgeStorage.set('bridge_send_prompt', payload);
    if (!ok) {
      window.showToast?.(_tr('detail.modal.send_failed_quota',
        'データが大きすぎて送信できません'), true);
      return;
    }
    let url = BRIDGE_URL[target] + '?resume_sweep=' + encodeURIComponent(String(fileId));
    if (omitSeed) url += '&omit_seed=1';
    window.location.href = url;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    window.showToast?.(_tr('sweep_view.rerun_other_failed',
      'Failed to load source metadata: ') + msg, true);
  }
}

/**
 * Cross-bridge "Re-run on other bridge" — converts NAI<->SD prompt syntax
 * via shared/bridge-payload.ts and pushes the result through the
 * `bridge_send_prompt` localStorage protocol. Navigates with
 * `?resume_sweep=<id>&cross=1` (and `&omit_seed=1` if requested) so the
 * destination bridge restores the sweep axes too.
 *
 * NOTE: Cross-bridge seed semantics differ between NAI / SD / ComfyUI, so
 * the calling UI typically defaults `omitSeed` to true. Callers may still
 * pass false when the user explicitly opts to keep the seed.
 */
export async function sendCrossBridgeRerun(
  fileId: number,
  target: BridgeTarget,
  omitSeed: boolean,
): Promise<void> {
  try {
    const r = await fetch(`/api/file/${fileId}`, {
      headers: { 'X-Requested-With': 'XMLHttpRequest' },
    });
    if (!r.ok) {
      window.showToast?.(_tr('sweep_view.rerun_other_failed',
        'Failed to load source metadata: ') + r.status, true);
      return;
    }
    const data = (await r.json()) as PromptSource;
    const payload = await buildPromptPayload(data, target, {
      source: 'sweep-rerun',
      convertFailedMessage: _tr('detail.modal.send_failed_convert',
        'プロンプト変換に失敗しました。元の文法のまま送信されています'),
    });
    if (omitSeed && 'seed' in payload) delete (payload as { seed?: number }).seed;

    const ok = await bridgeStorage.set('bridge_send_prompt', payload);
    if (!ok) {
      window.showToast?.(_tr('detail.modal.send_failed_quota',
        'データが大きすぎて送信できません'), true);
      return;
    }
    if (payload.convert_warning) {
      window.showToast?.(payload.convert_warning, true);
    }
    let url = BRIDGE_URL[target]
      + '?resume_sweep=' + encodeURIComponent(String(fileId))
      + '&cross=1';
    if (omitSeed) url += '&omit_seed=1';
    window.location.href = url;
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    window.showToast?.(_tr('sweep_view.rerun_other_failed',
      'Failed to load source metadata: ') + msg, true);
  }
}
