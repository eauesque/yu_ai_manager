import * as uiState from '../../runtime-pre/ui-state';
import { copyToClipboard } from '../../shared/clipboard';
import { buildModalInfoHtml } from '../content/media';
import { renderCharacterPromptsForData } from '../content/character';
import { renderCharacterGridForData } from '../content/character-grid-bridge';
import { interactionsFocusBestInModal } from '../interactions/interactions-index';
import { detailModalRuntimeControls } from './controls';
import { initDragToShare } from './drag-to-share';
import { getDetailModalRuntimeHooks } from './runtime-hooks';
import type { state as runtimeState } from './state';
import { initModalTabs, onTabActivated } from '../tabs/modal-tabs';
import { getAppApi, getDetailModalApi, getRuntimeToolsApi } from '../../shared/browser-apis';
import { initToolbarCollapse } from '../content/toolbar/toolbar-collapse';
import { loadSweepCard } from './sweep-card';

const ui = () => uiState;

/**
 * Defer non-critical initialization tasks.
 * Uses requestIdleCallback (or setTimeout fallback) to avoid blocking
 * the critical path for image display.
 *
 * Cancels any previously scheduled idle callback so that rapid arrow-key
 * navigation only fires API calls for the LAST image, preventing a 429
 * rate-limit storm.
 */

let _pendingIdleHandle: number | ReturnType<typeof setTimeout> | null = null;
let _pendingSecondaryIdleHandle: number | ReturnType<typeof setTimeout> | null = null;

function _clearPendingDeferred(): void {
  if (_pendingIdleHandle !== null) {
    if (typeof cancelIdleCallback === 'function' && typeof _pendingIdleHandle === 'number') {
      cancelIdleCallback(_pendingIdleHandle as number);
    } else {
      clearTimeout(_pendingIdleHandle as ReturnType<typeof setTimeout>);
    }
    _pendingIdleHandle = null;
  }
  if (_pendingSecondaryIdleHandle !== null) {
    if (typeof cancelIdleCallback === 'function' && typeof _pendingSecondaryIdleHandle === 'number') {
      cancelIdleCallback(_pendingSecondaryIdleHandle as number);
    } else {
      clearTimeout(_pendingSecondaryIdleHandle as ReturnType<typeof setTimeout>);
    }
    _pendingSecondaryIdleHandle = null;
  }
}

