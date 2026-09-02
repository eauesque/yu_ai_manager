export type RenderSectionState = Set<string>;

export function runSectionOnce(state: RenderSectionState, key: string, fn: () => void): void {
  if (state.has(key)) return;
  state.add(key);
  fn();
}

export function observeSectionOnce(
  target: Element | null,
  state: RenderSectionState,
  key: string,
  fn: () => void,
): void {
  if (!target || state.has(key)) return;
  if (typeof IntersectionObserver !== 'function') {
    runSectionOnce(state, key, fn);
    return;
  }
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.disconnect();
      runSectionOnce(state, key, fn);
      break;
    }
  }, {
    rootMargin: '250px 0px',
    threshold: 0.01,
  });
  observer.observe(target);
}
