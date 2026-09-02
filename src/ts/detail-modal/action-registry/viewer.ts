import type { DetailModalActionRegistry, DetailModalActionRegistryDeps } from './types';

export function createDetailModalViewerActions(
  deps: Pick<
    DetailModalActionRegistryDeps,
    'setFitCustomHeight' | 'setImageMode' | 'toggleFullscreen' | 'zoomReset' | 'zoomStep'
  >,
): DetailModalActionRegistry {
  return {
    detailModalSetFitCustomHeight: ({ element }) => {
      deps.setFitCustomHeight((element as HTMLInputElement).value);
    },
    setImageMode: ({ arg }) => {
      deps.setImageMode(arg || 'fit');
    },
    toggleFullscreen: () => {
      deps.toggleFullscreen();
    },
    zoomReset: () => {
      deps.zoomReset();
    },
    zoomStep: ({ arg }) => {
      deps.zoomStep(Number(arg));
    },
  };
}