function _scheduleIdle(task: () => void, timeout: number): number | ReturnType<typeof setTimeout> {
  if (typeof requestIdleCallback === 'function') {
    return requestIdleCallback(task, { timeout });
  }
  return setTimeout(task, 16);
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
export function deferredInit(data: any, id: number, loadSeq: number, currentState: typeof runtimeState): void {
  // Cancel previous pending deferred init (user navigated before it ran)
  _clearPendingDeferred();

  const run = () => {
    _pendingIdleHandle = null;
    if (currentState.detailLoadSeq !== loadSeq) return;
    initModalTabs();
    getDetailModalRuntimeHooks().updateModalNavButtons();
    interactionsFocusBestInModal();
    getAppApi().updateKeyboardGuideVisibility();
    detailModalRuntimeControls.initFilmstripHover();
    initToolbarCollapse();
    initDragToShare();
    _pendingSecondaryIdleHandle = _scheduleIdle(() => {
      _pendingSecondaryIdleHandle = null;
      if (currentState.detailLoadSeq !== loadSeq) return;
      // buildModalInfoHtml returns server-derived metadata rendered as
      // escaped HTML (no user-authored raw HTML); this is existing code
      // being reorganised, not a new innerHTML sink.
      const info = document.querySelector<HTMLElement>('.modal-info');
      if (info && info.dataset.infoReady !== '1') {
        info.innerHTML = buildModalInfoHtml(data);
        info.dataset.infoReady = '1';
      }
      renderCharacterPromptsForData(data);
      renderCharacterGridForData(data);
      // Inject the Sweep card only when the file is flagged as having sweep XMP,
      // avoiding 404 noise for the vast majority of non-sweep files.
      if (data.has_sweep) loadSweepCard(id);
      // Initialize recipe share section after info HTML is ready.
      void import('../../recipe_share').then(async ({
        fetchRecipeById,
        buildA1111Text,
        buildCompatQR,
        buildAppQR,
        downloadRecipeCSV,
        downloadRecipeJSON,
        openImportModal,
        openSealRecipeModal,
      }) => {
        const placeholder = document.getElementById(`recipeSectionPlaceholder-${id}`);
        if (!placeholder || currentState.detailLoadSeq !== loadSeq) return;

        const recipe = await fetchRecipeById(id);
        if (!recipe || currentState.detailLoadSeq !== loadSeq) return;

        placeholder.innerHTML = `
          <div class="meta-section recipe-share-section">
            <div class="meta-section-title">📋 レシピ共有</div>
            <div class="recipe-share-body">
              <div class="recipe-qr-col">
                <canvas id="recipeCompatQR-${id}" width="200" height="200" style="max-width:100%"></canvas>
                <div class="recipe-qr-label">🌐 互換 QR</div>
              </div>
              <div class="recipe-info-col">
                <div class="recipe-info-row" id="recipeModelLabel-${id}"></div>
                <div class="recipe-info-row" id="recipeSeedLabel-${id}"></div>
                <div class="recipe-info-row" id="recipeStepsLabel-${id}"></div>
                <div class="recipe-btns">
                  <button class="btn-small recipe-btn" id="recipeBtnCopy-${id}">📋 コピー</button>
                  <button class="btn-small recipe-btn" id="recipeBtnCSV-${id}">📄 CSV</button>
                  <button class="btn-small recipe-btn" id="recipeBtnJSON-${id}">📦 JSON</button>
                  <button class="btn-small recipe-btn recipe-btn-accent" id="recipeBtnAppQR-${id}">📱 App QR</button>
                  <button class="btn-small recipe-btn recipe-btn-import" id="recipeBtnImport-${id}">▶ 生成</button>
                  <button class="btn-small recipe-btn" id="recipeBtnSeal-${id}">🔐 封印送信</button>
                </div>
                <div class="recipe-disclaimer">※ ハードウェア差により完全一致しない場合があります</div>
              </div>
            </div>
          </div>
        `;

        const modelEl = document.getElementById(`recipeModelLabel-${id}`);
        if (modelEl && recipe.model) modelEl.textContent = `Model: ${recipe.model}`;
        const seedEl = document.getElementById(`recipeSeedLabel-${id}`);
        if (seedEl && recipe.seed != null) seedEl.textContent = `Seed: ${recipe.seed}`;
        const stepsEl = document.getElementById(`recipeStepsLabel-${id}`);
        if (stepsEl && recipe.steps != null) stepsEl.textContent = `Steps: ${recipe.steps}${recipe.cfg != null ? ` · CFG: ${recipe.cfg}` : ''}`;

        const compatCanvas = document.getElementById(`recipeCompatQR-${id}`) as HTMLCanvasElement | null;
        if (compatCanvas) void buildCompatQR(buildA1111Text(recipe), compatCanvas);

        document.getElementById(`recipeBtnCopy-${id}`)?.addEventListener('click', async () => {
          await copyToClipboard(buildA1111Text(recipe));
          window.showToast?.('パラメータをコピーしました');
        });
        document.getElementById(`recipeBtnCSV-${id}`)?.addEventListener('click', () => void downloadRecipeCSV(id));
        document.getElementById(`recipeBtnJSON-${id}`)?.addEventListener('click', () => void downloadRecipeJSON(id));
        document.getElementById(`recipeBtnImport-${id}`)?.addEventListener('click', () => void openImportModal(recipe));
        document.getElementById(`recipeBtnSeal-${id}`)?.addEventListener('click', () => void openSealRecipeModal(recipe));
        document.getElementById(`recipeBtnAppQR-${id}`)?.addEventListener('click', async () => {
          const canvas = document.createElement('canvas');
          const result = await buildAppQR(recipe, canvas);
          if (!result.ok && result.oversized) {
            const { customConfirm } = await import('../../shared/dialog');
            if (await customConfirm('QRに収まりません。JSONとして保存しますか？')) {
              await downloadRecipeJSON(id);
            }
            return;
          }

          const overlay = document.createElement('div');
          overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,.6);z-index:9999;display:flex;align-items:center;justify-content:center';
          const box = document.createElement('div');
          box.style.cssText = 'background:#1e1e2e;border-radius:8px;padding:16px;text-align:center';
          const label = document.createElement('div');
          label.style.cssText = 'color:#89b4fa;font-size:11px;margin-bottom:8px;font-weight:bold';
          label.textContent = '📱 App QR（アプリ専用）';
          box.appendChild(label);
          box.appendChild(canvas);
          const closeBtn = document.createElement('button');
          closeBtn.textContent = '閉じる';
          closeBtn.style.cssText = 'margin-top:10px;padding:5px 14px;background:#45475a;color:#cdd6f4;border:none;border-radius:4px;cursor:pointer;display:block;width:100%';
          closeBtn.onclick = () => overlay.remove();
          box.appendChild(closeBtn);
          overlay.appendChild(box);
          overlay.addEventListener('click', (e) => { if (e.target === overlay) overlay.remove(); });
          document.body.appendChild(overlay);
        });
      }).catch(() => {
        // fetchRecipeById returned null or threw — recipe section stays hidden.
      });

      // Auxiliary tab init: deferred until the tab is actually selected.
      // This avoids blocking the initial modal open with API calls for
      // AI analysis / OCR / S2T / character-grid that are never used
      // unless the user clicks the corresponding tab.
      let _auxTabsInitDone = false;
      const _initAuxTabs = (): void => {
        if (_auxTabsInitDone) return;
        if (currentState.detailLoadSeq !== loadSeq) return;
        _auxTabsInitDone = true;
        const runtimeToolsApi = getRuntimeToolsApi();
        const detailModalApi = getDetailModalApi();
        void runtimeToolsApi.loadSavedAnalysis(id);
        void runtimeToolsApi.loadWdTags(id);
        detailModalApi.initOcrTab?.(id);
        detailModalApi.initS2tTab?.(id);
        detailModalApi.initAnnotationsTab?.(id);
        void detailModalApi.initAnalysisTraceTab?.(id);
      };
      initModalTabs();
      // If a non-info tab is already active (persisted preference),
      // init immediately; otherwise wait for tab switch.
      const activeTab = localStorage.getItem('modalActiveTab') || 'info';
      if (activeTab !== 'info') {
        _initAuxTabs();
      } else {
        onTabActivated((tab) => {
          if (tab !== 'info') _initAuxTabs();
        });
      }
    }, 700);
  };
  _pendingIdleHandle = _scheduleIdle(run, 200);
}

export function syncDetailViewerScope(id: number, currentState: typeof runtimeState): void {
  ui()?.setFocus?.('asset', id);
  ui()?.openViewer?.(currentState.viewerScope, id);
}
