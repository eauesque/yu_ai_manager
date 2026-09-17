/**
 * Theme QR sharing — entry point.
 * Delegates to qr-export-dialog (export) and qr-import-dialog (import).
 */

import { showExportDialog } from './qr-export-dialog';
import { showImportDialog } from './qr-import-dialog';
import { setQrExportCallback, setQrImportCallback } from './manager-ui';

/** Initialize: register QR callbacks on the theme manager. */
export function initThemeQr(): void {
  setQrExportCallback(showExportDialog);
  setQrImportCallback(showImportDialog);
}
