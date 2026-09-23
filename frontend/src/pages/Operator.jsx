import { useCallback, useEffect, useRef, useState } from 'react'
import { api, getUser, openSocket } from '../api.js'
import { AlertRow, Badge, Card, Progress, Shell, Stat, StatusBadge, fmtMin, fmtTime } from '../components/ui.jsx'

const vehicleIdFromDevice = () => Number(sessionStorage.getItem('device_vehicle_id') || 1)

export default function Operator() {
  const user = getUser()
  const vehicleId = vehicleIdFromDevice()
  const [vc, setVc] = useState(() => JSON.parse(sessionStorage.getItem('vehicle_check') || 'null'))
  const [device, setDevice] = useState({ seatbelt_status: 'fastened', proximity_m: 25 })
  const [task, setTask] = useState(null)
  const [alerts, setAlerts] = useState([])
  const [lastCheck, setLastCheck] = useState(null)
  const [cfg, setCfg] = useState(null)
  const [toast, setToast] = useState(null)

  const refreshVc = useCallback(() => api(`/auth/vehicle-check?vehicle_id=${vehicleId}`).then(setVc).catch(() => {}), [vehicleId])
  const refreshTask = useCallback(() => api('/tasks/current').then(setTask).catch(() => {}), [])
  const refreshAlerts = useCallback((tid) => tid && api(`/alerts?task_id=${tid}`).then(setAlerts).catch(() => {}), [])

  useEffect(() => {
    api('/config').then(setCfg)
    api(`/device/${vehicleId}`).then(setDevice)
    refreshVc(); refreshTask()
  }, [vehicleId, refreshVc, refreshTask])

  useEffect(() => { if (task?.id) refreshAlerts(task.id) }, [task?.id, refreshAlerts])

  useEffect(() => openSocket((ev) => {
    if (ev.event === 'task_update') setTask(t => (!t || t.id === ev.data.id) ? ev.data : t)
    if (ev.event === 'alert') {
      setAlerts(list => {
        const i = list.findIndex(a => a.id === ev.data.id)
        if (i >= 0) { const c = [...list]; c[i] = { ...c[i], ...ev.data }; return c }
        return [ev.data, ...list]
      })
      if (!ev.data.resolved && ev.data.target === 'operator') setToast(ev.data)
      refreshTask()
    }
    if (ev.event === 'anomaly_check') setLastCheck(ev.data)
    if (ev.event === 'assignment') refreshVc()
    if (ev.event === 'device_state' && ev.data.vehicle_id === vehicleId) setDevice(ev.data)
  }), [vehicleId, refreshVc, refreshTask])

  useEffect(() => { if (toast) { const t = setTimeout(() => setToast(null), 8000); return () => clearTimeout(t) } }, [toast])

  const setDev = async (patch) => setDevice(await api('/device/state', { method: 'POST', body: { vehicle_id: vehicleId, ...patch } }))
  const resolve = async (a) => { await api(`/alerts/${a.id}/resolve`, { method: 'POST' }); refreshAlerts(task?.id); refreshTask() }

  const right = <Badge tone={vc?.ok ? 'ok' : 'critical'}>Vehicle #{vehicleId}{vc?.ok ? ' · verified' : ' · mismatch'}</Badge>

  return (
    <Shell title="Operator Console" subtitle={`Operator ${user?.name} · Device vehicle #${vehicleId}`} right={right}>
      {toast && (
        <div className="fixed top-20 right-6 z-50 max-w-md card border-cat border-2 shadow-2xl">
          <div className="card-title text-cat">{toast.type} alert</div>
          <div className="text-sm">{toast.message}</div>
        </div>
      )}
      <div className="grid grid-cols-12 gap-4">
        <div className="col-span-12 lg:col-span-9 space-y-4">
          {vc && !vc.ok ? (
            <WrongVehicle vc={vc} onRetry={refreshVc} />
          ) : !task || ['pending', 'blocked', 'suspended'].includes(task.status) ? (
            <PreTask vehicleId={vehicleId} task={task} setTask={setTask} device={device} cfg={cfg} />
          ) : (
            <Monitor task={task} setTask={setTask} alerts={alerts} resolve={resolve} lastCheck={lastCheck} cfg={cfg} />
          )}
        </div>
        <div className="col-span-12 lg:col-span-3 space-y-4">
          <Cockpit device={device} setDev={setDev} cfg={cfg} />
          <Card title="Device config">
            <div className="text-xs text-graphite-400 space-y-1">
              <div>Vehicle ID: <span className="text-slate-100">#{vehicleId}</span> (from device config)</div>
              <div>Assigned: <span className="text-slate-100">#{vc?.assigned_vehicle_id ?? '—'}</span></div>
              {cfg && <div>Telemetry every {cfg.sensor_interval_s}s · anomaly check every {cfg.anomaly_interval_s}s</div>}
            </div>
          </Card>
        </div>
      </div>
    </Shell>
  )
}

