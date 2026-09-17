/** Toolbar attach helper for Prompt Library. */

import {
  CharacterEntry, PromptItem,
  openPicker, openSaveModal,
} from './prompt-library-picker';
import { detectSyntax } from './syntax-detect';
import { getAppApi } from '../shared/browser-apis';

export interface PromptLibraryAttachConfig {
  toolbarSelector?: string;
  prefix?: string;
  setPrompt?: (v: string) => void;
  setNegative?: (v: string) => void;
  getPrompt?: () => string;
  getNegative?: () => string;
  getParams?: () => Record<string, string>;
  getCharacters?: () => CharacterEntry[];
  setCharacters?: (chars: CharacterEntry[]) => void;
  /** Syntax mode for mismatch detection on insert. */
  syntaxMode?: 'sd_to_nai' | 'nai_to_sd' | 'none';
}

function showSyntaxConfirmDialog(opts: {
  onConvert: () => void;
  onInsertAsIs: () => void;
  onCancel: () => void;
}): void {
  const { tr } = getAppApi();
  const overlay = document.createElement('div');
  overlay.style.cssText =
    'position:fixed;inset:0;background:rgba(0,0,0,0.4);display:flex;' +
    'align-items:center;justify-content:center;z-index:9999';

  const dialog = document.createElement('div');
  dialog.setAttribute('role', 'dialog');
  dialog.setAttribute('aria-modal', 'true');
  dialog.setAttribute('aria-labelledby', 'scd-title');
  dialog.style.cssText =
    'background:var(--bg,#fff);color:var(--text,#1a1a1a);border-radius:10px;' +
    'padding:24px;max-width:420px;width:90%;box-shadow:0 8px 32px rgba(0,0,0,0.25)';

  const titleEl = document.createElement('h3');
  titleEl.id = 'scd-title';
  titleEl.style.cssText = 'margin:0 0 12px;font-size:16px';
  titleEl.textContent = tr('prompt_library.insert_syntax_mismatch_title');

  const bodyEl = document.createElement('p');
  bodyEl.style.cssText = 'margin:0 0 20px;font-size:14px;white-space:pre-line';
  bodyEl.textContent = tr('prompt_library.insert_syntax_mismatch_body');

  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display:flex;gap:8px;justify-content:flex-end';

  const cancelBtn = document.createElement('button');
  cancelBtn.id = 'scd-cancel';
  cancelBtn.style.cssText =
    'padding:6px 14px;border-radius:6px;border:1px solid #ccc;background:transparent;cursor:pointer';
  cancelBtn.textContent = tr('prompt_library.insert_cancel');

  const asIsBtn = document.createElement('button');
  asIsBtn.id = 'scd-as-is';
  asIsBtn.style.cssText =
    'padding:6px 14px;border-radius:6px;border:1px solid #ccc;background:transparent;cursor:pointer';
  asIsBtn.textContent = tr('prompt_library.insert_as_is');

  const convertBtn = document.createElement('button');
  convertBtn.id = 'scd-convert';
  convertBtn.style.cssText =
    'padding:6px 14px;border-radius:6px;border:none;background:#f59e0b;' +
    'color:#fff;cursor:pointer;font-weight:600';
  convertBtn.textContent = tr('prompt_library.insert_convert_and_insert');

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(asIsBtn);
  btnRow.appendChild(convertBtn);
  dialog.appendChild(titleEl);
  dialog.appendChild(bodyEl);
  dialog.appendChild(btnRow);
  overlay.appendChild(dialog);
  document.body.appendChild(overlay);

  const focusables = [convertBtn, asIsBtn, cancelBtn];
  convertBtn.focus();

  function cleanup(): void {
    if (overlay.parentNode) overlay.parentNode.removeChild(overlay);
  }

  dialog.addEventListener('keydown', (e) => {
    if (e.key === 'Tab') {
      e.preventDefault();
      const idx = focusables.indexOf(document.activeElement as HTMLButtonElement);
      focusables[(idx + (e.shiftKey ? -1 : 1) + focusables.length) % focusables.length].focus();
    }
    if (e.key === 'Escape') { e.preventDefault(); cleanup(); opts.onCancel(); }
    if (e.key === 'Enter') { e.preventDefault(); cleanup(); opts.onConvert(); }
  });

  cancelBtn.addEventListener('click', () => { cleanup(); opts.onCancel(); });
  asIsBtn.addEventListener('click', () => { cleanup(); opts.onInsertAsIs(); });
  convertBtn.addEventListener('click', () => { cleanup(); opts.onConvert(); });
}

