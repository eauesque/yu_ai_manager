import { splitIntoRawTokens, detectDuplicates } from './linter-duplicate';
import type { SyntaxMode } from './linter-duplicate';
import { checkSpelling, toQueryForm } from './linter-spell';
import type { SpellError } from './linter-spell';
import { buildOverlayHtml, syncLayout } from './linter-render';
import { openPopover, closePopover } from './linter-tooltip';

export interface PromptLinterOptions {
  spellCheck?: boolean;
  dupCheck?: boolean;
  debounceMs?: number;
  syntaxMode?: SyntaxMode;
  hasSyntaxWidget?: boolean;
}
export interface PromptLinterHandle { detach(): void; }

export function attach(textarea: HTMLTextAreaElement, opts: PromptLinterOptions = {}): PromptLinterHandle {
  const spellCheck = opts.spellCheck !== false;
  const dupCheck = opts.dupCheck !== false;
  const debounceMs = opts.debounceMs ?? 400;
  const syntaxMode: SyntaxMode = opts.syntaxMode ?? 'unknown';
  const hasPSW = !!opts.hasSyntaxWidget;

  const lintDiv = document.createElement('div');
  lintDiv.className = 'ps-lint-layer';
  lintDiv.setAttribute('aria-hidden', 'true');
  lintDiv.setAttribute('data-1p-ignore', '');
  lintDiv.setAttribute('data-lpignore', 'true');
  lintDiv.style.position = 'absolute';
  lintDiv.style.top = '0';
  lintDiv.style.left = '0';
  lintDiv.style.width = '100%';
  lintDiv.style.height = '100%';
  lintDiv.style.pointerEvents = 'none';
  lintDiv.style.color = 'transparent';
  lintDiv.style.zIndex = '1';
  lintDiv.style.overflow = 'hidden';

  let wrapper: HTMLElement | null = null;
  let origParent: Element | null = null;
  let origNext: ChildNode | null = null;

  if (hasPSW) {
    // PSW context: insert lintDiv after the syntax div (later sibling with same z-index paints on top)
    // DOM order: [syntax div z:1] -> [lint div z:1] -> textarea (z:2, receives input)
    const parent = textarea.parentElement!;
    const taIdx = Array.from(parent.children).indexOf(textarea);
    if (taIdx > 0) (parent.children[taIdx - 1] as HTMLElement).after(lintDiv);
    else parent.insertBefore(lintDiv, textarea);
  } else {
    // Plain context: wrap textarea; lint div AFTER textarea so it paints above (z-index 1 > 0)
    origParent = textarea.parentElement;
    origNext = textarea.nextSibling;
    wrapper = document.createElement('div');
    wrapper.style.cssText = 'position:relative;display:inline-block;';
    textarea.style.position = 'relative';
    textarea.style.zIndex = '0';
    origParent?.insertBefore(wrapper, textarea);
    wrapper.appendChild(textarea);
    wrapper.appendChild(lintDiv);
  }

  syncLayout(lintDiv, textarea);

  const ignoreSet = new Set<string>();
  let runId = 0;
  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let lastSpellErrors: SpellError[] = [];

  async function lint(): Promise<void> {
    const text = textarea.value;
    const cur = ++runId;
    const dups = dupCheck ? detectDuplicates(text, syntaxMode) : [];
    const tokens = splitIntoRawTokens(text);
    const spellErrors = spellCheck
      ? await checkSpelling(tokens, syntaxMode, cur, () => runId, ignoreSet)
      : [];
    if (runId !== cur) return;
    lastSpellErrors = spellErrors;
    lintDiv.innerHTML = buildOverlayHtml(text, dups, spellErrors);
    lintDiv.scrollTop = textarea.scrollTop;
    lintDiv.scrollLeft = textarea.scrollLeft;
  }

  function onInput(): void {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => void lint(), debounceMs);
  }

  function onScroll(): void {
    lintDiv.scrollTop = textarea.scrollTop;
    lintDiv.scrollLeft = textarea.scrollLeft;
  }

  function onClick(e: MouseEvent): void {
    if (e.detail !== 1) return;
    const idx = textarea.selectionStart;
    if (idx !== textarea.selectionEnd) return;
    const err = lastSpellErrors.find(s => s.start <= idx && idx < s.end);
    if (!err) return;
    openPopover({
      candidates: err.candidates,
      tokenStart: err.start,
      tokenEnd: err.end,
      textarea,
      onReplace(cand: string) {
        const val = textarea.value;
        textarea.focus();
        textarea.setSelectionRange(err.start, err.end);
        try {
          if (!document.execCommand('insertText', false, cand)) throw new Error('execCommand failed');
        } catch {
          textarea.value = val.slice(0, err.start) + cand + val.slice(err.end);
          textarea.setSelectionRange(err.start + cand.length, err.start + cand.length);
          textarea.dispatchEvent(new Event('input', { bubbles: true }));
        }
        textarea.focus();
      },
      onIgnore() {
        const raw = textarea.value.slice(err.start, err.end);
        ignoreSet.add(toQueryForm(raw));
        void lint();
      },
    });
  }

  function onMouseMove(e: MouseEvent): void {
    const els = lintDiv.querySelectorAll<HTMLElement>('.ps-lint-spell');
    let over = false;
    for (const el of els) {
      const r = el.getBoundingClientRect();
      if (e.clientX >= r.left && e.clientX <= r.right && e.clientY >= r.top && e.clientY <= r.bottom) { over = true; break; }
    }
    textarea.style.cursor = over ? 'pointer' : '';
  }

  function updateLayout(): void {
    syncLayout(lintDiv, textarea);
    lintDiv.scrollTop = textarea.scrollTop;
    lintDiv.scrollLeft = textarea.scrollLeft;
  }

  const ro = new ResizeObserver(updateLayout);
  ro.observe(wrapper ?? textarea.parentElement ?? textarea);

  textarea.addEventListener('input', onInput);
  textarea.addEventListener('scroll', onScroll);
  textarea.addEventListener('click', onClick);
  textarea.addEventListener('mousemove', onMouseMove);

  return {
    detach() {
      if (debounceTimer) clearTimeout(debounceTimer);
      closePopover();
      ro.disconnect();
      textarea.removeEventListener('input', onInput);
      textarea.removeEventListener('scroll', onScroll);
      textarea.removeEventListener('click', onClick);
      textarea.removeEventListener('mousemove', onMouseMove);
      textarea.style.cursor = '';
      lintDiv.remove();
      if (wrapper && origParent) {
        origParent.insertBefore(textarea, origNext ?? null);
        textarea.style.position = '';
        textarea.style.zIndex = '';
        wrapper.remove();
      }
    },
  };
}
