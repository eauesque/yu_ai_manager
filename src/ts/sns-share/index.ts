/**
 * sns-share/index.ts — Entry point. Exposes window bridge functions.
 */

import { showSnsShareModal, closeSnsShareModal } from './sns-share-modal';
import { installWindowApi } from '../shared/window-api';

declare const window: Window & {
  showSnsShare?: (fileId: number) => Promise<void>;
  closeSnsShare?: () => void;
};

installWindowApi('snsShareApi', {
  showSnsShare: showSnsShareModal,
  closeSnsShare: closeSnsShareModal,
}, {
  showSnsShare: 'showSnsShare',
  closeSnsShare: 'closeSnsShare',
});

export { showSnsShareModal, closeSnsShareModal };
