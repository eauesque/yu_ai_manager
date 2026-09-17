import { axisCaption, truncate } from './sweep-view-format';
import { tr } from './sweep-view-i18n';
import type { FileMeta, SweepFilesEntry } from './sweep-view-types';

interface LightboxRefs {
  overlay: HTMLDivElement;
  img: HTMLImageElement;
  info: HTMLDivElement;
  counter: HTMLDivElement;
  toggleBtn: HTMLButtonElement;
}

const _entries: SweepFilesEntry[] = [];
const _metaCache = new Map<number, FileMeta>();
const _metaInflight = new Map<number, Promise<FileMeta | null>>();
let _lightbox: LightboxRefs | null = null;
let _lightboxIndex = 0;
let _lightboxInfoVisible = (() => {
  if (typeof localStorage === 'undefined') return true;
  const v = localStorage.getItem('sweepView.lightboxInfo');
  return v === null ? true : v === '1';
})();

export function clearLightboxEntries(): void {
  _entries.length = 0;
}

export function registerLightboxEntry(m: SweepFilesEntry): number {
  const index = _entries.length;
  _entries.push(m);
  return index;
}

export function openLightbox(index: number): void {
  const refs = ensureLightbox();
  renderLightboxAt(index);
  refs.overlay.style.display = 'flex';
  document.documentElement.style.overflow = 'hidden';
  document.addEventListener('keydown', onLightboxKey);
}

async function fetchFileMeta(id: number): Promise<FileMeta | null> {
  const cached = _metaCache.get(id);
  if (cached) return cached;
  const inflight = _metaInflight.get(id);
  if (inflight) return inflight;
  const p = (async () => {
    try {
      const r = await fetch(`/api/file/${id}`, { headers: { 'X-Requested-With': 'XMLHttpRequest' } });
      if (!r.ok) return null;
      const data: FileMeta = await r.json();
      _metaCache.set(id, data);
      return data;
    } catch (_e) {
      return null;
    } finally {
      _metaInflight.delete(id);
    }
  })();
  _metaInflight.set(id, p);
  return p;
}

function renderInfoInto(host: HTMLElement, m: SweepFilesEntry, meta: FileMeta | null): void {
  host.textContent = '';
  const axisLine = document.createElement('div');
  axisLine.style.cssText = 'font-size:13px;font-weight:600;color:#fff;margin-bottom:6px;';
  axisLine.textContent = axisCaption(m);
  host.appendChild(axisLine);

  const params = (meta?.parameters as Record<string, unknown> | undefined) || undefined;
  const chips: { icon: string; text: string }[] = [];
  if (params) {
    if (params.Seed != null) chips.push({ icon: '🎲', text: String(params.Seed) });
    if (typeof meta?.model === 'string' && meta.model) chips.push({ icon: '🎨', text: meta.model });
    if (params.Steps != null) chips.push({ icon: '⚙', text: `Steps ${params.Steps}` });
    if (params.Sampler != null) chips.push({ icon: '🧪', text: String(params.Sampler) });
    if (params['CFG scale'] != null) chips.push({ icon: '⚖', text: `CFG ${params['CFG scale']}` });
  }
  if (chips.length) {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;flex-wrap:wrap;gap:8px;margin-bottom:8px;font-size:12px;color:#eee;';
    for (const c of chips) {
      const chip = document.createElement('span');
      chip.style.cssText =
        'padding:2px 8px;border:1px solid rgba(255,255,255,0.2);' +
        'border-radius:10px;background:rgba(255,255,255,0.06);font-family:monospace;';
      chip.textContent = `${c.icon} ${c.text}`;
      row.appendChild(chip);
    }
    host.appendChild(row);
  }
  appendPromptBlock(host, meta?.positive || meta?.positive_prompt || '', 'pos');
  appendPromptBlock(host, meta?.negative || meta?.negative_prompt || '', 'neg');
  const pathLine = document.createElement('div');
  pathLine.style.cssText = 'font-size:11px;color:#888;font-family:monospace;text-align:left;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;';
  pathLine.textContent = m.path;
  pathLine.title = m.path;
  host.appendChild(pathLine);
  if (meta == null && m.file_id != null) {
    const loading = document.createElement('div');
    loading.style.cssText = 'font-size:11px;color:#777;margin-top:4px;';
    loading.textContent = tr('sweep_view.lightbox_loading_meta', 'Loading metadata…');
    host.appendChild(loading);
  }
}

function appendPromptBlock(host: HTMLElement, text: string, kind: 'pos' | 'neg'): void {
  if (!text) return;
  const el = document.createElement('div');
  el.style.cssText = kind === 'pos'
    ? 'font-size:12px;color:#dde;line-height:1.45;text-align:left;max-height:6em;overflow:auto;white-space:pre-wrap;word-break:break-word;padding:6px 8px;background:rgba(255,255,255,0.04);border-radius:4px;margin-bottom:6px;'
    : 'font-size:11px;color:#caa;line-height:1.4;text-align:left;max-height:4em;overflow:auto;white-space:pre-wrap;word-break:break-word;padding:6px 8px;background:rgba(120,40,40,0.18);border-radius:4px;margin-bottom:6px;';
  el.textContent = kind === 'pos' ? truncate(text, 800) : '⊘ ' + truncate(text, 400);
  el.title = text;
  host.appendChild(el);
}

