/**
 * boss-lock / skins / index — random skin dispatcher.
 *
 * Picks a skin per overlay show. Supports `?skin=<id>` URL override for QA
 * and `localStorage.bossModeSkin = '<id>'` for sticky personal preference.
 */

import type { BossModeEdition } from '../edition-data';
import type { EscFn, TrFn, Skin, SkinId } from './types';
import { ft } from './ft';
import { wsj } from './wsj';
import { bloomberg } from './bloomberg';
import { nikkei } from './nikkei';

export type { SkinId } from './types';
export { renderStaticQuoteRows, renderLiveQuoteRows } from './quote-rows';
export type { LiveQuoteRow } from './quote-rows';

const SKINS: Record<SkinId, Skin> = { ft, wsj, bloomberg, nikkei };
const SKIN_IDS: SkinId[] = ['ft', 'wsj', 'bloomberg', 'nikkei'];

function readQueryOverride(): SkinId | null {
  try {
    const u = new URL(window.location.href);
    const f = u.searchParams.get('skin');
    if (f && (SKIN_IDS as string[]).includes(f)) return f as SkinId;
  } catch { /* ignore */ }
  return null;
}

function readStoredOverride(): SkinId | null {
  try {
    const v = (localStorage.getItem('bossModeSkin') || '').trim().toLowerCase();
    if (v && (SKIN_IDS as string[]).includes(v)) return v as SkinId;
  } catch { /* ignore */ }
  return null;
}

export function pickSkin(): SkinId {
  return readQueryOverride() ?? readStoredOverride() ?? SKIN_IDS[Math.floor(Math.random() * SKIN_IDS.length)];
}

export function buildOverlayHtml(ed: BossModeEdition, trFn: TrFn, escFn: EscFn): string {
  return SKINS[pickSkin()].build(ed, trFn, escFn);
}
