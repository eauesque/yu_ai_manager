import type { SweepFilesEntry } from './sweep-view-types';

export function formatAxisValue(v: unknown, axisLetter?: 'x' | 'y' | 'z'): string {
  if (v == null) return '?';
  if (typeof v === 'object' && !Array.isArray(v)) {
    const parts: string[] = [];
    const prefix = (axisLetter === 'y' || axisLetter === 'z') ? axisLetter : '';
    for (const [k, val] of Object.entries(v as Record<string, unknown>)) {
      parts.push(`$${prefix}${k}=${val}`);
    }
    return parts.join(', ');
  }
  return String(v);
}

export function axisCaption(m: SweepFilesEntry): string {
  const parts: string[] = [];
  if (m.axis_0_value !== undefined) parts.push(formatAxisValue(m.axis_0_value, 'x'));
  if (m.axis_1_value !== undefined) parts.push(formatAxisValue(m.axis_1_value, 'y'));
  if (m.axis_2_value !== undefined) parts.push(formatAxisValue(m.axis_2_value, 'z'));
  return parts.length ? parts.join('  /  ') : m.path;
}

export function truncate(s: string, max: number): string {
  return s.length <= max ? s : s.slice(0, max) + '…';
}
