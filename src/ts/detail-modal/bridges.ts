import type { runtimeStateApi, modalDetailStateApi } from './runtime/state';
import type { detailModalRuntimeControls } from './runtime/controls';
import type { detailModalViewer } from './viewer/exports';
import type { DetailModalCompatApi } from './bridge-compat';
import { initOcrTab } from './tabs/ocr-panel';
import { initS2tTab } from './tabs/s2t-panel';
import { initAnnotationsTab } from './tabs/annotations-panel';
import { initAnalysisTraceTab } from './tabs/analysis-trace-panel';
import { installWindowApi } from '../shared/window-api';

interface DetailModalBridgeDeps {
  detailModalViewer: typeof detailModalViewer;
  runtimeStateApi: typeof runtimeStateApi;
  detailModalRuntimeControls: typeof detailModalRuntimeControls;
  modalDetailStateApi: typeof modalDetailStateApi;
  compatApi: DetailModalCompatApi;
}

export function installDetailModalWindowBridges(deps: DetailModalBridgeDeps): void {
  installWindowApi('detailModalApi', {
    viewer: deps.detailModalViewer,
    runtimeState: deps.runtimeStateApi,
    runtimeControls: deps.detailModalRuntimeControls,
    modalDetailState: deps.modalDetailStateApi,
    initOcrTab,
    initS2tTab,
    initAnnotationsTab,
    initAnalysisTraceTab,
    ...deps.compatApi,
  }, {
    detailModalViewer: 'viewer',
    detailModalRuntimeState: 'runtimeState',
    detailModalRuntimeControls: 'runtimeControls',
    modalDetailState: 'modalDetailState',
  });
}
