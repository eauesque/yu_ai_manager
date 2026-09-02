/**
 * ratings/index.ts — Entry point, window bridge registration.
 */

import { setRating, getRatingsBatch, getRating, createRatingWidget, getCardRatingHtml } from './ratings';
import { installWindowApi } from '../shared/window-api';

// Window bridges
installWindowApi('ratingsApi', {
  setRating,
  getRatingsBatch,
  getRating,
  createRatingWidget,
  getCardRatingHtml,
});
