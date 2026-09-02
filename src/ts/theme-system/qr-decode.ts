/**
 * QR decode utilities and image-to-ImageData helpers.
 */

// ---------------------------------------------------------------------------
// jsQR is bundled from the locked package dependency.
// ---------------------------------------------------------------------------

import jsQR from 'jsqr';

export async function ensureJsQR(): Promise<void> {}

// ---------------------------------------------------------------------------
// Decode helpers
// ---------------------------------------------------------------------------

export function decodeImageData(imageData: ImageData): string | null {
  const code = jsQR(imageData.data, imageData.width, imageData.height);
  return code?.data ?? null;
}

export function imageToCanvas(
  img: HTMLImageElement | HTMLVideoElement | HTMLCanvasElement,
  sx?: number, sy?: number, sw?: number, sh?: number,
): ImageData | null {
  const canvas = document.createElement('canvas');
  const w = sw ?? (img instanceof HTMLVideoElement ? img.videoWidth : img.width);
  const h = sh ?? (img instanceof HTMLVideoElement ? img.videoHeight : img.height);
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext('2d');
  if (!ctx) return null;
  if (sx !== undefined && sy !== undefined && sw !== undefined && sh !== undefined) {
    ctx.drawImage(img, sx, sy, sw, sh, 0, 0, sw, sh);
  } else {
    ctx.drawImage(img, 0, 0);
  }
  return ctx.getImageData(0, 0, w, h);
}

// ---------------------------------------------------------------------------
// HTML escape
// ---------------------------------------------------------------------------

export function escapeHtml(s: string): string {
  const d = document.createElement('div');
  d.textContent = s;
  return d.innerHTML;
}
