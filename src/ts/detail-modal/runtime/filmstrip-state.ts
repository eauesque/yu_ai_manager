let _filmstripPinned = false;

export function initFilmstripPinnedFromStorage(): void {
  _filmstripPinned = localStorage.getItem('filmstripPinned') === '1';
}

export function isFilmstripPinned(): boolean {
  return _filmstripPinned;
}

export function setFilmstripPinned(value: boolean): void {
  _filmstripPinned = value;
  localStorage.setItem('filmstripPinned', value ? '1' : '0');
}
