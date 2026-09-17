/**
 * sns-share/sns-share-modal.ts — SNS share modal UI.
 *
 * Called from detail-modal or context-menu.
 * Text editing + grapheme count + X Intent / Bluesky posting.
 */

import { getNavApi } from '../shared/browser-apis';
import { fetchSnsPreview, fetchXIntentUrl, postToBluesky } from './sns-share-api';

declare const window: Window & {
  tr: (key: string, fallback?: string) => string;
};

function _tr(key: string, fb: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fb) : fb;
}

let _overlay: HTMLElement | null = null;

export async function showSnsShareModal(fileId: number): Promise<void> {
  const navApi = getNavApi();
  // Close existing modal
  closeSnsShareModal();

  // Fetch preview
  let preview;
  try {
    preview = await fetchSnsPreview(fileId);
  } catch {
    navApi.showToast('Failed to load preview', true);
    return;
  }

  // Overlay
  const overlay = document.createElement('div');
  overlay.className = 'sns-share-overlay';
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) closeSnsShareModal();
  });

  const modal = document.createElement('div');
  modal.className = 'sns-share-modal';

  // Header
  const header = document.createElement('div');
  header.className = 'sns-share-header';
  const title = document.createElement('h3');
  title.textContent = _tr('sns.modal_title', 'SNS Share');
  header.appendChild(title);
  const closeBtn = document.createElement('button');
  closeBtn.type = 'button';
  closeBtn.className = 'sns-share-close';
  closeBtn.textContent = '\u2715';
  closeBtn.addEventListener('click', closeSnsShareModal);
  header.appendChild(closeBtn);
  modal.appendChild(header);

  // Textarea
  const textarea = document.createElement('textarea');
  textarea.className = 'sns-share-textarea';
  textarea.value = preview.text;
  textarea.rows = 6;
  modal.appendChild(textarea);

  // Grapheme counter
  const counter = document.createElement('div');
  counter.className = 'sns-share-counter';
  const updateCounter = () => {
    const len = _countGraphemes(textarea.value);
    counter.textContent = `${len} graphemes`;
    counter.style.color = len > 300 ? '#e74c3c' : 'var(--muted)';
  };
  updateCounter();
  textarea.addEventListener('input', updateCounter);
  modal.appendChild(counter);

  // Image attachment checkbox
  const attachRow = document.createElement('label');
  attachRow.className = 'sns-share-attach';
  const attachCb = document.createElement('input');
  attachCb.type = 'checkbox';
  attachCb.checked = true;
  attachRow.appendChild(attachCb);
  attachRow.appendChild(document.createTextNode(' ' + _tr('sns.attach_image', 'Attach image (Bluesky)')));
  modal.appendChild(attachRow);

  // Button row
  const btnRow = document.createElement('div');
  btnRow.className = 'sns-share-buttons';

  // X button
  const xBtn = document.createElement('button');
  xBtn.type = 'button';
  xBtn.className = 'sns-share-btn sns-share-btn-x';
  xBtn.textContent = _tr('sns.share_x', 'X (Twitter)');
  xBtn.addEventListener('click', async () => {
    const url = await fetchXIntentUrl(fileId);
    if (url) window.open(url, '_blank', 'noopener');
  });
  btnRow.appendChild(xBtn);

  // Bluesky button
  const bskyBtn = document.createElement('button');
  bskyBtn.type = 'button';
  bskyBtn.className = 'sns-share-btn sns-share-btn-bsky';
  bskyBtn.textContent = _tr('sns.share_bluesky', 'Bluesky');
  bskyBtn.addEventListener('click', async () => {
    bskyBtn.disabled = true;
    bskyBtn.textContent = _tr('sns.posting', 'Posting...');
    try {
      const result = await postToBluesky(fileId, textarea.value, attachCb.checked);
      if (result.ok) {
        navApi.showToast(_tr('sns.post_success', 'Bluesky posted!'));
        closeSnsShareModal();
      } else {
        navApi.showToast(result.error || 'Post failed', true);
      }
    } finally {
      bskyBtn.disabled = false;
      bskyBtn.textContent = _tr('sns.share_bluesky', 'Bluesky');
    }
  });
  btnRow.appendChild(bskyBtn);

  modal.appendChild(btnRow);

  // Settings link
  const settingsLink = document.createElement('div');
  settingsLink.className = 'sns-share-settings-link';
  const settingsAnchor = document.createElement('a');
  settingsAnchor.href = '/settings';
  settingsAnchor.target = '_blank';
  settingsAnchor.textContent = _tr('sns.configure', 'Configure in Settings');
  settingsLink.appendChild(settingsAnchor);
  modal.appendChild(settingsLink);

  overlay.appendChild(modal);
  document.body.appendChild(overlay);
  _overlay = overlay;

  // Close on Esc (capture: true to catch before detail-modal)
  const onKey = (e: KeyboardEvent) => {
    if (e.key === 'Escape' && _overlay) {
      e.stopPropagation();
      e.preventDefault();
      closeSnsShareModal();
      document.removeEventListener('keydown', onKey, true);
    }
  };
  document.addEventListener('keydown', onKey, true);
}

export function closeSnsShareModal(): void {
  if (_overlay) {
    _overlay.remove();
    _overlay = null;
  }
}

/** Simple grapheme count (excludes combining characters). */
function _countGraphemes(text: string): number {
  let count = 0;
  for (const ch of text) {
    const cat = _charCategory(ch);
    if (cat !== 'Mn' && cat !== 'Mc' && cat !== 'Me') count++;
  }
  return count;
}

/** Simple Unicode category check (only whether it is a combining character). */
function _charCategory(ch: string): string {
  const code = ch.codePointAt(0)!;
  // Combining Diacritical Marks
  if (code >= 0x0300 && code <= 0x036F) return 'Mn';
  // Combining Diacritical Marks Extended
  if (code >= 0x1AB0 && code <= 0x1AFF) return 'Mn';
  // Combining Half Marks
  if (code >= 0xFE20 && code <= 0xFE2F) return 'Mn';
  return 'L';
}