function WrongVehicle({ vc, onRetry }) {
  return (
    <Card className="border-red-600 border-2">
      <div className="flex items-start gap-4">
        <div className="text-5xl">⛔</div>
        <div className="flex-1">
          <div className="font-display text-3xl font-bold text-red-400 uppercase">Wrong vehicle</div>
          <p className="mt-2">You are logged in on vehicle <b>#{vc.device_vehicle_id}</b>. Your assigned vehicle is <b className="text-cat">#{vc.assigned_vehicle_id ?? '?'}</b>.</p>
          <p className="text-sm text-graphite-400 mt-1">Operation is blocked. Move to the correct machine or ask a supervisor for a temporary override. This screen updates automatically when the override is granted.</p>
          <button className="btn-ghost mt-4" onClick={onRetry}>Re-check assignment</button>
        </div>
      </div>
    </Card>
  )
}

function Cockpit({ device, setDev, cfg }) {
  const hazard = cfg && device.proximity_m < cfg.proximity_hazard_m
  return (
    <Card title="Cockpit sensors (simulated)" accent>
      <div className="space-y-4">
        <div>
          <div className="flex justify-between items-center">
            <span className="text-sm">Seatbelt</span>
            <Badge tone={device.seatbelt_status === 'fastened' ? 'ok' : 'critical'}>{device.seatbelt_status}</Badge>
          </div>
          <div className="grid grid-cols-2 gap-2 mt-2">
            <button className="btn-ghost !text-xs" onClick={() => setDev({ seatbelt_status: 'fastened' })}>Fasten</button>
            <button className="btn-ghost !text-xs" onClick={() => setDev({ seatbelt_status: 'unfastened' })}>Unfasten</button>
          </div>
        </div>
        <div>
          <div className="flex justify-between items-center">
            <span className="text-sm">Nearest obstacle</span>
            <Badge tone={hazard ? 'critical' : 'ok'}>{Number(device.proximity_m).toFixed(1)} m</Badge>
          </div>
          <input type="range" min="0.5" max="30" step="0.5" className="w-full mt-2 accent-cat" value={device.proximity_m}
                 onChange={e => setDev({ proximity_m: Number(e.target.value) })} />
          {cfg && <div className="text-[11px] text-graphite-400">Hazard threshold {cfg.proximity_hazard_m} m</div>}
        </div>
      </div>
    </Card>
  )
}

