/**
 * LAN Share guest page — countdown timer.
 *
 * Reads `data-remaining` from #lsTimer and counts down every second.
 * When time runs out, replaces the page content with an expiry message.
 */

function initCountdown(): void {
  const timer = document.getElementById('lsTimer') as HTMLElement | null;
  if (!timer) return;

  let remaining = parseInt(timer.dataset.remaining ?? '0', 10);
  if (remaining <= 0) return;

  function format(sec: number): string {
    const m = Math.floor(sec / 60);
    const s = sec % 60;
    return `${m}:${s.toString().padStart(2, '0')} remaining`;
  }

  function tick(): void {
    if (!timer) return;
    remaining--;
    if (remaining <= 0) {
      // Replace page with expiry message
      document.body.innerHTML =
        '<div class="ls-expired">' +
        '<div class="ls-expired-icon">&#x23F0;</div>' +
        '<h1>Share Expired</h1>' +
        '<p>This shared link has expired. Please ask the host to create a new share.</p>' +
        '</div>';
      return;
    }
    timer.textContent = format(remaining);
    if (remaining < 120) {
      timer.classList.add('ls-urgent');
    }
    setTimeout(tick, 1000);
  }

  timer.textContent = format(remaining);
  setTimeout(tick, 1000);
}

document.addEventListener('DOMContentLoaded', initCountdown);
