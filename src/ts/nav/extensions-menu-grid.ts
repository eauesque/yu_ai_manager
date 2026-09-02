/**
 * nav/extensions-menu-grid — Grid construction, search/filter, and
 * category management for the Extension Launcher overlay.
 *
 * Extracted from extensions-menu.ts to keep file sizes manageable.
 */

/* ── Interfaces ── */

export interface ExtensionNavChild {
  path: string;
  label: string;
}

export interface ExtensionNav {
  label?: string;
  icon?: string;
  href?: string;
  children?: ExtensionNavChild[];
}

export interface ExtensionInfo {
  name: string;
  type: string;
  category?: string;
  enabled: boolean;
  has_blueprint: boolean;
  blueprint_prefix?: string;
  nav?: ExtensionNav;
}

export interface ExtensionsResponse {
  extensions: ExtensionInfo[];
  category_order?: string[];
}

/* ── Constants ── */

const TYPE_ICONS: Record<string, string> = {
  ui_widget: '\uD83E\uDDEA',    // test tube
  transformer: '\uD83D\uDD04',  // arrows
  exporter: '\uD83D\uDCE4',     // outbox
  general: '\uD83E\uDDE9',      // puzzle
};

const CATEGORY_LABELS: Record<string, string> = {
  metadata: '\uD83D\uDCCB Metadata',
  ai: '\uD83E\uDDE0 AI',
  bridge: '\uD83D\uDD17 Bridge',
  prompt: '\u270F\uFE0F Prompt',
  library: '\uD83D\uDCDA Library',
  system: '\u2699\uFE0F System',
};

export const DEFAULT_CATEGORY_ORDER = ['metadata', 'ai', 'bridge', 'prompt', 'library', 'system'];
const COLLAPSED_KEY = 'ext-launcher-collapsed';

/* ── Helpers ── */

export function escHtml(s: string): string {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(s));
  return d.innerHTML;
}

export function escAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

/* ── localStorage helpers ── */

function getCollapsed(): Set<string> {
  try {
    const raw = localStorage.getItem(COLLAPSED_KEY);
    return raw ? new Set(JSON.parse(raw)) : new Set();
  } catch { return new Set(); }
}

function saveCollapsed(collapsed: Set<string>): void {
  try { localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...collapsed])); } catch { /* noop */ }
}

/* ── Grid building ── */

