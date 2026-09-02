/**
 * Inline fullsize image overlay used by the bridge result panel and the
 * sweep grid cells. Stays inside the page so it works in environments
 * (Tauri webview, mobile in-app browsers) where window.open does not
 * actually open a new top-level tab.
 *
 * Accepts any browser-loadable src — data:, blob:, or http(s):.
 */
export function openFullsize(src: string): void {
  const overlay = document.createElement('div');
  overlay.className = 'brp-fullsize-overlay';
  const img = document.createElement('img');
  img.src = src;
  img.alt = 'Fullsize';
  overlay.appendChild(img);
  const onKey = (e: KeyboardEvent): void => {
    if (e.key === 'Escape') {
      close();
    }
  };
  const close = (): void => {
    overlay.remove();
    document.removeEventListener('keydown', onKey);
  };
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });
  img.addEventListener('click', close);
  document.addEventListener('keydown', onKey);
  document.body.appendChild(overlay);
}
