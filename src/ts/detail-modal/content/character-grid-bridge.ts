/**
 * Bridge between detail modal data and the character grid overlay.
 * Extracts character position data and renders the grid on the modal image.
 */

import { getRuntimeInitApi } from '../../shared/browser-apis';

interface GridCharacter {
  index: number;
  positions: Array<{ x: number; y: number }>;
}

/**
 * Extract GridCharacter[] from modal file data.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
function extractGridCharacters(data: any): GridCharacter[] {
  // Primary: data.novelai_v4.character_prompts
  if (data.novelai_v4?.character_prompts) {
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    return data.novelai_v4.character_prompts
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      .map((cp: any, i: number) => ({
        index: i + 1,
        positions: cp.centers || cp.positions || [],
      }))
      .filter((c: GridCharacter) => c.positions.length > 0);
  }

  // Fallback: raw_meta_json parse
  if ((data.meta_source === 'novelai_v4_png' || data.meta_source === 'novelai_v4_webp') && data.raw_meta_json) {
    try {
      const raw = JSON.parse(data.raw_meta_json);
      const comment = JSON.parse(raw.Comment || '{}');
      const chars = comment.v4_prompt?.caption?.char_captions;
      if (Array.isArray(chars)) {
        return chars
          .map((c: { centers?: Array<{ x: number; y: number }> }, i: number) => ({
            index: i + 1,
            positions: c.centers || [],
          }))
          .filter((c: GridCharacter) => c.positions.length > 0);
      }
    } catch { /* ignore */ }
  }

  return [];
}

/**
 * Render (or skip) the character position grid on the modal image.
 */
// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function renderCharacterGridForData(data: any): void {
  const runtimeInitApi = getRuntimeInitApi();
  const characters = extractGridCharacters(data);
  if (!characters.length) return;

  const stage = document.getElementById('modalImageStage');
  const img = document.getElementById('modalImage') as HTMLImageElement | null;
  if (!stage || !img) return;

  // Ensure the stage is position:relative for absolute overlay
  if (getComputedStyle(stage).position === 'static') {
    stage.style.position = 'relative';
  }

  const doRender = () => {
    if (img.clientWidth && img.clientHeight) {
      void runtimeInitApi.renderCharacterGrid(stage, img, characters).then(() => {
        // Grid is rendered but hidden by default — user toggles with button
        const gridEl = stage.querySelector('.char-position-grid') as HTMLElement | null;
        if (gridEl) gridEl.style.display = 'none';
        // Show the toggle button in inactive state
        const btn = document.getElementById('charGridToggle');
        if (btn) {
          btn.style.display = '';
          btn.style.opacity = '0.45';
        }
      });
    }
  };

  // If image is already loaded, render immediately; otherwise wait
  if (img.complete && img.naturalWidth) {
    doRender();
  } else {
    img.addEventListener('load', doRender, { once: true });
  }
}
