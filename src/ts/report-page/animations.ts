/**
 * Report page animations — count-up, stagger reveal.
 */

/**
 * Animate a number counting up from 0 to target over ~1.5s.
 */
export function animateCountUp(elementId: string, target: number): void {
  const el = document.getElementById(elementId);
  if (!el) return;

  if (target === 0) {
    el.textContent = '0';
    return;
  }

  const duration = 1500;
  const start = performance.now();

  function step(now: number): void {
    const elapsed = now - start;
    const progress = Math.min(elapsed / duration, 1);
    // Ease-out cubic
    const eased = 1 - Math.pow(1 - progress, 3);
    const current = Math.round(eased * target);
    el!.textContent = current.toLocaleString();
    if (progress < 1) {
      requestAnimationFrame(step);
    }
  }

  requestAnimationFrame(step);
}

/**
 * Trigger stagger reveal on children that have animation-delay set.
 * This forces reflow to restart CSS animations.
 */
export function staggerReveal(container: HTMLElement): void {
  const items = container.querySelectorAll('.report-rank-item');
  items.forEach((item) => {
    const el = item as HTMLElement;
    el.style.animationPlayState = 'running';
  });
}
