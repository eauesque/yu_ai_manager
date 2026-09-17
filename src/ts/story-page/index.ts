/**
 * Story page entry point.
 * Bundles: page (loadStory + displayStory).
 * Replaces 1 <script> tag with one bundled IIFE.
 */

import { loadStory, initStoryPage } from './page';
import { installWindowApi } from '../shared/window-api';

// Local window augmentation for story-page bridge
declare global {
  interface Window {
    loadStory: () => Promise<void>;
  }
}

// Bridge: expose loadStory for unconverted consumers
installWindowApi('storyPageApi', {
  loadStory,
}, {
  loadStory: 'loadStory',
});

// Self-init: start loading story data (with tr-runtime wait)
initStoryPage();
