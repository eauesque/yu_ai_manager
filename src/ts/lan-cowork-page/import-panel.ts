/**
 * lan-cowork-page/import-panel.ts
 * Import form, polling, progress bar, and button state management.
 */
import { createSession, executeImport, pollSession, showToast, tr, Peer } from './api';

const POLL_INTERVAL_MS = 500;
const PENDING_TIMEOUT_MS = 60_000;

type BothButtons = { startBtn: HTMLButtonElement; refreshBtn: HTMLButtonElement };

function setBothDisabled(btns: BothButtons, disabled: boolean): void {
  btns.startBtn.disabled = disabled;
  btns.refreshBtn.disabled = disabled;
}

function resetButtons(btns: BothButtons): void {
  setBothDisabled(btns, false);
  btns.startBtn.textContent = tr('lan_cowork.import.start', 'Start import');
}

function setProgressIndeterminate(bar: HTMLProgressElement): void {
  bar.removeAttribute('value');
  bar.hidden = false;
}

function setProgressValue(bar: HTMLProgressElement, done: number, total: number): void {
  bar.value = total > 0 ? (done / total) * 100 : 0;
  bar.max = 100;
  bar.hidden = false;
}

function hideProgress(bar: HTMLProgressElement, label: HTMLElement): void {
  bar.hidden = true;
  label.textContent = '';
}

async function runPoller(
  sessionId: string,
  bar: HTMLProgressElement,
  label: HTMLElement,
  btns: BothButtons,
): Promise<void> {
  const startedAt = Date.now();
  let failCount = 0;

  while (true) {
    await new Promise(r => setTimeout(r, POLL_INTERVAL_MS));

    const elapsed = Date.now() - startedAt;

    let data;
    try {
      data = await pollSession(sessionId);
      failCount = 0;
    } catch {
      failCount++;
      if (failCount >= 3) {
        hideProgress(bar, label);
        showToast(tr('lan_cowork.import.error', 'Import failed'));
        resetButtons(btns);
        return;
      }
      continue;
    }

    if (!data.ok) {
      hideProgress(bar, label);
      showToast(data.error ?? tr('lan_cowork.import.error', 'Import failed'));
      resetButtons(btns);
      return;
    }

    const s = data.session!;

    if (s.status === 'pending' && elapsed >= PENDING_TIMEOUT_MS) {
      hideProgress(bar, label);
      showToast(tr('lan_cowork.import.timeout', 'Import timed out'));
      resetButtons(btns);
      return;
    }

    const total = s.total_files ?? 0;
    const done = s.done_files ?? 0;
    // Show indeterminate while running but no files registered yet (e.g. batch zip download phase)
    if (total === 0 || (done === 0 && s.status === 'running')) {
      setProgressIndeterminate(bar);
    } else {
      setProgressValue(bar, done, total);
    }
    label.textContent = `${done} / ${total > 0 ? total : '?'}`;

    if (s.status === 'completed') {
      bar.hidden = false;
      if (done < total) {
        showToast(tr('lan_cowork.import.partial', 'Import completed with some files missing'));
      } else {
        bar.value = 100;
        bar.max = 100;
        showToast(tr('lan_cowork.import.done', 'Import completed'));
      }
      resetButtons(btns);
      return;
    }

    if (s.status === 'failed') {
      hideProgress(bar, label);
      showToast(tr('lan_cowork.import.error', 'Import failed'));
      resetButtons(btns);
      return;
    }
  }
}

function buildPeerOptions(select: HTMLSelectElement, peers: Peer[]): void {
  // Clear existing options using DOM API to avoid XSS
  while (select.firstChild) {
    select.removeChild(select.firstChild);
  }
  for (const p of peers) {
    const opt = document.createElement('option');
    opt.value = p.peer_id;
    opt.dataset.name = p.name;
    opt.textContent = `${p.name} (${p.api_host}:${p.api_port})`;
    select.appendChild(opt);
  }
}

