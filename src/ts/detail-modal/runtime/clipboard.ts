import { getAppApi } from '../../shared/browser-apis';

// Decode HTML entities via shared app API
function _decode(text: string): string {
  return getAppApi().decodeHtmlEntities(text);
}

export async function copyToClipboard(text: string): Promise<boolean> {
  const decoded = _decode(text);
  // Try Clipboard API first (requires HTTPS or localhost)
  if (navigator.clipboard?.writeText) {
    try {
      await navigator.clipboard.writeText(decoded);
      return true;
    } catch (_err) {
      // Fall through to execCommand fallback
    }
  }
  // Fallback: textarea + execCommand (works on HTTP)
  try {
    const ta = document.createElement('textarea');
    ta.value = decoded;
    ta.style.cssText = 'position:fixed;left:-9999px;top:0;opacity:0;';
    document.body.appendChild(ta);
    ta.focus();
    ta.select();
    const ok = document.execCommand('copy');
    document.body.removeChild(ta);
    return !!ok;
  } catch (_) { return false; }
}
