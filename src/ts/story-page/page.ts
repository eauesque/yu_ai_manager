/**
 * Story page — loads /api/stats/story and renders the event timeline.
 * Converted from static/js/story/page.js
 */

import { createPagePerfTracker } from '../shared/page-perf';
import { loadTrophyDetails, renderMilestoneShelf } from './page-trophies';

/** A single story event from the API. */
export interface StoryEvent {
  type?: string;
  title_key?: string;
  desc_key?: string;
  params?: Record<string, unknown>;
  icon?: string;
  date: string;
}

/** Timeline data keyed by month. */
export type TimelineMap = Record<string, unknown>;

/** "On this day" data from the API. */
interface OnThisDay {
  date: string;
  count: number;
}

/** Shape of /api/stats/story response. */
interface StoryResponse {
  story: StoryEvent[];
  timeline: TimelineMap;
  streak_days?: number;
  on_this_day?: OnThisDay;
}

/** Resolve an i18n key with params, falling back to a literal. */
function _evt(key: string | undefined, params: Record<string, unknown> | undefined, fallback: string): string {
  if (!key) return fallback;
  const trFn = typeof window.tr === 'function' ? window.tr : null;
  if (!trFn) return fallback;
  const result = trFn(key, params || {});
  return (result as string) || fallback;
}

/** Escape HTML special characters to prevent XSS. */
function _escHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#039;');
}

/** Number of timeline events to show per batch. */
const EVENTS_PER_PAGE = 30;

/** State for progressive loading. */
let _allEvents: StoryEvent[] = [];
let _shownCount = 0;

function _defer(task: () => void): void {
  const win = window as Window & { requestIdleCallback?: (cb: () => void, opts?: { timeout: number }) => void };
  if (typeof win.requestIdleCallback === 'function') {
    win.requestIdleCallback(task, { timeout: 1200 });
    return;
  }
  setTimeout(task, 60);
}

const _perf = createPagePerfTracker('story');
_perf.markOnce('module_ready');

/** Render a single event card HTML. */
function _renderEvent(event: StoryEvent, index: number): string {
  const typeClass = _escHtml(event.type || '');
  const title = _escHtml(_evt(event.title_key, event.params, event.type || ''));
  const desc = _escHtml(_evt(event.desc_key, event.params, ''));
  const icon = _escHtml(event.icon || '');
  const date = _escHtml(event.date);
  return '<div class="event ' + typeClass + '" style="animation-delay: ' + (index * 0.05) + 's">'
    + '<div class="event-icon">' + icon + '</div>'
    + '<div class="event-date">' + date + '</div>'
    + '<div class="event-title">' + title + '</div>'
    + '<div class="event-description">' + desc + '</div>'
    + '</div>';
}

/** Show next batch of events in the timeline. */
function _showMoreEvents(): void {
  const container = document.getElementById('timeline');
  if (!container) return;
  const btn = document.getElementById('storyLoadMore');

  const end = Math.min(_shownCount + EVENTS_PER_PAGE, _allEvents.length);
  const fragment = document.createDocumentFragment();
  const wrapper = document.createElement('div');
  wrapper.innerHTML = _allEvents.slice(_shownCount, end)
    .map((e, i) => _renderEvent(e, _shownCount + i))
    .join('');
  while (wrapper.firstChild) fragment.appendChild(wrapper.firstChild);

  // Insert before the "load more" button
  if (btn) {
    container.insertBefore(fragment, btn);
  } else {
    container.appendChild(fragment);
  }
  _shownCount = end;

  // Update or hide button
  if (btn) {
    if (_shownCount >= _allEvents.length) {
      btn.style.display = 'none';
    } else {
      const remaining = _allEvents.length - _shownCount;
      const trFn = typeof window.tr === 'function' ? window.tr : null;
      const label = (trFn ? trFn('story.load_more', { count: remaining }) : '') ||
        ('Show more (' + remaining + ' remaining)');
      btn.textContent = label;
    }
  }
}

