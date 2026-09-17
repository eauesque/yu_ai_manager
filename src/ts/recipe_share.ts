/**
 * recipe_share.ts - Generation parameter recipe sharing.
 *
 * buildA1111Text(recipe)     - A1111-format text for compat QR + clipboard
 * buildAppQR(recipe, canvas) - pure-JSON QR for app users (with size check)
 * buildCompatQR(text, canvas)- A1111 text QR for compat display
 * copyRecipeParams(fileId)   - fetch recipe -> A1111 text -> clipboard
 * downloadRecipeJSON(fileId) - fetch recipe -> download .json
 * downloadRecipeCSV(fileId)  - fetch recipe -> download single-row .csv
 * openImportModal(recipe)    - Bridge selector dialog + bridgeStorage write
 */

import QRCode from 'qrcode';
import { bridgeStorage } from './shared/bridge-storage';
import { customAlert } from './shared/dialog';
import { copyToClipboard } from './shared/clipboard';
import type { PromptPayload } from './shared/bridge-payload';
import type { PublicKeyEnvelope } from './crypto/subtle_ops';

const APP_QR_MAX_BYTES = 2150;

export interface RecipeObject {
  schema: string;
  bridge_id: string;
  model?: string;
  model_hash?: string;
  seed?: number;
  steps?: number;
  cfg?: number;
  sampler?: string;
  width?: number;
  height?: number;
  positive: string;
  negative: string;
  capture_warnings: string[];
}

export interface ImportResult {
  bridge_id: string;
  generate_url: string | null;
  generate_body: Record<string, unknown> | null;
  import_warnings: string[];
}

function _apiFetch(url: string, opts?: RequestInit): Promise<Response> {
  const api = (window as unknown as Record<string, unknown>);
  const fn = (api['appApi'] as Record<string, unknown>)?.['apiFetch'] ?? api['apiFetch'];
  if (typeof fn === 'function') return (fn as (u: string, o?: RequestInit) => Promise<Response>)(url, opts);
  return fetch(url, opts);
}

export async function fetchRecipeById(fileId: number): Promise<RecipeObject | null> {
  // Pass silent:true (recognised by main/api-utils apiFetch) so expected
  // 404 "no gen metadata" responses are not reported as error bundles.
  // Wrap in try/catch because apiFetch throws on non-2xx instead of returning
  // a non-ok Response, so `if (!res.ok)` would never be reached otherwise.
  try {
    const res = await _apiFetch(
      `/api/recipe/export/${fileId}`,
      { silent: true } as unknown as RequestInit,
    );
    if (!res.ok) return null;
    const json = await res.json() as { data?: RecipeObject };
    return json.data ?? null;
  } catch {
    // 404 (no gen metadata) or network error — recipe section stays hidden.
    return null;
  }
}

export function buildA1111Text(recipe: RecipeObject): string {
  const parts: string[] = [];
  if (recipe.positive) parts.push(recipe.positive);
  if (recipe.negative) parts.push(`Negative prompt: ${recipe.negative}`);

  const params: string[] = [];
  if (recipe.steps != null) params.push(`Steps: ${recipe.steps}`);
  if (recipe.cfg != null) params.push(`CFG scale: ${recipe.cfg}`);
  if (recipe.seed != null) params.push(`Seed: ${recipe.seed}`);
  if (recipe.sampler) params.push(`Sampler: ${recipe.sampler}`);
  if (recipe.width != null && recipe.height != null) params.push(`Size: ${recipe.width}x${recipe.height}`);
  if (recipe.model) params.push(`Model: ${recipe.model}`);
  if (params.length) parts.push(params.join(', '));

  return parts.join('\n');
}

export async function buildAppQR(
  recipe: RecipeObject,
  canvas: HTMLCanvasElement,
): Promise<{ ok: boolean; oversized: boolean }> {
  // Omit capture_warnings from QR payload — diagnostic metadata not needed by receiver.
  const { capture_warnings: _cw, ...compact } = recipe;
  const jsonStr = JSON.stringify(compact);
  const byteLen = new TextEncoder().encode(jsonStr).length;
  if (byteLen > APP_QR_MAX_BYTES) return { ok: false, oversized: true };
  await QRCode.toCanvas(canvas, jsonStr, { errorCorrectionLevel: 'M', width: 200 });
  return { ok: true, oversized: false };
}

