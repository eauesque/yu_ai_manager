/**
 * Bridge Autocomplete -- lightweight Danbooru tag + LoRA + Wildcard autocomplete
 * for bridge prompt textareas.
 *
 * Fetch logic is in autocomplete-fetch.ts.
 */

import { getCaretCoordinates } from '../shared/caret-position';
import {
  AcItem,
  fetchTagDict, fetchLora, fetchEmbedding, searchWc,
} from './autocomplete-fetch';

export interface AutocompleteOpts {
  onConfirm?: (item: AcItem) => void;
  /** Bridge base path for live resource discovery (e.g. "/ext/sd-webui", "/ext/comfyui-bridge"). */
  bridgeBase?: string;
}

export interface AutocompleteInstance {
  hide: () => void;
  setEnabled: (flag: boolean) => void;
}

interface AnalyzeResult {
  mode: 'tag' | 'lora' | 'embedding' | 'wc';
  query: string;
}

const DEBOUNCE_MS = 200;
const MIN_CHARS = 2;

function attach(textarea: HTMLTextAreaElement, opts?: AutocompleteOpts): AutocompleteInstance | null {
  if (!textarea) return null;
  const options = opts || {};

  let drop: HTMLDivElement | null = null;
  let items: AcItem[] = [];
  let idx = -1;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let tokenStart = 0;
  let wcPrefixPos = 0;
  let curMode: string | null = null;
  let enabled = true;

  function ensureDrop(): HTMLDivElement {
    if (drop) return drop;
    drop = document.createElement('div');
    drop.className = 'bridge-ac-dropdown';
    drop.style.display = 'none';
    // Walk up to find a parent without overflow:hidden (ps-editor-wrap clips it)
    let parent = textarea.parentElement;
    while (parent && parent !== document.body) {
      const ov = getComputedStyle(parent).overflow;
      if (ov === 'hidden' || ov === 'clip') {
        parent = parent.parentElement;
      } else {
        break;
      }
    }
    (parent || document.body).appendChild(drop);
    drop.addEventListener('mousedown', (e) => e.preventDefault());
    return drop;
  }

  function escHtml(s: string): string {
    const d = document.createElement('div');
    d.appendChild(document.createTextNode(s));
    return d.innerHTML;
  }

  function show(results: AcItem[]): void {
    if (!results.length) {
      hide();
      return;
    }
    items = results;
    idx = 0;
    const d = ensureDrop();
    let html = '';
    for (let i = 0; i < results.length; i++) {
      const it = results[i];
      const cls = 'bridge-ac-item' + (i === 0 ? ' active' : '');
      html += '<div class="' + cls + '" data-idx="' + i + '">';
      if (it.category != null) {
        html += '<span class="bridge-ac-cat bridge-ac-cat-' + it.category + '"></span>';
      }
      html += '<span class="bridge-ac-name">' + escHtml(it.label) + '</span>';
      if (it.sub) html += '<span class="bridge-ac-sub">' + escHtml(it.sub) + '</span>';
      html += '</div>';
    }
    d.innerHTML = html;
    d.style.display = '';
    // Position at caret within textarea
    const rect = textarea.getBoundingClientRect();
    const pRect = (d.parentNode as HTMLElement).getBoundingClientRect();
    const caret = getCaretCoordinates(textarea, textarea.selectionStart);
    const caretAbsTop = rect.top + caret.top;
    const caretAbsLeft = rect.left + caret.left;
    let dropTop = caretAbsTop + caret.height + 2 - pRect.top;
    // Flip above caret if dropdown would overflow viewport bottom
    const dropHeight = Math.min(d.scrollHeight || 200, 200);
    if (caretAbsTop + caret.height + 2 + dropHeight > window.innerHeight) {
      dropTop = caretAbsTop - dropHeight - 2 - pRect.top;
    }
    d.style.left = Math.max(0, caretAbsLeft - pRect.left) + 'px';
    d.style.top = dropTop + 'px';
    d.style.width = '';
    d.querySelectorAll<HTMLElement>('.bridge-ac-item').forEach((el) => {
      el.addEventListener('click', () => {
        idx = parseInt(el.getAttribute('data-idx') || '0', 10);
        confirm();
      });
    });
  }

  function hide(): void {
    if (drop) drop.style.display = 'none';
    items = [];
    idx = -1;
  }

  function visible(): boolean {
    return !!drop && drop.style.display !== 'none' && items.length > 0;
  }

  function updateHighlight(): void {
    if (!drop) return;
    const els = drop.querySelectorAll<HTMLElement>('.bridge-ac-item');
    els.forEach((el, i) => {
      el.classList.toggle('active', i === idx);
    });
    if (els[idx]) els[idx].scrollIntoView({ block: 'nearest' });
  }

  function confirm(): void {
    if (idx < 0 || idx >= items.length) return;
    const item = items[idx];
    const val = textarea.value;
    if (curMode === 'wc') {
      const before = val.substring(0, wcPrefixPos);
      const after = val.substring(textarea.selectionStart);
      let insert = '__' + item.value + '__';
      if (after && after[0] !== ',' && after[0] !== '\n') insert += ', ';
      textarea.value = before + insert + after;
      const newPos = wcPrefixPos + insert.length;
      textarea.selectionStart = textarea.selectionEnd = newPos;
    } else {
      const before = val.substring(0, tokenStart);
      const after = val.substring(textarea.selectionStart);
      let insert = item.value;
      if (after && after[0] !== ',' && after[0] !== '\n') insert += ', ';
      textarea.value = before + insert + after;
      const newPos = tokenStart + insert.length;
      textarea.selectionStart = textarea.selectionEnd = newPos;
    }
    textarea.focus();
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
    hide();
    if (options.onConfirm) options.onConfirm(item);
  }

  function analyze(): AnalyzeResult | null {
    const val = textarea.value;
    const pos = textarea.selectionStart;
    const left = val.substring(0, pos);

    const wcMatch = left.match(/__([a-zA-Z0-9_/\-]*)$/);
    if (wcMatch) {
      wcPrefixPos = pos - wcMatch[0].length;
      return { mode: 'wc', query: wcMatch[1] };
    }

    const loraMatch = left.match(/<lora:([^>]*)$/);
    if (loraMatch) {
      tokenStart = pos - loraMatch[1].length;
      return { mode: 'lora', query: loraMatch[1] };
    }

    // <embedding:name>, (embedding:name), embedding:name, <hypernet:name>
    const embedMatch = left.match(/(?:<embedding:|<hypernet:|\(embedding:|(?<![<(a-zA-Z])embedding:)([^>):,\s]*)$/i);
    if (embedMatch) {
      tokenStart = pos - embedMatch[1].length;
      return { mode: 'embedding', query: embedMatch[1] };
    }

    const lastSep = Math.max(left.lastIndexOf(','), left.lastIndexOf('\n'));
    const token = left.substring(lastSep + 1).trim();
    tokenStart = lastSep + 1;
    while (tokenStart < pos && (val[tokenStart] === ' ' || val[tokenStart] === '\t')) tokenStart++;
    if (token.length >= MIN_CHARS) return { mode: 'tag', query: token };
    return null;
  }

  function onInput(): void {
    if (debounceTimer) clearTimeout(debounceTimer);
    if (!enabled) {
      hide();
      return;
    }
    // Skip programmatic input events (e.g. PromptSyntaxWidget.setValue dispatched
    // during "previous prompt" restore). Without this guard, restoring a prompt whose last
    // token has no trailing comma leaves the suggestion dropdown stuck open,
    // because the textarea was never focused so blur cannot dismiss it.
    if (document.activeElement !== textarea) {
      hide();
      return;
    }
    const info = analyze();
    if (!info) {
      hide();
      curMode = null;
      return;
    }
    curMode = info.mode;
    if (info.mode === 'wc') {
      searchWc(info.query, show, hide);
      return;
    }
    debounceTimer = setTimeout(() => {
      if (info.mode === 'lora') fetchLora(info.query, options.bridgeBase, show, hide);
      else if (info.mode === 'embedding') fetchEmbedding(info.query, options.bridgeBase, show, hide);
      else fetchTagDict(info.query, show, hide);
    }, DEBOUNCE_MS);
  }

  function setEnabled(flag: boolean): void {
    enabled = !!flag;
    if (!enabled) hide();
  }

  function onKeydown(e: KeyboardEvent): void {
    if (!visible()) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      idx = (idx + 1) % items.length;
      updateHighlight();
      return;
    }
    if (e.key === 'ArrowUp') {
      e.preventDefault();
      idx = (idx - 1 + items.length) % items.length;
      updateHighlight();
      return;
    }
    if (e.key === 'Enter' && e.shiftKey) {
      e.preventDefault();
      confirm();
      return;
    }
    if (e.key === 'Escape') {
      e.preventDefault();
      hide();
      return;
    }
  }

  textarea.addEventListener('input', onInput);
  textarea.addEventListener('keydown', onKeydown);
  textarea.addEventListener('blur', () => setTimeout(hide, 150));

  return { hide, setEnabled };
}

export const BridgeAutocomplete = { attach };
