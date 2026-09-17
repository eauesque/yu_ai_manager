/**
 * folder-tree-model.ts — Types, shared state, and tree construction
 * for the folder tree panel.
 */

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface FolderNode {
  name: string;
  fullPath: string;
  fileCount: number;
  children: Map<string, FolderNode>;
}

export interface GroupEntry {
  ids: number[];
  label: string;
}

export interface GroupsIndex {
  folders: Record<string, GroupEntry>;
  zips?: Record<string, GroupEntry>;
}

// ---------------------------------------------------------------------------
// Shared state (mutable, accessed by folder-tree.ts and folder-tree-render.ts)
// ---------------------------------------------------------------------------

export const ftState = {
  root: null as FolderNode | null,
  expanded: {} as Record<string, boolean>,
  selectedPath: null as string | null,
  filterText: '',
  loaded: false,
  folderCountTotal: 0,

  // DOM refs
  treeEl: null as HTMLElement | null,
  filterInput: null as HTMLInputElement | null,
  countEl: null as HTMLElement | null,
};

export const STORAGE_KEY_EXPANDED = 'ft_expanded';
export const STORAGE_KEY_SELECTED = 'ft_selected';

// ---------------------------------------------------------------------------
// Tree construction from groups-index
// ---------------------------------------------------------------------------

function _makeNode(name: string, fullPath: string): FolderNode {
  return { name, fullPath, fileCount: 0, children: new Map() };
}

/**
 * Build a hierarchical tree from the flat groups-index folders dict.
 * Keys are "folder:c:/path/to/dir" — we strip "folder:" prefix and
 * split on "/" to create the hierarchy.
 */
export function buildTree(groupsIndex: GroupsIndex): FolderNode {
  const root = _makeNode('', '');
  const folders = groupsIndex.folders || {};

  for (const [key, entry] of Object.entries(folders)) {
    // Strip "folder:" prefix
    const rawPath = key.startsWith('folder:') ? key.slice(7) : key;
    const segments = rawPath.split('/').filter(Boolean);

    let current = root;
    let builtPath = '';

    for (let i = 0; i < segments.length; i++) {
      const seg = segments[i];
      builtPath = builtPath ? builtPath + '/' + seg : seg;

      if (!current.children.has(seg)) {
        current.children.set(seg, _makeNode(seg, builtPath));
      }
      current = current.children.get(seg)!;
    }

    // Leaf node gets file count from ids
    current.fileCount = entry.ids.length;
  }

  // Add ZIP member counts to their parent folders
  const zips = groupsIndex.zips || {};
  for (const [key, entry] of Object.entries(zips)) {
    const zipPath = key.startsWith('zip:') ? key.slice(4) : key.startsWith('archive:') ? key.slice(8) : key;
    // Parent folder of the ZIP container
    const norm = zipPath.replace(/\\/g, '/');
    const lastSlash = norm.lastIndexOf('/');
    if (lastSlash <= 0) continue; // root-level ZIP, skip
    const parentDir = norm.slice(0, lastSlash);
    const segments = parentDir.split('/').filter(Boolean);

    let current = root;
    let builtPath = '';
    for (const seg of segments) {
      builtPath = builtPath ? builtPath + '/' + seg : seg;
      if (!current.children.has(seg)) {
        current.children.set(seg, _makeNode(seg, builtPath));
      }
      current = current.children.get(seg)!;
    }
    current.fileCount += entry.ids.length;
  }

  // Aggregate file counts up the tree
  _aggregateCounts(root);

  return root;
}

function _aggregateCounts(node: FolderNode): number {
  if (node.children.size === 0) return node.fileCount;

  let childSum = 0;
  for (const child of node.children.values()) {
    childSum += _aggregateCounts(child);
  }
  // Keep own direct count, add children
  node.fileCount = node.fileCount + childSum;
  return node.fileCount;
}
