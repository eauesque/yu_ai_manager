let _savedScrollY: number | null = null;
let _isPageReturn = false;
let _startupAutoSearch = false;

export function setSavedScrollY(value: number | null): void {
  _savedScrollY = value;
}

export function getSavedScrollY(): number | null {
  return _savedScrollY;
}

export function setIsPageReturn(value: boolean): void {
  _isPageReturn = value;
}

export function isPageReturn(): boolean {
  return _isPageReturn;
}

export function setStartupAutoSearch(value: boolean): void {
  _startupAutoSearch = value;
}

export function isStartupAutoSearch(): boolean {
  return _startupAutoSearch;
}
