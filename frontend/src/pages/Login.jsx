import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { APP_MODE, DEVICE_VEHICLE_ID, api, setSession } from '../api.js'

export default function Login() {
  const nav = useNavigate()
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [vehicleId, setVehicleId] = useState(DEVICE_VEHICLE_ID ?? 1)
  const [error, setError] = useState(null)
  const [busy, setBusy] = useState(false)

  const submit = async (e) => {
    e.preventDefault()
    setBusy(true); setError(null)
    try {
      const vid = APP_MODE === 'admin' ? null : Number(vehicleId)
      const r = await api('/auth/login', { method: 'POST', body: { username, password, vehicle_id: vid }, auth: false })
      setSession(r.access_token, r.user)
      if (r.user.role === 'admin') {
        nav('/admin')
      } else {
        if (vid) sessionStorage.setItem('device_vehicle_id', String(vid))
        sessionStorage.setItem('vehicle_check', JSON.stringify(r.vehicle_check))
        nav('/operator')
      }
    } catch (err) {
      setError(err.message)
    } finally { setBusy(false) }
  }

  return (
    <div className="min-h-full flex flex-col">
      <div className="hazard-stripe h-2" />
      <div className="flex-1 flex items-center justify-center p-6">
        <form onSubmit={submit} className="card w-full max-w-md space-y-5 !p-8">
          <div className="flex items-center gap-4">
            <div className="bg-cat text-graphite-950 font-display font-extrabold text-4xl px-3 leading-[3rem]">CAT</div>
            <div>
              <div className="font-display font-bold text-2xl uppercase tracking-wide">Command Center</div>
              <div className="text-xs text-graphite-400 uppercase tracking-widest">Smart Operator Assistant</div>
            </div>
          </div>
          <div>
            <label className="label">Operator / Admin ID</label>
            <input className="input" value={username} onChange={e => setUsername(e.target.value)} autoFocus placeholder="e.g. maya" />
          </div>
          <div>
            <label className="label">Password</label>
            <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} />
          </div>
          {APP_MODE !== 'admin' && (
            <div>
              <label className="label">This device · Vehicle ID {DEVICE_VEHICLE_ID ? '(from device config)' : '(VITE_VEHICLE_ID not set — dev override)'}</label>
              <input className="input" type="number" value={vehicleId} onChange={e => setVehicleId(e.target.value)}
                     disabled={DEVICE_VEHICLE_ID != null} />
            </div>
          )}
          {error && <div className="text-red-400 text-sm">{error}</div>}
          <button className="btn-cat w-full" disabled={busy}>{busy ? 'Signing in…' : 'Sign in'}</button>
          <div className="text-[11px] text-graphite-400 leading-relaxed">
            Demo accounts — admin/admin123 · maya (veh 1) · raj (veh 2) · leo (veh 3) · sam (veh 4), password operator123
          </div>
        </form>
      </div>
    </div>
  )
}
