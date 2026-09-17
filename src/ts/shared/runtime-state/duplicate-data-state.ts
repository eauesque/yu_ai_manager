import type { DuplicateData } from '../../tools-page/duplicates/render';

let duplicateData: DuplicateData | null = null;

export function setDuplicateData(data: DuplicateData | null): void {
  duplicateData = data;
}

export function getDuplicateData(): DuplicateData | null {
  return duplicateData;
}