export async function buildCompatQR(text: string, canvas: HTMLCanvasElement): Promise<void> {
  await QRCode.toCanvas(canvas, text, { errorCorrectionLevel: 'M', width: 200 });
}

export async function copyRecipeParams(fileId: number): Promise<boolean> {
  const recipe = await fetchRecipeById(fileId);
  if (!recipe) return false;
  try {
    await copyToClipboard(buildA1111Text(recipe));
    return true;
  } catch {
    return false;
  }
}

function _triggerDownload(blob: Blob, filename: string): void {
  const a = document.createElement('a');
  a.href = URL.createObjectURL(blob);
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(() => URL.revokeObjectURL(a.href), 100);
}

export async function downloadRecipeJSON(fileId: number): Promise<void> {
  const recipe = await fetchRecipeById(fileId);
  if (!recipe) return;
  const blob = new Blob([JSON.stringify(recipe, null, 2)], { type: 'application/json' });
  _triggerDownload(blob, `recipe_${fileId}.json`);
}

export async function downloadRecipeCSV(fileId: number): Promise<void> {
  const recipe = await fetchRecipeById(fileId);
  if (!recipe) return;
  function esc(v: unknown): string {
    const s = String(v ?? '');
    return s.includes(',') || s.includes('"') || s.includes('\n')
      ? `"${s.replace(/"/g, '""')}"`
      : s;
  }
  const headers = 'id,bridge_id,model,model_hash,seed,steps,cfg,sampler,width,height,positive,negative';
  const row = [
    fileId, recipe.bridge_id, recipe.model ?? '', recipe.model_hash ?? '',
    recipe.seed ?? '', recipe.steps ?? '', recipe.cfg ?? '', recipe.sampler ?? '',
    recipe.width ?? '', recipe.height ?? '', recipe.positive, recipe.negative,
  ].map(esc).join(',');
  const bom = '\uFEFF';
  const blob = new Blob([bom + headers + '\n' + row], { type: 'text/csv;charset=utf-8' });
  _triggerDownload(blob, `recipe_${fileId}.csv`);
}

const BRIDGE_URLS: Record<string, string> = {
  nai: '/ext/nai-bridge/',
  'sd-webui': '/ext/sd-webui/',
  comfyui: '/ext/comfyui-bridge/',
};

