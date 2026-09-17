/**
 * BridgeResultPanel — 2-column layout with controls (left) + result panel (right).
 * Replaces BridgeGenThumbnails with richer result display + history grid.
 *
 * Responsive history layout:
 *   - Wide viewports (>= FILMSTRIP_BREAKPOINT) get a ComfyUI-style horizontal
 *     filmstrip below the result area. Easier to scan many sweep results
 *     without scrolling the right column.
 *   - Narrower viewports stay with the original right-column grid.
 * Switch happens live via matchMedia listener; entries re-bind to the
 * active container.
 */

import { createHistoryStore, type HistoryStoreEntry } from './history-store';
import { buildHistoryEntry, showEntry } from './result-panel-view';

export interface ResultPanelAction {
  label: string;
  title?: string;
  onClick: (base64: string) => void;
}

export interface ResultPanelConfig {
  prefix: string;
  containerSelector?: string;
  actions?: ResultPanelAction[];
}

export interface CharacterPrompt {
  prompt?: string;
  negative?: string;
  center?: { x: number; y: number };
}

export interface AdetailerEntry {
  model?: string;
  prompt?: string;
  negative?: string;
}

export interface ResultData {
  elapsed_ms?: number;
  expanded_prompt?: string;
  original_prompt?: string;
  final_negative?: string;
  characters?: CharacterPrompt[];
  adetailer?: AdetailerEntry[];
  saved?: string[];
}

export interface ResultPanelInstance {
  update: (images: Array<{ base64?: string; seed?: number | string }>, format?: string, resultData?: ResultData) => void;
  clear: () => void;
}

const FILMSTRIP_BREAKPOINT = '(min-width: 1600px)';

function makeEl(tag: string, opts?: { className?: string; id?: string; text?: string; title?: string; dataset?: Record<string, string> }): HTMLElement {
  const el = document.createElement(tag);
  if (opts?.className) el.className = opts.className;
  if (opts?.id) el.id = opts.id;
  if (opts?.text != null) el.textContent = opts.text;
  if (opts?.title) el.title = opts.title;
  if (opts?.dataset) {
    for (const [k, v] of Object.entries(opts.dataset)) el.dataset[k] = v;
  }
  return el;
}