function attach(config: PromptLibraryAttachConfig): void {
  const toolbar = document.querySelector(
    config.toolbarSelector || '.bridge-editor-toolbar',
  ) as HTMLElement | null;
  if (!toolbar) return;

  const hint = toolbar.querySelector('.bridge-toolbar-hint');
  const prefix = config.prefix || '';
  const { tr } = getAppApi();
  const i18n = {
    t: (key: string): string => tr(key),
  };

  function doInsert(item: PromptItem, positiveText: string, negativeText?: string): void {
    if (positiveText && config.setPrompt) config.setPrompt(positiveText);
    const negText = negativeText ?? (item.negative as string);
    if (negText && config.setNegative) config.setNegative(negText);
    if (config.setCharacters && Array.isArray(item.characters)) {
      config.setCharacters(item.characters as CharacterEntry[]);
    }
  }

  const loadBtn = document.createElement('button');
  loadBtn.className = prefix + '-btn small';
  loadBtn.textContent = '📂 PL';
  loadBtn.title = i18n.t('bridge.pl.load_tooltip');
  loadBtn.setAttribute('aria-label', loadBtn.title);
  loadBtn.addEventListener('click', () => {
    openPicker({
      onSelect(item: PromptItem) {
        const syntaxMode = config.syntaxMode ?? 'none';
        const positive = (item.positive as string) ?? '';

        if (syntaxMode === 'none' || !positive) {
          doInsert(item, positive);
          return;
        }

        const detected = detectSyntax(positive);
        const shouldWarn =
          (syntaxMode === 'sd_to_nai' && (detected === 'sd' || detected === 'mixed')) ||
          (syntaxMode === 'nai_to_sd' && (detected === 'nai' || detected === 'mixed'));

        if (!shouldWarn) {
          doInsert(item, positive);
          return;
        }

        const { apiFetch } = getAppApi();

        showSyntaxConfirmDialog({
          onInsertAsIs: () => doInsert(item, positive),
          onCancel: () => { /* picker already closed */ },
          onConvert: async () => {
            try {
              const resp = await apiFetch('/api/convert', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: positive, mode: syntaxMode }),
              });
              const data = await resp.json() as { result?: string };
              const convertedPositive = data.result ?? positive;

              let convertedNegative: string | undefined;
              const negative = (item.negative as string) ?? '';
              if (negative) {
                try {
                  const negResp = await apiFetch('/api/convert', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ prompt: negative, mode: syntaxMode }),
                  });
                  const negData = await negResp.json() as { result?: string };
                  convertedNegative = negData.result ?? negative;
                } catch {
                  convertedNegative = negative;
                }
              }

              doInsert(item, convertedPositive, convertedNegative);
            } catch {
              doInsert(item, positive);
            }
          },
        });
      },
    });
  });

  const saveBtn = document.createElement('button');
  saveBtn.className = prefix + '-btn small';
  saveBtn.textContent = '💾 PL';
  saveBtn.title = i18n.t('bridge.pl.save_tooltip');
  saveBtn.setAttribute('aria-label', saveBtn.title);
  saveBtn.addEventListener('click', () => {
    openSaveModal({
      positive: config.getPrompt ? config.getPrompt() : '',
      negative: config.getNegative ? config.getNegative() : '',
      params: config.getParams ? config.getParams() : {},
      characters: config.getCharacters ? config.getCharacters() : [],
    });
  });

  if (hint) {
    toolbar.insertBefore(loadBtn, hint);
    toolbar.insertBefore(saveBtn, hint);
  } else {
    toolbar.appendChild(loadBtn);
    toolbar.appendChild(saveBtn);
  }

  appendToolbarLegendButton(toolbar, prefix);
}

