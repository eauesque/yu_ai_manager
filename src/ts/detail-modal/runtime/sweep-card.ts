/**
 * Detail-modal "Sweep" card.
 *
 * If the currently-displayed file has sweep XMP attached (written during a
 * previous Sweep run by the image generation bridges), this module fetches
 * the parsed meta from `GET /api/sweep/info/<file_id>` and injects a small
 * card into the modal info area with two actions:
 *
 *   • Re-run this sweep — navigates to `/{bridge}?resume_sweep=<file_id>`,
 *     where `sweep-resume.js` on the Bridge page populates the Sweep form.
 *   • Show other images in this sweep — fetches
 *     `/api/sweep/files/<sweep_id>?file_id=<hint>` and renders thumbnails
 *     of the matching files in the same folder.
 *
 * Files without sweep XMP get a 404 from the info endpoint and we render
 * nothing — there is no extra cost on non-sweep images beyond a single
 * cached fetch.
 */

import {
  attachSameBridgeRerunHandler,
  bridgePath as _bridgePath,
  toBridgeTarget,
  sendCrossBridgeRerun,
  BRIDGE_LABEL,
  BRIDGE_URL,
} from '../../shared/sweep-rerun';
import type { BridgeTarget } from '../../shared/bridge-payload';

interface SweepAxis {
  param: string;
  index: number;
  total: number;
  value: unknown;
  series: unknown[];
}

interface SweepMeta {
  id: string;
  bridge: string;
  axes: SweepAxis[];
  base_seed: number;
  created_at: number;
}

interface SweepInfoResponse {
  ok?: boolean;
  meta?: SweepMeta;
  path?: string;
}

function _tr(key: string, fallback: string): string {
  const w = window as unknown as { tr?: (k: string, f?: string) => string };
  return typeof w.tr === 'function' ? w.tr(key, fallback) : fallback;
}

function _div(style?: string, text?: string): HTMLElement {
  const el = document.createElement('div');
  if (style) el.style.cssText = style;
  if (text != null) el.textContent = text;
  return el;
}

function _renderHeader(meta: SweepMeta, parent: HTMLElement): void {
  const head = _div('font-weight:600;color:#4fc3f7;margin-bottom:4px;');
  head.appendChild(document.createTextNode(
    '🔁 ' + _tr('sweep.card_title', 'Sweep') + ' · ' + (meta.bridge || '?') + ' · ',
  ));
  const idSpan = document.createElement('span');
  idSpan.style.cssText = 'opacity:0.65;font-family:monospace;';
  const idShort = meta.id.length > 12 ? meta.id.slice(0, 8) + '…' : meta.id;
  idSpan.textContent = idShort;
  head.appendChild(idSpan);
  parent.appendChild(head);

  if (!meta.axes || meta.axes.length === 0) {
    const noAxis = _div('margin-bottom:8px;');
    noAxis.textContent = _tr('sweep.card_no_axis', 'no axis info');
    parent.appendChild(noAxis);
    return;
  }
  const axisLetters = ['', 'y', 'z'];  // X uses `$1` (alias of `$x1`), Y/Z prefix the letter.
  for (let i = 0; i < meta.axes.length; i++) {
    const axis = meta.axes[i];
    const axisLine = _div('margin-bottom:4px;');
    let valStr: string;
    if (axis.value == null) {
      valStr = '?';
    } else if (axis.param === '_macros' && typeof axis.value === 'object') {
      // Macros axis: show `$1=happy, $2=0.5` (X) or `$y1=...` / `$z1=...`
      // (Y/Z) instead of "[object Object]".
      const prefix = axisLetters[i] ?? '';
      const parts: string[] = [];
      for (const [k, v] of Object.entries(axis.value as Record<string, unknown>)) {
        parts.push(`$${prefix}${k}=${v}`);
      }
      valStr = parts.join(', ');
    } else {
      valStr = String(axis.value);
    }
    axisLine.textContent = axis.param === '_macros'
      ? `Prompt macros: ${valStr}  (${axis.index + 1}/${axis.total})`
      : `${axis.param} = ${valStr}  (${axis.index + 1}/${axis.total})`;
    parent.appendChild(axisLine);
  }
  // Spacer matching the original margin-bottom:8px; on the single-axis line.
  const spacer = _div('height:4px;');
  parent.appendChild(spacer);
}

