/**
 * ui/autocomplete-events.ts — Tag autocomplete: keyboard, mouse, and dismiss handlers.
 * Converted from runtime-ui-autocomplete-events.js
 */

export interface ItemsRef {
  get: () => string[];
  set: (v: string[]) => void;
}

export interface ActiveRef {
  get: () => number;
  set: (v: number) => void;
}

export function bindCommaSpaceFix(input: HTMLInputElement): void {
  input.addEventListener('input', (e: Event) => {
    const ie = e as InputEvent;
    if (ie.inputType !== 'insertText' && ie.inputType !== 'insertCompositionText') return;
    if (ie.data !== ',') return;

    const cursorPos = input.selectionStart || 0;
    const value = input.value;
    if (cursorPos >= value.length || value[cursorPos] !== ' ') {
      input.value = value.slice(0, cursorPos) + ' ' + value.slice(cursorPos);
      input.setSelectionRange(cursorPos + 1, cursorPos + 1);
    }
  });
}

export function bindListMouse(
  box: HTMLElement,
  itemsRef: ItemsRef,
  onPick: (item: string) => void,
  onHide: () => void,
): void {
  box.addEventListener('mousedown', (e: MouseEvent) => {
    const el = (e.target as HTMLElement).closest('[data-idx]') as HTMLElement | null;
    if (!el) return;
    const idx = parseInt(el.getAttribute('data-idx') || '0', 10);
    const item = itemsRef.get()[idx];
    if (item) onPick(item);
    onHide();
    e.preventDefault();
  });
}

export function bindKeyboard(
  input: HTMLInputElement,
  box: HTMLElement,
  itemsRef: ItemsRef,
  activeRef: ActiveRef,
  onRender: () => void,
  onPick: (item: string) => void,
  onHide: () => void,
): void {
  input.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape') {
      if (box.style.display === 'block') {
        onHide();
        e.stopPropagation();
        e.preventDefault();
      }
      return;
    }

    if (e.key === 'Enter') {
      // Shift+Enter accepts the highlighted suggestion; plain Enter falls
      // through to normal form submission (search) and just dismisses the box.
      if (box.style.display === 'block') {
        if (e.shiftKey) {
          const items = itemsRef.get();
          const idx = activeRef.get();
          if (items.length && idx >= 0) {
            onPick(items[idx]);
          }
          onHide();
          e.preventDefault();
          return;
        }
        onHide();
      }
      return;
    }

    if (box.style.display !== 'block') return;

    if (e.key === 'ArrowDown') {
      const items = itemsRef.get();
      activeRef.set(Math.min(items.length - 1, activeRef.get() + 1));
      onRender();
      e.preventDefault();
    }
    if (e.key === 'ArrowUp') {
      activeRef.set(Math.max(0, activeRef.get() - 1));
      onRender();
      e.preventDefault();
    }
  });
}

export function bindDismissHandlers(
  input: HTMLInputElement,
  box: HTMLElement,
  onHide: () => void,
  onReposition: () => void,
): () => void {
  const onMouseDown = (e: MouseEvent): void => {
    if (e.target === input || box.contains(e.target as Node)) return;
    onHide();
  };

  document.addEventListener('mousedown', onMouseDown);
  window.addEventListener('scroll', onReposition, { passive: true });
  window.addEventListener('resize', onReposition);

  return () => {
    document.removeEventListener('mousedown', onMouseDown);
    window.removeEventListener('scroll', onReposition);
    window.removeEventListener('resize', onReposition);
  };
}
