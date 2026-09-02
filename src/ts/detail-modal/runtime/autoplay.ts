let _timer: ReturnType<typeof setTimeout> | null = null;
let _active = false;
let _countdownEl: HTMLDivElement | null = null;
let _remaining = 0;
let _tickInterval: ReturnType<typeof setInterval> | null = null;
import { getDetailModalRuntimeHooks } from './runtime-hooks';

const LS_KEY = 'autoplayEnabled';
const LS_INTERVAL_KEY = 'autoplayInterval';

function getInterval(): number {
  const val = parseInt(localStorage.getItem(LS_INTERVAL_KEY) || '5', 10);
  return (val >= 1 && val <= 60) ? val : 5;
}

export function isActive(): boolean { return _active; }

function updateButton(): void {
  const btn = document.getElementById('btnAutoplay');
  if (!btn) return;
  (btn as HTMLElement).style.background = _active ? 'rgba(100,255,200,0.4)' : 'rgba(255,255,255,0.2)';
  btn.title = _active ? 'Stop auto-play (P)' : 'Auto-play (P)';
}

function clearTimers(): void {
  if (_timer) { clearTimeout(_timer); _timer = null; }
  if (_tickInterval) { clearInterval(_tickInterval); _tickInterval = null; }
}

function showCountdown(text: string): void {
  if (!_countdownEl) {
    _countdownEl = document.createElement('div');
    _countdownEl.className = 'autoplay-badge';
  }
  _countdownEl.textContent = text;
  const container = document.getElementById('modalImageContainer');
  if (container && !_countdownEl.parentNode) container.appendChild(_countdownEl);
}

function hideCountdown(): void {
  if (_countdownEl && _countdownEl.parentNode) _countdownEl.parentNode.removeChild(_countdownEl);
}

function scheduleNext(): void {
  if (!_active) return;
  const modal = document.getElementById('modal');
  if (!modal || !modal.classList.contains('active')) { stop(); return; }
  clearTimers();
  const video = document.getElementById('modalImage');
  if (video && video.tagName === 'VIDEO') { showCountdown('▶ Auto'); return; }
  const audio = document.getElementById('modalAudio');
  if (audio) { showCountdown('▶ Auto'); return; }
  const sec = getInterval();
  _remaining = sec;
  showCountdown(_remaining + 's');
  _tickInterval = setInterval(() => {
    _remaining--;
    if (_remaining <= 0) { clearInterval(_tickInterval!); _tickInterval = null; showCountdown('▶'); }
    else showCountdown(_remaining + 's');
  }, 1000);
  _timer = setTimeout(() => {
    _timer = null;
    if (!_active) return;
    getDetailModalRuntimeHooks().navigateModal(1);
  }, sec * 1000);
}

export function start(): void {
  _active = true;
  localStorage.setItem(LS_KEY, '1');
  updateButton();
  scheduleNext();
}

export function stop(): void {
  _active = false;
  localStorage.setItem(LS_KEY, '0');
  clearTimers();
  hideCountdown();
  updateButton();
}

export function toggle(): void { if (_active) stop(); else start(); }

export function onNavigate(): void {
  if (!_active) return;
  setTimeout(scheduleNext, 200);
}

export function onMediaEnded(): void {
  if (!_active) return;
  const repeatOn = localStorage.getItem('modalRepeatMode') === '1';
  if (repeatOn) return;
  setTimeout(() => {
    if (!_active) return;
    getDetailModalRuntimeHooks().navigateModal(1);
  }, 500);
}

export function onModalClose(): void { if (_active) stop(); }

export function setInterval_val(val: string): void {
  const v = parseInt(val, 10);
  if (v >= 1 && v <= 60) localStorage.setItem(LS_INTERVAL_KEY, String(v));
  const input = document.getElementById('autoplayIntervalInput') as HTMLInputElement | null;
  if (input) input.value = String(getInterval());
}
