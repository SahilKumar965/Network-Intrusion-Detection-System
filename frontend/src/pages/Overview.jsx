import { Link } from 'react-router-dom'
import {
  AlertTable, Card, classColor, EmptyState, ErrorBox, fmtInt, fmtPct, labelName, Loading, PageHeader, RankedList, Stat, useApi,
} from '../components'

const plural = (n, word) => `${fmtInt(n)} ${word}${n === 1 ? '' : 's'}`

/** One strip showing every record: benign in grey, each attack type in its severity colour. */
function CompositionStrip({ benign, attacks, total }) {
  const segments = [['BENIGN', benign], ...attacks]
  return (
    <div className="flex h-7 w-full gap-0.5 overflow-hidden rounded-md">
      {segments.map(([label, n]) => (
        <div key={label} title={`${labelName(label)}: ${fmtInt(n)} (${fmtPct(n / total)})`}
          className="h-full first:rounded-l-md last:rounded-r-md"
          style={{ flex: `${n} 0 3px`, background: label === 'BENIGN' ? '#3a3a3e' : classColor(label) }} />
      ))}
    </div>
  )
}

export default function Overview() {
  const { data: s, error, loading, reload } = useApi('/api/v1/dashboard/stats')

  if (loading) return <Loading />
  if (error) return <ErrorBox message={error} onRetry={reload} />

  const attacks = Object.entries(s.class_distribution).filter(([k]) => k !== 'BENIGN').sort((a, b) => b[1] - a[1])
  const share = s.total_records ? s.malicious_records / s.total_records : 0
  const sev = { HIGH: 0, MEDIUM: 0, LOW: 0, ...s.severity_counts }

  return (
    <>
      <PageHeader title="Overview" subtitle={`Every flow analysed across ${plural(s.uploads, 'upload')}`} />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Flows analysed" value={fmtInt(s.total_records)} hint={plural(s.uploads, 'upload')} />
        <Stat label="Suspicious flows" value={fmtInt(s.malicious_records)} tone="text-high" hint={`${fmtPct(share)} of all flows`} />
        <Stat label="Benign flows" value={fmtInt(s.benign_records)} hint={s.total_records ? `${fmtPct(1 - share)} of all flows` : null} />
        <Stat label="High-severity alerts" value={fmtInt(sev.HIGH)} hint={`${fmtInt(sev.MEDIUM)} medium · ${fmtInt(sev.LOW)} low`} />
      </div>

      {s.total_records === 0 ? (
        <div className="mt-6">
          <EmptyState>
            No traffic analysed yet. <Link to="/traffic" className="text-fg underline">Upload a CSV</Link> to see results here
          </EmptyState>
        </div>
      ) : (
        <>
          <Card title="Traffic composition" className="mt-6">
            <CompositionStrip benign={s.benign_records} attacks={attacks} total={s.total_records} />
            <div className="mt-2 flex justify-between font-mono text-xs text-fg3">
              <span>Benign {fmtPct(1 - share)}</span>
              <span>Attacks {fmtPct(share)}</span>
            </div>
            <div className="mt-8 grid gap-8 lg:grid-cols-3">
              <div>
                <div className="text-[13px] text-fg2">Attack types found</div>
                <div className="mt-2 font-mono text-[28px] leading-8 font-medium text-fg">{attacks.length}</div>
                <p className="mt-3 text-[13px] text-fg3">
                  Bars use the alert severity: red for attacks that do damage, amber for reconnaissance like port scans
                </p>
              </div>
              <div className="lg:col-span-2">
                {attacks.length
                  ? <RankedList rows={attacks.map(([k, v]) => ({ key: k, label: labelName(k), value: v }))} total={s.malicious_records} color={classColor} />
                  : <EmptyState>No attacks detected</EmptyState>}
              </div>
            </div>
          </Card>

          <Card title="Recent alerts" className="mt-6" flush
            actions={<Link to="/alerts" className="text-xs text-fg2 transition-colors duration-150 hover:text-fg">View all alerts</Link>}>
            <AlertTable alerts={s.recent_alerts} />
          </Card>
        </>
      )}
    </>
  )
}