function ensureLightbox(): LightboxRefs {
  if (_lightbox) return _lightbox;
  const overlay = document.createElement('div');
  overlay.id = 'sweepViewLightbox';
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.92);z-index:9999;display:none;flex-direction:column;align-items:stretch;justify-content:center;';
  const stage = document.createElement('div');
  stage.style.cssText = 'flex:1;display:flex;align-items:center;justify-content:center;position:relative;min-height:0;padding:48px 64px 8px;';
  const img = document.createElement('img');
  img.style.cssText = 'max-width:100%;max-height:100%;object-fit:contain;box-shadow:0 4px 32px rgba(0,0,0,0.6);background:#000;';
  stage.appendChild(img);
  stage.appendChild(navBtn('‹', 'left', -1));
  stage.appendChild(navBtn('›', 'right', +1));
  const topRight = document.createElement('div');
  topRight.style.cssText = 'position:absolute;top:8px;right:12px;display:flex;gap:6px;z-index:1;';
  const toggleBtn = smallButton('ℹ', tr('sweep_view.lightbox_toggle_info', 'Toggle info bar (i)'));
  toggleBtn.addEventListener('click', (ev) => { ev.stopPropagation(); toggleLightboxInfo(); });
  topRight.appendChild(toggleBtn);
  const closeBtn = smallButton('×', tr('sweep_view.lightbox_close', 'Close'));
  closeBtn.setAttribute('aria-label', tr('sweep_view.lightbox_close', 'Close'));
  closeBtn.addEventListener('click', (ev) => { ev.stopPropagation(); closeLightbox(); });
  topRight.appendChild(closeBtn);
  overlay.appendChild(topRight);
  const counter = document.createElement('div');
  counter.style.cssText = 'position:absolute;top:14px;left:16px;font-size:13px;color:#ddd;font-family:monospace;';
  overlay.appendChild(counter);
  const info = document.createElement('div');
  info.style.cssText = 'flex:0 0 30vh;box-sizing:border-box;padding:10px 14px;color:#eee;background:rgba(0,0,0,0.55);overflow:auto;border-top:1px solid rgba(255,255,255,0.08);';
  overlay.appendChild(stage);
  overlay.appendChild(info);
  overlay.addEventListener('click', (ev) => { if (ev.target === overlay) closeLightbox(); });
  document.body.appendChild(overlay);
  _lightbox = { overlay, img, info, counter, toggleBtn };
  applyLightboxInfoVisibility();
  return _lightbox;
}

function smallButton(text: string, title: string): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = text;
  btn.title = title;
  btn.style.cssText = 'width:36px;height:36px;font-size:18px;line-height:1;background:rgba(0,0,0,0.6);color:#fff;border:1px solid rgba(255,255,255,0.25);border-radius:4px;cursor:pointer;';
  return btn;
}

function navBtn(text: string, side: 'left' | 'right', delta: number): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = text;
  btn.style.cssText = `position:absolute;top:50%;${side}:8px;transform:translateY(-50%);width:48px;height:64px;font-size:28px;line-height:1;background:rgba(0,0,0,0.5);color:#fff;border:1px solid rgba(255,255,255,0.25);border-radius:4px;cursor:pointer;`;
  btn.addEventListener('click', (ev) => { ev.stopPropagation(); navLightbox(delta); });
  return btn;
}

function applyLightboxInfoVisibility(): void {
  if (!_lightbox) return;
  _lightbox.info.style.display = _lightboxInfoVisible ? '' : 'none';
  _lightbox.toggleBtn.style.background = _lightboxInfoVisible ? 'rgba(79,195,247,0.7)' : 'rgba(0,0,0,0.6)';
  _lightbox.toggleBtn.style.color = _lightboxInfoVisible ? '#000' : '#fff';
}

function toggleLightboxInfo(): void {
  _lightboxInfoVisible = !_lightboxInfoVisible;
  try { localStorage.setItem('sweepView.lightboxInfo', _lightboxInfoVisible ? '1' : '0'); } catch (_e) { /* no-op */ }
  applyLightboxInfoVisibility();
}

function onLightboxKey(ev: KeyboardEvent): void {
  if (!_lightbox || _lightbox.overlay.style.display === 'none') return;
  if (ev.key === 'Escape') { ev.preventDefault(); closeLightbox(); }
  else if (ev.key === 'ArrowRight' || ev.key === ' ') { ev.preventDefault(); navLightbox(+1); }
  else if (ev.key === 'ArrowLeft') { ev.preventDefault(); navLightbox(-1); }
  else if (ev.key === 'i' || ev.key === 'I') { ev.preventDefault(); toggleLightboxInfo(); }
}

function renderLightboxAt(index: number): void {
  const refs = ensureLightbox();
  const total = _entries.length;
  if (total === 0) return;
  const safeIdx = ((index % total) + total) % total;
  _lightboxIndex = safeIdx;
  const m = _entries[safeIdx];
  refs.img.src = m.file_id != null ? `/api/original/${m.file_id}` : '';
  refs.img.alt = m.path;
  refs.counter.textContent = `${safeIdx + 1} / ${total}`;
  const cached = m.file_id != null ? _metaCache.get(m.file_id) ?? null : null;
  renderInfoInto(refs.info, m, cached);
  if (m.file_id != null && cached == null) {
    const expectedIdx = safeIdx;
    void fetchFileMeta(m.file_id).then((meta) => {
      if (_lightboxIndex === expectedIdx) renderInfoInto(refs.info, m, meta);
    });
  }
}

function navLightbox(delta: number): void {
  renderLightboxAt(_lightboxIndex + delta);
}

function closeLightbox(): void {
  if (!_lightbox) return;
  _lightbox.overlay.style.display = 'none';
  _lightbox.img.src = '';
  document.documentElement.style.overflow = '';
  document.removeEventListener('keydown', onLightboxKey);
}
