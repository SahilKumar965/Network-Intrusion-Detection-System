// Shared UI pieces: layout, cards, labels, tables, charts, loading/error states.
import { useEffect, useState } from 'react'
import createPlotlyComponent from 'react-plotly.js/factory'
import Plotly from 'plotly.js-dist-min'
import { NavLink, Link } from 'react-router-dom'
import { Activity, BrainCircuit, LayoutDashboard, ShieldAlert } from 'lucide-react'
import { api } from './api'

const Plot = createPlotlyComponent(Plotly)

// Colour only carries severity. Attack classes are told apart by name, and coloured by how serious they are.
export const SEVERITY_COLOR = { HIGH: 'var(--color-high)', MEDIUM: 'var(--color-medium)', LOW: 'var(--color-fg3)' }
const CLASS_SEVERITY = { DoS: 'HIGH', DDoS: 'HIGH', BruteForce: 'HIGH', WebAttack: 'HIGH', Bot: 'HIGH', PortScan: 'MEDIUM' }
export const classColor = (label) => SEVERITY_COLOR[CLASS_SEVERITY[label]] ?? 'var(--color-fg3)'
const LABEL_NAMES = { BENIGN: 'Benign', BruteForce: 'Brute force', WebAttack: 'Web attack', PortScan: 'Port scan' }
export const labelName = (label) => LABEL_NAMES[label] ?? label

export const fmtInt = (n) => (n ?? 0).toLocaleString('en-US')
export const fmtPct = (x, digits = 2) => `${(x * 100).toFixed(digits)}%`
export const fmtTime = (iso) =>
  new Date(iso.endsWith('Z') || iso.includes('+') ? iso : `${iso}Z`).toLocaleString('en-GB', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  })

/** Fetch `path` on mount and whenever `path` changes. */
export function useApi(path) {
  const [state, setState] = useState({ data: null, error: null, loading: true })
  const [reloadKey, setReloadKey] = useState(0)
  useEffect(() => {
    if (!path) return
    let alive = true
    setState((s) => ({ ...s, loading: true, error: null }))
    api(path)
      .then((data) => alive && setState({ data, error: null, loading: false }))
      .catch((error) => alive && setState({ data: null, error: error.message, loading: false }))
    return () => { alive = false }
  }, [path, reloadKey])
  return { ...state, reload: () => setReloadKey((k) => k + 1) }
}

const NAV = [
  ['/', 'Overview', LayoutDashboard],
  ['/traffic', 'Traffic analysis', Activity],
  ['/alerts', 'Alerts', ShieldAlert],
  ['/model', 'Model performance', BrainCircuit],
]

export function Layout({ children }) {
  const health = useApi('/health')
  const ok = health.data?.status === 'ok'
  return (
    <div className="flex min-h-full">
      <div className="w-60 shrink-0 border-r border-line bg-sidebar">
      <aside className="sticky top-0 flex h-screen flex-col px-3 py-5">
        <div className="mb-6 flex h-8 items-center gap-2.5 px-2.5">
          <img src="/favicon.svg" alt="" className="h-5 w-5" />
          <span className="text-[15px] font-semibold text-fg">NIDS Console</span>
        </div>
        <nav className="space-y-0.5">
          {NAV.map(([to, label, Icon]) => (
            <NavLink key={to} to={to} end={to === '/'}
              className={({ isActive }) =>
                `flex h-9 items-center gap-2.5 rounded-lg px-2.5 text-sm transition-colors duration-150 ${isActive
                  ? 'bg-raised text-fg shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]'
                  : 'text-fg2 hover:bg-card hover:text-fg'}`}>
              {({ isActive }) => <>
                <Icon size={16} strokeWidth={1.5} className={isActive ? 'text-accent' : 'text-fg3'} />
                {label}
              </>}
            </NavLink>
          ))}
        </nav>
        <div className="mt-auto flex items-center gap-2 px-2.5 font-mono text-xs text-fg3">
          <span className={`h-1.5 w-1.5 rounded-full ${ok ? 'bg-positive' : health.loading ? 'bg-fg3' : 'bg-high'}`} />
          {ok ? 'API online · model loaded' : health.loading ? 'Checking API' : 'API offline'}
        </div>
      </aside>
      </div>
      <main className="min-w-0 flex-1 px-8 py-8">
        <div className="mx-auto max-w-[1400px]">{children}</div>
      </main>
    </div>
  )
}

