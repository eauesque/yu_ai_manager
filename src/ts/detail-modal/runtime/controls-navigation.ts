import { state } from './state';
import { showDetail } from './show-detail-load';
import { getAppApi, getNavApi } from '../../shared/browser-apis';

export function reloadCurrentDetail(): void {
  if (state.currentModalIndex < 0) return;
  const id = state.currentResultIds[state.currentModalIndex];
  if (id != null) {
    showDetail(id, {
      scope: state.viewerScope,
      scopeIds: state.currentResultIds,
    });
  }
}

export function toggleSpreadView(): void {
  const { tr } = getAppApi();
  const enabled = localStorage.getItem('spreadViewEnabled') === '1';
  localStorage.setItem('spreadViewEnabled', enabled ? '0' : '1');
  if (enabled) {
    getNavApi().showToast(tr('detail.modal.toast_spread_off', 'Spread: OFF'));
  } else {
    const rtl = localStorage.getItem('spreadViewRTL') !== '0';
    const dirHint = rtl
      ? tr('detail.modal.toast_spread_nav_rtl', '\u2190 Next / Prev \u2192')
      : '';
    getNavApi().showToast(tr('detail.modal.toast_spread_on', 'Spread: ON') + (dirHint ? '\n' + dirHint : ''));
  }
  reloadCurrentDetail();
}

export function toggleSpreadDirection(): void {
  const { tr } = getAppApi();
  const rtl = localStorage.getItem('spreadViewRTL') !== '0';
  localStorage.setItem('spreadViewRTL', rtl ? '0' : '1');
  if (rtl) {
    getNavApi().showToast(tr('detail.modal.toast_spread_ltr', 'Read: L\u2192R'));
  } else {
    getNavApi().showToast(tr('detail.modal.toast_spread_rtl', 'Read: R\u2192L') + '\n' + tr('detail.modal.toast_spread_nav_rtl', '\u2190 Next / Prev \u2192'));
  }
  reloadCurrentDetail();
}

export function openRandomResult(): void {
  const { tr } = getAppApi();
  if (!Array.isArray(state.currentResultIds) || state.currentResultIds.length === 0) {
    getNavApi().showToast(tr('random.empty'));
    return;
  }
  let idx = Math.floor(Math.random() * state.currentResultIds.length);
  if (state.currentResultIds.length > 1 && state.currentModalIndex >= 0 && idx === state.currentModalIndex) {
    idx = (idx + 1) % state.currentResultIds.length;
  }
  const id = state.currentResultIds[idx];
  if (typeof id === 'number') {
    showDetail(id, {
      scope: state.viewerScope,
      scopeIds: state.currentResultIds,
    });
    getNavApi().showToast(tr('random.opened_one'));
  }
}
