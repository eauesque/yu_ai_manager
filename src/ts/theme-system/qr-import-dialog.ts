/**
 * Theme QR import dialog — main dialog shell with tabbed UI.
 * Tab-specific logic (file, camera, snip) lives in qr-import-tabs.ts.
 */

import { addCustomTheme, setActiveThemeId } from './storage';
import { applyTheme } from './apply';
import { refreshThemeManager } from './manager-ui';
import {
  type DialogState,
  showStatus, clearStatus, handleDecodedText,
  decodeFile, startCamera, stopCamera, startSnip,
} from './qr-import-tabs';

// ---------------------------------------------------------------------------
// Import dialog HTML template
// ---------------------------------------------------------------------------

function buildImportHtml(): string {
  return `<div class="theme-editor-panel" style="max-width:500px;">
    <h3 style="font-size:15px;margin-bottom:12px;">Import Theme</h3>

    <!-- Tabs -->
    <div class="qr-import-tabs" style="display:flex;gap:0;border-bottom:2px solid var(--border);margin-bottom:12px;">
      <button type="button" class="qr-import-tab qr-import-tab--active" data-tab="text">Text</button>
      <button type="button" class="qr-import-tab" data-tab="file">Image</button>
      <button type="button" class="qr-import-tab" data-tab="camera">Camera</button>
      <button type="button" class="qr-import-tab" data-tab="snip">Snip</button>
    </div>

    <!-- Text tab -->
    <div class="qr-import-pane" data-pane="text">
      <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Paste the theme JSON data:</p>
      <textarea id="theme-import-text" style="width:100%;height:100px;font-size:11px;font-family:monospace;background:var(--bg);color:var(--text);border:1px solid var(--border);border-radius:6px;padding:8px;resize:vertical;" placeholder='{"schema":"yu://theme/1","theme":{...}}'></textarea>
    </div>

    <!-- File tab -->
    <div class="qr-import-pane" data-pane="file" style="display:none;">
      <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Select a QR code image file:</p>
      <label class="qr-file-drop" id="qr-file-drop">
        <input type="file" accept="image/*" id="qr-file-input" style="display:none;">
        <div style="padding:24px;text-align:center;border:2px dashed var(--border);border-radius:8px;cursor:pointer;transition:border-color .2s;">
          <div style="font-size:24px;margin-bottom:4px;">&#x1f4c1;</div>
          <div style="font-size:12px;color:var(--muted);">Click to select or drag &amp; drop</div>
        </div>
      </label>
    </div>

    <!-- Camera tab -->
    <div class="qr-import-pane" data-pane="camera" style="display:none;">
      <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Point camera at a QR code:</p>
      <div id="qr-camera-container" style="position:relative;width:100%;max-width:320px;margin:0 auto;">
        <video id="qr-camera-video" autoplay playsinline muted style="width:100%;border-radius:8px;background:#000;"></video>
        <div id="qr-camera-crosshair" style="position:absolute;inset:0;pointer-events:none;display:flex;align-items:center;justify-content:center;">
          <div style="width:60%;height:60%;border:2px solid rgba(255,255,255,0.5);border-radius:8px;"></div>
        </div>
      </div>
      <div style="text-align:center;margin-top:8px;">
        <button type="button" class="theme-mgr-btn" id="qr-camera-start">Start Camera</button>
        <button type="button" class="theme-mgr-btn" id="qr-camera-stop" style="display:none;">Stop</button>
      </div>
    </div>

    <!-- Snip tab -->
    <div class="qr-import-pane" data-pane="snip" style="display:none;">
      <p style="font-size:12px;color:var(--muted);margin-bottom:8px;">Capture a screen region containing a QR code:</p>
      <div style="text-align:center;padding:16px;">
        <button type="button" class="theme-mgr-btn theme-mgr-btn-primary" id="qr-snip-start" style="font-size:14px;padding:10px 24px;">Start Screen Capture</button>
        <p style="font-size:11px;color:var(--muted);margin-top:8px;">Select a window/screen, then drag to select the QR code area</p>
      </div>
    </div>

    <!-- Result area -->
    <div id="theme-import-preview" style="margin-top:8px;display:none;"></div>
    <div id="theme-import-status" style="margin-top:6px;font-size:12px;display:none;"></div>

    <!-- Action buttons -->
    <div style="margin-top:12px;display:flex;gap:8px;justify-content:flex-end;">
      <button type="button" class="theme-mgr-btn" data-action="close">Cancel</button>
      <button type="button" class="theme-mgr-btn theme-mgr-btn-primary" data-action="import" disabled>Import</button>
    </div>
  </div>`;
}

