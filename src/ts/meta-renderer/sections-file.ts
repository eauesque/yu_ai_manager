/**
 * Meta-renderer file header and parameters rendering.
 * Converted from static/js/meta-renderer/sections-file.js
 */

import { esc, escAttr, toB64, sectionOpen, sectionClose } from './utils';
import { getRuntimeToolsApi } from '../shared/browser-apis';
import { extractSeed } from '../shared/bridge-payload';

function _tr(key: string, fallback: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fallback) : fallback;
}

// Detect hires-fix / upscale by comparing the recorded source Size against
// the actual file dimensions. When they diverge, surface both values plus the
// scale factor (e.g. "832×1216 → 1664×2432 (×2)").
function _formatResolution(
  data: Record<string, unknown>,
  params: Record<string, unknown> | undefined,
): string | null {
  const actualW = Number(data.width) || 0;
  const actualH = Number(data.height) || 0;
  const actualRes = (actualW && actualH) ? `${actualW}×${actualH}` : null;

  let origW = 0;
  let origH = 0;
  if (params) {
    const sizeRaw = params.Size ?? (params as Record<string, unknown>).size;
    if (typeof sizeRaw === 'string') {
      const m = sizeRaw.match(/^\s*(\d+)\s*[x×]\s*(\d+)\s*$/i);
      if (m) {
        origW = parseInt(m[1], 10) || 0;
        origH = parseInt(m[2], 10) || 0;
      }
    }
  }

  if (origW && origH && actualW && actualH && (origW !== actualW || origH !== actualH)) {
    const ratioW = actualW / origW;
    const ratioH = actualH / origH;
    let ratioLabel = '';
    if (Math.abs(ratioW - ratioH) < 0.02) {
      const r = Math.round(ratioW * 100) / 100;
      const rStr = (Math.abs(r - Math.round(r)) < 0.005) ? String(Math.round(r)) : r.toFixed(2);
      ratioLabel = ` (×${rStr})`;
    }
    return `${origW}×${origH} → ${actualW}×${actualH}${ratioLabel}`;
  }

  if (typeof data.resolution === 'string' && data.resolution) return data.resolution;
  return actualRes;
}

export function renderFileHeader(data: Record<string, unknown>): string {
  const runtimeToolsApi = getRuntimeToolsApi();
  const id = data.id as number | undefined;
  let html = '';
  if (id !== undefined) {
    html += '<div class="file-header">';
    html += '<h2 class="filename-clickable" data-action="runtimeToolsApi.openFileDirectory" data-action-arg="' + escAttr(String(id)) + '" title="' + esc(_tr('meta.click_open_dir', 'Click to open directory')) + '">';
    html += runtimeToolsApi.renderFileName(String(data.path || ''));
    html += '</h2>';
    html += '<div class="file-path-container">' + runtimeToolsApi.renderPathDisplay(String(data.path || ''), id) + '</div>';
    html += '</div>';
  }

  html += '<div class="meta-file-info">';
  if (data.mtime) html += '<span>' + esc(new Date((data.mtime as number) * 1000).toLocaleString()) + '</span>';
  if (data.meta_source) html += '<span>\uD83D\uDCCB ' + esc(String(data.meta_source)) + '</span>';
  if (data.size) html += '<span>' + esc(((data.size as number) / 1024).toFixed(1)) + ' KB</span>';
  const params = data.parameters as Record<string, unknown> | undefined;
  const res = _formatResolution(data, params);
  if (res) html += '<span>\uD83D\uDCD0 ' + esc(res) + '</span>';
  if (data.model) html += '<span class="model-clickable" data-action="runtimeToolsApi.searchByCheckpoint" data-action-arg="' + escAttr(String(data.model)) + '" title="' + esc(_tr('meta.checkpoint_search', 'Checkpoint search')) + '" style="cursor:pointer;">\uD83C\uDFA8 ' + esc(String(data.model)) + '</span>';
  const seed = extractSeed({ parameters: params });
  if (seed != null) html += '<span class="seed-clickable" data-action="runtimeToolsApi.copySeed" data-action-arg="' + escAttr(String(seed)) + '" title="' + esc(_tr('meta.seed_copy', 'Copy Seed')) + '" style="cursor:pointer;">\uD83C\uDFB2 ' + esc(String(seed)) + '</span>';
  if (data.file_hash) html += '<span>\uD83D\uDD11 ' + esc(String(data.file_hash)) + '</span>';
  if (data.parsed !== undefined) html += '<span>' + (data.parsed ? '\u2705 ' + _tr('meta.parse_success', 'Parse succeeded') : '\u26A0\uFE0F ' + _tr('meta.no_metadata', 'No metadata')) + '</span>';
  html += '</div>';
  return html;
}

const PARAMS_HIDDEN_KEYS = new Set(['Model', 'Model hash', 'VAE hash', 'Seed', 'seed', 'noise_seed', 'Size', 'Version']);

export function renderParams(params: unknown): string {
  if (!params) return '';
  if (typeof params === 'string') {
    if (!params.trim()) return '';
    return sectionOpen('\u2699\uFE0F', _tr('meta.parameters_title', 'Parameters')) + '<div class="meta-params-text">' + esc(params) + '</div>' + sectionClose();
  }
  if (typeof params !== 'object' || Object.keys(params as object).length === 0) return '';

  let html = sectionOpen('\u2699\uFE0F', _tr('share.gen_params', 'Generation Parameters'));
  html += '<div class="meta-params-grid">';
  for (const key in params as Record<string, unknown>) {
    if (!Object.prototype.hasOwnProperty.call(params, key)) continue;
    if (PARAMS_HIDDEN_KEYS.has(key)) continue;
    const v = (params as Record<string, unknown>)[key];
    const val = v === null || v === undefined ? '' : typeof v === 'object' ? JSON.stringify(v) : String(v);
    const b64 = toB64(val);
    html += '<div class="meta-param-item">';
    html += '<span class="meta-param-key">' + esc(key) + ':</span> ';
    html += '<span class="copy-target meta-param-val" data-copy-b64="' + b64 + '" data-copy-label="' + escAttr(key) + ': " title="' + esc(_tr('meta.click_to_copy', 'Click to copy')) + '">' + esc(val) + '</span>';
    html += '</div>';
  }
  html += '</div>';
  html += sectionClose();
  return html;
}