export function initImportPanel(): void {
  const startBtn = document.getElementById('lcImportStartBtn') as HTMLButtonElement | null;
  const refreshBtn = document.getElementById('lcRefreshBtn') as HTMLButtonElement | null;
  const peerSelect = document.getElementById('lcPeerSelect') as HTMLSelectElement | null;
  const modeSelect = document.getElementById('lcModeSelect') as HTMLSelectElement | null;
  const folderInput = document.getElementById('lcFolderInput') as HTMLInputElement | null;
  const folderPickBtn = document.getElementById('lcFolderPickBtn') as HTMLButtonElement | null;
  const optFav = document.getElementById('lcOptFavorites') as HTMLInputElement | null;
  const optMerge = document.getElementById('lcOptMerge') as HTMLInputElement | null;
  const bar = document.getElementById('lcProgressBar') as HTMLProgressElement | null;
  const label = document.getElementById('lcProgressLabel') as HTMLElement | null;

  if (!startBtn || !refreshBtn || !peerSelect || !modeSelect || !folderInput || !bar || !label) return;

  const btns: BothButtons = { startBtn, refreshBtn };

  // Initialize: start button disabled until peers arrive
  startBtn.disabled = true;

  // Native folder picker (server-side OS dialog via Tauri / tkinter fallback)
  if (folderPickBtn) {
    folderPickBtn.addEventListener('click', async () => {
      const current = folderInput.value.trim();
      const qs = current ? '?initial=' + encodeURIComponent(current) : '';
      folderPickBtn.disabled = true;
      try {
        const res = await fetch('/api/tools/select-folder' + qs);
        const data: { path?: string; cancelled?: boolean; error?: string; message?: string } =
          await res.json();
        if (data.path) {
          folderInput.value = data.path;
          return;
        }
        if (data.cancelled) return;
        if (data.message) {
          showToast(data.message);
          return;
        }
        if (data.error) {
          showToast(tr('lan_cowork.import.folder.pick_failed',
            'Could not open folder picker. Please enter the path manually.'));
        }
      } catch {
        showToast(tr('lan_cowork.import.folder.pick_failed',
          'Could not open folder picker. Please enter the path manually.'));
      } finally {
        folderPickBtn.disabled = false;
      }
    });
  }

  // Sync dropdown from peers-updated event
  document.addEventListener('lc:peers-updated', (e: Event) => {
    const peers = (e as CustomEvent<Peer[]>).detail;
    buildPeerOptions(peerSelect, peers);
    startBtn.disabled = peers.length === 0;
  });

  startBtn.addEventListener('click', async () => {
    const peerId = peerSelect.value;
    const peerName = peerSelect.selectedOptions[0]?.dataset.name ?? '';
    const mode = modeSelect.value;
    const folder = folderInput.value.trim();

    // Client-side validation
    if (!peerId) {
      showToast(tr('lan_cowork.import.err.no_peer', 'Please select a peer'));
      return;
    }
    if (!folder) {
      showToast(tr('lan_cowork.import.err.no_folder', 'Please specify an import folder'));
      return;
    }

    // Disable both buttons, reset progress, show indeterminate
    setBothDisabled(btns, true);
    startBtn.textContent = tr('lan_cowork.import.running', 'Importing...');
    hideProgress(bar, label);
    setProgressIndeterminate(bar);

    // POST session
    let sessionResp;
    try {
      sessionResp = await createSession(
        peerId, peerName, mode, folder,
        { include_favorites: optFav?.checked ?? false, merge_metadata: optMerge?.checked ?? false },
      );
    } catch {
      showToast(tr('lan_cowork.import.error', 'Import failed'));
      hideProgress(bar, label);
      resetButtons(btns);
      return;
    }
    if (!sessionResp.ok || !sessionResp.session_id) {
      showToast(sessionResp.error ?? tr('lan_cowork.import.error', 'Import failed'));
      hideProgress(bar, label);
      resetButtons(btns);
      return;
    }

    // POST execute
    let execResp;
    try {
      execResp = await executeImport(sessionResp.session_id);
    } catch {
      showToast(tr('lan_cowork.import.error', 'Import failed'));
      hideProgress(bar, label);
      resetButtons(btns);
      return;
    }
    if (!execResp.ok) {
      showToast(execResp.error ?? tr('lan_cowork.import.error', 'Import failed'));
      hideProgress(bar, label);
      resetButtons(btns);
      return;
    }

    // Start polling
    await runPoller(sessionResp.session_id, bar, label, btns);
  });
}
