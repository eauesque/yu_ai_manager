/**
 * scan-banner entry point — initializes jobs polling and scroll button.
 */

import './ui';
import './jobs-core';
import './jobs-actions';
import * as jobs from './jobs';
import * as scroll from './scroll';

// Initialize
jobs.init();
scroll.init();
