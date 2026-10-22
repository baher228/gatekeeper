import { useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { api, REASON_LABELS, RECONSIDERABLE } from '../api'
import type { ReasonCategory } from '../api'
import { useAsync } from '../hooks'
import { Button, Card, ErrorState, Label, Loading, StatusBadge, Tag, fmtDate, timeAgo } from '../components/ui'
import { EvidencePanel, HistoryPanel, RuleChecks, VerdictSummary } from '../components/Evidence'

export default function ApplicantPage() {
  const { slug = '', id = '' } = useParams()
  const a = useAsync(() => api.applicant(id), [id])
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null)
  const [reason, setReason] = useState<ReasonCategory>('skill_gap')

  const act = async (fn: () => Promise<unknown>, ok: string) => {
    setBusy(true); setMsg(null)
    try { await fn(); setMsg({ ok: true, text: ok }); a.reload() } catch (e) { setMsg({ ok: false, text: (e as Error).message }) } finally { setBusy(false) }
  }

  if (a.loading && !a.data) return <Loading />
  if (a.error || !a.data) return <ErrorState message={a.error ?? 'Not found'} onRetry={a.reload} />
  const x = a.data
  const r = x.recommendation
  const rec = x.reconsideration
  const canRecheck = (x.status === 'declined' || x.status === 'waitlisted') && x.decline_reason && RECONSIDERABLE.includes(x.decline_reason)

  return (
    <div className="fade-in">
      <Link to={`/c/${slug}/applicants`} className="text-sm text-muted hover:text-fg">← Applicants</Link>
      <div className="mt-3 mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <h1 className="text-2xl font-semibold tracking-tight">{x.name}</h1>
            <StatusBadge status={x.status} />
            <Tag>{x.category}</Tag>
            {x.is_seed && <Tag>seed data</Tag>}
            <Tag>{x.decision_source === 'lead' ? 'decided by lead' : 'auto-routed'}</Tag>
          </div>
          <div className="mt-1.5 break-all font-mono text-xs text-muted">{[x.email, x.phone_masked, x.github && `github:${x.github}`, x.devpost && `devpost:${x.devpost}`, x.chat_handle].filter(Boolean).join(' · ')}</div>
        </div>
        <div className="font-mono text-xs text-muted">applied {fmtDate(x.created_at)}{x.decided_at && ` · decided ${fmtDate(x.decided_at)}`}</div>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_320px]">
        <div className="min-w-0 space-y-4">
          <Card><Label>What they build</Label><p className="mt-2 whitespace-pre-line text-sm leading-relaxed">{x.what_build}</p></Card>
          <Card><VerdictSummary a={x} /></Card>
          <Card><Label className="mb-4">Rule-by-rule</Label><RuleChecks r={r} /></Card>
          <div><Label className="mb-3">Evidence</Label><EvidencePanel r={r} /></div>
          <Card><Label className="mb-3">History model</Label><HistoryPanel r={r} /></Card>
        </div>
        <div className="space-y-4">
          <Card>
            <Label>Lead decision</Label>
            <div className="mt-3 grid grid-cols-2 gap-2">
              <Button variant="accept" disabled={busy} onClick={() => act(() => api.decide(x.id, { verdict: 'accept' }), 'Accepted · model retrained')}>Accept</Button>
              <Button variant="ask" disabled={busy} onClick={() => act(() => api.decide(x.id, { verdict: 'ask_more' }), 'Moved to queue')}>Ask more</Button>
            </div>
            <div className="mt-2 flex gap-2">
              <select aria-label="Decline reason" value={reason} onChange={e => setReason(e.target.value as ReasonCategory)} className="h-9 min-w-0 flex-1 rounded-lg border border-line bg-bg px-2 text-sm">
                {(Object.keys(REASON_LABELS) as ReasonCategory[]).map(k => <option key={k} value={k}>{REASON_LABELS[k]}</option>)}
              </select>
              <Button variant="decline" disabled={busy} onClick={() => act(() => api.decide(x.id, { verdict: 'decline', reason_category: reason }), 'Declined · model retrained')}>Decline</Button>
            </div>
            {msg && <p className={`mt-3 text-sm ${msg.ok ? 'text-muted' : 'text-decline'}`}>{msg.text}</p>}
          </Card>
          <Card>
            <Label>Quota · {r.quota.category}</Label>
            <div className="mt-2 text-sm">{r.quota.bypass_quota ? 'This category bypasses the quota.' : `${r.quota.used}/${r.quota.quota} seats used, ${r.quota.remaining} left at decision time.`}</div>
            {r.quota.outcome === 'waitlisted' && <div className="mt-1 text-sm text-ask">Waitlisted, rank #{r.quota.waitlist_rank} by score.</div>}
          </Card>
          <Card>
            <Label>Reconsideration</Label>
            {x.decline_reason === 'scam_abuse' && <p className="mt-2 text-sm text-muted">Declined for scam / abuse, so it’s never re-checked automatically.</p>}
            {rec.previous && <p className="mt-2 text-sm">Previously declined {fmtDate(rec.previous.declined_at)} for <span className="font-mono">{REASON_LABELS[rec.previous.reason_category] ?? rec.previous.reason_category}</span>.</p>}
            {rec.note && <p className="mt-2 rounded-lg border border-accept/20 bg-accept/[.04] px-3 py-2 text-sm">{rec.note}</p>}
            {canRecheck && <p className="mt-2 text-sm text-muted">{rec.eligible ? 'Cool-down is over, so this can be re-checked now.' : `Eligible for a re-check from ${fmtDate(rec.reconsider_after)}.`}</p>}
            {!canRecheck && !rec.previous && x.decline_reason !== 'scam_abuse' && <p className="mt-2 text-sm text-muted">Not declined, so nothing to reconsider.</p>}
            {canRecheck && <Button className="mt-3 w-full" disabled={busy || !rec.eligible} onClick={() => act(() => api.recheck(x.id), 'Re-checked with fresh evidence')}>{busy ? 'Re-checking…' : 'Re-check now'}</Button>}
          </Card>
          <Card>
            <Label>History</Label>
            <div className="mt-2 space-y-2">
              {x.decisions.length === 0 && <p className="text-sm text-muted">No decisions recorded yet.</p>}
              {x.decisions.map((d, i) => (
                <div key={i} className="flex items-start gap-2 text-sm">
                  <StatusBadge status={d.verdict} className="shrink-0" />
                  <div className="min-w-0"><div className="font-mono text-xs text-muted">{d.source} · {timeAgo(d.created_at)}{d.reason_category && ` · ${d.reason_category}`}</div>{d.note && <div className="text-sm">{d.note}</div>}</div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  )
}
