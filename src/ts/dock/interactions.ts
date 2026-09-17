/**
 * Regex cheat sheet dock — interactions aggregator.
 *
 * Initialises all sub-interaction modules (hotkeys, scroller, resize)
 * in the correct order.
 */

import { bindCheatDockHotkeys } from './hotkeys';
import { enhanceCheatScroller } from './scroller';
import { initCheatResize } from './resize';

export function initCheatDockInteractions(): void {
  bindCheatDockHotkeys();
  enhanceCheatScroller();
  initCheatResize();
}
