const _unionCheckedIds = new Set<number>();

export function getUnionCheckedIds(): number[] {
  return Array.from(_unionCheckedIds);
}

export function hasUnionCheckedId(id: number): boolean {
  return _unionCheckedIds.has(id);
}

export function setUnionChecked(id: number, checked: boolean): void {
  if (checked) {
    _unionCheckedIds.add(id);
  } else {
    _unionCheckedIds.delete(id);
  }
}

export function clearUnionCheckedIds(): void {
  _unionCheckedIds.clear();
}

export function getUnionCheckedCount(): number {
  return _unionCheckedIds.size;
}
