/**
 * ratings/rating-widget.ts — Star rating widget HTML generation and interaction.
 */

import { getRatingsApi } from '../shared/browser-apis';

/** Create a 5-star rating widget HTML string (inline, small for cards). */
export function buildCardRatingHtml(fileId: number, rating: number): string {
  if (rating <= 0) return '';
  let html = '<span class="card-rating" data-file-id="' + fileId + '">';
  for (let i = 1; i <= 5; i++) {
    html += '<span class="rating-star' + (i <= rating ? ' active' : '') + '">\u2605</span>';
  }
  html += '</span>';
  return html;
}

/** Create an interactive 5-star rating widget for the detail modal. */
export function createModalRatingWidget(fileId: number, rating: number): HTMLElement {
  const wrap = document.createElement('span');
  wrap.className = 'modal-rating-widget';
  wrap.dataset.fileId = String(fileId);

  for (let i = 1; i <= 5; i++) {
    const star = document.createElement('span');
    star.className = 'rating-star interactive' + (i <= rating ? ' active' : '');
    star.dataset.value = String(i);
    star.textContent = '\u2605';
    star.title = i + ' / 5';

    star.addEventListener('mouseenter', () => {
      _previewHover(wrap, i);
    });

    star.addEventListener('click', (e: MouseEvent) => {
      e.stopPropagation();
      const current = parseInt(wrap.dataset.currentRating || '0', 10);
      // Click same star = clear rating
      const newRating = current === i ? 0 : i;
      void getRatingsApi().setRating(fileId, newRating);
    });

    wrap.appendChild(star);
  }

  wrap.addEventListener('mouseleave', () => {
    const current = parseInt(wrap.dataset.currentRating || '0', 10);
    _setStars(wrap, current);
  });

  wrap.dataset.currentRating = String(rating);
  return wrap;
}

/** Update an existing modal widget to reflect a new rating. */
export function updateModalRatingWidget(fileId: number, rating: number): void {
  const widget = document.querySelector<HTMLElement>(
    '.modal-rating-widget[data-file-id="' + fileId + '"]'
  );
  if (!widget) return;
  widget.dataset.currentRating = String(rating);
  _setStars(widget, rating);
}

function _previewHover(wrap: HTMLElement, hoverValue: number): void {
  const stars = wrap.querySelectorAll<HTMLElement>('.rating-star');
  stars.forEach((star, idx) => {
    star.classList.toggle('active', idx < hoverValue);
  });
}

function _setStars(wrap: HTMLElement, rating: number): void {
  const stars = wrap.querySelectorAll<HTMLElement>('.rating-star');
  stars.forEach((star, idx) => {
    star.classList.toggle('active', idx < rating);
  });
}
