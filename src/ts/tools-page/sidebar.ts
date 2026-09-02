export type CategoryId = 'search' | 'ai' | 'organize' | 'maintenance' | 'system';

const PANEL_MAP: Record<CategoryId, string> = {
  search:      'toolsCatSearch',
  ai:          'toolsCatAi',
  organize:    'toolsCatOrganize',
  maintenance: 'toolsCatMaintenance',
  system:      'toolsCatSystem',
};

const _categoryLoaded = new Set<CategoryId>();
const _categoryLoaders = new Map<CategoryId, () => void>();
let _manualActiveUntil = 0;

export function registerCategoryLoader(cat: CategoryId, loader: () => void): void {
  _categoryLoaders.set(cat, loader);
}

export function initSidebar(): void {
  const items = document.querySelectorAll<HTMLElement>('[data-cat]');
  if (!items.length) return;

  items.forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      const cat = item.dataset.cat as CategoryId;
      const panelId = PANEL_MAP[cat];
      if (!panelId) return;
      document.getElementById(panelId)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
      _manualActiveUntil = Date.now() + 700;
      _setActive(cat, items);
      _loadCategory(cat);
    });
  });

  if (typeof IntersectionObserver === 'function') {
    const observer = new IntersectionObserver(_onIntersect(items), {
      threshold: 0.15,
      rootMargin: '-44px 0px 0px 0px',
    });
    Object.values(PANEL_MAP).forEach(id => {
      const el = document.getElementById(id);
      if (el) observer.observe(el);
    });
  }
}

function _onIntersect(items: NodeListOf<HTMLElement>) {
  return (entries: IntersectionObserverEntry[]) => {
    if (Date.now() < _manualActiveUntil) return;
    entries.forEach(entry => {
      if (!entry.isIntersecting) return;
      const cat = _catFromPanelId(entry.target.id);
      if (!cat) return;
      _setActive(cat, items);
      _loadCategory(cat);
    });
  };
}

function _loadCategory(cat: CategoryId): void {
  if (_categoryLoaded.has(cat)) return;
  _categoryLoaded.add(cat);
  _categoryLoaders.get(cat)?.();
}

function _setActive(cat: CategoryId, items: NodeListOf<HTMLElement>): void {
  items.forEach(el => {
    el.classList.toggle('tools-sidebar-item--active', el.dataset.cat === cat);
  });
}

function _catFromPanelId(panelId: string): CategoryId | null {
  for (const [cat, id] of Object.entries(PANEL_MAP)) {
    if (id === panelId) return cat as CategoryId;
  }
  return null;
}
