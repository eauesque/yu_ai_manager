/**
 * autocomplete-fetch.ts -- Data fetching functions for tag, LoRA,
 * embedding, and wildcard autocomplete suggestions.
 */

import { BridgeWildcardCache } from './wildcard-cache';

export interface AcItem {
  label: string;
  sub?: string;
  value: string;
  category?: number;
}

const MAX_RESULTS = 10;

/** Category ID to display label mapping */
export const CATEGORY_LABELS: Record<number, string> = {
  0: 'General', 1: 'Artist', 3: 'Copyright', 4: 'Character', 5: 'Meta',
};

/** Shared abort controller for cancelling in-flight requests */
let _bridgeAcAbort: AbortController | null = null;

export function cancelPrev(): AbortSignal {
  if (_bridgeAcAbort) _bridgeAcAbort.abort();
  _bridgeAcAbort = new AbortController();
  return _bridgeAcAbort.signal;
}

export function getAbortSignal(): AbortSignal | undefined {
  return _bridgeAcAbort?.signal;
}

/* ------------------------------------------------------------------ */
/* Tag fetching                                                        */
/* ------------------------------------------------------------------ */

export function fetchTagDict(
  query: string,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  const signal = cancelPrev();
  fetch('/api/tag-dict/search?q=' + encodeURIComponent(query) + '&limit=' + MAX_RESULTS, { signal })
    .then((r) => r.json())
    .then((data: { results?: Array<{ tag_name: string; category: number; post_count: number }> }) => {
      if (!data.results?.length) {
        fetchDanbooruLive(query, showCb, hideCb);
        return;
      }
      showCb(data.results.map((t) => ({
        label: t.tag_name,
        sub: (CATEGORY_LABELS[t.category] || '') + ' (' + t.post_count.toLocaleString() + ')',
        value: t.tag_name,
        category: t.category,
      })));
    })
    .catch(() => fetchDanbooruLive(query, showCb, hideCb));
}

function fetchDanbooruLive(
  query: string,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  const signal = getAbortSignal();
  fetch('/ext/prompt-sim/danbooru-ac?q=' + encodeURIComponent(query) + '&limit=' + MAX_RESULTS, { signal: signal as AbortSignal })
    .then((r) => r.json())
    .then((data: { tags?: Array<{ name: string; count?: number }> }) => {
      const tags: AcItem[] = (data.tags || []).map((t) => ({
        label: t.name,
        sub: t.count ? '(' + t.count.toLocaleString() + ')' : '',
        value: t.name,
      }));
      if (tags.length) showCb(tags);
      else hideCb();
    })
    .catch(() => hideCb());
}

/* ------------------------------------------------------------------ */
/* LoRA fetching                                                       */
/* ------------------------------------------------------------------ */

export function fetchLora(
  query: string,
  bridgeBase: string | undefined,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  if (!bridgeBase) {
    fetchLoraDB(query, showCb, hideCb);
    return;
  }
  const signal = cancelPrev();
  fetch(bridgeBase + '/api/loras?q=' + encodeURIComponent(query), { signal })
    .then((r) => r.json())
    .then((data: { loras?: Array<string | { name: string; alias?: string }> }) => {
      const raw = data.loras || [];
      const loras: AcItem[] = raw.slice(0, MAX_RESULTS).map((l) => {
        const name = typeof l === 'string' ? l : l.name || '';
        const alias = typeof l === 'object' && l.alias ? l.alias : '';
        const sub = alias && alias !== name ? 'LoRA (live) - ' + alias : 'LoRA (live)';
        return { label: name, sub, value: name };
      });
      if (loras.length) showCb(loras);
      else fetchLoraDB(query, showCb, hideCb);
    })
    .catch(() => fetchLoraDB(query, showCb, hideCb));
}

function fetchLoraDB(
  query: string,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  const signal = getAbortSignal();
  fetch('/api/suggest/lora?q=' + encodeURIComponent(query) + '&limit=' + MAX_RESULTS, { signal: signal as AbortSignal })
    .then((r) => r.json())
    .then((data: { loras?: Array<string | { name: string }>; results?: Array<string | { name: string }> }) => {
      const loras: AcItem[] = (data.loras || data.results || []).map((l) => {
        const name = typeof l === 'string' ? l : l.name || '';
        return { label: name, sub: 'LoRA', value: name };
      });
      if (loras.length) showCb(loras);
      else hideCb();
    })
    .catch(() => hideCb());
}

/* ------------------------------------------------------------------ */
/* Embedding fetching                                                  */
/* ------------------------------------------------------------------ */

export function fetchEmbedding(
  query: string,
  bridgeBase: string | undefined,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  if (!bridgeBase) {
    fetchEmbeddingDB(query, showCb, hideCb);
    return;
  }
  const signal = cancelPrev();
  fetch(bridgeBase + '/api/embeddings?q=' + encodeURIComponent(query), { signal })
    .then((r) => r.json())
    .then((data: { loaded?: string[]; skipped?: string[]; embeddings?: string[] }) => {
      const names = data.loaded || data.embeddings || [];
      const embeds: AcItem[] = names.slice(0, MAX_RESULTS).map((name) => ({
        label: name,
        sub: 'Embedding (live)',
        value: name,
      }));
      if (embeds.length) showCb(embeds);
      else fetchEmbeddingDB(query, showCb, hideCb);
    })
    .catch(() => fetchEmbeddingDB(query, showCb, hideCb));
}

function fetchEmbeddingDB(
  query: string,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  const signal = getAbortSignal();
  fetch('/api/suggest/embedding?q=' + encodeURIComponent(query) + '&limit=' + MAX_RESULTS, { signal: signal as AbortSignal })
    .then((r) => r.json())
    .then((data: { suggestions?: string[] }) => {
      const embeds: AcItem[] = (data.suggestions || []).map((name) => ({
        label: name,
        sub: 'Embedding',
        value: name,
      }));
      if (embeds.length) showCb(embeds);
      else hideCb();
    })
    .catch(() => hideCb());
}

/* ------------------------------------------------------------------ */
/* Wildcard search                                                     */
/* ------------------------------------------------------------------ */

export function searchWc(
  query: string,
  showCb: (items: AcItem[]) => void,
  hideCb: () => void,
): void {
  const names = BridgeWildcardCache.getNames();
  const data = BridgeWildcardCache.getData();
  const q = query.toLowerCase();
  // Prefix matches first, then segment matches (directory recursion)
  const prefixHits: AcItem[] = [];
  const segmentHits: AcItem[] = [];
  for (let i = 0; i < names.length; i++) {
    const nl = names[i].toLowerCase();
    const count = data[names[i]] ? data[names[i]].length : 0;
    const item: AcItem = {
      label: '__' + names[i] + '__',
      sub: count + ' entries',
      value: names[i],
    };
    if (q === '' || nl.indexOf(q) === 0) {
      prefixHits.push(item);
    } else {
      // Match after any '/' boundary (e.g. "color" matches "danbooru/color")
      const slashIdx = nl.lastIndexOf('/');
      if (slashIdx >= 0) {
        const seg = nl.substring(slashIdx + 1);
        if (seg.indexOf(q) === 0) {
          segmentHits.push(item);
        }
      }
    }
  }
  const results = prefixHits.concat(segmentHits).slice(0, MAX_RESULTS);
  if (results.length) showCb(results);
  else hideCb();
}
