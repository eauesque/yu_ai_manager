import { getCaretCoordinates } from '../caret-position';

export interface TooltipOptions {
  candidates: string[];
  tokenStart: number;
  tokenEnd: number;
  textarea: HTMLTextAreaElement;
  onReplace: (candidate: string) => void;
  onIgnore: () => void;
}

let currentPopover: HTMLElement | null = null;
let outsideHandler: ((e: MouseEvent) => void) | null = null;

export function closePopover(): void {
  currentPopover?.remove();
  currentPopover = null;
  if (outsideHandler) { document.removeEventListener('mousedown', outsideHandler); outsideHandler = null; }
}

export function openPopover(opts: TooltipOptions): void {
  closePopover();
  const { candidates, tokenStart, textarea, onReplace, onIgnore } = opts;
  const pop = document.createElement('div');
  pop.className = 'ps-lint-popover';
  pop.setAttribute('role', 'listbox');

  const btns: HTMLButtonElement[] = [];
  for (const cand of candidates) {
    const btn = document.createElement('button');
    btn.setAttribute('role', 'option');
    btn.textContent = cand;
    btn.addEventListener('mousedown', e => e.preventDefault());
    btn.addEventListener('click', () => { closePopover(); onReplace(cand); });
    pop.appendChild(btn);
    btns.push(btn);
  }

  const ignoreBtn = document.createElement('button');
  ignoreBtn.className = 'ps-lint-ignore-btn';
  ignoreBtn.textContent = 'Ignore';
  ignoreBtn.addEventListener('mousedown', e => e.preventDefault());
  ignoreBtn.addEventListener('click', () => { closePopover(); onIgnore(); });
  pop.appendChild(ignoreBtn);
  btns.push(ignoreBtn);

  let focusIdx = 0;
  pop.addEventListener('keydown', e => {
    if (e.key === 'ArrowDown') { e.preventDefault(); focusIdx = (focusIdx + 1) % btns.length; btns[focusIdx].focus(); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); focusIdx = (focusIdx - 1 + btns.length) % btns.length; btns[focusIdx].focus(); }
    else if (e.key === 'Escape') { e.preventDefault(); closePopover(); onIgnore(); }
  });

  document.body.appendChild(pop);
  currentPopover = pop;

  const rect = textarea.getBoundingClientRect();
  const caret = getCaretCoordinates(textarea, tokenStart);
  const top = rect.top + caret.top + caret.height + 2;
  const left = rect.left + caret.left;
  pop.style.top = Math.min(top, window.innerHeight - 200) + 'px';
  pop.style.left = Math.min(Math.max(0, left), window.innerWidth - 270) + 'px';

  outsideHandler = (e: MouseEvent) => { if (!pop.contains(e.target as Node)) closePopover(); };
  setTimeout(() => document.addEventListener('mousedown', outsideHandler!), 0);
  if (btns.length > 0) { btns[0].focus(); focusIdx = 0; }
}