function _renderCard(meta: SweepMeta, fileId: number): HTMLElement {
  const card = _div(
    'margin:10px 0;padding:10px 12px;border-left:3px solid #4fc3f7;' +
    'background:rgba(79,195,247,0.06);border-radius:4px;font-size:13px;',
  );
  card.className = 'modal-sweep-card';
  card.dataset.sweepId = meta.id;

  _renderHeader(meta, card);

  const actions = _div('display:flex;gap:8px;flex-wrap:wrap;');
  actions.className = 'sweep-card-actions';
  card.appendChild(actions);

  // Open dedicated Sweep view — single primary action. The full grid /
  // re-run / "show others" UI now lives at /sweep/<id> so this card stays
  // compact and the dedicated view can scale to 2-axis / 3-axis layouts.
  const openView = document.createElement('a');
  openView.href = '/sweep/' + encodeURIComponent(meta.id) +
    '?from=' + encodeURIComponent(String(fileId));
  openView.target = '_blank';
  openView.rel = 'noopener';
  openView.className = 'btn small';
  openView.style.cssText = 'padding:4px 10px;text-decoration:none;';
  openView.textContent = _tr('sweep.card_open_view_btn', '🔎 Open Sweep view');
  actions.appendChild(openView);

  // Re-run this sweep — split into two buttons so the user can choose
  // whether to reuse the original base seed (exact reproduction) or let
  // the bridge pick a new seed (shuffle / explore variations). The click
  // handler fetches the source file's prompt/negative/characters and
  // pushes them via `bridge_send_prompt` so the destination bridge
  // restores the *full* prompt — without it, the bridge falls back to
  // its `XX_last_params`, which may be from a later single-image
  // generate. Shared with the dedicated /sweep/<id> view.
  const path = _bridgePath(meta.bridge);
  const sourceTarget = toBridgeTarget(meta.bridge);
  if (path && sourceTarget) {
    // `href` is only used for middle-/Ctrl-/Shift-click fallthrough (open in
    // new tab). reRunSeed keeps the seed; reRunNoSeed appends `omit_seed=1`.
    // Plain left-click is intercepted by attachSameBridgeRerunHandler and
    // routed through bridge_send_prompt, so the omit_seed flag is enforced
    // there too — keep the two href tails in sync if you change them.
    const base = path + '?resume_sweep=' + encodeURIComponent(String(fileId));

    const reRunSeed = document.createElement('a');
    reRunSeed.href = base;
    reRunSeed.className = 'btn small';
    reRunSeed.style.cssText = 'padding:4px 10px;text-decoration:none;';
    reRunSeed.textContent = _tr('sweep.card_rerun_with_seed_btn', '🔁 Re-run (same seed)');
    attachSameBridgeRerunHandler(reRunSeed, fileId, sourceTarget, false);
    actions.appendChild(reRunSeed);

    const reRunNoSeed = document.createElement('a');
    reRunNoSeed.href = base + '&omit_seed=1';
    reRunNoSeed.className = 'btn small';
    reRunNoSeed.style.cssText = 'padding:4px 10px;text-decoration:none;';
    reRunNoSeed.textContent = _tr('sweep.card_rerun_no_seed_btn', '🎲 Re-run (new seed)');
    attachSameBridgeRerunHandler(reRunNoSeed, fileId, sourceTarget, true);
    actions.appendChild(reRunNoSeed);

    // Cross-bridge dropdown — convert NAI<->SD prompt and re-run on a
    // different bridge. Uses the shared sendCrossBridgeRerun (same code path
    // as the dedicated /sweep/<id> page). Includes a "シードを含めない"
    // checkbox; defaults to checked because cross-bridge seed semantics
    // (NAI vs SD vs ComfyUI) are not directly compatible.
    const others = (Object.keys(BRIDGE_URL) as BridgeTarget[]).filter(t => t !== sourceTarget);
    if (others.length > 0) {
      actions.appendChild(_renderCrossBridgeDropdown(fileId, others));
    }
  }

  return card;
}

let _crossDropdownAbort: AbortController | null = null;

