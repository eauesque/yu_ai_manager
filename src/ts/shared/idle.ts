export function scheduleVisibleIdle(
  loader: () => Promise<unknown>,
  timeout = 2500,
  fallbackMs = 1200,
): void {
  let fired = false;
  const run = (): void => {
    if (document.hidden) {
      document.addEventListener('visibilitychange', run, { once: true });
      return;
    }
    if (fired) return;
    fired = true;
    void loader().catch(() => {});
  };

  const schedule = (): void => {
    if ('requestIdleCallback' in window) {
      window.requestIdleCallback(run, { timeout });
    } else {
      setTimeout(run, fallbackMs);
    }
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', schedule, { once: true });
    return;
  }

  schedule();
}

export function scheduleDelayedVisibleIdle(
  loader: () => Promise<unknown>,
  delayMs = 3500,
  timeout = 5000,
  fallbackMs = 1400,
): void {
  const arm = (): void => {
    setTimeout(() => scheduleVisibleIdle(loader, timeout, fallbackMs), delayMs);
  };

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', arm, { once: true });
    return;
  }

  arm();
}
