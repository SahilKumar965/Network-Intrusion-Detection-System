import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ArrowLeft, X } from 'lucide-react'
import { qs } from '../api'
import {
  AlertTable, buttonGhost, Card, ClassLabel, ErrorBox, Flow, fmtPct, fmtTime, labelName, Loading, PageHeader, Pagination,
  SeverityBadge, useApi,
} from '../components'

const PAGE_SIZE = 50
const CATEGORIES = ['DoS', 'DDoS', 'PortScan', 'BruteForce', 'WebAttack', 'Bot']

export function AlertsList() {
  // Filters live in the URL so a filtered view can be bookmarked or linked from other pages.
  const [params, setParams] = useSearchParams()
  const filters = { severity: params.get('severity') ?? '', category: params.get('category') ?? '', upload_id: params.get('upload_id') ?? '' }
  const page = Number(params.get('page') ?? 1)
  const update = (changes) => setParams(qs({ ...filters, page, ...changes }))
  const { data, error, loading } = useApi(`/api/v1/alerts?${qs({ ...filters, page, page_size: PAGE_SIZE })}`)

  return (
    <>
      <PageHeader title="Alerts" subtitle="Every flow the model classified as an attack, newest first" />
      <Card flush>
        <div className="flex flex-wrap items-center gap-3 border-b border-line px-5 py-3">
          <select value={filters.severity} onChange={(e) => update({ severity: e.target.value, page: 1 })} aria-label="Severity">
            <option value="">All severities</option>
            {['HIGH', 'MEDIUM', 'LOW'].map((s) => <option key={s} value={s}>{s[0] + s.slice(1).toLowerCase()}</option>)}
          </select>
          <select value={filters.category} onChange={(e) => update({ category: e.target.value, page: 1 })} aria-label="Category">
            <option value="">All categories</option>
            {CATEGORIES.map((c) => <option key={c} value={c}>{labelName(c)}</option>)}
          </select>
          {filters.upload_id && (
            <button onClick={() => update({ upload_id: '', page: 1 })} className={`${buttonGhost} inline-flex items-center gap-1.5`}>
              Upload #{filters.upload_id}<X size={14} strokeWidth={1.5} />
            </button>
          )}
        </div>
        {error ? <div className="p-5"><ErrorBox message={error} /></div> : !data ? <Loading /> : (
          <div className={loading ? 'opacity-50' : ''}>
            <AlertTable alerts={data.items} />
            {data.total > 0 && <Pagination page={page} pageSize={PAGE_SIZE} total={data.total} onPage={(p) => update({ page: p })} />}
          </div>
        )}
      </Card>
    </>
  )
}

const PLAIN = ['Source Port', 'Destination Port', 'Protocol'] // identifiers, not quantities: no thousands separator
const fmtValue = (v, key) => (v === null || v === undefined ? '—'
  : typeof v === 'number' && !PLAIN.includes(key) ? v.toLocaleString('en-US', { maximumFractionDigits: 4 }) : String(v))

function Rows({ entries }) {
  return (
    <dl>
      {entries.map(([k, v]) => (
        <div key={k} className="flex h-10 items-center justify-between gap-4 border-b border-line text-sm last:border-0">
          <dt className="text-fg2">{k}</dt>
          <dd className={`text-right tabular-nums text-fg ${typeof v === 'object' ? '' : 'font-mono'}`}>{v}</dd>
        </div>
      ))}
    </dl>
  )
}

export function AlertDetail() {
  const { id } = useParams()
  const { data: a, error, loading } = useApi(`/api/v1/alerts/${id}`)

  if (loading) return <Loading />
  if (error) return <ErrorBox message={error} />

  const context = ['Source IP', 'Source Port', 'Destination IP', 'Destination Port', 'Protocol', 'Timestamp']
  const features = Object.entries(a.features).filter(([k]) => !context.includes(k))

  return (
    <>
      <Link to="/alerts" className="mb-4 inline-flex items-center gap-1.5 text-[13px] text-fg2 transition-colors duration-150 hover:text-fg">
        <ArrowLeft size={14} strokeWidth={1.5} />All alerts
      </Link>
      <PageHeader title={`Alert #${a.id} · ${labelName(a.category)}`} subtitle={`${a.filename}, row ${a.row_index}`} />

      <div className="mb-6 rounded-xl border border-line bg-card px-5 py-5">
        <div className="text-[13px] text-fg2">Connection</div>
        <Flow src={a.features['Source IP']} dst={a.features['Destination IP']} port={a.features['Destination Port']} className="mt-2 block text-xl" />
        <div className="mt-3 flex flex-wrap gap-6 font-mono text-xs text-fg3">
          <span>source port {fmtValue(a.features['Source Port'], 'Source Port')}</span>
          <span>protocol {fmtValue(a.features.Protocol, 'Protocol')}</span>
          <span>flow time {a.flow_timestamp ?? '—'}</span>
        </div>
      </div>

      <div className="grid items-start gap-4 lg:grid-cols-2">
        <Card title="Classification">
          <Rows entries={[
            ['Category', <ClassLabel key="c" label={a.category} />],
            ['Severity', <SeverityBadge key="s" severity={a.severity} />],
            ['Model confidence', <span key="p" className={`font-mono ${a.confidence < 0.6 ? 'text-medium' : ''}`}>{fmtPct(a.confidence, 1)}</span>],
            ['Detected', fmtTime(a.created_at)],
          ]} />
          <p className="mt-4 text-xs text-fg3">
            High for DoS, DDoS, brute force, web attacks and bots. Medium for port scans. One level lower when confidence is under 60%.
          </p>
          <p className="mt-2 text-xs text-fg3">
            Source and destination IP, source port and timestamp are shown for investigation only; the model never sees them.
            Destination port and protocol are model features.
          </p>
        </Card>

        <Card title="Key traffic features">
          <Rows entries={features.map(([k, v]) => [k, fmtValue(v, k)])} />
        </Card>
      </div>
    </>
  )
}
