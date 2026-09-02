import type { InspectData } from './drop-zone';
import { handleJsonDownloadClick } from '../shared/json-download';
import { copyToClipboard } from '../shared/clipboard';

export function esc(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

export async function renderInspectCharacterPrompts(
  panel: HTMLElement,
  data: InspectData,
  loadCharacterRender: () => Promise<typeof import('../runtime-init/novelai/character-render')>,
  loadCharacterParse: () => Promise<typeof import('../runtime-init/novelai/character-parse')>,
): Promise<void> {
  const container = document.createElement('div');
  container.id = 'characterPromptsContainer';
  panel.appendChild(container);
  if (data.novelai_v4) {
    const { renderCharacterPrompts } = await loadCharacterRender();
    const charData = {
      baseCaption: data.novelai_v4.base_caption || '',
      characters: (data.novelai_v4.character_prompts || []).map((cp: Record<string, unknown>, i: number) => ({
        index: i + 1,
        prompt: cp.prompt || cp.char_caption || '',
        positions: cp.centers || cp.positions || [],
      })),
      negativeBase: data.novelai_v4.negative_base || '',
      negativeCharacters: (data.novelai_v4.negative_characters || []).map((nc: Record<string, unknown>, i: number) => ({
        index: i + 1,
        prompt: nc.prompt || nc.char_caption || '',
        positions: nc.centers || nc.positions || [],
      })),
      vibeTransfer: data.novelai_v4.vibe_transfer || null,
    };
    renderCharacterPrompts(container, charData);
    return;
  }
  if (data.raw_meta_json && (data.meta_source === 'novelai_v4_png' || data.meta_source === 'novelai_v4_webp')) {
    try {
      const { parseNovelAICharacterPrompts } = await loadCharacterParse();
      const { renderCharacterPrompts } = await loadCharacterRender();
      const charData = parseNovelAICharacterPrompts(data.raw_meta_json);
      if (charData) renderCharacterPrompts(container, charData);
    } catch {
      // ignore parse failure
    }
  }
}

export async function renderInspectCharGrid(
  data: InspectData,
  loadCharacterGrid: () => Promise<typeof import('../runtime-init/novelai/character-grid')>,
): Promise<void> {
  const wrapper = document.getElementById('inspectPreviewWrap');
  const img = document.getElementById('previewImg') as HTMLImageElement | null;
  if (!wrapper || !img) return;
  const { renderCharacterGrid, removeCharacterGrid } = await loadCharacterGrid();
  removeCharacterGrid(wrapper);
  try {
    let commentStr = '';
    if (data.raw_meta_json) {
      try {
        const parsed = JSON.parse(data.raw_meta_json);
        commentStr = parsed.Comment || '';
      } catch {
        // ignore
      }
    }
    if (!commentStr) {
      const raw = data.raw_metadata || {};
      if (typeof raw.Comment === 'string') commentStr = raw.Comment;
    }
    if (!commentStr) return;
    const comment = JSON.parse(commentStr);
    const chars = comment.v4_prompt?.caption?.char_captions;
    if (!Array.isArray(chars)) return;
    const gridChars = chars.map((c: any, i: number) => ({
      index: i + 1,
      positions: c.centers || [],
    })).filter((c: { positions: unknown[] }) => c.positions.length > 0);
    if (!gridChars.length) return;
    const doRender = () => {
      requestAnimationFrame(() => {
        if (img.clientWidth && img.clientHeight) {
          renderCharacterGrid(wrapper, img, gridChars);
        } else {
          requestAnimationFrame(() => {
            if (img.clientWidth && img.clientHeight) renderCharacterGrid(wrapper, img, gridChars);
          });
        }
      });
    };
    if (img.complete && img.naturalWidth) doRender();
    else img.addEventListener('load', doRender, { once: true });
  } catch {
    // ignore unsupported data
  }
}

function showCopyBadge(el: HTMLElement, ok: boolean): void {
  const old = el.querySelector('.copy-badge');
  if (old) old.remove();
  const badge = document.createElement('span');
  badge.className = 'copy-badge';
  badge.textContent = ok ? '\u2713' : '\u00d7';
  badge.style.cssText =
    'position:absolute;top:-6px;right:-6px;font-size:11px;font-weight:bold;line-height:1;'
    + `color:${ok ? '#2ecc71' : '#e74c3c'};`
    + `background:${ok ? 'rgba(46,204,113,0.15)' : 'rgba(231,76,60,0.15)'};`
    + 'border-radius:50%;width:16px;height:16px;display:flex;align-items:center;justify-content:center;pointer-events:none;';
  el.style.position = 'relative';
  el.appendChild(badge);
  setTimeout(() => badge.remove(), 1800);
}

export function copyRawMeta(t: (key: string, fallback: string) => string): void {
  const rawMetaEl = document.getElementById('rawMeta');
  if (!rawMetaEl) return;
  const text = rawMetaEl.textContent || '';
  void copyToClipboard(text).then(() => {
    const btn = document.activeElement as HTMLElement | null;
    if (btn) {
      const original = btn.textContent;
      btn.textContent = '\u2705 ' + t('inspect.copied', 'Copied');
      setTimeout(() => { btn.textContent = original; }, 1500);
    }
  });
}

export function initCopyB64Handler(): void {
  document.addEventListener('click', (e: MouseEvent) => {
    const target = e.target as HTMLElement;

    // Download branch must come before [data-copy-b64] to avoid interference.
    const dlTarget = target.closest('[data-download-json-b64]') as HTMLElement | null;
    if (dlTarget) {
      handleJsonDownloadClick(dlTarget);
      return;
    }

    const btn = target.closest('[data-copy-b64]') as HTMLElement | null;
    if (!btn) return;
    const b64 = btn.getAttribute('data-copy-b64') || btn.dataset.copyB64 || '';
    const label = btn.dataset.copyLabel || '';
    try {
      const text = decodeURIComponent(escape(atob(b64)));
      copyToClipboard(text).then(() => {
        showCopyBadge(btn, true);
        if (window.showToast) {
          const msg = window.tr ? window.tr('toast.copy_with_label', { label }) || 'Copied' : 'Copied';
          window.showToast(msg);
        }
      }).catch(() => {
        showCopyBadge(btn, false);
        if (window.showToast) window.showToast(window.tr?.('toast.copy_failed') || 'Copy failed', true);
      });
    } catch (err) {
      console.error('Copy failed:', err);
      if (window.showToast) window.showToast(window.tr?.('toast.copy_failed') || 'Copy failed', true);
    }
  });
}

export function openInSimulator(lastInspectData: InspectData | null, which: string): void {
  if (!lastInspectData) return;
  const positive = lastInspectData.positive || lastInspectData.positive_prompt || '';
  const negative = lastInspectData.negative || lastInspectData.negative_prompt || '';
  const text = which === 'negative' ? negative : positive;
  if (!text) return;
  try {
    sessionStorage.setItem('prompt_sim_data', text);
  } catch {
    // ignore quota issues
  }
  window.open('/ext/prompt-sim/', '_blank');
}
