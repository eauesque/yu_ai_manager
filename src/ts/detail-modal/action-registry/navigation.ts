import type { DetailModalActionRegistry, DetailModalActionRegistryDeps } from './types';

export function createDetailModalNavigationActions(
  deps: Pick<DetailModalActionRegistryDeps, 'navigateModal' | 'scrollFilmstripPage' | 'showDetail'>,
): DetailModalActionRegistry {
  return {
    detailModalShowFromThumb: ({ element }) => {
      const id = Number(element.dataset.fid);
      const scope = element.dataset.scope;
      if (!Number.isFinite(id)) return;
      deps.showDetail(id, scope ? { scope } : undefined);
    },
    navigateModal: ({ arg }) => {
      deps.navigateModal(Number(arg));
    },
    scrollFilmstripPage: ({ arg }) => {
      deps.scrollFilmstripPage(Number(arg));
    },
  };
}
