type CompatFn = (...args: any[]) => unknown;

export interface DetailModalCompatApi {
  [key: string]: CompatFn;
}

interface DetailModalCompatBridgeDeps {
  closeModal: () => void;
  copyToClipboard: (text: string) => Promise<boolean>;
  searchByTag: (tag: string) => void;
  showDetail: (id: number, opts?: { scope?: string }) => void;
}

export function createDetailModalCompatApi(deps: DetailModalCompatBridgeDeps): DetailModalCompatApi {
  return {
    closeModal: deps.closeModal,
    copyToClipboard: deps.copyToClipboard,
    searchByTag: deps.searchByTag,
    showDetail: deps.showDetail,
  };
}
