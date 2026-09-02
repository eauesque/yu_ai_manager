/**
 * ui/autocomplete-utils.ts — Tag autocomplete: suggest box creation, token parsing, fetch.
 * Converted from runtime-ui-autocomplete-utils.js
 */

import { getAppApi } from '../../shared/browser-apis';

let _suggestAbort: AbortController | null = null;

export function createSuggestBox(): HTMLDivElement {
  const box = document.createElement('div');
  box.id = 'tagSuggestBox';
  box.style.position = 'absolute';
  box.style.zIndex = '1500';
  box.style.minWidth = '320px';
  box.style.maxWidth = 'min(720px, calc(100vw - 24px))';
  box.style.maxHeight = '280px';
  box.style.overflow = 'auto';
  box.style.display = 'none';
  box.style.padding = '6px';
  box.style.border = '1px solid var(--border)';
  box.style.borderRadius = '10px';
  box.style.background = 'var(--card)';
  box.style.boxShadow = '0 12px 30px rgba(0,0,0,0.18)';
  document.body.appendChild(box);
  return box;
}

export function getCurrentToken(input: HTMLInputElement): string {
  const v = input.value || '';
  const parts = v.split(',');
  return (parts[parts.length - 1] || '').trim();
}

export function replaceLastToken(input: HTMLInputElement, replacement: string): void {
  const v = input.value || '';
  const parts = v.split(',');
  const head = parts
    .slice(0, -1)
    .map((x) => x.trim())
    .filter(Boolean);
  const out = [...head, replacement].join(', ');
  input.value = out;
  const cursorPos = out.length;
  input.setSelectionRange(cursorPos, cursorPos);
  input.focus();
}

export async function fetchSuggest(token: string): Promise<string[]> {
  // Cancel any in-flight suggest request to free up browser connections
  if (_suggestAbort) _suggestAbort.abort();
  _suggestAbort = new AbortController();
  const signal = _suggestAbort.signal;

  // LoRA prefix autocomplete: "<lora:NAME" -> /api/suggest/lora?q=NAME, format as <lora:NAME:1.0>
  const loraMatch = token.match(/^<lora:(.*)$/i);
  if (loraMatch) {
    const loraQ = loraMatch[1] || '';
    const url = getAppApi().apiUrl(`/api/suggest/lora?q=${encodeURIComponent(loraQ)}&limit=20`);
    const res = await fetch(url, { signal });
    if (!res.ok) return [];
    const data = await res.json();
    const names: string[] = Array.isArray(data.suggestions) ? data.suggestions : [];
    return names.map((n) => `<lora:${n}:1.0>`);
  }
  const url = getAppApi().apiUrl(`/api/suggest?q=${encodeURIComponent(token)}&limit=20`);
  const res = await fetch(url, { signal });
  if (!res.ok) return [];
  const data = await res.json();
  return Array.isArray(data.suggestions) ? data.suggestions : [];
}
