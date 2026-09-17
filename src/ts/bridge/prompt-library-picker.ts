/**
 * prompt-library-picker.ts -- Picker modal for Prompt Library.
 * Contains the UI for browsing prompts and shared types/utilities.
 *
 * Save modal is in prompt-library-save.ts.
 */

export interface CharacterEntry {
  prompt: string;
  negative?: string;
  center?: { x: number; y: number };
}

export interface PromptItem {
  positive?: string;
  negative?: string;
  [key: string]: unknown;
}

interface PickerOpts {
  onSelect: (item: PromptItem) => void;
}

export interface SaveModalOpts {
  positive?: string;
  negative?: string;
  params?: Record<string, string>;
  characters?: CharacterEntry[];
  syntaxMode?: string;
}

const PL_API = '/ext/prompt-library/api/prompts';
const PER_PAGE = 20;

export function escHtml(s: string): string {
  const d = document.createElement('div');
  d.appendChild(document.createTextNode(s));
  return d.innerHTML;
}

export function showToast(msg: string, isError?: boolean): void {
  const prev = document.querySelector('.bpl-toast');
  if (prev) prev.remove();
  const el = document.createElement('div');
  el.className = 'bpl-toast' + (isError ? ' bpl-toast-error' : '');
  el.textContent = msg;
  document.body.appendChild(el);
  setTimeout(() => {
    if (el.parentNode) el.remove();
  }, 3000);
}

export function openPicker(opts: PickerOpts): void {
  const overlay = document.createElement('div');
  overlay.className = 'bpl-overlay';

  const modal = document.createElement('div');
  modal.className = 'bpl-modal';
  modal.innerHTML =
    '<div class="bpl-modal-header">' +
    '<h3>Prompt Library</h3>' +
    '<button class="bpl-close">&times;</button>' +
    '</div>' +
    '<div class="bpl-search-wrap">' +
    '<input class="bpl-search" type="text" placeholder="&#x691C;&#x7D22;...">' +
    '</div>' +
    '<div class="bpl-list"></div>' +
    '<div class="bpl-pager"></div>';

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  const searchInput = modal.querySelector('.bpl-search') as HTMLInputElement;
  const listEl = modal.querySelector('.bpl-list') as HTMLElement;
  const pagerEl = modal.querySelector('.bpl-pager') as HTMLElement;
  let currentOffset = 0;

  function close(): void {
    overlay.remove();
  }

  (modal.querySelector('.bpl-close') as HTMLElement).onclick = close;
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  function onEsc(e: KeyboardEvent): void {
    if (e.key === 'Escape') {
      close();
      document.removeEventListener('keydown', onEsc);
    }
  }
  document.addEventListener('keydown', onEsc);

  function load(offset: number): void {
    currentOffset = Math.max(offset || 0, 0);
    const q = searchInput.value.trim();
    let url = PL_API + '?limit=' + PER_PAGE + '&offset=' + currentOffset;
    if (q) url += '&q=' + encodeURIComponent(q);

    listEl.innerHTML = '<div class="bpl-loading">\u8AAD\u307F\u8FBC\u307F\u4E2D...</div>';

    fetch(url)
      .then((r) => r.json())
      .then(
        (resp: {
          items?: Array<{
            id: number;
            title?: string;
            positive?: string;
            steps?: number;
            sampler?: string;
            cfg_scale?: number;
          }>;
          total?: number;
        }) => {
          const items = resp.items || [];
          const total = resp.total || 0;

          if (!items.length) {
            listEl.innerHTML =
              '<div class="bpl-empty">\u30D7\u30ED\u30F3\u30D7\u30C8\u304C\u898B\u3064\u304B\u308A\u307E\u305B\u3093</div>';
            pagerEl.innerHTML = '';
            return;
          }

          let html = '';
          items.forEach((item) => {
            let preview = (item.positive || '').substring(0, 120);
            if ((item.positive || '').length > 120) preview += '...';
            const params: string[] = [];
            if (item.steps) params.push('Steps: ' + item.steps);
            if (item.sampler) params.push(item.sampler);
            if (item.cfg_scale) params.push('CFG: ' + item.cfg_scale);

            html +=
              '<div class="bpl-card" data-id="' +
              item.id +
              '">' +
              '<div class="bpl-card-title">' +
              escHtml(item.title || 'Untitled') +
              '</div>' +
              '<div class="bpl-card-preview">' +
              escHtml(preview) +
              '</div>' +
              (params.length
                ? '<div class="bpl-card-params">' + escHtml(params.join(' / ')) + '</div>'
                : '') +
              '</div>';
          });
          listEl.innerHTML = html;

          listEl.querySelectorAll<HTMLElement>('.bpl-card').forEach((card) => {
            card.addEventListener('click', () => {
              const id = card.getAttribute('data-id');
              fetch(PL_API + '/' + id)
                .then((r) => r.json())
                .then((resp2: { prompt?: PromptItem }) => {
                  if (resp2.prompt) {
                    opts.onSelect(resp2.prompt);
                    close();
                  }
                });
            });
          });

          let ph = '';
          if (currentOffset > 0) {
            ph += '<button class="bpl-pager-btn" data-dir="prev">&larr; \u524D\u3078</button>';
          }
          if (currentOffset + PER_PAGE < total) {
            ph += '<button class="bpl-pager-btn" data-dir="next">\u6B21\u3078 &rarr;</button>';
          }
          pagerEl.innerHTML = ph;
          pagerEl.querySelectorAll<HTMLElement>('.bpl-pager-btn').forEach((btn) => {
            btn.addEventListener('click', () => {
              if (btn.getAttribute('data-dir') === 'prev') load(currentOffset - PER_PAGE);
              else load(currentOffset + PER_PAGE);
            });
          });
        },
      )
      .catch(() => {
        listEl.innerHTML =
          '<div class="bpl-empty">\u8AAD\u307F\u8FBC\u307F\u306B\u5931\u6557\u3057\u307E\u3057\u305F</div>';
        pagerEl.innerHTML = '';
      });
  }

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  searchInput.addEventListener('input', () => {
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(() => load(0), 300);
  });

  searchInput.focus();
  load(0);
}

// Re-export openSaveModal for backward compatibility
export { openSaveModal } from './prompt-library-save';
