/**
 * video-analysis/core.ts -- Video analysis config CRUD for Tools page.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';
import { apiFetch } from '../api';

function _t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

// ── Config load ────────────────────────────────────────

export async function vaLoadConfig(): Promise<void> {
  try {
    const res = await fetch('/api/video-analysis/config');
    const data = await res.json();
    if (!data.ok) return;
    const cfg = data.config || data.data?.config;
    if (!cfg) return;

    const enabledChk = document.getElementById('vaEnabled') as HTMLInputElement | null;
    if (enabledChk) enabledChk.checked = cfg.enabled !== false;

    const strategySel = document.getElementById('vaStrategy') as HTMLSelectElement | null;
    if (strategySel) strategySel.value = cfg.strategy || 'uniform';

    const kfSlider = document.getElementById('vaKeyframeCount') as HTMLInputElement | null;
    if (kfSlider) {
      kfSlider.value = String(cfg.keyframe_count ?? 4);
      const valEl = document.getElementById('vaKfCountVal');
      if (valEl) valEl.textContent = kfSlider.value;
    }

    const sceneSlider = document.getElementById('vaSceneThreshold') as HTMLInputElement | null;
    if (sceneSlider) {
      sceneSlider.value = String(cfg.scene_threshold ?? 0.4);
      const valEl = document.getElementById('vaSceneThVal');
      if (valEl) valEl.textContent = parseFloat(sceneSlider.value).toFixed(2);
    }

    const storeChk = document.getElementById('vaStorePerKeyframe') as HTMLInputElement | null;
    if (storeChk) storeChk.checked = cfg.store_per_keyframe === true;

    vaOnStrategyChange();
  } catch { /* ignore */ }

  vaLoadStatus();
}


// ── Config save ────────────────────────────────────────

export async function vaSaveConfig(): Promise<void> {
  const enabled = (document.getElementById('vaEnabled') as HTMLInputElement | null)?.checked ?? true;
  const strategy = (document.getElementById('vaStrategy') as HTMLSelectElement | null)?.value || 'uniform';
  const keyframe_count = parseInt(
    (document.getElementById('vaKeyframeCount') as HTMLInputElement | null)?.value || '4', 10,
  );
  const scene_threshold = parseFloat(
    (document.getElementById('vaSceneThreshold') as HTMLInputElement | null)?.value || '0.4',
  );
  const store_per_keyframe = (document.getElementById('vaStorePerKeyframe') as HTMLInputElement | null)?.checked ?? false;

  try {
    const res = await apiFetch('/api/video-analysis/config', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ enabled, strategy, keyframe_count, scene_threshold, store_per_keyframe }),
    });
    const data = await res.json();
    if (data.ok !== false) {
      getNavApi().showToast(_t('tools.va_config_saved', 'Video analysis config saved'));
    }
  } catch {
    getNavApi().showToast(_t('tools.va_config_failed', 'Failed to save config'), true);
  }
}


// ── Strategy change (show/hide scene threshold) ────────

export function vaOnStrategyChange(): void {
  const strategySel = document.getElementById('vaStrategy') as HTMLSelectElement | null;
  const sceneGroup = document.getElementById('vaSceneThresholdGroup');
  if (strategySel && sceneGroup) {
    sceneGroup.style.display = strategySel.value === 'scene' ? '' : 'none';
  }
}


// ── Status ─────────────────────────────────────────────

async function vaLoadStatus(): Promise<void> {
  const el = document.getElementById('vaStatus');
  if (!el) return;
  try {
    const res = await fetch('/api/video-analysis/status');
    const data = await res.json();
    const info = data.data || data;
    const ffmpegOk = info.ffmpeg ? '&#x2713;' : '&#x2717;';
    const videoCount = info.video_files ?? 0;
    const kfCount = info.files_with_keyframes ?? 0;
    el.innerHTML = `ffmpeg ${ffmpegOk} | ${videoCount} video files | ${kfCount} with keyframes`;
  } catch {
    el.textContent = '';
  }
}
