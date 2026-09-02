/**
 * tools/convert.ts — Prompt format conversion (NAI <-> SD) with copy/show.
 * Converted from runtime-tools-convert.js
 */

import { getAppApi } from '../../shared/browser-apis';
import { copyWithFeedback } from './copy';

const { apiFetch, tr } = getAppApi();

export async function convertAndCopy(
  targetId: string,
  mode: string,
  evt?: Event,
): Promise<void> {
  const textEl = document.getElementById(targetId + 'Text');
  if (!textEl) return;
  const originalText = textEl.textContent || '';
  try {
    const response = await apiFetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: originalText, mode }),
    });
    const data = await response.json();
    if (!data.result) {
      alert(tr('convert.failed_with_error', { error: data.error || 'Unknown error' }));
      return;
    }
    const modeLabel =
      mode === 'nai_to_sd'
        ? tr('convert.label.sd', {})
        : mode === 'sd_to_nai'
          ? tr('convert.label.nai', {})
          : '';
    await copyWithFeedback(data.result, (evt?.target as HTMLElement) || null, modeLabel);
  } catch (error) {
    console.error('Conversion failed:', error);
    alert(tr('convert.failed'));
  }
}

export async function convertAndShow(
  targetId: string,
  mode: string,
  evt?: Event,
): Promise<void> {
  const textEl = document.getElementById(targetId + 'Text') as HTMLElement | null;
  if (!textEl) return;
  const originalText = textEl.textContent || '';
  try {
    const response = await apiFetch('/api/convert', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ prompt: originalText, mode, seed: Date.now() }),
    });
    const data = await response.json();
    if (!data.result) {
      alert(tr('convert.failed_with_error', { error: data.error || 'Unknown error' }));
      return;
    }
    const el = textEl as HTMLElement & { dataset: DOMStringMap };
    if (!el.dataset.original) el.dataset.original = originalText;
    if (textEl.textContent === el.dataset.original) {
      textEl.textContent = data.result;
      if (evt?.target) (evt.target as HTMLElement).textContent = tr('convert.btn_restore');
    } else {
      textEl.textContent = el.dataset.original!;
      if (evt?.target) (evt.target as HTMLElement).textContent = tr('convert.btn_expand_dynamic');
    }
  } catch (error) {
    console.error('Conversion failed:', error);
    alert(tr('convert.failed'));
  }
}