function attach(config: ResultPanelConfig): ResultPanelInstance | null {
  const prefix = config.prefix || '';
  const containerSel = config.containerSelector || '.' + prefix + '-container';
  const container = document.querySelector<HTMLElement>(containerSel);
  if (!container) return null;

  // Already wrapped — idempotent guard
  if (container.querySelector('.brp-left')) return null;

  const resultEl = document.getElementById(prefix + 'Result');
  if (!resultEl) return null;

  // --- Build layout wrapper ---
  const layout = makeEl('div', { className: 'brp-layout' });
  const left = makeEl('div', { className: 'brp-left' });
  const right = makeEl('div', { className: 'brp-right' });

  // Right panel: latest preview + meta + sidebar history
  const latestEl = makeEl('div', { className: 'brp-latest', id: prefix + 'BrpLatest' });
  latestEl.appendChild(makeEl('div', { className: 'brp-latest-empty', text: 'No images yet' }));
  right.appendChild(latestEl);

  const metaEl = makeEl('div', { className: 'brp-meta', id: prefix + 'BrpMeta' });
  right.appendChild(metaEl);

  const sideHeader = makeEl('div', { className: 'brp-history-header brp-history-sidebar-header' });
  sideHeader.appendChild(makeEl('span', { text: 'History' }));
  const sideClearBtn = makeEl('button', { className: 'brp-clear-btn', text: '×', title: 'クリア' });
  sideHeader.appendChild(sideClearBtn);
  right.appendChild(sideHeader);

  const sidebarHistoryEl = makeEl('div', { className: 'brp-history brp-history-sidebar', id: prefix + 'BrpHistory' });
  right.appendChild(sidebarHistoryEl);

  // Move all existing controls into left column
  while (container.firstChild) {
    left.appendChild(container.firstChild);
  }
  if (resultEl.parentNode === left) {
    left.removeChild(resultEl);
  }
  resultEl.style.display = 'none';
  left.appendChild(resultEl);

  layout.appendChild(left);
  layout.appendChild(right);

  // Bottom filmstrip — full width, sits below the 2-column layout. Hidden
  // when the sidebar mode is active.
  const filmstripWrap = makeEl('div', { className: 'brp-filmstrip-wrap' });
  const filmHeader = makeEl('div', { className: 'brp-history-header brp-filmstrip-header' });
  filmHeader.appendChild(makeEl('span', { text: 'History' }));
  const filmClearBtn = makeEl('button', { className: 'brp-clear-btn', text: '×', title: 'クリア' });
  filmHeader.appendChild(filmClearBtn);
  filmstripWrap.appendChild(filmHeader);
  const filmstripHistoryEl = makeEl('div', { className: 'brp-history brp-filmstrip', id: prefix + 'BrpFilmstrip' });
  filmstripWrap.appendChild(filmstripHistoryEl);

  container.appendChild(layout);
  container.appendChild(filmstripWrap);

  const actions = config.actions || [];
  const store = createHistoryStore();

  let activeMode: 'sidebar' | 'filmstrip' = 'sidebar';
  let activeContainer: HTMLElement = sidebarHistoryEl;

  function thumbContainerFor(mode: 'sidebar' | 'filmstrip'): HTMLElement {
    return mode === 'filmstrip' ? filmstripHistoryEl : sidebarHistoryEl;
  }

  function buildThumb(entry: HistoryStoreEntry): HTMLElement {
    const thumb = makeEl('div', { className: 'brp-thumb' });
    const imgEl = document.createElement('img');
    imgEl.src = entry.src;
    imgEl.alt = 'Seed: ' + entry.seed;
    imgEl.loading = 'lazy';
    thumb.appendChild(imgEl);

    thumb.addEventListener('click', () => {
      showEntry(entry, latestEl, metaEl, actions);
      activeContainer.querySelectorAll('.brp-thumb').forEach((t) => t.classList.remove('active'));
      thumb.classList.add('active');
    });

    return thumb;
  }

  function reattachAll(): void {
    sidebarHistoryEl.textContent = '';
    filmstripHistoryEl.textContent = '';
    store.entries.forEach((e) => {
      const thumb = buildThumb(e);
      e.thumbEl = thumb;
      activeContainer.appendChild(thumb);
    });
  }

  function applyMode(mode: 'sidebar' | 'filmstrip'): void {
    if (mode === activeMode) return;
    activeMode = mode;
    activeContainer = thumbContainerFor(mode);
    if (mode === 'filmstrip') {
      filmstripWrap.classList.add('active');
      right.classList.add('history-hidden');
    } else {
      filmstripWrap.classList.remove('active');
      right.classList.remove('history-hidden');
    }
    reattachAll();
  }

  // Wire mode-switch via matchMedia.
  const mq = window.matchMedia(FILMSTRIP_BREAKPOINT);
  function syncFromMq(): void {
    applyMode(mq.matches ? 'filmstrip' : 'sidebar');
  }
  // Initial state without the no-op guard
  activeMode = mq.matches ? 'filmstrip' : 'sidebar';
  activeContainer = thumbContainerFor(activeMode);
  if (activeMode === 'filmstrip') {
    filmstripWrap.classList.add('active');
    right.classList.add('history-hidden');
  }
  if (typeof mq.addEventListener === 'function') {
    mq.addEventListener('change', syncFromMq);
  } else if (typeof (mq as MediaQueryList & { addListener?: (l: () => void) => void }).addListener === 'function') {
    (mq as MediaQueryList & { addListener: (l: () => void) => void }).addListener(syncFromMq);
  }

  sideClearBtn.addEventListener('click', () => clear());
  filmClearBtn.addEventListener('click', () => clear());

  store.onEvict = (e) => {
    if (e.thumbEl && e.thumbEl.parentNode) {
      e.thumbEl.parentNode.removeChild(e.thumbEl);
    }
  };
  store.onDownsample = (e) => {
    if (!e.thumbEl) return;
    const im = e.thumbEl.querySelector('img');
    if (im) im.src = e.src;
  };

  function update(images: Array<{ base64?: string; seed?: number | string }>, format?: string, resultData?: ResultData): void {
    if (!images || !images.length) return;
    const mime = format || 'image/png';

    images.forEach((img) => {
      const built = buildHistoryEntry(img, mime, resultData);
      if (!built) return;
      const entry = store.add(built);

      showEntry(entry, latestEl, metaEl, actions);

      const thumb = buildThumb(entry);
      entry.thumbEl = thumb;
      activeContainer.insertBefore(thumb, activeContainer.firstChild);
    });
  }

  function clear(): void {
    store.clear();
    latestEl.textContent = '';
    latestEl.appendChild(makeEl('div', { className: 'brp-latest-empty', text: 'No images yet' }));
    metaEl.textContent = '';
    sidebarHistoryEl.textContent = '';
    filmstripHistoryEl.textContent = '';
  }

  return { update, clear };
}

export const BridgeResultPanel = { attach };

// Backward compatibility alias
export const BridgeGenThumbnails = BridgeResultPanel;

