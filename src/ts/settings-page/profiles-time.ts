import { getAppApi } from '../shared/browser-apis';

export function formatRelativeTime(isoStr: string): string {
  try {
    const then = new Date(isoStr).getTime();
    const now = Date.now();
    const diffSec = Math.floor((now - then) / 1000);
    const tr = getAppApi().tr;
    if (diffSec < 60) return tr('settings.profile_just_now', 'just now');
    if (diffSec < 3600) return Math.floor(diffSec / 60) + tr('settings.unit_minutes', 'm') + ' ' + tr('settings.profile_ago', 'ago');
    if (diffSec < 86400) return Math.floor(diffSec / 3600) + tr('settings.unit_hours', 'h') + ' ' + tr('settings.profile_ago', 'ago');
    return Math.floor(diffSec / 86400) + tr('settings.profile_days', 'd') + ' ' + tr('settings.profile_ago', 'ago');
  } catch {
    return isoStr;
  }
}
