/**
 * sse-sync.ts -- SSE-driven sidebar auto-sync.
 *
 * Listens for scan_roots_changed and scan.complete events via the
 * shared SSE module to refresh the folder tree and collections sidebar.
 */

import { sseSubscribe } from '../sse';

function memoImport<T>(loader: () => Promise<T>): () => Promise<T> {
  let promise: Promise<T> | null = null;
  return () => (promise ??= loader());
}

const _loadFolderTree = memoImport(() => import('./folder-tree'));
const _loadCollectionsSidebar = memoImport(() => import('./collections-sidebar'));

function onScanRootsChanged(): void {
  void _loadFolderTree().then((mod) => mod.refreshFolderTree()).catch(() => {});
  void _loadCollectionsSidebar().then((mod) => mod.loadSidebarCollections()).catch(() => {});
}

function onScanComplete(): void {
  void _loadFolderTree().then((mod) => mod.refreshFolderTree()).catch(() => {});
}

export function initSseSync(): void {
  sseSubscribe('config.scan_roots_changed', onScanRootsChanged);
  sseSubscribe('scan.complete', onScanComplete);
}