function PreTask({ vehicleId, task, setTask, device, cfg }) {
  const [form, setForm] = useState({ zone: 'Zone A - Pit', task_type: 'Excavation', ground_condition: 'dry', ground_moisture: 0.2, obstacle_distance_m: 10, demo_scenario: '' })
  const [prep, setPrep] = useState(null)
  const [gate, setGate] = useState(null)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState(null)
  const [scenarios, setScenarios] = useState([])
  const pollRef = useRef(null)

  useEffect(() => { api('/demo-scenarios').then(setScenarios).catch(() => {}) }, [])

  const pollGate = useCallback(async () => {
    try { setGate(await api(`/safety-gate?vehicle_id=${vehicleId}`)) } catch { /* ignore */ }
  }, [vehicleId])

  useEffect(() => {
    pollGate()
    pollRef.current = setInterval(pollGate, 5000)
    return () => clearInterval(pollRef.current)
  }, [pollGate, device.seatbelt_status, device.proximity_m])

  const upd = (k, v) => setForm(f => ({ ...f, [k]: v }))
  const applyScenario = (key) => {
    upd('demo_scenario', key)
    const s = scenarios.find(x => x.key === key)
    if (s) setForm(f => ({ ...f, zone: s.zone, task_type: s.task_type, ground_condition: s.ground_condition || f.ground_condition,
      ground_moisture: s.ground_moisture ?? f.ground_moisture, obstacle_distance_m: s.obstacle_distance_m ?? f.obstacle_distance_m, demo_scenario: key }))
  }

  const prepare = async () => {
    setBusy(true); setErr(null)
    try {
      const r = await api('/tasks/prepare', { method: 'POST', body: { ...form, vehicle_id: vehicleId, demo_scenario: form.demo_scenario || null,
        ground_moisture: Number(form.ground_moisture), obstacle_distance_m: Number(form.obstacle_distance_m) } })
      setPrep(r); setTask(r.task); setGate(r.safety_gate)
    } catch (e) { setErr(e.message) } finally { setBusy(false) }
  }
  const start = async () => {
    setBusy(true); setErr(null)
    try { setTask(await api(`/tasks/${task.id}/start`, { method: 'POST' })) }
    catch (e) { setErr(e.message); pollGate(); if (e.detail?.gate) setGate(e.detail.gate) }
    finally { setBusy(false) }
  }
  const suspend = async () => setTask(await api(`/tasks/${task.id}/suspend`, { method: 'POST' }))

  const gateOk = gate?.ok
  const risky = prep?.risk?.risky || task?.status === 'suspended'

  return (
    <>
      <Card title="Pre-task safety gate" accent>
        <div className="grid md:grid-cols-3 gap-4">
          <GateItem ok={gate?.seatbelt_ok} label="Seatbelt" value={gate?.seatbelt_status ?? '…'} />
          <GateItem ok={gate?.proximity_ok} label="Proximity" value={gate ? `${Number(gate.proximity_m).toFixed(1)} m clearance` : '…'} />
          <GateItem ok={gate && !gate.sensor_fault} label="Sensor health" value={gate?.sensor_fault ? 'SEATBELT SENSOR FAULT' : 'nominal'} />
        </div>
        {gate && !gate.ok && (
          <div className="mt-4 p-4 rounded border-2 border-red-600 bg-red-950/40">
            {gate.sensor_fault ? (
              <>
                <div className="font-display text-2xl font-bold text-red-400 uppercase">Seatbelt sensor fault suspected</div>
                <p className="text-sm mt-1">Seatbelt status has not changed for over {cfg?.seatbelt_fault_timeout_s}s after the training prompt. Your supervisor has been notified — wait for inspection instead of re-trying.</p>
              </>
            ) : (
              <>
                <div className="font-display text-2xl font-bold text-red-400 uppercase">
                  {!gate.seatbelt_ok ? 'Seatbelt not fastened' : 'Proximity hazard detected'}
                </div>
                <p className="text-sm mt-1">Task start is blocked. {!gate.seatbelt_ok ? `Fasten your seatbelt (${gate.seconds_since_video ?? 0}s since prompt).` : 'Clear the obstacle before starting.'}</p>
                {gate.training_module && (
                  <div className="mt-3">
                    <div className="card-title">Required training · {gate.training_module.title}</div>
                    <iframe title={gate.training_module.title} className="w-full aspect-video rounded border border-graphite-600"
                            src={`${gate.training_module.video_url}?autoplay=1&mute=1`} allow="autoplay; encrypted-media" allowFullScreen />
                  </div>
                )}
              </>
            )}
          </div>
        )}
      </Card>

      <Card title="Task parameters">
        <div className="grid md:grid-cols-3 gap-3">
          <Field label="Demo scenario">
            <select className="input" value={form.demo_scenario} onChange={e => applyScenario(e.target.value)}>
              <option value="">— none (normal operation) —</option>
              {scenarios.map(s => <option key={s.key} value={s.key}>{s.title}</option>)}
            </select>
          </Field>
          <Field label="Zone"><select className="input" value={form.zone} onChange={e => upd('zone', e.target.value)}>{(cfg?.zones || []).map(z => <option key={z}>{z}</option>)}</select></Field>
          <Field label="Task type"><select className="input" value={form.task_type} onChange={e => upd('task_type', e.target.value)}>{(cfg?.task_types || []).map(z => <option key={z}>{z}</option>)}</select></Field>
          <Field label="Ground condition"><select className="input" value={form.ground_condition} onChange={e => upd('ground_condition', e.target.value)}>{(cfg?.ground_conditions || []).map(z => <option key={z}>{z}</option>)}</select></Field>
          <Field label={`Ground moisture (${form.ground_moisture})`}><input type="range" min="0" max="1" step="0.01" className="w-full accent-cat mt-2" value={form.ground_moisture} onChange={e => upd('ground_moisture', e.target.value)} /></Field>
          <Field label="Obstacle distance (m)"><input type="number" className="input" value={form.obstacle_distance_m} onChange={e => upd('obstacle_distance_m', e.target.value)} /></Field>
        </div>
        <div className="flex gap-3 mt-4 items-center">
          <button className="btn-cat" onClick={prepare} disabled={busy}>{prep ? 'Re-run estimate & risk check' : 'Prepare task'}</button>
          {task && <StatusBadge status={task.status} />}
          {err && <span className="text-red-400 text-sm">{err}</span>}
        </div>
      </Card>

      {prep && (
        <div className="grid md:grid-cols-3 gap-4">
          <Card title="AI time estimate (LightGBM quantile)">
            <Stat label="Point estimate" value={Math.round(prep.prediction.p50)} unit="min" sub={`Range ${Math.round(prep.prediction.p10)}–${Math.round(prep.prediction.p90)} min (p10–p90)`} tone="text-cat" />
            <div className="text-xs text-graphite-400 mt-3">
              Your last time for {form.task_type}: <span className="text-slate-100">{fmtMin(prep.last_time_for_task)}</span><br />
              Machine {prep.params.machine_type} · skill {prep.params.operator_skill}/3 · {prep.params.ground_condition} ground
            </div>
          </Card>
          <Card title={`Weather · ${prep.weather.source}`}>
            <div className="grid grid-cols-2 gap-3">
              <Stat label="Temp" value={Math.round(prep.weather.temp_c)} unit="°C" />
              <Stat label="Wind" value={Math.round(prep.weather.wind_kmh)} unit="km/h" tone={prep.weather.wind_kmh > (cfg?.risk_thresholds.wind_kmh_max ?? 40) ? 'text-red-400' : ''} />
              <Stat label="Visibility" value={prep.weather.visibility_m >= 1000 ? (prep.weather.visibility_m / 1000).toFixed(1) : prep.weather.visibility_m} unit={prep.weather.visibility_m >= 1000 ? 'km' : 'm'} tone={prep.weather.visibility_m < (cfg?.risk_thresholds.visibility_m_min ?? 50) ? 'text-red-400' : ''} />
              <Stat label="Sky" value={<span className="text-xl">{prep.weather.condition}</span>} />
            </div>
          </Card>
          <Card title="Risk check" className={risky ? 'border-red-600 border-2' : 'border-emerald-700'}>
            {prep.risk.risky ? (
              <>
                <div className="font-display text-2xl font-bold text-red-400 uppercase">Suspension suggested</div>
                <ul className="text-sm mt-2 list-disc pl-5 space-y-1">{prep.risk.reasons.map(r => <li key={r}>{r}</li>)}</ul>
              </>
            ) : (
              <div className="font-display text-2xl font-bold text-emerald-400 uppercase">Within thresholds</div>
            )}
            <div className="text-[11px] text-graphite-400 mt-3">Limits: wind ≤ {prep.risk.thresholds.wind_kmh_max} km/h · visibility ≥ {prep.risk.thresholds.visibility_m_min} m · moisture ≤ {prep.risk.thresholds.ground_moisture_max} · clearance ≥ {prep.risk.thresholds.obstacle_distance_m_min} m</div>
          </Card>
        </div>
      )}

      {task && (
        <Card>
          <div className="flex flex-wrap gap-3 items-center">
            <button className="btn-cat !text-base !px-8 !py-3" onClick={start} disabled={busy || !gateOk || task.status === 'suspended'}>▶ Start task</button>
            {risky && task.status !== 'suspended' && <button className="btn-danger" onClick={suspend}>Suspend task</button>}
            {task.status === 'suspended' && <span className="text-sm text-cat">Task suspended pending conditions. Re-run the estimate when conditions improve.</span>}
            {!gateOk && task.status !== 'suspended' && <span className="text-sm text-red-400">Start disabled until the safety gate is satisfied.</span>}
          </div>
        </Card>
      )}
    </>
  )
}

