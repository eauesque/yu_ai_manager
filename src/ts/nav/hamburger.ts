/**
 * nav/hamburger — Hamburger menu open/close/outside-click.
 *
 * Toggles the `.open` class on #navLinks and updates the hamburger
 * button icon and aria-expanded state. Closes on link click or
 * outside click.
 */

import { safeViewTransition } from '../shared/view-transition';
import { icon, setIconSymbol } from '../shared/icon';

function setHamburgerIcon(el: HTMLElement, symbol: 'menu' | 'x'): void {
  const svgEl = el.querySelector('svg.icon') as SVGSVGElement | null;
  if (svgEl) {
    setIconSymbol(svgEl, symbol);
  } else {
    // Initial paint: replace the legacy textContent glyph with an SVG.
    el.replaceChildren();
    el.insertAdjacentHTML('beforeend', icon(symbol));
  }
}

/** Initialize hamburger menu toggle and auto-close behaviors. */
export function initHamburger(): void {
  const hamburger = document.getElementById('navHamburger');
  const navLinks = document.getElementById('navLinks');
  if (!hamburger || !navLinks) return;

  // Initial render — replace any pre-existing textContent glyph with an SVG.
  setHamburgerIcon(hamburger, 'menu');

  /** Close the hamburger menu and reset the button state. */
  const closeMenu = (): void => {
    navLinks.classList.remove('open');
    hamburger.setAttribute('aria-expanded', 'false');
    setHamburgerIcon(hamburger, 'menu');
  };

  // Toggle on hamburger click
  hamburger.addEventListener('click', () => {
    const doToggle = () => {
      const isOpen = navLinks.classList.toggle('open');
      hamburger.setAttribute('aria-expanded', isOpen ? 'true' : 'false');
      setHamburgerIcon(hamburger, isOpen ? 'x' : 'menu');
    };
    safeViewTransition(doToggle);
  });

  // Close when a nav link is clicked
  navLinks.addEventListener('click', (e: Event) => {
    if ((e.target as HTMLElement).closest('.nav-link')) {
      closeMenu();
    }
  });

  // Close on outside click
  document.addEventListener('click', (e: Event) => {
    if (!(e.target as HTMLElement).closest('#fixedNav')) {
      closeMenu();
    }
  });

  // Close on Escape key
  document.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Escape' && navLinks.classList.contains('open')) {
      closeMenu();
      hamburger.focus();
    }
  });
}
