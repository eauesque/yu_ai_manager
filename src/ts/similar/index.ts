/**
 * similar/index.ts — Similar image finding, panel display in detail modal.
 */

import { safeViewTransition } from '../shared/view-transition';
import { installWindowApi } from '../shared/window-api';
import { getAppApi, getDetailModalApi } from '../shared/browser-apis';

interface SimilarResult {
  id: number;
  path: string;
  distance: number;
  mtime: number;
}

let _activePanel: HTMLElement | null = null;

/** Find similar images for a given file and show results in a panel. */
export async function findSimilarImages(fileId: number): Promise<void> {
  // Remove existing panel
  _closePanel();

  const modal = document.querySelector('.modal-overlay') || document.querySelector('.detail-modal');
  if (!modal) return;

  // Create panel
  const panel = document.createElement('div');
  panel.className = 'similar-panel';
  panel.innerHTML =
    '<div class="similar-panel-header">' +
    '<span class="similar-panel-title">' +
    (window.tr('similar.title', '類似画像') || '類似画像') +
    '</span>' +
    '<button class="similar-panel-close" title="Close">\u2715</button>' +
    '</div>' +
    '<div class="similar-panel-body">' +
    '<div class="similar-loading">' +
    (window.tr('similar.searching', '検索中...') || '検索中...') +
    '</div>' +
    '</div>';

  _activePanel = panel;
  safeViewTransition(() => { modal.appendChild(panel); });

  // Close button
  panel.querySelector('.similar-panel-close')?.addEventListener('click', _closePanel);

  try {
    const response = await getAppApi().apiFetch('/api/tools/find-similar?file_id=' + fileId + '&threshold=8');
    if (!response.ok) throw new Error('API error');
    const data = await response.json();
    const results: SimilarResult[] = data.results || [];
    _renderResults(panel, results, fileId);
  } catch (e) {
    const body = panel.querySelector('.similar-panel-body');
    if (body) {
      body.innerHTML = '<div class="similar-error">' +
        (window.tr('similar.error', 'エラーが発生しました') || 'エラーが発生しました') +
        '</div>';
    }
    console.error('findSimilarImages failed:', e);
  }
}

function _renderResults(panel: HTMLElement, results: SimilarResult[], sourceFileId: number): void {
  const body = panel.querySelector('.similar-panel-body');
  if (!body) return;

  if (results.length === 0) {
    body.innerHTML = '<div class="similar-empty">' +
      (window.tr('similar.none_found', '類似画像が見つかりませんでした。先にハッシュ計算を実行してください。') ||
       '類似画像が見つかりませんでした。先にハッシュ計算を実行してください。') +
      '</div>';
    return;
  }

  const title = panel.querySelector('.similar-panel-title');
  if (title) {
    title.textContent = (window.tr('similar.title', '類似画像') || '類似画像') + ' (' + results.length + ')';
  }

  let html = '<div class="similar-grid">';
  for (const r of results) {
    const pct = Math.max(0, 100 - (r.distance / 64 * 100));
    html += '<div class="similar-item" data-id="' + r.id + '">' +
      '<img class="similar-thumb" src="' + getAppApi().apiUrl('/api/thumbnail/' + r.id) + '" loading="lazy" alt="">' +
      '<div class="similar-dist">' + pct.toFixed(0) + '%</div>' +
      '</div>';
  }
  html += '</div>';
  body.innerHTML = html;

  // Click handler for thumbnails
  body.querySelectorAll<HTMLElement>('.similar-item').forEach((item) => {
    item.addEventListener('click', () => {
      const id = parseInt(item.dataset.id || '0', 10);
      if (id) {
        _closePanel();
        getDetailModalApi().showDetail(id, { source: 'similar' });
      }
    });
  });
}

function _closePanel(): void {
  if (_activePanel) {
    const panel = _activePanel;
    _activePanel = null;
    safeViewTransition(() => { panel.remove(); });
  }
}

// Window bridge
installWindowApi('similarApi', {
  findSimilarImages,
});
