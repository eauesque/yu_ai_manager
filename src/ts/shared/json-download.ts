/**
 * Shared JSON download helper.
 * Used by both runtime-tools-ui (search page) and inspect-page handlers.
 */

/**
 * Trigger a browser download of JSON content encoded in a data attribute.
 *
 * @param el - Element carrying `data-download-json-b64` (base64-encoded UTF-8 JSON)
 *             and optionally `data-download-filename` (defaults to "workflow.json").
 * @returns true if download was triggered, false if the element lacked the required attribute.
 */
export function handleJsonDownloadClick(el: HTMLElement): boolean {
  const b64 = el.dataset.downloadJsonB64;
  const filename = el.dataset.downloadFilename || 'workflow.json';
  if (!b64) return false;

  // Same decode pattern as existing .copy-target handler in intro.ts.
  const text = decodeURIComponent(escape(atob(b64)));
  const blob = new Blob([text], { type: 'application/json' });
  const url = URL.createObjectURL(blob);

  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);

  // Defer revoke so the browser has time to start the download.
  window.setTimeout(() => URL.revokeObjectURL(url), 100);
  return true;
}