export async function openImportModal(recipe: RecipeObject): Promise<void> {
  if (recipe.schema !== 'yu://recipe/1') {
    await customAlert(`サポートされていないスキーマです: ${recipe.schema}`);
    return;
  }

  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center';

  const panel = document.createElement('div');
  panel.style.cssText = 'background:#1e1e2e;border-radius:8px;padding:24px;min-width:340px;max-width:480px;color:#cdd6f4;font-family:sans-serif';

  const title = document.createElement('h3');
  title.textContent = 'レシピをインポート';
  title.style.margin = '0 0 12px';
  panel.appendChild(title);

  const summary = document.createElement('pre');
  summary.style.cssText = 'background:#181825;border-radius:4px;padding:10px;font-size:11px;white-space:pre-wrap;margin-bottom:12px;color:#a6e3a1';
  summary.textContent = [
    recipe.model ? `Model: ${recipe.model}` : '',
    recipe.seed != null ? `Seed: ${recipe.seed}` : '',
    recipe.steps != null ? `Steps: ${recipe.steps}` : '',
    recipe.positive ? `Prompt: ${recipe.positive.slice(0, 80)}${recipe.positive.length > 80 ? '…' : ''}` : '',
  ].filter(Boolean).join('\n');
  panel.appendChild(summary);

  if (recipe.capture_warnings.length) {
    const warn = document.createElement('div');
    warn.style.cssText = 'background:#45475a;border-radius:4px;padding:8px;font-size:11px;margin-bottom:12px;color:#f9e2af';
    warn.textContent = `⚠ 正規化できなかったキー: ${recipe.capture_warnings.join(', ')}`;
    panel.appendChild(warn);
  }

  const selLabel = document.createElement('div');
  selLabel.textContent = 'Bridge を選択:';
  selLabel.style.marginBottom = '6px';
  panel.appendChild(selLabel);

  const sel = document.createElement('select');
  sel.style.cssText = 'width:100%;padding:6px;background:#313244;color:#cdd6f4;border:1px solid #45475a;border-radius:4px;margin-bottom:16px';
  const bridgeLabels: Record<string, string> = { nai: 'NAI Bridge', 'sd-webui': 'SD WebUI Bridge', comfyui: 'ComfyUI Bridge' };
  for (const bid of ['nai', 'sd-webui', 'comfyui']) {
    const opt = document.createElement('option');
    opt.value = bid;
    opt.textContent = bridgeLabels[bid] ?? bid;
    if (bid === recipe.bridge_id) opt.selected = true;
    sel.appendChild(opt);
  }
  panel.appendChild(sel);

  const btnRow = document.createElement('div');
  btnRow.style.cssText = 'display:flex;gap:8px;justify-content:flex-end';

  const cancelBtn = document.createElement('button');
  cancelBtn.textContent = 'キャンセル';
  cancelBtn.style.cssText = 'padding:8px 16px;background:#45475a;color:#cdd6f4;border:none;border-radius:4px;cursor:pointer';
  cancelBtn.onclick = () => overlay.remove();

  const genBtn = document.createElement('button');
  genBtn.textContent = '生成する';
  genBtn.style.cssText = 'padding:8px 16px;background:#89b4fa;color:#1e1e2e;border:none;border-radius:4px;cursor:pointer;font-weight:bold';
  genBtn.onclick = async () => {
    const selectedBridgeId = sel.value;
    const url = BRIDGE_URLS[selectedBridgeId];
    if (!url) return;

    const payload: PromptPayload = {
      prompt: recipe.positive,
      negative: recipe.negative,
      source: 'recipe_import',
      ...(recipe.seed != null ? { seed: recipe.seed } : {}),
      ...(recipe.steps != null ? { steps: recipe.steps } : {}),
      ...(recipe.cfg != null ? { scale: recipe.cfg } : {}),
      ...(recipe.model ? { model: recipe.model } : {}),
      ...(recipe.sampler ? { sampler: recipe.sampler } : {}),
      ...(recipe.width != null ? { width: recipe.width } : {}),
      ...(recipe.height != null ? { height: recipe.height } : {}),
    };

    const ok = await bridgeStorage.set('bridge_send_prompt', payload);
    overlay.remove();
    if (ok) window.open(url, '_blank');
  };

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(genBtn);
  panel.appendChild(btnRow);

  const note = document.createElement('p');
  note.style.cssText = 'margin:12px 0 0;font-size:10px;color:#6c7086';
  note.textContent = '※ 同一パラメータでもハードウェア差により完全一致しない場合があります';
  panel.appendChild(note);

  overlay.appendChild(panel);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}

// ─── Sealed recipe (yu://seal/1 wrapping yu://recipe/1) ─────────────────────

export async function sealRecipeForRecipient(
  recipe: RecipeObject,
  recipientEnvJson: string,
): Promise<string> {
  const { sealForRecipient, base64UrlToBytes } = await import('./crypto/subtle_ops');
  const { getKey } = await import('./crypto/key_store');

  let recipientEnv: Record<string, unknown>;
  try {
    recipientEnv = JSON.parse(recipientEnvJson) as Record<string, unknown>;
  } catch {
    throw new Error('公開鍵 JSON の解析に失敗しました。');
  }
  if (recipientEnv['schema'] !== 'yu://key/1' || recipientEnv['alg'] !== 'x25519') {
    throw new Error('yu://key/1 形式の公開鍵 JSON が必要です。');
  }

  const { capture_warnings: _cw, ...recipePayload } = recipe;
  const plaintext = JSON.stringify(recipePayload);

  const record = await getKey();
  const signPrivJwk = record?.signPrivJwk;
  const signPubRaw = record?.signPubRaw ? base64UrlToBytes(record.signPubRaw) : undefined;

  const sealed = await sealForRecipient(
    plaintext,
    recipientEnv as unknown as PublicKeyEnvelope,
    signPrivJwk,
    signPubRaw,
  );
  return JSON.stringify(sealed);
}

