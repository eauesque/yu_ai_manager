/**
 * container-view/index.ts — Window bridge registration + initialization.
 */

import { isContainerViewOpen } from './state';
import {
  openContainerViewPanel,
  closeContainerViewPanel,
  returnToContainerView,
  initPanelButtons,
} from './panel';
import { installWindowApi } from '../shared/window-api';

// Window bridge for cross-module / template access
installWindowApi('containerViewApi', {
  openContainerViewPanel,
  closeContainerViewPanel,
  isContainerViewOpen,
  returnToContainerView,
});

// Wire panel buttons once DOM is ready
if (document.readyState === 'loading') {
  document.addEventListener('DOMContentLoaded', initPanelButtons);
} else {
  initPanelButtons();
}
