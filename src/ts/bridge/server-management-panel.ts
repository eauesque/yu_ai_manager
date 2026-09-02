/**
 * Inline server/group management panel for the Bridge page.
 * Uses admin-token for mutation operations.
 */
import type { BackendEntry, DefaultsEntry, GroupEntry } from '../shared/bridge-server'
import { fetchBackends, fetchDefaults, fetchGroups } from '../shared/bridge-server'
import { mutationHeaders, invalidateAdminToken, getAdminToken } from '../shared/gateway-auth'
import { showToast } from '../shared/toast'

type LabeledInput = {
  el: HTMLElement
  input: HTMLInputElement
  value: () => string
}

let _styleSheet: CSSStyleSheet | null = null
let _domIdSeq = 0
let _backendColorSeq = 0
const _backendColorClasses = new Map<string, string>()

export function attachServerManagement(containerEl: HTMLElement): void {
  // Pre-fetch admin token so it's cached before any mutation attempt
  void getAdminToken()

  const details = document.createElement('details')
  details.className = 'server-management-section'
  const STORE_KEY = 'bridge_server_mgmt_open'
  details.open = localStorage.getItem(STORE_KEY) === 'true'
  details.addEventListener('toggle', () => localStorage.setItem(STORE_KEY, String(details.open)))

  const summary = document.createElement('summary')
  summary.textContent = 'サーバー管理'
  details.appendChild(summary)

  const body = document.createElement('div')
  body.className = 'server-mgmt-body'
  details.appendChild(body)
  containerEl.appendChild(details)

  void _refresh(body)
}

async function _refresh(body: HTMLElement): Promise<void> {
  const [beRes, grRes, dfRes] = await Promise.all([fetchBackends(), fetchGroups(), fetchDefaults()])
  while (body.firstChild) body.removeChild(body.firstChild)

  if (!beRes.ok || !grRes.ok) {
    body.textContent = 'Failed to load server list'
    return
  }

  const defaults: DefaultsEntry = dfRes.ok
    ? dfRes.data
    : { default_comfy_backend_id: null, default_sd_backend_id: null }

  _renderBackends(body, beRes.data, () => void _refresh(body))
  _renderGroups(body, grRes.data, beRes.data, () => void _refresh(body))
  _renderDefaults(body, beRes.data, defaults, () => void _refresh(body))
}

function _renderBackends(parent: HTMLElement, backends: BackendEntry[], refresh: () => void): void {
  const h = document.createElement('h4')
  h.textContent = 'バックエンド'
  parent.appendChild(h)

  for (const b of backends) {
    const row = document.createElement('div')
    row.className = 'backend-row'
    const dot = document.createElement('span')
    dot.className = `backend-color-dot ${_backendColorClass(b.id, b.color)}`
    row.appendChild(dot)
    row.appendChild(document.createTextNode(b.name + ' (' + b.type + ')'))
    const delBtn = document.createElement('button')
    delBtn.className = 'btn-delete'
    delBtn.textContent = '削除'
    delBtn.addEventListener('click', async () => {
      const msg = `バックエンド「${b.name}」を削除しますか？\nこの操作は元に戻せません。`
      if (!(await window.customConfirm(msg))) return
      const hdr = await mutationHeaders()
      await fetch('/api/gateway/backends/' + b.id, { method: 'DELETE', headers: hdr })
      refresh()
    })
    row.appendChild(delBtn)
    parent.appendChild(row)
  }

  const addBtn = document.createElement('button')
  addBtn.className = 'btn-secondary'
  addBtn.textContent = '+ バックエンド追加'
  addBtn.addEventListener('click', () => _showAddBackendForm(parent, refresh))
  parent.appendChild(addBtn)

  const addOneBtn = document.createElement('button')
  addOneBtn.className = 'btn-tertiary btn-small'
  addOneBtn.textContent = '+ もう1つ追加'
  addOneBtn.title = 'フォームが既に開いている場合にバックエンドをもう1つ追加'
  addOneBtn.addEventListener('click', () => {
    if (!parent.querySelector('.add-backend-form')) _showAddBackendForm(parent, refresh)
  })
  parent.appendChild(addOneBtn)
}

