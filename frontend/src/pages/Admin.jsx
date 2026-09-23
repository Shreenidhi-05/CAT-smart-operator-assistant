import { useCallback, useEffect, useState } from 'react'
import { api, openSocket } from '../api.js'
import { AlertRow, Badge, Card, Progress, Shell, Stat, StatusBadge, fmtMin, fmtTime } from '../components/ui.jsx'

export default function Admin() {
  const [ov, setOv] = useState(null)
  const [assignments, setAssignments] = useState([])
  const [flash, setFlash] = useState(null)
  const [override, setOverride] = useState({ operator_id: '', vehicle_id: '' })
  const [msg, setMsg] = useState(null)

  const refresh = useCallback(async () => {
    const [o, a] = await Promise.all([api('/admin/overview'), api('/assignments')])
    setOv(o); setAssignments(a)
  }, [])

  useEffect(() => { refresh(); const t = setInterval(refresh, 15000); return () => clearInterval(t) }, [refresh])
  useEffect(() => openSocket((ev) => {
    if (ev.event === 'alert' && ev.data.target === 'admin' && !ev.data.resolved) setFlash(ev.data)
    if (ev.event === 'task_update') setOv(o => o && ({ ...o, tasks: o.tasks.some(t => t.id === ev.data.id) ? o.tasks.map(t => t.id === ev.data.id ? ev.data : t) : [ev.data, ...o.tasks] }))
    else refresh()
  }), [refresh])
  useEffect(() => { if (flash) { const t = setTimeout(() => setFlash(null), 10000); return () => clearTimeout(t) } }, [flash])

  const resolve = async (a) => { await api(`/alerts/${a.id}/resolve`, { method: 'POST' }); refresh() }
  const doOverride = async (e) => {
    e.preventDefault(); setMsg(null)
    try {
      await api('/admin/override-assignment', { method: 'POST', body: { operator_id: Number(override.operator_id), vehicle_id: Number(override.vehicle_id), temporary: true } })
      setMsg('Override granted'); refresh()
    } catch (err) { setMsg(err.message) }
  }

  if (!ov) return <Shell title="Admin Command Center"><div className="text-graphite-400">Loading…</div></Shell>

  const operators = ov.users.filter(u => u.role === 'operator')
  const nameOf = (id) => ov.users.find(u => u.id === id)?.name ?? `#${id}`
  const openAlerts = ov.alerts.filter(a => !a.resolved)
  const escalations = openAlerts.filter(a => a.type === 'escalation' || a.type === 'sensor_fault' || a.type === 'wrong_vehicle')
  const active = ov.tasks.filter(t => t.status === 'active')

  return (
    <Shell title="Admin Command Center" subtitle="Fleet supervision · live" right={<Badge tone={escalations.length ? 'critical' : 'ok'}>{escalations.length} escalations</Badge>}>
      {flash && (
        <div className="fixed top-20 right-6 z-50 max-w-md card border-red-600 border-2 shadow-2xl">
          <div className="card-title text-red-400">{flash.type} · supervisor attention</div>
          <div className="text-sm">{flash.message}</div>
        </div>
      )}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 grid md:grid-cols-5 gap-4">
          <Card><Stat label="Active tasks" value={active.length} /></Card>
          <Card><Stat label="Open alerts" value={openAlerts.length} tone={openAlerts.length ? 'text-cat' : ''} /></Card>
          <Card><Stat label="Escalations" value={escalations.length} tone={escalations.length ? 'text-red-400' : ''} /></Card>
          <Card><Stat label="Incidents (auto)" value={ov.incidents.length} /></Card>
          <Card><Stat label="Vehicles" value={ov.vehicles.length} sub={`${Object.values(ov.devices).filter(d => d.seatbelt_status !== 'fastened').length} seatbelt warnings`} /></Card>
        </div>

        <div className="col-span-12 lg:col-span-8 space-y-4">
          <Card title="Live tasks" accent>
            {ov.tasks.length === 0 ? <div className="text-sm text-graphite-400">No tasks in progress.</div> : (
              <div className="space-y-3">
                {ov.tasks.map(t => <TaskRow key={t.id} t={t} nameOf={nameOf} />)}
              </div>
            )}
          </Card>

          <Card title="Alerts feed">
            <div className="space-y-2 max-h-[420px] overflow-auto pr-1">
              {ov.alerts.map(a => <AlertRow key={a.id} a={a} onResolve={resolve} />)}
            </div>
          </Card>
        </div>

        <div className="col-span-12 lg:col-span-4 space-y-4">
          <Card title="Fleet · vehicles & sensors">
            <table className="w-full text-sm">
              <thead className="text-[10px] uppercase text-graphite-400 text-left"><tr><th>Veh</th><th>Type</th><th>Operator</th><th>Belt</th><th>Prox</th></tr></thead>
              <tbody>
                {ov.vehicles.map(v => {
                  const d = ov.devices[v.id]
                  return (
                    <tr key={v.id} className="border-t border-graphite-700">
                      <td className="py-1.5 font-bold">#{v.id}</td><td>{v.machine_type}</td><td>{v.current_operator_id ? nameOf(v.current_operator_id) : '—'}</td>
                      <td>{d ? <Badge tone={d.seatbelt_status === 'fastened' ? 'ok' : 'critical'}>{d.seatbelt_status}</Badge> : <span className="text-graphite-400">—</span>}</td>
                      <td>{d ? `${Number(d.proximity_m).toFixed(1)} m` : '—'}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Card>

          <Card title="Supervisor override · reassign operator">
            <form onSubmit={doOverride} className="space-y-2">
              <select className="input" value={override.operator_id} onChange={e => setOverride(o => ({ ...o, operator_id: e.target.value }))} required>
                <option value="">Operator…</option>
                {operators.map(u => <option key={u.id} value={u.id}>{u.name} (currently veh #{assignments.find(a => a.operator_id === u.id)?.vehicle_id ?? '—'})</option>)}
              </select>
              <select className="input" value={override.vehicle_id} onChange={e => setOverride(o => ({ ...o, vehicle_id: e.target.value }))} required>
                <option value="">Vehicle…</option>
                {ov.vehicles.map(v => <option key={v.id} value={v.id}>#{v.id} {v.machine_type}</option>)}
              </select>
              <button className="btn-cat w-full">Grant temporary override</button>
              {msg && <div className="text-xs text-cat">{msg}</div>}
            </form>
          </Card>

          <Card title="Incidents (auto-generated)">
            <div className="space-y-2 max-h-[300px] overflow-auto text-sm">
              {ov.incidents.length === 0 && <div className="text-graphite-400">None.</div>}
              {ov.incidents.map(i => (
                <div key={i.id} className="border border-graphite-700 rounded p-2 bg-graphite-900">
                  <div className="flex justify-between"><Badge tone="critical">{i.type.replace('_', ' ')}</Badge><span className="text-[11px] text-graphite-400">{fmtTime(i.timestamp)}</span></div>
                  <div className="mt-1 text-xs">{i.details}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </Shell>
  )
}

function TaskRow({ t, nameOf }) {
  const [, tick] = useState(0)
  useEffect(() => { const i = setInterval(() => tick(x => x + 1), 5000); return () => clearInterval(i) }, [])
  const started = t.actual_start ? new Date(t.actual_start + 'Z') : null
  const elapsed = started ? (Date.now() - started.getTime()) / 60000 : 0
  const pct = t.status === 'active' ? Math.min(99, (elapsed / (t.predicted_time_min || 60)) * 100) : 0
  return (
    <div className="border border-graphite-700 rounded p-3 bg-graphite-900">
      <div className="flex flex-wrap items-center gap-3">
        <span className="font-display font-bold text-lg">#{t.id} {t.task_type}</span>
        <span className="text-sm text-graphite-400">{t.zone} · veh #{t.vehicle_id} · {nameOf(t.operator_id)}</span>
        <StatusBadge status={t.status} />
        {t.paused && <Badge tone="warning">planned pause</Badge>}
        {t.unresolved_alert_count > 0 && <Badge tone="critical">{t.unresolved_alert_count} unresolved</Badge>}
        <span className="ml-auto text-xs text-graphite-400">{Math.floor(elapsed)} / {fmtMin(t.predicted_time_min)} · range {t.predicted_range_min}</span>
      </div>
      {t.status === 'active' && <div className="mt-2"><Progress pct={pct} tone={elapsed > t.predicted_time_min ? 'bg-red-500' : 'bg-cat'} /></div>}
    </div>
  )
}
