/**
 * Minimal type declarations for vendor libraries loaded via CDN / static.
 * Expand as needed when converting consuming modules.
 */

/* ---- QRCode (qrcode.min.js) ---- */
declare class QRCode {
  constructor(el: HTMLElement | string, options?: Record<string, unknown>);
  makeCode(text: string): void;
  clear(): void;
}

/* ---- Chart.js (loaded via CDN in stats.html) ---- */
declare const Chart: {
  new (ctx: CanvasRenderingContext2D | HTMLCanvasElement, config: Record<string, unknown>): unknown;
  register(...items: unknown[]): void;
  defaults: Record<string, unknown>;
};

/* ---- jsQR (jsqr.min.js) ---- */
declare function jsQR(
  data: Uint8ClampedArray,
  width: number,
  height: number,
  options?: Record<string, unknown>,
): { data: string } | null;
