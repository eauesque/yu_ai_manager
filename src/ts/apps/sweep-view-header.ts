import { type BridgeTarget } from '../shared/bridge-payload';
import {
  BRIDGE_LABEL,
  BRIDGE_URL,
  attachSameBridgeRerunHandler,
  sendCrossBridgeRerun,
  toBridgeTarget,
} from '../shared/sweep-rerun';
import { currentFit, setFitMode, type FitMode } from './sweep-view-fit';
import { setText, tr } from './sweep-view-i18n';
import type { SweepMeta } from './sweep-view-types';

let _crossBridgeAbort: AbortController | null = null;

export function renderToolbar(): void {
  const host = document.getElementById('sweepViewToolbar');
  if (!host) return;
  host.textContent = '';
  const wrap = document.createElement('div');
  wrap.style.cssText = 'display:inline-flex;border:1px solid rgba(127,127,127,0.3);border-radius:6px;overflow:hidden;font-size:12px;';
  wrap.appendChild(fitButton('cover', '🔲', 'sweep_view.fit_cover', 'Square'));
  wrap.appendChild(fitButton('contain', '🖼️', 'sweep_view.fit_contain', 'Fit'));
  host.appendChild(wrap);
  refreshToolbarSelection();
}

export function renderHeader(meta: SweepMeta, hintFileId: number | null): void {
  const idShort = meta.id.length > 12 ? meta.id.slice(0, 8) + '…' : meta.id;
  setText('sweepViewId', idShort);
  setText('sweepViewBridge', meta.bridge || '');
  setText('sweepViewAxisSummary', meta.axes.map((ax, i) => `axis ${i}: ${ax.param} × ${ax.total}`).join('  /  '));
  if (hintFileId == null) return;
  const path = bridgePath(meta.bridge);
  const sourceTarget = toBridgeTarget(meta.bridge);
  if (path) {
    const base = path + '?resume_sweep=' + encodeURIComponent(String(hintFileId));
    wireRerunLink('sweepViewRerunBtn', base, '🔁 ' + tr('sweep_view.rerun_with_seed', 'Re-run (same seed)'), hintFileId, sourceTarget, false);
    wireRerunLink('sweepViewRerunNoSeedBtn', base + '&omit_seed=1', '🎲 ' + tr('sweep_view.rerun_no_seed', 'Re-run (new seed)'), hintFileId, sourceTarget, true);
  }
  renderCrossBridgeDropdown(meta, hintFileId);
}

export function renderHistorySection(): void {
  const host = document.getElementById('sweepViewHistory');
  if (!host) return;
  const w = window as unknown as {
    BridgeSweepQuickJump?: {
      renderHistoryList?: (el: HTMLElement, opts?: { referenceSweepId?: string }) => unknown;
    };
  };
  const api = w.BridgeSweepQuickJump;
  if (api && typeof api.renderHistoryList === 'function') {
    const refId = document.body.getAttribute('data-sweep-id') || undefined;
    api.renderHistoryList(host, refId ? { referenceSweepId: refId } : undefined);
  }
}

function fitButton(mode: FitMode, icon: string, labelKey: string, fallback: string): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.dataset.fit = mode;
  btn.title = tr(labelKey, fallback);
  btn.textContent = `${icon} ${tr(labelKey, fallback)}`;
  btn.style.cssText = 'padding:5px 10px;border:0;cursor:pointer;font-size:12px;background:transparent;color:inherit;';
  btn.addEventListener('click', () => {
    setFitMode(mode);
    refreshToolbarSelection();
  });
  return btn;
}

function refreshToolbarSelection(): void {
  const host = document.getElementById('sweepViewToolbar');
  if (!host) return;
  const buttons = host.querySelectorAll<HTMLButtonElement>('button[data-fit]');
  buttons.forEach((b) => {
    const active = b.dataset.fit === currentFit();
    b.style.background = active ? '#4fc3f7' : 'transparent';
    b.style.color = active ? '#000' : 'inherit';
    b.style.fontWeight = active ? '600' : 'normal';
  });
}

function bridgePath(bridge: string): string | null {
  const target = toBridgeTarget(bridge);
  return target ? BRIDGE_URL[target] : null;
}

function wireRerunLink(
  id: string,
  href: string,
  label: string,
  fileId: number,
  sourceTarget: BridgeTarget | null,
  omitSeed: boolean,
): void {
  const link = document.getElementById(id) as HTMLAnchorElement | null;
  if (!link) return;
  link.href = href;
  link.textContent = label;
  link.style.display = '';
  if (sourceTarget) attachSameBridgeRerunHandler(link, fileId, sourceTarget, omitSeed);
}

function renderCrossBridgeDropdown(meta: SweepMeta, hintFileId: number): void {
  const host = document.getElementById('sweepViewCrossBridge');
  if (!host) return;
  host.textContent = '';
  if (_crossBridgeAbort) _crossBridgeAbort.abort();
  _crossBridgeAbort = new AbortController();
  const sourceTarget = toBridgeTarget(meta.bridge);
  if (!sourceTarget) return;
  const others = (Object.keys(BRIDGE_URL) as BridgeTarget[]).filter((t) => t !== sourceTarget);
  if (others.length === 0) return;
  const wrap = document.createElement('div');
  wrap.style.cssText = 'position:relative;display:inline-block;';
  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn small';
  trigger.style.cssText = 'padding:6px 12px;cursor:pointer;';
  trigger.textContent = '🔀 ' + tr('sweep_view.rerun_other_bridge', 'Re-run on other bridge') + ' ▾';
  wrap.appendChild(trigger);
  const menu = document.createElement('div');
  menu.style.cssText =
    'position:absolute;top:100%;right:0;margin-top:4px;display:none;background:var(--card-bg, #1e1e1e);' +
    'color:var(--fg, #ddd);border:1px solid rgba(127,127,127,0.3);border-radius:6px;' +
    'box-shadow:0 4px 12px rgba(0,0,0,0.3);z-index:10;min-width:180px;padding:4px;';
  for (const target of others) menu.appendChild(crossBridgeOption(target, hintFileId, menu));
  wrap.appendChild(menu);
  trigger.addEventListener('click', (ev) => {
    ev.stopPropagation();
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  });
  document.addEventListener('click', () => { menu.style.display = 'none'; }, { signal: _crossBridgeAbort.signal });
  host.appendChild(wrap);
}

function crossBridgeOption(target: BridgeTarget, hintFileId: number, menu: HTMLElement): HTMLButtonElement {
  const opt = document.createElement('button');
  opt.type = 'button';
  opt.style.cssText =
    'display:block;width:100%;text-align:left;padding:6px 10px;background:transparent;' +
    'color:inherit;border:0;cursor:pointer;border-radius:4px;font-size:13px;';
  opt.textContent = '🔁 ' + BRIDGE_LABEL[target];
  opt.title = tr('sweep_view.rerun_other_bridge_hint', 'Convert prompt syntax and re-run on this bridge (seed omitted)');
  opt.addEventListener('mouseenter', () => { opt.style.background = 'rgba(127,127,127,0.18)'; });
  opt.addEventListener('mouseleave', () => { opt.style.background = 'transparent'; });
  opt.addEventListener('click', () => {
    menu.style.display = 'none';
    void sendCrossBridgeRerun(hintFileId, target, true);
  });
  return opt;
}
