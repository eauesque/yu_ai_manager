/**
 * prompt-library-save.ts -- Save modal for Prompt Library.
 *
 * Contains the openSaveModal function for saving prompts
 * to the Prompt Library.
 * Extracted from prompt-library-picker.ts to keep each module under 300 lines.
 */

import type { CharacterEntry, SaveModalOpts } from './prompt-library-picker';
import { escHtml, showToast } from './prompt-library-picker';

const PL_API = '/ext/prompt-library/api/prompts';

export function openSaveModal(opts: SaveModalOpts): void {
  const overlay = document.createElement('div');
  overlay.className = 'bpl-overlay';

  const modal = document.createElement('div');
  modal.className = 'bpl-modal bpl-save-modal';

  const p = opts.params || {};
  const chars = opts.characters || [];

  modal.innerHTML =
    '<div class="bpl-modal-header">' +
    '<h3>PL \u306B\u4FDD\u5B58</h3>' +
    '<button class="bpl-close">&times;</button>' +
    '</div>' +
    '<div class="bpl-save-form">' +
    '<label>Title <span class="bpl-required">*</span></label>' +
    '<input class="bpl-input" id="bplSaveTitle" type="text" placeholder="\u30D7\u30ED\u30F3\u30D7\u30C8\u306E\u30BF\u30A4\u30C8\u30EB">' +
    '<label>Positive</label>' +
    '<textarea class="bpl-textarea" id="bplSavePositive" rows="3">' +
    escHtml(opts.positive || '') +
    '</textarea>' +
    '<label>Negative</label>' +
    '<textarea class="bpl-textarea" id="bplSaveNegative" rows="2">' +
    escHtml(opts.negative || '') +
    '</textarea>' +
    '<div class="bpl-save-params">' +
    '<div class="bpl-save-param"><label>Steps</label><input class="bpl-input" id="bplSaveSteps" value="' +
    escHtml(p.steps || '') +
    '"></div>' +
    '<div class="bpl-save-param"><label>Sampler</label><input class="bpl-input" id="bplSaveSampler" value="' +
    escHtml(p.sampler || '') +
    '"></div>' +
    '<div class="bpl-save-param"><label>CFG</label><input class="bpl-input" id="bplSaveCfg" value="' +
    escHtml(p.cfg_scale || '') +
    '"></div>' +
    '<div class="bpl-save-param"><label>Seed</label><input class="bpl-input" id="bplSaveSeed" value="' +
    escHtml(p.seed || '') +
    '"></div>' +
    '<div class="bpl-save-param"><label>Model</label><input class="bpl-input" id="bplSaveModel" value="' +
    escHtml(p.model_name || '') +
    '"></div>' +
    '</div>' +
    '<label>Memo</label>' +
    '<textarea class="bpl-textarea" id="bplSaveMemo" rows="2" placeholder="\u30E1\u30E2 (\u4EFB\u610F)"></textarea>' +
    (chars.length > 0
      ? '<div class="bpl-chars-summary" id="bplSaveCharsInfo">' +
        '<label>Character Prompts (' + chars.length + ')</label>' +
        chars.map((c: CharacterEntry, i: number) => {
          const preview = (c.prompt || '').substring(0, 60) + ((c.prompt || '').length > 60 ? '...' : '');
          const pos = c.center ? ' [' + c.center.x.toFixed(2) + ', ' + c.center.y.toFixed(2) + ']' : ' [AI]';
          return '<div class="bpl-char-entry">#' + (i + 1) + pos + ': ' + escHtml(preview) + '</div>';
        }).join('') +
        '</div>'
      : '') +
    '<button class="bpl-save-btn">\u4FDD\u5B58</button>' +
    '</div>';

  overlay.appendChild(modal);
  document.body.appendChild(overlay);

  type LinterHandle = { detach(): void };
  const linterApi = (window as unknown as Record<string, unknown>)['PromptLinter'] as { attach(ta: HTMLTextAreaElement, opts?: Record<string, unknown>): LinterHandle } | undefined;
  let posLinter: LinterHandle | null = null;
  let negLinter: LinterHandle | null = null;
  if (linterApi) {
    const posTa = document.getElementById('bplSavePositive') as HTMLTextAreaElement | null;
    const negTa = document.getElementById('bplSaveNegative') as HTMLTextAreaElement | null;
    if (posTa) posLinter = linterApi.attach(posTa, { syntaxMode: opts.syntaxMode || 'unknown', hasSyntaxWidget: false });
    if (negTa) negLinter = linterApi.attach(negTa, { syntaxMode: opts.syntaxMode || 'unknown', hasSyntaxWidget: false });
  }

  function close(): void {
    posLinter?.detach();
    negLinter?.detach();
    overlay.remove();
  }

  (modal.querySelector('.bpl-close') as HTMLElement).onclick = close;
  overlay.addEventListener('click', (e) => {
    if (e.target === overlay) close();
  });

  modal.querySelector('.bpl-save-btn')!.addEventListener('click', () => {
    const titleEl = document.getElementById('bplSaveTitle') as HTMLInputElement;
    const title = titleEl.value.trim();
    if (!title) {
      titleEl.focus();
      return;
    }

    const body: Record<string, unknown> = {
      title,
      positive: (document.getElementById('bplSavePositive') as HTMLTextAreaElement).value.trim(),
      negative: (document.getElementById('bplSaveNegative') as HTMLTextAreaElement).value.trim(),
      steps: (document.getElementById('bplSaveSteps') as HTMLInputElement).value.trim(),
      sampler: (document.getElementById('bplSaveSampler') as HTMLInputElement).value.trim(),
      cfg_scale: (document.getElementById('bplSaveCfg') as HTMLInputElement).value.trim(),
      seed: (document.getElementById('bplSaveSeed') as HTMLInputElement).value.trim(),
      model_name: (document.getElementById('bplSaveModel') as HTMLInputElement).value.trim(),
      memo: (document.getElementById('bplSaveMemo') as HTMLTextAreaElement).value.trim(),
    };
    if (chars.length > 0) {
      body.characters = chars;
    }

    fetch(PL_API, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((resp: { ok?: boolean; error?: string }) => {
        if (resp.ok === false) {
          showToast(resp.error || '\u4FDD\u5B58\u306B\u5931\u6557\u3057\u307E\u3057\u305F', true);
        } else {
          showToast('\u4FDD\u5B58\u3057\u307E\u3057\u305F');
          close();
        }
      })
      .catch(() => showToast('\u4FDD\u5B58\u306B\u5931\u6557\u3057\u307E\u3057\u305F', true));
  });

  (document.getElementById('bplSaveTitle') as HTMLInputElement).focus();
}