export type MultiServerPanelInstance = { update: () => void; clear: () => void }

export function attachMultiServer(
  containerEl: HTMLElement,
  getTasks: () => Map<string, { backend: { name: string; color: string } | null; status: string; progress: number; images: Array<{ url: string; received_at_ms: number }>; error_message?: string }>,
  targetKind: 'server' | 'group' | 'default',
  groupName?: string,
): MultiServerPanelInstance {
  let unified = false

  const toggleBtn = document.createElement('button')
  toggleBtn.className = 'result-view-toggle'
  toggleBtn.textContent = 'Unified View'
  toggleBtn.addEventListener('click', () => {
    unified = !unified
    toggleBtn.textContent = unified ? 'Swimlane View' : 'Unified View'
    _render()
  })
  containerEl.appendChild(toggleBtn)

  const root = document.createElement('div')
  root.className = 'multi-server-results'
  containerEl.appendChild(root)

  function _render(): void {
    while (root.firstChild) root.removeChild(root.firstChild)
    const tasks = getTasks()
    if (unified) {
      _renderUnified(root, tasks)
    } else {
      _renderSwimlanes(root, tasks, targetKind, groupName)
    }
  }

  _render()
  return {
    update: () => _render(),
    clear: () => _render(),
  }
}

function _renderSwimlanes(
  root: HTMLElement,
  tasks: Map<string, { backend: { name: string; color: string } | null; status: string; progress: number; images: Array<{ url: string; received_at_ms: number }>; error_message?: string }>,
  targetKind: string,
  groupName?: string,
): void {
  if (targetKind === 'group' && groupName) {
    const hdr = document.createElement('div')
    hdr.className = 'swimlane-group-header'
    hdr.textContent = 'Groups: ' + groupName
    hdr.addEventListener('click', () => {
      const next = hdr.nextElementSibling as HTMLElement | null
      if (next) next.style.display = next.style.display === 'none' ? '' : 'none'
    })
    root.appendChild(hdr)
    const body = document.createElement('div')
    root.appendChild(body)
    for (const [, s] of tasks) body.appendChild(_swimlane(s))
  } else {
    for (const [, s] of tasks) root.appendChild(_swimlane(s))
  }
}

function _renderUnified(
  root: HTMLElement,
  tasks: Map<string, { backend: { name: string; color: string } | null; images: Array<{ url: string; received_at_ms: number }> }>,
): void {
  const all: Array<{ url: string; received_at_ms: number; color: string }> = []
  for (const [, s] of tasks) {
    const color = s.backend?.color ?? '#888'
    for (const img of s.images) all.push({ ...img, color })
  }
  all.sort((a, b) => a.received_at_ms - b.received_at_ms)

  const strip = document.createElement('div')
  strip.className = 'unified-filmstrip'
  for (const item of all) {
    const thumb = document.createElement('div')
    thumb.className = 'filmstrip-thumb'
    const img = document.createElement('img')
    img.src = item.url
    const badge = document.createElement('span')
    badge.className = 'backend-color-badge'
    badge.style.background = item.color
    thumb.appendChild(img)
    thumb.appendChild(badge)
    strip.appendChild(thumb)
  }
  root.appendChild(strip)
}

function _swimlane(
  s: { backend: { name: string; color: string } | null; status: string; progress: number; images: Array<{ url: string }>; error_message?: string },
): HTMLElement {
  const lane = document.createElement('div')
  lane.className = 'swimlane'

  const hdr = document.createElement('div')
  hdr.className = 'swimlane-header'
  const dot = document.createElement('span')
  dot.className = 'status-dot'
  dot.style.background = s.backend?.color ?? '#888'
  hdr.appendChild(dot)
  hdr.appendChild(document.createTextNode(' ' + (s.backend?.name ?? 'Default')))
  lane.appendChild(hdr)

  if (s.status === 'generating') {
    const pb = document.createElement('div')
    pb.className = 'progress-bar'
    const fill = document.createElement('div')
    fill.className = 'progress-fill'
    fill.style.width = s.progress + '%'
    pb.appendChild(fill)
    lane.appendChild(pb)
  }

  if (s.status === 'error' && s.error_message) {
    const err = document.createElement('div')
    err.className = 'swimlane-error'
    err.textContent = s.error_message
    lane.appendChild(err)
  }

  const imgs = document.createElement('div')
  imgs.className = 'swimlane-images'
  for (const i of s.images) {
    const imgEl = document.createElement('img')
    imgEl.src = i.url
    imgs.appendChild(imgEl)
  }
  lane.appendChild(imgs)
  return lane
}
