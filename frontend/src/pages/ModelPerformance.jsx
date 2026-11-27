import { useState } from 'react'
import { Card, Chart, ClassLabel, ErrorBox, fmtInt, fmtPct, labelName, Loading, PageHeader, Stat, td, th, useApi } from '../components'

const NAMES = { random_forest: 'Random Forest', xgboost: 'XGBoost' }

/**
 * Correct predictions (diagonal) in quiet grey; mistakes (off-diagonal) in amber that strengthens with the count,
 * so the confusions are what you see first. Both ranges are packed into one 0-1 colour scale.
 */
function ConfusionMatrix({ cm }) {
  const names = cm.labels.map(labelName)
  const maxOff = Math.max(1, ...cm.matrix.flatMap((row, i) => row.filter((_, j) => j !== i)))
  const z = cm.matrix.map((row, i) => {
    const total = row.reduce((a, b) => a + b, 0) || 1
    // Diagonal stays below 0.49 so a perfect class never touches the "zero mistakes" colour at exactly 0.5.
    return row.map((v, j) => (i === j ? 0.49 * (v / total)
      : v === 0 ? 0.5 : 0.5 + 0.5 * (0.1 + 0.9 * Math.log10(1 + v) / Math.log10(1 + maxOff))))
  })
  const text = cm.matrix.map((row, i) => row.map((v, j) => (v === 0 && i !== j ? '·' : v.toLocaleString('en-US'))))
  return (
    <Chart height={400} data={[{
      type: 'heatmap', x: names, y: names, z, zmin: 0, zmax: 1, showscale: false, xgap: 2, ygap: 2,
      colorscale: [[0, '#232325'], [0.49, '#48484d'], [0.4901, '#19191b'], [0.5, '#19191b'], [0.55, '#2e2a22'], [1, '#a8732b']],
      text, texttemplate: '%{text}', textfont: { family: 'IBM Plex Mono', size: 12, color: '#ededed' },
      customdata: cm.matrix,
      hovertemplate: 'Actual %{y}, predicted %{x}<br>%{customdata:,} flows<extra></extra>',
    }]} layout={{
      margin: { t: 8, r: 8, b: 56, l: 96 },
      xaxis: { title: { text: 'Predicted', font: { size: 12, color: '#85858b' } }, tickangle: 0, showgrid: false, tickfont: { family: 'IBM Plex Sans', size: 12, color: '#a1a1a6' } },
      yaxis: { title: { text: 'Actual', font: { size: 12, color: '#85858b' }, standoff: 12 }, autorange: 'reversed', showgrid: false, automargin: true, tickfont: { family: 'IBM Plex Sans', size: 12, color: '#a1a1a6' } },
    }} />
  )
}

function F1List({ info, classes, shown }) {
  const others = Object.keys(info.models).filter((m) => m !== shown)
  return (
    <ul className="space-y-4">
      {classes.map((c) => {
        const f1 = info.models[shown].test.per_class[c]['f1-score']
        return (
          <li key={c}>
            <div className="flex items-baseline justify-between text-sm">
              <span className="text-fg">{labelName(c)}</span>
              <span className={`font-mono text-xs tabular-nums ${f1 < 0.9 ? 'text-medium' : 'text-fg'}`}>{fmtPct(f1)}</span>
            </div>
            <div className="mt-1.5 h-1 rounded-full bg-raised">
              <div className="h-1 rounded-full bg-fg2" style={{ width: `${f1 * 100}%` }} />
            </div>
            {others.map((m) => (
              <div key={m} className="mt-1 h-0.5 rounded-full bg-raised">
                <div className="h-0.5 rounded-full bg-fg3/60" style={{ width: `${info.models[m].test.per_class[c]['f1-score'] * 100}%` }} />
              </div>
            ))}
          </li>
        )
      })}
      <li className="pt-1 text-xs text-fg3">Thin line underneath: {others.map((m) => NAMES[m] ?? m).join(', ')}</li>
    </ul>
  )
}

