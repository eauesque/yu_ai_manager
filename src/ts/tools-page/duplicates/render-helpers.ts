import { getAppApi } from '../../shared/browser-apis';

const SVG_NS = 'http://www.w3.org/2000/svg';
const XLINK_NS = 'http://www.w3.org/1999/xlink';
const SPRITE_URL = '/static/img/icons/icons.svg';

let thumbObserver: IntersectionObserver | null = null;

export function t(key: string, fallback: string): string {
  return getAppApi().tr(key, fallback);
}

export function getThumbObserver(): IntersectionObserver {
  if (thumbObserver) return thumbObserver;
  thumbObserver = new IntersectionObserver(
    (entries, obs) => {
      for (const entry of entries) {
        if (!entry.isIntersecting) continue;
        const img = entry.target as HTMLImageElement;
        const id = img.dataset.thumbId;
        if (id && !img.src) img.src = `/api/thumbnail/${id}`;
        obs.unobserve(img);
      }
    },
    { rootMargin: '200px 0px' },
  );
  return thumbObserver;
}

export function onThumbError(ev: Event): void {
  (ev.target as HTMLImageElement).classList.add('thumb-broken');
}

type IdleCb = (deadline: { didTimeout: boolean; timeRemaining: () => number }) => void;
type WindowWithIdle = Window & {
  requestIdleCallback?: (cb: IdleCb, opts?: { timeout: number }) => number;
};

export function scheduleIdle(cb: () => void): void {
  const w = window as WindowWithIdle;
  if (typeof w.requestIdleCallback === 'function') {
    w.requestIdleCallback(() => cb(), { timeout: 200 });
  } else {
    setTimeout(cb, 0);
  }
}

export function buildIcon(name: string): SVGElement {
  const svg = document.createElementNS(SVG_NS, 'svg');
  svg.setAttribute('class', 'icon');
  svg.setAttribute('aria-hidden', 'true');
  const use = document.createElementNS(SVG_NS, 'use');
  use.setAttributeNS(XLINK_NS, 'xlink:href', `${SPRITE_URL}#icon-${name}`);
  use.setAttribute('href', `${SPRITE_URL}#icon-${name}`);
  svg.append(use);
  return svg;
}
