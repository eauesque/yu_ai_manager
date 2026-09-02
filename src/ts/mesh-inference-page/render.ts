/**
 * render.ts — build the peer × inference_type matrix table.
 *
 * Cells encode three states:
 *   enabled    → checked checkbox
 *   disabled   → unchecked checkbox
 *   unavailable → "—" placeholder, not interactive
 *
 * Each interactive cell carries data-peer-id and data-inference-type for
 * event delegation from index.ts and Playwright selector stability.
 */
import { ALL_TYPES, InferenceType, Peer, StateResponse, tr } from './api';

export interface MatrixRefs {
  head: HTMLElement;
  body: HTMLElement;
  wrap: HTMLElement;
  empty: HTMLElement;
  localOnlyBtn: HTMLButtonElement;
}

export function getRefs(): MatrixRefs {
  return {
    head: document.getElementById('miMatrixHead')!,
    body: document.getElementById('miMatrixBody')!,
    wrap: document.getElementById('miMatrixWrap')!,
    empty: document.getElementById('miEmpty')!,
    localOnlyBtn: document.getElementById('miLocalOnlyBtn') as HTMLButtonElement,
  };
}

function buildHead(types: InferenceType[]): string {
  const cells = types.map(
    (t) =>
      `<th data-inference-type="${t}" data-i18n="mesh_inference.type.${t}">${t}</th>`,
  );
  return `<th data-i18n="mesh_inference.col.peer">Peer</th>${cells.join('')}`;
}

function buildRow(peer: Peer, types: InferenceType[]): string {
  const badge = peer.status === 'online'
    ? '<span class="mi-badge mi-badge-online">●</span>'
    : '<span class="mi-badge mi-badge-offline">●</span>';
  const localIcon = peer.is_local ? '🏠 ' : '';
  const device = peer.device_info ? `<span class="mi-device">(${escapeHtml(peer.device_info)})</span>` : '';
  const name = `${localIcon}${escapeHtml(peer.name)} ${device} ${badge}`;
  const disabledSet = new Set(peer.disabled_types);
  const advertisedSet = new Set(peer.inference_types);

  const cells = types.map((t) => {
    if (!advertisedSet.has(t)) {
      return `<td class="mi-cell-na" data-peer-id="${escapeHtml(peer.peer_id)}" data-inference-type="${t}">—</td>`;
    }
    const isDisabled = disabledSet.has(t);
    return `<td class="mi-cell" data-peer-id="${escapeHtml(peer.peer_id)}" data-inference-type="${t}">
      <label class="mi-cell-label">
        <input type="checkbox" class="mi-toggle" ${isDisabled ? '' : 'checked'}
               data-peer-id="${escapeHtml(peer.peer_id)}"
               data-inference-type="${t}" />
      </label>
    </td>`;
  }).join('');

  const rowClasses = ['mi-row'];
  if (peer.is_local) rowClasses.push('mi-row-local');
  if (peer.status !== 'online') rowClasses.push('mi-row-offline');
  return `<tr class="${rowClasses.join(' ')}"><td class="mi-peer">${name}</td>${cells}</tr>`;
}

export function renderMatrix(data: StateResponse): void {
  const refs = getRefs();
  const peers = data.peers ?? [];

  if (peers.length === 0) {
    refs.wrap.style.display = 'none';
    refs.empty.style.display = '';
    refs.localOnlyBtn.disabled = true;
    return;
  }
  refs.wrap.style.display = '';
  refs.empty.style.display = 'none';

  // Build the union of advertised types across all peers. If nothing is
  // advertised, fall back to the canonical list so the header is stable.
  const union = new Set<string>();
  peers.forEach((p) => p.inference_types.forEach((t) => union.add(t)));
  const orderedTypes = (ALL_TYPES as readonly string[]).filter((t) => union.has(t)) as InferenceType[];
  const types: InferenceType[] = orderedTypes.length
    ? orderedTypes
    : (ALL_TYPES as readonly InferenceType[]).slice();

  refs.head.innerHTML = buildHead(types);

  // Put local first, then remote by name
  const local = peers.filter((p) => p.is_local);
  const remote = peers.filter((p) => !p.is_local).sort((a, b) => a.name.localeCompare(b.name));
  refs.body.innerHTML = [...local, ...remote]
    .map((p) => buildRow(p, types))
    .join('');

  // local_only button enable/disable based on the API-side condition:
  // localIsEffective = any advertised type on local that is not disabled
  const localPeer = peers.find((p) => p.is_local);
  let localIsEffective = false;
  if (localPeer) {
    const disabledSet = new Set(localPeer.disabled_types);
    localIsEffective = (ALL_TYPES as readonly string[]).some(
      (t) => localPeer.inference_types.includes(t) && !disabledSet.has(t),
    );
  }
  refs.localOnlyBtn.disabled = !localIsEffective;
  refs.localOnlyBtn.title = localIsEffective
    ? tr('mesh_inference.action.local_only', 'Local-only mode')
    : tr(
        'mesh_inference.action.local_only_tooltip',
        'Local peer has no effective inference types',
      );
}

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}
