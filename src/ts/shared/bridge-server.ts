/**
 * Type definitions, fetch helpers, and target resolution for multi-server Bridge.
 */

export type BackendEntry = {
  id: string
  type: 'comfyui' | 'sd_webui' | (string & {})
  base_url: string
  name: string
  color: string
  status: 'running' | 'stopped' | 'unknown'
}

export type GroupEntry = {
  id: string
  name: string
  backend_ids: string[]
}

export type SendTarget =
  | { kind: 'server'; backend_id: string }
  | { kind: 'group';  group_id: string }
  | { kind: 'default' }

export type SendTargetPayload = {
  bridge_type: 'comfyui' | 'sd_webui'
  target: SendTarget
}

export type FetchResult<T> =
  | { ok: true;  data: T }
  | { ok: false; error: string }

function _sendTargetKey(bridgeType: 'comfyui' | 'sd_webui'): string {
  return `bridge_send_target_${bridgeType}`
}

// Run once at module init to clear legacy single-key entry.
let _migrationDone = false

async function _runMigrationOnce(): Promise<void> {
  if (_migrationDone) return
  _migrationDone = true
  try {
    const { bridgeStorage } = await import('./bridge-storage')
    await bridgeStorage.remove('bridge_send_target').catch(() => undefined)
  } catch {
    // Ignore migration failures; loading can continue with scoped keys.
  }
}

export async function saveSendTarget(
  bridgeType: 'comfyui' | 'sd_webui',
  target: SendTarget,
): Promise<void> {
  const { bridgeStorage } = await import('./bridge-storage')
  const payload: SendTargetPayload = { bridge_type: bridgeType, target }
  await bridgeStorage.set(_sendTargetKey(bridgeType), JSON.stringify(payload))
}

export async function loadSendTarget(
  bridgeType: 'comfyui' | 'sd_webui',
): Promise<SendTarget> {
  await _runMigrationOnce()
  try {
    const { bridgeStorage } = await import('./bridge-storage')
    const raw = await bridgeStorage.get(_sendTargetKey(bridgeType))
    if (!raw) return { kind: 'default' }
    const parsed = JSON.parse(raw as string) as SendTargetPayload
    if (parsed.bridge_type !== bridgeType) return { kind: 'default' }
    return parsed.target
  } catch {
    return { kind: 'default' }
  }
}

export async function clearSendTarget(bridgeType: 'comfyui' | 'sd_webui'): Promise<void> {
  const { bridgeStorage } = await import('./bridge-storage')
  await bridgeStorage.remove(_sendTargetKey(bridgeType)).catch(() => undefined)
}

export async function fetchBackends(): Promise<FetchResult<BackendEntry[]>> {
  try {
    const res = await fetch('/api/gateway/backends')
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` }
    const json = await res.json() as { backends?: BackendEntry[] }
    return { ok: true, data: json.backends ?? [] }
  } catch (e) {
    return { ok: false, error: String(e) }
  }
}

export type DefaultsEntry = {
  default_comfy_backend_id: string | null
  default_sd_backend_id: string | null
}

export async function fetchDefaults(): Promise<FetchResult<DefaultsEntry>> {
  try {
    const res = await fetch('/api/gateway/defaults')
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` }
    const json = await res.json() as Partial<DefaultsEntry>
    return {
      ok: true,
      data: {
        default_comfy_backend_id: json.default_comfy_backend_id ?? null,
        default_sd_backend_id: json.default_sd_backend_id ?? null,
      },
    }
  } catch (e) {
    return { ok: false, error: String(e) }
  }
}

export async function fetchGroups(): Promise<FetchResult<GroupEntry[]>> {
  try {
    const res = await fetch('/api/gateway/groups')
    if (!res.ok) return { ok: false, error: `HTTP ${res.status}` }
    const json = await res.json() as GroupEntry[] | { groups?: GroupEntry[] }
    const data = Array.isArray(json) ? json : (json.groups ?? [])
    return { ok: true, data }
  } catch (e) {
    return { ok: false, error: String(e) }
  }
}

export function resolveTargetToBackends(
  target: SendTarget,
  backends: BackendEntry[],
  groups: GroupEntry[],
  bridgeType: 'comfyui' | 'sd_webui',
): BackendEntry[] {
  if (target.kind === 'default') return []
  if (target.kind === 'server') {
    const b = backends.find(b => b.id === target.backend_id)
    if (!b || b.type !== bridgeType) return []
    return [b]
  }
  const group = groups.find(g => g.id === target.group_id)
  if (!group) return []
  return group.backend_ids
    .map(id => backends.find(b => b.id === id))
    .filter((b): b is BackendEntry => !!b && b.type === bridgeType)
}
