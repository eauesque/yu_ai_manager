const OPEN_STORAGE_KEY = 'toolsOpenItems';

interface LazyEntry {
  loader: () => void;
  fired: boolean;
}

const _lazyRegistry = new Map<string, LazyEntry>();

export function registerLazy(id: string, loader: () => void): void {
  _lazyRegistry.set(id, { loader, fired: false });
}

function _dispatchSection(section: HTMLElement): void {
  document.dispatchEvent(new CustomEvent('tools:activate-section', {
    detail: { id: section.id },
  }));
}

function _activateDetails(details: HTMLDetailsElement): void {
  if (!details.id) return;
  const entry = _lazyRegistry.get(details.id);
  if (entry && !entry.fired) {
    entry.fired = true;
    entry.loader();
  }
  details.querySelectorAll<HTMLElement>('.tool-section[id]').forEach(_dispatchSection);
}

function _activateDirectSections(): void {
  document.querySelectorAll<HTMLElement>('.tool-section[id]').forEach(section => {
    if (!section.closest('details.tool-item')) _dispatchSection(section);
  });
}

export function initAccordion(): void {
  const items = document.querySelectorAll<HTMLDetailsElement>('details.tool-item');
  if (!items.length) return;

  let saved: string[] = [];
  try {
    saved = JSON.parse(localStorage.getItem(OPEN_STORAGE_KEY) ?? '[]');
  } catch { /* ignore */ }

  items.forEach(details => {
    if (details.id && saved.includes(details.id)) {
      details.open = true;
      _activateDetails(details);
    }
  });
  _activateDirectSections();

  items.forEach(details => {
    details.addEventListener('toggle', () => {
      const openIds = Array.from(items)
        .filter(d => d.open && d.id)
        .map(d => d.id);
      try {
        localStorage.setItem(OPEN_STORAGE_KEY, JSON.stringify(openIds));
      } catch { /* ignore */ }

      if (details.open && details.id) {
        _activateDetails(details);
      }
    });
  });
}
