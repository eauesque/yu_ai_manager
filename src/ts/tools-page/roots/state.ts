/**
 * roots/state.ts -- Global state for scan roots management.
 * Converted from tools-roots-state.js
 */

export interface ScanRoot {
  path: string;
  recursive?: boolean;
  enabled?: boolean;
  comment?: string;
  file_count?: number;
  exists?: boolean;
}

export let rootsData: ScanRoot[] = [];
export let selectedRootIdx = -1;
export let dragIdx = -1;

export function setRootsData(data: ScanRoot[]): void {
  rootsData = data;
}

export function setSelectedRootIdx(idx: number): void {
  selectedRootIdx = idx;
}

export function setDragIdx(idx: number): void {
  dragIdx = idx;
}
