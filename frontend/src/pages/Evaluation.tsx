import { useState } from 'react'
import { api } from '../api'
import type { EvalVariant } from '../api'
import { useAsync, useElapsed } from '../hooks'
import { Button, Card, ErrorState, Label, Loading, PageHeader, cx, fmtDate, pct } from '../components/ui'

const METRICS: [keyof EvalVariant, string, boolean][] = [
  ['accuracy', 'Accuracy (ask counts as wrong)', true], ['accuracy_on_decided', 'Accuracy on auto-decided', true],
  ['accept_precision', 'Accept precision', true], ['accept_recall', 'Accept recall', true],
  ['decline_precision', 'Decline precision', true], ['decline_recall', 'Decline recall', true],
  ['false_block_rate', 'False-block rate on real people', false], ['ask_rate', 'Ask rate (sent to lead)', false],
]
const NAMES: Record<string, string> = { rules_only: '(a) Rules only', rules_plus_history: '(b) Rules + history model' }

export default function EvalPage() {
  const r = useAsync(() => api.evalReport(), [])
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const elapsed = useElapsed(busy)
  const run = async () => { setBusy(true); setErr(null); try { r.setData(await api.runEval()) } catch (e) { setErr((e as Error).message) } finally { setBusy(false) } }
  const d = r.data
  const kinds = d ? Object.keys(d.variants[0]?.by_kind ?? {}) : []
  const missing = r.error?.startsWith('404') || r.error?.toLowerCase().includes('not found')
  return (
    <div>
      <PageHeader label="Evaluation · labelled test set" title="How good are the calls?"
        sub="Track 1 is judged on correct accept and decline calls, clear reasons, and few real people wrongly blocked. This page shows the real numbers from the held-out synthetic test set. The history model never sees the test set."
        right={<><Button disabled={busy} onClick={run}>{busy ? `Running… ${elapsed}s` : 'Re-run evaluation'}</Button></>} />
      {err && <div className="mb-4"><ErrorState message={err} /></div>}
      {r.loading && <Loading label="Loading latest report" />}
      {r.error && !d && (missing ? <Card><p className="text-sm text-muted">No report yet. Run <span className="font-mono text-fg">python -m app.eval</span> or press “Re-run evaluation”.</p></Card> : <ErrorState message={r.error} onRetry={r.reload} />)}
      {d && (
        <div className="fade-in space-y-4">
          <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
            {[['Test applicants', d.test_set.n], ['Label: accept', d.test_set.n_accept], ['Label: decline', d.test_set.n_decline], ['Scammers / edge cases', `${d.test_set.n_scam} / ${d.test_set.n_edge}`]].map(([k, v]) => (
              <Card key={k as string}><Label>{k}</Label><div className="mt-2 font-mono text-2xl">{v}</div></Card>
            ))}
          </div>
          <Card pad={false} className="overflow-x-auto">
            <table className="w-full min-w-[520px] text-sm">
              <thead><tr className="border-b border-line font-mono text-[11px] uppercase tracking-[0.12em] text-muted">
                <th className="px-4 py-3 text-left font-normal">Metric</th>
                {d.variants.map(v => <th key={v.name} className="px-4 py-3 text-right font-normal">{NAMES[v.name] ?? v.name}</th>)}
              </tr></thead>
              <tbody>
                {METRICS.map(([k, label, higher]) => {
                  const vals = d.variants.map(v => v[k] as number)
                  const best = higher ? Math.max(...vals) : Math.min(...vals)
                  return (
                    <tr key={k} className="border-b border-line/60 last:border-0">
                      <td className="px-4 py-2.5 text-muted">{label}</td>
                      {vals.map((v, i) => <td key={i} className={cx('px-4 py-2.5 text-right font-mono', v === best && vals.some(x => x !== v) ? 'text-fg' : 'text-muted')}>{pct(v)}</td>)}
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </Card>
          <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
            {d.variants.map(v => (
              <Card key={v.name}>
                <Label>Confusion · {NAMES[v.name] ?? v.name}</Label>
                <table className="mt-3 w-full text-sm">
                  <thead><tr className="font-mono text-[11px] text-muted"><th className="py-1 text-left font-normal">label ↓ / routed →</th>{['accept', 'ask', 'decline'].map(c => <th key={c} className="py-1 text-right font-normal">{c}</th>)}</tr></thead>
                  <tbody>{(['accept', 'decline'] as const).map(lab => (
                    <tr key={lab} className="border-t border-line/60"><td className="py-1.5 font-mono text-xs">{lab}</td>{(['accept', 'ask', 'decline'] as const).map(c => <td key={c} className={cx('py-1.5 text-right font-mono', c === lab ? 'text-fg' : 'text-muted')}>{v.confusion_matrix?.[lab]?.[c] ?? '–'}</td>)}</tr>
                  ))}</tbody>
                </table>
              </Card>
            ))}
          </div>
          {kinds.length > 0 && (
            <Card pad={false} className="overflow-x-auto">
              <div className="px-4 pt-4"><Label>Accuracy by applicant type (incl. real-but-unusual people and scammers)</Label></div>
              <table className="mt-2 w-full min-w-[520px] text-sm">
                <thead><tr className="border-b border-line font-mono text-[11px] uppercase tracking-[0.12em] text-muted"><th className="px-4 py-2 text-left font-normal">Type</th><th className="px-4 py-2 text-right font-normal">n</th>{d.variants.map(v => <th key={v.name} className="px-4 py-2 text-right font-normal">{NAMES[v.name] ?? v.name}</th>)}</tr></thead>
                <tbody>{kinds.map(k => (
                  <tr key={k} className="border-b border-line/60 last:border-0"><td className="px-4 py-2 font-mono text-xs">{k}</td><td className="px-4 py-2 text-right font-mono text-muted">{d.variants[0].by_kind?.[k]?.n}</td>{d.variants.map(v => { const b = v.by_kind?.[k]; return <td key={v.name} className="px-4 py-2 text-right font-mono">{b ? <>{pct(b.accuracy)} <span className="text-faint">· ask {pct(b.ask_rate)}</span></> : '–'}</td> })}</tr>
                ))}</tbody>
              </table>
            </Card>
          )}
          <Card>
            <Label>Method & caveats</Label>
            <ul className="mt-3 space-y-1.5 text-sm text-muted">
              <li>Test set: {d.test_set.source}. Training history: {d.train_set.n} decisions, {d.train_set.source}.</li>
              {d.notes.map((n, i) => <li key={i}>{n}</li>)}
              <li className="font-mono text-xs">generated {fmtDate(d.generated_at)} {new Date(d.generated_at).toLocaleTimeString('en-GB')}</li>
            </ul>
          </Card>
        </div>
      )}
    </div>
  )
}
