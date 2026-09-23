// Per-device config: the vehicle this operator terminal is mounted in comes from the build env,
// never from application logic. Admin builds leave it unset.
export const DEVICE_VEHICLE_ID = import.meta.env.VITE_VEHICLE_ID ? Number(import.meta.env.VITE_VEHICLE_ID) : null
export const APP_MODE = import.meta.env.VITE_APP_MODE || 'both' // operator | admin | both

const BASE = import.meta.env.VITE_API_URL || ''

export function getToken() { return localStorage.getItem('token') }
export function getUser() { try { return JSON.parse(localStorage.getItem('user')) } catch { return null } }
export function setSession(token, user) {
  localStorage.setItem('token', token)
  localStorage.setItem('user', JSON.stringify(user))
}
export function clearSession() { localStorage.removeItem('token'); localStorage.removeItem('user') }

export async function api(path, { method = 'GET', body, auth = true } = {}) {
  const headers = { 'Content-Type': 'application/json' }
  if (auth && getToken()) headers.Authorization = `Bearer ${getToken()}`
  const r = await fetch(`${BASE}/api${path}`, { method, headers, body: body ? JSON.stringify(body) : undefined })
  const text = await r.text()
  let data = null
  try { data = text ? JSON.parse(text) : null } catch { data = text }
  if (!r.ok) {
    const err = new Error(typeof data?.detail === 'string' ? data.detail : (data?.detail?.message || `HTTP ${r.status}`))
    err.status = r.status
    err.detail = data?.detail
    throw err
  }
  return data
}

export function openSocket(onEvent) {
  const token = getToken()
  if (!token) return () => {}
  const proto = location.protocol === 'https:' ? 'wss' : 'ws'
  const host = BASE ? BASE.replace(/^https?:\/\//, '') : location.host
  let ws, timer, closed = false
  const connect = () => {
    ws = new WebSocket(`${proto}://${host}/ws?token=${token}`)
    ws.onmessage = (m) => { try { onEvent(JSON.parse(m.data)) } catch { /* ignore */ } }
    ws.onopen = () => { timer = setInterval(() => ws.readyState === 1 && ws.send('ping'), 20000) }
    ws.onclose = () => { clearInterval(timer); if (!closed) setTimeout(connect, 2000) }
  }
  connect()
  return () => { closed = true; clearInterval(timer); if (ws) ws.close() }
}
