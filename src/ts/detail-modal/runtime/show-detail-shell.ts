import { suppressViewTransitionRejections } from '../../shared/view-transition';
import { getAppApi } from '../../shared/browser-apis';
import { icon } from '../../shared/icon';

function buildOptimisticShell(id: number): string {
  const { apiUrl, escapeHtml } = getAppApi();
  const closeLabel = escapeHtml(window.tr?.('detail.modal.close') || 'Close');
  const VIEWING_MODE_LABEL = escapeHtml(window.tr?.('detail.modal.viewing_mode') || 'Viewing mode (V)');
  const imageAlt = escapeHtml(window.tr?.('detail.image_alt') || 'Image');
  const isImmersive = localStorage.getItem('immersiveMode') === '1';
  const infoStyle = !isImmersive && localStorage.getItem('modalInfoHidden') === '1'
    ? ' style="display:none"'
    : '';
  return `
    <div class="modal-image-container modal-image-container--loading" id="modalImageContainer" style="position:relative;">
      <button class="modal-close" type="button" data-action-scope="detail-modal" data-action="closeModal" aria-label="${closeLabel}">${icon('x')}</button>
      <button type="button" class="modal-viewing-toggle" id="modalViewingToggle"
        data-action-scope="detail-modal" data-action="toggleImmersiveMode"
        aria-pressed="${isImmersive ? 'true' : 'false'}"
        title="${VIEWING_MODE_LABEL}" aria-label="${VIEWING_MODE_LABEL}">🖼</button>
      <div class="modal-viewer" id="modalViewer">
        <div class="modal-image-stage" id="modalImageStage">
          <img class="modal-image fit" id="modalImage" src="${apiUrl(`/api/thumbnail/${id}`)}" alt="${imageAlt}" style="filter:blur(2px);transition:filter .3s ease">
        </div>
      </div>
    </div>
    <div class="modal-info" data-info-ready="0"${infoStyle}>
      <div class="modal-info-loading"></div>
    </div>
  `;
}

function applyStoredShellMode(modal: HTMLElement): void {
  modal.classList.toggle('immersive', localStorage.getItem('immersiveMode') === '1');
}

function bindOptimisticShellEvents(content: HTMLElement): void {
  const image = content.querySelector<HTMLImageElement>('#modalImage');
  if (!image) return;
  const markLoaded = (): void => {
    image.dataset.loaded = '1';
    image.style.filter = '';
  };
  if (image.complete && image.naturalWidth > 0) {
    markLoaded();
    return;
  }
  image.addEventListener('load', markLoaded, { once: true });
  image.addEventListener('error', () => {
    image.style.filter = '';
  }, { once: true });
}

export async function openModalShell(
  modal: HTMLElement,
  content: HTMLElement,
  id: number,
  wasActive: boolean,
  onShellOpened?: () => void,
): Promise<void> {
  const optimisticHtml = buildOptimisticShell(id);
  if (!wasActive) {
    const openModal = () => {
      content.innerHTML = optimisticHtml;
      applyStoredShellMode(modal);
      bindOptimisticShellEvents(content);
      modal.classList.add('active');
      modal.setAttribute('role', 'dialog');
      modal.setAttribute('aria-modal', 'true');
      onShellOpened?.();
    };
    if (document.startViewTransition && !document.hidden) {
      try {
        const transition = suppressViewTransitionRejections(document.startViewTransition(openModal));
        await transition.updateCallbackDone;
      } catch {
        openModal();
      }
      return;
    }
    openModal();
    return;
  }

  content.classList.add('transitioning');
  content.innerHTML = optimisticHtml;
  applyStoredShellMode(modal);
  bindOptimisticShellEvents(content);
  onShellOpened?.();
  await new Promise((resolve) => requestAnimationFrame(resolve));
  content.classList.remove('transitioning');
}
