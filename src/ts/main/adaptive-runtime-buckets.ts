/**
 * Adaptive runtime buckets — time/season/date categorization.
 * Converted from static/js/main/main-adaptive-runtime-buckets.js
 */

import { state } from './adaptive-runtime-state';

export function getTimeBucket(now: Date = new Date()): string {
  const h = now.getHours();
  if (h < 5) return 'late_night';
  if (h < 8) return 'early_morning';
  if (h < 11) return 'morning';
  if (h < 14) return 'noon';
  if (h < 18) return 'afternoon';
  if (h < 21) return 'evening';
  return 'night';
}

export function getSeasonBucket(now: Date = new Date()): string {
  const m = now.getMonth() + 1;
  if (m >= 3 && m <= 5) return 'spring';
  if (m >= 6 && m <= 8) return 'summer';
  if (m >= 9 && m <= 11) return 'autumn';
  return 'winter';
}

export function getDayTypeBucket(now: Date = new Date()): string {
  const d = now.getDay();
  return d === 0 || d === 6 ? 'weekend' : 'weekday';
}

export function getMonthEventBucket(now: Date = new Date()): string {
  const m = now.getMonth() + 1;
  const day = now.getDate();
  if (m === 1 && day <= 10) return 'new_year';
  if (m === 4 && day >= 26) return 'golden_week';
  if (m === 5 && day <= 6) return 'golden_week';
  if (m >= 7 && m <= 8) return 'summer_holiday';
  if (m === 12 && day >= 20) return 'year_end';
  return 'normal_month';
}

export function getCurrentLang(): string {
  const stored = (localStorage.getItem('lang') || '').trim().toLowerCase();
  if (stored) return stored;
  const nav = String(navigator.language || 'en').toLowerCase();
  return nav.split('-')[0] || 'en';
}

// Wire into shared state
state.getTimeBucket = getTimeBucket;
state.getSeasonBucket = getSeasonBucket;
state.getDayTypeBucket = getDayTypeBucket;
state.getMonthEventBucket = getMonthEventBucket;
state.getCurrentLang = getCurrentLang;
