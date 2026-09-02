/**
 * context-menu/context-menu-actions.ts — Action dispatchers for context menu items.
 *
 * Each action references the namespaced browser APIs with legacy alias fallback.
 */

import { getAppApi, getDetailModalApi, getNavApi, getRatingsApi, getRuntimeToolsApi, getSimilarApi } from '../shared/browser-apis';

interface CardData {
  id: number;
  path: string;
  positive: string;
  negative: string;
}

function _tr(key: string, fb: string): string {
  return getAppApi().tr(key, fb);
}

function _toast(msg: string): void {
  getNavApi().showToast(msg);
}

export function actionShowDetail(data: CardData): void {
  getDetailModalApi().showDetail(data.id, { source: 'context_menu' });
}

export function actionCopyPositive(data: CardData): void {
  getDetailModalApi().copyToClipboard(data.positive).then(() => _toast(_tr('ctx.copied', 'コピーしました')));
}

export function actionCopyNegative(data: CardData): void {
  getDetailModalApi().copyToClipboard(data.negative).then(() => _toast(_tr('ctx.copied', 'コピーしました')));
}

export function actionCopySD(data: CardData): void {
  const text = data.positive + (data.negative ? '\nNegative prompt: ' + data.negative : '');
  getDetailModalApi().copyToClipboard(text).then(() => _toast(_tr('ctx.copied_sd', 'SD形式でコピーしました')));
}

export function actionCopyNAI(data: CardData): void {
  // NAI format: positive is same, negative separate
  const text = data.positive;
  getDetailModalApi().copyToClipboard(text).then(() => _toast(_tr('ctx.copied_nai', 'NAI形式でコピーしました')));
}

export function actionToggleFavorite(data: CardData): void {
  void getRuntimeToolsApi().toggleFavorite?.(data.id);
}

export function actionSetRating(data: CardData, rating: number): void {
  void getRatingsApi().setRating(data.id, rating);
}

export function actionSendToBridge(data: CardData, target: string): void {
  const urls: Record<string, string> = {
    sd: '/ext/sd-webui/',
    comfy: '/ext/comfyui-bridge/',
    nai: '/ext/nai-bridge/',
  };
  const url = urls[target];
  if (!url) return;
  localStorage.setItem('bridge_send_prompt', JSON.stringify({
    prompt: data.positive,
    negative: data.negative,
  }));
  window.open(url, '_blank');
}

export function actionSaveToPromptLibrary(data: CardData): void {
  getRuntimeToolsApi().saveToPromptLibrary(data.id);
}

export function actionFindSimilar(data: CardData): void {
  // Open detail first, then trigger similar search
  getDetailModalApi().showDetail(data.id, { source: 'context_menu' });
  setTimeout(() => {
    void getSimilarApi().findSimilarImages(data.id);
  }, 300);
}

export function actionShowQR(data: CardData): void {
  void getRuntimeToolsApi().showQRShare(data.id);
}

export function actionCopyFilePath(data: CardData): void {
  getDetailModalApi().copyToClipboard(data.path).then(() => _toast(_tr('ctx.path_copied', 'パスをコピーしました')));
}

export function actionAnalyze(data: CardData): void {
  getDetailModalApi().showDetail(data.id, { source: 'context_menu' });
  setTimeout(() => {
    void getRuntimeToolsApi().analyzeCurrentImage(data.id);
  }, 300);
}

export function actionSnsShare(data: CardData): void {
  const snsShareApi = window.snsShareApi as Record<string, unknown> | undefined;
  const fn = snsShareApi?.showSnsShare;
  if (typeof fn === 'function') (fn as (fileId: number) => Promise<void>)(data.id);
}

export function actionCopyRecipeParams(data: CardData): void {
  void import('../recipe_share').then(({ copyRecipeParams }) => {
    void copyRecipeParams(data.id).then((ok) => {
      if (ok) _toast(_tr('ctx.recipe_copied', 'パラメータをコピーしました'));
    });
  });
}

export function actionSendWorkflowToComfyUI(data: CardData): void {
  void import('../apps/bridge-workflow-queue').then(({ sendWorkflowToComfyUI }) => {
    sendWorkflowToComfyUI(data.id);
  }).catch(() => {
    const { showToast } = getNavApi();
    showToast('ComfyUI ワークフロー送信の初期化に失敗しました', true);
  });
}

export function actionShowAppQR(data: CardData): void {
  void import('../recipe_share').then(async ({ fetchRecipeById, buildAppQR, downloadRecipeJSON }) => {
    const recipe = await fetchRecipeById(data.id);
    if (!recipe) {
      _toast(_tr('ctx.recipe_no_meta', 'この画像には生成情報がありません'));
      return;
    }

    const overlay = document.createElement('div');
    overlay.style.cssText =
      'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center';

    const panel = document.createElement('div');
    panel.style.cssText =
      'background:#1e1e2e;border-radius:8px;padding:20px;text-align:center;color:#cdd6f4;font-family:sans-serif;min-width:240px';

    const titleEl = document.createElement('div');
    titleEl.style.cssText = 'font-size:12px;color:#89b4fa;margin-bottom:12px;font-weight:bold';
    titleEl.textContent = '📱 App QR（アプリ専用）';
    panel.appendChild(titleEl);

    const canvas = document.createElement('canvas');
    panel.appendChild(canvas);

    const closeBtn = document.createElement('button');
    closeBtn.textContent = '閉じる';
    closeBtn.style.cssText =
      'margin-top:12px;padding:6px 16px;background:#45475a;color:#cdd6f4;border:none;border-radius:4px;cursor:pointer;display:block;width:100%';
    closeBtn.onclick = () => overlay.remove();
    panel.appendChild(closeBtn);

    overlay.appendChild(panel);
    overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
    document.body.appendChild(overlay);

    try {
      const result = await buildAppQR(recipe, canvas);
      if (!result.ok && result.oversized) {
        overlay.remove();
        const { customConfirm } = await import('../shared/dialog');
        if (await customConfirm(_tr('ctx.recipe_qr_oversized', 'QRに収まりません。JSONとして保存しますか？'))) {
          await downloadRecipeJSON(data.id);
        }
      }
    } catch {
      overlay.remove();
      const { customAlert } = await import('../shared/dialog');
      await customAlert(_tr('ctx.recipe_qr_error', 'QRコードの生成に失敗しました'));
    }
  });
}
