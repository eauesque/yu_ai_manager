import { renderGrid } from './sweep-view-grid';
import { hideSpinner, showError, tr } from './sweep-view-i18n';
import { renderHeader, renderHistorySection, renderToolbar } from './sweep-view-header';
import type { SweepFilesEntry, SweepMeta } from './sweep-view-types';

async function main(): Promise<void> {
  renderHistorySection();
  const sweepId = document.body.dataset.sweepId || '';
  if (!sweepId) {
    showError(tr('sweep_view.missing_id', 'Sweep id missing from URL.'));
    return;
  }
  const hintFileId = parseHintFileId();
  if (hintFileId == null) {
    showError(tr(
      'sweep_view.missing_hint',
      'Open this view from a file detail modal — a "?from=<file_id>" hint is required to find the sweep folder.',
    ));
    return;
  }
  try {
    const [infoRes, filesRes] = await Promise.all([
      fetch(`/api/sweep/info/${encodeURIComponent(String(hintFileId))}`, {
        headers: { 'X-Requested-With': 'XMLHttpRequest' },
      }),
      fetch(
        `/api/sweep/files/${encodeURIComponent(sweepId)}?file_id=${encodeURIComponent(String(hintFileId))}`,
        { headers: { 'X-Requested-With': 'XMLHttpRequest' } },
      ),
    ]);
    const meta = await readSweepMeta(infoRes);
    if (!meta) return;
    renderHeader(meta, hintFileId);
    renderToolbar();
    const matches = await readSweepFiles(filesRes);
    if (!matches) return;
    hideSpinner();
    renderGrid(meta, matches);
  } catch (e: unknown) {
    const msg = e instanceof Error ? e.message : String(e);
    showError(tr('sweep_view.network_failed', 'Network error: ') + msg);
  }
}

function parseHintFileId(): number | null {
  const fromRaw = new URL(window.location.href).searchParams.get('from');
  const hintFileId = fromRaw ? parseInt(fromRaw, 10) : null;
  return hintFileId == null || !Number.isFinite(hintFileId) ? null : hintFileId;
}

async function readSweepMeta(infoRes: Response): Promise<SweepMeta | null> {
  if (!infoRes.ok) {
    showError(tr('sweep_view.info_failed', 'Failed to load sweep meta: ') + infoRes.status);
    return null;
  }
  const infoData = await infoRes.json();
  if (!infoData.ok || !infoData.meta) {
    showError(tr('sweep_view.info_failed', 'Failed to load sweep meta: ') + (infoData.error || 'unknown'));
    return null;
  }
  return infoData.meta as SweepMeta;
}

async function readSweepFiles(filesRes: Response): Promise<SweepFilesEntry[] | null> {
  if (!filesRes.ok) {
    showError(tr('sweep_view.files_failed', 'Failed to load sweep files: ') + filesRes.status);
    return null;
  }
  const filesData = await filesRes.json();
  return (filesData && filesData.matches) || [];
}

void main();