// ---------------------------------------------------------------------------
// Main entry: show the import dialog
// ---------------------------------------------------------------------------

export function showImportDialog(): void {
  const overlay = document.createElement('div');
  overlay.className = 'theme-editor-overlay';
  overlay.innerHTML = buildImportHtml();
  document.body.appendChild(overlay);

  const st: DialogState = {
    overlay,
    parsedTheme: null,
    cameraStream: null,
    cameraAnimFrame: 0,
    previewDiv: overlay.querySelector('#theme-import-preview') as HTMLElement,
    statusDiv: overlay.querySelector('#theme-import-status') as HTMLElement,
    importBtn: overlay.querySelector('[data-action="import"]') as HTMLButtonElement,
  };

  // --- Tab switching ---
  const tabs = overlay.querySelectorAll('.qr-import-tab');
  const panes = overlay.querySelectorAll('.qr-import-pane');
  tabs.forEach(tab => {
    tab.addEventListener('click', () => {
      const target = (tab as HTMLElement).dataset.tab!;
      tabs.forEach(t => t.classList.toggle('qr-import-tab--active', t === tab));
      panes.forEach(p => {
        (p as HTMLElement).style.display = (p as HTMLElement).dataset.pane === target ? '' : 'none';
      });
      if (target !== 'camera') stopCamera(st);
      clearStatus(st);
    });
  });

  // --- Text tab ---
  const textarea = overlay.querySelector('#theme-import-text') as HTMLTextAreaElement;
  textarea.addEventListener('input', () => {
    const raw = textarea.value.trim();
    if (!raw) {
      clearStatus(st);
      st.previewDiv.style.display = 'none';
      st.importBtn.disabled = true;
      return;
    }
    handleDecodedText(st, raw);
  });

  // --- File tab ---
  const fileInput = overlay.querySelector('#qr-file-input') as HTMLInputElement;
  const fileDrop = overlay.querySelector('#qr-file-drop') as HTMLElement;

  fileInput.addEventListener('change', () => {
    const file = fileInput.files?.[0];
    if (file) decodeFile(st, file);
  });
  fileDrop.addEventListener('dragover', (e) => {
    e.preventDefault();
    fileDrop.style.borderColor = 'var(--accent)';
  });
  fileDrop.addEventListener('dragleave', () => { fileDrop.style.borderColor = ''; });
  fileDrop.addEventListener('drop', (e) => {
    e.preventDefault();
    fileDrop.style.borderColor = '';
    const file = e.dataTransfer?.files[0];
    if (file?.type.startsWith('image/')) decodeFile(st, file);
  });

  // --- Camera tab ---
  overlay.querySelector('#qr-camera-start')?.addEventListener('click', () => startCamera(st));
  overlay.querySelector('#qr-camera-stop')?.addEventListener('click', () => stopCamera(st));

  // --- Snip tab ---
  overlay.querySelector('#qr-snip-start')?.addEventListener('click', () => startSnip(st));

  // --- Import button ---
  st.importBtn.addEventListener('click', () => {
    if (!st.parsedTheme) return;
    addCustomTheme(st.parsedTheme);
    setActiveThemeId(st.parsedTheme.id);
    applyTheme(st.parsedTheme);
    refreshThemeManager();
    stopCamera(st);
    overlay.remove();
  });

  // --- Close / cleanup ---
  overlay.querySelector('[data-action="close"]')?.addEventListener('click', () => {
    stopCamera(st);
    overlay.remove();
  });
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) { stopCamera(st); overlay.remove(); }
  });
  document.addEventListener('keydown', function esc(e) {
    if (e.key === 'Escape' && overlay.parentElement) {
      stopCamera(st);
      overlay.remove();
      document.removeEventListener('keydown', esc);
    }
  });
}
