/**
 * Inspect page global function bridge.
 * Provides window.* functions that meta-renderer and character-render
 * depend on but are normally supplied by main-app / runtime-tools-ui bundles.
 *
 * Must be imported in inspect-app.ts before other modules that call
 * these at runtime (character-render, convert buttons, etc.).
 */

import { escapeHtml, apiUrl, apiFetch, decodeHtmlEntities } from '../main/api-utils';
import { installWindowApi } from '../shared/window-api';

let _convertModPromise: Promise<typeof import('../runtime-tools-ui/tools/convert')> | null = null;
let _copyModPromise: Promise<typeof import('../runtime-tools-ui/tools/copy')> | null = null;

function _loadConvertMod(): Promise<typeof import('../runtime-tools-ui/tools/convert')> {
  if (!_convertModPromise) {
    _convertModPromise = import('../runtime-tools-ui/tools/convert');
  }
  return _convertModPromise;
}

function _loadCopyMod(): Promise<typeof import('../runtime-tools-ui/tools/copy')> {
  if (!_copyModPromise) {
    _copyModPromise = import('../runtime-tools-ui/tools/copy');
  }
  return _copyModPromise;
}

async function copyToClipboard(text: string): Promise<boolean> {
  const decoded = decodeHtmlEntities(text);
  try {
    await navigator.clipboard.writeText(decoded);
    return true;
  } catch {
    try {
      const ta = document.createElement('textarea');
      ta.value = decoded;
      ta.style.cssText = 'position:fixed;left:-9999px;top:0';
      document.body.appendChild(ta);
      ta.focus();
      ta.select();
      const ok = document.execCommand('copy');
      document.body.removeChild(ta);
      return !!ok;
    } catch { return false; }
  }
}
const copySeed = async (seed: string | number, event?: Event) => {
  const { copyWithFeedback } = await _loadCopyMod();
  await copyWithFeedback(String(seed), (event?.target as HTMLElement) || null, 'Seed ');
};

const searchByCheckpoint = async (modelName: string, event?: Event) => {
  if (!modelName) return;
  const { copyWithFeedback } = await _loadCopyMod();
  await copyWithFeedback(modelName, (event?.target as HTMLElement) || null, 'Model ');
};

async function convertAndCopy(...args: Parameters<typeof import('../runtime-tools-ui/tools/convert').convertAndCopy>): Promise<void> {
  const mod = await _loadConvertMod();
  return mod.convertAndCopy(...args);
}

async function convertAndShow(...args: Parameters<typeof import('../runtime-tools-ui/tools/convert').convertAndShow>): Promise<void> {
  const mod = await _loadConvertMod();
  return mod.convertAndShow(...args);
}

installWindowApi('inspectPageApi', {
  escapeHtml,
  apiUrl,
  apiFetch,
  decodeHtmlEntities,
  copyToClipboard,
  convertAndCopy,
  convertAndShow,
  copySeed,
  searchByCheckpoint,
});