function _showAddBackendForm(parent: HTMLElement, refresh: () => void): void {
  const form = document.createElement('div')
  form.className = 'add-backend-form'
  const typeInput = _labeled('タイプ', 'comfyui')
  const urlInput = _labeled('URL', 'http://127.0.0.1:8188')
  const nameInput = _labeled('名前', '')
  form.append(typeInput.el, urlInput.el, nameInput.el)
  const saveBtn = document.createElement('button')
  saveBtn.className = 'btn-secondary'
  saveBtn.textContent = '保存'
  const updateSaveState = () => {
    saveBtn.disabled = !(typeInput.value() && urlInput.value() && nameInput.value())
  }
  for (const inp of form.querySelectorAll('input')) {
    inp.addEventListener('input', updateSaveState)
  }
  saveBtn.addEventListener('click', async () => {
    if (saveBtn.disabled) return
    const hdr = await mutationHeaders()
    const bodyStr = JSON.stringify({ type: typeInput.value(), base_url: urlInput.value(), name: nameInput.value() })
    const res = await fetch('/api/gateway/backends', { method: 'POST', headers: hdr as HeadersInit, body: bodyStr })
    if (res.ok) { form.remove(); refresh() }
    else { showToast('Error: ' + await _responseErrorMessage(res), true) }
  })
  const cancelBtn = document.createElement('button')
  cancelBtn.className = 'btn-tertiary'
  cancelBtn.textContent = 'キャンセル'
  cancelBtn.addEventListener('click', () => form.remove())
  updateSaveState()
  form.appendChild(saveBtn)
  form.appendChild(cancelBtn)
  parent.appendChild(form)
  _focusInput(nameInput.input)
}

function _labeled(label: string, placeholder: string): LabeledInput {
  const wrap = document.createElement('label')
  wrap.className = 'mgmt-label'
  const input = document.createElement('input')
  const inputId = _domId('mgmt-input')
  input.id = inputId
  input.placeholder = placeholder
  const labelEl = document.createElement('span')
  labelEl.textContent = label + ': '
  wrap.htmlFor = inputId
  wrap.appendChild(labelEl)
  wrap.appendChild(input)
  return { el: wrap, input, value: () => input.value.trim() }
}

function _renderGroups(parent: HTMLElement, groups: GroupEntry[], backends: BackendEntry[], refresh: () => void): void {
  const h = document.createElement('h4')
  h.textContent = 'グループ'
  parent.appendChild(h)

  for (const g of groups) {
    const row = document.createElement('div')
    row.className = 'group-row'
    row.textContent = g.name + ' (' + g.backend_ids.length + ' backends) '
    const delBtn = document.createElement('button')
    delBtn.className = 'btn-delete'
    delBtn.textContent = '削除'
    delBtn.addEventListener('click', async () => {
      const msg = `グループ「${g.name}」を削除しますか？\nこの操作は元に戻せません。`
      if (!(await window.customConfirm(msg))) return
      const hdr = await mutationHeaders()
      await fetch('/api/gateway/groups/' + g.id, { method: 'DELETE', headers: hdr })
      refresh()
    })
    row.appendChild(delBtn)
    parent.appendChild(row)
  }

  const addBtn = document.createElement('button')
  addBtn.className = 'btn-secondary'
  addBtn.textContent = '+ グループ追加'
  addBtn.addEventListener('click', () => _showAddGroupForm(parent, backends, refresh))
  parent.appendChild(addBtn)

  const addOneBtn = document.createElement('button')
  addOneBtn.className = 'btn-tertiary btn-small'
  addOneBtn.textContent = '+ もう1つ追加'
  addOneBtn.title = 'フォームが既に開いている場合にグループをもう1つ追加'
  addOneBtn.addEventListener('click', () => {
    if (!parent.querySelector('.add-group-form')) _showAddGroupForm(parent, backends, refresh)
  })
  parent.appendChild(addOneBtn)
}

function _showAddGroupForm(parent: HTMLElement, backends: BackendEntry[], refresh: () => void): void {
  const form = document.createElement('div')
  form.className = 'add-group-form'
  const nameInput = _labeled('グループ名', '')
  form.appendChild(nameInput.el)
  const checkboxes: Array<{ id: string; el: HTMLInputElement }> = []
  for (const b of backends) {
    const lbl = document.createElement('label')
    lbl.className = 'mgmt-checkbox-label'
    const cb = document.createElement('input')
    cb.type = 'checkbox'
    cb.id = _domId('backend-checkbox')
    cb.value = b.id
    cb.setAttribute('aria-label', `Include ${b.name}`)
    checkboxes.push({ id: b.id, el: cb })
    lbl.htmlFor = cb.id
    lbl.appendChild(cb)
    lbl.appendChild(document.createTextNode(' ' + b.name))
    form.appendChild(lbl)
  }
  const saveBtn = document.createElement('button')
  saveBtn.className = 'btn-secondary'
  saveBtn.textContent = '保存'
  const updateSaveState = () => {
    saveBtn.disabled = !nameInput.value()
  }
  nameInput.input.addEventListener('input', updateSaveState)
  saveBtn.addEventListener('click', async () => {
    if (saveBtn.disabled) return
    const hdr = await mutationHeaders()
    const selected = checkboxes.filter(c => c.el.checked).map(c => c.id)
    const bodyStr = JSON.stringify({ name: nameInput.value(), backend_ids: selected })
    const res = await fetch('/api/gateway/groups', { method: 'POST', headers: hdr as HeadersInit, body: bodyStr })
    if (res.ok) { form.remove(); refresh() }
    else { showToast('Error: ' + await _responseErrorMessage(res), true) }
  })
  const cancelBtn = document.createElement('button')
  cancelBtn.className = 'btn-tertiary'
  cancelBtn.textContent = 'キャンセル'
  cancelBtn.addEventListener('click', () => form.remove())
  updateSaveState()
  form.appendChild(saveBtn)
  form.appendChild(cancelBtn)
  parent.appendChild(form)
  _focusInput(nameInput.input)
}

