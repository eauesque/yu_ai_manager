/**
 * Bridge Wildcard Browser — tree panel UI for browsing and inserting wildcards.
 */

import { BridgeWildcardCache } from './wildcard-cache';

export interface WildcardBrowserConfig {
  container: HTMLElement;
  onInsert?: (name: string) => void;
}

export interface WildcardBrowserInstance {
  refresh: () => void;
  show: () => void;
  hide: () => void;
  isVisible: () => boolean;
}

let _styleInjected = false;

function _injectStyle(): void {
  if (_styleInjected) return;
  _styleInjected = true;
  const css = [
    '.bwc-panel { padding:8px; max-height:300px; overflow-y:auto; ',
    '  border:1px solid rgba(128,128,128,0.3); border-radius:6px; ',
    '  background:rgba(20,20,40,0.9); margin-bottom:8px; }',
    '.bwc-empty { color:#888; font-size:12px; padding:8px; }',
    '.bwc-item { display:flex; align-items:center; gap:6px; ',
    '  padding:4px 8px; border-radius:4px; cursor:pointer; ',
    '  font-size:13px; }',
    '.bwc-item:hover { background:rgba(102,126,234,0.12); }',
    '.bwc-item-name { color:#7cc; flex:1; overflow:hidden; ',
    '  text-overflow:ellipsis; white-space:nowrap; font-family:monospace; }',
    '.bwc-item-count { color:#888; font-size:11px; white-space:nowrap; }',
    '.bwc-dir-toggle { display:flex; align-items:center; gap:4px; ',
    '  padding:4px 8px; cursor:pointer; font-size:13px; color:#ccc; ',
    '  user-select:none; }',
    '.bwc-dir-toggle:hover { background:rgba(102,126,234,0.08); border-radius:4px; }',
    '.bwc-dir-arrow { display:inline-block; transition:transform 0.15s; ',
    '  font-size:10px; width:12px; text-align:center; }',
    '.bwc-dir-arrow.open { transform:rotate(90deg); }',
    '.bwc-dir-children { padding-left:16px; }',
    '.bwc-dir-children.collapsed { display:none; }',
    '.bwc-dir-count { color:#666; font-size:11px; }',
  ].join('\n');
  const el = document.createElement('style');
  el.textContent = css;
  document.head.appendChild(el);
}

function create(opts: WildcardBrowserConfig): WildcardBrowserInstance {
  _injectStyle();
  const container = opts.container;
  const onInsert = opts.onInsert || (() => {});
  const dirOpen: Record<string, boolean> = {};

  function _renderEmpty(msg: string, linkText?: string, linkHref?: string): void {
    container.textContent = '';
    const div = document.createElement('div');
    div.className = 'bwc-empty';
    div.textContent = msg;
    if (linkText && linkHref) {
      const a = document.createElement('a');
      a.href = linkHref;
      a.target = '_blank';
      a.style.cssText = 'color:#7cc;margin-left:4px;';
      a.textContent = linkText;
      div.appendChild(a);
    }
    container.appendChild(div);
  }

  function _render(): void {
    const names = BridgeWildcardCache.getNames();
    const data = BridgeWildcardCache.getData();
    if (names.length === 0) {
      const dirsConfigured = BridgeWildcardCache.isDirsConfigured();
      if (dirsConfigured === false) {
        _renderEmpty(
          'ワイルドカードディレクトリが未設定です。',
          'Prompt Simulator 設定を開く',
          '/ext/prompt-sim/manager',
        );
      } else {
        _renderEmpty('ワイルドカードファイルが見つかりません。');
      }
      return;
    }
    const topLevel: string[] = [];
    const dirs: Record<string, string[]> = {};
    names.forEach((name) => {
      const slash = name.indexOf('/');
      if (slash === -1) {
        topLevel.push(name);
      } else {
        const dir = name.substring(0, slash);
        if (!dirs[dir]) dirs[dir] = [];
        dirs[dir].push(name);
      }
    });
    container.textContent = '';

    function renderItem(parent: HTMLElement, name: string, displayName: string): void {
      const count = data[name] ? data[name].length : 0;
      const item = document.createElement('div');
      item.className = 'bwc-item';
      item.dataset.wcName = name;
      const itemName = document.createElement('span');
      itemName.className = 'bwc-item-name';
      itemName.textContent = `__${displayName}__`;
      const itemCount = document.createElement('span');
      itemCount.className = 'bwc-item-count';
      itemCount.textContent = String(count);
      item.appendChild(itemName);
      item.appendChild(itemCount);
      item.addEventListener('click', () => onInsert(name));
      parent.appendChild(item);
    }

    topLevel.forEach((name) => renderItem(container, name, name));
    Object.keys(dirs)
      .sort()
      .forEach((dir) => {
        const open = dirOpen[dir] === true;
        const toggle = document.createElement('div');
        toggle.className = 'bwc-dir-toggle';
        toggle.dataset.wcDir = dir;
        const arrow = document.createElement('span');
        arrow.className = 'bwc-dir-arrow' + (open ? ' open' : '');
        arrow.innerHTML = '&#9654;';
        const count = document.createElement('span');
        count.className = 'bwc-dir-count';
        count.textContent = `(${dirs[dir].length})`;
        toggle.appendChild(arrow);
        toggle.appendChild(document.createTextNode(` ${dir} `));
        toggle.appendChild(count);
        toggle.addEventListener('click', () => {
          dirOpen[dir] = !dirOpen[dir];
          _render();
        });
        container.appendChild(toggle);

        const children = document.createElement('div');
        children.className = 'bwc-dir-children' + (open ? '' : ' collapsed');
        dirs[dir].forEach((name) => {
          renderItem(children, name, name.substring(dir.length + 1));
        });
        container.appendChild(children);
      });
  }

  function refresh(): void {
    BridgeWildcardCache.fetch().then(() => _render());
  }

  function show(): void {
    container.style.display = '';
    refresh();
  }

  function hide(): void {
    container.style.display = 'none';
  }

  function isVisible(): boolean {
    return container.style.display !== 'none';
  }

  return { refresh, show, hide, isVisible };
}

export const BridgeWildcardBrowser = { create };
