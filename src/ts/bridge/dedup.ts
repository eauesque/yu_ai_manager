/**
 * Bridge Dedup — remove duplicate comma-separated tags from bridge prompt textareas.
 */

export interface DedupAttachConfig {
  getInput: () => string;
  setInput: (v: string) => void;
  toast?: (msg: string) => void;
}

async function runDedup(text: string, keepLast: boolean): Promise<string | null> {
  try {
    const res = await fetch('/api/tags/dedup', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ tags: text, keep: keepLast ? 'last' : 'first' }),
    });
    if (!res.ok) return null;
    const json = await res.json();
    // api_result() flattens the payload onto the top-level response
    // (data stays null); the string/tags/removed fields live at json.*.
    // Python and Rust servers both confirmed to use this shape, but read
    // json.data?.string as a fallback in case a server nests it instead.
    return (json.string ?? json.data?.string ?? null) as string | null;
  } catch {
    return null;
  }
}

function attach(config: DedupAttachConfig): { runFirst: () => void; runLast: () => void } {
  const toast = config.toast ?? (() => {});

  async function run(keepLast: boolean): Promise<void> {
    const text = config.getInput();
    if (!text.trim()) return;
    const result = await runDedup(text, keepLast);
    if (result === null) {
      toast('dedup: error');
      return;
    }
    const before = text.split(',').map((s) => s.trim()).filter(Boolean).length;
    const after = result ? result.split(',').map((s) => s.trim()).filter(Boolean).length : 0;
    const removed = before - after;
    config.setInput(result);
    toast(removed > 0 ? `dedup: ${removed} removed` : 'dedup: no duplicates');
  }

  return {
    runFirst: () => run(false),
    runLast: () => run(true),
  };
}

export const BridgeDedup = { runDedup, attach };
