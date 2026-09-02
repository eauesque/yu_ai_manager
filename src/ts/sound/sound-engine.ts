/**
 * sound/sound-engine.ts — Sound effects engine.
 *
 * - Lazy AudioContext creation (on first playSound call, for autoplay policy compliance)
 * - Monitors prefers-reduced-motion: reduce and auto-disables
 * - Hover throttle (minimum 50ms interval)
 * - Global event delegation (mouseover on .result-card, click on button)
 * - localStorage: soundEnabled (default '0'=OFF) / soundVolume (default '0.5')
 */

export type SoundType = 'hover' | 'click' | 'favorite' | 'modalOpen' | 'modalClose' | 'navigate';

type SynthModule = typeof import('./synth');

let _ctx: AudioContext | null = null;
let _master: GainNode | null = null;
let _reducedMotion = false;
let _lastHoverTime = 0;
let _listenersBound = false;
let _synthPromise: Promise<SynthModule> | null = null;

function _loadSynth(): Promise<SynthModule> {
  if (!_synthPromise) {
    _synthPromise = import('./synth');
  }
  return _synthPromise;
}

/* ---- localStorage helpers ---- */

export function isSoundEnabled(): boolean {
  return localStorage.getItem('soundEnabled') === '1';
}

export function getSoundVolume(): number {
  const v = parseFloat(localStorage.getItem('soundVolume') || '0.5');
  return Number.isFinite(v) ? Math.max(0, Math.min(1, v)) : 0.5;
}

export function setSoundEnabled(on: boolean): void {
  localStorage.setItem('soundEnabled', on ? '1' : '0');
  if (on) void _loadSynth();
  window.dispatchEvent(new CustomEvent('yu:sound-enabled-changed', { detail: { enabled: on } }));
}

export function setSoundVolume(vol: number): void {
  const clamped = Math.max(0, Math.min(1, vol));
  localStorage.setItem('soundVolume', String(clamped));
  if (_master) _master.gain.setValueAtTime(clamped, _ctx!.currentTime);
}

/* ---- core ---- */

function ensureContext(): boolean {
  if (_reducedMotion) return false;
  if (!isSoundEnabled()) return false;
  if (!_ctx) {
    try {
      _ctx = new AudioContext();
      _master = _ctx.createGain();
      _master.gain.setValueAtTime(getSoundVolume(), _ctx.currentTime);
      _master.connect(_ctx.destination);
    } catch {
      return false;
    }
  }
  if (_ctx.state === 'suspended') {
    _ctx.resume();
  }
  // Apply volume
  _master!.gain.setValueAtTime(getSoundVolume(), _ctx.currentTime);
  return true;
}

export function playSound(type: SoundType): void {
  if (!ensureContext()) return;
  void _loadSynth().then((mod) => {
    const synthMap: Record<SoundType, (ctx: AudioContext, g: GainNode) => void> = {
      hover: mod.synthHover,
      click: mod.synthClick,
      favorite: mod.synthFavorite,
      modalOpen: mod.synthModalOpen,
      modalClose: mod.synthModalClose,
      navigate: mod.synthNavigate,
    };
    const fn = synthMap[type];
    if (fn && _ctx && _master) fn(_ctx, _master);
  }).catch(() => {});
}

/* ---- global delegation ---- */

function onGlobalMouseover(e: Event): void {
  if (!isSoundEnabled()) return;
  const t = e.target as HTMLElement;
  if (!t?.closest?.('.result-card')) return;
  const now = Date.now();
  if (now - _lastHoverTime < 50) return;
  _lastHoverTime = now;
  playSound('hover');
}

function onGlobalClick(e: Event): void {
  if (!isSoundEnabled()) return;
  const t = e.target as HTMLElement;
  if (t?.closest?.('button, .btn-save, .toggle-switch, [role="button"]')) {
    playSound('click');
  }
}

function bindGlobalListeners(): void {
  if (_listenersBound) return;
  _listenersBound = true;
  void _loadSynth();
  document.addEventListener('mouseover', onGlobalMouseover, { passive: true });
  document.addEventListener('click', onGlobalClick, { passive: true });
}

function unbindGlobalListeners(): void {
  if (!_listenersBound) return;
  _listenersBound = false;
  document.removeEventListener('mouseover', onGlobalMouseover);
  document.removeEventListener('click', onGlobalClick);
}

function syncListenerState(): void {
  if (isSoundEnabled() && !_reducedMotion) {
    bindGlobalListeners();
    return;
  }
  unbindGlobalListeners();
}

/* ---- init ---- */

export function initSoundEngine(): void {
  // Monitor prefers-reduced-motion
  const mq = window.matchMedia('(prefers-reduced-motion: reduce)');
  _reducedMotion = mq.matches;
  mq.addEventListener('change', (ev) => {
    _reducedMotion = ev.matches;
    syncListenerState();
  });

  window.addEventListener('storage', (ev: StorageEvent) => {
    if (ev.key === 'soundEnabled') syncListenerState();
  });
  window.addEventListener('yu:sound-enabled-changed', () => {
    syncListenerState();
  });

  syncListenerState();
}