function _renderCrossBridgeDropdown(fileId: number, others: BridgeTarget[]): HTMLElement {
  if (_crossDropdownAbort) _crossDropdownAbort.abort();
  _crossDropdownAbort = new AbortController();
  const abortSignal = _crossDropdownAbort.signal;

  const wrap = document.createElement('span');
  wrap.style.cssText = 'position:relative;display:inline-block;';

  const trigger = document.createElement('button');
  trigger.type = 'button';
  trigger.className = 'btn small';
  trigger.style.cssText = 'padding:4px 10px;cursor:pointer;';
  trigger.textContent = '🔀 ' + _tr('sweep.card_rerun_other_bridge_btn', 'Re-run on other bridge') + ' ▾';
  wrap.appendChild(trigger);

  const menu = document.createElement('div');
  menu.style.cssText =
    'position:absolute;top:100%;left:0;margin-top:4px;display:none;' +
    'background:var(--card-bg, #1e1e1e);color:var(--fg, #ddd);' +
    'border:1px solid rgba(127,127,127,0.3);border-radius:6px;' +
    'box-shadow:0 4px 12px rgba(0,0,0,0.3);z-index:10;min-width:200px;' +
    'padding:6px;';

  // Omit-seed checkbox (default checked — cross-bridge seeds rarely
  // reproduce identically across NAI/SD/ComfyUI).
  const optLabel = document.createElement('label');
  optLabel.style.cssText =
    'display:flex;align-items:center;gap:6px;padding:4px 6px;' +
    'font-size:12px;cursor:pointer;user-select:none;';
  optLabel.title = _tr('detail.modal.send_omit_seed_title',
    'シードを含めずに送ります（毎回ランダム）');
  const cb = document.createElement('input');
  cb.type = 'checkbox';
  cb.checked = true;
  optLabel.appendChild(cb);
  optLabel.appendChild(document.createTextNode(
    _tr('detail.modal.send_omit_seed_label', 'シードを含めない'),
  ));
  menu.appendChild(optLabel);

  const sep = document.createElement('div');
  sep.style.cssText = 'height:1px;background:rgba(127,127,127,0.25);margin:4px 0;';
  menu.appendChild(sep);

  for (const t of others) {
    const opt = document.createElement('button');
    opt.type = 'button';
    opt.style.cssText =
      'display:block;width:100%;text-align:left;padding:6px 10px;' +
      'background:transparent;color:inherit;border:0;cursor:pointer;' +
      'border-radius:4px;font-size:13px;';
    opt.textContent = '🔁 ' + BRIDGE_LABEL[t];
    opt.title = _tr('sweep_view.rerun_other_bridge_hint',
      'Convert prompt syntax and re-run on this bridge');
    opt.addEventListener('mouseenter', () => { opt.style.background = 'rgba(127,127,127,0.18)'; });
    opt.addEventListener('mouseleave', () => { opt.style.background = 'transparent'; });
    opt.addEventListener('click', () => {
      menu.style.display = 'none';
      void sendCrossBridgeRerun(fileId, t, cb.checked);
    });
    menu.appendChild(opt);
  }
  wrap.appendChild(menu);

  trigger.addEventListener('click', (ev) => {
    ev.stopPropagation();
    menu.style.display = menu.style.display === 'none' ? 'block' : 'none';
  });
  document.addEventListener('click', () => { menu.style.display = 'none'; }, { signal: abortSignal });

  return wrap;
}

let _lastFetchSeq = 0;

/** Fetch sweep info for *fileId* and inject a card into the Info tab pane.
 *
 * The card lives inside ``#miPanel-info`` (the Info tab content) rather than
 * at the top of ``.modal-info``: putting it above the tab bar would push the
 * tab strip down on every modal open and stack a clickable element above the
 * sticky tab strip, which is also where the "can't click the buttons" bug
 * came from. As an Info-pane child it scrolls with the rest of the metadata
 * and doesn't compete with the tab strip for pointer events.
 */
export function loadSweepCard(fileId: number): void {
  if (!fileId || !Number.isFinite(fileId)) return;
  const mySeq = ++_lastFetchSeq;

  document.querySelectorAll('.modal-sweep-card').forEach((el) => el.remove());

  fetch(`/api/sweep/info/${encodeURIComponent(String(fileId))}`, {
    headers: { 'X-Requested-With': 'XMLHttpRequest' },
  })
    .then((r) => {
      if (r.status === 404) return null;
      return r.json() as Promise<SweepInfoResponse>;
    })
    .then((d) => {
      if (!d || !d.ok || !d.meta) return;
      if (mySeq !== _lastFetchSeq) return;
      const target = document.querySelector<HTMLElement>('#miPanel-info')
        ?? document.querySelector<HTMLElement>('.modal-info');
      if (!target) return;
      target.insertBefore(_renderCard(d.meta, fileId), target.firstChild);
    })
    .catch((e: unknown) => {
      // eslint-disable-next-line no-console
      console.debug('loadSweepCard:', e);
    });
}
