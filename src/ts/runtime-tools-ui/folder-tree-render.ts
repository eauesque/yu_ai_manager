/**
 * folder-tree-render.ts — HTML generation and filter matching
 * for the folder tree panel.
 */

import { FolderNode, ftState } from './folder-tree-model';

// ---------------------------------------------------------------------------
// Rendering
// ---------------------------------------------------------------------------

export function renderTree(): void {
  if (!ftState.treeEl || !ftState.root) return;

  const html: string[] = [];
  let visibleFolders = 0;

  const filter = ftState.filterText.toLowerCase();

  // "/ (All)" root item — clears folder selection
  if (!filter) {
    const allActive = ftState.selectedPath === null ? ' active' : '';
    html.push(
      '<div class="ft-node ft-all-node' + allActive + '" data-path="">',
      '<span class="ft-toggle"></span>',
      '<span class="ft-name">/ (All)</span>',
      '<span class="ft-count">' + ftState.root.fileCount + '</span>',
      '</div>',
    );
  }

  // Render children of root (root itself is virtual)
  for (const child of _sortedChildren(ftState.root)) {
    visibleFolders += _renderNode(child, html, filter, 0);
  }

  ftState.treeEl.innerHTML = html.join('');
  if (ftState.countEl) ftState.countEl.textContent = String(visibleFolders);
}

function _sortedChildren(node: FolderNode): FolderNode[] {
  return Array.from(node.children.values()).sort((a, b) =>
    a.name.localeCompare(b.name, undefined, { numeric: true, sensitivity: 'base' }),
  );
}

/**
 * Check if a node or any of its descendants match the filter text.
 */
function _matchesFilter(node: FolderNode, filter: string): boolean {
  if (!filter) return true;
  if (node.name.toLowerCase().includes(filter)) return true;
  for (const child of node.children.values()) {
    if (_matchesFilter(child, filter)) return true;
  }
  return false;
}

function _renderNode(node: FolderNode, html: string[], filter: string, depth: number): number {
  if (!_matchesFilter(node, filter)) return 0;

  const hasChildren = node.children.size > 0;
  const isExpanded = ftState.expanded[node.fullPath] ?? (depth < 1 && !filter);
  const isActive = ftState.selectedPath === node.fullPath;
  const activeCls = isActive ? ' active' : '';

  html.push('<div class="ft-node-wrap">');

  // Node row
  html.push(
    '<div class="ft-node' + activeCls + '" data-path="' + _escAttr(node.fullPath) + '">',
  );

  // Toggle arrow
  if (hasChildren) {
    html.push(
      '<span class="ft-toggle" data-action="toggle" data-path="' +
        _escAttr(node.fullPath) +
        '"><span class="ft-arrow' +
        (isExpanded ? ' open' : '') +
        '">\u25B6</span></span>',
    );
  } else {
    html.push('<span class="ft-toggle"></span>');
  }

  // Name
  html.push('<span class="ft-name">' + _escHtml(node.name) + '</span>');

  // Count
  html.push('<span class="ft-count">' + node.fileCount + '</span>');

  html.push('</div>');

  // Children
  let count = 1;
  if (hasChildren) {
    const collapsedCls = isExpanded ? '' : ' collapsed';
    html.push('<div class="ft-children' + collapsedCls + '" data-parent="' + _escAttr(node.fullPath) + '">');
    for (const child of _sortedChildren(node)) {
      count += _renderNode(child, html, filter, depth + 1);
    }
    html.push('</div>');
  }

  html.push('</div>');

  return count;
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function _escHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

function _escAttr(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/"/g, '&quot;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}