export function buildGrid(
  extensions: ExtensionInfo[],
  categoryOrder: string[],
  bodyEl: HTMLElement,
): void {
  const items = extensions.filter(
    (e) => e.has_blueprint && e.enabled && e.nav && Object.keys(e.nav).length > 0,
  );

  if (!items.length) {
    bodyEl.innerHTML = '<div class="ext-launcher-empty">No extensions available</div>';
    return;
  }

  // Group by category
  const order = categoryOrder.length ? categoryOrder : DEFAULT_CATEGORY_ORDER;
  const grouped = new Map<string, ExtensionInfo[]>();
  for (const e of items) {
    const cat = e.category || 'system';
    if (!grouped.has(cat)) grouped.set(cat, []);
    grouped.get(cat)!.push(e);
  }

  // Build ordered category list (known order + remaining)
  const catKeys: string[] = [];
  for (const cat of order) {
    if (grouped.has(cat)) catKeys.push(cat);
  }
  for (const cat of grouped.keys()) {
    if (!catKeys.includes(cat)) catKeys.push(cat);
  }

  const collapsed = getCollapsed();
  let html = '';

  for (const cat of catKeys) {
    const group = grouped.get(cat)!;
    const catLabel = CATEGORY_LABELS[cat] || cat;
    const isCollapsed = collapsed.has(cat);

    html += '<div class="ext-launcher-section' + (isCollapsed ? ' collapsed' : '') + '" data-category="' + cat + '">';
    html += '<button class="ext-launcher-section-header" type="button">';
    html += '<span>' + catLabel + '</span>';
    html += '<span class="ext-launcher-chevron">\u25BE</span>';
    html += '</button>';
    html += '<div class="ext-launcher-grid">';

    for (const e of group) {
      const nav = e.nav || {};
      const label = nav.label || e.name;
      const icon = nav.icon || TYPE_ICONS[e.type] || '\uD83E\uDDE9';
      const href = nav.href || e.blueprint_prefix || '#';
      const hasChildren = nav.children && nav.children.length > 0;
      const dataAttr = ' data-name="' + escAttr(label) + '"';

      if (hasChildren) {
        // Card with children -> click shows popover
        html += '<div class="ext-launcher-card" tabindex="0"' + dataAttr + '>';
        html += '<div class="ext-launcher-icon">' + icon + '</div>';
        html += '<div class="ext-launcher-label">' + escHtml(label) + '</div>';
        html += '<div class="ext-launcher-children">';
        html += '<a class="ext-launcher-child-link ext-launcher-child-main" href="' + escAttr(href) + '">' + escHtml(label) + '</a>';
        for (const c of nav.children!) {
          html += '<a class="ext-launcher-child-link" href="' + escAttr(href + c.path) + '">' + escHtml(c.label) + '</a>';
        }
        html += '</div>';
        html += '</div>';
      } else {
        // Simple card -> direct link
        html += '<a class="ext-launcher-card" href="' + escAttr(href) + '"' + dataAttr + '>';
        html += '<div class="ext-launcher-icon">' + icon + '</div>';
        html += '<div class="ext-launcher-label">' + escHtml(label) + '</div>';
        html += '</a>';
      }
    }

    html += '</div></div>';
  }

  bodyEl.innerHTML = html;

  // Attach category toggle handlers
  bodyEl.querySelectorAll<HTMLElement>('.ext-launcher-section-header').forEach((btn) => {
    btn.addEventListener('click', () => {
      const section = btn.closest('.ext-launcher-section') as HTMLElement;
      if (!section) return;
      section.classList.toggle('collapsed');
      const cat = section.getAttribute('data-category') || '';
      const c = getCollapsed();
      if (section.classList.contains('collapsed')) c.add(cat);
      else c.delete(cat);
      saveCollapsed(c);
    });
  });

  // Attach children popover handlers
  bodyEl.querySelectorAll<HTMLElement>('.ext-launcher-card[tabindex]').forEach((card) => {
    card.addEventListener('click', (e: Event) => {
      // Don't toggle if clicking a child link
      if ((e.target as HTMLElement).closest('.ext-launcher-child-link')) return;
      e.preventDefault();
      // Close other popovers
      bodyEl.querySelectorAll('.ext-launcher-card.show-children').forEach((c) => {
        if (c !== card) c.classList.remove('show-children');
      });
      card.classList.toggle('show-children');
    });
  });

  // Close children popovers when clicking outside
  bodyEl.addEventListener('click', (e: Event) => {
    if (!(e.target as HTMLElement).closest('.ext-launcher-card[tabindex]')) {
      bodyEl.querySelectorAll('.ext-launcher-card.show-children').forEach((c) => {
        c.classList.remove('show-children');
      });
    }
  });
}

/* ── Search / filter ── */

export function onSearch(
  bodyEl: HTMLElement,
  searchInput: HTMLInputElement,
  noResults: HTMLElement,
): void {
  const q = searchInput.value.toLowerCase().trim();

  const cards = bodyEl.querySelectorAll<HTMLElement>('.ext-launcher-card');
  let anyVisible = false;

  cards.forEach((card) => {
    const name = (card.getAttribute('data-name') || '').toLowerCase();
    const match = !q || name.includes(q);
    card.classList.toggle('hidden', !match);
    if (match) anyVisible = true;
  });

  // Hide empty sections
  bodyEl.querySelectorAll<HTMLElement>('.ext-launcher-section').forEach((section) => {
    const hasVisible = section.querySelector('.ext-launcher-card:not(.hidden)');
    section.style.display = hasVisible ? '' : 'none';
    // Temporarily expand when searching
    if (q && hasVisible) section.classList.remove('collapsed');
  });

  noResults.style.display = anyVisible || !q ? 'none' : 'block';

  // Restore collapsed state when search is cleared
  if (!q) {
    const collapsed = getCollapsed();
    bodyEl.querySelectorAll<HTMLElement>('.ext-launcher-section').forEach((section) => {
      section.style.display = '';
      const cat = section.getAttribute('data-category') || '';
      section.classList.toggle('collapsed', collapsed.has(cat));
    });
  }
}
