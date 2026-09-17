/** Search WebWorker: execute regex filters in the background */

import type { WorkerRequest, RegexFilterRequest, FilterItem } from './worker-protocol';

function handleRegexFilter(req: RegexFilterRequest): FilterItem[] {
  const re = new RegExp(req.pattern, req.flags);
  return req.items.filter((r) => {
    const hay =
      (r.positive || '') + '\n' +
      (r.negative || '') + '\n' +
      (r.artist || '') + '\n' +
      (r.path || '');
    return re.test(hay);
  });
}

self.onmessage = (e: MessageEvent<WorkerRequest>) => {
  const req = e.data;
  try {
    if (req.type === 'regex-filter') {
      const filtered = handleRegexFilter(req);
      self.postMessage({ type: 'regex-filter', id: req.id, filtered });
    }
  } catch (err: unknown) {
    const msg = err instanceof Error ? err.message : 'worker error';
    self.postMessage({ type: 'error', id: req.id, message: msg });
  }
};