function displayStory(events: StoryEvent[], timeline: TimelineMap, data: StoryResponse): void {
  const container = document.getElementById('timeline');
  if (!container) return;

  const months = Object.keys(timeline).length;
  const milestones = events.filter((e) => e.type && e.type.startsWith('milestone')).length;

  const summaryEl = document.getElementById('summary');
  if (summaryEl) summaryEl.style.display = 'block';
  const totalMonthsEl = document.getElementById('totalMonths');
  if (totalMonthsEl) totalMonthsEl.textContent = String(months);
  const totalEventsEl = document.getElementById('totalEvents');
  if (totalEventsEl) totalEventsEl.textContent = String(events.length);
  const totalMilestonesEl = document.getElementById('totalMilestones');
  if (totalMilestonesEl) totalMilestonesEl.textContent = String(milestones);
  _perf.markOnce('summary_ready');

  // Streak days
  const streak = data.streak_days || 0;
  const streakEl = document.getElementById('streakDays');
  if (streakEl) streakEl.textContent = String(streak);

  // On this day
  const otd = data.on_this_day;
  if (otd && otd.count > 0) {
    const card = document.getElementById('onThisDayCard');
    // Format the YYYY-MM-DD ISO date via the user's locale so it reads
    // naturally in JP ("2025年4月29日") / EN ("April 29, 2025") instead of
    // the raw ISO string interpolated into the i18n template.
    const lang = (localStorage.getItem('lang') || navigator.language || 'en').toLowerCase();
    let formatted = otd.date;
    try {
      const d = new Date(otd.date + 'T00:00:00');
      if (!isNaN(d.getTime())) {
        formatted = new Intl.DateTimeFormat(lang, {
          year: 'numeric', month: 'long', day: 'numeric',
        }).format(d);
      }
    } catch {
      // fall back to raw ISO date
    }
    const text = _evt('story.on_this_day', { date: formatted, count: otd.count },
      '1 year ago today (' + formatted + '): ' + otd.count + ' images created');
    const textEl = document.getElementById('onThisDayText');
    if (textEl) textEl.textContent = text;
    if (card) card.style.display = 'block';
  }

  // Progressive timeline: show first batch + "load more" button
  _allEvents = events;
  _shownCount = 0;
  container.innerHTML = '';

  // Create "load more" button (hidden initially, appended to container)
  if (events.length > EVENTS_PER_PAGE) {
    const btn = document.createElement('button');
    btn.id = 'storyLoadMore';
    btn.className = 'story-load-more';
    btn.type = 'button';
    btn.addEventListener('click', _showMoreEvents);
    container.appendChild(btn);
  }

  _defer(() => {
    renderMilestoneShelf(events, typeof window.tr === 'function' ? window.tr : null);
    _showMoreEvents();
    _perf.markOnce('timeline_ready');
  });
}

export async function loadStory(): Promise<void> {
  const trFn = typeof window.tr === 'function' ? window.tr : null;

  // Show today's date context in header
  const dateCtx = document.getElementById('storyDateContext');
  if (dateCtx) {
    const today = new Date();
    const locale = document.documentElement.lang || 'ja';
    const formatted = today.toLocaleDateString(locale, { year: 'numeric', month: 'long', day: 'numeric', weekday: 'long' });
    const label = (trFn ? trFn('story.date_context', { date: formatted }) as string : '') ||
      ('📅 ' + formatted);
    dateCtx.textContent = label;
    dateCtx.style.display = '';
  }

  try {
    const response = await fetch('/api/stats/story');

    // 401 = session expired / boss-lock engaged — redirect to re-authenticate
    if (response.status === 401) {
      window.location.href = '/?next=' + encodeURIComponent(window.location.pathname);
      return;
    }

    if (!response.ok) {
      throw new Error('HTTP ' + response.status);
    }

    const data: StoryResponse = await response.json();

    if (data.story && data.story.length > 0) {
      displayStory(data.story, data.timeline, data);
      const loadingEl = document.getElementById('loading');
      if (loadingEl) loadingEl.style.display = 'none';
      _defer(() => { void loadTrophyDetails(trFn); });
    } else {
      const loadingEl = document.getElementById('loading');
      if (loadingEl) {
        const msg = (trFn ? trFn('story.no_data') : '') || 'Not enough data to create your story yet';
        const p = document.createElement('p');
        p.textContent = msg;
        loadingEl.textContent = '';
        loadingEl.appendChild(p);
      }
    }
  } catch (error) {
    console.error('Failed to load story:', error);
    const loadingEl = document.getElementById('loading');
    if (loadingEl) {
      const msg = (trFn ? trFn('story.load_failed') : '') || 'Failed to load story';
      const p = document.createElement('p');
      p.style.color = '#ff6b6b';
      p.textContent = msg;
      loadingEl.textContent = '';
      loadingEl.appendChild(p);
    }
  }
}

/** Init: wait for tr-runtime to be ready, with timeout fallback. */
export function initStoryPage(): void {
  let loaded = false;
  function go(): void {
    if (loaded) return;
    loaded = true;
    loadStory();
    _perf.markOnce('load_started');
  }
  document.addEventListener('tr-runtime:ready', go);
  // fallback: if tr-runtime doesn't fire within 2s, load anyway
  setTimeout(go, 2000);
}
