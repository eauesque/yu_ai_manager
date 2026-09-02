/**
 * Save to Prompt Library — saves a file's prompt data to the Prompt Library extension.
 */

import { getAppApi, getNavApi } from '../../shared/browser-apis';

const { tr } = getAppApi();
const { showToast } = getNavApi();

export function saveToPromptLibrary(fileId: number): void {
  fetch('/ext/prompt-library/api/prompts/from-file', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ file_id: fileId }),
  })
    .then(r => r.json())
    .then(res => {
      if (res.ok) {
        showToast(tr('detail.saved_to_library', 'Saved to Prompt Library'));
      } else {
        showToast(res.error || tr('detail.save_failed', 'Save failed'), true);
      }
    })
    .catch(() => {
      showToast(tr('detail.save_failed', 'Save failed'), true);
    });
}
