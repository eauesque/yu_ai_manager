/**
 * Stats chart panels — time periods, personality, turning points.
 * Converted from static/js/stats/charts/render/panels.js
 */

/** A time-period bucket returned by the stats API. */
export interface TimePeriod {
  label_key: string;
  /** @deprecated legacy field — use label_key instead */
  label?: string;
  percentage: number;
  count: number;
}

/** Personality profile from hourly analysis (i18n key-based). */
export interface Personality {
  type_key: string;
  /** @deprecated legacy field — use type_key instead */
  type?: string;
  /** @deprecated legacy field — use type_key instead */
  description?: string;
  /** @deprecated legacy field — use type_key instead */
  advice?: string;
}

/** A resolution turning-point event. */
export interface TurningPoint {
  month: string;
  message: string;
}

const PERIOD_ORDER: string[] = ['evening', 'night', 'day', 'dawn'];

export function displayTimePeriods(periods: Record<string, TimePeriod>): void {
  const container = document.getElementById('timePeriods');
  if (!container) return;

  /** Translate with fallback — tr() returns the key path when no translation exists. */
  const t = (path: string, fallback: string): string => {
    if (typeof window.tr !== 'function') return fallback;
    const v = window.tr(path);
    return (v && v !== path) ? v : fallback;
  };

  container.replaceChildren(
    ...PERIOD_ORDER.flatMap((key) => {
      const period = periods[key];
      if (!period) return [];
      const label = period.label_key ? t(period.label_key, period.label || key) : (period.label || key);

      const labelLeft = document.createElement('span');
      labelLeft.textContent = label;

      const strong = document.createElement('strong');
      strong.textContent = `${period.percentage}%`;

      const labelRight = document.createElement('span');
      labelRight.appendChild(strong);
      labelRight.appendChild(document.createTextNode(` (${period.count.toLocaleString()})`));

      const labelRow = document.createElement('div');
      labelRow.className = 'period-label';
      labelRow.appendChild(labelLeft);
      labelRow.appendChild(labelRight);

      const fill = document.createElement('div');
      fill.className = 'period-fill';
      fill.style.width = `${period.percentage}%`;

      const bar = document.createElement('div');
      bar.className = 'period-bar';
      bar.appendChild(fill);

      const item = document.createElement('div');
      item.className = 'period-item';
      item.appendChild(labelRow);
      item.appendChild(bar);
      return [item];
    })
  );
}

export function displayPersonality(personality: Personality): void {
  const card = document.getElementById('personalityCard');
  if (card) card.style.display = 'block';

  const key = personality.type_key || 'unknown';
  const prefix = `stats.personality.${key}`;

  /** Translate with fallback — tr() returns the key path when no translation exists. */
  const t = (path: string, fallback: string): string => {
    if (typeof window.tr !== 'function') return fallback;
    const v = window.tr(path);
    return (v && v !== path) ? v : fallback;
  };

  const typeText = t(`${prefix}.type`, personality.type || key);
  const descText = t(`${prefix}.description`, personality.description || '');
  const adviceText = t(`${prefix}.advice`, personality.advice || '');

  const typeEl = document.getElementById('personalityType');
  if (typeEl) typeEl.textContent = typeText;
  const descEl = document.getElementById('personalityDesc');
  if (descEl) descEl.textContent = descText;
  const adviceEl = document.getElementById('personalityAdvice');
  if (adviceEl) adviceEl.textContent = adviceText;
}

export function displayTurningPoints(points: TurningPoint[] | null | undefined): void {
  const container = document.getElementById('turningPoints');
  if (!container) return;

  container.replaceChildren();
  if (!points || !points.length) return;

  const trFn = typeof window.tr === 'function' ? window.tr : null;
  const heading = (trFn ? trFn('stats.turning_points') : '') || 'Turning Points (Resolution Changes)';
  const hint = (trFn ? trFn('stats.new_gpu_hint') : '') || 'New GPU perhaps?';

  const h3 = document.createElement('h3');
  h3.textContent = '\uD83C\uDFAF ' + heading;
  container.appendChild(h3);

  for (const p of points) {
    const strong = document.createElement('strong');
    strong.textContent = p.month;

    const small = document.createElement('small');
    small.textContent = hint;

    const div = document.createElement('div');
    div.className = 'turning-point';
    div.appendChild(strong);
    div.appendChild(document.createTextNode(': ' + p.message));
    div.appendChild(document.createElement('br'));
    div.appendChild(small);
    container.appendChild(div);
  }
}
