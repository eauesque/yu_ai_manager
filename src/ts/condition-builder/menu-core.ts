import { CONDITIONS } from './config';
import * as state from './state';
import { addCondition } from './condition-actions';
import { getMode } from '../search-results/results/grouping-utils';
import { safeViewTransition } from '../shared/view-transition';
import { getServerPlatform } from '../shared/runtime-state/server-info-state';
import { getAppApi } from '../shared/browser-apis';

let lastConditionTriggerEl: HTMLElement | null = null;

function esc(value: unknown): string {
  return getAppApi().escapeHtml(value);
}

export function announceA11yStatus(text: string): void {
  const el = document.getElementById('a11yStatus');
  if (!el) return;
  el.textContent = '';
  requestAnimationFrame(() => {
    el.textContent = text;
  });
}

export function getConditionMenuButtons(): HTMLButtonElement[] {
  const items = document.getElementById('conditionMenuItems');
  if (!items) return [];
  return Array.from(items.querySelectorAll<HTMLButtonElement>('button:not([disabled])'));
}

export function closeConditionMenu(opts: { restoreFocus?: boolean } = {}): void {
  const menu = document.getElementById('conditionMenu');
  const trigger = document.getElementById('addConditionBtn');
  if (!menu) return;
  const doClose = () => {
    menu.style.display = 'none';
    menu.setAttribute('aria-hidden', 'true');
    if (trigger) trigger.setAttribute('aria-expanded', 'false');
  };
  safeViewTransition(doClose);
  if (opts.restoreFocus !== false && lastConditionTriggerEl && typeof lastConditionTriggerEl.focus === 'function') {
    lastConditionTriggerEl.focus();
  }
}

const GROUPED_MODE_ALLOWED: Record<string, boolean> = { period: true, sort: true, inFolder: true, orTags: true };

function isTagCaseAllowedInGrouped(): boolean {
  const platform = getServerPlatform();
  return !!platform && platform !== 'Windows';
}

export function renderConditionMenu(): void {
  const container = document.getElementById('conditionMenuItems');
  if (!container) return;
  const groupMode = getMode();
  const isGrouped = groupMode === 'folder' || groupMode === 'zip';
  let html = '';
  for (const [key, cond] of Object.entries(CONDITIONS)) {
    const active = state.hasCondition(key);
    let modeDisabled = false;
    if (isGrouped) {
      if (key === 'tagCase') {
        modeDisabled = !isTagCaseAllowedInGrouped();
      } else {
        modeDisabled = !GROUPED_MODE_ALLOWED[key];
      }
    }
    const isDisabled = active || modeDisabled;
    let style: string;
    if (modeDisabled) {
      style = 'background:rgba(255,255,255,0.03);border-color:rgba(255,255,255,0.08);opacity:0.35;cursor:not-allowed;';
    } else if (active) {
      style = 'background:rgba(102,126,234,0.3);border-color:rgba(102,126,234,0.6);opacity:0.5;';
    } else {
      style = 'background:rgba(255,255,255,0.08);border-color:rgba(255,255,255,0.15);cursor:pointer;';
    }
    let tooltipTitle: string;
    if (modeDisabled) {
      tooltipTitle = window.tr('conditions.disabled_in_grouped', 'Not available in folder/ZIP view') as string;
    } else if (cond.descKey) {
      tooltipTitle = window.tr(cond.descKey, '') as string;
    } else {
      tooltipTitle = '';
    }
    const tooltip = tooltipTitle ? ` title="${esc(tooltipTitle)}"` : '';
    html += `<button type="button" role="menuitem" data-cond-key="${key}" ${isDisabled ? 'disabled' : ''}${tooltip}
      style="padding:5px 12px;border-radius:14px;border:1px solid;font-size:12px;color:inherit;${style}">${esc(state.conditionLabel(cond))}</button>`;
  }
  container.innerHTML = html;
  container.querySelectorAll<HTMLButtonElement>('[data-cond-key]').forEach((btn) => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.condKey;
      if (!key || btn.disabled) return;
      addCondition(key);
    });
  });
}

export function openConditionMenu(opts: { focusFirst?: boolean } = {}): void {
  const menu = document.getElementById('conditionMenu');
  const trigger = document.getElementById('addConditionBtn');
  if (!menu) return;
  renderConditionMenu();
  const doOpen = () => {
    menu.style.display = '';
    menu.setAttribute('aria-hidden', 'false');
    if (trigger) trigger.setAttribute('aria-expanded', 'true');
    if (opts.focusFirst) {
      const first = getConditionMenuButtons()[0];
      if (first) first.focus();
    }
  };
  safeViewTransition(doOpen);
  announceA11yStatus(window.tr('a11y.condition_menu_opened'));
}

export function toggleConditionMenu(): void {
  const menu = document.getElementById('conditionMenu');
  lastConditionTriggerEl = document.activeElement as HTMLElement;
  if (menu?.style.display === 'none') {
    openConditionMenu({ focusFirst: true });
  } else {
    closeConditionMenu({ restoreFocus: true });
  }
}

export function setLastConditionTriggerEl(el: HTMLElement | null): void {
  lastConditionTriggerEl = el;
}