export default function ModelPerformance() {
  const { data: info, error, loading } = useApi('/api/v1/model/info')
  const [shown, setShown] = useState(null)

  if (loading) return <Loading />
  if (error) return <ErrorBox message={error} />

  const selected = info.selected_model
  const modelName = shown ?? selected
  const test = info.models[modelName].test
  const modelKeys = Object.keys(info.models)
  const classes = info.classes

  return (
    <>
      <PageHeader title="Model performance"
        subtitle={`Held-out test set: ${fmtInt(info.split_sizes.test)} flows the model never saw · trained ${new Date(info.trained_at).toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })}`}>
        <div className="flex rounded-lg border border-line bg-sidebar p-0.5 text-[13px]" role="tablist">
          {modelKeys.map((m) => (
            <button key={m} role="tab" aria-selected={m === modelName} onClick={() => setShown(m)}
              className={`h-7 rounded-md px-3 transition-colors duration-150 ${m === modelName ? 'bg-raised text-fg' : 'text-fg2 hover:text-fg'}`}>
              {NAMES[m] ?? m}
              {m === selected && <span className="ml-2 font-mono text-[11px] text-fg3">in use</span>}
            </button>
          ))}
        </div>
      </PageHeader>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <Stat label="Macro F1" value={fmtPct(test.macro.f1)} tone="text-accent" hint="Selection metric, every class weighted equally" />
        <Stat label="Macro precision" value={fmtPct(test.macro.precision)} hint="Of alerts raised, how many were real" />
        <Stat label="Macro recall" value={fmtPct(test.macro.recall)} hint="Of real attacks, how many were caught" />
        <Stat label="Accuracy" value={fmtPct(test.accuracy)} hint="Misleading alone: 83% of flows are benign" />
      </div>

      <div className="mt-6 grid items-start gap-4 lg:grid-cols-3">
        <Card title={`Confusion matrix · ${NAMES[modelName]}`} className="lg:col-span-2">
          <ConfusionMatrix cm={test.confusion_matrix} />
          <p className="mt-3 text-xs text-fg3">
            Grey diagonal: flows classified correctly. Amber: mistakes, brighter where there are more of them
          </p>
        </Card>
        <Card title="F1-score per class">
          <F1List info={info} classes={classes} shown={modelName} />
        </Card>
      </div>

      <Card title={`Per-class metrics · ${NAMES[modelName]}`} className="mt-6" flush>
        <table className="w-full text-sm">
          <thead className="border-b border-line">
            <tr>
              <th className={th}>Class</th>
              <th className={`${th} text-right`}>Precision</th>
              <th className={`${th} text-right`}>Recall</th>
              <th className={`${th} text-right`}>F1</th>
              <th className={`${th} text-right`}>Test flows</th>
            </tr>
          </thead>
          <tbody className="font-mono tabular-nums">
            {classes.map((c) => {
              const v = test.per_class[c]
              return (
                <tr key={c} className="border-b border-line last:border-0">
                  <td className={`${td} font-sans`}><ClassLabel label={c} /></td>
                  <td className={`${td} text-right`}>{fmtPct(v.precision)}</td>
                  <td className={`${td} text-right`}>{fmtPct(v.recall)}</td>
                  <td className={`${td} text-right ${v['f1-score'] < 0.9 ? 'text-medium' : ''}`}>{fmtPct(v['f1-score'])}</td>
                  <td className={`${td} text-right text-fg3`}>{fmtInt(v.support)}</td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </Card>

      <div className="mt-6 grid items-start gap-4 lg:grid-cols-2">
        <Card title="Model comparison" flush>
          <table className="w-full text-sm">
            <thead className="border-b border-line">
              <tr>
                <th className={th}>Model</th>
                <th className={`${th} text-right`}>Val. F1</th>
                <th className={`${th} text-right`}>Test F1</th>
                <th className={`${th} text-right`}>Accuracy</th>
                <th className={`${th} text-right`}>Train time</th>
              </tr>
            </thead>
            <tbody className="font-mono tabular-nums">
              {modelKeys.map((m) => (
                <tr key={m} className="border-b border-line last:border-0">
                  <td className={`${td} font-sans whitespace-nowrap`}>
                    <span className="inline-flex items-center gap-2">
                      <span className={`h-1.5 w-1.5 rounded-full ${m === selected ? 'bg-accent' : 'bg-transparent'}`} />
                      {NAMES[m] ?? m}
                    </span>
                  </td>
                  <td className={`${td} text-right ${m === selected ? 'text-fg' : 'text-fg2'}`}>{fmtPct(info.models[m].validation.macro.f1)}</td>
                  <td className={`${td} text-right text-fg2`}>{fmtPct(info.models[m].test.macro.f1)}</td>
                  <td className={`${td} text-right text-fg2`}>{fmtPct(info.models[m].test.accuracy)}</td>
                  <td className={`${td} text-right text-fg3`}>{info.models[m].train_seconds}s</td>
                </tr>
              ))}
            </tbody>
          </table>
          <p className="border-t border-line px-5 py-4 text-xs text-fg3">
            F1 here is macro F1. The model with the best validation F1 is used; the test set only reports final numbers
          </p>
        </Card>

        <Card title="Training data" flush>
          <dl className="px-5">
            {[
              ['Dataset', info.dataset],
              ['Rows loaded', fmtInt(info.cleaning.rows_loaded)],
              ['Duplicates removed', fmtInt(info.cleaning.duplicates_removed)],
              ['Dropped: blank or too-rare labels', fmtInt(Object.values(info.cleaning.dropped_labels).reduce((a, b) => a + b, 0))],
              ['Rows used', fmtInt(info.cleaning.rows_used)],
              ['Train / validation / test', `${fmtInt(info.split_sizes.train)} / ${fmtInt(info.split_sizes.validation)} / ${fmtInt(info.split_sizes.test)}`],
              ['Features', info.feature_columns.length],
            ].map(([k, v]) => (
              <div key={k} className="flex h-10 items-center justify-between gap-4 border-b border-line text-sm last:border-0">
                <dt className="text-fg2">{k}</dt>
                <dd className="font-mono tabular-nums text-fg">{v}</dd>
              </div>
            ))}
          </dl>
        </Card>
      </div>
    </>
  )
}
