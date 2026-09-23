import { clearSession, getUser } from '../api.js'

export function Shell({ title, subtitle, right, children }) {
  const user = getUser()
  const logout = () => { clearSession(); location.href = '/login' }
  return (
    <div className="min-h-full flex flex-col">
      <div className="hazard-stripe h-1.5" />
      <header className="flex items-center justify-between px-6 py-3 bg-graphite-900 border-b border-graphite-700">
        <div className="flex items-center gap-4">
          <div className="bg-cat text-graphite-950 font-display font-extrabold text-2xl px-2 leading-8 tracking-tight">CAT</div>
          <div>
            <div className="font-display font-bold text-xl leading-tight uppercase tracking-wide">{title}</div>
            {subtitle && <div className="text-xs text-graphite-400">{subtitle}</div>}
          </div>
        </div>
        <div className="flex items-center gap-4 text-sm">
          {right}
          {user && (
            <div className="flex items-center gap-3">
              <span className="text-graphite-400">{user.name} · <span className="uppercase">{user.role}</span></span>
              <button onClick={logout} className="btn-ghost !py-1 !px-3 !text-xs">Logout</button>
            </div>
          )}
        </div>
      </header>
      <main className="flex-1 p-6">{children}</main>
    </div>
  )
}

export function Card({ title, className = '', children, accent }) {
  return (
    <section className={`card ${accent ? 'border-l-4 border-l-cat' : ''} ${className}`}>
      {title && <div className="card-title">{title}</div>}
      {children}
    </section>
  )
}

export function Stat({ label, value, unit, sub, tone = '' }) {
  return (
    <div>
      <div className="card-title !mb-1">{label}</div>
      <div className={`stat ${tone}`}>{value}{unit && <span className="text-base font-sans font-normal text-graphite-400 ml-1">{unit}</span>}</div>
      {sub && <div className="text-xs text-graphite-400 mt-1">{sub}</div>}
    </div>
  )
}

const TONE = {
  critical: 'bg-red-600 text-white', warning: 'bg-cat text-graphite-950', info: 'bg-graphite-600 text-slate-100',
  ok: 'bg-emerald-600 text-white',
}
export function Badge({ tone = 'info', children }) {
  return <span className={`badge ${TONE[tone] || TONE.info}`}>{children}</span>
}

export function StatusBadge({ status }) {
  const tone = { active: 'ok', completed: 'info', blocked: 'critical', suspended: 'warning', pending: 'info' }[status] || 'info'
  return <Badge tone={tone}>{status}</Badge>
}

export function AlertRow({ a, onResolve }) {
  const tone = a.severity === 'critical' ? 'critical' : a.type === 'anomaly' ? 'warning' : 'info'
  return (
    <div className={`flex items-start gap-3 p-3 rounded border ${a.resolved ? 'border-graphite-700 opacity-50' : 'border-graphite-600 bg-graphite-900'}`}>
      <Badge tone={tone}>{a.type.replace('_', ' ')}</Badge>
      <div className="flex-1 text-sm">
        <div>{a.message}</div>
        <div className="text-[11px] text-graphite-400 mt-1">
          {a.task_id ? `Task #${a.task_id} · ` : ''}{fmtTime(a.timestamp)}{a.escalated ? ' · ESCALATED' : ''}
        </div>
      </div>
      {onResolve && !a.resolved && <button className="btn-ghost !py-1 !px-2 !text-[11px]" onClick={() => onResolve(a)}>Resolve</button>}
    </div>
  )
}

export function fmtTime(ts) {
  if (!ts) return '—'
  const d = new Date(ts.endsWith('Z') ? ts : ts + 'Z')
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function fmtMin(m) {
  if (m == null) return '—'
  return `${Math.round(m)} min`
}

export function Progress({ pct, tone = 'bg-cat' }) {
  return (
    <div className="h-3 w-full bg-graphite-900 rounded overflow-hidden border border-graphite-700">
      <div className={`h-full ${tone} transition-all`} style={{ width: `${Math.min(100, pct || 0)}%` }} />
    </div>
  )
}
