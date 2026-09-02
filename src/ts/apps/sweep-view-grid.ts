import { applyFitToImage, clearGridImages, trackGridImage } from './sweep-view-fit';
import { formatAxisValue } from './sweep-view-format';
import { clearLightboxEntries, openLightbox, registerLightboxEntry } from './sweep-view-lightbox';
import { tr } from './sweep-view-i18n';
import type { SweepFilesEntry, SweepMeta } from './sweep-view-types';

function buildCell(m: SweepFilesEntry, label: string): HTMLElement {
  const cell = m.file_id != null ? document.createElement('a') : document.createElement('div');
  cell.style.cssText =
    'display:flex;flex-direction:column;align-items:center;padding:6px;' +
    'border:1px solid rgba(127,127,127,0.18);border-radius:6px;text-decoration:none;' +
    'color:inherit;background:rgba(127,127,127,0.03);cursor:' + (m.file_id != null ? 'pointer' : 'default') + ';';
  if (m.file_id != null) {
    (cell as HTMLAnchorElement).href = `/api/original/${m.file_id}`;
    (cell as HTMLAnchorElement).target = '_blank';
    (cell as HTMLAnchorElement).rel = 'noopener';
    cell.title = m.path;
    const lbIndex = registerLightboxEntry(m);
    cell.addEventListener('click', (ev) => {
      const me = ev as MouseEvent;
      if (me.button !== 0 || me.metaKey || me.ctrlKey || me.shiftKey || me.altKey) return;
      ev.preventDefault();
      openLightbox(lbIndex);
    });
  } else {
    cell.title = m.path + ' (not indexed)';
  }
  appendImageOrPlaceholder(cell, m);
  if (label) {
    const meta = document.createElement('div');
    meta.style.cssText = 'margin-top:6px;font-size:12px;font-weight:600;text-align:center;';
    meta.textContent = label;
    cell.appendChild(meta);
  }
  return cell;
}

function appendImageOrPlaceholder(cell: HTMLElement, m: SweepFilesEntry): void {
  if (m.file_id != null) {
    const img = document.createElement('img');
    img.src = `/api/thumbnail/${m.file_id}`;
    img.alt = m.path;
    img.loading = 'lazy';
    img.style.cssText = 'width:100%;aspect-ratio:1/1;border-radius:4px;';
    applyFitToImage(img);
    trackGridImage(img);
    cell.appendChild(img);
    return;
  }
  const placeholder = document.createElement('div');
  placeholder.style.cssText =
    'width:100%;aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;' +
    'font-size:32px;background:rgba(127,127,127,0.12);border-radius:4px;';
  placeholder.textContent = '📷';
  cell.appendChild(placeholder);
}

function render1AxisGrid(host: HTMLElement, matches: SweepFilesEntry[]): void {
  const grid = document.createElement('div');
  grid.style.cssText = 'display:grid;grid-template-columns:repeat(auto-fill,minmax(180px,1fr));gap:12px;';
  for (const m of matches) {
    const indexLabel = (m.axis_0_index ?? -1) >= 0 ? String((m.axis_0_index as number) + 1) : '?';
    grid.appendChild(buildCell(m, `#${indexLabel}  ${formatAxisValue(m.axis_0_value)}`));
  }
  host.appendChild(grid);
}

function build2AxisTable(
  xAxis: SweepMeta['axes'][number],
  yAxis: SweepMeta['axes'][number],
  byCell: Map<string, SweepFilesEntry>,
): HTMLTableElement {
  const table = document.createElement('table');
  table.style.cssText = 'border-collapse:separate;border-spacing:8px;margin:0 auto;';
  const head = document.createElement('tr');
  head.appendChild(document.createElement('th'));
  const xIsMacros = xAxis.param === '_macros';
  const yIsMacros = yAxis.param === '_macros';
  for (let xi = 0; xi < xAxis.series.length; xi++) {
    const th = document.createElement('th');
    th.style.cssText = 'font-size:12px;font-weight:600;padding:4px 8px;text-align:center;';
    th.textContent = xIsMacros ? formatAxisValue(xAxis.series[xi], 'x') : `${xAxis.param} = ${xAxis.series[xi]}`;
    head.appendChild(th);
  }
  table.appendChild(head);
  for (let yi = 0; yi < yAxis.series.length; yi++) {
    const row = document.createElement('tr');
    const yLabel = document.createElement('th');
    yLabel.style.cssText = 'font-size:12px;font-weight:600;padding:4px 8px;text-align:right;white-space:nowrap;';
    yLabel.textContent = yIsMacros ? formatAxisValue(yAxis.series[yi], 'y') : `${yAxis.param} = ${yAxis.series[yi]}`;
    row.appendChild(yLabel);
    for (let xi = 0; xi < xAxis.series.length; xi++) {
      const td = document.createElement('td');
      td.style.cssText = 'width:160px;vertical-align:top;';
      const m = byCell.get(`${xi}:${yi}`);
      td.appendChild(m ? buildCell(m, '') : blankCell());
      row.appendChild(td);
    }
    table.appendChild(row);
  }
  return table;
}

