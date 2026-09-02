import type { SearchPagerState } from './pagination-state';

/**
 * Place the sentinel outside #results (at the sibling #loadMoreSentinelAnchor position).
 * This prevents the sentinel from being destroyed when VirtualGrid's renderCards()
 * clears #results via container clearing.
 *
 * Idle by default — the sentinel is an invisible marker that only exists so the
 * IntersectionObserver can trigger loadMore when the user scrolls near the
 * bottom. The spinner + "読み込み中..." label is only revealed while a load is
 * actually in flight (see setSentinelLoading), which the load-more handler
 * toggles on/off. Without this gating, has_more=true keeps the spinner running
 * forever and looks like the search never finished.
 */
export function showLoadMoreSentinel(): void {
  const anchor = document.getElementById('loadMoreSentinelAnchor');
  if (!anchor) return;
  const old = document.getElementById('loadMoreSentinel');
  if (old) old.remove();

  const sentinel = document.createElement('div');
  sentinel.id = 'loadMoreSentinel';
  sentinel.style.cssText = 'text-align:center;padding:20px;color:#888;font-size:13px;min-height:1px;';

  const spinner = document.createElement('span');
  spinner.className = 'load-more-spinner';
  spinner.style.cssText = 'display:none;width:18px;height:18px;border:2px solid rgba(255,255,255,0.15);border-top-color:#667eea;border-radius:50%;animation:spin 0.8s linear infinite;vertical-align:middle;margin-right:8px;';

  const label = document.createElement('span');
  label.className = 'load-more-label';
  label.style.display = 'none';
  label.textContent = window.tr('search.loading_more');

  sentinel.appendChild(spinner);
  sentinel.appendChild(label);
  anchor.replaceChildren(sentinel);
}

/**
 * Toggle the visible "読み込み中..." spinner on the existing sentinel without
 * recreating it. Called by the load-more handler at fetch start / completion
 * so the spinner only animates while a load is actually in flight.
 */
export function setSentinelLoading(active: boolean): void {
  const sentinel = document.getElementById('loadMoreSentinel');
  if (!sentinel) return;
  const spinner = sentinel.querySelector<HTMLElement>('.load-more-spinner');
  const label = sentinel.querySelector<HTMLElement>('.load-more-label');
  if (spinner) spinner.style.display = active ? 'inline-block' : 'none';
  if (label) label.style.display = active ? 'inline' : 'none';
}

export function setupScrollObserver(
  currentObserver: IntersectionObserver | null,
  state: SearchPagerState,
  onLoadMore: () => void,
): IntersectionObserver {
  if (currentObserver) {
    currentObserver.disconnect();
  }

  const observer = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting && state.getHasMore() && !state.isLoading()) {
          onLoadMore();
        }
      }
    },
    { rootMargin: '800px' },
  );

  requestAnimationFrame(() => {
    const sentinel = document.getElementById('loadMoreSentinel');
    if (sentinel) observer.observe(sentinel);
  });

  return observer;
}

export function removeLoadMoreSentinel(): void {
  const anchor = document.getElementById('loadMoreSentinelAnchor');
  if (anchor) anchor.replaceChildren();
}

export function observeCurrentSentinel(observer: IntersectionObserver | null): void {
  requestAnimationFrame(() => {
    const sentinel = document.getElementById('loadMoreSentinel');
    if (sentinel && observer) observer.observe(sentinel);
  });
}
