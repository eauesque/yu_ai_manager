/**
 * nav/konami — Konami Code Easter Egg (retro theme toggle).
 *
 * Sequence: Up Up Down Down Left Right Left Right B A
 * Toggles `theme-retro` class on body and persists in localStorage.
 * Shows a centered toast notification on activation/deactivation.
 */

const KONAMI_SEQ: readonly number[] = [38, 38, 40, 40, 37, 39, 37, 39, 66, 65];
const STORAGE_KEY = 'theme-retro';
let _pos = 0;
let _initialized = false;

/** Show a temporary centered toast notification. */
function showKonamiToast(isRetro: boolean): void {
  const msg = isRetro ? 'RETRO MODE ACTIVATED' : 'Retro mode deactivated';
  const toast = document.createElement('div');
  toast.textContent = msg;

  const baseStyle =
    'position:fixed;top:50%;left:50%;transform:translate(-50%,-50%);' +
    'z-index:99999;padding:16px 32px;border-radius:12px;font-size:18px;' +
    'font-weight:bold;pointer-events:none;transition:opacity 0.8s;';

  const retroStyle =
    'background:linear-gradient(135deg,#1a0040,#2a0060);color:#e0d0ff;' +
    'border:2px solid rgba(191,90,242,0.6);' +
    'box-shadow:0 0 40px rgba(191,90,242,0.5),0 0 80px rgba(191,90,242,0.2);' +
    'text-shadow:0 0 12px rgba(255,110,242,0.8);';

  const normalStyle =
    'background:var(--card,#1b1f2a);color:var(--text,#e7eaf0);' +
    'border:1px solid var(--border,#2b3240);box-shadow:var(--shadow);';

  toast.style.cssText = baseStyle + (isRetro ? retroStyle : normalStyle);
  document.body.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
  }, 1500);
  setTimeout(() => {
    if (toast.parentNode) toast.parentNode.removeChild(toast);
  }, 2400);
}

export function restoreRetroTheme(): void {
  if (localStorage.getItem(STORAGE_KEY) === '1') {
    document.body.classList.add('theme-retro');
  }
}

function _handleKeyCode(keyCode: number): void {
  if (keyCode === KONAMI_SEQ[_pos]) {
    _pos++;
    if (_pos === KONAMI_SEQ.length) {
      _pos = 0;
      const isRetro = document.body.classList.toggle('theme-retro');
      localStorage.setItem(STORAGE_KEY, isRetro ? '1' : '0');
      showKonamiToast(isRetro);
    }
  } else {
    _pos = keyCode === KONAMI_SEQ[0] ? 1 : 0;
  }
}

/** Initialize the Konami Code listener and restore previous retro state. */
export function initKonami(): void {
  if (_initialized) return;
  _initialized = true;
  restoreRetroTheme();
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    _handleKeyCode(e.keyCode);
  });
}

export function handleKonamiKeydown(keyCode: number): void {
  _handleKeyCode(keyCode);
}
