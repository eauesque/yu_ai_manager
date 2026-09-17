export interface SearchPagerState {
  beginSearch(params: URLSearchParams | null): void;
  getParams(): URLSearchParams | null;
  setOffset(v: number): void;
  getOffset(): number;
  addOffset(v: number): void;
  setHasMore(v: boolean): void;
  getHasMore(): boolean;
  setLoading(v: boolean): void;
  isLoading(): boolean;
  setTotalCount(v: number): void;
  getTotalCount(): number;
  setCursor(v: string | null): void;
  getCursor(): string | null;
}

export function createSearchPagerState(): SearchPagerState {
  let searchParams: URLSearchParams | null = null;
  let searchOffset = 0;
  let searchHasMore = false;
  let searchLoading = false;
  let searchTotalCount = 0;
  let searchCursor: string | null = null;

  return {
    beginSearch(params) { searchParams = params; searchOffset = 0; searchHasMore = false; searchTotalCount = 0; searchCursor = null; },
    getParams() { return searchParams; },
    setOffset(v) { searchOffset = Number(v) || 0; },
    getOffset() { return searchOffset; },
    addOffset(v) { searchOffset += Number(v) || 0; },
    setHasMore(v) { searchHasMore = !!v; },
    getHasMore() { return !!searchHasMore; },
    setLoading(v) { searchLoading = !!v; },
    isLoading() { return !!searchLoading; },
    setTotalCount(v) { searchTotalCount = Number(v) || 0; },
    getTotalCount() { return searchTotalCount; },
    setCursor(v) { searchCursor = v || null; },
    getCursor() { return searchCursor; },
  };
}
