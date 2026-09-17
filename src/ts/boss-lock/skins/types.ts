/**
 * boss-lock / skins / types — shared types & helpers for skin modules.
 */

import type { BossModeEdition } from '../edition-data';

export type SkinId = 'ft' | 'wsj' | 'bloomberg' | 'nikkei';
export type EscFn = (s: unknown) => string;
export type TrFn = (key: string) => string;

export interface Skin {
  id: SkinId;
  build(ed: BossModeEdition, trFn: TrFn, escFn: EscFn): string;
}

/* ------------------------------------------------------------------ */
/*  Cosmetic helpers (random vol/issue/edition/weather/price)          */
/* ------------------------------------------------------------------ */

export const ROMAN_VOLS = ['CXXI', 'CXXII', 'CXXIII', 'CXXIV', 'CXXV', 'CXXVI', 'CLIII', 'CLXXXVIII'];
export const EDITION_TAGS = ['Late Edition', 'Final Edition', 'Morning Edition', 'City Edition', 'National Edition'];
export const WEATHER_LINES = [
  'Tokyo: Mostly Cloudy 18°C',
  'London: Showers 11°C',
  'New York: Clear 14°C',
  'Hong Kong: Humid 24°C',
  'Frankfurt: Overcast 9°C',
  'Singapore: Storms 28°C',
];
export const PRICES = ['¥350', '¥420', '£3.50', '$4.00', '€3.20', 'HK$15'];

export function pick<T>(arr: T[]): T { return arr[Math.floor(Math.random() * arr.length)]; }

export function formatDateUS(d: Date): string {
  return d.toLocaleDateString('en-US', { weekday: 'long', year: 'numeric', month: 'long', day: 'numeric' }).toUpperCase();
}

export function buildIssueNo(): string {
  const n = 3000 + Math.floor(Math.random() * 5000);
  return n.toLocaleString('en-US');
}