function _renderDefaults(
  parent: HTMLElement,
  backends: BackendEntry[],
  defaults: DefaultsEntry,
  refresh: () => void,
): void {
  const h = document.createElement('h4')
  h.textContent = 'デフォルトバックエンド'
  parent.appendChild(h)

  const pairs: Array<['default_comfy_backend_id' | 'default_sd_backend_id', string]> = [
    ['default_comfy_backend_id', 'ComfyUI デフォルト'],
    ['default_sd_backend_id', 'SD WebUI デフォルト'],
  ]

  for (const [key, label] of pairs) {
    const btype = key.includes('comfy') ? 'comfyui' : 'sd_webui'
    const wrap = document.createElement('label')
    wrap.className = 'mgmt-label'
    const selectId = `mgmt-select-${key}`
    const labelEl = document.createElement('span')
    labelEl.textContent = label + ': '
    const sel = document.createElement('select')
    sel.id = selectId
    wrap.htmlFor = selectId
    const none = document.createElement('option')
    none.value = ''
    none.textContent = '（なし / フォールバック）'
    sel.appendChild(none)
    for (const b of backends.filter(b => b.type === btype)) {
      const opt = document.createElement('option')
      opt.value = b.id
      opt.textContent = b.name
      sel.appendChild(opt)
    }
    // Reflect current persisted default
    const currentId = defaults[key]
    sel.value = (currentId && backends.some(b => b.id === currentId)) ? currentId : ''
    sel.addEventListener('change', async () => {
      const bodyStr = JSON.stringify({ [key]: sel.value || null })
      let hdr = await mutationHeaders()
      const hasAuth = !!(hdr as Record<string, string>)['Authorization']
      let res = await fetch('/api/gateway/defaults', { method: 'PATCH', headers: hdr as HeadersInit, body: bodyStr })
      if (res.status === 401) {
        // Token may be stale - invalidate and retry once
        invalidateAdminToken()
        hdr = await mutationHeaders()
        const hasAuth2 = !!(hdr as Record<string, string>)['Authorization']
        res = await fetch('/api/gateway/defaults', { method: 'PATCH', headers: hdr as HeadersInit, body: bodyStr })
        if (res.status === 401 && !hasAuth2) {
          showToast('Admin token unavailable — check server logs for admin-token endpoint errors', true)
          return
        }
      }
      if (!res.ok) {
        const detail = hasAuth ? `${res.status}` : `${res.status} (no Authorization sent)`
        showToast('Error saving default: ' + detail, true)
        return
      }
      refresh()
    })
    wrap.append(labelEl, sel)
    parent.appendChild(wrap)
  }
}

async function _responseErrorMessage(res: Response): Promise<string> {
  const fallback = `HTTP ${res.status}`
  const contentType = res.headers.get('content-type') ?? ''
  try {
    if (contentType.includes('application/json')) {
      const json = await res.json() as { detail?: unknown; message?: unknown; error?: unknown }
      return _stringError(json.detail) ?? _stringError(json.message) ?? _stringError(json.error) ?? fallback
    }
    const text = (await res.text()).trim()
    return text ? text.slice(0, 100) : fallback
  } catch {
    return fallback
  }
}

function _stringError(value: unknown): string | null {
  return typeof value === 'string' && value.trim() ? value.trim() : null
}

function _focusInput(input: HTMLInputElement): void {
  setTimeout(() => input.focus(), 0)
}

function _domId(prefix: string): string {
  _domIdSeq += 1
  return `${prefix}-${_domIdSeq}`
}

function _backendColorClass(backendId: string, color: string): string {
  const existing = _backendColorClasses.get(backendId)
  if (existing) return existing
  _backendColorSeq += 1
  const className = `backend-color-${_backendColorSeq}`
  _backendColorClasses.set(backendId, className)
  _insertBackendColorRule(className, color)
  return className
}

function _insertBackendColorRule(className: string, color: string): void {
  if (!CSS.supports('color', color)) return
  const sheet = _getStyleSheet()
  const rule = `.server-mgmt-body .backend-color-dot.${className} { background: ${color}; }`
  try {
    sheet.insertRule(rule, sheet.cssRules.length)
  } catch {
    // Ignore invalid backend colors; the CSS fallback keeps the marker visible.
  }
}

function _getStyleSheet(): CSSStyleSheet {
  if (_styleSheet) return _styleSheet
  const style = document.createElement('style')
  style.id = 'server-mgmt-dynamic-styles'
  document.head.appendChild(style)
  _styleSheet = style.sheet as CSSStyleSheet
  return _styleSheet
}
