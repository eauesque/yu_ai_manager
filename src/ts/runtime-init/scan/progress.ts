/**
 * Scan progress controller — legacy stubs.
 *
 * Active job progress is now handled by nav/job-progress.ts (SSE + polling).
 * These functions remain as no-op runtimeInitApi scan-progress stubs.
 */

// eslint-disable-next-line @typescript-eslint/no-unused-vars
export function startScanProgress(_rootPath: string, _recursive = true, _force = false): void {
  // No-op: progress display is handled by nav/job-progress.ts
}

export function hideScanProgress(): void {
  const bar = document.getElementById('scanProgressBar');
  if (bar) bar.classList.remove('active');
}
