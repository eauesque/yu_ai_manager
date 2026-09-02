function releaseMediaElement(el: HTMLElement): void {
  if (!el) return;
  const media = el as HTMLMediaElement;
  try { media.pause?.(); } catch (_) { /* ignore */ }
  try {
    // Remove <source> elements entirely — leaving them with empty src causes
    // browser errors ("source element has no src") when .load() is called.
    const sources = el.querySelectorAll('source');
    sources.forEach((srcEl) => { try { srcEl.remove(); } catch (_) { /* ignore */ } });
    el.removeAttribute('src');
    if (typeof media.load === 'function') media.load();
  } catch (_) { /* ignore */ }
}

export function releaseModalMedia(modal?: HTMLElement | null): void {
  const root = modal || document.getElementById('modal');
  if (!root) return;
  root.querySelectorAll('video, audio').forEach((el) => releaseMediaElement(el as HTMLElement));
  root.querySelectorAll('img').forEach((img) => {
    const src = String(img.getAttribute('src') || '');
    if (src.startsWith('blob:')) { try { URL.revokeObjectURL(src); } catch (_) { /* ignore */ } }
    try { img.removeAttribute('src'); } catch (_) { /* ignore */ }
  });
}