function blankCell(): HTMLElement {
  const blank = document.createElement('div');
  blank.style.cssText =
    'width:100%;aspect-ratio:1/1;display:flex;align-items:center;justify-content:center;' +
    'background:rgba(127,127,127,0.06);border:1px dashed rgba(127,127,127,0.2);' +
    'border-radius:4px;opacity:0.5;font-size:11px;';
  blank.textContent = '—';
  return blank;
}

function render2AxisGrid(host: HTMLElement, meta: SweepMeta, matches: SweepFilesEntry[]): void {
  const byCell = new Map<string, SweepFilesEntry>();
  for (const m of matches) {
    const xi = m.axis_0_index ?? -1;
    const yi = m.axis_1_index ?? -1;
    if (xi >= 0 && yi >= 0) byCell.set(`${xi}:${yi}`, m);
  }
  host.appendChild(build2AxisTable(meta.axes[0], meta.axes[1], byCell));
}

function render3AxisGrid(host: HTMLElement, meta: SweepMeta, matches: SweepFilesEntry[]): void {
  const [xAxis, yAxis, zAxis] = meta.axes;
  const byZ = new Map<number, Map<string, SweepFilesEntry>>();
  for (const m of matches) {
    const xi = m.axis_0_index ?? -1;
    const yi = m.axis_1_index ?? -1;
    const zi = m.axis_2_index ?? -1;
    if (xi < 0 || yi < 0 || zi < 0) continue;
    let bucket = byZ.get(zi);
    if (!bucket) { bucket = new Map(); byZ.set(zi, bucket); }
    bucket.set(`${xi}:${yi}`, m);
  }
  const tabs = document.createElement('div');
  tabs.style.cssText = 'display:flex;gap:6px;flex-wrap:wrap;margin-bottom:12px;';
  const grids: HTMLDivElement[] = [];
  for (let zi = 0; zi < zAxis.series.length; zi++) {
    const grid = document.createElement('div');
    grid.style.display = zi === 0 ? '' : 'none';
    grid.appendChild(build2AxisTable(xAxis, yAxis, byZ.get(zi) ?? new Map()));
    grids.push(grid);
    tabs.appendChild(zTabButton(zAxis, zi, tabs, grids));
  }
  host.appendChild(tabs);
  for (const g of grids) host.appendChild(g);
}

function zTabButton(zAxis: SweepMeta['axes'][number], zi: number, tabs: HTMLElement, grids: HTMLDivElement[]): HTMLButtonElement {
  const btn = document.createElement('button');
  btn.type = 'button';
  btn.textContent = zAxis.param === '_macros' ? formatAxisValue(zAxis.series[zi], 'z') : `${zAxis.param} = ${zAxis.series[zi]}`;
  btn.style.cssText =
    'font-size:12px;padding:4px 10px;border-radius:4px;cursor:pointer;border:1px solid rgba(127,127,127,0.3);' +
    (zi === 0 ? 'background:#4fc3f7;color:#000;' : 'background:transparent;color:inherit;');
  btn.addEventListener('click', () => {
    grids.forEach((g, k) => { g.style.display = k === zi ? '' : 'none'; });
    Array.prototype.forEach.call(tabs.children, (b: HTMLButtonElement, k: number) => {
      b.style.background = k === zi ? '#4fc3f7' : 'transparent';
      b.style.color = k === zi ? '#000' : 'inherit';
    });
  });
  return btn;
}

export function renderGrid(meta: SweepMeta, matches: SweepFilesEntry[]): void {
  const host = document.getElementById('sweepViewGrid');
  if (!host) return;
  host.textContent = '';
  clearGridImages();
  clearLightboxEntries();
  if (matches.length === 0) {
    const empty = document.createElement('div');
    empty.style.cssText = 'padding:20px;opacity:0.7;text-align:center;';
    empty.textContent = tr('sweep_view.empty', 'No images found in this sweep. The folder may have been moved or the files were not indexed.');
    host.appendChild(empty);
    return;
  }
  if (meta.axes.length >= 3) render3AxisGrid(host, meta, matches);
  else if (meta.axes.length === 2) render2AxisGrid(host, meta, matches);
  else render1AxisGrid(host, matches);
}