export function PageHeader({ title, subtitle, children }) {
  return (
    <div className="mb-6 flex items-end justify-between gap-4">
      <div>
        <h1 className="text-[28px] leading-9 font-medium text-fg">{title}</h1>
        {subtitle && <p className="mt-1 text-sm text-fg2">{subtitle}</p>}
      </div>
      {children}
    </div>
  )
}

export function Card({ title, children, className = '', actions, flush = false }) {
  return (
    <section className={`rounded-xl border border-line bg-card ${className}`}>
      {title && (
        <div className="flex h-12 items-center justify-between border-b border-line px-5">
          <h2 className="text-sm font-medium text-fg">{title}</h2>
          {actions}
        </div>
      )}
      <div className={flush ? '' : 'p-5'}>{children}</div>
    </section>
  )
}

export function Stat({ label, value, hint, tone = 'text-fg' }) {
  return (
    <div className="rounded-xl border border-line bg-card px-5 py-4">
      <div className="text-[13px] text-fg2">{label}</div>
      <div className={`mt-2 font-mono text-[28px] leading-8 font-medium tabular-nums ${tone}`}>{value}</div>
      {hint && <div className="mt-1 text-xs text-fg3">{hint}</div>}
    </div>
  )
}

export function SeverityBadge({ severity }) {
  if (!severity) return <span className="text-xs text-fg3">None</span>
  return (
    <span className="inline-flex items-center gap-1.5 font-mono text-xs" style={{ color: SEVERITY_COLOR[severity] }}>
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: SEVERITY_COLOR[severity] }} />
      {severity}
    </span>
  )
}

export function ClassLabel({ label }) {
  return (
    <span className="inline-flex items-center gap-2 text-sm text-fg">
      <span className="h-1.5 w-1.5 rounded-full" style={{ background: classColor(label) }} />
      {labelName(label)}
    </span>
  )
}

/** The signature: a connection written like a packet header. */
export function Flow({ src, dst, port, className = '' }) {
  if (!src && !dst) return <span className="text-fg3">—</span>
  return (
    <span className={`font-mono whitespace-nowrap ${className}`}>
      <span className="text-fg2">{src ?? '?'}</span>
      <span className="px-1.5 text-fg3">→</span>
      <span className="text-fg">{dst ?? '?'}</span>
      {port != null && <span className="text-fg3">:{port}</span>}
    </span>
  )
}

export function Loading() {
  return <div className="py-12 text-center text-sm text-fg3">Loading…</div>
}

export function ErrorBox({ message, onRetry }) {
  return (
    <div className="rounded-lg border border-high/30 bg-high/10 px-4 py-3 text-sm text-fg">
      {message}
      {onRetry && <button onClick={onRetry} className="ml-3 text-fg2 underline hover:text-fg">Retry</button>}
    </div>
  )
}

export function EmptyState({ children }) {
  return <div className="rounded-xl border border-dashed border-line-strong px-6 py-12 text-center text-sm text-fg2">{children}</div>
}

export const buttonGhost =
  'h-8 rounded-lg border border-line bg-raised px-3 text-xs text-fg2 transition-colors duration-150 enabled:hover:border-line-strong enabled:hover:text-fg disabled:opacity-40'

export function Pagination({ page, pageSize, total, onPage }) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  return (
    <div className="flex h-14 items-center justify-between border-t border-line px-5 text-xs text-fg3">
      <span className="font-mono tabular-nums">{fmtInt(total)} rows · page {fmtInt(page)} of {fmtInt(pages)}</span>
      <div className="flex gap-2">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)} className={buttonGhost}>Previous</button>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)} className={buttonGhost}>Next</button>
      </div>
    </div>
  )
}