export async function openSealRecipeModal(recipe: RecipeObject): Promise<void> {
  const overlay = document.createElement('div');
  overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center';

  const panel = document.createElement('div');
  panel.style.cssText = 'background:#1e1e2e;border-radius:8px;padding:24px;width:min(480px,94vw);color:#cdd6f4;font-family:sans-serif';

  const mkEl = <K extends keyof HTMLElementTagNameMap>(tag: K, style: string, text?: string): HTMLElementTagNameMap[K] => {
    const el = document.createElement(tag);
    el.style.cssText = style;
    if (text !== undefined) el.textContent = text;
    return el;
  };

  panel.appendChild(mkEl('h3', 'margin:0 0 12px', '🔐 レシピを暗号化して共有'));
  panel.appendChild(mkEl('p', 'font-size:12px;color:#a6adc8;margin:0 0 10px', '受信者の公開鍵（yu://key/1 JSON）を貼り付けてください。'));

  const pubkeyArea = document.createElement('textarea');
  pubkeyArea.rows = 4;
  pubkeyArea.placeholder = '{"schema":"yu://key/1","alg":"x25519","pub":"..."}';
  pubkeyArea.style.cssText = 'width:100%;box-sizing:border-box;background:#313244;color:#cdd6f4;border:1px solid #45475a;border-radius:4px;padding:8px;font-size:12px;font-family:monospace;resize:vertical';
  panel.appendChild(pubkeyArea);

  const resultBlock = mkEl('div', 'margin-top:12px');
  resultBlock.hidden = true;
  resultBlock.appendChild(mkEl('p', 'font-size:12px;color:#a6adc8;margin:0 0 6px', '封印済みペイロード（受信者は Crypto Tools で復号）:'));

  const outputArea = document.createElement('textarea');
  outputArea.rows = 5;
  outputArea.readOnly = true;
  outputArea.style.cssText = 'width:100%;box-sizing:border-box;background:#181825;color:#a6e3a1;border:1px solid #45475a;border-radius:4px;padding:8px;font-size:11px;font-family:monospace;resize:vertical';
  resultBlock.appendChild(outputArea);

  const copyBtn = mkEl('button', 'margin-top:6px;padding:6px 14px;background:#89b4fa;color:#1e1e2e;border:none;border-radius:4px;cursor:pointer;font-weight:bold', 'コピー');
  copyBtn.addEventListener('click', async () => {
    await copyToClipboard(outputArea.value).catch(() => undefined);
    copyBtn.textContent = '✅ コピー済み';
  });
  resultBlock.appendChild(copyBtn);
  panel.appendChild(resultBlock);

  const errEl = mkEl('p', 'color:#f38ba8;font-size:12px;margin:8px 0 0');
  errEl.hidden = true;
  panel.appendChild(errEl);

  const btnRow = mkEl('div', 'display:flex;gap:8px;justify-content:flex-end;margin-top:16px');
  const cancelBtn = mkEl('button', 'padding:8px 16px;background:#45475a;color:#cdd6f4;border:none;border-radius:4px;cursor:pointer', '閉じる');
  cancelBtn.addEventListener('click', () => overlay.remove());

  const sealBtn = mkEl('button', 'padding:8px 16px;background:#a6e3a1;color:#1e1e2e;border:none;border-radius:4px;cursor:pointer;font-weight:bold', '暗号化する');
  sealBtn.addEventListener('click', async () => {
    errEl.hidden = true;
    resultBlock.hidden = true;
    copyBtn.textContent = 'コピー';
    try {
      const sealedJson = await sealRecipeForRecipient(recipe, pubkeyArea.value.trim());
      outputArea.value = sealedJson;
      resultBlock.hidden = false;
    } catch (e) {
      errEl.textContent = (e as Error).message;
      errEl.hidden = false;
    }
  });

  btnRow.appendChild(cancelBtn);
  btnRow.appendChild(sealBtn);
  panel.appendChild(btnRow);
  overlay.appendChild(panel);
  overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
  document.body.appendChild(overlay);
}
