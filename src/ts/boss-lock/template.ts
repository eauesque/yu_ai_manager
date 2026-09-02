/**
 * boss-lock / template — re-export thin shim.
 *
 * The actual implementation lives under `./skins/`. Each render randomly
 * selects one of the four broadsheet/terminal skins (ft, wsj, bloomberg,
 * nikkei). See `./skins/index.ts` for the dispatcher.
 */

export type { LiveQuoteRow } from './skins/quote-rows';
export { renderStaticQuoteRows, renderLiveQuoteRows } from './skins/quote-rows';
export { buildOverlayHtml, pickSkin } from './skins/index';
export type { SkinId } from './skins/index';
