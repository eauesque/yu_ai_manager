type FitMode = 'cover' | 'contain';

const FIT_STORAGE_KEY = 'sweepView.fit';
const _gridImages: HTMLImageElement[] = [];

let _currentFit: FitMode =
  (typeof localStorage !== 'undefined'
    && localStorage.getItem(FIT_STORAGE_KEY) === 'contain') ? 'contain' : 'cover';

export function currentFit(): FitMode {
  return _currentFit;
}

export function applyFitToImage(img: HTMLImageElement): void {
  img.style.objectFit = _currentFit;
  img.style.background = _currentFit === 'contain'
    ? 'rgba(0,0,0,0.18)'
    : 'rgba(127,127,127,0.12)';
}

export function trackGridImage(img: HTMLImageElement): void {
  _gridImages.push(img);
}

export function clearGridImages(): void {
  _gridImages.length = 0;
}

export function setFitMode(mode: FitMode): void {
  _currentFit = mode;
  try { localStorage.setItem(FIT_STORAGE_KEY, mode); } catch (_e) { /* no-op */ }
  for (const img of _gridImages) applyFitToImage(img);
}

export type { FitMode };
