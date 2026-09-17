let extensionsMenuModulePromise: Promise<typeof import('./extensions-menu')> | null = null;
let textareaDragModulePromise: Promise<typeof import('./textarea-drag')> | null = null;
let konamiModulePromise: Promise<typeof import('./konami')> | null = null;

function loadExtensionsMenu() {
  if (!extensionsMenuModulePromise) extensionsMenuModulePromise = import('./extensions-menu');
  return extensionsMenuModulePromise;
}

function loadKonami() {
  if (!konamiModulePromise) {
    konamiModulePromise = import('./konami').then((mod) => {
      mod.initKonami();
      return mod;
    });
  }
  return konamiModulePromise;
}

function loadTextareaDrag() {
  if (!textareaDragModulePromise) {
    textareaDragModulePromise = import('./textarea-drag').then((mod) => {
      mod.initTextareaDrag();
      return mod;
    }).catch((e) => {
      textareaDragModulePromise = null;
      return Promise.reject(e) as never;
    });
  }
  return textareaDragModulePromise;
}

export async function openExtensionLauncher(): Promise<void> {
  const mod = await loadExtensionsMenu();
  mod.openExtensionLauncher();
}

export function initExtensionsMenuLazy(): void {
  const btn = document.getElementById('navExtBtn');
  if (btn && !btn.dataset.bound) {
    btn.dataset.bound = '1';
    btn.addEventListener('click', (e: Event) => {
      e.stopPropagation();
      openExtensionLauncher().catch(() => {});
    });
  }

  let keyBound = false;
  const bindKeyboard = (): void => {
    if (keyBound) return;
    keyBound = true;
    document.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Escape') return;
      if (e.key.toLowerCase() !== 'e' || e.ctrlKey || e.metaKey || e.altKey) return;
      const target = e.target as HTMLElement | null;
      const tag = target?.tagName || '';
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') return;
      if (target?.isContentEditable) return;
      e.preventDefault();
      openExtensionLauncher().catch(() => {});
    });
  };

  if (btn) bindKeyboard();
}

export function initTextareaDragLazy(): void {
  let loaded = false;
  const maybeLoad = (target: EventTarget | null): void => {
    if (loaded) return;
    const el = target as HTMLElement | null;
    if (!el?.closest('textarea')) return;
    loaded = true;
    document.removeEventListener('focusin', onFocusIn, true);
    document.removeEventListener('mouseover', onMouseOver, true);
    loadTextareaDrag().catch(() => {
      loaded = false;
      document.addEventListener('focusin', onFocusIn, true);
      document.addEventListener('mouseover', onMouseOver, true);
    });
  };
  const onFocusIn = (e: Event): void => { maybeLoad(e.target); };
  const onMouseOver = (e: Event): void => { maybeLoad(e.target); };
  document.addEventListener('focusin', onFocusIn, true);
  document.addEventListener('mouseover', onMouseOver, true);
}

export function initKonamiLazy(): void {
  try {
    if (localStorage.getItem('theme-retro') === '1') document.body.classList.add('theme-retro');
  } catch {
    // ignore storage failures
  }
  const triggerKeys = new Set(['ArrowUp', 'ArrowDown', 'ArrowLeft', 'ArrowRight', 'a', 'b', 'A', 'B']);
  const onKeyDown = (e: KeyboardEvent): void => {
    if (!triggerKeys.has(e.key)) return;
    document.removeEventListener('keydown', onKeyDown, true);
    void loadKonami().then((mod) => {
      mod.handleKonamiKeydown(e.keyCode);
    }).catch(() => {});
  };
  document.addEventListener('keydown', onKeyDown, true);
}
