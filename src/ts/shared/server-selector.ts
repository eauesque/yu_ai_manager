/**
 * Dropdown server selector for Bridge send UI.
 * Always shows Default option. Groups (lightning) and Individual servers follow.
 * Stopped-only groups and stopped individual backends are disabled.
 */
import type { BackendEntry, GroupEntry, SendTarget } from './bridge-server'
import { fetchBackends, fetchGroups } from './bridge-server'
import { showToast } from './toast'

export async function showServerSelector(
  anchorEl: HTMLElement,
  bridgeType: 'comfyui' | 'sd_webui',
  onSelect: (target: SendTarget) => void,
  onDismiss?: () => void,
): Promise<void> {
  const [beResult, grResult] = await Promise.all([fetchBackends(), fetchGroups()])

  if (!beResult.ok || !grResult.ok) {
    const error = !beResult.ok ? beResult.error : !grResult.ok ? grResult.error : 'unknown'
    showToast(`Failed to load servers: ${error}`, true)
    return
  }

  const backends = beResult.data.filter(b => b.type === bridgeType)
  const groups = grResult.data

  _removeExisting()
  const menu = _buildMenu(backends, groups, onSelect)
  document.body.appendChild(menu)
  _positionMenu(menu, anchorEl)

  const dismiss = (e: MouseEvent) => {
    if (!menu.contains(e.target as Node)) {
      menu.remove()
      document.removeEventListener('click', dismiss)
      onDismiss?.()
    }
  }
  requestAnimationFrame(() => document.addEventListener('click', dismiss))
}

function _buildMenu(
  backends: BackendEntry[],
  groups: GroupEntry[],
  onSelect: (t: SendTarget) => void,
): HTMLElement {
  const menu = document.createElement('div')
  menu.className = 'bridge-server-dropdown'
  menu.setAttribute('role', 'listbox')

  // Default option (always visible)
  menu.appendChild(_item(
    'Default (gateway default / fallback)',
    false,
    () => { onSelect({ kind: 'default' }); menu.remove() },
  ))

  // Groups
  if (groups.length > 0) {
    menu.appendChild(_section('Groups'))
    for (const g of groups) {
      const members = g.backend_ids.map(id => backends.find(b => b.id === id)).filter(Boolean) as BackendEntry[]
      const active = members.filter(b => b.status === 'running' || b.status === 'unknown')
      menu.appendChild(_item(
        `${g.name} (${members.length})`,
        active.length === 0,
        () => { onSelect({ kind: 'group', group_id: g.id }); menu.remove() },
      ))
    }
  }

  // Individual backends
  if (backends.length > 0) {
    menu.appendChild(_section('Servers'))
    for (const b of backends) {
      const disabled = b.status === 'stopped'
      const dot = b.status === 'running' ? 'running' : b.status === 'stopped' ? 'stopped' : 'unknown'
      menu.appendChild(_item(
        `${b.name} [${dot}]`,
        disabled,
        () => { onSelect({ kind: 'server', backend_id: b.id }); menu.remove() },
      ))
    }
  }

  return menu
}

function _item(label: string, disabled: boolean, onClick: () => void): HTMLElement {
  const btn = document.createElement('button')
  btn.className = 'bridge-server-item' + (disabled ? ' disabled' : '')
  btn.setAttribute('role', 'option')
  btn.disabled = disabled
  btn.textContent = label
  if (!disabled) btn.addEventListener('click', onClick)
  return btn
}

function _section(text: string): HTMLElement {
  const div = document.createElement('div')
  div.className = 'bridge-server-section'
  div.textContent = text
  return div
}

function _positionMenu(menu: HTMLElement, anchor: HTMLElement): void {
  const r = anchor.getBoundingClientRect()
  menu.style.cssText = `position:fixed;top:${r.bottom + 4}px;left:${r.left}px;z-index:9999`
}

function _removeExisting(): void {
  document.querySelector('.bridge-server-dropdown')?.remove()
}
