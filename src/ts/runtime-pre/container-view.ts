/* runtime-pre/container-view.ts — Container view for ZIP/folder navigation */

import { setScopeResultIds, setFocus } from './ui-state';
import { getAppApi, getContainerViewApi, getDetailModalApi } from '../shared/browser-apis';

function _extractDetailFileId(): number | null {
  const modalImage = document.getElementById('modalImage') as HTMLImageElement | null;
  const match = modalImage?.src?.match(/\/api\/(?:thumbnail|original)\/(\d+)/);
  if (match) {
    const id = Number(match[1]);
    if (Number.isFinite(id)) return id;
  }
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const st = (window as any).detailModalRuntimeState?.getState?.();
  if (!st) return null;
  if (st.currentModalIndex >= 0 && Array.isArray(st.currentResultIds)) {
    const id = Number(st.currentResultIds[st.currentModalIndex]);
    if (Number.isFinite(id)) return id;
  }
  return null;
}

export async function openContainerViewForFile(fileId: number): Promise<void> {
  const n = Number(fileId);
  if (!Number.isFinite(n)) return;
  const { apiFetch, tr } = getAppApi();
  const { openContainerViewPanel } = getContainerViewApi();
  const { showDetail } = getDetailModalApi();
  const response = await apiFetch(`/api/container-members/${n}`);
  const data = await response.json();
  if (!response.ok) {
    alert(data?.error || tr('detail.load_failed'));
    return;
  }
  const ids: number[] = Array.isArray(data?.member_ids)
    ? data.member_ids.map((x: unknown) => Number(x)).filter(Number.isFinite)
    : [];
  if (!ids.length) {
    alert(tr('container.no_members', 'Container has no indexed members.'));
    return;
  }
  const focusId = Number(data?.focus_id);
  const entryId = Number.isFinite(focusId) && ids.includes(focusId) ? focusId : ids[0];
  setFocus('container', data?.container_path || null);

  // Prefer ContainerView panel when available
  if (openContainerViewPanel) {
    openContainerViewPanel({
      containerType: 'zip',
      containerKey: 'zip:' + (data?.container_path || ''),
      containerPath: data?.container_path || '',
      memberIds: ids,
      focusFileId: entryId,
    });
    return;
  }

  // Fallback: open modal directly
  setScopeResultIds('container_only', ids);
  if (showDetail) {
    showDetail(entryId, {
      source: 'container',
      scope: 'container_only',
      scopeIds: ids,
      containerMeta: {
        containerPath: data?.container_path || '',
        memberCount: Number(data?.member_count) || ids.length,
        representatives: Array.isArray(data?.representatives) ? data.representatives : [],
      },
    });
  }
}

export async function openContainerViewForCurrentDetail(): Promise<void> {
  const fileId = _extractDetailFileId();
  if (!Number.isFinite(fileId)) return;
  await openContainerViewForFile(fileId!);
}
