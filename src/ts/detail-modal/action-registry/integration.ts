import type { DetailModalActionRegistry, DetailModalActionRegistryDeps } from './types';
import { showCollectionPickerPopover } from '../../runtime-tools-ui/favorites/favorites-popover';
import { getAppApi, getNavApi } from '../../shared/browser-apis';
import {
  sendPromptToBridge as sendPromptToBridgeImpl,
  sendImageToBridge as sendImageToBridgeImpl,
  sendRemixToBridge as sendRemixToBridgeImpl,
} from './bridge-send';
import { toggleOverflowMenu, collapseToolbar } from '../content/toolbar/toolbar-collapse';

export function createDetailModalIntegrationActions(
  deps: Pick<
    DetailModalActionRegistryDeps,
    'openContainerViewForCurrentDetail' | 'openFpbForCurrentImage' | 'toggleCharGridOverlay' | 'toggleFavorite'
  >,
): DetailModalActionRegistry {
  return {
    openContainerViewForCurrentDetail: () => {
      deps.openContainerViewForCurrentDetail();
    },
    openFpbForCurrentImage: () => {
      deps.openFpbForCurrentImage();
    },
    toggleCharGridOverlay: () => {
      deps.toggleCharGridOverlay();
    },
    toggleFavorite: ({ arg }) => {
      deps.toggleFavorite(Number(arg));
    },
    addToCollectionPicker: ({ arg }) => {
      const fileId = Number(arg);
      if (!fileId) return;
      const btn = document.getElementById('modalCollectionBtn');
      if (btn) showCollectionPickerPopover(fileId, btn);
    },

    // Prompt format conversion (replaces inline onclick)
    convertAndCopy: ({ arg, event }) => {
      if (!arg) return;
      const [targetId, mode] = arg.split(':');
      const api = (window as unknown as Record<string, unknown>).runtimeToolsApi as
        { convertAndCopy?: (t: string, m: string, e?: Event) => Promise<void> } | undefined;
      if (api?.convertAndCopy) {
        void api.convertAndCopy(targetId, mode, event);
      }
    },

    // Search by prompt: close modal and fill search bar
    searchByPrompt: ({ arg }) => {
      if (!arg) return;
      try {
        const text = decodeURIComponent(escape(atob(arg)));
        const modal = document.getElementById('modal');
        if (modal) modal.classList.remove('active');
        const tagQuery = document.getElementById('tagQuery') as HTMLInputElement | null;
        if (tagQuery) {
          tagQuery.value = text;
          tagQuery.dispatchEvent(new Event('input', { bubbles: true }));
          const form = document.getElementById('searchForm') as HTMLFormElement | null;
          form?.requestSubmit();
        }
      } catch { /* ignore decode errors */ }
    },

    // Tag editing (replaces inline onclick/onkeydown/oninput)
    addUserTag: ({ arg }) => {
      const fileId = Number(arg);
      const api = (window as unknown as Record<string, unknown>).tagEditApi as
        { addUserTag?: (id: number) => Promise<void> } | undefined;
      if (api?.addUserTag) void api.addUserTag(fileId);
    },
    removeUserTag: ({ arg }) => {
      if (!arg) return;
      const sep = arg.indexOf(':');
      const fileId = Number(arg.substring(0, sep));
      const tag = arg.substring(sep + 1);
      const api = (window as unknown as Record<string, unknown>).tagEditApi as
        { removeUserTag?: (id: number, t: string) => Promise<void> } | undefined;
      if (api?.removeUserTag) void api.removeUserTag(fileId, tag);
    },
    handleTagInputKey: ({ arg, event }) => {
      const fileId = Number(arg);
      const api = (window as unknown as Record<string, unknown>).tagEditApi as
        { handleTagInputKey?: (e: KeyboardEvent, id: number) => void } | undefined;
      if (api?.handleTagInputKey) api.handleTagInputKey(event as KeyboardEvent, fileId);
    },

    // Bridge-send actions
    sendPromptToBridge: ({ arg }) => {
      if (arg) void sendPromptToBridgeImpl(arg as 'nai' | 'sd' | 'comfyui');
    },
    sendImageToBridge: ({ arg }) => {
      if (arg) void sendImageToBridgeImpl(arg as 'nai' | 'sd' | 'comfyui');
    },
    sendRemixToBridge: ({ arg }) => {
      if (arg) void sendRemixToBridgeImpl(arg as 'nai' | 'sd' | 'comfyui');
    },
    toggleModalBridgeMenu: ({ arg }) => {
      if (arg) (window as any).toggleModalBridgeMenu(arg);
    },
    sendWorkflowToComfyUI: () => {
      const currentData = (window as unknown as Record<string, unknown>)
        .__currentDetailModalData as { id?: number } | undefined;
      const fileId = currentData?.id;
      if (!fileId) return;
      void import('../../apps/bridge-workflow-queue').then(({ sendWorkflowToComfyUI }) => {
        sendWorkflowToComfyUI(fileId);
      });
    },

    toggleModalToolbarOverflow: () => {
      toggleOverflowMenu();
    },
    collapseModalToolbar: () => {
      collapseToolbar();
    },
  };
}
