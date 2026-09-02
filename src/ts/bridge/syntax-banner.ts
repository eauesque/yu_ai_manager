/**
 * Syntax warning banner for NAI / SD bridge prompt textareas.
 *
 * Watches a textarea for input, detects SD vs NAI syntax, shows a warning
 * banner with a convert button.  Calls /api/convert to perform the conversion.
 */

import { detectSyntax } from './syntax-detect';
import { getAppApi, getNavApi } from '../shared/browser-apis';

// Re-export so bridge-app.ts can pick it up as a single name.
export { setupSyntaxBanner };

/** Debounce helper */
function debounce<T extends (...args: unknown[]) => void>(fn: T, ms: number): T {
  let timer: ReturnType<typeof setTimeout>;
  return ((...args: unknown[]) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), ms);
  }) as T;
}

/**
 * Insert text into a textarea in an undo-able way.
 * Falls back to direct .value assignment when execCommand is unavailable.
 */
function insertTextWithUndo(textarea: HTMLTextAreaElement, value: string): void {
  textarea.focus();
  textarea.select();
  if (!document.execCommand('insertText', false, value)) {
    textarea.value = value;
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
  }
}

/**
 * Attach a syntax-detection banner to a textarea.
 *
 * @param textarea      - The prompt textarea to watch
 * @param bannerId      - id of the <div class="syntax-warning-banner"> element
 * @param mode          - 'sd_to_nai': warn when SD syntax found (NAI bridge)
 *                        'nai_to_sd': warn when NAI syntax found (SD bridge)
 * @param convertAction - data-action value for the convert button
 * @param dismissAction - data-action value for the dismiss button
 */
function setupSyntaxBanner(
  textarea: HTMLTextAreaElement,
  bannerId: string,
  mode: 'sd_to_nai' | 'nai_to_sd',
  convertAction: string,
  dismissAction: string,
): void {
  const banner = document.getElementById(bannerId);
  if (!banner) return;

  let dismissed = false;
  const { apiFetch, tr } = getAppApi();
  const { showToast } = getNavApi();

  function showBanner(show: boolean): void {
    if (show && !dismissed) {
      banner!.removeAttribute('hidden');
      banner!.setAttribute('data-visible', '');
    } else {
      banner!.setAttribute('hidden', '');
      banner!.removeAttribute('data-visible');
    }
  }

  function checkSyntax(): void {
    const result = detectSyntax(textarea.value);
    const shouldWarn = mode === 'sd_to_nai'
      ? result === 'sd' || result === 'mixed'
      : result === 'nai' || result === 'mixed';
    showBanner(shouldWarn);
  }

  const debouncedCheck = debounce(checkSyntax as (...args: unknown[]) => void, 300);
  textarea.addEventListener('input', () => debouncedCheck());

  banner.addEventListener('click', async (e) => {
    const target = e.target as HTMLElement;

    // Convert button
    const convertBtn = target.closest<HTMLButtonElement>(`[data-action="${convertAction}"]`);
    if (convertBtn) {
      const originalText = convertBtn.textContent || '';
      convertBtn.textContent = tr('bridge.syntax_warning.converting', 'Converting...');
      convertBtn.disabled = true;

      try {
        const resp = await apiFetch('/api/convert', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ prompt: textarea.value, mode }),
        });
        const data = await resp.json() as { result?: string };
        if (data.result) {
          insertTextWithUndo(textarea, data.result);
          showBanner(false);
        } else {
          showToast(tr('bridge.syntax_warning.error', 'Conversion failed'), true);
        }
      } catch {
        showToast(tr('bridge.syntax_warning.error', 'Conversion failed'), true);
      } finally {
        convertBtn.textContent = originalText;
        convertBtn.disabled = false;
      }
    }

    // Dismiss button
    const dismissBtn = target.closest<HTMLElement>(`[data-action="${dismissAction}"]`);
    if (dismissBtn) {
      dismissed = true;
      showBanner(false);
    }
  });
}
