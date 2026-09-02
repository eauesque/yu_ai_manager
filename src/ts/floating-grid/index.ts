/**
 * floating-grid entry point — initializes the floating grid control panel.
 */

import {
  isPanelOpen, closePanel,
} from './state';
import './apply';
import { installWindowApi } from '../shared/window-api';

// Import init for side effects (event bindings, observer, state restore)
import './init';

// Bridge: expose minimal API for cross-module consumers (keyboard shortcuts)
const floatingGridApi = {
  isPanelOpen,
  closePanel,
};

installWindowApi('floatingGridApi', floatingGridApi);

// window.updateGridCompactMode is set in init.ts (side-effect import)
