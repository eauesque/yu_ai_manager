import type { ShareData } from '../../share-page/page';

let shareData: ShareData | null = null;

export function setShareData(data: ShareData | null): void {
  shareData = data;
}

export function getShareData(): ShareData | null {
  return shareData;
}