function appendToolbarLegendButton(toolbar: Element, prefix: string): void {
  const id = `${prefix}-toolbar-legend-btn`;
  if (toolbar.querySelector(`#${id}`)) return;
  const tr = (k: string, fb: string): string =>
    typeof window.tr === 'function' ? window.tr(k, fb) : fb;
  const btn = document.createElement('button');
  btn.id = id;
  btn.type = 'button';
  btn.className = `${prefix}-btn small`;
  btn.textContent = '?';
  btn.title = tr('bridge.toolbar_legend.title', 'ツールバーの略語ガイド');
  btn.setAttribute('aria-label', btn.title);
  btn.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleLegendPopover(btn, tr);
  });
  toolbar.appendChild(btn);
}

type PopoverWithCloser = HTMLElement & { _legendCloser?: (ev: MouseEvent) => void };

function _detachLegendPopover(pop: PopoverWithCloser): void {
  const closer = pop._legendCloser;
  if (closer) {
    document.removeEventListener('click', closer, true);
    delete pop._legendCloser;
  }
  pop.remove();
}

function toggleLegendPopover(anchor: HTMLElement, tr: (k: string, fb: string) => string): void {
  const existing = document.getElementById('bridge-toolbar-legend-popover') as PopoverWithCloser | null;
  if (existing) {
    _detachLegendPopover(existing);
    return;
  }
  const pop = document.createElement('div') as PopoverWithCloser;
  pop.id = 'bridge-toolbar-legend-popover';
  pop.setAttribute('role', 'dialog');
  pop.setAttribute('aria-label', tr('bridge.toolbar_legend.title', 'ツールバーの略語ガイド'));
  pop.style.cssText =
    'position:absolute;z-index:9000;min-width:280px;max-width:360px;padding:10px 14px;' +
    'border-radius:10px;background:var(--card,#1e1e2e);color:var(--text,#eee);' +
    'border:1px solid var(--border,rgba(128,128,128,0.3));' +
    'box-shadow:0 6px 24px rgba(0,0,0,0.25);font-size:12px;line-height:1.55;';
  const rect = anchor.getBoundingClientRect();
  pop.style.top = `${window.scrollY + rect.bottom + 6}px`;
  pop.style.left = `${Math.max(8, window.scrollX + rect.right - 320)}px`;
  const items: Array<[string, string, string]> = [
    ['sed', 'bridge.legend.sed', 'プロンプトに正規表現置換 (stream editor)'],
    ['Tags', 'bridge.legend.tags', 'Danbooru タグオートコンプリート ON/OFF'],
    ['Wildcard', 'bridge.legend.wc', 'Wildcard / Dynamic Prompt 展開 (server-side)'],
    ['PL', 'bridge.legend.pl', 'Prompt Library への読込・保存'],
    ['Quality Preset', 'bridge.legend.qp', 'Quality Presets — よく使う品質プロンプトをワンクリック'],
  ];
  const heading = document.createElement('div');
  heading.style.cssText = 'font-weight:600;margin-bottom:6px;';
  heading.textContent = tr('bridge.toolbar_legend.title', 'ツールバーの略語ガイド');
  pop.appendChild(heading);
  items.forEach(([abbr, key, fallback]) => {
    const row = document.createElement('div');
    row.style.cssText = 'display:flex;gap:8px;align-items:start;padding:3px 0;';
    const code = document.createElement('code');
    code.style.cssText = 'flex:0 0 96px;padding:1px 6px;border-radius:4px;background:rgba(128,128,128,0.18);font-family:ui-monospace,Consolas,monospace;font-size:11px;text-align:center;white-space:normal;';
    code.textContent = abbr;
    const desc = document.createElement('span');
    desc.textContent = tr(key, fallback);
    row.append(code, desc);
    pop.appendChild(row);
  });
  const closer = (ev: MouseEvent) => {
    if (!pop.contains(ev.target as Node) && ev.target !== anchor) {
      _detachLegendPopover(pop);
    }
  };
  pop._legendCloser = closer;
  document.addEventListener('click', closer, true);
  document.body.appendChild(pop);
}

export const BridgePromptLibrary = { attach, openPicker, openSaveModal };
