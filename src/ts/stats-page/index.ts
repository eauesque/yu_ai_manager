/**
 * Stats page entry point.
 * Bundles: theme + charts (panels, core-utils, core) + data-loader.
 * Replaces 7 individual <script> tags with one bundled IIFE.
 */

import { initStatsThemeToggle } from './theme';
import { displayTimePeriods, displayPersonality, displayTurningPoints } from './charts/panels';
import type { TimePeriod, Personality, TurningPoint } from './charts/panels';
import { displayTimelineChart, displayTopTags, displayModelChart, displayResolutionChart } from './charts/core';
import { loadStats } from './data-loader';
import { installWindowApi } from '../shared/window-api';

// Self-init: apply theme immediately
initStatsThemeToggle();

installWindowApi('statsPageApi', {
  displayTimePeriods,
  displayPersonality,
  displayTurningPoints,
  displayTimelineChart,
  displayTopTags,
  displayModelChart,
  displayResolutionChart,
  loadStats,
});

// Wait for i18n before loading stats so period/personality labels translate
document.addEventListener('tr-runtime:ready', () => loadStats());
setTimeout(() => loadStats(), 2000); // fallback if i18n never fires
