import { useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { Download, FileUp } from 'lucide-react'
import { api, qs } from '../api'
import {
  buttonGhost, Card, ClassLabel, classColor, EmptyState, ErrorBox, fmtInt, fmtPct, fmtTime, labelName, Loading, PageHeader,
  Pagination, RankedList, Stat, td, th, useApi,
} from '../components'

const PAGE_SIZE = 25

function UploadForm({ onDone }) {
  const [file, setFile] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)
  const input = useRef(null)

  async function submit(e) {
    e.preventDefault()
    if (!file) return
    setBusy(true)
    setError(null)
    const body = new FormData()
    body.append('file', file)
    try {
      onDone(await api('/api/v1/upload', { method: 'POST', body }))
      setFile(null)
      input.current.value = ''
    } catch (err) {
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card title="Upload traffic CSV">
      <form onSubmit={submit} className="flex flex-wrap items-center gap-3">
        <input ref={input} id="csv" type="file" accept=".csv,text/csv" className="sr-only"
          onChange={(e) => setFile(e.target.files[0] ?? null)} />
        <label htmlFor="csv" className={`${buttonGhost} inline-flex cursor-pointer items-center gap-2 text-sm`}>
          <FileUp size={16} strokeWidth={1.5} />Choose CSV
        </label>
        <span className={`font-mono text-[13px] ${file ? 'text-fg' : 'text-fg3'}`}>
          {file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : 'No file chosen'}
        </span>
        <button disabled={!file || busy}
          className="ml-auto h-8 rounded-lg bg-fg px-4 text-sm font-medium text-page shadow-[inset_0_1px_0_rgb(255_255_255/0.12)] transition-[background-color,transform,opacity] duration-150 enabled:hover:bg-white enabled:active:scale-[0.98] disabled:opacity-40">
          {busy ? 'Analysing…' : 'Analyse'}
        </button>
      </form>
      <p className="mt-3 text-xs text-fg3">CICIDS2017 flow CSV with the 78 feature columns, up to 50 MB</p>
      {error && <div className="mt-3"><ErrorBox message={error} /></div>}
    </Card>
  )
}

function Results({ upload }) {
  const [filters, setFilters] = useState({ label: '', malicious_only: false, min_confidence: 0, row_index: '' })
  const [page, setPage] = useState(1)
  const set = (k, v) => { setFilters((f) => ({ ...f, [k]: v })); setPage(1) }
  const results = useApi(`/api/v1/uploads/${upload.id}/results?${qs({ ...filters, page, page_size: PAGE_SIZE })}`)
  const counts = Object.entries(upload.class_counts).sort((a, b) => b[1] - a[1])

  return (
    <>
      <div className="mt-6 grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Flows classified" value={fmtInt(upload.row_count)} hint={upload.filename} />
        <Stat label="Suspicious flows" value={fmtInt(upload.malicious_count)} tone="text-high"
          hint={`${fmtPct(upload.malicious_count / upload.row_count)} of this file`} />
        <Stat label="Invalid cells" value={fmtInt(upload.invalid_cells)} hint="Non-numeric values, filled with the median" />
        <Stat label="Uploaded" value={<span className="text-lg">{fmtTime(upload.created_at)}</span>} hint={`Upload #${upload.id}`} />
      </div>

      <div className="mt-6 grid items-start gap-4 lg:grid-cols-3">
        <Card title="Predicted classes">
          <RankedList rows={counts.map(([k, v]) => ({ key: k, label: labelName(k), value: v }))} total={upload.row_count} color={classColor} />
        </Card>

        <Card title="Predictions" className="lg:col-span-2" flush
          actions={
            <a href={`/api/v1/uploads/${upload.id}/results.csv`}
              className="inline-flex items-center gap-1.5 text-xs text-fg2 transition-colors duration-150 hover:text-fg">
              <Download size={14} strokeWidth={1.5} />Download CSV
            </a>}>
          <div className="flex flex-wrap items-center gap-4 border-b border-line px-5 py-3 text-[13px] text-fg2">
            <select value={filters.label} onChange={(e) => set('label', e.target.value)} aria-label="Filter by class">
              <option value="">All classes</option>
              {counts.map(([c]) => <option key={c} value={c}>{labelName(c)}</option>)}
            </select>
            <label className="flex items-center gap-2">
              <input type="checkbox" checked={filters.malicious_only} onChange={(e) => set('malicious_only', e.target.checked)} />
              Suspicious only
            </label>
            <label className="flex items-center gap-2">
              Min confidence
              <input type="range" min="0" max="1" step="0.05" value={filters.min_confidence} className="w-24"
                onChange={(e) => set('min_confidence', Number(e.target.value))} />
              <span className="w-9 font-mono text-xs tabular-nums text-fg">{fmtPct(filters.min_confidence, 0)}</span>
            </label>
            <input type="number" min="0" placeholder="Row" value={filters.row_index} aria-label="Find row" className="ml-auto w-24"
              onChange={(e) => set('row_index', e.target.value)} />
          </div>

          {results.error ? <div className="p-5"><ErrorBox message={results.error} /></div>
            : !results.data ? <Loading />
            : results.data.items.length === 0 ? <div className="p-5"><EmptyState>No rows match these filters</EmptyState></div>
            : (
              <>
                <table className="w-full text-sm">
                  <thead className="border-b border-line">
                    <tr>
                      <th className={th}>Row</th>
                      <th className={th}>Prediction</th>
                      <th className={th}>Confidence</th>
                    </tr>
                  </thead>
                  <tbody className={results.loading ? 'opacity-50' : ''}>
                    {results.data.items.map((r) => (
                      <tr key={r.row_index} className="border-b border-line last:border-0">
                        <td className={`${td} font-mono text-fg3 tabular-nums`}>{r.row_index}</td>
                        <td className={td}><ClassLabel label={r.label} /></td>
                        <td className={td}>
                          <div className="flex items-center gap-3">
                            <div className="h-1 w-28 rounded-full bg-raised">
                              <div className="h-1 rounded-full" style={{ width: `${r.confidence * 100}%`, background: r.confidence < 0.6 ? 'var(--color-medium)' : 'var(--color-fg3)' }} />
                            </div>
                            <span className={`font-mono text-xs tabular-nums ${r.confidence < 0.6 ? 'text-medium' : 'text-fg2'}`}>{fmtPct(r.confidence, 1)}</span>
                          </div>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                <Pagination page={page} pageSize={PAGE_SIZE} total={results.data.total} onPage={setPage} />
              </>
            )}
        </Card>
      </div>
      {upload.malicious_count > 0 && (
        <p className="mt-4 text-[13px] text-fg3">
          Each suspicious flow also became an alert.{' '}
          <Link to={`/alerts?upload_id=${upload.id}`} className="text-fg2 underline hover:text-fg">Investigate alerts from this upload</Link>
        </p>
      )}
    </>
  )
}

function RecentUploads({ current, onPick, reloadKey }) {
  const { data, error } = useApi(`/api/v1/uploads?limit=10&_=${reloadKey}`)
  if (error) return <div className="mt-4"><ErrorBox message={error} /></div>
  if (!data?.length) return null
  return (
    <Card title="Recent uploads" className="mt-4" flush>
      <ul>
        {data.map((u) => {
          const active = String(u.id) === current
          return (
            <li key={u.id} className="border-b border-line last:border-0">
              <button onClick={() => onPick(u.id)}
                className={`flex h-11 w-full items-center gap-4 px-5 text-left text-sm transition-colors duration-150 ${active ? 'bg-raised' : 'hover:bg-raised/60'}`}>
                <span className={`h-1.5 w-1.5 rounded-full ${active ? 'bg-accent' : 'bg-transparent'}`} />
                <span className="w-10 font-mono text-xs text-fg3">#{u.id}</span>
                <span className="flex-1 truncate text-fg">{u.filename}</span>
                <span className="font-mono text-xs tabular-nums text-fg2">{fmtInt(u.row_count)} flows</span>
                <span className="w-32 text-right font-mono text-xs tabular-nums text-high">{fmtInt(u.malicious_count)} suspicious</span>
                <span className="w-40 text-right text-xs text-fg3">{fmtTime(u.created_at)}</span>
              </button>
            </li>
          )
        })}
      </ul>
    </Card>
  )
}

export default function Traffic() {
  const [params, setParams] = useSearchParams()
  const uploadId = params.get('upload')
  const upload = useApi(uploadId ? `/api/v1/uploads/${uploadId}` : null)

  return (
    <>
      <PageHeader title="Traffic analysis" subtitle="Upload recorded network flows and see how each one was classified" />
      <UploadForm onDone={(u) => setParams({ upload: u.id })} />
      <RecentUploads current={uploadId} reloadKey={uploadId} onPick={(id) => setParams({ upload: id })} />
      {uploadId && (upload.error ? <div className="mt-6"><ErrorBox message={upload.error} /></div>
        : upload.data && String(upload.data.id) === uploadId ? <Results key={uploadId} upload={upload.data} /> : <Loading />)}
    </>
  )
}