export const th = 'h-10 px-5 text-left text-xs font-normal whitespace-nowrap text-fg3'
export const td = 'h-11 px-5'

export function AlertTable({ alerts }) {
  if (!alerts.length) return <div className="p-5"><EmptyState>No alerts</EmptyState></div>
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-sm">
        <thead className="border-b border-line">
          <tr>
            <th className={th}>Alert</th>
            <th className={th}>Severity</th>
            <th className={th}>Category</th>
            <th className={th}>Connection</th>
            <th className={`${th} text-right`}>Confidence</th>
            <th className={th}>Flow time</th>
            <th className={th}>Detected</th>
          </tr>
        </thead>
        <tbody>
          {alerts.map((a) => (
            <tr key={a.id} className="border-b border-line last:border-0 transition-colors duration-150 hover:bg-raised/60">
              <td className={td}>
                <Link to={`/alerts/${a.id}`} className="font-mono text-fg2 hover:text-fg hover:underline">#{a.id}</Link>
              </td>
              <td className={td}><SeverityBadge severity={a.severity} /></td>
              <td className={td}><ClassLabel label={a.category} /></td>
              <td className={`${td} text-[13px]`}><Flow src={a.source_ip} dst={a.destination_ip} port={a.destination_port} /></td>
              <td className={`${td} text-right font-mono tabular-nums ${a.confidence < 0.6 ? 'text-medium' : 'text-fg'}`}>{fmtPct(a.confidence, 1)}</td>
              <td className={`${td} font-mono text-xs text-fg3`}>{a.flow_timestamp ?? '—'}</td>
              <td className={`${td} text-xs text-fg3`}>{fmtTime(a.created_at)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Ranked list with thin bars: the compact way to show a breakdown. */
export function RankedList({ rows, total, color = () => 'var(--color-fg3)' }) {
  const max = Math.max(...rows.map((r) => r.value), 1)
  return (
    <ul className="space-y-3">
      {rows.map((r) => (
        <li key={r.key}>
          <div className="flex items-baseline justify-between gap-3 text-sm">
            <span className="text-fg">{r.label}</span>
            <span className="font-mono text-xs tabular-nums text-fg2">
              {fmtInt(r.value)}{total ? <span className="ml-2 text-fg3">{fmtPct(r.value / total)}</span> : null}
            </span>
          </div>
          <div className="mt-1.5 h-1 rounded-full bg-raised">
            <div className="h-1 rounded-full" style={{ width: `${Math.max((r.value / max) * 100, 0.8)}%`, background: color(r.key) }} />
          </div>
        </li>
      ))}
    </ul>
  )
}

const AXIS = { gridcolor: 'rgba(237,237,237,0.06)', zerolinecolor: 'rgba(237,237,237,0.10)', linecolor: 'rgba(237,237,237,0.10)', tickfont: { family: 'IBM Plex Mono', size: 11, color: '#85858b' } }
const BASE_LAYOUT = {
  paper_bgcolor: 'rgba(0,0,0,0)',
  plot_bgcolor: 'rgba(0,0,0,0)',
  font: { family: 'IBM Plex Sans', color: '#a1a1a6', size: 12 },
  margin: { t: 8, r: 8, b: 40, l: 48 },
  hoverlabel: { bgcolor: '#232325', bordercolor: 'rgba(237,237,237,0.14)', font: { family: 'IBM Plex Sans', color: '#ededed' } },
  xaxis: AXIS,
  yaxis: AXIS,
  showlegend: false,
}

export function Chart({ data, layout = {}, height = 300 }) {
  return (
    <Plot
      data={data}
      layout={{ ...BASE_LAYOUT, ...layout, xaxis: { ...AXIS, ...layout.xaxis }, yaxis: { ...AXIS, ...layout.yaxis }, height, autosize: true }}
      config={{ displayModeBar: false, responsive: true }}
      useResizeHandler
      style={{ width: '100%' }}
    />
  )
}
