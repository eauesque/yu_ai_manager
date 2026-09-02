/** Main thread Worker client (Promise wrapper) */

import type { FilterItem, WorkerResponse } from './worker-protocol';

const SYNC_THRESHOLD = 50;

let _worker: Worker | null = null;
let _seq = 0;
let _failed = false;
const _pending = new Map<number, { resolve: (v: FilterItem[]) => void; reject: (e: Error) => void }>();

function getWorker(): Worker | null {
  if (_failed) return null;
  if (_worker) return _worker;
  try {
    _worker = new Worker('/static/dist/workers/search-worker.js');
    _worker.onmessage = (e: MessageEvent<WorkerResponse>) => {
      const resp = e.data;
      const p = _pending.get(resp.id);
      if (!p) return;
      _pending.delete(resp.id);
      if (resp.type === 'error') {
        p.reject(new Error(resp.message));
      } else {
        p.resolve(resp.filtered);
      }
    };
    _worker.onerror = () => {
      _failed = true;
      _worker = null;
      for (const p of _pending.values()) {
        p.reject(new Error('worker crashed'));
      }
      _pending.clear();
    };
    return _worker;
  } catch {
    _failed = true;
    return null;
  }
}

/**
 * Execute regex filter asynchronously.
 * Falls back to synchronous execution for small datasets or when Worker is unavailable.
 */
export function regexFilterAsync(
  items: FilterItem[],
  regex: RegExp,
  syncFallback: (items: FilterItem[], re: RegExp) => FilterItem[],
): Promise<FilterItem[]> {
  if (items.length < SYNC_THRESHOLD) {
    return Promise.resolve(syncFallback(items, regex));
  }

  const w = getWorker();
  if (!w) {
    return Promise.resolve(syncFallback(items, regex));
  }

  const id = ++_seq;
  return new Promise<FilterItem[]>((resolve, reject) => {
    _pending.set(id, { resolve, reject });
    w.postMessage({
      type: 'regex-filter',
      id,
      items,
      pattern: regex.source,
      flags: regex.flags,
    });
  }).catch(() => syncFallback(items, regex));
}
