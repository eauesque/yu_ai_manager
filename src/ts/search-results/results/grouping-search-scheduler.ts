export function scheduleAfterPaint(task: () => void): void {
  requestAnimationFrame(() => {
    requestAnimationFrame(task);
  });
}

export function scheduleIdle(task: () => void, timeout = 120): void {
  if ('requestIdleCallback' in window) {
    window.requestIdleCallback(task, { timeout });
    return;
  }
  setTimeout(task, 16);
}

export function isPerfEnabled(): boolean {
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get('perf') === '1') return true;
    return localStorage.getItem('yu_page_perf') === '1';
  } catch {
    return false;
  }
}
