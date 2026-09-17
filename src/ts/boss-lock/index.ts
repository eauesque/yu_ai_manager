/**
 * boss-lock entry point — initializes the boss-mode camouflage overlay.
 */

import * as utils from './utils';
import { buildBossModeEdition } from './edition';
import './template';
import * as render from './render';
import * as actions from './actions';
import { installWindowApi } from '../shared/window-api';

/* ------------------------------------------------------------------ */
/*  Window bridges: function shortcuts (onclick handlers)              */
/* ------------------------------------------------------------------ */

installWindowApi('bossLockApi', {
  buildBossModeEdition,
  stopAllMediaPlayback: utils.stopAllMediaPlayback,
  showBossMode: render.showBossMode,
  hideBossMode: render.hideBossMode,
  maybeLaunchBossModeFromQuery: actions.maybeLaunchBossModeFromQuery,
  activateQuickLock: actions.activateQuickLock,
}, {
  buildBossModeEdition: 'buildBossModeEdition',
  stopAllMediaPlayback: 'stopAllMediaPlayback',
  showBossMode: 'showBossMode',
  hideBossMode: 'hideBossMode',
  maybeLaunchBossModeFromQuery: 'maybeLaunchBossModeFromQuery',
  activateQuickLock: 'activateQuickLock',
});
