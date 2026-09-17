/**
 * context-menu/context-menu.ts — DOM generation, positioning, submenu, keyboard nav.
 */

import { buildMenuItems, type CardData, type MenuEntry, type MenuItem } from './context-menu-build';

declare const window: Window & {
  tr: (key: string, fallback?: string) => string;
};

let _menuEl: HTMLElement | null = null;
let _subMenuEl: HTMLElement | null = null;
let _focusIndex = -1;

function _tr(key: string, fb: string): string {
  return typeof window.tr === 'function' ? window.tr(key, fb) : fb;
}

function _createMenuElement(items: MenuEntry[]): HTMLElement {
  const menu = document.createElement('div');
  menu.className = 'ctx-menu';
  menu.setAttribute('role', 'menu');

  items.forEach((item, idx) => {
    if (item.separator) {
      const sep = document.createElement('div');
      sep.className = 'ctx-menu-sep';
      sep.setAttribute('role', 'separator');
      menu.appendChild(sep);
      return;
    }

    const el = document.createElement('div');
    el.className = 'ctx-menu-item';
    el.setAttribute('role', 'menuitem');
    el.setAttribute('tabindex', '-1');
    el.dataset.index = String(idx);
    el.textContent = item.label;

    if (item.submenu) {
      el.classList.add('has-submenu');
      const arrow = document.createElement('span');
      arrow.className = 'ctx-submenu-arrow';
      arrow.textContent = '\u25B8';
      el.appendChild(arrow);

      el.addEventListener('mouseenter', () => {
        _showSubmenu(el, item.submenu!);
      });
    } else {
      el.addEventListener('mouseenter', () => {
        _closeSubmenu();
      });
    }

    if (item.action) {
      el.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        close();
        item.action!(null as unknown as CardData);
      });
    }

    menu.appendChild(el);
  });

  return menu;
}

function _showSubmenu(anchorEl: HTMLElement, items: MenuItem[]): void {
  _closeSubmenu();

  const sub = document.createElement('div');
  sub.className = 'ctx-menu ctx-submenu';
  sub.setAttribute('role', 'menu');

  items.forEach((item) => {
    if (item.separator) {
      const sep = document.createElement('div');
      sep.className = 'ctx-menu-sep';
      sub.appendChild(sep);
      return;
    }
    const el = document.createElement('div');
    el.className = 'ctx-menu-item';
    el.setAttribute('role', 'menuitem');
    el.textContent = item.label;
    if (item.action) {
      el.addEventListener('click', (e: MouseEvent) => {
        e.stopPropagation();
        close();
        item.action!(null as unknown as CardData);
      });
    }
    sub.appendChild(el);
  });

  document.body.appendChild(sub);
  _subMenuEl = sub;

  // Position submenu to the right of the anchor
  const rect = anchorEl.getBoundingClientRect();
  const subW = 180;
  const rightSpace = window.innerWidth - rect.right;
  if (rightSpace >= subW) {
    sub.style.left = rect.right + 'px';
  } else {
    sub.style.left = (rect.left - subW) + 'px';
  }
  sub.style.top = rect.top + 'px';

  // Clamp vertical overflow
  const subRect = sub.getBoundingClientRect();
  if (subRect.bottom > window.innerHeight) {
    sub.style.top = Math.max(4, window.innerHeight - subRect.height - 4) + 'px';
  }
}

function _closeSubmenu(): void {
  if (_subMenuEl) {
    _subMenuEl.remove();
    _subMenuEl = null;
  }
}

export function show(e: MouseEvent, data: CardData): void {
  close();

  const items = buildMenuItems(data, _tr);
  const menu = _createMenuElement(items);
  document.body.appendChild(menu);
  _menuEl = menu;
  _focusIndex = -1;

  // Position with viewport clamping
  const menuRect = menu.getBoundingClientRect();
  let x = e.clientX;
  let y = e.clientY;

  if (x + menuRect.width > window.innerWidth - 4) {
    x = window.innerWidth - menuRect.width - 4;
  }
  if (y + menuRect.height > window.innerHeight - 4) {
    y = window.innerHeight - menuRect.height - 4;
  }
  x = Math.max(4, x);
  y = Math.max(4, y);

  menu.style.left = x + 'px';
  menu.style.top = y + 'px';

  // Listeners
  requestAnimationFrame(() => {
    document.addEventListener('click', _onDocClick);
    document.addEventListener('keydown', _onDocKeydown);
    document.addEventListener('contextmenu', _onDocContext);
  });
}

export function close(): void {
  _closeSubmenu();
  if (_menuEl) {
    _menuEl.remove();
    _menuEl = null;
  }
  _focusIndex = -1;
  document.removeEventListener('click', _onDocClick);
  document.removeEventListener('keydown', _onDocKeydown);
  document.removeEventListener('contextmenu', _onDocContext);
}

function _onDocClick(): void {
  close();
}

function _onDocContext(e: MouseEvent): void {
  // Close menu on another right-click outside
  if (_menuEl && !_menuEl.contains(e.target as Node)) {
    close();
  }
}

function _onDocKeydown(e: KeyboardEvent): void {
  if (!_menuEl) return;

  const items = _menuEl.querySelectorAll<HTMLElement>('.ctx-menu-item');
  if (items.length === 0) return;

  if (e.key === 'Escape') {
    e.preventDefault();
    close();
    return;
  }

  if (e.key === 'ArrowDown') {
    e.preventDefault();
    _focusIndex = (_focusIndex + 1) % items.length;
    items[_focusIndex].focus();
    return;
  }

  if (e.key === 'ArrowUp') {
    e.preventDefault();
    _focusIndex = (_focusIndex - 1 + items.length) % items.length;
    items[_focusIndex].focus();
    return;
  }

  if (e.key === 'Enter' && _focusIndex >= 0) {
    e.preventDefault();
    items[_focusIndex].click();
    return;
  }
}
