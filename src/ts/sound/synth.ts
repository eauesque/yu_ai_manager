/**
 * sound/synth.ts — Pure functions for programmatic UI sound synthesis via Web Audio API.
 * No external mp3 files needed. Each function receives an AudioContext and masterGain,
 * generates short sounds using OscillatorNode + GainNode, and auto-stops.
 */

type Ctx = AudioContext;
type Gain = GainNode;

/* ---- helpers ---- */

function osc(
  ctx: Ctx, dest: Gain, type: OscillatorType,
  freqStart: number, freqEnd: number,
  startSec: number, durSec: number, vol: number,
): void {
  const o = ctx.createOscillator();
  const g = ctx.createGain();
  o.type = type;
  o.frequency.setValueAtTime(freqStart, ctx.currentTime + startSec);
  if (freqStart !== freqEnd) {
    o.frequency.linearRampToValueAtTime(freqEnd, ctx.currentTime + startSec + durSec);
  }
  g.gain.setValueAtTime(vol, ctx.currentTime + startSec);
  g.gain.linearRampToValueAtTime(0, ctx.currentTime + startSec + durSec);
  o.connect(g).connect(dest);
  o.start(ctx.currentTime + startSec);
  o.stop(ctx.currentTime + startSec + durSec + 0.01);
}

/* ---- sound definitions ---- */

/** Ultra-short, quiet hover beep */
export function synthHover(ctx: Ctx, master: Gain): void {
  osc(ctx, master, 'sine', 2400, 2400, 0, 0.04, 0.15);
}

/** Light tap sound */
export function synthClick(ctx: Ctx, master: Gain): void {
  osc(ctx, master, 'triangle', 800, 600, 0, 0.06, 0.25);
}

/** Sparkle chord (perfect fifth) */
export function synthFavorite(ctx: Ctx, master: Gain): void {
  osc(ctx, master, 'sine', 880, 1320, 0, 0.20, 0.25);
  osc(ctx, master, 'sine', 1320, 1760, 0.05, 0.18, 0.18);
}

/** Modal open — sweep up */
export function synthModalOpen(ctx: Ctx, master: Gain): void {
  osc(ctx, master, 'sine', 440, 660, 0, 0.14, 0.22);
}

/** Modal close — sweep down */
export function synthModalClose(ctx: Ctx, master: Gain): void {
  osc(ctx, master, 'sine', 660, 330, 0, 0.12, 0.20);
}

/** Navigation — light tap sound */
export function synthNavigate(ctx: Ctx, master: Gain): void {
  osc(ctx, master, 'triangle', 1200, 1200, 0, 0.05, 0.20);
}