function GateItem({ ok, label, value }) {
  return (
    <div className={`p-3 rounded border ${ok == null ? 'border-graphite-600' : ok ? 'border-emerald-600 bg-emerald-950/30' : 'border-red-600 bg-red-950/30'}`}>
      <div className="card-title !mb-0">{label}</div>
      <div className={`font-display text-xl font-bold uppercase ${ok == null ? '' : ok ? 'text-emerald-400' : 'text-red-400'}`}>{value}</div>
    </div>
  )
}

function Field({ label, children }) {
  return <div><label className="label">{label}</label>{children}</div>
}

function Monitor({ task, setTask, alerts, resolve, lastCheck, cfg }) {
  const [busy, setBusy] = useState(false)
  const [, tick] = useState(0)
  useEffect(() => { const t = setInterval(() => tick(x => x + 1), 1000); return () => clearInterval(t) }, [])

  const started = task.actual_start ? new Date(task.actual_start + 'Z') : null
  const elapsed = started ? (Date.now() - started.getTime()) / 60000 : 0
  const [lo, hi] = (task.predicted_range_min || '0-0').split('-').map(Number)
  const pct = task.status === 'completed' ? 100 : Math.min(99, (elapsed / (task.predicted_time_min || 60)) * 100)
  const finish = (m) => started ? fmtTime(new Date(started.getTime() + m * 60000).toISOString()) : '—'
  const over = elapsed > (task.predicted_time_min || Infinity)
  const unresolved = alerts.filter(a => !a.resolved && a.target === 'operator')

  const pause = async () => setTask(await api(`/tasks/${task.id}/pause`, { method: 'POST', body: { paused: !task.paused } }))
  const complete = async () => { setBusy(true); try { setTask(await api(`/tasks/${task.id}/complete`, { method: 'POST' })) } finally { setBusy(false) } }
  const check = async () => { setBusy(true); try { await api(`/tasks/${task.id}/anomaly-check`, { method: 'POST' }) } finally { setBusy(false) } }
  const newTask = () => setTask(null)

  const logs = task.recent_logs || []
  const maxIdle = Math.max(1, ...logs.map(l => l.idling_min))
  const maxFuel = Math.max(1, ...logs.map(l => l.fuel_used))

  return (
    <>
      <Card accent>
        <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div>
            <div className="card-title !mb-0">Task #{task.id} · {task.task_type}</div>
            <div className="font-display text-3xl font-bold uppercase">{task.zone}</div>
          </div>
          <div className="flex items-center gap-2">
            <StatusBadge status={task.status} />
            {task.paused && <Badge tone="warning">Planned pause · anomaly checks suppressed</Badge>}
            {task.unresolved_alert_count > 0 && <Badge tone="critical">{task.unresolved_alert_count}/{cfg?.escalation_after ?? 3} unresolved → escalation</Badge>}
          </div>
        </div>
        <Progress pct={pct} tone={over ? 'bg-red-500' : 'bg-cat'} />
        <div className="grid md:grid-cols-4 lg:grid-cols-6 gap-4 mt-4">
          <Stat label="% complete" value={Math.round(pct)} unit="%" />
          <Stat label="Elapsed" value={Math.floor(elapsed)} unit="min" sub={`predicted ${fmtMin(task.predicted_time_min)}`} tone={over ? 'text-red-400' : ''} />
          <Stat label="Expected finish" value={<span className="text-xl">{finish(lo)}–{finish(hi)}</span>} sub={`range ${Math.round(lo)}–${Math.round(hi)} min`} />
          <Stat label="Your last time" value={task.last_time_for_task != null ? Math.round(task.last_time_for_task) : '—'} unit="min" sub={`for ${task.task_type}`} />
          <Stat label="Temperature" value={task.weather?.temp_c != null ? Math.round(task.weather.temp_c) : '—'} unit="°C" sub={task.weather?.condition} />
          <Stat label="Ground" value={<span className="text-xl uppercase">{task.ground_condition}</span>} sub={`moisture ${task.ground_moisture}`} />
        </div>
        <div className="flex flex-wrap gap-3 mt-5">
          {task.status === 'active' && (
            <>
              <button className={task.paused ? 'btn-cat' : 'btn-ghost'} onClick={pause}>{task.paused ? '▶ Resume from planned pause' : '⏸ Log planned pause'}</button>
              <button className="btn-ghost" onClick={check} disabled={busy || task.paused}>Run anomaly check now</button>
              <button className="btn-cat ml-auto" onClick={complete} disabled={busy}>✓ Mark complete</button>
            </>
          )}
          {task.status === 'completed' && (
            <>
              <div className="text-sm">Completed at {fmtTime(task.actual_end)} · total idle time <b className="text-cat">{task.total_idle_min} min</b> (computed from sensor logs)</div>
              <button className="btn-cat ml-auto" onClick={newTask}>New task</button>
            </>
          )}
        </div>
      </Card>

      <div className="grid lg:grid-cols-2 gap-4">
        <Card title="AI insight · anomaly monitor">
          {lastCheck && lastCheck.task_id === task.id ? (
            <>
              <div className="flex items-center gap-2 mb-2">
                <Badge tone={lastCheck.anomaly ? 'critical' : 'ok'}>{lastCheck.anomaly ? 'Anomaly' : 'Normal'}</Badge>
                <span className="text-xs text-graphite-400">baseline: {lastCheck.baseline} · window {lastCheck.window_rows} rows · {fmtTime(lastCheck.checked_at)}</span>
              </div>
              {lastCheck.explanation && <p className="text-sm">{lastCheck.explanation}</p>}
              <div className="grid grid-cols-3 gap-2 mt-3">
                {Object.entries(lastCheck.zscores || {}).map(([k, z]) => (
                  <div key={k} className="bg-graphite-900 rounded p-2 border border-graphite-700">
                    <div className="text-[10px] uppercase text-graphite-400">{k.replace('_', ' ')}</div>
                    <div className={`font-display text-xl font-bold ${Math.abs(z) >= (cfg?.anomaly_z ?? 2.5) ? 'text-red-400' : ''}`}>{z > 0 ? '+' : ''}{z}σ</div>
                  </div>
                ))}
              </div>
              <div className="text-[11px] text-graphite-400 mt-2">Isolation Forest: {lastCheck.isolation_forest_flag ? 'multivariate outlier' : 'in envelope'}{lastCheck.isolation_forest_score != null ? ` (score ${lastCheck.isolation_forest_score.toFixed(3)})` : ''}</div>
            </>
          ) : <div className="text-sm text-graphite-400">First check runs {cfg?.anomaly_interval_s ?? 30}s after start (z-score vs personal/fleet baseline + Isolation Forest).</div>}
        </Card>

        <Card title="Live telemetry">
          {logs.length === 0 ? <div className="text-sm text-graphite-400">Waiting for first sensor log…</div> : (
            <>
              <div className="grid grid-cols-3 gap-3 mb-3">
                <Stat label="Fuel (last)" value={logs.at(-1).fuel_used} unit="L" />
                <Stat label="Load cycles" value={logs.at(-1).load_cycles} />
                <Stat label="Idling" value={logs.at(-1).idling_min} unit="min" />
              </div>
              <div className="text-[10px] uppercase text-graphite-400 mb-1">Idling per interval</div>
              <div className="flex items-end gap-0.5 h-12">
                {logs.map((l, i) => <div key={i} title={`${l.idling_min} min`} className={`flex-1 ${l.safety_alert_triggered ? 'bg-red-500' : 'bg-cat'}`} style={{ height: `${(l.idling_min / maxIdle) * 100}%` }} />)}
              </div>
              <div className="text-[10px] uppercase text-graphite-400 mb-1 mt-2">Fuel per interval</div>
              <div className="flex items-end gap-0.5 h-12">
                {logs.map((l, i) => <div key={i} title={`${l.fuel_used} L`} className={`flex-1 ${l.safety_alert_triggered ? 'bg-red-500' : 'bg-slate-400'}`} style={{ height: `${(l.fuel_used / maxFuel) * 100}%` }} />)}
              </div>
              <div className="text-[11px] text-graphite-400 mt-2">Engine hours {logs.at(-1).engine_hours} · seatbelt {logs.at(-1).seatbelt_status} · last log {fmtTime(logs.at(-1).timestamp)}</div>
            </>
          )}
        </Card>
      </div>

      <Card title={`Alerts for this task (${unresolved.length} unresolved)`}>
        {alerts.length === 0 ? <div className="text-sm text-graphite-400">No alerts.</div> : (
          <div className="space-y-2">{alerts.filter(a => a.target === 'operator').map(a => <AlertRow key={a.id} a={a} onResolve={resolve} />)}</div>
        )}
      </Card>
    </>
  )
}
