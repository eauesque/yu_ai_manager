// runtime-pre — entry point (loads before main-utils.js and search-results.js)
import './ui-state';
import { openContainerViewForFile, openContainerViewForCurrentDetail } from './container-view';
import { installWindowApi } from '../shared/window-api';

export function installRuntimePreWindowBridges(): void {
  installWindowApi('runtimePreApi', {
    openContainerViewForCurrentDetail,
    openContainerViewForFile,
  }, {
    openContainerViewForCurrentDetail: 'openContainerViewForCurrentDetail',
    openContainerViewForFile: 'openContainerViewForFile',
  });
}

installRuntimePreWindowBridges();
