/**
 * Inspect page — drag-and-drop zone setup + ZIP selector UI.
 * Leaf module: no imports from sibling inspect-page modules.
 */

/** Inspect API response shape. */
export interface InspectData {
  error?: string;
  zip_images?: string[];
  zip_current?: string;
  raw_metadata?: Record<string, unknown>;
  raw_meta_json?: string;
  positive?: string;
  positive_prompt?: string;
  negative?: string;
  negative_prompt?: string;
  meta_source?: string;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  novelai_v4?: Record<string, any>;
  [key: string]: unknown;
}

/** Callback type for file handling. */
export type FileHandler = (file: File, zipEntry?: string) => void;

/** Module-level state for ZIP re-inspection. */
let _lastZipFile: File | null = null;
let _fileHandler: FileHandler | null = null;

/** Simple HTML-escape via DOM. */
export function escHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}

/** Resolve a tr() key with a literal fallback. */
export function _t(key: string, fallback: string): string {
  const trFn = typeof window.tr === 'function' ? window.tr : null;
  if (!trFn) return fallback;
  return (trFn(key) as string) || fallback;
}

// ─── Drag-and-drop setup ────────────────────────────────────────

/**
 * Initialise the drop zone element with drag-and-drop listeners.
 * @param onFile — callback invoked when a file is dropped or selected.
 */
export function initDropZone(onFile: FileHandler): void {
  _fileHandler = onFile;

  const dropZone = document.getElementById('dropZone');
  if (!dropZone) return;

  dropZone.addEventListener('dragover', (e: DragEvent) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  dropZone.addEventListener('dragleave', () => {
    dropZone.classList.remove('dragover');
  });

  dropZone.addEventListener('drop', (e: DragEvent) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer && e.dataTransfer.files.length > 0) {
      onFile(e.dataTransfer.files[0]);
    }
  });
}

// ─── ZIP selector ────────────────────────────────────────────────

/**
 * Render the ZIP image selector dropdown.
 * @param images — list of image paths inside the ZIP
 * @param current — currently selected entry
 */
export function renderZipSelector(images: string[], current: string | undefined): void {
  let container = document.getElementById('zipSelector');
  if (!container) {
    container = document.createElement('div');
    container.id = 'zipSelector';
    container.style.cssText =
      'margin-bottom:12px;padding:10px;border-radius:8px;border:1px solid rgba(128,128,128,0.3);background:rgba(0,0,0,0.1);';
    const resultArea = document.getElementById('resultArea');
    if (resultArea) resultArea.insertBefore(container, resultArea.firstChild);
  }

  let html =
    '<label style="font-size:13px;color:var(--muted,#888);">'
    + _t('inspect.zip_select', 'Image in ZIP') + ' (' + images.length + '): </label>'
    + '<select id="zipEntrySelect" style="margin-left:6px;padding:4px 8px;border-radius:4px;border:1px solid rgba(128,128,128,0.3);background:var(--bg,#1a1a2e);color:var(--text,#eee);font-size:12px;max-width:400px;">';

  for (let i = 0; i < images.length; i++) {
    const sel = images[i] === current ? ' selected' : '';
    html += '<option value="' + escHtml(images[i]) + '"' + sel + '>' + escHtml(images[i]) + '</option>';
  }
  html += '</select>';

  container.innerHTML = html;
  container.style.display = 'block';

  // Bind change handler
  const select = document.getElementById('zipEntrySelect') as HTMLSelectElement | null;
  if (select) {
    select.addEventListener('change', () => {
      onZipEntryChange();
    });
  }
}

export function hideZipSelector(): void {
  const container = document.getElementById('zipSelector');
  if (container) container.style.display = 'none';
}

function onZipEntryChange(): void {
  const select = document.getElementById('zipEntrySelect') as HTMLSelectElement | null;
  if (!select || !_lastZipFile || !_fileHandler) return;
  _fileHandler(_lastZipFile, select.value);
}

// ─── ZIP file state helpers ──────────────────────────────────────

export function setLastZipFile(file: File | null): void {
  _lastZipFile = file;
}
