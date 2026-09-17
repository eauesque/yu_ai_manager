/**
 * share-page entry point — initializes the prompt share page.
 * Replaces 2 individual <script> tags with one bundled IIFE.
 *
 * Exposes namespaced browser API for template actions.
 */

import { decodeShareData, renderShareData, copyPrompt, copyAll, showCopied, escHtml } from './page';
import { decodeQRFile } from './qr';
import { installWindowApi } from '../shared/window-api';
import { createPagePerfTracker } from '../shared/page-perf';
const _perf = createPagePerfTracker('share');
_perf.markOnce('module_ready');

installWindowApi('sharePageApi', {
  decodeShareData,
  renderShareData,
  copyPrompt,
  copyAll,
  showCopied,
  escHtml,
  decodeQRFile,
});

function _initSharePage(): void {
  const run = () => decodeShareData();
  const win = window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void };
  if (typeof win.requestIdleCallback === 'function') {
    win.requestIdleCallback(run, { timeout: 800 });
  } else {
    setTimeout(run, 0);
  }
}

if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', () => {
    _perf.markOnce('dom_ready');
    _initSharePage();
  }, { once: true });
} else {
  _initSharePage();
}
