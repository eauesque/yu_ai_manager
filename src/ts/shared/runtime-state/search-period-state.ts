let _searchFromTs: string | null = null;

export function getSearchFromTs(): string | null {
  return _searchFromTs;
}

export function setSearchFromTs(value: string | null): void {
  _searchFromTs = value;
}
