/** Cached gateway admin token for mutation API calls. */
const _TOKEN_TTL_MS = 5 * 60 * 1000
let _cachedToken: string | null = null
let _cachedAt = 0
let _inFlight: Promise<string | null> | null = null

export function invalidateAdminToken(): void {
  _cachedToken = null
  _cachedAt = 0
  _inFlight = null
}

async function _fetchAdminToken(): Promise<string | null> {
  try {
    const res = await fetch('/api/gateway/admin-token')
    if (!res.ok) {
      console.error('[gateway-auth] admin-token HTTP', res.status, res.statusText)
      return null
    }
    const d = await res.json() as { token?: string }
    const tok = (typeof d.token === 'string' && d.token.length > 0) ? d.token : null
    if (!tok) {
      console.error('[gateway-auth] admin-token response missing/empty token:', d)
      return null
    }
    _cachedToken = tok
    _cachedAt = Date.now()
    return tok
  } catch (e) {
    console.error('[gateway-auth] admin-token exception:', e)
    return null
  }
}

export async function getAdminToken(): Promise<string | null> {
  const now = Date.now()
  if (_cachedToken && (now - _cachedAt) < _TOKEN_TTL_MS) return _cachedToken
  if (_inFlight) return _inFlight
  _inFlight = _fetchAdminToken().finally(() => { _inFlight = null })
  return _inFlight
}

export async function mutationHeaders(): Promise<HeadersInit> {
  const token = await getAdminToken()
  const h: Record<string, string> = { 'Content-Type': 'application/json' }
  if (token) {
    h['Authorization'] = `Bearer ${token}`
  } else {
    console.error('[gateway-auth] mutationHeaders: no token — Authorization header will be omitted')
  }
  return h
}
